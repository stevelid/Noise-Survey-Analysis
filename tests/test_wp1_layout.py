"""Layout and navigation (WP1): plot-frame borders, position header, saved order, range selector trace."""
import numpy as np
import pandas as pd
from bokeh.document import Document

from noise_survey_analysis.core.config import (
    CHART_SETTINGS, FRAME_BORDER_LEFT, FRAME_BORDER_RIGHT, LAYOUT_SETTINGS,
)
from noise_survey_analysis.core.data_manager import DataManager, PositionData
from noise_survey_analysis.ui.component_parts.navigation import decimate_minmax
from noise_survey_analysis.ui.component_parts.position_header import create_position_header
from noise_survey_analysis.visualization.dashBuilder import DashBuilder, apply_saved_position_order


def _position(name, offset_minutes=0):
    times = pd.date_range("2026-10-01 10:00", periods=40, freq="5min", tz="UTC") + pd.Timedelta(minutes=offset_minutes)
    position = PositionData(name=name)
    position.overview_totals = pd.DataFrame({
        "Datetime": times, "LAeq": np.linspace(40, 60, 40),
        "LAFmax": np.linspace(50, 70, 40), "LAF90": np.linspace(35, 45, 40),
    })
    position.overview_spectral = pd.DataFrame({"Datetime": times, "LZeq_63": np.linspace(30, 40, 40)})
    return position


def _build(names, saved=None):
    manager = DataManager(use_cache=False)
    manager._positions_data = {name: _position(name, i) for i, name in enumerate(names)}
    manager._position_order = list(names)
    document = Document()
    builder = DashBuilder()
    builder.build_layout(document, manager, CHART_SETTINGS, server_mode=False, saved_workspace_state=saved)
    return document, builder


def test_every_time_domain_figure_uses_the_same_fixed_frame_borders():
    document, builder = _build(["P1", "P2"])
    figures = []
    for comp in builder.components.values():
        figures += [comp["timeseries"].figure, comp["spectrogram"].figure]
    figures.append(builder.shared_components["range_selector"].figure)
    figures.append(builder.shared_components["freq_bar"].figure)
    assert FRAME_BORDER_LEFT > FRAME_BORDER_RIGHT > 0
    for fig in figures:
        assert fig.min_border_left == FRAME_BORDER_LEFT, fig.name
        assert fig.min_border_right == FRAME_BORDER_RIGHT, fig.name
        assert fig.toolbar_location is None or fig.name == "frequency_bar_chart"
        assert not fig.xaxis[0].axis_label if fig.xaxis else True


def test_compact_heights_and_range_selector_strip():
    document, builder = _build(["P1"])
    comp = builder.components["P1"]
    assert comp["timeseries"].figure.height == CHART_SETTINGS["low_freq_height"] == 150
    assert comp["spectrogram"].figure.height == CHART_SETTINGS["spectrogram_height"] == 124
    selector = builder.shared_components["range_selector"].figure
    assert selector.height == 44
    # Root cause of the empty strip: it relied on a DataRange1d with no explicit trace. Now an explicit
    # decimated LAeq line is always drawn.
    trace = builder.shared_components["range_selector"].trace_source
    assert len(trace.data["Datetime"]) == 40 and len(trace.data["level"]) == 40
    assert selector.y_range.start < 40 and selector.y_range.end > 60


def test_position_header_keeps_spinner_names_and_adds_controls():
    header = create_position_header("P1", chart_offset_seconds=1.5, audio_offset_seconds=-2.0)
    assert header["chart_offset_spinner"].name == "chart_offset_spinner_P1"
    assert header["audio_offset_spinner"].name == "audio_offset_spinner_P1"
    assert header["chart_offset_spinner"].value == 1.5
    assert header["audio_offset_spinner"].value == -2.0
    assert header["offsets_row"].visible is False
    assert header["layout"].name == "position_controls_P1"
    for key in ("status_div", "up_button", "down_button", "spec_button", "offsets_toggle", "banner_div"):
        assert header[key] is not None
    assert header["header_row"].height == LAYOUT_SETTINGS["position_header_height"]


def test_spinners_are_findable_by_name_in_the_built_document():
    document, _ = _build(["P1", "P2"])
    for pos in ("P1", "P2"):
        assert document.get_model_by_name(f"chart_offset_spinner_{pos}") is not None
        assert document.get_model_by_name(f"audio_offset_spinner_{pos}") is not None


def test_saved_position_order_applied_at_build_time():
    saved = {"appState": {"layout": {"positionOrder": ["P3", "P1"]}}}
    document, _ = _build(["P1", "P2", "P3"], saved=saved)
    stack = document.get_model_by_name("charts_stack_layout")
    assert [child.name for child in stack.children] == ["layout_P3", "layout_P1", "layout_P2"]
    default_doc, _ = _build(["P1", "P2", "P3"])
    assert [c.name for c in default_doc.get_model_by_name("charts_stack_layout").children] == [
        "layout_P1", "layout_P2", "layout_P3"]


def test_apply_saved_position_order_edge_cases():
    names = ["A", "B", "C"]
    assert apply_saved_position_order(names, None) == names
    assert apply_saved_position_order(names, {"layout": {"positionOrder": ["C", "X", "C", "A"]}}) == ["C", "A", "B"]
    assert apply_saved_position_order(names, {"appState": {"layout": {"positionOrder": []}}}) == names
    assert apply_saved_position_order(names, {"appState": {"layout": {"positionOrder": "bad"}}}) == names


def test_decimate_minmax_keeps_peaks_and_caps_points():
    x = np.arange(20000, dtype=float)
    y = np.zeros(20000)
    y[12345] = 90.0
    y[777] = -10.0
    dx, dy = decimate_minmax(x, y, max_points=2000)
    assert dx.size <= 2000
    assert dy.max() == 90.0 and dy.min() == -10.0
    assert np.all(np.diff(dx) > 0)
    short_x, short_y = decimate_minmax([1, 2, np.nan], [3, 4, 5], 2000)
    assert list(short_x) == [1.0, 2.0]


def test_dock_holds_frequency_and_summary_and_stack_models_are_bridged():
    document, builder = _build(["P1"])
    dock = document.get_model_by_name("frequency_dock_layout")
    assert dock is not None
    refs = dock.references()
    assert document.get_model_by_name("frequency_bar_layout") in refs
    assert document.get_model_by_name("summary_table_div") in refs
    bridge = builder._assemble_js_bridge_dictionary()
    for key in ("chartsStackLayout", "positionLayouts", "rangeSelectorFigure", "frequencyDockInner", "layoutControls"):
        assert bridge[key], key
