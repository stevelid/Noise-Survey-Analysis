"""Audio-specific post-processing utilities."""

import logging
import os
from typing import Any

import numpy as np
import pandas as pd

try:
    import soundfile as sf
    _HAS_SOUNDFILE = True
except Exception:
    sf = None
    _HAS_SOUNDFILE = False

try:
    from scipy.signal import bilinear_zpk, sosfilt, zpk2sos
    _HAS_SCIPY = True
except Exception:
    bilinear_zpk = sosfilt = zpk2sos = None
    _HAS_SCIPY = False

from .config import AUDIO_ANCHORING_SETTINGS

logger = logging.getLogger(__name__)

MAX_MATCH_DISTANCE = pd.Timedelta(hours=AUDIO_ANCHORING_SETTINGS['max_match_hours'])
WARNING_MATCH_DISTANCE = pd.Timedelta(hours=AUDIO_ANCHORING_SETTINGS['warning_match_hours'])
MIN_GAP = pd.Timedelta(seconds=AUDIO_ANCHORING_SETTINGS['min_gap_seconds'])
GAP_MULTIPLIER = AUDIO_ANCHORING_SETTINGS['gap_multiplier']
DURATION_TOLERANCE = pd.Timedelta(seconds=AUDIO_ANCHORING_SETTINGS['duration_tolerance_seconds'])
CORRELATION_ENABLED = AUDIO_ANCHORING_SETTINGS.get('correlation_enabled', True)
CORRELATION_SEARCH_SECONDS = int(AUDIO_ANCHORING_SETTINGS.get('correlation_search_seconds', 300))
CORRELATION_WINDOW_SECONDS = int(AUDIO_ANCHORING_SETTINGS.get('correlation_window_seconds', 300))
CORRELATION_MAX_WINDOWS = int(AUDIO_ANCHORING_SETTINGS.get('correlation_max_windows', 3))
CORRELATION_MIN_SCORE = float(AUDIO_ANCHORING_SETTINGS.get('correlation_min_score', 0.80))
CORRELATION_MAX_LAG_SPREAD_SECONDS = float(
    AUDIO_ANCHORING_SETTINGS.get('correlation_max_lag_spread_seconds', 2)
)
CORRELATION_MIN_APPLY_SECONDS = float(
    AUDIO_ANCHORING_SETTINGS.get('correlation_min_apply_seconds', 2)
)


class AudioDataProcessor:
    """Handles audio-specific post-processing separate from data loading."""

    def anchor_audio_files(self, app_data: Any) -> None:
        """Anchors audio file timestamps based on measurement data."""
        if app_data is None:
            logger.warning("AudioDataProcessor: No application data provided for anchoring.")
            return

        if not hasattr(app_data, 'positions') or not callable(app_data.positions):
            logger.error("AudioDataProcessor: Provided app_data does not expose positions().")
            return

        logger.info("AudioDataProcessor: Starting post-processing to anchor audio files...")
        for position_name in app_data.positions():
            try:
                pos_data = app_data[position_name]
            except KeyError:
                logger.warning("AudioDataProcessor: Position '%s' not found during anchoring.", position_name)
                continue

            if not getattr(pos_data, 'has_audio_files', False):
                continue

            has_log_totals = getattr(pos_data, 'has_log_totals', False)
            has_overview_totals = getattr(pos_data, 'has_overview_totals', False)
            if not has_log_totals and not has_overview_totals:
                continue

            logger.info("AudioDataProcessor: Anchoring audio for position '%s'...", position_name)
            logger.info("  has_log_totals=%s, has_overview_totals=%s", has_log_totals, has_overview_totals)

            measurement_times = self._collect_measurement_times(pos_data)
            if measurement_times.empty:
                logger.warning("AudioDataProcessor: Could not find measurement times for position '%s'.", position_name)
                continue

            segments = self._split_measurement_segments(measurement_times)
            logger.info("  Measurement times range: %s -> %s (%d points)", measurement_times.iloc[0] if len(measurement_times) > 0 else 'N/A', measurement_times.iloc[-1] if len(measurement_times) > 0 else 'N/A', len(measurement_times))
            for si, seg in enumerate(segments):
                logger.info("  Segment %d: %s -> %s", si, seg['start'], seg['end'])
            if not segments:
                logger.warning("AudioDataProcessor: No valid measurement segments for position '%s'.", position_name)
                continue

            audio_df = pos_data.audio_files_list
            if audio_df is None or audio_df.empty:
                continue

            logger.info("  Audio files before anchoring: %d files", len(audio_df))
            for _, arow in audio_df.iterrows():
                logger.info("    File: %s, modified_time=%s, duration=%.1fs", arow.get('filename', 'unknown'), arow.get('modified_time', arow.get('Datetime', 'N/A')), arow.get('duration_sec', 0))
            anchored_df = self._anchor_audio_files_to_segments(audio_df, segments, position_name)
            anchored_df = self._refine_audio_alignment(
                anchored_df,
                pos_data,
                position_name,
            )
            pos_data.audio_files_list = anchored_df
            for _, arow in anchored_df.iterrows():
                logger.info("  Anchored: %s -> %s (confidence=%s, warning=%s)", arow.get('filename', 'unknown'), arow.get('Datetime', 'NaT'), arow.get('anchor_confidence', ''), arow.get('anchor_warning', ''))

            logger.info(
                "AudioDataProcessor: Successfully anchored %d audio files for '%s'.",
                len(anchored_df),
                position_name,
            )

    @staticmethod
    def _collect_measurement_times(pos_data: Any) -> pd.Series:
        times = []
        if getattr(pos_data, 'has_log_totals', False):
            times.append(pos_data.log_totals['Datetime'])
        if getattr(pos_data, 'has_overview_totals', False):
            times.append(pos_data.overview_totals['Datetime'])
        if not times:
            return pd.Series(dtype='datetime64[ns, UTC]')
        return pd.concat(times).dropna().sort_values().reset_index(drop=True)

    @staticmethod
    def _split_measurement_segments(times: pd.Series) -> list[dict[str, pd.Timestamp]]:
        if times.empty:
            return []
        deltas = times.diff().dropna()
        median_delta = deltas.median() if not deltas.empty else pd.Timedelta(seconds=0)
        gap_threshold = max(MIN_GAP, median_delta * GAP_MULTIPLIER)
        segment_boundaries = deltas[deltas > gap_threshold].index.tolist()
        segments = []
        start_idx = 0
        for boundary_idx in segment_boundaries:
            segments.append({
                'start': times.iloc[start_idx],
                'end': times.iloc[boundary_idx - 1],
            })
            start_idx = boundary_idx
        segments.append({'start': times.iloc[start_idx], 'end': times.iloc[-1]})
        return segments

    def _anchor_audio_files_to_segments(
        self,
        audio_df: pd.DataFrame,
        segments: list[dict[str, pd.Timestamp]],
        position_name: str,
    ) -> pd.DataFrame:
        working_df = audio_df.copy()
        if 'modified_time' not in working_df.columns:
            working_df['modified_time'] = working_df.get('Datetime')

        anchor_dtype = self._anchor_datetime_dtype(working_df)
        working_df['anchored_datetime'] = pd.Series(
            pd.NaT,
            index=working_df.index,
            dtype=anchor_dtype,
        )
        if 'anchor_confidence' not in working_df.columns:
            working_df['anchor_confidence'] = 'low'
        else:
            working_df['anchor_confidence'] = working_df['anchor_confidence'].fillna('low')
        if 'anchor_warning' not in working_df.columns:
            working_df['anchor_warning'] = ''
        else:
            working_df['anchor_warning'] = working_df['anchor_warning'].fillna('')
        if 'anchor_source' not in working_df.columns:
            working_df['anchor_source'] = 'filesystem_modified_time'
        working_df['segment_index'] = pd.NA

        assignments: dict[int, list[int]] = {idx: [] for idx in range(len(segments))}
        for idx, row in working_df.iterrows():
            recorded_start = row.get('recorded_start_time')
            has_recorded_start = recorded_start is not None and not pd.isna(recorded_start)
            modified_time = row.get('modified_time')
            if not has_recorded_start and pd.isna(modified_time):
                working_df.at[idx, 'anchor_warning'] = 'missing modified time'
                continue

            # Use the full recording span (start→end) for matching, not just modified_time
            duration_sec = row.get('duration_sec', 0)
            duration_sec = duration_sec if pd.notna(duration_sec) and duration_sec > 0 else 0
            if has_recorded_start:
                recording_start = recorded_start
                recording_end = recording_start + pd.Timedelta(seconds=duration_sec)
            else:
                recording_start = modified_time - pd.Timedelta(seconds=duration_sec)
                recording_end = modified_time

            best_idx = None
            best_distance = None
            for segment_idx, segment in enumerate(segments):
                seg_start = segment['start']
                seg_end = segment['end']
                # Check if recording span overlaps the segment
                if recording_start <= seg_end and recording_end >= seg_start:
                    distance = pd.Timedelta(seconds=0)
                else:
                    # No overlap: distance is gap between nearest edges
                    distance = min(
                        abs(recording_start - seg_end),
                        abs(recording_end - seg_start),
                    )
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_idx = segment_idx

            if best_distance is None or best_distance > MAX_MATCH_DISTANCE:
                warning = 'no close measurement segment'
                if best_distance is not None:
                    warning += f" (delta {best_distance})"
                working_df.at[idx, 'anchor_warning'] = warning
                continue

            assignments[best_idx].append(idx)
            working_df.at[idx, 'segment_index'] = best_idx
            if has_recorded_start:
                working_df.at[idx, 'anchor_confidence'] = 'high'
            elif best_distance <= WARNING_MATCH_DISTANCE:
                working_df.at[idx, 'anchor_confidence'] = 'high'
            else:
                working_df.at[idx, 'anchor_confidence'] = 'medium'
                working_df.at[idx, 'anchor_warning'] = f"far from segment start (delta {best_distance})"

        for segment_idx, row_indices in assignments.items():
            if not row_indices:
                continue
            segment = segments[segment_idx]
            row_indices = sorted(
                row_indices,
                key=lambda index: (
                    working_df.at[index, 'recorded_start_time']
                    if 'recorded_start_time' in working_df.columns
                    and pd.notna(working_df.at[index, 'recorded_start_time'])
                    else working_df.at[index, 'modified_time']
                ),
            )
            for index in row_indices:
                recorded_start = (
                    working_df.at[index, 'recorded_start_time']
                    if 'recorded_start_time' in working_df.columns
                    else pd.NaT
                )
                modified_time = working_df.at[index, 'modified_time']
                duration_seconds = working_df.at[index, 'duration_sec']
                duration_seconds = duration_seconds if pd.notna(duration_seconds) and duration_seconds > 0 else 0
                if pd.notna(recorded_start):
                    recording_start = recorded_start
                else:
                    # Last-resort fallback for formats without embedded/explicit timing.
                    recording_start = modified_time - pd.to_timedelta(duration_seconds, unit='s')
                    working_df.at[index, 'anchor_source'] = 'filesystem_modified_time-duration'
                working_df.at[index, 'anchored_datetime'] = recording_start

        working_df['Datetime'] = working_df['anchored_datetime']
        return working_df

    def _refine_audio_alignment(
        self,
        audio_df: pd.DataFrame,
        pos_data: Any,
        position_name: str,
    ) -> pd.DataFrame:
        """Verify/refine an anchor using short, bounded audio-envelope correlations."""
        if not CORRELATION_ENABLED or not _HAS_SOUNDFILE or audio_df.empty:
            return audio_df
        measurement_selection = self._select_correlation_measurement(pos_data)
        if measurement_selection is None:
            return audio_df
        measurement, weighting = measurement_selection
        if len(measurement) < CORRELATION_WINDOW_SECONDS:
            return audio_df

        candidates = self._correlation_window_candidates(audio_df)
        results = []
        for row_index, offset_seconds in candidates:
            row = audio_df.loc[row_index]
            envelope = self._read_rms_envelope(
                row.get('full_path'),
                offset_seconds,
                CORRELATION_WINDOW_SECONDS,
                weighting,
            )
            if envelope is None or len(envelope) < 30 or np.nanstd(envelope) < 1.0:
                continue
            nominal_start = row.get('Datetime')
            if nominal_start is None or pd.isna(nominal_start):
                continue
            nominal_start = pd.Timestamp(nominal_start) + pd.Timedelta(seconds=offset_seconds)
            result = self._find_bounded_correlation_lag(
                envelope,
                nominal_start,
                measurement,
            )
            if result is not None:
                results.append(result)

        if len(results) < 2:
            logger.info(
                "AudioDataProcessor: correlation QA skipped for '%s' (%d usable window%s).",
                position_name,
                len(results),
                '' if len(results) == 1 else 's',
            )
            return audio_df

        lags = np.asarray([result['lag_seconds'] for result in results], dtype=float)
        scores = np.asarray([result['score'] for result in results], dtype=float)
        margins = np.asarray([result['uniqueness_margin'] for result in results], dtype=float)
        median_lag = float(np.median(lags))
        lag_spread = float(np.max(np.abs(lags - median_lag)))
        median_score = float(np.median(scores))
        accepted = (
            median_score >= CORRELATION_MIN_SCORE
            and lag_spread <= CORRELATION_MAX_LAG_SPREAD_SECONDS
            and float(np.median(margins)) >= 0.02
        )
        refined = audio_df.copy()
        refined['correlation_offset_sec'] = median_lag
        refined['correlation_score'] = median_score
        refined['correlation_windows'] = len(results)
        refined['correlation_lag_spread_sec'] = lag_spread
        refined['correlation_accepted'] = accepted
        if not accepted:
            logger.warning(
                "AudioDataProcessor: correlation QA rejected for '%s' "
                "(lag=%+.1fs, score=%.3f, spread=%.1fs).",
                position_name,
                median_lag,
                median_score,
                lag_spread,
            )
            return refined

        if abs(median_lag) >= CORRELATION_MIN_APPLY_SECONDS:
            refined['Datetime'] = refined['Datetime'] + pd.to_timedelta(median_lag, unit='s')
            refined['anchored_datetime'] = refined['Datetime']
            refined['anchor_source'] = refined['anchor_source'].astype(str) + '+envelope_correlation'
            logger.info(
                "AudioDataProcessor: applied correlation refinement for '%s': "
                "%+.1fs (median r=%.3f, %d windows).",
                position_name,
                median_lag,
                median_score,
                len(results),
            )
        else:
            logger.info(
                "AudioDataProcessor: correlation verified '%s' without adjustment "
                "(lag=%+.1fs, median r=%.3f, %d windows).",
                position_name,
                median_lag,
                median_score,
                len(results),
            )
        refined['anchor_confidence'] = 'high'
        return refined

    @staticmethod
    def _select_correlation_measurement(pos_data: Any) -> tuple[pd.Series, str] | None:
        frames = []
        if getattr(pos_data, 'has_log_totals', False):
            frames.append(pos_data.log_totals)
        if not frames:
            return None
        data = frames[0]
        if data is None or data.empty or 'Datetime' not in data.columns:
            return None
        preferred = None
        for target in ('LZeq', 'LAeq'):
            for column in data.columns:
                if str(column).strip() == target:
                    preferred = column
                    break
            if preferred is not None:
                break
        if preferred is None:
            return None
        values = pd.to_numeric(data[preferred], errors='coerce')
        times = pd.to_datetime(data['Datetime'], errors='coerce', utc=True)
        series = pd.Series(values.to_numpy(dtype=float), index=pd.DatetimeIndex(times))
        series = series[~series.index.isna() & np.isfinite(series.to_numpy())]
        series = series[~series.index.duplicated(keep='last')].sort_index()
        weighting = 'Z' if str(preferred).strip() == 'LZeq' else 'A'
        return series, weighting

    @staticmethod
    def _correlation_window_candidates(audio_df: pd.DataFrame) -> list[tuple[Any, float]]:
        usable = []
        for row_index, row in audio_df.iterrows():
            duration = row.get('duration_sec', 0)
            path = row.get('full_path')
            if not path or not os.path.isfile(path) or pd.isna(duration):
                continue
            duration = float(duration)
            if duration < CORRELATION_WINDOW_SECONDS + 2:
                continue
            usable.append((row_index, duration))
        if not usable:
            return []
        candidates: list[tuple[Any, float]] = []
        if len(usable) >= CORRELATION_MAX_WINDOWS:
            selected_indices = np.linspace(0, len(usable) - 1, CORRELATION_MAX_WINDOWS).round().astype(int)
            for selected_index in selected_indices:
                row_index, duration = usable[int(selected_index)]
                offset = max(1.0, (duration - CORRELATION_WINDOW_SECONDS) / 2.0)
                candidates.append((row_index, offset))
        else:
            fractions = (0.1, 0.5, 0.85)
            for row_index, duration in usable:
                for fraction in fractions:
                    available = duration - CORRELATION_WINDOW_SECONDS
                    candidates.append((row_index, max(1.0, available * fraction)))
                    if len(candidates) >= CORRELATION_MAX_WINDOWS:
                        return candidates
        return candidates[:CORRELATION_MAX_WINDOWS]

    @staticmethod
    def _read_rms_envelope(
        path: Any,
        offset_seconds: float,
        window_seconds: int,
        weighting: str = 'Z',
    ) -> np.ndarray | None:
        if not path or not _HAS_SOUNDFILE:
            return None
        try:
            with sf.SoundFile(str(path)) as audio_file:
                sample_rate = int(audio_file.samplerate)
                if sample_rate <= 0:
                    return None
                audio_file.seek(int(round(offset_seconds * sample_rate)))
                samples = audio_file.read(
                    int(window_seconds * sample_rate),
                    dtype='float64',
                    always_2d=True,
                )
        except Exception as exc:
            logger.debug("Audio envelope read failed for %s: %s", path, exc)
            return None
        complete_seconds = len(samples) // sample_rate
        if complete_seconds <= 0:
            return None
        samples = samples[:complete_seconds * sample_rate]
        if weighting == 'A':
            samples = AudioDataProcessor._apply_a_weighting(samples, sample_rate)
            if samples is None:
                return None
        samples = samples.reshape(complete_seconds, sample_rate, samples.shape[1])
        mean_square = np.mean(samples * samples, axis=(1, 2))
        return 10.0 * np.log10(np.maximum(mean_square, 1e-30))

    @staticmethod
    def _apply_a_weighting(samples: np.ndarray, sample_rate: int) -> np.ndarray | None:
        """Apply a numerically stable digital A-weighting filter for correlation QA."""
        if not _HAS_SCIPY:
            return None
        f1, f2, f3, f4 = 20.598997, 107.65265, 737.86223, 12194.217
        zeros = [0.0, 0.0, 0.0, 0.0]
        poles = [
            -2.0 * np.pi * f1,
            -2.0 * np.pi * f1,
            -2.0 * np.pi * f2,
            -2.0 * np.pi * f3,
            -2.0 * np.pi * f4,
            -2.0 * np.pi * f4,
        ]
        gain = (2.0 * np.pi * f4) ** 2 * 10.0 ** (1.9997 / 20.0)
        digital_zeros, digital_poles, digital_gain = bilinear_zpk(
            zeros,
            poles,
            gain,
            fs=sample_rate,
        )
        sections = zpk2sos(digital_zeros, digital_poles, digital_gain)
        return sosfilt(sections, samples, axis=0)

    @staticmethod
    def _find_bounded_correlation_lag(
        envelope: np.ndarray,
        nominal_start: pd.Timestamp,
        measurement: pd.Series,
    ) -> dict[str, float] | None:
        nominal_second = pd.Timestamp(nominal_start).round('s')
        search_start = nominal_second - pd.Timedelta(seconds=CORRELATION_SEARCH_SECONDS)
        sample_count = len(envelope) + 2 * CORRELATION_SEARCH_SECONDS
        target_index = pd.date_range(search_start, periods=sample_count, freq='s')
        target = measurement.reindex(target_index).to_numpy(dtype=float)
        scores = []
        for lag in range(-CORRELATION_SEARCH_SECONDS, CORRELATION_SEARCH_SECONDS + 1):
            offset = lag + CORRELATION_SEARCH_SECONDS
            values = target[offset:offset + len(envelope)]
            valid = np.isfinite(values) & np.isfinite(envelope)
            if valid.sum() < max(30, int(len(envelope) * 0.8)):
                continue
            audio_values = envelope[valid]
            measured_values = values[valid]
            if np.std(audio_values) < 0.5 or np.std(measured_values) < 0.5:
                continue
            score = float(np.corrcoef(audio_values, measured_values)[0, 1])
            if np.isfinite(score):
                scores.append((score, lag))
        if not scores:
            return None
        scores.sort(reverse=True)
        best_score, best_lag = scores[0]
        alternatives = [score for score, lag in scores if abs(lag - best_lag) > 2]
        runner_up = max(alternatives) if alternatives else -1.0
        return {
            'lag_seconds': float(best_lag),
            'score': float(best_score),
            'uniqueness_margin': float(best_score - runner_up),
        }

    @staticmethod
    def _anchor_datetime_dtype(working_df: pd.DataFrame) -> str:
        for column_name in ('modified_time', 'Datetime'):
            if column_name not in working_df.columns:
                continue
            series = working_df[column_name]
            if isinstance(series.dtype, pd.DatetimeTZDtype):
                return str(series.dtype)
        return 'datetime64[ns]'
