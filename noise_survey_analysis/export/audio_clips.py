"""Optional audio clips for static exports (``--audio-clips``).

For every region of at most ``MAX_CLIP_SECONDS`` that has anchored audio at a position, writes a
16 kHz mono PCM16 WAV to ``<name>_clips/region_<id>_<position>.wav`` (about 1 MB per 30 s) and
returns relative URLs the page can reference. The total is capped at ``MAX_TOTAL_BYTES``.
Timing matches live playback: display time minus (chart offset + audio offset) is the audio time;
meters a region marks ``absent`` get no clip; a region that spans several audio files is stitched.
No ffmpeg: decoding is ``soundfile`` (libsndfile), resampling is ``scipy.signal.resample_poly``.
"""
from __future__ import annotations

import logging
import re
from math import gcd
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

MAX_CLIP_SECONDS = 60.0
MAX_TOTAL_BYTES = 20 * 1024 * 1024
TARGET_RATE = 16000


def _safe(text: Any) -> str:
    return re.sub(r'[^A-Za-z0-9_.-]+', '_', str(text))


def _read_segment(path: str, start_s: float, end_s: float) -> Optional[tuple]:
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


def _effective_offset_ms(position: str, view: Dict[str, Any], chart_offsets_ms: Dict[str, float],
                         audio_offsets_ms: Dict[str, float]) -> float:
    """Display time minus data time, as live playback computes it: chart offset + audio offset.
    The saved ``view.positionEffectiveOffsets`` wins; otherwise chart + audio offsets are summed."""
    def number(value: Any) -> Optional[float]:
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if np.isfinite(result) else None

    saved = number((view.get('positionEffectiveOffsets') or {}).get(position))
    if saved is not None:
        return saved
    chart = number(chart_offsets_ms.get(position))
    if chart is None:
        chart = number((view.get('positionChartOffsets') or {}).get(position)) or 0.0
    audio = number(audio_offsets_ms.get(position))
    if audio is None:
        audio = number((view.get('positionAudioOffsets') or {}).get(position)) or 0.0
    return chart + audio


def _cut_region(files: Any, data_start: float, data_end: float, to_bokeh_ms: Any, resample_poly: Any) -> Optional[np.ndarray]:
    """16 kHz mono PCM16 for [data_start, data_end] (ms), stitched across every audio file that
    overlaps it; gaps between files stay silent. ``None`` when no file overlaps."""
    starts = np.asarray(to_bokeh_ms(files['Datetime']), dtype=np.float64)
    durations = files['duration_sec'].to_numpy(dtype=float) * 1000.0
    hits = [int(i) for i in np.flatnonzero((starts < data_end) & (starts + durations > data_start))]
    hits.sort(key=lambda i: starts[i])
    if not hits:
        return None
    buffer = np.zeros(int(round((data_end - data_start) / 1000.0 * TARGET_RATE)), dtype=np.float32)
    filled = False
    for i in hits:
        piece_start = max(data_start, starts[i])
        piece_end = min(data_end, starts[i] + durations[i])
        segment = _read_segment(str(files.iloc[i]['full_path']),
                                (piece_start - starts[i]) / 1000.0, (piece_end - starts[i]) / 1000.0)
        if segment is None:
            continue
        mono, rate = segment
        divisor = gcd(TARGET_RATE, int(rate))
        resampled = resample_poly(mono, TARGET_RATE // divisor, int(rate) // divisor) if rate != TARGET_RATE else mono
        at = int(round((piece_start - data_start) / 1000.0 * TARGET_RATE))
        chunk = np.asarray(resampled, dtype=np.float32)[:max(0, len(buffer) - at)]
        buffer[at:at + len(chunk)] = chunk
        filled = filled or len(chunk) > 0
    if not filled:
        return None
    return (np.clip(buffer, -1.0, 1.0) * 32767.0).astype(np.int16)


def write_region_clips(
    app_data: Any,
    app_state: Optional[Dict[str, Any]],
    clips_dir: Path,
    chart_offsets_ms: Optional[Dict[str, float]] = None,
    audio_offsets_ms: Optional[Dict[str, float]] = None,
) -> Dict[str, Dict[str, str]]:
    """Write clips; returns ``{region_id: {position: relative_url}}`` (URL = ``<dir name>/<file>``)."""
    from scipy.signal import resample_poly
    import soundfile as sf
    from noise_survey_analysis.core.utils import to_bokeh_ms

    regions = ((app_state or {}).get('regions') or {}).get('byId') or {}
    view = (app_state or {}).get('view') or {}
    chart_offsets_ms = chart_offsets_ms or {}
    audio_offsets_ms = audio_offsets_ms or {}
    result: Dict[str, Dict[str, str]] = {}
    total = 0
    clips_dir = Path(clips_dir)
    for region_id, region in regions.items():
        if not isinstance(region, dict) or region.get('status') == 'rejected':
            continue
        areas = region.get('areas') or [{'start': region.get('start'), 'end': region.get('end')}]
        try:
            start = min(float(a['start']) for a in areas)
            end = max(float(a['end']) for a in areas)
        except (KeyError, TypeError, ValueError):
            continue
        if end <= start or (end - start) / 1000.0 > MAX_CLIP_SECONDS:
            continue
        meter_states = region.get('meterStates') or {}
        for position in list(app_data.positions()):
            if position != region.get('positionId') and meter_states.get(position) == 'absent':
                continue  # the consultant marked this meter as not hearing the event
            files = getattr(app_data[position], 'audio_files_list', None)
            if files is None or len(files) == 0:
                continue
            offset = _effective_offset_ms(position, view, chart_offsets_ms, audio_offsets_ms)
            data_start, data_end = start - offset, end - offset
            try:
                pcm = _cut_region(files, data_start, data_end, to_bokeh_ms, resample_poly)
            except Exception as exc:
                logger.warning("Could not write audio clip for region %s at %s: %s", region_id, position, exc)
                continue
            if pcm is None:
                logger.info("No audio covers region %s at %s; no clip written.", region_id, position)
                continue
            if total + pcm.nbytes + 44 > MAX_TOTAL_BYTES:
                logger.warning("Audio clip cap (%d MB) reached; remaining regions get no clip.",
                               MAX_TOTAL_BYTES // (1024 * 1024))
                return result
            try:
                clips_dir.mkdir(parents=True, exist_ok=True)
                name = f"region_{_safe(region_id)}_{_safe(position)}.wav"
                sf.write(str(clips_dir / name), pcm, TARGET_RATE, subtype='PCM_16', format='WAV')
            except Exception as exc:
                logger.warning("Could not write audio clip for region %s at %s: %s", region_id, position, exc)
                continue
            total += pcm.nbytes + 44
            result.setdefault(str(region_id), {})[str(position)] = f"{clips_dir.name}/{name}"
    logger.info("Wrote %d audio clip(s), %.1f MB", sum(len(v) for v in result.values()), total / 1048576)
    return result
