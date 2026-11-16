"""Localhost media server for browser audio playback (``audio_backend = 'browser'``).

The dashboard plays survey audio in the page instead of through python-vlc. For that the
page fetches short clips from this server::

    GET /clip?pos=<position>&start_ms=<epoch ms>&dur_s=<seconds>&token=<token>

The answer is an in-memory PCM16 mono WAV holding only the frames of that window. The window is
cut from the position's anchored audio file index, so it may span several recordings (the true
start time of every file is used) and gaps between recordings come out as silence. ``start_ms``
is the *audio* time, i.e. the tap time minus the position's effective offset, exactly what the
VLC path hands to ``AudioPlaybackHandler.play``.

Security model (same style as ``control/control_server.py``): binds ``127.0.0.1`` only, picks a
random free port, and every dashboard session registers its own random token; a request without
a valid token is refused. CORS is granted only to ``localhost`` / ``127.0.0.1`` origins so the
page's Web Audio graph (gain, limiter) may read the samples.
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import struct
import threading
from collections import OrderedDict
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from math import gcd
from typing import Dict, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlparse

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_CLIP_SECONDS = 60.0
MAX_CLIP_SECONDS = 120.0
MIN_CLIP_SECONDS = 0.05
# A request this close before the first recording starts at that recording (matches
# AudioPlaybackHandler.SNAP_TO_FIRST_FILE_TOLERANCE_SECONDS); anything earlier has no audio.
SNAP_TO_FIRST_FILE_TOLERANCE_SECONDS = 60.0
# Rendered clips kept for Range requests / replays.
CACHE_MAX_ENTRIES = 8
CACHE_MAX_BYTES = 96 * 1024 * 1024

_EXPOSED_HEADERS = ("X-Clip-Start-Ms, X-Clip-Duration-Ms, X-Clip-Frames, X-Sample-Rate, "
                    "X-File-Name, X-File-Start-Ms, Content-Range, Accept-Ranges, Content-Length")
_LOCAL_ORIGIN = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$", re.IGNORECASE)

# One entry per file: (path, start_ms since the epoch, duration in seconds), sorted by start.
FileIndex = Sequence[Tuple[str, float, float]]


class NoAudio(Exception):
    """No recording covers the requested window."""


@dataclass
class Clip:
    wav: bytes
    start_ms: float      # where the clip really starts (after snapping to the first file)
    duration_ms: float
    frames: int
    sample_rate: int
    file_name: str
    file_start_ms: float


def _read_segment(path: str, start_s: float, end_s: float):
    import soundfile as sf

    with sf.SoundFile(path) as handle:
        rate = handle.samplerate
        first = max(0, int(round(start_s * rate)))
        last = min(len(handle), int(round(end_s * rate)))
        if last <= first:
            return None
        handle.seek(first)
        audio = handle.read(last - first, dtype='float32', always_2d=True)
    return audio.mean(axis=1), rate


def _encode_wav(pcm: np.ndarray, rate: int) -> bytes:
    data = pcm.astype('<i2', copy=False).tobytes()
    header = (b'RIFF' + struct.pack('<I', 36 + len(data)) + b'WAVE'
              + b'fmt ' + struct.pack('<IHHIIHH', 16, 1, 1, rate, rate * 2, 2, 16)
              + b'data' + struct.pack('<I', len(data)))
    return header + data


def resolve_window(files: FileIndex, start_ms: float, dur_s: float) -> Tuple[float, float, List[tuple]]:
    """Snap and clip the request against the file index.

    Returns ``(start_ms, end_ms, overlapping_files)`` or raises ``NoAudio``.
    """
    valid = sorted((f for f in files if f[2] and f[2] > 0), key=lambda f: f[1])
    if not valid:
        raise NoAudio("no audio files indexed")
    first_start = valid[0][1]
    last_end = max(f[1] + f[2] * 1000.0 for f in valid)
    if start_ms < first_start:
        if first_start - start_ms > SNAP_TO_FIRST_FILE_TOLERANCE_SECONDS * 1000.0:
            raise NoAudio("before the first recording")
        start_ms = first_start
    if start_ms >= last_end:
        raise NoAudio("after the last recording")
    end_ms = min(start_ms + dur_s * 1000.0, last_end)
    hits = [f for f in valid if f[1] < end_ms and f[1] + f[2] * 1000.0 > start_ms]
    if not hits:
        raise NoAudio("in a gap between recordings")
    return start_ms, end_ms, hits


def build_clip(files: FileIndex, start_ms: float, dur_s: float = DEFAULT_CLIP_SECONDS) -> Clip:
    """Cut ``[start_ms, start_ms + dur_s)`` from ``files`` as one mono PCM16 WAV."""
    from scipy.signal import resample_poly

    dur_s = min(max(float(dur_s), MIN_CLIP_SECONDS), MAX_CLIP_SECONDS)
    start_ms, end_ms, hits = resolve_window(files, float(start_ms), dur_s)

    rate = None
    buffer = None
    filled = False
    for path, file_start, file_dur in hits:
        piece_start = max(start_ms, file_start)
        piece_end = min(end_ms, file_start + file_dur * 1000.0)
        segment = _read_segment(path, (piece_start - file_start) / 1000.0, (piece_end - file_start) / 1000.0)
        if segment is None:
            continue
        mono, file_rate = segment
        if rate is None:
            rate = int(file_rate)
            buffer = np.zeros(int(round((end_ms - start_ms) / 1000.0 * rate)), dtype=np.float32)
        if int(file_rate) != rate:
            divisor = gcd(rate, int(file_rate))
            mono = resample_poly(mono, rate // divisor, int(file_rate) // divisor)
        at = int(round((piece_start - start_ms) / 1000.0 * rate))
        chunk = np.asarray(mono, dtype=np.float32)[:max(0, len(buffer) - at)]
        buffer[at:at + len(chunk)] = chunk
        filled = filled or len(chunk) > 0
    if not filled or buffer is None or rate is None:
        raise NoAudio("recordings could not be read")

    pcm = (np.clip(buffer, -1.0, 1.0) * 32767.0).astype(np.int16)
    named = next((f for f in hits if f[1] <= start_ms < f[1] + f[2] * 1000.0), hits[0])
    return Clip(
        wav=_encode_wav(pcm, rate),
        start_ms=start_ms,
        duration_ms=len(pcm) / rate * 1000.0,
        frames=len(pcm),
        sample_rate=rate,
        file_name=named[0].replace('\\', '/').rsplit('/', 1)[-1],
        file_start_ms=named[1],
    )


def _parse_range(header: str, size: int) -> Optional[Tuple[int, int]]:
    match = re.match(r"^bytes=(\d*)-(\d*)$", (header or '').strip())
    if not match:
        return None
    first, last = match.groups()
    if first == '' and last == '':
        return None
    if first == '':
        length = int(last)
        if length <= 0:
            return None
        return max(0, size - length), size - 1
    begin = int(first)
    end = int(last) if last != '' else size - 1
    end = min(end, size - 1)
    if begin >= size or end < begin:
        return None
    return begin, end


class _ClipCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._items: "OrderedDict[tuple, Clip]" = OrderedDict()
        self._bytes = 0

    def get(self, key):
        with self._lock:
            clip = self._items.get(key)
            if clip is not None:
                self._items.move_to_end(key)
            return clip

    def put(self, key, clip: Clip):
        with self._lock:
            if key in self._items:
                self._bytes -= len(self._items[key].wav)
            self._items[key] = clip
            self._items.move_to_end(key)
            self._bytes += len(clip.wav)
            while self._items and (len(self._items) > CACHE_MAX_ENTRIES or self._bytes > CACHE_MAX_BYTES):
                _, dropped = self._items.popitem(last=False)
                self._bytes -= len(dropped.wav)

    def drop_token(self, token: str):
        with self._lock:
            for key in [k for k in self._items if k[0] == token]:
                self._bytes -= len(self._items.pop(key).wav)


class _ClipHandler(BaseHTTPRequestHandler):
    owner: "MediaServer"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: D401 - BaseHTTPRequestHandler API
        logger.debug("MediaServer: " + fmt, *args)

    # -- helpers -------------------------------------------------------------------------
    def _cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin and _LOCAL_ORIGIN.match(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Expose-Headers", _EXPOSED_HEADERS)

    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    # -- verbs ---------------------------------------------------------------------------
    def do_OPTIONS(self):  # noqa: N802
        self.send_response(204)
        self._cors_headers()
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Range")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):  # noqa: N802
        try:
            self._handle_get()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logger.debug("MediaServer: client went away")
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("MediaServer: unexpected error")
            try:
                self._send_json(500, {"error": f"internal error: {exc}"})
            except Exception:
                pass

    def _handle_get(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") == "/health":
            self._send_json(200, {"status": "ok"})
            return
        if parsed.path.rstrip("/") != "/clip":
            self._send_json(404, {"error": "not found"})
            return

        query = {k: v[0] for k, v in parse_qs(parsed.query).items() if v}
        token = query.get("token", "")
        index = self.owner.index_for(token)
        if index is None:
            self._send_json(401, {"error": "unauthorized"})
            return

        position = query.get("pos", "")
        files = index.get(position)
        if files is None:
            self._send_json(404, {"error": f"no audio for position {position!r}"})
            return
        try:
            start_ms = float(query["start_ms"])
            dur_s = float(query.get("dur_s", DEFAULT_CLIP_SECONDS))
            if not (np.isfinite(start_ms) and np.isfinite(dur_s)) or dur_s <= 0:
                raise ValueError
        except (KeyError, ValueError):
            self._send_json(400, {"error": "start_ms and dur_s must be finite numbers"})
            return

        key = (token, position, int(round(start_ms)), round(min(dur_s, MAX_CLIP_SECONDS), 3))
        clip = self.owner.cache.get(key)
        if clip is None:
            try:
                clip = build_clip(files, start_ms, dur_s)
            except NoAudio as exc:
                self._send_json(404, {"error": f"no audio: {exc}"})
                return
            self.owner.cache.put(key, clip)

        size = len(clip.wav)
        byte_range = _parse_range(self.headers.get("Range", ""), size)
        if byte_range is None:
            begin, end, code = 0, size - 1, 200
        else:
            (begin, end), code = byte_range, 206
        body = clip.wav[begin:end + 1]
        self.send_response(code)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        if code == 206:
            self.send_header("Content-Range", f"bytes {begin}-{end}/{size}")
        self.send_header("Cache-Control", "private, max-age=300")
        self.send_header("X-Clip-Start-Ms", str(int(round(clip.start_ms))))
        self.send_header("X-Clip-Duration-Ms", str(int(round(clip.duration_ms))))
        self.send_header("X-Clip-Frames", str(clip.frames))
        self.send_header("X-Sample-Rate", str(clip.sample_rate))
        self.send_header("X-File-Name", clip.file_name)
        self.send_header("X-File-Start-Ms", str(int(round(clip.file_start_ms))))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)


class MediaServer:
    """One localhost server per process; each dashboard session registers its own file index."""

    def __init__(self):
        self._lock = threading.Lock()
        self._indexes: Dict[str, Dict[str, list]] = {}
        self.cache = _ClipCache()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    @property
    def port(self) -> Optional[int]:
        return self._server.server_address[1] if self._server is not None else None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}" if self.port else ""

    def start(self, port: int = 0) -> int:
        """Start listening on ``127.0.0.1`` (``port=0`` picks a free one). Idempotent."""
        with self._lock:
            if self.is_running:
                return self.port  # type: ignore[return-value]
            owner = self

            class Handler(_ClipHandler):
                pass

            Handler.owner = owner  # type: ignore[attr-defined]
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            server.daemon_threads = True
            self._server = server
            self._thread = threading.Thread(target=server.serve_forever, name="nsa-media-server", daemon=True)
            self._thread.start()
            logger.info("MediaServer: listening on http://127.0.0.1:%d", self.port)
            return self.port  # type: ignore[return-value]

    def stop(self) -> None:
        with self._lock:
            server, thread = self._server, self._thread
            self._server = self._thread = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)

    def register_session(self, index: Dict[str, FileIndex]) -> str:
        """Register ``{position: [(path, start_ms, duration_s), ...]}``; returns the session token."""
        token = secrets.token_hex(16)
        clean = {pos: sorted(((str(p), float(s), float(d)) for p, s, d in files), key=lambda f: f[1])
                 for pos, files in index.items() if files}
        with self._lock:
            self._indexes[token] = clean
        return token

    def unregister_session(self, token: Optional[str]) -> None:
        if not token:
            return
        with self._lock:
            self._indexes.pop(token, None)
        self.cache.drop_token(token)

    def index_for(self, token: str) -> Optional[Dict[str, list]]:
        with self._lock:
            return self._indexes.get(token or "")


_media_server: Optional[MediaServer] = None
_media_server_lock = threading.Lock()


def get_media_server() -> MediaServer:
    """The process-wide server, started on first use."""
    global _media_server
    with _media_server_lock:
        if _media_server is None:
            _media_server = MediaServer()
        server = _media_server
    server.start()
    return server


def unregister_session(token: Optional[str]) -> None:
    """Forget a session's index without starting the server if it is not running."""
    with _media_server_lock:
        server = _media_server
    if server is not None:
        server.unregister_session(token)


def build_file_index(file_info_by_position: Dict[str, list]) -> Dict[str, List[Tuple[str, float, float]]]:
    """Convert ``AudioPlaybackHandler.file_info_by_position`` (path, aware datetime, seconds) to
    the epoch-millisecond index this server uses."""
    index: Dict[str, List[Tuple[str, float, float]]] = {}
    for position, files in (file_info_by_position or {}).items():
        rows = []
        for path, start, duration in files:
            try:
                rows.append((str(path), float(start.timestamp()) * 1000.0, float(duration)))
            except Exception:
                continue
        if rows:
            index[position] = rows
    return index
