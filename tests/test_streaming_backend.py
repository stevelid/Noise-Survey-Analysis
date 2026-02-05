import unittest
from unittest.mock import MagicMock

import pandas as pd
from bokeh.models import ColumnDataSource

from noise_survey_analysis.core.app_callbacks import AppCallbacks
from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_manager import PositionData
from noise_survey_analysis.core.server_data_handler import ServerDataHandler


class DummyDataManager:
    def __init__(self, positions):
        self._positions = positions

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

        # Now we push raw flat data instead of pre-computed image
        # All arrays are wrapped in single-element lists to satisfy Bokeh ColumnDataSource constraints
        spectrogram_data = spectrogram_log_source.data
        self.assertIn("levels_flat_transposed", spectrogram_data)
        self.assertIn("times_ms", spectrogram_data)
        self.assertIn("frequency_labels", spectrogram_data)
        self.assertIn("frequencies_hz", spectrogram_data)
        
        # Verify wrapping (list of lists)
        self.assertEqual(len(spectrogram_data["frequency_labels"]), 1)
        self.assertEqual(len(spectrogram_data["frequency_labels"][0]), 2)  # 2 frequency bands inside wrapper

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


if __name__ == "__main__":
    unittest.main()
