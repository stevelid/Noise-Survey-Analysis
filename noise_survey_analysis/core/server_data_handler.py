import logging
from typing import Dict, Optional

import pandas as pd

from noise_survey_analysis.core.config import (
    CHART_SETTINGS,
    LOG_VIEW_MAX_VIEWPORT_SECONDS,
    LOG_STREAM_TARGET_POINTS,
)
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.data_processors import GlyphDataProcessor

logger = logging.getLogger(__name__)


class ServerDataHandler:
    def __init__(
        self,
        doc,
        app_data: DataManager,
        chart_settings: Optional[Dict] = None,
    ) -> None:
        self.doc = doc
        self.app_data = app_data
        self.chart_settings = chart_settings or CHART_SETTINGS
        self.processor = GlyphDataProcessor()
        self.selected_parameter = self.chart_settings.get('default_spectral_param', 'LZeq')
        self.position_models = self._collect_position_models()
        self._buffer_bounds = {}  # Track buffer bounds per position for edge detection

    def _collect_position_models(self) -> Dict[str, Dict[str, object]]:
        models: Dict[str, Dict[str, object]] = {}
        for position_id in self.app_data.positions():
            models[position_id] = {
                # Push to log_source (reservoir) instead of display source
                'timeseries_log_source': self.doc.get_model_by_name(f"source_{position_id}_timeseries_log"),
                'spectrogram_log_source': self.doc.get_model_by_name(f"source_{position_id}_spectrogram_log"),
                'timeseries_figure': self.doc.get_model_by_name(f"figure_{position_id}_timeseries"),
                'spectrogram_figure': self.doc.get_model_by_name(f"figure_{position_id}_spectrogram"),
            }
        return models

    def set_selected_parameter(self, param: str) -> None:
        if isinstance(param, str) and param.strip():
            self.selected_parameter = param.strip()

    def _estimate_log_time_step_ms(self, position_data) -> Optional[float]:
        def extract_step_from_df(df: Optional[pd.DataFrame]) -> Optional[float]:
            if df is None or df.empty or 'Datetime' not in df.columns:
                return None
            try:
                times_ms = (pd.to_datetime(df['Datetime']).astype('int64') // 10**6).to_numpy()
            except Exception:
                return None
            if len(times_ms) < 2:
                return None
            deltas = pd.Series(times_ms).diff().dropna()
            positive = deltas[deltas > 0]
            if positive.empty:
                return None
            return float(positive.median())

        step_ms = extract_step_from_df(getattr(position_data, 'log_totals', None))
        if step_ms and step_ms > 0:
            return step_ms

        step_ms = extract_step_from_df(getattr(position_data, 'log_spectral', None))
        if step_ms and step_ms > 0:
            return step_ms

        sample_periods = getattr(position_data, 'sample_periods_seconds', None)
        if sample_periods:
            positive_periods = [float(v) for v in sample_periods if isinstance(v, (int, float)) and v > 0]
            if positive_periods:
                return min(positive_periods) * 1000

        return None

    def _position_max_viewport_seconds(self, position_data) -> float:
        hard_cap_seconds = float(LOG_VIEW_MAX_VIEWPORT_SECONDS)
        target_points = max(1, int(LOG_STREAM_TARGET_POINTS))
        fallback_seconds = min(300.0, hard_cap_seconds)

        step_ms = self._estimate_log_time_step_ms(position_data)
        if not step_ms or step_ms <= 0:
            return fallback_seconds

        adaptive_seconds = (step_ms * target_points) / 1000.0
        if adaptive_seconds <= 0:
            return fallback_seconds

        return min(adaptive_seconds, hard_cap_seconds)

    def handle_range_update(self, start_ms: float, end_ms: float) -> None:
        if not isinstance(start_ms, (int, float)) or not isinstance(end_ms, (int, float)):
            return

        viewport_width_ms = abs(end_ms - start_ms)
        viewport_width_seconds = viewport_width_ms / 1000

        # Evaluate stream eligibility per position so low-sample-rate positions
        # can stream wider windows than high-sample-rate ones.
        for position_id in self.app_data.positions():
            position_data = self.app_data[position_id]
            max_viewport_seconds = self._position_max_viewport_seconds(position_data)
            if viewport_width_seconds > max_viewport_seconds:
                logger.debug(
                    "Viewport too large for %s (%.0fs > %.0fs), skipping log stream",
                    position_id,
                    viewport_width_seconds,
                    max_viewport_seconds,
                )
                continue

            if not self._buffer_covers_viewport(position_id, start_ms, end_ms):
                buffer_start, buffer_end = self._calculate_buffer(start_ms, end_ms)
                self._update_position(position_id, buffer_start, buffer_end)
                self._buffer_bounds[position_id] = (buffer_start, buffer_end)

    def _update_position(self, position_id: str, start_ms: float, end_ms: float) -> None:
        position_data = self.app_data[position_id]
        
        # Lazy load log data if not already loaded
        # Use getattr for backward compatibility with cached PositionData objects
        log_data_loaded = getattr(position_data, '_log_data_loaded', False)
        log_file_paths = getattr(position_data, 'log_file_paths', [])
        
        if not log_data_loaded and log_file_paths:
            logger.info(f"[LAZY LOAD] Triggering lazy load for {position_id}")
            position_data.load_log_data_lazy(self.app_data.parser_factory, self.app_data.use_cache)
        
        model_bundle = self.position_models.get(position_id, {})
        logger.debug(f"[UPDATE] Position {position_id}: has_log_totals={position_data.has_log_totals}, has_log_spectral={position_data.has_log_spectral}")
        logger.debug(f"[UPDATE] Position {position_id}: model_bundle keys={list(model_bundle.keys())}")
        if position_data.has_log_totals:
            self._update_log_totals(position_data.log_totals, model_bundle, start_ms, end_ms)
        if position_data.has_log_spectral:
            logger.info(f"[UPDATE] Updating spectrogram for {position_id}")
            self._update_log_spectrogram(position_data.log_spectral, model_bundle, start_ms, end_ms)

    def _update_log_totals(self, df: pd.DataFrame, model_bundle: Dict[str, object], start_ms: float, end_ms: float) -> None:
        timeseries_source = model_bundle.get('timeseries_log_source')
        if timeseries_source is None:
            logger.warning(f"[UPDATE] timeseries_log_source is None - cannot push log totals")
            return
        if df is None or df.empty:
            logger.warning(f"[UPDATE] log_totals df is None/empty - cannot push")
            return
        sliced = self._slice_by_time(df, start_ms, end_ms)
        if sliced.empty:
            logger.debug(f"[UPDATE] Sliced log_totals is empty for range {start_ms}-{end_ms}")
            return
        logger.info(f"[UPDATE] Pushing {len(sliced)} log totals rows to timeseries source")
        
        # Stream full-resolution log data (no downsampling)
        # Resolution can be anything from 0.1s to 60s depending on the source data
        data_dict = sliced.to_dict(orient='list')
        # Convert Datetime to int64 ms timestamps
        data_dict['Datetime'] = (pd.to_datetime(sliced['Datetime']).astype('int64') // 10**6).tolist()
        
        timeseries_source.data = data_dict

    def _update_log_spectrogram(self, df: pd.DataFrame, model_bundle: Dict[str, object], start_ms: float, end_ms: float) -> None:
        spectrogram_source = model_bundle.get('spectrogram_log_source')
        if spectrogram_source is None or df is None or df.empty:
            return
        param = self.selected_parameter
        param_columns = [col for col in df.columns if col.startswith(f"{param}_")]
        if not param_columns:
            return
        subset = df[['Datetime', *param_columns]]
        sliced = self._slice_by_time(subset, start_ms, end_ms)
        if sliced.empty:
            return
        
        # Stream full-resolution log spectrogram data (no downsampling)
        # Resolution can be anything from 0.1s to 60s depending on the source data
        prepared = self.processor.prepare_single_spectrogram_data(sliced, param, self.chart_settings)
        if prepared:
            # Send COMPLETE prepared data structure matching preparedGlyphData format
            # BUT: Bokeh ColumnDataSource requires ALL values to be sequences
            # So wrap EVERYTHING (arrays AND scalars) in single-element lists
            # This creates a "1-row table" where each cell can hold an array or scalar value
            new_data = {
                # Array fields (wrap in single-element lists)
                'levels_flat_transposed': [prepared['levels_flat_transposed'].tolist()],
                'times_ms': [prepared['times_ms']],
                'frequency_labels': [prepared['frequency_labels']],
                'frequencies_hz': [prepared['frequencies_hz']],
                # Metadata scalars (also wrap in single-element lists for Bokeh)
                'n_times': [prepared['n_times']],
                'n_freqs': [prepared['n_freqs']],
                'chunk_time_length': [prepared['chunk_time_length']],
                'time_step': [prepared['time_step']],
                'min_val': [prepared['min_val']],
                'max_val': [prepared['max_val']],
                'min_time': [prepared['min_time']],
                'max_time': [prepared['max_time']],
                # initial_glyph_data fields (already lists from prepared, keep them)
                'initial_glyph_data_x': [prepared['initial_glyph_data']['x']],
                'initial_glyph_data_y': [prepared['initial_glyph_data']['y']],
                'initial_glyph_data_dw': [prepared['initial_glyph_data']['dw']],
                'initial_glyph_data_dh': [prepared['initial_glyph_data']['dh']],
                'initial_glyph_data_image': [prepared['initial_glyph_data']['image'][0].tolist()],
            }

            # Log data structure for verification
            logger.debug(f"Pushing log spectrogram data: keys={list(new_data.keys())}")
            logger.debug(f"All columns have length 1 (Bokeh format): {all(len(v) == 1 for v in new_data.values())}")

            spectrogram_source.data = new_data

    def _slice_by_time(self, df: pd.DataFrame, start_ms: float, end_ms: float) -> pd.DataFrame:
        if df is None or df.empty or 'Datetime' not in df.columns:
            return df
        start, end = sorted([start_ms, end_ms])
        times = pd.to_datetime(df['Datetime'])
        # Create timezone-aware timestamps to match the data
        start_ts = pd.to_datetime(start, unit='ms', utc=True)
        end_ts = pd.to_datetime(end, unit='ms', utc=True)
        mask = (times >= start_ts) & (times <= end_ts)
        return df.loc[mask]

    def _buffer_covers_viewport(self, position_id: str, start_ms: float, end_ms: float) -> bool:
        """Check if current buffer covers viewport with 20% margin."""
        bounds = self._buffer_bounds.get(position_id)
        if not bounds:
            return False
        margin = (end_ms - start_ms) * 0.2
        return bounds[0] <= start_ms - margin and bounds[1] >= end_ms + margin
    
    def _calculate_buffer(self, start_ms: float, end_ms: float) -> tuple:
        """Calculate buffer as viewport ± 50%."""
        width = end_ms - start_ms
        return start_ms - width * 0.5, end_ms + width * 0.5
