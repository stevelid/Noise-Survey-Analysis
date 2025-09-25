"""Audio-specific post-processing utilities."""

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)


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

            anchor_time = pd.Timestamp.max.tz_localize('UTC')
            if has_log_totals:
                anchor_time = min(anchor_time, pos_data.log_totals['Datetime'].min())
            if has_overview_totals:
                anchor_time = min(anchor_time, pos_data.overview_totals['Datetime'].min())

            if anchor_time == pd.Timestamp.max.tz_localize('UTC'):
                logger.warning("AudioDataProcessor: Could not find an anchor time for position '%s'.", position_name)
                continue

            audio_df = pos_data.audio_files_list
            if audio_df is None or audio_df.empty:
                continue

            timestamps = []
            current_time = anchor_time
            for _, row in audio_df.iterrows():
                timestamps.append(current_time)
                duration_seconds = row.get('duration_sec')
                duration_seconds = duration_seconds if pd.notna(duration_seconds) else 0
                current_time += pd.to_timedelta(duration_seconds, unit='s')

            audio_df['Datetime'] = timestamps
            pos_data.audio_files_list = audio_df

            logger.info("AudioDataProcessor: Successfully anchored %d audio files for '%s'.", len(audio_df), position_name)
