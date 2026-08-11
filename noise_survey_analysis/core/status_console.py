"""Terminal status pane for the live Bokeh server.

The dashboard emits a lot of detail while parsing files and streaming viewport
updates. Sending all of it to the console makes the useful signal impossible to
read, so this module provides the small amount of output that is actually worth
watching:

* a one-off startup summary showing which files were loaded for each position,
  and whether that position has audio and spectral data;
* a rolling pane of the last few events (viewport streams, lazy loads, audio
  transport) with a live elapsed timer on whatever is currently running.

Everything else keeps going to the log file at full detail. See
``configure_logging`` in ``main`` for how the two are wired together.

The pane repaints in place using ANSI cursor movement. That only works when
stdout is a real terminal and nothing else writes to it concurrently, so
``WARNING`` and above are routed through :class:`StatusConsoleHandler` rather
than a plain ``StreamHandler``. When stdout is redirected or the terminal has no
ANSI support, the pane degrades to plain appended lines and stays readable.
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import threading
import time
from collections import deque
from typing import Deque, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

# Number of past events kept visible above the live phase line.
DEFAULT_HISTORY_LINES = 8

# How often the ticker repaints the elapsed timer, in seconds.
_TICK_INTERVAL = 0.25

# A phase running longer than this is called out, so a stall is obvious.
_SLOW_PHASE_SECONDS = 5.0

_ESC = "\x1b["
_RESET = f"{_ESC}0m"
_DIM = f"{_ESC}2m"
_CLEAR_LINE = f"{_ESC}2K"

_CATEGORY_COLOURS = {
    "data": f"{_ESC}36m",    # cyan
    "audio": f"{_ESC}35m",   # magenta
    "load": f"{_ESC}33m",    # yellow
    "ok": f"{_ESC}32m",      # green
    "warn": f"{_ESC}31m",    # red
}


def _enable_windows_ansi() -> bool:
    """Turn on virtual terminal processing so ANSI codes work in PowerShell."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


class StatusConsole:
    """A fixed-height, in-place status pane written to stdout.

    Thread safe. The VLC playback monitor, the Bokeh session callbacks and the
    internal ticker all write to it, so every mutation takes the lock and every
    repaint is atomic.
    """

    def __init__(self, history_lines: int = DEFAULT_HISTORY_LINES, stream=None) -> None:
        self._stream = stream if stream is not None else sys.stdout
        self._history: Deque[Tuple[str, str]] = deque(maxlen=max(1, history_lines))
        self._phase: Optional[Tuple[str, str, float]] = None  # category, text, started_at
        self._lock = threading.RLock()
        self._painted_lines = 0
        self._ticker: Optional[threading.Thread] = None
        self._stop_ticker = threading.Event()

        is_tty = bool(getattr(self._stream, "isatty", lambda: False)())
        self.ansi = is_tty and _enable_windows_ansi()
        # Without a TTY we still emit events, just as plain appended lines.
        self.enabled = True

    # -- public API ---------------------------------------------------------

    def event(self, category: str, text: str) -> None:
        """Record a completed event in the rolling history."""
        with self._lock:
            self._history.append((category, text))
            if self.ansi:
                self._repaint()
            else:
                self._append(category, text)

    def start_phase(self, category: str, text: str) -> None:
        """Mark the start of ongoing work, shown with a live elapsed timer."""
        with self._lock:
            self._phase = (category, text, time.perf_counter())
            if self.ansi:
                self._ensure_ticker()
                self._repaint()
            else:
                # No cursor control, so no live timer. Bracketing the work with
                # a start and a finish line still shows where a stall began.
                self._append(category, f"{text} ...")

    def end_phase(self, result: Optional[str] = None, category: Optional[str] = None) -> None:
        """Finish the current phase, optionally promoting it into the history."""
        with self._lock:
            phase = self._phase
            self._phase = None
            if phase is not None and result is not None:
                elapsed = time.perf_counter() - phase[2]
                line = f"{result}  {_format_elapsed(elapsed)}"
                self._history.append((category or phase[0], line))
                if not self.ansi:
                    self._append(category or phase[0], line)
            if self.ansi:
                self._repaint()

    def _append(self, category: str, text: str) -> None:
        """Plain fallback for redirected output or terminals without ANSI."""
        try:
            self._stream.write(f"{_format_row(category, text, False)}\n")
            self._flush()
        except Exception:
            self.enabled = False

    def write_block(self, lines: Sequence[str]) -> None:
        """Print a static block (the startup summary) above the pane."""
        with self._lock:
            self._erase()
            for line in lines:
                self._stream.write(f"{line}\n")
            self._flush()
            self._repaint()

    def close(self) -> None:
        self._stop_ticker.set()
        with self._lock:
            self._phase = None
            self._repaint()

    # -- internals ----------------------------------------------------------

    def _ensure_ticker(self) -> None:
        if self._ticker is not None and self._ticker.is_alive():
            return
        self._stop_ticker.clear()
        self._ticker = threading.Thread(
            target=self._tick_loop, name="status-console-ticker", daemon=True
        )
        self._ticker.start()

    def _tick_loop(self) -> None:
        # Only repaints while a phase is live, so an idle server writes nothing.
        while not self._stop_ticker.wait(_TICK_INTERVAL):
            with self._lock:
                if self._phase is None:
                    return
                self._repaint()

    def _width(self) -> int:
        try:
            return max(40, shutil.get_terminal_size(fallback=(120, 30)).columns)
        except Exception:
            return 120

    def _render_lines(self) -> list:
        width = self._width() - 1
        lines = []
        for category, text in self._history:
            lines.append(_truncate(_format_row(category, text, self.ansi), width))
        if self._phase is not None:
            category, text, started_at = self._phase
            elapsed = time.perf_counter() - started_at
            marker = "!" if elapsed >= _SLOW_PHASE_SECONDS else "*"
            body = f"{marker} {text}  {_format_elapsed(elapsed)}"
            lines.append(_truncate(_format_row(category, body, self.ansi), width))
        return lines

    def _erase(self) -> None:
        if not self.ansi or self._painted_lines <= 0:
            self._painted_lines = 0
            return
        self._stream.write(f"{_ESC}{self._painted_lines}A")
        self._stream.write(f"{_CLEAR_LINE}{_ESC}1B" * self._painted_lines)
        self._stream.write(f"{_ESC}{self._painted_lines}A")
        self._painted_lines = 0

    def _repaint(self) -> None:
        if not self.enabled or not self.ansi:
            return
        try:
            self._erase()
            lines = self._render_lines()
            for line in lines:
                self._stream.write(f"{_CLEAR_LINE}{line}\n")
            self._painted_lines = len(lines)
            self._flush()
        except Exception:
            # A broken pane must never take the dashboard down with it.
            self.ansi = False
            self._painted_lines = 0

    def _flush(self) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass


def _format_row(category: str, text: str, ansi: bool) -> str:
    tag = f"{category:<5}"
    if not ansi:
        return f"  {tag}  {text}"
    colour = _CATEGORY_COLOURS.get(category, "")
    return f"  {colour}{tag}{_RESET}  {text}"


def _format_elapsed(seconds: float) -> str:
    if seconds < 1.0:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60.0:
        return f"{seconds:.1f} s"
    return f"{int(seconds // 60)}m {seconds % 60:04.1f}s"


def _truncate(text: str, width: int) -> str:
    # Colour codes are zero-width on screen, so measure the visible text only.
    visible = 0
    out = []
    index = 0
    while index < len(text):
        if text[index] == "\x1b":
            end = text.find("m", index)
            if end == -1:
                break
            out.append(text[index : end + 1])
            index = end + 1
            continue
        if visible >= width:
            out.append(_RESET)
            return "".join(out)
        out.append(text[index])
        visible += 1
        index += 1
    return "".join(out)


class _NullStatusConsole:
    """No-op stand-in used for static export and CLI runs."""

    ansi = False
    enabled = False

    def event(self, category: str, text: str) -> None: ...
    def start_phase(self, category: str, text: str) -> None: ...
    def end_phase(self, result=None, category=None) -> None: ...
    def write_block(self, lines) -> None: ...
    def close(self) -> None: ...


_console: object = _NullStatusConsole()


def get_console():
    return _console


def install(history_lines: int = DEFAULT_HISTORY_LINES) -> StatusConsole:
    """Create the process-wide status pane and return it."""
    global _console
    if not isinstance(_console, StatusConsole):
        _console = StatusConsole(history_lines=history_lines)
    return _console  # type: ignore[return-value]


def disable() -> None:
    global _console
    _console = _NullStatusConsole()


# -- convenience wrappers ---------------------------------------------------

def event(category: str, text: str) -> None:
    _console.event(category, text)


def start_phase(category: str, text: str) -> None:
    _console.start_phase(category, text)


def end_phase(result: Optional[str] = None, category: Optional[str] = None) -> None:
    _console.end_phase(result, category)


def write_block(lines: Sequence[str]) -> None:
    _console.write_block(lines)


def _format_span(df) -> str:
    """Render the datetime span of a dataframe as ``dd/mm HH:MM -> dd/mm HH:MM``."""
    if df is None or getattr(df, "empty", True) or "Datetime" not in df.columns:
        return ""
    try:
        first = df["Datetime"].iloc[0]
        last = df["Datetime"].iloc[-1]
        return f"{first:%d/%m %H:%M} -> {last:%d/%m %H:%M}"
    except Exception:
        return ""


def _peek_log_step_ms(log_file_paths) -> float:
    """Estimate a deferred log file's native time step without parsing it."""
    try:
        # Imported here rather than at module scope: data_manager imports this
        # module, and data_processors pulls in the data layer, so a top-level
        # import would close an import cycle.
        from noise_survey_analysis.core.data_processors import _peek_log_file_time_step_ms
        return float(_peek_log_file_time_step_ms(log_file_paths) or 0.0)
    except Exception as exc:
        logger.debug("Could not peek log sample rate: %s", exc)
        return 0.0


def _total_size_mb(log_file_paths) -> float:
    total = 0
    for entry in log_file_paths or []:
        try:
            total += os.path.getsize(str(entry.get("file_path", "")))
        except OSError:
            continue
    return total / (1024 * 1024)


def _format_rate(seconds) -> str:
    if not seconds:
        return ""
    if seconds < 1:
        return f"{seconds:g} s"
    return f"{int(seconds)} s"


def build_startup_summary(app_data, config_path=None, job_number=None, cache_hit=None) -> list:
    """Build the one-off summary block describing what was loaded per position.

    Deliberately reports what the dashboard will actually be able to *show* --
    whether a position has spectra, and whether it has audio -- because those
    are the two things that silently differ between meter types and determine
    which panels stay empty.
    """
    lines = ["", "Noise Survey Analysis" + (f" -- job {job_number}" if job_number else "")]
    if config_path:
        lines.append(f"config  {config_path}")
    lines.append("")

    total_files = 0
    positions_with_audio = 0

    try:
        position_names = app_data.positions()
    except Exception:
        position_names = []

    for name in position_names:
        try:
            position = app_data[name]
        except Exception:
            continue

        parsers = "/".join(sorted(position.parser_types_used or {"?"}))
        lines.append(f"{name}   [{parsers}]")

        if position.has_overview_totals:
            total_files += 1
            spectral = "1/3-oct" if position.has_overview_spectral else "broadband"
            rows = f"{len(position.overview_totals):,} rows"
            lines.append(
                f"    summary  {rows:>14}  {_format_span(position.overview_totals):<28}{spectral}"
            )

        log_paths = getattr(position, "log_file_paths", []) or []
        if position.has_log_totals:
            total_files += len(log_paths) or 1
            spectral = "1/3-oct" if position.has_log_spectral else "broadband"
            rows = f"{len(position.log_totals):,} rows"
            lines.append(
                f"    log      {rows:>14}  {_format_span(position.log_totals):<28}{spectral}"
            )
        elif log_paths:
            # Log files are deferred until first zoom, so their real sample rate
            # is not in sample_periods_seconds yet (that still describes the
            # summary file). Peek at the file head instead -- roughly 8 KB per
            # file, fast even on a network drive -- so the reported resolution
            # is the log's own rather than the summary's.
            total_files += len(log_paths)
            names = ", ".join(
                os.path.basename(str(entry.get("file_path", "?"))) for entry in log_paths[:2]
            )
            if len(log_paths) > 2:
                names += f", +{len(log_paths) - 2} more"

            detail = []
            step_ms = _peek_log_step_ms(log_paths)
            if step_ms:
                detail.append(_format_rate(step_ms / 1000.0))
            size_mb = _total_size_mb(log_paths)
            if size_mb:
                detail.append(f"{size_mb:,.0f} MB" if size_mb >= 1 else "<1 MB")
            # ASCII only: the Windows console codepage mangles punctuation
            # like the middle dot into a replacement character.
            suffix = f"   {', '.join(detail)}" if detail else ""
            lines.append(f"    log      {'deferred':>14}  {names}{suffix}")

        if position.has_audio_files:
            positions_with_audio += 1
            count = len(position.audio_files_list)
            total_files += count
            folder = os.path.basename(str(position.audio_files_path or "").rstrip("\\/"))
            lines.append(f"    audio    {f'{count:,} files':>14}  {folder}")
        else:
            lines.append(f"    audio    {'--':>14}  none")

    lines.append("")
    audio_note = (
        "no audio" if positions_with_audio == 0
        else f"audio on {positions_with_audio} of {len(position_names)}"
    )
    footer = f"{len(position_names)} positions - {total_files} files - {audio_note}"
    if cache_hit is not None:
        footer += f" - parse cache {'HIT' if cache_hit else 'MISS'}"
    lines.append(footer)
    lines.append("")
    return lines


class StatusConsoleHandler(logging.Handler):
    """Route ``WARNING`` and above into the pane instead of raw stdout.

    Writing directly to stdout would land in the middle of the repainting pane
    and corrupt the cursor arithmetic, so warnings become ordinary pane events.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            category = "warn" if record.levelno >= logging.WARNING else "data"
            _console.event(category, self.format(record))
        except Exception:
            pass
