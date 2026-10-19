"""Real document checks for retirement of the widget-based annotation panels."""
import json

import pandas as pd
from bokeh.document import Document
from bokeh.models import DataTable, Tabs

from noise_survey_analysis.core.app_setup import load_config_extras
from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_manager import DataManager, PositionData
from noise_survey_analysis.visualization.dashBuilder import DashBuilder


def test_dashboard_document_contains_html_annotations_without_legacy_widgets():
    times = pd.date_range("2026-10-01", periods=3, freq="5min", tz="UTC")
    position = PositionData(name="P1")
    position.overview_totals = pd.DataFrame({
        "Datetime": times, "LAeq": [45.0, 46.0, 47.0],
        "LAFmax": [55.0, 56.0, 57.0], "LAF90": [38.0, 39.0, 40.0],
    })
    position.overview_spectral = pd.DataFrame({"Datetime": times, "LZeq_63": [32.0, 33.0, 34.0]})
    manager = DataManager(use_cache=False)
    manager._positions_data = {"P1": position}
    manager._position_order = ["P1"]
    document = Document()

    DashBuilder().build_layout(document, manager, CHART_SETTINGS, server_mode=False)

    # This includes models referenced by CustomJS arguments, not just roots.
    # Such hidden references previously caused missing DataTable resources.
    assert document.get_model_by_name("html_side_panel") is not None
    assert list(document.select({"type": DataTable})) == []
    assert list(document.select({"type": Tabs})) == []


def test_retired_panel_flag_is_ignored_without_losing_recording_setup(tmp_path):
    path = tmp_path / "old-config.json"
    path.write_text(json.dumps({
        "ui": {"side_panel": "legacy"},
        "positions": {"P1": {"chart_offset_seconds": 12.5}},
        "default_view": {"param": "LAeq"},
    }), encoding="utf-8")

    extras = load_config_extras(path)

    assert extras["positions"]["P1"]["chart_offset_seconds"] == 12.5
    assert extras["default_view"]["param"] == "LAeq"
    assert "ui" not in extras
