import json

import pandas as pd
import pytest
from bokeh.document import Document

from noise_survey_analysis.core.app_setup import load_config_extras
from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_manager import DataManager, PositionData
from noise_survey_analysis.core.weather import parse_weather_csv
from noise_survey_analysis.visualization.dashBuilder import DashBuilder


def test_pce_uses_interval_rain_and_drops_calm_direction_and_lost_samples(tmp_path):
    path = tmp_path / "pce.csv"
    path.write_text(
        "DateTime (UTC),Wind avg (m/s),Wind gust (m/s),Wind dir (deg),"
        "Rain in interval (mm),Rain counter (mm),Sensor lost\n"
        "2026-11-04 13:55,3,4,22.5,9.0,246,\n"
        "2026-11-04 14:00,0,0,22.5,,246,\n"
        "2026-11-04 14:06,2,5,337.5,0.3,246.3,\n"
        "2026-11-04 14:11,7,9,270,0.3,246.6,Y\n",
        encoding="utf-8",
    )

    data = parse_weather_csv(path, {"start": "2026-11-04T13:58:00Z"}).samples.reset_index(drop=True)
    assert len(data) == 3
    assert data.rain.sum() == pytest.approx(0.3)
    assert pd.isna(data.direction[0]) and pd.isna(data.rain[0])
    assert data.direction[1] == 337.5 and data.gust[1] == 5
    assert data.interval_start[0] == pd.Timestamp("2026-11-04T13:55:00Z")
    assert data.interval_start[1] == pd.Timestamp("2026-11-04T14:00:00Z")
    assert data.loc[2, ["wind", "gust", "direction", "rain"]].isna().all()


def test_visual_crossing_requires_units_and_local_timezone(tmp_path):
    path = tmp_path / "vc.csv"
    path.write_text("datetime,windspeed,windgust,winddir,precip\n"
                    "2026-07-02T09:00:00,18,36,360,0.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="weather.units"):
        parse_weather_csv(path, {})
    with pytest.raises(ValueError, match="weather.timezone"):
        parse_weather_csv(path, {"units": "metric"})

    sample = parse_weather_csv(path, {"units": "metric", "timezone": "Europe/London"}).samples.iloc[0]
    assert sample.time == pd.Timestamp("2026-07-02T08:00:00Z")
    assert sample.interval_start == pd.Timestamp("2026-07-02T07:00:00Z")
    assert sample.wind == pytest.approx(5) and sample.gust == pytest.approx(10)
    assert sample.direction == 0 and sample.rain == 0.5


@pytest.mark.parametrize("include_weather", [True, False])
def test_optional_weather_is_last_and_shares_acoustic_range(tmp_path, include_weather):
    config = tmp_path / "config.json"
    settings = {}
    if include_weather:
        (tmp_path / "station.csv").write_text(
            "DateTime (UTC),Wind avg (m/s),Wind gust (m/s),Wind dir (deg),Rain in interval (mm)\n"
            "2026-11-04 14:05,2,5,45,0.3\n", encoding="utf-8",
        )
        settings["weather"] = {"path": "station.csv"}
    config.write_text(json.dumps(settings), encoding="utf-8")
    extras = load_config_extras(config)

    times = pd.date_range("2026-11-04 14:00", periods=3, freq="5min", tz="UTC")
    position = PositionData(name="P1")
    position.overview_totals = pd.DataFrame({"Datetime": times, "LAeq": [45.0, 46.0, 47.0]})
    position.overview_spectral = pd.DataFrame({"Datetime": times, "LZeq_63": [32.0, 33.0, 34.0]})
    manager = DataManager(use_cache=False)
    manager._positions_data = {"P1": position}
    manager._position_order = ["P1"]
    doc = Document()

    DashBuilder().build_layout(doc, manager, CHART_SETTINGS, weather_config=extras["weather"])
    weather = doc.get_model_by_name("survey_weather")
    stack = doc.get_model_by_name("charts_stack_layout")
    if include_weather:
        assert stack.children[-1] is weather
        assert len(weather.children) == 2
        assert all(plot.x_range is doc.get_model_by_name("master_x_range") for plot in weather.children)
        assert set(doc.get_model_by_name("weather_samples").data) == {
            "index", "time", "wind", "gust", "direction", "rain", "interval_start",
        }
    else:
        assert weather is None and len(stack.children) == 1
