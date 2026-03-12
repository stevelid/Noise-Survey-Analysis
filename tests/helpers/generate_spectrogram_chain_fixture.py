import json
import logging
import pathlib
import sys
from typing import Any

import numpy as np
import pandas as pd
from bokeh.models import ColumnDataSource

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_manager import PositionData
from noise_survey_analysis.core.server_data_handler import ServerDataHandler


logging.disable(logging.CRITICAL)


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

    def get_model_by_name(self, name):
        return self._models.get(name)


def _jsonify(value: Any):
    if isinstance(value, dict):
        return {key: _jsonify(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonify(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, pd.Timestamp):
        return int(value.value // 10**6)
    return value


def _build_case_specs(payload):
    times = payload["times_ms"][0]
    time_step_ms = float(payload["time_step"][0])
    chunk_ms = float(payload["initial_glyph_data_dw"][0][0])
    reservoir_start = float(times[0])
    reservoir_end = float(times[-1])
    initial_chunk_start = float(payload["initial_glyph_data_x"][0][0])
    initial_chunk_end = initial_chunk_start + chunk_ms

    margin = max(int(time_step_ms * 10), int(chunk_ms * 0.05))
    short_span = int(chunk_ms * 0.75)

    return {
        "inside_initial_chunk": {
            "min": int(initial_chunk_start + margin),
            "max": int(initial_chunk_start + margin + short_span),
            "expectedType": "log",
            "expectedStatus": "log_displayed",
        },
        "inside_reservoir_beyond_initial_chunk": {
            "min": int(initial_chunk_end + margin),
            "max": int(initial_chunk_end + margin + short_span),
            "expectedType": "log",
            "expectedStatus": "log_displayed",
        },
        "near_far_edge_inside_reservoir": {
            "min": int((reservoir_end - time_step_ms) - short_span),
            "max": int(reservoir_end - time_step_ms),
            "expectedType": "log",
            "expectedStatus": "log_displayed",
        },
        "partial_overlap_right": {
            "min": int(reservoir_end - (short_span * 0.25)),
            "max": int((reservoir_end - (short_span * 0.25)) + short_span),
            "expectedType": "overview",
            "expectedStatus": "loading_log",
        },
        "partial_overlap_left": {
            "min": int((reservoir_start + (short_span * 0.25)) - short_span),
            "max": int(reservoir_start + (short_span * 0.25)),
            "expectedType": "overview",
            "expectedStatus": "loading_log",
        },
        "oversized_viewport": {
            "min": int(initial_chunk_start + margin),
            "max": int(initial_chunk_start + margin + chunk_ms + 60000),
            "expectedType": "overview",
            "expectedStatus": "zoom_required",
        },
    }


def main():
    base_time = pd.Timestamp("2024-01-01T00:00:00Z")
    log_times = pd.date_range(base_time + pd.Timedelta(minutes=30), periods=18000, freq="100ms")

    position = PositionData(name="P_chain_fixture")
    position.sample_periods_seconds = {0.1}
    position.log_spectral = pd.DataFrame({
        "Datetime": log_times,
        "LZeq_100": 60 + (np.arange(len(log_times)) % 12),
        "LZeq_200": 65 + (np.arange(len(log_times)) % 9),
    })

    spectrogram_log_source = ColumnDataSource(data={})
    doc = FakeDoc({
        "source_P_chain_fixture_spectrogram_log": spectrogram_log_source,
        "figure_P_chain_fixture_spectrogram": DummyFigure(width=320),
    })
    handler = ServerDataHandler(doc, DummyDataManager({"P_chain_fixture": position}), CHART_SETTINGS)

    viewport_start_ms = int((base_time + pd.Timedelta(minutes=70)).value // 10**6)
    viewport_end_ms = int((base_time + pd.Timedelta(minutes=82)).value // 10**6)
    slice_start_ms = int(log_times[0].value // 10**6)
    slice_end_ms = int(log_times[-1].value // 10**6)

    handler._update_log_spectrogram(
        position.log_spectral,
        handler.position_models["P_chain_fixture"],
        slice_start_ms,
        slice_end_ms,
        viewport_start_ms=viewport_start_ms,
        viewport_end_ms=viewport_end_ms,
        position_id="P_chain_fixture",
    )

    payload = spectrogram_log_source.data
    reservoir_bounds = handler._spectrogram_chunk_bounds["P_chain_fixture"]

    fixture = {
        "position": "P_chain_fixture",
        "parameter": "LZeq",
        "config": {
            "spectrogram_freq_range_hz": [100, 200],
            "log_view_max_viewport_seconds": 3600,
        },
        "logPayload": payload,
        "reservoirBounds": reservoir_bounds,
        "cases": _build_case_specs(payload),
    }

    print(json.dumps(_jsonify(fixture)))


if __name__ == "__main__":
    main()
