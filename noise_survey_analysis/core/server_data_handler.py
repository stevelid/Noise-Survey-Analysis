import logging
import math
import threading
import time
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
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
from noise_survey_analysis.core.utils import to_bokeh_ms

logger = logging.getLogger(__name__)


def _debug_position() -> str:
    import os
    return os.environ.get('NSA_DEBUG_POSITION', '')


def _to_bokeh_ms(values) -> np.ndarray:
    return to_bokeh_ms(values)


class ServerDataHandler:
    _TIME_INDEX_CACHE_LIMIT = 16

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
        self._display_buffer_width = {}  # position_id -> pinned Image glyph buffer width
        self._time_index_cache = {}  # id(df) -> (df, int64 ms array or None)
        self._last_requested_range = None  # newest viewport, for deferred refreshes
        self._disposed = False
        self._lazy_load_lock = threading.Lock()
        self._lazy_load_in_flight = set()
        self._lazy_load_failed = set()
        self._lazy_load_futures = set()
        # Serialized: log files usually sit on a network drive, and loading several
        # multi-day files at once spikes memory without helping the user.
        self._lazy_load_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='nsa-lazy-load'
        )

    def _collect_position_models(self) -> Dict[str, Dict[str, object]]:
        models: Dict[str, Dict[str, object]] = {}
        for position_id in self.app_data.positions():
            models[position_id] = {
                # Push to log_source (reservoir) instead of display source
                'timeseries_log_source': self.doc.get_model_by_name(f"source_{position_id}_timeseries_log"),
                'spectrogram_log_source': self.doc.get_model_by_name(f"source_{position_id}_spectrogram_log"),
                # The display source is the one bound to the Image glyph.  Its buffer is
                # sized once at init and must never change shape — it is the authority on
                # how wide every streamed chunk has to be.
                'spectrogram_display_source': self.doc.get_model_by_name(f"source_{position_id}_spectrogram"),
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
        # Remembered so a background lazy load that finishes later refreshes against the
        # viewport the user is actually looking at, not the one that triggered it.
        self._last_requested_range = (start_ms, end_ms)
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
                streamed = self._update_position(
                    position_id,
                    buffer_start,
                    buffer_end,
                    viewport_start_ms=start_ms,
                    viewport_end_ms=end_ms,
                    sample_period_seconds=sample_period_seconds,
                )
                # Only record coverage when data actually went out. A deferred lazy load
                # has streamed nothing, so claiming coverage here would make every later
                # update skip this position - including the refresh the load itself
                # schedules once it finishes.
                if streamed:
                    self._buffer_bounds[position_id] = (buffer_start, buffer_end)
                else:
                    self._buffer_bounds.pop(position_id, None)
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
    ) -> bool:
        """Push this position's data. Returns False if it deferred to a background load."""
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
            # Parsing a multi-day log file takes seconds. Bokeh runs document callbacks
            # on a single IOLoop, so doing it here freezes the whole dashboard until it
            # finishes. Start it in the background and leave this position on overview
            # data; the client already shows a "waiting for log data" status while its
            # log source is empty. The load re-enters this method when it completes.
            self._ensure_lazy_load_started(position_id, position_data)
            return False

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
        return True

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
        sliced, sliced_times_ms = self._slice_by_time_with_index(df, start_ms, end_ms)
        slice_ms = (time.perf_counter() - slice_started_at) * 1000
        if sliced.empty:
            logger.debug(f"[UPDATE] Sliced log_totals is empty for range {start_ms}-{end_ms}")
            return
        logger.info(f"[UPDATE] Pushing {len(sliced)} log totals rows to timeseries source")
        figure = model_bundle.get('timeseries_figure')
        debug_pos = _debug_position()
        if debug_pos and figure is not None and getattr(figure, 'name', '') == f'figure_{debug_pos}_timeseries':
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
        # Keep columns as NumPy arrays: Bokeh serializes ndarrays over its binary
        # protocol, whereas Python lists go out as JSON text.
        build_started_at = time.perf_counter()
        data_dict = {}
        for column in sliced.columns:
            if column == 'Datetime':
                continue
            values = sliced[column].to_numpy()
            # Non-numeric columns gain nothing from the binary path; hand Bokeh a list
            # rather than an object-dtype array it would have to unpack anyway.
            data_dict[column] = values if values.dtype.kind in 'fiub' else values.tolist()
        # Reuse the cached index slice when the fast path produced one; only fall back to
        # converting when the frame was sliced by mask.
        data_dict['Datetime'] = (
            sliced_times_ms if sliced_times_ms is not None else _to_bokeh_ms(sliced['Datetime'])
        )
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

    def _ensure_lazy_load_started(self, position_id: str, position_data) -> None:
        """
        Kick off this position's deferred log parse in the background, at most once.

        Source files often live on a network drive, so the loads are serialized through a
        single worker rather than run in parallel. When one finishes it re-runs the range
        update on the document thread, using the viewport current at that moment - the
        user has usually kept panning while it was loading.
        """
        if self._disposed:
            return
        with self._lazy_load_lock:
            if position_id in self._lazy_load_in_flight:
                return
            self._lazy_load_in_flight.add(position_id)
            # Retried only because the user navigated back here, never in a tight loop.
            retrying = position_id in self._lazy_load_failed
            self._lazy_load_failed.discard(position_id)

        logger.info(
            "[LAZY LOAD] %s background load for %s",
            "Retrying" if retrying else "Starting",
            position_id,
        )
        try:
            future = self._lazy_load_executor.submit(self._run_lazy_load, position_id, position_data)
        except RuntimeError:
            # The executor was shut down between the disposed check and here.
            logger.debug("[LAZY LOAD] Executor closed; not starting %s", position_id)
            with self._lazy_load_lock:
                self._lazy_load_in_flight.discard(position_id)
            return
        with self._lazy_load_lock:
            self._lazy_load_futures.add(future)
        future.add_done_callback(self._forget_lazy_load_future)

    def _forget_lazy_load_future(self, future) -> None:
        with self._lazy_load_lock:
            self._lazy_load_futures.discard(future)

    def _run_lazy_load(self, position_id: str, position_data) -> None:
        started_at = time.perf_counter()
        succeeded = False
        try:
            # load_log_data_lazy absorbs per-file errors, so its return value - not the
            # absence of an exception - is what says whether any data arrived.
            succeeded = bool(
                position_data.load_log_data_lazy(self.app_data.parser_factory, self.app_data.use_cache)
            )
            if succeeded:
                logger.info(
                    "[LAZY LOAD] Completed for %s in %.0f ms",
                    position_id,
                    (time.perf_counter() - started_at) * 1000,
                )
            else:
                logger.error("[LAZY LOAD] Loaded no data for %s; will retry if revisited", position_id)
        except Exception:
            logger.error("[LAZY LOAD] Failed for %s", position_id, exc_info=True)
        finally:
            with self._lazy_load_lock:
                self._lazy_load_in_flight.discard(position_id)
                if not succeeded:
                    self._lazy_load_failed.add(position_id)

        if succeeded:
            self._schedule_refresh_after_lazy_load(position_id)

    def _schedule_refresh_after_lazy_load(self, position_id: str) -> None:
        """Re-run the range update on the document thread once loaded data is available."""
        if self._disposed:
            return

        pending = self._last_requested_range
        if pending is None:
            logger.debug("[LAZY LOAD] No viewport recorded for %s; nothing to refresh", position_id)
            return

        def refresh():
            if self._disposed:
                return
            # Read the range again here rather than closing over the one captured above:
            # the user may have panned between the load finishing and this callback running.
            latest = self._last_requested_range
            if latest is None:
                return
            logger.info("[LAZY LOAD] Refreshing %s at viewport %s", position_id, latest)
            try:
                self.handle_range_update(*latest)
            except Exception:
                logger.error("[LAZY LOAD] Refresh failed for %s", position_id, exc_info=True)

        try:
            self.doc.add_next_tick_callback(refresh)
        except Exception:
            # The session can be torn down while a load is in flight.
            logger.debug("[LAZY LOAD] Could not schedule refresh for %s", position_id, exc_info=True)

    def cleanup(self) -> None:
        """
        Release background workers. Safe to call more than once.

        Loads are queued one behind another, so without explicit cancellation the
        remaining positions would each start a multi-day parse after the session had
        already closed. A parse already under way is left to finish - interrupting it is
        not possible - but `_disposed` stops it publishing to the dead document.
        """
        self._disposed = True
        with self._lazy_load_lock:
            pending = list(self._lazy_load_futures)

        cancelled = [future for future in pending if future.cancel()]
        if cancelled:
            # A cancelled job never runs _run_lazy_load, so it would otherwise leave its
            # position marked in-flight forever.
            logger.info("[LAZY LOAD] Cancelled %s queued load(s) during cleanup", len(cancelled))
            with self._lazy_load_lock:
                for future in cancelled:
                    self._lazy_load_futures.discard(future)

        try:
            self._lazy_load_executor.shutdown(wait=False)
        except Exception as exc:
            logger.warning("Error shutting down lazy load executor: %s", exc)

    def _resolve_display_buffer_width(self, position_id: str, model_bundle: Dict[str, object]) -> Optional[int]:
        """
        Return the pinned width (time bins) of this position's Image glyph buffer.

        The browser's ``source.data.image`` buffer is fixed-size after initialization
        (AGENTS.md §6).  Every streamed chunk therefore has to be exactly as wide as the
        buffer that was created at init, otherwise the client's shape guard rejects the
        update and the spectrogram silently stops refreshing.

        The initialized display source is the ground truth for that width, so read it
        back rather than re-deriving it from the streamed slice's cadence.
        """
        if position_id in self._display_buffer_width:
            return self._display_buffer_width[position_id]

        width: Optional[int] = None
        display_source = model_bundle.get('spectrogram_display_source')
        image_column = getattr(display_source, 'data', {}).get('image') if display_source is not None else None

        if image_column is not None and len(image_column) > 0:
            buffer = image_column[0]
            try:
                shape = getattr(buffer, 'shape', None)
                if shape is not None and len(shape) == 2:
                    # (n_freqs, chunk_time_length)
                    width = int(shape[1])
                elif buffer is not None and len(buffer) > 0 and hasattr(buffer[0], '__len__'):
                    width = int(len(buffer[0]))
            except (TypeError, IndexError, ValueError):
                width = None

        if width is not None and width > 0:
            logger.info(
                "[SPEC PIN] position=%s display buffer width pinned to %s bins",
                position_id,
                width,
            )
            self._display_buffer_width[position_id] = width
            return width

        # No initialized buffer to read (e.g. a position whose spectrogram has not been
        # built yet).  Fall back to the dynamic window so behaviour is unchanged.
        logger.debug(
            "[SPEC PIN] position=%s no initialized display buffer; falling back to dynamic window",
            position_id,
        )
        return None

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
        # Slice rows before selecting columns.  The other order copies every band across
        # the whole survey (4 days of 1 s data x ~36 bands is ~100 MB) only to discard
        # all but the viewport, on every pan and zoom.
        slice_started_at = time.perf_counter()
        sliced_rows = self._slice_by_time(df, start_ms, end_ms)
        sliced = sliced_rows[['Datetime', *param_columns]]
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
        debug_pos = _debug_position()
        if debug_pos and figure is not None and getattr(figure, 'name', '') == f'figure_{debug_pos}_spectrogram':
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
        pinned_chunk_time_length = self._resolve_display_buffer_width(position_id, model_bundle)
        prepared = self.processor.prepare_single_spectrogram_data(
            sliced,
            param,
            self.chart_settings,
            use_dynamic_log_window=True,
            fixed_n_times=pinned_chunk_time_length,
        )
        prepare_ms = (time.perf_counter() - prepare_started_at) * 1000
        if prepared:
            if (
                pinned_chunk_time_length is not None
                and prepared['chunk_time_length'] != pinned_chunk_time_length
            ):
                # Should be unreachable now that the pin is honoured; loud if it ever is.
                logger.warning(
                    "[SPEC PIN] position=%s chunk_time_length=%s does not match pinned buffer width %s; "
                    "the client will reject this update",
                    position_id,
                    prepared['chunk_time_length'],
                    pinned_chunk_time_length,
                )
            log_cells = prepared['n_freqs'] * prepared['chunk_time_length']
            logger.debug(
                "[SPEC] Reservoir: n_times=%s chunk_time_length=%s n_freqs=%s cells=%s",
                prepared['n_times'],
                prepared['chunk_time_length'],
                prepared['n_freqs'],
                log_cells,
            )
            if debug_pos and figure is not None and getattr(figure, 'name', '') == f'figure_{debug_pos}_spectrogram':
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
            # Levels are rounded to int16 during preparation; keep that width rather
            # than upcasting, which doubles the payload for no extra precision.
            reservoir_levels = np.ascontiguousarray(prepared['levels_flat_transposed'])
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
                # Glyph metadata only.  `initial_glyph_data.image` is the leading chunk of
                # levels_flat_transposed, which is already in this payload, and the client
                # extracts its display chunk from the reservoir rather than from those
                # pixels.  Sending them meant a second copy of the same data, serialized
                # as JSON text instead of a binary buffer.
                'initial_glyph_data_x': [prepared['initial_glyph_data']['x']],
                'initial_glyph_data_y': [prepared['initial_glyph_data']['y']],
                'initial_glyph_data_dw': [prepared['initial_glyph_data']['dw']],
                'initial_glyph_data_dh': [prepared['initial_glyph_data']['dh']],
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

    def _time_index_ms(self, df: pd.DataFrame) -> Optional[np.ndarray]:
        """
        Return a cached int64-ms view of ``df['Datetime']``, or None if it is unusable.

        Converting the Datetime column is O(n) over the whole survey, and the streaming
        path slices on every pan and zoom.  Building it once per frame turns each slice
        into a pair of binary searches.  Returns None when the column is not sorted, so
        callers fall back to the mask path that does not assume ordering.
        """
        cache_key = id(df)
        cached = self._time_index_cache.get(cache_key)
        # Hold a strong reference to the frame alongside the array so the id() key
        # cannot be recycled onto a different object while the entry is live.
        if cached is not None and cached[0] is df:
            return cached[1]

        # Only a couple of frames per position are ever indexed, but lazy loading
        # replaces them, and entries hold a strong reference.  Drop the lot rather than
        # pin superseded frames in memory; a miss only costs one rebuild.
        if len(self._time_index_cache) >= self._TIME_INDEX_CACHE_LIMIT:
            self._time_index_cache.clear()

        try:
            times = _to_bokeh_ms(df['Datetime'])
        except (TypeError, ValueError) as exc:
            logger.debug("Could not build time index: %s", exc)
            self._time_index_cache[cache_key] = (df, None)
            return None

        if times.size and not np.all(np.diff(times) >= 0):
            logger.debug("Datetime column is not sorted; using mask-based slicing")
            self._time_index_cache[cache_key] = (df, None)
            return None

        self._time_index_cache[cache_key] = (df, times)
        return times

    def _slice_by_time_with_index(self, df: pd.DataFrame, start_ms: float, end_ms: float):
        """
        Slice by time, also returning the slice's int64 ms timestamps when available.

        Callers that need those timestamps (to push to Bokeh) can reuse this instead of
        re-deriving them from the sliced frame, which is the single most expensive step
        in a streamed update.  The second element is None on the fallback path.
        """
        if df is None or df.empty or 'Datetime' not in df.columns:
            return df, None
        start, end = sorted([start_ms, end_ms])

        times_ms = self._time_index_ms(df)
        if times_ms is not None:
            # Search with integer bounds. The viewport arrives from Bokeh as floats, and
            # a float needle promotes the whole int64 index to float64 on every call -
            # 276us instead of 1.3us over a 4-day 1s survey.
            # Rounding preserves the inclusive bounds: the first time >= start is the
            # first >= ceil(start), and the last time <= end is the last <= floor(end).
            left = int(np.searchsorted(times_ms, math.ceil(start), side='left'))
            right = int(np.searchsorted(times_ms, math.floor(end), side='right'))
            return df.iloc[left:right], times_ms[left:right]

        times = pd.to_datetime(df['Datetime'])
        # Create timezone-aware timestamps to match the data
        start_ts = pd.to_datetime(start, unit='ms', utc=True)
        end_ts = pd.to_datetime(end, unit='ms', utc=True)
        mask = (times >= start_ts) & (times <= end_ts)
        return df.loc[mask], None

    def _slice_by_time(self, df: pd.DataFrame, start_ms: float, end_ms: float) -> pd.DataFrame:
        sliced, _ = self._slice_by_time_with_index(df, start_ms, end_ms)
        return sliced

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
