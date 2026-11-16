"""Static-export payload helpers.

A static HTML export has no server to stream log-resolution data after load, so the
spectrogram's full prepared log dataset is embedded up front. These pure helpers build that
payload; ``DashBuilder`` calls them (and keeps thin wrappers of the same names).

Size is the whole problem with static exports (a three-meter, week-long survey was 590 MB), so
this module also holds the reductions:

* arrays stay NumPy (Bokeh embeds them as base64 binary, not as JSON text);
* spectra are quantised to ``uint8`` and decoded lazily in the browser
  (``app.session.decodeStaticPayload`` in sessionManager.js);
* the spectrum of the initially shown parameter is embedded once, not twice;
* ``--static-detail`` chooses how much 1 s log data goes in (full / around regions and markers /
  none), with ``auto`` estimating the size first.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# --- Static detail policy -------------------------------------------------------------------
STATIC_DETAIL_CHOICES = ('auto', 'full', 'lines', 'regions', 'overview')
# ``lines`` keeps the full 1 s line data and energy-averages the 1 s spectrogram in time to the finest of
# these uniform steps (seconds) that keeps the document under the threshold.
STATIC_LOG_STEPS_S = (2, 3, 5, 10, 15, 30)
# ``auto`` embeds the full 1 s log when the estimated document is under this many megabytes and
# falls back to ``regions`` above it.
STATIC_AUTO_MAX_MB = 150.0
# Log detail kept around each region / marker in ``regions`` mode. A region's background LA90
# looks 300 s either side by default, so the pad matches that and metrics agree with the live view.
STATIC_REGION_PAD_S = 300.0
STATIC_MARKER_PAD_S = 60.0
# Quantisation grid for embedded spectra (dB).
STATIC_QUANT_STEP_DB = 0.5
# BokehJS + the dashboard bundle + overview data: independent of survey length.
_STATIC_FIXED_OVERHEAD_BYTES = 8 * 1024 * 1024
_BASE64_FACTOR = 4.0 / 3.0


def to_list(value: Any) -> list:
    if value is None:
        return []
    if hasattr(value, 'tolist'):
        value = value.tolist()
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


# --- Quantisation ----------------------------------------------------------------------------
def quantize_levels(levels: Any, step: float = STATIC_QUANT_STEP_DB) -> Tuple[np.ndarray, float, float]:
    """Quantise a spectrum array to ``uint8``.

    Returns ``(codes, offset_db, step_db)`` with ``value ~= offset_db + code * step_db``.

    Integer-valued input (the prepared spectra are rounded to whole dB) whose range fits in 255
    uses a 1 dB step, which is exact. Otherwise the grid is ``step`` (0.5 dB), widened by doubling
    when the range needs more than 255 steps. Worst-case error is ``step_db / 2``; non-finite
    values map to the lowest code.
    """
    arr = np.asarray(levels)
    if arr.size == 0:
        return np.zeros(0, dtype=np.uint8), 0.0, float(step)
    if arr.dtype.kind in 'iu':
        low = int(arr.min())
        high = int(arr.max())
        if high - low <= 255:
            return (arr.astype(np.int32) - low).astype(np.uint8), float(low), 1.0
        arr = arr.astype(np.float32)
    else:
        arr = arr.astype(np.float32, copy=False)
    finite = np.isfinite(arr)
    if not finite.any():
        return np.zeros(arr.shape, dtype=np.uint8), 0.0, float(step)
    low = float(np.floor(arr[finite].min()))
    high = float(arr[finite].max())
    use_step = float(step)
    while (high - low) / use_step > 255.0:
        use_step *= 2.0
    codes = np.clip(np.rint((np.where(finite, arr, low) - low) / use_step), 0, 255).astype(np.uint8)
    return codes, low, use_step


def dequantize_levels(codes: Any, offset_db: float, step_db: float) -> np.ndarray:
    """Inverse of :func:`quantize_levels` (float32)."""
    return np.asarray(codes, dtype=np.float32) * np.float32(step_db) + np.float32(offset_db)


# --- Spectrogram log source ------------------------------------------------------------------
def pick_prepared_log_param(position_glyph_data: Dict[str, Any], preferred_param: str) -> Optional[str]:
    log_mode_data = position_glyph_data.get('log') if isinstance(position_glyph_data, dict) else None
    prepared_params = log_mode_data.get('prepared_params', {}) if isinstance(log_mode_data, dict) else {}
    if not prepared_params:
        return None
    return preferred_param if preferred_param in prepared_params else next(iter(prepared_params.keys()), None)


def build_static_spectrogram_log_source_data(
    position_glyph_data: Dict[str, Any],
    preferred_param: str,
    compact: bool = True,
) -> Optional[Dict[str, list]]:
    """Reservoir payload for one position's static spectrogram log source.

    ``compact`` (default) keeps NumPy arrays (binary in the document), quantises the spectrum to
    ``uint8`` (with ``quant_offset_db`` / ``quant_step_db`` columns for the browser to decode) and
    omits ``initial_glyph_data_image``: the browser extracts its display chunk from the full levels,
    exactly as it does for the live server's reservoir payload.
    """
    param_to_use = pick_prepared_log_param(position_glyph_data, preferred_param)
    if not param_to_use:
        return None
    prepared = position_glyph_data['log']['prepared_params'].get(param_to_use)
    if not isinstance(prepared, dict):
        return None

    initial_glyph_data = prepared.get('initial_glyph_data') or {}
    image_values = initial_glyph_data.get('image') or []
    levels_source = prepared.get('levels_flat_transposed')
    if levels_source is None or len(levels_source) == 0:
        if not len(image_values):
            return None
        levels_source = image_values[0]

    data: Dict[str, list] = {
        # A static export embeds the complete prepared log dataset.  Mark it
        # with the same reservoir contract used by the live server so the
        # browser treats the full time range as locally available instead of
        # mistaking it for one display-sized streamed chunk.
        'parameter': [param_to_use],
        'frequency_labels': [to_list(prepared.get('frequency_labels'))],
        'frequencies_hz': [to_list(prepared.get('frequencies_hz'))],
        'n_times': [int(prepared.get('n_times', 0))],
        'n_freqs': [int(prepared.get('n_freqs', 0))],
        'chunk_time_length': [int(prepared.get('chunk_time_length', 0))],
        'time_step': [prepared.get('time_step', 0)],
        'min_val': [prepared.get('min_val', 0)],
        'max_val': [prepared.get('max_val', 100)],
        'min_time': [prepared.get('min_time', 0)],
        'max_time': [prepared.get('max_time', 0)],
        'initial_glyph_data_x': [to_list(initial_glyph_data.get('x'))],
        'initial_glyph_data_y': [to_list(initial_glyph_data.get('y'))],
        'initial_glyph_data_dw': [to_list(initial_glyph_data.get('dw'))],
        'initial_glyph_data_dh': [to_list(initial_glyph_data.get('dh'))],
        'is_reservoir_payload': [True],
    }

    if compact:
        codes, offset, step = quantize_levels(np.ascontiguousarray(levels_source))
        data['times_ms'] = [np.asarray(prepared.get('times_ms'), dtype=np.float64)]
        data['levels_flat_transposed'] = [codes]
        data['quant_offset_db'] = [float(offset)]
        data['quant_step_db'] = [float(step)]
    else:
        data['times_ms'] = [to_list(prepared.get('times_ms'))]
        data['levels_flat_transposed'] = [to_list(levels_source)]
        if len(image_values):
            data['initial_glyph_data_image'] = [to_list(image_values[0])]
    return data


def compact_prepared_glyph_data(
    prepared_glyph_data: Dict[str, Dict[str, Any]],
    shared_params: Optional[Dict[str, str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Copy of ``preparedGlyphData`` for embedding in a static document.

    * log spectra are quantised (``uint8`` + ``quant_offset_db`` / ``quant_step_db``);
    * ``times_ms`` become float64 arrays (binary) instead of JSON lists;
    * the initial-chunk ``image`` copy is dropped (the browser slices the full levels);
    * for the parameter already embedded in the spectrogram log source (``shared_params``:
      position -> parameter) the large arrays are left out and flagged
      ``shared_with_log_source`` so the browser aliases them from that source.
    Overview data is small and passes through unchanged. The input is not modified.
    """
    shared_params = shared_params or {}
    result: Dict[str, Dict[str, Any]] = {}
    for position, position_data in (prepared_glyph_data or {}).items():
        if not isinstance(position_data, dict):
            result[position] = position_data
            continue
        position_copy = dict(position_data)
        log_mode = position_data.get('log')
        if isinstance(log_mode, dict) and isinstance(log_mode.get('prepared_params'), dict):
            params_copy: Dict[str, Any] = {}
            for param, prepared in log_mode['prepared_params'].items():
                if not isinstance(prepared, dict) or prepared.get('levels_flat_transposed') is None:
                    params_copy[param] = prepared
                    continue
                entry = dict(prepared)
                glyph = dict(entry.get('initial_glyph_data') or {})
                glyph.pop('image', None)
                entry['initial_glyph_data'] = glyph
                if shared_params.get(position) == param:
                    entry['levels_flat_transposed'] = None
                    entry['times_ms'] = None
                    entry['shared_with_log_source'] = True
                else:
                    codes, offset, step = quantize_levels(np.ascontiguousarray(prepared['levels_flat_transposed']))
                    entry['levels_flat_transposed'] = codes
                    entry['quant_offset_db'] = float(offset)
                    entry['quant_step_db'] = float(step)
                    entry['times_ms'] = np.asarray(prepared.get('times_ms'), dtype=np.float64)
                params_copy[param] = entry
            position_copy['log'] = {**log_mode, 'prepared_params': params_copy}
        result[position] = position_copy
    return result


def compact_timeseries_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Narrow a time-series ``ColumnDataSource`` dict for embedding: level columns to float32 and an
    integer ``index`` to int32. ``Datetime`` keeps full precision."""
    out: Dict[str, Any] = {}
    for key, column in data.items():
        arr = column if isinstance(column, np.ndarray) else None
        if arr is not None and key != 'Datetime' and arr.dtype == np.float64:
            out[key] = arr.astype(np.float32)
        elif arr is not None and key == 'index' and arr.dtype.kind in 'iu':
            out[key] = arr.astype(np.int32)
        else:
            out[key] = column
    return out


# --- Size estimate and detail decision -------------------------------------------------------
def estimate_static_bytes(app_data: Any) -> Tuple[int, Dict[str, int]]:
    """Estimate the document size (bytes) for ``--static-detail full``, after the reductions above.

    Per position: log totals (float64 Datetime + float32 per column + int32 index), the log
    spectral grid at one byte per cell (rows x columns: an upper bound, the frequency range is
    clipped later) plus its float64 time axis, all x 4/3 for base64. Overview data and the page
    itself are a fixed overhead.
    """
    per_position: Dict[str, int] = {}
    total = _STATIC_FIXED_OVERHEAD_BYTES
    for name in list(app_data.positions()):
        position = app_data[name]
        raw = 0
        totals = getattr(position, 'log_totals', None)
        if totals is not None and len(totals):
            raw += len(totals) * (8 + 4 * max(0, len(totals.columns) - 1) + 4)
        spectral = getattr(position, 'log_spectral', None)
        if spectral is not None and len(spectral):
            raw += len(spectral) * (len(spectral.columns) + 8)
        size = int(raw * _BASE64_FACTOR)
        per_position[str(name)] = size
        total += size
    return int(total), per_position


def _native_step_s(frame: Any) -> float:
    """Median spacing (s) of the first rows of a log frame; 1.0 when it cannot be told."""
    try:
        from noise_survey_analysis.core.utils import to_bokeh_ms
        times = np.asarray(to_bokeh_ms(frame['Datetime'].iloc[:2000]), dtype=np.float64)
        step = float(np.median(np.diff(times))) / 1000.0
        return step if step > 0 else 1.0
    except Exception:
        return 1.0


def estimate_static_parts(app_data: Any) -> Dict[str, Any]:
    """Size model split into what does not depend on the spectrogram step and what does (bytes, pre-base64)."""
    fixed = 0
    spectral_native = 0
    native_step = 1.0
    for name in list(app_data.positions()):
        position = app_data[name]
        totals = getattr(position, 'log_totals', None)
        if totals is not None and len(totals):
            fixed += len(totals) * (8 + 4 * max(0, len(totals.columns) - 1) + 4)
        spectral = getattr(position, 'log_spectral', None)
        if spectral is not None and len(spectral):
            spectral_native += len(spectral) * (len(spectral.columns) + 8)
            native_step = max(native_step, _native_step_s(spectral))
    return {'fixed': fixed, 'spectral_native': spectral_native, 'native_step_s': native_step}


def estimate_bytes_for_step(parts: Dict[str, Any], step_s: Optional[float]) -> int:
    """Document size with the log spectrogram averaged to ``step_s`` (None / native = full detail)."""
    scale = 1.0
    if step_s and step_s > parts['native_step_s']:
        scale = parts['native_step_s'] / step_s
    raw = parts['fixed'] + parts['spectral_native'] * scale
    return int(_STATIC_FIXED_OVERHEAD_BYTES + raw * _BASE64_FACTOR)


def plan_static_detail(requested: str, app_data: Any, max_mb: float = STATIC_AUTO_MAX_MB) -> Dict[str, Any]:
    """Decide the mode and spectrogram step. ``auto``: ``full`` if under the threshold, else ``lines`` with
    the finest step in STATIC_LOG_STEPS_S that fits, else ``regions``.
    Returns ``{'mode', 'step_s', 'estimate_bytes', 'explanation'}``."""
    requested = (requested or 'auto').lower()
    if requested not in STATIC_DETAIL_CHOICES:
        raise ValueError(f"static detail must be one of {', '.join(STATIC_DETAIL_CHOICES)}; got {requested!r}")
    parts = estimate_static_parts(app_data)
    limit = max_mb * 1024 * 1024
    full = estimate_bytes_for_step(parts, None)
    full_mb = full / 1048576

    def plan(mode, step, why):
        est = estimate_bytes_for_step(parts, step) if mode in ('full', 'lines') else None
        return {'mode': mode, 'step_s': step, 'estimate_bytes': est if est is not None else full, 'explanation': why}

    def finest_step():
        native = parts['native_step_s']
        return next((s for s in STATIC_LOG_STEPS_S if s > native and estimate_bytes_for_step(parts, s) <= limit), None)

    if requested == 'full':
        return plan('full', None, f"static detail 'full' (requested; estimate {full_mb:.0f} MB)")
    if requested == 'lines':
        step = finest_step() or STATIC_LOG_STEPS_S[-1]
        return plan('lines', step, f"static detail 'lines' (requested): full 1 s lines, spectrogram averaged to {step:g} s "
                                   f"(estimate {estimate_bytes_for_step(parts, step) / 1048576:.0f} MB)")
    if requested in ('regions', 'overview'):
        return plan(requested, None, f"static detail '{requested}' (requested; full-detail estimate {full_mb:.0f} MB)")
    if full <= limit:
        return plan('full', None, f"static detail 'full' (estimated {full_mb:.0f} MB <= {max_mb:.0f} MB threshold)")
    step = finest_step()
    if step is not None:
        return plan('lines', step, f"static detail 'lines' (full would be {full_mb:.0f} MB, over {max_mb:.0f} MB): full 1 s "
                                   f"lines, spectrogram averaged to {step:g} s (estimate "
                                   f"{estimate_bytes_for_step(parts, step) / 1048576:.0f} MB)")
    return plan('regions', None, f"static detail 'regions' (even {STATIC_LOG_STEPS_S[-1]} s averaging is over {max_mb:.0f} MB; "
                                 f"1 s detail kept around regions and markers only)")


def average_spectral_in_time(frame: Any, step_s: float) -> Any:
    """Energy-average a log spectral frame to a uniform ``step_s`` grid (bins aligned to the epoch).
    Columns whose name contains 'max' take the bin maximum; every other level column is the dB energy
    mean (NaN ignored). The row's Datetime is the first sample in its bin."""
    import pandas as pd
    from noise_survey_analysis.core.utils import to_bokeh_ms

    if frame is None or len(frame) == 0:
        return frame
    step_ms = float(step_s) * 1000.0
    times = np.asarray(to_bokeh_ms(frame['Datetime']), dtype=np.float64)
    bins = np.floor(times / step_ms).astype(np.int64)
    starts = np.flatnonzero(np.r_[True, np.diff(bins) != 0])
    out: Dict[str, Any] = {'Datetime': frame['Datetime'].iloc[starts].reset_index(drop=True)}
    counts_edge = np.r_[starts, len(frame)]
    sizes = np.diff(counts_edge)
    for column in frame.columns:
        if column == 'Datetime':
            continue
        values = pd.to_numeric(frame[column], errors='coerce').to_numpy(dtype=np.float64)
        valid = ~np.isnan(values)
        if 'max' in str(column).lower():
            filled = np.where(valid, values, -np.inf)
            reduced = np.maximum.reduceat(filled, starts)
            reduced[~np.isfinite(reduced)] = np.nan
        else:
            power = np.where(valid, np.power(10.0, values / 10.0), 0.0)
            total = np.add.reduceat(power, starts)
            count = np.add.reduceat(valid.astype(np.int64), starts)
            with np.errstate(divide='ignore', invalid='ignore'):
                reduced = np.where(count > 0, 10.0 * np.log10(total / np.maximum(count, 1)), np.nan)
        out[column] = reduced
    del sizes
    return pd.DataFrame(out)


def choose_static_detail(requested: str, estimated_bytes: int, max_mb: float = STATIC_AUTO_MAX_MB) -> Tuple[str, str]:
    """Resolve ``--static-detail``. Returns ``(mode, explanation)``; ``auto`` becomes ``full`` or ``regions``."""
    requested = (requested or 'auto').lower()
    if requested not in STATIC_DETAIL_CHOICES:
        raise ValueError(f"static detail must be one of {', '.join(STATIC_DETAIL_CHOICES)}; got {requested!r}")
    estimated_mb = estimated_bytes / (1024 * 1024)
    if requested != 'auto':
        return requested, f"static detail '{requested}' (requested; full-detail estimate {estimated_mb:.0f} MB)"
    if estimated_mb <= max_mb:
        return 'full', f"static detail 'full' (estimated {estimated_mb:.0f} MB <= {max_mb:.0f} MB threshold)"
    return 'regions', (
        f"static detail 'regions' (full detail would be about {estimated_mb:.0f} MB, over the "
        f"{max_mb:.0f} MB threshold; 1 s detail kept around regions and markers only)"
    )


# --- Detail windows ---------------------------------------------------------------------------
def _finite(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def merge_windows(windows: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    ordered = sorted((a, b) for a, b in windows if a is not None and b is not None and b >= a)
    merged: List[Tuple[float, float]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def collect_detail_windows(
    app_state: Optional[Dict[str, Any]],
    region_pad_s: float = STATIC_REGION_PAD_S,
    marker_pad_s: float = STATIC_MARKER_PAD_S,
) -> List[Tuple[float, float]]:
    """Display-time windows (epoch ms, merged) around every region area and marker in ``app_state``.
    Rejected suggestions are ignored."""
    windows: List[Tuple[float, float]] = []
    state = app_state if isinstance(app_state, dict) else {}
    regions = (state.get('regions') or {}).get('byId') or {}
    for region in regions.values() if isinstance(regions, dict) else []:
        if not isinstance(region, dict) or region.get('status') == 'rejected':
            continue
        areas = region.get('areas')
        if not isinstance(areas, list) or not areas:
            areas = [{'start': region.get('start'), 'end': region.get('end')}]
        for area in areas:
            if not isinstance(area, dict):
                continue
            start, end = _finite(area.get('start')), _finite(area.get('end'))
            if start is None or end is None:
                continue
            windows.append((min(start, end) - region_pad_s * 1000.0, max(start, end) + region_pad_s * 1000.0))
    markers = (state.get('markers') or {}).get('byId') or {}
    for marker in markers.values() if isinstance(markers, dict) else []:
        if not isinstance(marker, dict) or marker.get('status') == 'rejected':
            continue
        stamp = _finite(marker.get('timestamp'))
        if stamp is not None:
            windows.append((stamp - marker_pad_s * 1000.0, stamp + marker_pad_s * 1000.0))
    return merge_windows(windows)


def filter_totals_to_windows(frame: Any, windows_ms: Sequence[Tuple[float, float]]) -> Any:
    """Rows of a log-totals frame inside ``windows_ms`` (data-time epoch ms), with one all-NaN row
    after each window so lines do not join across the gaps. Empty frame when nothing matches."""
    import pandas as pd
    from noise_survey_analysis.core.utils import to_bokeh_ms

    if frame is None:
        return frame
    if len(frame) == 0 or not windows_ms:
        return frame.iloc[0:0].copy()
    times = np.asarray(to_bokeh_ms(frame['Datetime']), dtype=np.float64)
    keep = np.zeros(len(frame), dtype=bool)
    for start, end in windows_ms:
        keep |= (times >= start) & (times <= end)
    if not keep.any():
        return frame.iloc[0:0].copy()
    positions = np.flatnonzero(keep)
    kept = frame.iloc[positions].reset_index(drop=True)
    breaks = np.flatnonzero(np.diff(positions) > 1)  # last row of each run except the final one
    if len(breaks) == 0:
        return kept
    pieces = []
    previous = 0
    for end_idx in breaks:
        pieces.append(kept.iloc[previous:end_idx + 1])
        gap = {column: np.nan for column in kept.columns}
        gap['Datetime'] = kept['Datetime'].iloc[end_idx] + pd.Timedelta(milliseconds=1)
        pieces.append(pd.DataFrame([gap], columns=kept.columns))
        previous = end_idx + 1
    pieces.append(kept.iloc[previous:])
    return pd.concat(pieces, ignore_index=True)


def apply_static_detail(
    app_data: Any,
    mode: str,
    windows_display_ms: Sequence[Tuple[float, float]],
    chart_offsets_ms: Optional[Dict[str, float]] = None,
    step_s: Optional[float] = None,
) -> Dict[str, Dict[str, int]]:
    """Reduce each position's 1 s log data in place for ``mode`` ('full' does nothing).

    ``regions``: log totals are cut to the windows (shifted by that position's chart offset, because
    annotations are in displayed time); the log spectrogram is dropped (the browser falls back to the
    overview spectrogram, and to overview lines outside the kept windows). ``overview``: no log data.
    Returns per-position row counts after reduction.
    """
    summary: Dict[str, Dict[str, int]] = {}
    chart_offsets_ms = chart_offsets_ms or {}
    for name in list(app_data.positions()):
        position = app_data[name]
        if mode == 'regions':
            offset = float(chart_offsets_ms.get(name, 0.0) or 0.0)
            data_windows = [(a - offset, b - offset) for a, b in windows_display_ms]
            position.log_totals = filter_totals_to_windows(position.log_totals, data_windows)
            position.log_spectral = None
        elif mode == 'lines':
            if step_s and position.log_spectral is not None and len(position.log_spectral):
                position.log_spectral = average_spectral_in_time(position.log_spectral, step_s)
            position._log_data_loaded = True
        elif mode == 'overview':
            position.log_totals = None
            position.log_spectral = None
        if mode in ('regions', 'overview'):
            # Nothing left to load lazily, and nothing for the page to wait for.
            position.log_file_paths = []
            position._log_data_loaded = True
        summary[str(name)] = {
            'log_totals_rows': 0 if position.log_totals is None else int(len(position.log_totals)),
            'log_spectral_rows': 0 if position.log_spectral is None else int(len(position.log_spectral)),
        }
    return summary
