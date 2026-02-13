"""Audio-specific post-processing utilities."""

import logging
from typing import Any

import pandas as pd

from .config import AUDIO_ANCHORING_SETTINGS

logger = logging.getLogger(__name__)

MAX_MATCH_DISTANCE = pd.Timedelta(hours=AUDIO_ANCHORING_SETTINGS['max_match_hours'])
WARNING_MATCH_DISTANCE = pd.Timedelta(hours=AUDIO_ANCHORING_SETTINGS['warning_match_hours'])
MIN_GAP = pd.Timedelta(seconds=AUDIO_ANCHORING_SETTINGS['min_gap_seconds'])
GAP_MULTIPLIER = AUDIO_ANCHORING_SETTINGS['gap_multiplier']
DURATION_TOLERANCE = pd.Timedelta(seconds=AUDIO_ANCHORING_SETTINGS['duration_tolerance_seconds'])


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

        working_df['anchored_datetime'] = pd.NaT
        working_df['anchor_confidence'] = 'low'
        working_df['anchor_warning'] = ''
        working_df['segment_index'] = pd.NA

        assignments: dict[int, list[int]] = {idx: [] for idx in range(len(segments))}
        for idx, row in working_df.iterrows():
            modified_time = row.get('modified_time')
            if pd.isna(modified_time):
                working_df.at[idx, 'anchor_warning'] = 'missing modified time'
                continue

            # Use the full recording span (start→end) for matching, not just modified_time
            duration_sec = row.get('duration_sec', 0)
            duration_sec = duration_sec if pd.notna(duration_sec) and duration_sec > 0 else 0
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
            if best_distance <= WARNING_MATCH_DISTANCE:
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
                key=lambda index: working_df.at[index, 'modified_time'],
            )
            for index in row_indices:
                modified_time = working_df.at[index, 'modified_time']
                duration_seconds = working_df.at[index, 'duration_sec']
                duration_seconds = duration_seconds if pd.notna(duration_seconds) and duration_seconds > 0 else 0
                # Anchor to actual recording start: modified_time - duration
                recording_start = modified_time - pd.to_timedelta(duration_seconds, unit='s')
                working_df.at[index, 'anchored_datetime'] = recording_start

        working_df['Datetime'] = working_df['anchored_datetime']
        return working_df
