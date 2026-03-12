import unittest
import os
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
from bokeh.models import ColumnDataSource, Range1d

from noise_survey_analysis.core.app_callbacks import AppCallbacks
from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_parsers import ParsedData
from noise_survey_analysis.core.data_processors import GlyphDataProcessor
from noise_survey_analysis.core.data_manager import PositionData
from noise_survey_analysis.core.server_data_handler import ServerDataHandler
from noise_survey_analysis.visualization.dashBuilder import DashBuilder


class DummyDataManager:
    def __init__(self, positions):
        self._positions = positions
        self.parser_factory = MagicMock()
        self.use_cache = True

    def positions(self):
        return list(self._positions.keys())

    def __getitem__(self, position_id):
        return self._positions[position_id]


class DummyFigure:
    def __init__(self, width):
        self.width = width


class FakeDoc:
    def __init__(self, models):
        self._models = models
        self._timeout_callbacks = []

    def get_model_by_name(self, name):
        return self._models.get(name)

    def add_timeout_callback(self, callback, delay):
        self._timeout_callbacks.append(callback)
        return len(self._timeout_callbacks) - 1

    def flush_timeouts(self):
        callbacks = list(self._timeout_callbacks)
        self._timeout_callbacks.clear()
        for callback in callbacks:
            callback()


class FakeRange:
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self._callbacks = {}

    def on_change(self, attr, callback):
        self._callbacks.setdefault(attr, []).append(callback)

    def trigger(self, attr, old, new):
        for callback in self._callbacks.get(attr, []):
            callback(attr, old, new)


class StreamingBackendTests(unittest.TestCase):
    def setUp(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        times = [base_time + pd.Timedelta(seconds=idx * 60) for idx in range(3)]
        self.start_ms = int(times[0].value // 10**6)
        self.middle_ms = int(times[1].value // 10**6)
        self.end_ms = int(times[2].value // 10**6)

        self.position = PositionData(name="P1")
        self.position.log_totals = pd.DataFrame({
            "Datetime": times,
            "LAeq": [50, 52, 54],
        })
        self.position.log_spectral = pd.DataFrame({
            "Datetime": times,
            "LZeq_100": [60, 61, 62],
            "LZeq_200": [63, 64, 65],
        })

    def _write_temp_log_file(self, timestamps):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8", newline="") as handle:
            handle.write("Date & time,LAeq\n")
            for idx, timestamp in enumerate(timestamps):
                handle.write(f"{timestamp.isoformat()},{50 + idx}\n")
            return handle.name

    def test_prepare_single_spectrogram_data_rasterizes_overview_into_fixed_canvas(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        overview_df = pd.DataFrame({
            "Datetime": [
                base_time,
                base_time + pd.Timedelta(seconds=10),
                base_time + pd.Timedelta(seconds=20),
            ],
            "LZeq_100": [60, 61, 62],
            "LZeq_200": [70, 71, 72],
        })

        prepared = GlyphDataProcessor().prepare_single_spectrogram_data(
            overview_df,
            "LZeq",
            CHART_SETTINGS,
            use_dynamic_log_window=False,
            fixed_n_times=6,
        )

        self.assertIsNotNone(prepared)
        self.assertEqual(prepared["n_times"], 6)
        self.assertEqual(prepared["chunk_time_length"], 6)
        self.assertEqual(prepared["n_times_real"], 3)
        self.assertEqual(prepared["initial_glyph_data"]["image"][0].shape, (2, 6))
        self.assertAlmostEqual(
            prepared["initial_glyph_data"]["dw"][0],
            prepared["max_time"] - prepared["min_time"],
            places=6,
        )
        self.assertEqual(
            prepared["initial_glyph_data"]["image"][0][0].tolist(),
            [60, 60, 60, 61, 61, 62],
        )
        self.assertEqual(
            prepared["initial_glyph_data"]["image"][0][1].tolist(),
            [70, 70, 70, 71, 71, 72],
        )

    def test_prepare_all_spectral_data_keeps_overview_and_log_buffers_identical(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        overview_times = [base_time + pd.Timedelta(minutes=idx * 5) for idx in range(3)]
        log_times = [base_time + pd.Timedelta(milliseconds=idx * 100) for idx in range(100)]
        position = PositionData(name="P_contract")
        position.overview_spectral = pd.DataFrame({
            "Datetime": overview_times,
            "LZeq_100": [60, 61, 62],
            "LZeq_200": [70, 71, 72],
        })
        position.log_spectral = pd.DataFrame({
            "Datetime": log_times,
            "LZeq_100": [60 + (idx % 10) for idx in range(len(log_times))],
            "LZeq_200": [70 + (idx % 10) for idx in range(len(log_times))],
        })

        prepared = GlyphDataProcessor().prepare_all_spectral_data(position, CHART_SETTINGS)

        overview_prepared = prepared["overview"]["prepared_params"]["LZeq"]
        log_prepared = prepared["log"]["prepared_params"]["LZeq"]

        self.assertEqual(overview_prepared["chunk_time_length"], log_prepared["chunk_time_length"])
        self.assertEqual(
            overview_prepared["initial_glyph_data"]["image"][0].shape,
            log_prepared["initial_glyph_data"]["image"][0].shape,
        )
        self.assertEqual(overview_prepared["n_freqs"], log_prepared["n_freqs"])

    def test_prepare_all_spectral_data_uses_deferred_log_file_to_fix_overview_buffer(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        overview_times = [base_time + pd.Timedelta(minutes=idx * 5) for idx in range(3)]
        temp_path = self._write_temp_log_file([
            base_time,
            base_time + pd.Timedelta(milliseconds=100),
            base_time + pd.Timedelta(milliseconds=200),
            base_time + pd.Timedelta(milliseconds=300),
        ])
        try:
            position = PositionData(name="P_deferred_buffer")
            position.overview_spectral = pd.DataFrame({
                "Datetime": overview_times,
                "LZeq_100": [60, 61, 62],
                "LZeq_200": [70, 71, 72],
            })
            position.log_file_paths = [{
                "file_path": temp_path,
                "parser_type": "Svan",
                "return_all_cols": False,
            }]

            prepared = GlyphDataProcessor().prepare_all_spectral_data(position, CHART_SETTINGS)
            overview_prepared = prepared["overview"]["prepared_params"]["LZeq"]

            self.assertEqual(overview_prepared["chunk_time_length"], 9000)
            self.assertEqual(overview_prepared["initial_glyph_data"]["image"][0].shape, (2, 9000))
        finally:
            os.unlink(temp_path)

    def test_lazy_log_load_uses_cache_without_reparsing(self):
        cached_data = ParsedData(
            totals_df=self.position.log_totals.copy(),
            spectral_df=self.position.log_spectral.copy(),
            original_file_path="cached_log.csv",
            parser_type="Svan",
            data_profile="log",
            spectral_data_type="third_octave",
            sample_period_seconds=60.0,
        )
        cache = MagicMock()
        cache.get.return_value = cached_data
        parser_factory = MagicMock()
        self.position.log_totals = None
        self.position.log_spectral = None
        self.position.log_file_paths = [{
            "file_path": "cached_log.csv",
            "parser_type": "Svan",
            "return_all_cols": False,
        }]

        with patch("noise_survey_analysis.core.data_manager.get_parsed_data_cache", return_value=cache):
            self.position.load_log_data_lazy(parser_factory, use_cache=True)

        parser_factory.get_parser.assert_not_called()
        cache.get.assert_called_once_with("cached_log.csv", False)
        self.assertTrue(self.position._log_data_loaded)
        self.assertEqual(self.position.log_totals["LAeq"].tolist(), [50, 52, 54])
        self.assertEqual(self.position.log_spectral["LZeq_100"].tolist(), [60, 61, 62])

    def test_server_data_handler_updates_sources(self):
        timeseries_log_source = ColumnDataSource(data={})
        spectrogram_log_source = ColumnDataSource(data={})

        doc = FakeDoc({
            "source_P1_timeseries_log": timeseries_log_source,
            "source_P1_spectrogram_log": spectrogram_log_source,
            "figure_P1_timeseries": DummyFigure(width=320),
            "figure_P1_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P1": self.position}), CHART_SETTINGS)

        handler.handle_range_update(self.start_ms, self.end_ms)

        timeseries_data = timeseries_log_source.data
        self.assertEqual(timeseries_data["LAeq"], [50, 52, 54])
        self.assertEqual(
            [int(value) for value in timeseries_data["Datetime"]],
            [self.start_ms, self.middle_ms, self.end_ms],
        )

        # Now we push complete prepared data structure
        # All arrays are wrapped in single-element lists to satisfy Bokeh ColumnDataSource constraints
        spectrogram_data = spectrogram_log_source.data

        # Verify array fields (wrapped)
        self.assertIn("levels_flat_transposed", spectrogram_data)
        self.assertIn("times_ms", spectrogram_data)
        self.assertIn("frequency_labels", spectrogram_data)
        self.assertIn("frequencies_hz", spectrogram_data)

        # Verify metadata fields (scalars)
        self.assertIn("n_times", spectrogram_data)
        self.assertIn("n_freqs", spectrogram_data)
        self.assertIn("chunk_time_length", spectrogram_data)
        self.assertIn("time_step", spectrogram_data)
        self.assertIn("min_val", spectrogram_data)
        self.assertIn("max_val", spectrogram_data)
        self.assertIn("min_time", spectrogram_data)
        self.assertIn("max_time", spectrogram_data)

        # Verify initial_glyph_data fields
        self.assertIn("initial_glyph_data_x", spectrogram_data)
        self.assertIn("initial_glyph_data_y", spectrogram_data)
        self.assertIn("initial_glyph_data_dw", spectrogram_data)
        self.assertIn("initial_glyph_data_dh", spectrogram_data)
        self.assertIn("initial_glyph_data_image", spectrogram_data)

        # Verify wrapping (list of lists for arrays)
        self.assertEqual(len(spectrogram_data["frequency_labels"]), 1)
        self.assertEqual(len(spectrogram_data["frequency_labels"][0]), 2)  # 2 frequency bands inside wrapper

    def test_deferred_high_rate_log_viewport_is_rejected_before_lazy_load(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        temp_path = self._write_temp_log_file([
            base_time,
            base_time + pd.Timedelta(milliseconds=100),
            base_time + pd.Timedelta(milliseconds=200),
            base_time + pd.Timedelta(milliseconds=300),
        ])
        try:
            position = PositionData(name="P_deferred_high_rate")
            position.log_file_paths = [{
                "file_path": temp_path,
                "parser_type": "Svan",
                "return_all_cols": False,
            }]
            timeseries_log_source = ColumnDataSource(data={})
            spectrogram_log_source = ColumnDataSource(data={})
            data_manager = DummyDataManager({"P_deferred_high_rate": position})
            data_manager.parser_factory.get_parser.side_effect = AssertionError("lazy parse should not run")
            doc = FakeDoc({
                "source_P_deferred_high_rate_timeseries_log": timeseries_log_source,
                "source_P_deferred_high_rate_spectrogram_log": spectrogram_log_source,
                "figure_P_deferred_high_rate_timeseries": DummyFigure(width=320),
                "figure_P_deferred_high_rate_spectrogram": DummyFigure(width=320),
            })
            handler = ServerDataHandler(doc, data_manager, CHART_SETTINGS)

            start_ms = int(base_time.value // 10**6)
            handler.handle_range_update(start_ms, start_ms + (2 * 60 * 60 * 1000))

            self.assertEqual(timeseries_log_source.data, {})
            self.assertEqual(spectrogram_log_source.data, {})
            self.assertFalse(position._log_data_loaded)
        finally:
            os.unlink(temp_path)

    def test_deferred_log_file_cadence_overrides_coarse_metadata_for_viewport_gate(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        temp_path = self._write_temp_log_file([
            base_time,
            base_time + pd.Timedelta(milliseconds=100),
            base_time + pd.Timedelta(milliseconds=200),
            base_time + pd.Timedelta(milliseconds=300),
        ])
        try:
            position = PositionData(name="P_deferred_mixed_rate")
            position.sample_periods_seconds = {300.0}
            position.log_file_paths = [{
                "file_path": temp_path,
                "parser_type": "Svan",
                "return_all_cols": False,
            }]
            handler = ServerDataHandler(FakeDoc({}), DummyDataManager({"P_deferred_mixed_rate": position}), CHART_SETTINGS)

            self.assertEqual(handler._position_max_viewport_seconds(position), 3600)
        finally:
            os.unlink(temp_path)

    def test_app_callbacks_debounces_range_updates(self):
        master_x_range = FakeRange(start=0, end=0)
        doc = FakeDoc({"master_x_range": master_x_range})
        server_data_handler = MagicMock()

        callbacks = AppCallbacks(
            doc=doc,
            audio_handler=None,
            audio_control_source=ColumnDataSource(data={"command": [None]}),
            audio_status_source=ColumnDataSource(data={}),
            server_data_handler=server_data_handler,
            streaming_enabled=True,
            streaming_debounce_ms=200,
        )
        callbacks.attach_non_audio_callbacks()
        server_data_handler.handle_range_update.reset_mock()

        master_x_range.start = 100
        master_x_range.end = 200
        master_x_range.trigger("start", 0, 100)
        master_x_range.start = 150
        master_x_range.end = 250
        master_x_range.trigger("end", 200, 250)

        doc.flush_timeouts()

        server_data_handler.handle_range_update.assert_called_once_with(150, 250)

    def test_dash_builder_server_mode_uses_explicit_master_range1d(self):
        builder = DashBuilder()
        builder.server_mode = True

        initial_ts_range = Range1d(start=10, end=20)
        ts_figure = MagicMock()
        ts_figure.x_range = initial_ts_range
        spec_figure = MagicMock()
        spec_figure.x_range = Range1d(start=30, end=40)

        ts_component = MagicMock()
        ts_component.figure = ts_figure
        ts_component.overview_source = ColumnDataSource(data={
            "Datetime": [1000, 2000],
            "LAeq": [50, 52],
        })
        ts_component.log_source = ColumnDataSource(data={
            "Datetime": [1500, 2500],
            "LAeq": [51, 53],
        })

        spec_component = MagicMock()
        spec_component.figure = spec_figure

        range_selector = MagicMock()
        range_selector.range_tool = MagicMock()

        builder.components = {
            "P1": {
                "timeseries": ts_component,
                "spectrogram": spec_component,
            }
        }
        builder.shared_components = {
            "controls": MagicMock(),
            "freq_bar": MagicMock(),
            "range_selector": range_selector,
        }

        builder._wire_up_interactions()

        self.assertIsInstance(ts_component.figure.x_range, Range1d)
        self.assertIs(ts_component.figure.x_range, spec_component.figure.x_range)
        self.assertIs(range_selector.range_tool.x_range, ts_component.figure.x_range)
        self.assertEqual(ts_component.figure.x_range.name, "master_x_range")
        self.assertEqual(ts_component.figure.x_range.start, 1000)
        self.assertEqual(ts_component.figure.x_range.end, 2500)
        self.assertIsNot(ts_component.figure.x_range, initial_ts_range)

    def test_server_data_handler_allows_wider_low_sample_rate_viewport(self):
        timeseries_log_source = ColumnDataSource(data={})
        spectrogram_log_source = ColumnDataSource(data={})

        doc = FakeDoc({
            "source_P1_timeseries_log": timeseries_log_source,
            "source_P1_spectrogram_log": spectrogram_log_source,
            "figure_P1_timeseries": DummyFigure(width=320),
            "figure_P1_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P1": self.position}), CHART_SETTINGS)

        # 20-minute viewport, which exceeds the old fixed 300s limit.
        wide_end_ms = self.start_ms + (20 * 60 * 1000)
        handler.handle_range_update(self.start_ms, wide_end_ms)

        self.assertIn("Datetime", timeseries_log_source.data)
        self.assertEqual(timeseries_log_source.data["LAeq"], [50, 52, 54])

    def test_server_data_handler_skips_wide_high_sample_rate_viewport(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        high_rate_times = [base_time + pd.Timedelta(seconds=idx) for idx in range(20)]
        high_rate_position = PositionData(name="P2")
        high_rate_position.log_totals = pd.DataFrame({
            "Datetime": high_rate_times,
            "LAeq": [40 + idx for idx in range(20)],
        })
        high_rate_position.log_spectral = pd.DataFrame({
            "Datetime": high_rate_times,
            "LZeq_100": [60 + idx for idx in range(20)],
            "LZeq_200": [63 + idx for idx in range(20)],
        })
        # Set sample period to 1 second (high rate)
        high_rate_position.sample_periods_seconds = {1.0}

        timeseries_log_source = ColumnDataSource(data={})
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P2_timeseries_log": timeseries_log_source,
            "source_P2_spectrogram_log": spectrogram_log_source,
            "figure_P2_timeseries": DummyFigure(width=320),
            "figure_P2_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P2": high_rate_position}), CHART_SETTINGS)

        # 20-minute viewport should be skipped for 1-second log data at default target points.
        # With 36000 target rows at 1s period, max viewport = 36000s = 10 hours
        # But high-rate max is 3600s (1 hour), so 20 min (1200s) should be allowed
        # We need a viewport larger than the high-rate max to trigger the skip
        start_ms = int(high_rate_times[0].value // 10**6)
        wide_end_ms = start_ms + (2 * 60 * 60 * 1000)  # 2 hours - exceeds 1 hour high-rate max
        handler.handle_range_update(start_ms, wide_end_ms)

        self.assertEqual(timeseries_log_source.data, {})
        self.assertEqual(spectrogram_log_source.data, {})

    def test_step_size_aware_viewport_cap_100ms_data(self):
        """Test that 100ms data gets a 60-minute max viewport."""
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        times_100ms = [base_time + pd.Timedelta(milliseconds=idx * 100) for idx in range(100)]
        position_100ms = PositionData(name="P_100ms")
        position_100ms.log_totals = pd.DataFrame({
            "Datetime": times_100ms,
            "LAeq": [50 + idx * 0.1 for idx in range(100)],
        })
        position_100ms.sample_periods_seconds = {0.1}  # 100ms sample period

        timeseries_log_source = ColumnDataSource(data={})
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_100ms_timeseries_log": timeseries_log_source,
            "source_P_100ms_spectrogram_log": spectrogram_log_source,
            "figure_P_100ms_timeseries": DummyFigure(width=320),
            "figure_P_100ms_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_100ms": position_100ms}), CHART_SETTINGS)

        # 60-minute viewport should be allowed for 100ms data
        # With 36000 target rows at 0.1s period = 3600s = 60 min
        start_ms = int(times_100ms[0].value // 10**6)
        viewport_end_ms = start_ms + (60 * 60 * 1000)  # 60 minutes
        handler.handle_range_update(start_ms, viewport_end_ms)

        # Should have data (viewport within limit)
        self.assertIn("Datetime", timeseries_log_source.data)

    def test_step_size_aware_viewport_cap_rejects_oversized_100ms(self):
        """Test that 100ms data rejects viewports larger than 1 hour."""
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        times_100ms = [base_time + pd.Timedelta(milliseconds=idx * 100) for idx in range(100)]
        position_100ms = PositionData(name="P_100ms_oversized")
        position_100ms.log_totals = pd.DataFrame({
            "Datetime": times_100ms,
            "LAeq": [50 + idx * 0.1 for idx in range(100)],
        })
        position_100ms.sample_periods_seconds = {0.1}  # 100ms sample period

        timeseries_log_source = ColumnDataSource(data={})
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_100ms_oversized_timeseries_log": timeseries_log_source,
            "source_P_100ms_oversized_spectrogram_log": spectrogram_log_source,
            "figure_P_100ms_oversized_timeseries": DummyFigure(width=320),
            "figure_P_100ms_oversized_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_100ms_oversized": position_100ms}), CHART_SETTINGS)

        # 2-hour viewport should be rejected for 100ms data
        # High-rate max is 3600s (1 hour)
        start_ms = int(times_100ms[0].value // 10**6)
        oversized_end_ms = start_ms + (2 * 60 * 60 * 1000)  # 2 hours
        handler.handle_range_update(start_ms, oversized_end_ms)

        # Should NOT have data (viewport exceeds limit)
        self.assertEqual(timeseries_log_source.data, {})

    def test_adaptive_buffer_high_rate_uses_smaller_fraction(self):
        """Test that high-rate data uses smaller buffer fraction."""
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        times_100ms = [base_time + pd.Timedelta(milliseconds=idx * 100) for idx in range(100)]
        position_100ms = PositionData(name="P_buffer_test")
        position_100ms.log_totals = pd.DataFrame({
            "Datetime": times_100ms,
            "LAeq": [50 + idx * 0.1 for idx in range(100)],
        })
        position_100ms.sample_periods_seconds = {0.1}  # 100ms = high rate

        timeseries_log_source = ColumnDataSource(data={})
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_buffer_test_timeseries_log": timeseries_log_source,
            "source_P_buffer_test_spectrogram_log": spectrogram_log_source,
            "figure_P_buffer_test_timeseries": DummyFigure(width=320),
            "figure_P_buffer_test_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_buffer_test": position_100ms}), CHART_SETTINGS)

        # Request a 10-minute viewport
        start_ms = int(times_100ms[0].value // 10**6)
        viewport_end_ms = start_ms + (10 * 60 * 1000)  # 10 minutes

        # Calculate buffer and verify it uses 10% fraction for high-rate
        buffer_start, buffer_end = handler._calculate_buffer(start_ms, viewport_end_ms, position_100ms)
        viewport_width = viewport_end_ms - start_ms
        expected_buffer = viewport_width * 0.1  # 10% for high-rate

        self.assertAlmostEqual(buffer_end - viewport_end_ms, expected_buffer, places=0)
        self.assertAlmostEqual(start_ms - buffer_start, expected_buffer, places=0)

    def test_high_rate_buffer_bounds_cover_current_viewport_for_reuse(self):
        position = PositionData(name="P_buffer_reuse")
        position.sample_periods_seconds = {0.1}
        handler = ServerDataHandler(FakeDoc({}), DummyDataManager({"P_buffer_reuse": position}), CHART_SETTINGS)

        start_ms = 0
        end_ms = 10 * 60 * 1000
        handler._buffer_bounds["P_buffer_reuse"] = handler._calculate_buffer(start_ms, end_ms, position)

        self.assertTrue(handler._buffer_covers_viewport("P_buffer_reuse", start_ms, end_ms))

    def test_handle_range_update_refreshes_reservoir_within_existing_buffer(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        position = PositionData(name="P_reservoir_refresh")
        position.sample_periods_seconds = {0.1}
        position.log_spectral = pd.DataFrame({
            "Datetime": [base_time],
            "LZeq_100": [60],
            "LZeq_200": [65],
        })
        handler = ServerDataHandler(FakeDoc({}), DummyDataManager({"P_reservoir_refresh": position}), CHART_SETTINGS)

        viewport_start_ms = 30 * 60 * 1000
        viewport_end_ms = 42 * 60 * 1000
        buffer_start_ms = 24 * 60 * 1000
        buffer_end_ms = 96 * 60 * 1000
        handler._buffer_bounds["P_reservoir_refresh"] = (buffer_start_ms, buffer_end_ms)
        handler._spectrogram_chunk_bounds["P_reservoir_refresh"] = (24 * 60 * 1000, 36 * 60 * 1000)
        handler._update_position = MagicMock()

        handler.handle_range_update(viewport_start_ms, viewport_end_ms)

        handler._update_position.assert_called_once_with(
            "P_reservoir_refresh",
            buffer_start_ms,
            buffer_end_ms,
            viewport_start_ms=viewport_start_ms,
            viewport_end_ms=viewport_end_ms,
            sample_period_seconds=0.1,
            refresh_totals=False,
        )

    def test_handle_range_update_refreshes_reservoir_when_coverage_low_even_for_wide_viewport(self):
        """With reservoir mode, the viewport-exceeds-chunk-window gate is removed.

        Instead, the reservoir coverage ratio determines whether a refresh is needed.
        A wide viewport that has low reservoir coverage should trigger a refresh.
        """
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        position = PositionData(name="P_reservoir_gate")
        position.sample_periods_seconds = {0.1}
        position.log_spectral = pd.DataFrame({
            "Datetime": [base_time],
            "LZeq_100": [60],
            "LZeq_200": [65],
        })
        handler = ServerDataHandler(FakeDoc({}), DummyDataManager({"P_reservoir_gate": position}), CHART_SETTINGS)

        viewport_start_ms = 0
        viewport_end_ms = 40 * 60 * 1000
        buffer_start_ms = -4 * 60 * 1000
        buffer_end_ms = 44 * 60 * 1000
        handler._buffer_bounds["P_reservoir_gate"] = (buffer_start_ms, buffer_end_ms)
        # Reservoir covers only 10-25 min out of 0-40 min viewport → ~37.5% coverage → refresh
        handler._spectrogram_chunk_bounds["P_reservoir_gate"] = (10 * 60 * 1000, 25 * 60 * 1000)
        handler._update_position = MagicMock()

        handler.handle_range_update(viewport_start_ms, viewport_end_ms)

        # Should trigger a reservoir refresh (coverage < 80%)
        handler._update_position.assert_called_once()

    def test_update_log_spectrogram_streams_reservoir_for_wide_viewport(self):
        """With reservoir mode, wide viewports are no longer skipped by _update_log_spectrogram.

        The old chunk-window gate that blocked streaming when viewport exceeded
        the fixed chunk window has been removed. The reservoir covers the full
        prepared data and the browser extracts the display chunk client-side.
        """
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        times = pd.date_range(base_time, periods=20000, freq="100ms")
        position = PositionData(name="P_spec_reservoir_wide")
        position.sample_periods_seconds = {0.1}
        position.log_spectral = pd.DataFrame({
            "Datetime": times,
            "LZeq_100": [60 + (idx % 5) for idx in range(len(times))],
            "LZeq_200": [65 + (idx % 5) for idx in range(len(times))],
        })
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_spec_reservoir_wide_spectrogram_log": spectrogram_log_source,
            "figure_P_spec_reservoir_wide_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_spec_reservoir_wide": position}), CHART_SETTINGS)

        slice_start_ms = int(times[0].value // 10**6)
        slice_end_ms = int((base_time + pd.Timedelta(minutes=33)).value // 10**6)
        viewport_start_ms = int((base_time + pd.Timedelta(minutes=4)).value // 10**6)
        viewport_end_ms = int((base_time + pd.Timedelta(minutes=33)).value // 10**6)

        handler._update_log_spectrogram(
            position.log_spectral,
            handler.position_models["P_spec_reservoir_wide"],
            slice_start_ms,
            slice_end_ms,
            viewport_start_ms=viewport_start_ms,
            viewport_end_ms=viewport_end_ms,
            position_id="P_spec_reservoir_wide",
            position_data=position,
            sample_period_seconds=0.1,
        )

        # Reservoir streaming should succeed
        self.assertNotEqual(spectrogram_log_source.data, {})
        self.assertTrue(spectrogram_log_source.data["is_reservoir_payload"][0])
        self.assertIn("P_spec_reservoir_wide", handler._spectrogram_chunk_bounds)

    def test_streamed_reservoir_payload_reports_consistent_lengths(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        times = pd.date_range(base_time, periods=10000, freq="100ms")
        position = PositionData(name="P_long_reservoir")
        position.log_spectral = pd.DataFrame({
            "Datetime": times,
            "LZeq_100": [60 + (idx % 5) for idx in range(len(times))],
            "LZeq_200": [65 + (idx % 5) for idx in range(len(times))],
        })
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_long_reservoir_spectrogram_log": spectrogram_log_source,
            "figure_P_long_reservoir_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_long_reservoir": position}), CHART_SETTINGS)

        start_ms = int(times[0].value // 10**6)
        end_ms = int(times[-1].value // 10**6)
        handler._update_log_spectrogram(position.log_spectral, handler.position_models["P_long_reservoir"], start_ms, end_ms)

        payload = spectrogram_log_source.data
        times_len = len(payload["times_ms"][0])
        levels_len = len(payload["levels_flat_transposed"][0])
        n_times = payload["n_times"][0]
        n_freqs = payload["n_freqs"][0]

        # Reservoir payload: n_times matches the full reservoir, not just one chunk
        self.assertEqual(times_len, n_times)
        self.assertEqual(levels_len, n_freqs * n_times)
        # Reservoir is flagged
        self.assertTrue(payload["is_reservoir_payload"][0])

    def test_streamed_reservoir_payload_covers_full_slice(self):
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        periods = 72 * 60 * 10
        times = pd.date_range(base_time, periods=periods, freq="100ms")
        position = PositionData(name="P_reservoir_full")
        position.sample_periods_seconds = {0.1}
        position.log_spectral = pd.DataFrame({
            "Datetime": times,
            "LZeq_100": [60 + (idx % 5) for idx in range(len(times))],
            "LZeq_200": [65 + (idx % 5) for idx in range(len(times))],
        })
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_reservoir_full_spectrogram_log": spectrogram_log_source,
            "figure_P_reservoir_full_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_reservoir_full": position}), CHART_SETTINGS)

        slice_start_ms = int(times[0].value // 10**6)
        slice_end_ms = int(times[-1].value // 10**6)
        viewport_start_ms = int((base_time + pd.Timedelta(minutes=60)).value // 10**6)
        viewport_end_ms = int((base_time + pd.Timedelta(minutes=72)).value // 10**6)

        handler._update_log_spectrogram(
            position.log_spectral,
            handler.position_models["P_reservoir_full"],
            slice_start_ms,
            slice_end_ms,
            viewport_start_ms=viewport_start_ms,
            viewport_end_ms=viewport_end_ms,
            position_id="P_reservoir_full",
        )

        payload = spectrogram_log_source.data
        reservoir_times = payload["times_ms"][0]
        reservoir_levels = payload["levels_flat_transposed"][0]
        n_times = payload["n_times"][0]
        n_freqs = payload["n_freqs"][0]

        # Reservoir covers the full buffered slice, not just a viewport chunk
        self.assertEqual(len(reservoir_times), n_times)
        self.assertEqual(len(reservoir_levels), n_freqs * n_times)
        # Reservoir starts at the beginning of the prepared data
        self.assertEqual(payload["min_time"][0], float(reservoir_times[0]))
        self.assertEqual(payload["max_time"][0], float(reservoir_times[-1]))
        self.assertEqual(payload["parameter"][0], "LZeq")
        # Reservoir bounds tracked
        self.assertEqual(
            handler._spectrogram_chunk_bounds["P_reservoir_full"],
            (float(reservoir_times[0]), float(reservoir_times[-1]))
        )
        self.assertTrue(payload["is_reservoir_payload"][0])
        # The initial glyph metadata describes the fixed display chunk, not the
        # full reservoir backing span.
        reservoir_span_ms = float(reservoir_times[-1]) - float(reservoir_times[0])
        self.assertLess(payload["initial_glyph_data_dw"][0][0], reservoir_span_ms)

    def test_wide_buffer_reservoir_covers_viewport(self):
        """
        Contract test: The streamed reservoir must cover the viewport.
        With reservoir mode, the full prepared data is sent — not just one chunk.
        """
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        periods = 120 * 30
        times = pd.date_range(base_time, periods=periods, freq="2s")
        position = PositionData(name="P_wide_buffer")
        position.sample_periods_seconds = {2.0}
        position.log_spectral = pd.DataFrame({
            "Datetime": times,
            "LZeq_100": [60 + (idx % 5) for idx in range(len(times))],
            "LZeq_200": [65 + (idx % 5) for idx in range(len(times))],
        })
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_wide_buffer_spectrogram_log": spectrogram_log_source,
            "figure_P_wide_buffer_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_wide_buffer": position}), CHART_SETTINGS)

        viewport_start_ms = int((base_time + pd.Timedelta(minutes=30)).value // 10**6)
        viewport_end_ms = int((base_time + pd.Timedelta(minutes=90)).value // 10**6)

        buffer_start, buffer_end = handler._calculate_buffer(viewport_start_ms, viewport_end_ms, position)
        handler._update_position(
            "P_wide_buffer",
            buffer_start,
            buffer_end,
            viewport_start_ms=viewport_start_ms,
            viewport_end_ms=viewport_end_ms,
            sample_period_seconds=2.0,
        )

        payload = spectrogram_log_source.data
        times_array = payload["times_ms"][0]
        n_times = payload["n_times"][0]
        n_freqs = payload["n_freqs"][0]

        # Reservoir should have data
        self.assertGreater(len(times_array), 0, "Reservoir should contain time points")
        # Reservoir n_times matches actual times array length
        self.assertEqual(len(times_array), n_times)
        # Reservoir levels are consistent
        self.assertEqual(len(payload["levels_flat_transposed"][0]), n_freqs * n_times)
        self.assertTrue(payload["is_reservoir_payload"][0])
        # Reservoir bounds should be tracked
        bounds = handler._spectrogram_chunk_bounds.get("P_wide_buffer")
        self.assertIsNotNone(bounds, "Reservoir bounds should be tracked")
        self.assertEqual(bounds[0], float(times_array[0]))
        self.assertEqual(bounds[1], float(times_array[-1]))


    def test_reservoir_payload_uses_numpy_arrays_not_lists(self):
        """Assert reservoir payload preserves NumPy arrays instead of .tolist()."""
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        times = pd.date_range(base_time, periods=500, freq="100ms")
        position = PositionData(name="P_numpy_check")
        position.log_spectral = pd.DataFrame({
            "Datetime": times,
            "LZeq_100": [60 + (idx % 5) for idx in range(len(times))],
            "LZeq_200": [65 + (idx % 5) for idx in range(len(times))],
        })
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_numpy_check_spectrogram_log": spectrogram_log_source,
            "figure_P_numpy_check_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_numpy_check": position}), CHART_SETTINGS)

        start_ms = int(times[0].value // 10**6)
        end_ms = int(times[-1].value // 10**6)
        handler._update_log_spectrogram(
            position.log_spectral,
            handler.position_models["P_numpy_check"],
            start_ms, end_ms,
            position_id="P_numpy_check",
        )

        payload = spectrogram_log_source.data
        levels = payload["levels_flat_transposed"][0]
        times_data = payload["times_ms"][0]

        self.assertIsInstance(levels, np.ndarray, "levels_flat_transposed should be NumPy array")
        self.assertIsInstance(times_data, np.ndarray, "times_ms should be NumPy array")
        self.assertEqual(levels.dtype, np.float32, "levels should be float32")
        self.assertEqual(times_data.dtype, np.float64, "times should be float64")

    def test_reservoir_column_data_source_outer_lengths_valid(self):
        """Assert all ColumnDataSource columns have length 1 (Bokeh single-row format)."""
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        times = pd.date_range(base_time, periods=200, freq="100ms")
        position = PositionData(name="P_cds_check")
        position.log_spectral = pd.DataFrame({
            "Datetime": times,
            "LZeq_100": [60 + (idx % 5) for idx in range(len(times))],
            "LZeq_200": [65 + (idx % 5) for idx in range(len(times))],
        })
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_cds_check_spectrogram_log": spectrogram_log_source,
            "figure_P_cds_check_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_cds_check": position}), CHART_SETTINGS)

        start_ms = int(times[0].value // 10**6)
        end_ms = int(times[-1].value // 10**6)
        handler._update_log_spectrogram(
            position.log_spectral,
            handler.position_models["P_cds_check"],
            start_ms, end_ms,
            position_id="P_cds_check",
        )

        payload = spectrogram_log_source.data
        for key, val in payload.items():
            self.assertEqual(len(val), 1, f"Column '{key}' should have outer length 1, got {len(val)}")

    def test_reservoir_streaming_not_blocked_by_old_chunk_window_gate(self):
        """Assert spectrogram streaming is allowed even when viewport exceeds old chunk window.

        The old gating logic blocked streaming when viewport_width > spectrogram_max_viewport_seconds.
        With reservoir mode, the viewport no longer has to fit inside one fixed chunk window.
        """
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        times = pd.date_range(base_time, periods=20000, freq="100ms")
        position = PositionData(name="P_gate_check")
        position.sample_periods_seconds = {0.1}
        position.log_spectral = pd.DataFrame({
            "Datetime": times,
            "LZeq_100": [60 + (idx % 5) for idx in range(len(times))],
            "LZeq_200": [65 + (idx % 5) for idx in range(len(times))],
        })
        spectrogram_log_source = ColumnDataSource(data={})
        doc = FakeDoc({
            "source_P_gate_check_spectrogram_log": spectrogram_log_source,
            "figure_P_gate_check_spectrogram": DummyFigure(width=320),
        })
        handler = ServerDataHandler(doc, DummyDataManager({"P_gate_check": position}), CHART_SETTINGS)

        slice_start_ms = int(times[0].value // 10**6)
        slice_end_ms = int((base_time + pd.Timedelta(minutes=33)).value // 10**6)
        # Viewport wider than old 15-minute chunk window but narrower than max viewport
        viewport_start_ms = int((base_time + pd.Timedelta(minutes=4)).value // 10**6)
        viewport_end_ms = int((base_time + pd.Timedelta(minutes=24)).value // 10**6)

        handler._update_log_spectrogram(
            position.log_spectral,
            handler.position_models["P_gate_check"],
            slice_start_ms,
            slice_end_ms,
            viewport_start_ms=viewport_start_ms,
            viewport_end_ms=viewport_end_ms,
            position_id="P_gate_check",
            position_data=position,
            sample_period_seconds=0.1,
        )

        # With reservoir mode, this should NOT be skipped
        self.assertNotEqual(spectrogram_log_source.data, {},
            "Reservoir streaming should not be blocked by old chunk window gate")
        self.assertTrue(spectrogram_log_source.data["is_reservoir_payload"][0])

    def test_reservoir_refresh_on_coverage_drop(self):
        """Assert reservoir is refreshed when coverage drops below 98%."""
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        position = PositionData(name="P_refresh")
        position.sample_periods_seconds = {0.1}
        position.log_spectral = pd.DataFrame({
            "Datetime": [base_time],
            "LZeq_100": [60],
            "LZeq_200": [65],
        })
        handler = ServerDataHandler(FakeDoc({}), DummyDataManager({"P_refresh": position}), CHART_SETTINGS)

        # Set up existing buffer and reservoir bounds
        viewport_start_ms = 30 * 60 * 1000
        viewport_end_ms = 42 * 60 * 1000
        buffer_start_ms = 24 * 60 * 1000
        buffer_end_ms = 96 * 60 * 1000
        handler._buffer_bounds["P_refresh"] = (buffer_start_ms, buffer_end_ms)
        # Old reservoir covers 24-36 min, new viewport 30-42 min (~50% coverage)
        handler._spectrogram_chunk_bounds["P_refresh"] = (24 * 60 * 1000, 36 * 60 * 1000)
        handler._update_position = MagicMock()

        handler.handle_range_update(viewport_start_ms, viewport_end_ms)

        handler._update_position.assert_called_once_with(
            "P_refresh",
            buffer_start_ms,
            buffer_end_ms,
            viewport_start_ms=viewport_start_ms,
            viewport_end_ms=viewport_end_ms,
            sample_period_seconds=0.1,
            refresh_totals=False,
        )

    def test_reservoir_not_refreshed_when_coverage_meets_threshold(self):
        """Assert reservoir is reused when viewport coverage remains above 98%."""
        base_time = pd.Timestamp("2024-01-01T00:00:00Z")
        position = PositionData(name="P_refresh_ok")
        position.sample_periods_seconds = {0.1}
        position.log_spectral = pd.DataFrame({
            "Datetime": [base_time],
            "LZeq_100": [60],
            "LZeq_200": [65],
        })
        handler = ServerDataHandler(FakeDoc({}), DummyDataManager({"P_refresh_ok": position}), CHART_SETTINGS)

        viewport_start_ms = 30 * 60 * 1000
        viewport_end_ms = 42 * 60 * 1000
        buffer_start_ms = 24 * 60 * 1000
        buffer_end_ms = 96 * 60 * 1000
        handler._buffer_bounds["P_refresh_ok"] = (buffer_start_ms, buffer_end_ms)
        # Coverage = 11.95 / 12.0 = 0.9958..., which should reuse the reservoir.
        handler._spectrogram_chunk_bounds["P_refresh_ok"] = (
            (30 * 60 * 1000) - 60 * 1000,
            (42 * 60 * 1000) - 3 * 1000,
        )
        handler._update_position = MagicMock()

        handler.handle_range_update(viewport_start_ms, viewport_end_ms)

        handler._update_position.assert_not_called()


if __name__ == "__main__":
    unittest.main()
