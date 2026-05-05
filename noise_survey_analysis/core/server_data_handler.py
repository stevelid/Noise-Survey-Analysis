import logging
import time
from bisect import bisect_left
from typing import Dict, Optional

import numpy as np
import pandas as pd

from noise_survey_analysis.core.config import (
    CHART_SETTINGS,
    LOG_VIEW_MAX_VIEWPORT_SECONDS,
    LOG_VIEW_TARGET_ROWS,
    LOG_VIEW_MIN_VIEWPORT_SECONDS,
    LOG_VIEW_MAX_VIEWPORT_SECONDS_HIGH_RATE,
    LOG_VIEW_BUFFER_FRACTION_DEFAULT,
    LOG_VIEW_BUFFER_FRACTION_HIGH_RATE,
    LOG_VIEW_HIGH_RATE_THRESHOLD_SECONDS,
)
from noise_survey_analysis.core.data_processors import (
    GlyphDataProcessor,
    _calculate_spectrogram_log_window_ms,
    _peek_log_file_time_step_ms,
)
from noise_survey_analysis.core.data_manager import DataManager

logger = logging.getLogger(__name__)
DEBUG_POSITION = 'Residential boundary (971-2, 440 m)'


def _to_bokeh_ms(values) -> pd.Series:
    dt = pd.Series(pd.to_datetime(values, utc=True))
    return (
        dt.dt.tz_convert("UTC").dt.tz_localize(None).astype("datetime64[ns]").astype("int64") // 10**6
    ).to_numpy()


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
        self._spectrogram_chunk_bounds = {}
        self._range_update_counter = 0

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

    def _position_max_viewport_seconds(self, position_data) -> float:
        """
        Calculate max viewport based on sample period and row budget.
        
        For high-rate data (<=1s), limit viewport to keep row count bounded.
        For low-rate data, allow wider viewports up to the global max.
        """
        sample_period_seconds = self._get_effective_sample_period(position_data)
        
        if sample_period_seconds is None or sample_period_seconds <= 0:
            # Unknown sample period - use global max as fallback
            return float(LOG_VIEW_MAX_VIEWPORT_SECONDS)
        
        
        # Calculate max viewport based on row budget
        # max_seconds = target_rows * sample_period
        max_from_budget = LOG_VIEW_TARGET_ROWS * sample_period_seconds
        
        # Check if this is high-rate data
        is_high_rate = sample_period_seconds <= LOG_VIEW_HIGH_RATE_THRESHOLD_SECONDS
        
        if is_high_rate:
            # Clamp to high-rate max (e.g., 1 hour for 100ms data)
            max_viewport = min(max_from_budget, LOG_VIEW_MAX_VIEWPORT_SECONDS_HIGH_RATE)
        else:
            # For low-rate data, allow wider viewports
            max_viewport = min(max_from_budget, LOG_VIEW_MAX_VIEWPORT_SECONDS)
        
        # Ensure minimum viewport
        max_viewport = max(max_viewport, LOG_VIEW_MIN_VIEWPORT_SECONDS)
        
        logger.debug(
            "Max viewport for %s: %.0fs (sample_period=%.3fs, is_high_rate=%s)",
            getattr(position_data, 'name', 'unknown'),
            max_viewport,
            sample_period_seconds,
            is_high_rate,
        )
        return max_viewport

    def _position_max_spectrogram_viewport_seconds(self, position_data, sample_period_seconds: Optional[float] = None) -> Optional[float]:
        if position_data is None or not getattr(position_data, 'has_log_spectral', False):
            return None

        effective_sample_period = sample_period_seconds
        if effective_sample_period is None or effective_sample_period <= 0:
            effective_sample_period = self._get_effective_sample_period(position_data)

        if effective_sample_period is None or effective_sample_period <= 0:
            return None

        spectrogram_window_ms = _calculate_spectrogram_log_window_ms(effective_sample_period * 1000.0, self.chart_settings)
        max_viewport_seconds = max(LOG_VIEW_MIN_VIEWPORT_SECONDS, spectrogram_window_ms / 1000.0)
        logger.debug(
            "Max spectrogram viewport for %s: %.0fs (sample_period=%.3fs)",
            getattr(position_data, 'name', 'unknown'),
            max_viewport_seconds,
            effective_sample_period,
        )
        return max_viewport_seconds

    def handle_range_update(self, start_ms: float, end_ms: float) -> None:
        if not isinstance(start_ms, (int, float)) or not isinstance(end_ms, (int, float)):
            return

        self._range_update_counter += 1
        request_id = self._range_update_counter
        viewport_width_ms = abs(end_ms - start_ms)
        viewport_width_seconds = viewport_width_ms / 1000
        logger.debug(
            "[RANGE] request=%s start_ms=%s end_ms=%s width_s=%.3f",
            request_id,
            start_ms,
            end_ms,
            viewport_width_seconds,
        )

        # Evaluate stream eligibility per position so low-sample-rate positions
        # can stream wider windows than high-sample-rate ones.
        for position_id in self.app_data.positions():
            position_data = self.app_data[position_id]
            max_viewport_seconds = self._position_max_viewport_seconds(position_data)
            sample_period_seconds = self._get_effective_sample_period(position_data)
            spectrogram_max_viewport_seconds = self._position_max_spectrogram_viewport_seconds(
                position_data,
                sample_period_seconds,
            )
            buffer_bounds = self._buffer_bounds.get(position_id)
            chunk_bounds = self._spectrogram_chunk_bounds.get(position_id)
            if viewport_width_seconds > max_viewport_seconds:
                logger.debug(
                    "Viewport too large for %s (%.0fs > %.0fs), skipping log stream [request=%s sample_period=%.3fs buffer_bounds=%s chunk_bounds=%s]",
                    position_id,
                    viewport_width_seconds,
                    max_viewport_seconds,
                    request_id,
                    sample_period_seconds if sample_period_seconds is not None else -1,
                    buffer_bounds,
                    chunk_bounds,
                )
                continue

            if not self._buffer_covers_viewport(position_id, start_ms, end_ms):
                buffer_start, buffer_end = self._calculate_buffer(start_ms, end_ms, position_data)
                logger.debug(
                    "[RANGE] request=%s position=%s action=refresh_buffer viewport=(%s, %s) existing_buffer=%s new_buffer=(%s, %s) chunk_bounds=%s",
                    request_id,
                    position_id,
                    start_ms,
                    end_ms,
                    buffer_bounds,
                    buffer_start,
                    buffer_end,
                    chunk_bounds,
                )
                self._update_position(
                    position_id,
                    buffer_start,
                    buffer_end,
                    viewport_start_ms=start_ms,
                    viewport_end_ms=end_ms,
                    sample_period_seconds=sample_period_seconds,
                )
                self._buffer_bounds[position_id] = (buffer_start, buffer_end)
                continue

            # Reservoir coverage check: refresh reservoir when viewport is not
            # adequately covered by the current reservoir bounds.  Unlike the old
            # chunk-window gate, the viewport no longer has to fit inside one
            # fixed display chunk — the browser extracts the display chunk from
            # the wider reservoir client-side.
            reservoir_coverage = self._spectrogram_chunk_coverage_ratio(position_id, start_ms, end_ms)
            if position_data.has_log_spectral and reservoir_coverage < 0.98:
                buffer_start, buffer_end = self._buffer_bounds[position_id]
                logger.debug(
                    "[RANGE] request=%s position=%s action=refresh_reservoir viewport=(%s, %s) buffer=(%s, %s) reservoir_bounds=%s reservoir_coverage=%.3f",
                    request_id,
                    position_id,
                    start_ms,
                    end_ms,
                    buffer_start,
                    buffer_end,
                    chunk_bounds,
                    reservoir_coverage,
                )
                self._update_position(
                    position_id,
                    buffer_start,
                    buffer_end,
                    viewport_start_ms=start_ms,
                    viewport_end_ms=end_ms,
                    sample_period_seconds=sample_period_seconds,
                    refresh_totals=False,
                )
            else:
                logger.debug(
                    "[RANGE] request=%s position=%s action=reuse_existing_reservoir buffer_bounds=%s reservoir_bounds=%s reservoir_coverage=%.3f",
                    request_id,
                    position_id,
                    buffer_bounds,
                    chunk_bounds,
                    reservoir_coverage,
                )

    def _update_position(
        self,
        position_id: str,
        start_ms: float,
        end_ms: float,
        viewport_start_ms: Optional[float] = None,
        viewport_end_ms: Optional[float] = None,
        sample_period_seconds: Optional[float] = None,
        refresh_totals: bool = True,
    ) -> None:
        position_data = self.app_data[position_id]
        update_started_at = time.perf_counter()
        lazy_load_ms = 0.0
        totals_update_ms = 0.0
        spectrogram_update_ms = 0.0
        
        # Lazy load log data if not already loaded
        # Use getattr for backward compatibility with cached PositionData objects
        log_data_loaded = getattr(position_data, '_log_data_loaded', False)
        log_file_paths = getattr(position_data, 'log_file_paths', [])
        
        if not log_data_loaded and log_file_paths:
            logger.info(f"[LAZY LOAD] Triggering lazy load for {position_id}")
            lazy_load_started_at = time.perf_counter()
            position_data.load_log_data_lazy(self.app_data.parser_factory, self.app_data.use_cache)
            lazy_load_ms = (time.perf_counter() - lazy_load_started_at) * 1000

        if viewport_start_ms is None:
            viewport_start_ms = start_ms
        if viewport_end_ms is None:
            viewport_end_ms = end_ms
        
        logger.debug(
            "[UPDATE] Position %s: range=(%s, %s) viewport=(%s, %s) refresh_totals=%s",
            position_id,
            start_ms,
            end_ms,
            viewport_start_ms,
            viewport_end_ms,
            refresh_totals,
        )
        model_bundle = self.position_models.get(position_id, {})
        logger.debug(f"[UPDATE] Position {position_id}: has_log_totals={position_data.has_log_totals}, has_log_spectral={position_data.has_log_spectral}")
        logger.debug(f"[UPDATE] Position {position_id}: model_bundle keys={list(model_bundle.keys())}")
        if refresh_totals and position_data.has_log_totals:
            totals_started_at = time.perf_counter()
            self._update_log_totals(position_data.log_totals, model_bundle, start_ms, end_ms)
            totals_update_ms = (time.perf_counter() - totals_started_at) * 1000
        if position_data.has_log_spectral:
            logger.info(f"[UPDATE] Updating spectrogram for {position_id}")
            spectrogram_started_at = time.perf_counter()
            self._update_log_spectrogram(
                position_data.log_spectral,
                model_bundle,
                start_ms,
                end_ms,
                viewport_start_ms=viewport_start_ms,
                viewport_end_ms=viewport_end_ms,
                position_id=position_id,
                position_data=position_data,
                sample_period_seconds=sample_period_seconds,
            )
            spectrogram_update_ms = (time.perf_counter() - spectrogram_started_at) * 1000
        logger.info(
            "[STREAM PERF] position=%s lazy_load_ms=%.1f totals_update_ms=%.1f spectrogram_update_ms=%.1f total_ms=%.1f",
            position_id,
            lazy_load_ms,
            totals_update_ms,
            spectrogram_update_ms,
            (time.perf_counter() - update_started_at) * 1000,
        )

    def _update_log_totals(self, df: pd.DataFrame, model_bundle: Dict[str, object], start_ms: float, end_ms: float) -> None:
        timeseries_source = model_bundle.get('timeseries_log_source')
        if timeseries_source is None:
            logger.warning(f"[UPDATE] timeseries_log_source is None - cannot push log totals")
            return
        if df is None or df.empty:
            logger.warning(f"[UPDATE] log_totals df is None/empty - cannot push")
            return
        update_started_at = time.perf_counter()
        slice_started_at = time.perf_counter()
        sliced = self._slice_by_time(df, start_ms, end_ms)
        slice_ms = (time.perf_counter() - slice_started_at) * 1000
        if sliced.empty:
            logger.debug(f"[UPDATE] Sliced log_totals is empty for range {start_ms}-{end_ms}")
            return
        logger.info(f"[UPDATE] Pushing {len(sliced)} log totals rows to timeseries source")
        figure = model_bundle.get('timeseries_figure')
        if figure is not None and getattr(figure, 'name', '') == f'figure_{DEBUG_POSITION}_timeseries':
            logger.info(
                "[TH DEBUG] rows=%s first=%s last=%s requested_start_ms=%s requested_end_ms=%s",
                len(sliced),
                sliced['Datetime'].iloc[0],
                sliced['Datetime'].iloc[-1],
                start_ms,
                end_ms,
            )
        
        # Stream full-resolution log data (no downsampling)
        # Resolution can be anything from 0.1s to 60s depending on the source data
        build_started_at = time.perf_counter()
        data_dict = sliced.to_dict(orient='list')
        # Convert Datetime to int64 ms timestamps
        data_dict['Datetime'] = _to_bokeh_ms(sliced['Datetime']).tolist()
        build_ms = (time.perf_counter() - build_started_at) * 1000
        
        push_started_at = time.perf_counter()
        timeseries_source.data = data_dict
        push_ms = (time.perf_counter() - push_started_at) * 1000
        logger.info(
            "[TH PERF] rows=%s cols=%s slice_ms=%.1f build_ms=%.1f push_ms=%.1f total_ms=%.1f",
            len(sliced),
            len(data_dict),
            slice_ms,
            build_ms,
            push_ms,
            (time.perf_counter() - update_started_at) * 1000,
        )

    def _update_log_spectrogram(
        self,
        df: pd.DataFrame,
        model_bundle: Dict[str, object],
        start_ms: float,
        end_ms: float,
        viewport_start_ms: Optional[float] = None,
        viewport_end_ms: Optional[float] = None,
        position_id: Optional[str] = None,
        position_data=None,
        sample_period_seconds: Optional[float] = None,
    ) -> None:
        spectrogram_source = model_bundle.get('spectrogram_log_source')
        if spectrogram_source is None:
            logger.debug("[SPEC SKIP] position=%s reason=no_spectrogram_source", position_id)
            if position_id is not None:
                self._spectrogram_chunk_bounds.pop(position_id, None)
            return
        if df is None or df.empty:
            logger.debug("[SPEC SKIP] position=%s reason=empty_spectral_df", position_id)
            if position_id is not None:
                self._spectrogram_chunk_bounds.pop(position_id, None)
            return
        update_started_at = time.perf_counter()
        param = self.selected_parameter
        if viewport_start_ms is None:
            viewport_start_ms = start_ms
        if viewport_end_ms is None:
            viewport_end_ms = end_ms
        subset_started_at = time.perf_counter()
        param_columns = [col for col in df.columns if col.startswith(f"{param}_")]
        subset_ms = (time.perf_counter() - subset_started_at) * 1000
        if not param_columns:
            logger.debug("[SPEC SKIP] position=%s reason=missing_param_columns param=%s", position_id, param)
            if position_id is not None:
                self._spectrogram_chunk_bounds.pop(position_id, None)
            return
        subset = df[['Datetime', *param_columns]]
        slice_started_at = time.perf_counter()
        sliced = self._slice_by_time(subset, start_ms, end_ms)
        slice_ms = (time.perf_counter() - slice_started_at) * 1000
        if sliced.empty:
            logger.debug(
                "[SPEC SKIP] position=%s reason=empty_time_slice range=(%s, %s) viewport=(%s, %s)",
                position_id,
                start_ms,
                end_ms,
                viewport_start_ms,
                viewport_end_ms,
            )
            if position_id is not None:
                self._spectrogram_chunk_bounds.pop(position_id, None)
            return
        figure = model_bundle.get('spectrogram_figure')
        if figure is not None and getattr(figure, 'name', '') == f'figure_{DEBUG_POSITION}_spectrogram':
            logger.info(
                "[SPEC DEBUG] rows=%s first=%s last=%s requested_start_ms=%s requested_end_ms=%s param=%s",
                len(sliced),
                sliced['Datetime'].iloc[0],
                sliced['Datetime'].iloc[-1],
                start_ms,
                end_ms,
                param,
            )

        # Stream reservoir payload: send the full prepared data as NumPy arrays.
        # The browser extracts the visible display chunk from this reservoir,
        # allowing panning within the reservoir without a new server round-trip.
        prepare_started_at = time.perf_counter()
        prepared = self.processor.prepare_single_spectrogram_data(
            sliced, param, self.chart_settings, use_dynamic_log_window=True
        )
        prepare_ms = (time.perf_counter() - prepare_started_at) * 1000
        if prepared:
            log_cells = prepared['n_freqs'] * prepared['chunk_time_length']
            logger.debug(
                "[SPEC] Reservoir: n_times=%s chunk_time_length=%s n_freqs=%s cells=%s",
                prepared['n_times'],
                prepared['chunk_time_length'],
                prepared['n_freqs'],
                log_cells,
            )
            if figure is not None and getattr(figure, 'name', '') == f'figure_{DEBUG_POSITION}_spectrogram':
                logger.info(
                    "[SPEC DEBUG] prepared n_times=%s chunk_time_length=%s time_step=%s min_time=%s max_time=%s initial_x=%s initial_dw=%s cells=%s",
                    prepared['n_times'],
                    prepared['chunk_time_length'],
                    prepared['time_step'],
                    prepared['min_time'],
                    prepared['max_time'],
                    prepared['initial_glyph_data']['x'][0],
                    prepared['initial_glyph_data']['dw'][0],
                    log_cells,
                )

            build_started_at = time.perf_counter()

            # Build reservoir payload: send full prepared backing data as NumPy arrays.
            # The browser will extract the display chunk client-side.
            reservoir_times = np.asarray(prepared['times_ms'], dtype=np.float64)
            reservoir_levels = np.asarray(prepared['levels_flat_transposed'], dtype=np.float32)
            reservoir_n_times = len(reservoir_times)
            reservoir_n_freqs = prepared['n_freqs']
            chunk_time_length = prepared['chunk_time_length']

            logger.debug(
                "[SPEC RESERVOIR] position=%s viewport=(%s, %s) slice=(%s, %s) reservoir_n_times=%s chunk_time_length=%s n_freqs=%s",
                position_id,
                viewport_start_ms,
                viewport_end_ms,
                start_ms,
                end_ms,
                reservoir_n_times,
                chunk_time_length,
                reservoir_n_freqs,
            )

            new_data = {
                'levels_flat_transposed': [reservoir_levels],
                'times_ms': [reservoir_times],
                'parameter': [param],
                'frequency_labels': [prepared['frequency_labels']],
                'frequencies_hz': [prepared['frequencies_hz']],
                'n_times': [reservoir_n_times],
                'n_freqs': [reservoir_n_freqs],
                'chunk_time_length': [chunk_time_length],
                'time_step': [prepared['time_step']],
                'min_val': [prepared['min_val']],
                'max_val': [prepared['max_val']],
                'min_time': [float(reservoir_times[0])],
                'max_time': [float(reservoir_times[-1])],
                'initial_glyph_data_x': [prepared['initial_glyph_data']['x']],
                'initial_glyph_data_y': [prepared['initial_glyph_data']['y']],
                'initial_glyph_data_dw': [prepared['initial_glyph_data']['dw']],
                'initial_glyph_data_dh': [prepared['initial_glyph_data']['dh']],
                'initial_glyph_data_image': [prepared['initial_glyph_data']['image'][0].tolist()],
                'is_reservoir_payload': [True],
            }
            build_ms = (time.perf_counter() - build_started_at) * 1000

            # Log data structure for verification
            logger.debug(f"Pushing reservoir spectrogram data: keys={list(new_data.keys())}")
            logger.debug(f"All columns have length 1 (Bokeh format): {all(len(v) == 1 for v in new_data.values())}")

            push_started_at = time.perf_counter()
            spectrogram_source.data = new_data
            if position_id is not None:
                self._spectrogram_chunk_bounds[position_id] = (float(reservoir_times[0]), float(reservoir_times[-1]))
            push_ms = (time.perf_counter() - push_started_at) * 1000
            logger.info(
                "[SPEC PERF] param=%s rows=%s bands=%s chunk_time_length=%s reservoir_n_times=%s levels_len=%s subset_ms=%.1f slice_ms=%.1f prepare_ms=%.1f build_ms=%.1f push_ms=%.1f total_ms=%.1f",
                param,
                len(sliced),
                len(param_columns),
                chunk_time_length,
                reservoir_n_times,
                len(reservoir_levels),
                subset_ms,
                slice_ms,
                prepare_ms,
                build_ms,
                push_ms,
                (time.perf_counter() - update_started_at) * 1000,
            )
        else:
            logger.debug(
                "[SPEC SKIP] position=%s reason=prepare_single_spectrogram_data_returned_none range=(%s, %s) viewport=(%s, %s) param=%s",
                position_id,
                start_ms,
                end_ms,
                viewport_start_ms,
                viewport_end_ms,
                param,
            )

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
        """Check if current buffer covers viewport with 10% margin."""
        bounds = self._buffer_bounds.get(position_id)
        if not bounds:
            return False
        margin = (end_ms - start_ms) * 0.1
        return bounds[0] <= start_ms - margin and bounds[1] >= end_ms + margin

    def _spectrogram_chunk_coverage_ratio(self, position_id: str, start_ms: float, end_ms: float) -> float:
        bounds = self._spectrogram_chunk_bounds.get(position_id)
        if not bounds:
            return 0.0
        viewport_start, viewport_end = sorted([start_ms, end_ms])
        viewport_width = viewport_end - viewport_start
        if viewport_width <= 0:
            return 1.0 if bounds[0] <= viewport_start <= bounds[1] else 0.0
        overlap_start = max(viewport_start, bounds[0])
        overlap_end = min(viewport_end, bounds[1])
        overlap_width = max(0, overlap_end - overlap_start)
        return overlap_width / viewport_width

    def _spectrogram_chunk_covers_viewport(self, position_id: str, start_ms: float, end_ms: float) -> bool:
        return self._spectrogram_chunk_coverage_ratio(position_id, start_ms, end_ms) >= 0.98

    def _infer_log_file_sample_period_seconds(self, position_data):
        log_file_paths = getattr(position_data, 'log_file_paths', None)
        if not log_file_paths:
            return None

        cached_inferred_period = getattr(position_data, '_inferred_sample_period_seconds', None)
        if cached_inferred_period is not None and cached_inferred_period > 0:
            logger.debug(
                "Using cached inferred sample period for %s: %.3fs",
                getattr(position_data, 'name', 'unknown'),
                cached_inferred_period,
            )
            return cached_inferred_period

        time_step_ms = _peek_log_file_time_step_ms(log_file_paths)
        if time_step_ms > 0:
            sample_period_seconds = time_step_ms / 1000.0
            position_data._inferred_sample_period_seconds = sample_period_seconds
            logger.debug(
                "Estimated and cached sample period from log file for %s: %.3fs",
                getattr(position_data, 'name', 'unknown'),
                sample_period_seconds,
            )
            return sample_period_seconds

        return None
    
    def _get_effective_sample_period(self, position_data):
        """Get effective sample period, checking both metadata and inferred log cadence."""
        candidate_periods = []
        sample_periods = getattr(position_data, 'sample_periods_seconds', None)
        if sample_periods:
            valid_periods = [p for p in sample_periods if p is not None and p > 0]
            if valid_periods:
                candidate_periods.extend(valid_periods)

        inferred_period = self._infer_log_file_sample_period_seconds(position_data)
        if inferred_period is not None and inferred_period > 0:
            candidate_periods.append(inferred_period)

        if not candidate_periods:
            return None

        effective_period = min(candidate_periods)
        logger.debug(
            "Resolved effective sample period for %s: %.3fs from candidates=%s",
            getattr(position_data, 'name', 'unknown'),
            effective_period,
            sorted(set(round(period, 6) for period in candidate_periods)),
        )
        return effective_period

    def _calculate_buffer(self, start_ms: float, end_ms: float, position_data=None) -> tuple:
        """
        Calculate buffer with adaptive fraction based on sample period.
        
        High-rate data gets smaller buffer (10%) to limit payload size.
        Low-rate data gets larger buffer (50%) for smoother panning.
        """
        width = end_ms - start_ms
        
        # Determine buffer fraction based on sample period
        buffer_fraction = LOG_VIEW_BUFFER_FRACTION_DEFAULT  # Default 50%
        
        if position_data is not None:
            effective_period = self._get_effective_sample_period(position_data)
            if effective_period is not None and effective_period <= LOG_VIEW_HIGH_RATE_THRESHOLD_SECONDS:
                buffer_fraction = LOG_VIEW_BUFFER_FRACTION_HIGH_RATE  # 10% for high-rate
        
        buffer_width = width * buffer_fraction
        return start_ms - buffer_width, end_ms + buffer_width
