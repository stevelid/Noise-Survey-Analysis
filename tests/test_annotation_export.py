"""Known answers, migration round trips and bounded source-reader contracts."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from noise_survey_analysis.core.annotation_metrics import (
    background_intervals, compute_region_metrics, datetime_milliseconds,
    subtract_intervals, weighted_quantile,
)
from noise_survey_analysis.core.annotation_windows import iter_source_windows
from noise_survey_analysis.export.annotations import (
    export_annotations, load_annotation_input, read_export_section,
)

BASE = 1_700_000_000_000


def frame(levels, *, step=1, offset=0, **columns):
    return pd.DataFrame({"Datetime": pd.to_datetime(BASE + offset + np.arange(len(levels)) * step * 1000, unit="ms", utc=True),
                         "LAeq": levels, **columns})


def areas(start, end):
    return [{"start": BASE + start * 1000, "end": BASE + end * 1000}]


def workspace(tmp_path: Path, *, include_overview=False):
    source = tmp_path / "P1_log.csv"
    frame([60, 70], LAFmax=[65, 75], LZeq_63=[50, 60], LZeq_1000=[40, 50]).to_csv(source, index=False)
    sources = [{"position_name": "P1", "parser_type": "generic", "timezone": "UTC", "file_paths": [str(source)]}]
    if include_overview:
        overview = tmp_path / "P1_summary.csv"
        frame([65, 65], step=300, LAFmax=[75, 75], LZeq_63=[55, 55]).to_csv(overview, index=False)
        sources.append({"position_name": "P1", "parser_type": "generic", "timezone": "UTC", "data_profile": "overview", "file_paths": [str(overview)]})
    region = {"id": 7, "positionId": "P1", "areas": areas(0, 2), "note": 'Dog, then "traffic"\n[OVERALL]\nünicode',
              "categoryId": "custom", "color": None, "meterStates": {"P1": "present", "P2": "absent"}}
    payload = {"version": 2, "sourceConfigs": sources, "appState": {
        "view": {"availablePositions": ["P1", "P2"], "positionDisplayTitles": {"P1": "Garden", "P2": "Road"}},
        "regions": {"byId": {"7": region}, "allIds": [7], "categories": {"byId": {
            "custom": {"id": "custom", "label": "Custom category", "color": "#112233"},
            "unused": {"id": "unused", "label": "Unused", "color": "#abcdef"},
            "other": {"id": "other", "label": "Other", "color": "#1e88e5"}}, "allIds": ["custom", "unused", "other"]}},
        "markers": {"byId": {"1": {"id": 1, "timestamp": BASE, "note": "Marker", "metrics": {"P1": {"LAeq": 60}}}}, "allIds": [1]}}}
    path = tmp_path / "workspace.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, payload


def test_known_answer_and_fractional_interval_weighting():
    data = frame([60, 70], LAFmax=[65, 75])
    result = compute_region_metrics(data, areas(0, 2), sample_interval_s=1)
    assert result.LAeq_dB == pytest.approx(67.4036269, abs=1e-6)
    assert result.LAFmax_dB == 75
    assert result.coverage == 1
    partial = compute_region_metrics(data, areas(0, 1.5), sample_interval_s=1)
    assert partial.LAeq_dB == pytest.approx(66.0205999, abs=1e-6)
    assert "indicative" in result.percentile_method


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_datetime_storage_unit_does_not_change_region_or_spectral_metrics(unit):
    data = frame([60, 70], LZeq_63=[50, 60])
    data["Datetime"] = data["Datetime"].dt.as_unit(unit)
    result = compute_region_metrics(data, areas(0, 2), sample_interval_s=1)
    assert datetime_milliseconds(data["Datetime"]).tolist() == [BASE, BASE + 1000]
    assert result.coverage == 1
    assert result.LAeq_dB == pytest.approx(67.4036269)
    assert result.spectra["LZeq"][63] == pytest.approx(57.4036269)


def test_overlapping_areas_counted_once_and_offset_applies_to_query():
    result = compute_region_metrics(frame([60, 70]), [*areas(1, 2.5), *areas(2, 3)],
                                    chart_offset_ms=1000, sample_interval_s=1)
    assert result.LAeq_dB == pytest.approx(67.4036269)
    assert result.coverage == 1


def test_gaps_are_not_filled_by_preceding_sample():
    result = compute_region_metrics(frame([60, 70], step=10), areas(0, 11), sample_interval_s=1)
    assert result.coverage == pytest.approx(2/11)
    assert any("incomplete" in reason for reason in result.missing_reasons)


def test_no_lafmax_fallback_and_exact_weighted_percentile():
    result = compute_region_metrics(frame([60, 70]), areas(0, 2), sample_interval_s=1)
    assert result.LAFmax_dB is None
    assert result.LAF90_dB == 60
    assert weighted_quantile(np.array([30, 50]), np.array([1, 99])) == 50


def test_background_is_pooled_la90_plus_same_context_laeq():
    data = frame([30]*100 + [60]*10 + [50]*100)
    result = compute_region_metrics(data, areas(100, 110), sample_interval_s=1,
                                    context_areas=[*areas(0, 100), *areas(110, 210)])
    assert result.background_LA90_dB == 30
    assert result.background_LAeq_dB == pytest.approx(47.03291378)
    assert result.diff_from_background_dB == 30
    assert result.context_duration_s == 200


def test_background_excludes_present_regions_only_and_minimum_context():
    region = {"positionId": "P1", "areas": areas(100, 110), "meterStates": {"P1": "present"}}
    other = {"positionId": "P2", "areas": areas(0, 20), "meterStates": {"P1": "present"}}
    absent = {"positionId": "P2", "areas": areas(20, 40), "meterStates": {"P1": "absent"}}
    context = background_intervals(region, [region, other, absent], "P1", 100)
    assert context == [(BASE + 20000, BASE + 100000), (BASE + 110000, BASE + 210000)]
    result = compute_region_metrics(frame([30]*10), areas(0, 1), sample_interval_s=1,
                                    context_areas=areas(1, 10), min_context_s=60)
    assert result.background_LA90_dB is None
    assert result.context_duration_s == 9


def test_sectioned_export_round_trip_preserves_annotations_categories_and_markers(tmp_path):
    path, original = workspace(tmp_path)
    output = export_annotations(path)
    table = read_export_section(output, "REGIONS")
    assert len(table) == 1
    assert table.loc[0, "LAeq_dB"] == pytest.approx(67.403627)
    restored = load_annotation_input(output)
    expected = original["appState"]["regions"]["byId"]["7"]
    actual = restored["appState"]["regions"]["byId"]["7"]
    for key in ("id", "positionId", "areas", "note", "categoryId", "color", "meterStates"):
        assert actual[key] == expected[key]
    assert restored["appState"]["regions"]["categories"] == original["appState"]["regions"]["categories"]
    assert restored["appState"]["markers"]["byId"]["1"]["note"] == "Marker"
    assert len(read_export_section(output, "OVERALL")) == 2
    spectrum = read_export_section(output, "SPECTRAL")
    assert list(spectrum.columns)[-2:] == ["63Hz", "1000Hz"]
    notes = read_export_section(output, "NOTES")
    assert "LA90" in notes.set_index("key").loc["background_method", "value"]


def test_optional_resolutions_are_off_by_default_and_overview_fallback_is_labelled(tmp_path):
    path, _ = workspace(tmp_path, include_overview=True)
    normal = export_annotations(path, tmp_path / "normal.csv")
    overall = read_export_section(normal, "OVERALL")
    assert list(overall.data_resolution) == ["log", "none"]
    both = export_annotations(path, tmp_path / "both.csv", include_all_resolutions=True)
    assert len(read_export_section(both, "OVERALL")) == 3
    assert len(read_export_section(both, "SPECTRAL")) == 3
    (tmp_path / "P1_log.csv").unlink()
    missing = export_annotations(path, tmp_path / "missing.csv")
    overall = read_export_section(missing, "OVERALL")
    assert overall.loc[0, "LAeq_dB"] == 65
    assert overall.loc[0, "data_resolution"] == "overview"
    assert overall.loc[1, "data_resolution"] == "none"
    assert "resolution=best-available" in missing.read_text(encoding="utf-8-sig").splitlines()[0]


def test_reader_respects_chunks_and_keeps_only_requested_windows(tmp_path, monkeypatch):
    source = tmp_path / "meter_log.csv"
    frame(np.full(1000, 45)).to_csv(source, index=False)
    import noise_survey_analysis.core.annotation_windows as readers
    sizes = []
    original = readers._normalize

    def observe(raw, parser, options):
        sizes.append(len(raw))
        return original(raw, parser, options)

    monkeypatch.setattr(readers, "_normalize", observe)
    chunks = list(iter_source_windows(source, areas(500, 501), options={"parser_type": "generic", "timezone": "UTC"}, chunk_rows=37))
    assert max(sizes) <= 37
    assert sum(len(chunk.frame) for chunk in chunks) == 1
    assert chunks[0].sample_interval_s == 1


def test_full_export_does_not_call_eager_lazy_loader(tmp_path, monkeypatch):
    from noise_survey_analysis.core.data_manager import PositionData

    def forbidden(*args, **kwargs):
        pytest.fail("Full-resolution exporter called eager dashboard loader")

    monkeypatch.setattr(PositionData, "load_log_data_lazy", forbidden)
    path, _ = workspace(tmp_path)
    assert export_annotations(path).exists()


def test_nti_streaming_header_reuses_instrument_normalization(tmp_path):
    source = tmp_path / "meter_123_Log.txt"
    source.write_text("# Broadband LOG Results\nDate\tTime\tLAeq_dt\tLAFmax_dt\n[d]\t[t]\t[dB]\t[dB]\n2023-11-14\t22:13:20\t60\t65\n2023-11-14\t22:13:21\t70\t75\n#CheckSum\n", encoding="utf-8")
    chunks = list(iter_source_windows(source, areas(0, 2), options={"parser_type": "nti", "timezone": "UTC"}))
    assert len(chunks) == 1
    assert list(chunks[0].frame.LAeq) == [60, 70]
    assert chunks[0].resolution == "log"


def test_excel_read_only_source_and_legacy_xls_limitation(tmp_path):
    source = tmp_path / "meter.xlsx"
    data = frame([60, 70])
    data["Datetime"] = data["Datetime"].dt.tz_localize(None)
    data.to_excel(source, index=False)
    chunks = list(iter_source_windows(source, areas(0, 2), options={"parser_type": "generic", "timezone": "UTC"}))
    assert sum(len(chunk.frame) for chunk in chunks) == 2
    legacy = tmp_path / "meter.xls"
    legacy.touch()
    with pytest.raises(ValueError, match="Legacy .xls"):
        list(iter_source_windows(legacy, areas(0, 2), options={"parser_type": "generic"}))


def test_reader_stops_before_analysis_and_handles_empty_unknown_sections(tmp_path):
    path = tmp_path / "export.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows([["NSA annotations export", "format=2"], ["[REGIONS]"], ["id", "note"],
                          [1, "One\n[OVERALL]\nTwo"], [], ["[OVERALL]"], ["region_id", "LAeq_dB"],
                          [1, 67.4], [], ["[SPECTRAL]"], ["region_id", "meter"], [], ["[FUTURE]"], ["x"], ["y"]])
    assert read_export_section(path, "REGIONS").loc[0, "note"] == "One\n[OVERALL]\nTwo"
    assert read_export_section(path, "OVERALL").loc[0, "LAeq_dB"] == 67.4
    assert read_export_section(path, "SPECTRAL").empty
    assert read_export_section(path, "MISSING").empty


def test_legacy_csv_import_and_self_overwrite_rejected(tmp_path):
    path = tmp_path / "legacy.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows([["type", "id", "positionId", "start_utc", "end_utc", "note", "color"],
                          ["region", 1, "P1", "2023-11-14 22:13:20", "2023-11-14 22:13:22", "Old", "#112233"],
                          ["region", 2, "P2", "2023-11-14 22:13:20", "2023-11-14 22:13:22", "Old", "#112233"]])
    restored = load_annotation_input(path)
    assert len(restored["appState"]["regions"]["allIds"]) == 1
    assert restored["appState"]["regions"]["byId"]["1"]["meterStates"] == {"P1": "present", "P2": "present"}
    with pytest.raises(ValueError, match="overwrite"):
        export_annotations(path, path)


def test_subtract_intervals_handles_multiple_exclusions():
    assert subtract_intervals([(0, 10)], [(1, 2), (4, 6)]) == [(0, 1), (2, 4), (6, 10)]


@pytest.mark.parametrize("parser_type,text,expected", [
    ("sentry", "Time (Date hh:mm:ss.ms),LEQ dB-A,Lmax dB-A,L10 dB-A,L90 dB-A\n"
               "2023-11-14 22:13:20,60,65,63,55\n2023-11-14 22:13:21,70,75,73,65\n",
     {"LAeq": [60, 70], "LAFmax": [65, 75], "LAF90": [55, 65]}),
    ("svan", "L348\nSerial: 143568 Meter: 971-2\n\n"
             ",,P3,1/3 Octave,1/3 Octave\n"
             ",,LAeq (TH) [dB],1/3 Oct LZeq (TH) [dB],1/3 Oct LZeq (TH) [dB]\n"
             "Date & time,flags,,8 Hz,10 Hz\n"
             "2023-11-14 22:13:20,0,60,40,41\n2023-11-14 22:13:21,0,70,50,51\n",
     {"LAeq": [60, 70], "LZeq_8": [40, 50], "LZeq_10": [41, 51]}),
    ("nti", "# RTA LOG Results LZeq_dt\nBand [Hz]\tDate\tTime\t63\t1000\n"
            "[]\t[d]\t[t]\t[dB]\t[dB]\n"
            "0\t2023-11-14\t22:13:20\t40\t41\n0\t2023-11-14\t22:13:21\t50\t51\n#CheckSum\n",
     {"LZeq_63": [40, 50], "LZeq_1000": [41, 51]}),
])
def test_real_instrument_headers_match_eager_parser_columns(tmp_path, parser_type, text, expected):
    from noise_survey_analysis.core.data_parsers import NoiseParserFactory
    suffix = "_RTA_3rd_Log.txt" if parser_type == "nti" else "_log.csv"
    path = tmp_path / ("meter" + suffix)
    path.write_text(text, encoding="utf-8")
    chunks = list(iter_source_windows(path, areas(0, 2), options={"parser_type": parser_type, "timezone": "UTC"}))
    actual = pd.concat([chunk.frame for chunk in chunks], ignore_index=True)
    parsed = NoiseParserFactory.get_parser(str(path), parser_type, timezone="UTC").parse(str(path))
    for column, values in expected.items():
        assert list(actual[column]) == values
        eager = parsed.totals_df if parsed.totals_df is not None and column in parsed.totals_df else parsed.spectral_df
        assert eager is not None and list(eager[column]) == values


def test_svan_xlsx_preamble_is_read_only_and_normalized(tmp_path):
    from openpyxl import Workbook
    path = tmp_path / "meter_overview.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.append(["Meter overview"])
    sheet.append(["Date & time", "LAeq (TH) [dB]", "LAFmax (TH) [dB]"])
    sheet.append(["2023-11-14 22:13:20", 60, 65])
    sheet.append(["2023-11-14 22:18:20", 70, 75])
    book.save(path)
    chunks = list(iter_source_windows(path, areas(0, 301), options={"parser_type": "svan", "timezone": "UTC"}))
    assert list(chunks[0].frame.LAeq) == [60, 70]
    assert list(chunks[0].frame.LAFmax) == [65, 75]
    assert chunks[0].resolution == "overview"


def test_offset_round_trip_and_target_meter_window_queries(tmp_path, monkeypatch):
    path, payload = workspace(tmp_path)
    # Source P1 samples 0--2 s appear at 10--12 s on aligned charts.
    payload["appState"]["view"]["positionChartOffsets"] = {"P1": 10000, "P2": -3000}
    payload["appState"]["regions"]["byId"]["7"]["areas"] = areas(10, 12)
    path.write_text(json.dumps(payload), encoding="utf-8")
    output = export_annotations(path)
    overall = read_export_section(output, "OVERALL")
    assert overall.loc[0, "LAeq_dB"] == pytest.approx(67.403627)
    assert load_annotation_input(output)["appState"]["view"]["positionChartOffsets"] == {"P1": 10000, "P2": -3000}
    headers = read_export_section(output, "REGIONS")
    assert headers.loc[0, "chart_offset_ms"] == 10000


def test_legacy_multiple_datetime_areas_are_preserved(tmp_path):
    path = tmp_path / "old.csv"
    serialized = json.dumps([{"startUtc": "2023-11-14 22:13:20", "endUtc": "2023-11-14 22:13:21"},
                             {"startUtc": "2023-11-14 22:13:23", "endUtc": "2023-11-14 22:13:24"}])
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([["type", "id", "positionId", "start_utc", "end_utc", "note", "color", "areas"],
             ["region", 1, "P1", "2023-11-14 22:13:20", "2023-11-14 22:13:24", "Old", "#123456", serialized]])
    regions = load_annotation_input(path)["appState"]["regions"]
    assert regions["byId"]["1"]["areas"] == [*areas(0, 1), *areas(3, 4)]


def test_mixed_source_periods_retain_duration_weights_instead_of_global_minimum():
    data = frame([60, 70], step=1)
    data["__sample_interval_s"] = [.1, 1]
    result = compute_region_metrics(data, areas(0, 2))
    assert result.coverage == pytest.approx(1.1 / 2)
    assert result.sample_interval_s == 1
    assert result.LAeq_dB == pytest.approx(69.62928689)


def test_missing_spectral_rows_still_cover_absent_meter(tmp_path):
    path, _ = workspace(tmp_path)
    output = export_annotations(path)
    table = read_export_section(output, "SPECTRAL")
    assert len(table) == 2
    assert set(table.meter) == {"P1", "P2"}
    missing = table.loc[table.meter == "P2"].iloc[0]
    assert missing["state"] == "absent"
    assert pd.isna(missing["63Hz"])
    assert "unavailable" in missing["missing_reasons"]


def test_source_iteration_finishes_one_meter_before_next(tmp_path, monkeypatch):
    path, payload = workspace(tmp_path)
    source2 = tmp_path / "P2_log.csv"
    frame([50, 60]).to_csv(source2, index=False)
    payload["sourceConfigs"].append({"position_name": "P2", "parser_type": "generic", "timezone": "UTC", "file_paths": [str(source2)]})
    path.write_text(json.dumps(payload), encoding="utf-8")
    import noise_survey_analysis.export.annotations as exporter
    original = exporter.iter_source_windows
    events = []

    def observe(source, windows, **kwargs):
        events.append(("open", Path(source).name))
        try:
            yield from original(source, windows, **kwargs)
        finally:
            events.append(("close", Path(source).name))

    monkeypatch.setattr(exporter, "iter_source_windows", observe)
    export_annotations(path)
    assert events == [("open", "P1_log.csv"), ("close", "P1_log.csv"),
                      ("open", "P2_log.csv"), ("close", "P2_log.csv")]


def test_external_config_seconds_are_converted_once_and_workspace_ms_take_precedence(tmp_path):
    path, payload = workspace(tmp_path)
    payload["appState"]["regions"]["byId"]["7"]["areas"] = areas(10, 12)
    path.write_text(json.dumps(payload), encoding="utf-8")
    config = {"sources": [{"position": "P1", "parser_type": "generic", "timezone": "UTC", "path": "P1_log.csv"}],
              "positions": {"P1": {"chart_offset_seconds": 10}}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    output = export_annotations(path, tmp_path / "from-config.csv", source_configs=config_path)
    assert read_export_section(output, "REGIONS").loc[0, "chart_offset_ms"] == 10000
    assert read_export_section(output, "OVERALL").loc[0, "LAeq_dB"] == pytest.approx(67.403627)
    payload["appState"]["view"]["positionChartOffsets"] = {"P1": 9000}
    path.write_text(json.dumps(payload), encoding="utf-8")
    output = export_annotations(path, tmp_path / "override.csv", source_configs=config_path)
    assert read_export_section(output, "REGIONS").loc[0, "chart_offset_ms"] == 9000


def test_numeric_looking_notes_categories_and_meter_ids_stay_text(tmp_path):
    path, payload = workspace(tmp_path)
    region = payload["appState"]["regions"]["byId"]["7"]
    region.update({"note": "00123", "categoryId": "0007", "positionId": "001",
                   "meterStates": {"001": "present", "P2": "absent"}})
    payload["appState"]["regions"]["categories"]["byId"]["0007"] = {"id": "0007", "label": "007", "color": "#112233"}
    payload["appState"]["regions"]["categories"]["allIds"].append("0007")
    payload["appState"]["view"]["availablePositions"] = ["001", "P2"]
    payload["sourceConfigs"][0]["position_name"] = "001"
    path.write_text(json.dumps(payload), encoding="utf-8")
    restored = load_annotation_input(export_annotations(path))
    actual = restored["appState"]["regions"]["byId"]["7"]
    assert actual["note"] == "00123"
    assert actual["categoryId"] == "0007"
    assert actual["positionId"] == "001"


@pytest.mark.parametrize("reverse_files", [False, True])
def test_separate_broadband_and_spectrum_clocks_keep_native_sample_durations(tmp_path, reverse_files):
    path, payload = workspace(tmp_path)
    broad = tmp_path / "broad_log.csv"
    fast = tmp_path / "fast_log.csv"
    frame([60, 70], LAFmax=[65, 75]).to_csv(broad, index=False)
    pd.DataFrame({"Datetime": pd.to_datetime(BASE + np.arange(20) * 100, unit="ms", utc=True),
                  "LZeq_63": [40]*10 + [50]*10}).to_csv(fast, index=False)
    paths = [str(broad), str(fast)]
    if reverse_files:
        paths.reverse()
    payload["sourceConfigs"][0]["file_paths"] = paths
    payload["appState"]["regions"]["byId"]["7"]["areas"] = areas(.5, 1.5)
    path.write_text(json.dumps(payload), encoding="utf-8")
    output = export_annotations(path)
    overall = read_export_section(output, "OVERALL")
    assert overall.loc[0, "LAeq_dB"] == pytest.approx(67.403627)
    assert overall.loc[0, "coverage"] == 1
    assert read_export_section(output, "SPECTRAL").loc[0, "63Hz"] == pytest.approx(47.403627)


def test_fast_percentile_and_slow_energy_share_identical_context_time():
    times = pd.to_datetime(BASE + np.arange(20) * 100, unit="ms", utc=True)
    data = pd.DataFrame({"Datetime": times, "LAeq": [60] + [np.nan]*9 + [70] + [np.nan]*9,
                         "LAF": [30]*10 + [50]*10,
                         "__sample_interval_s:LAeq": [1] + [np.nan]*9 + [1] + [np.nan]*9,
                         "__sample_interval_s:LAF": [.1]*20, "__sample_interval_s": [.1]*20})
    result = compute_region_metrics(data, areas(0, .1), context_areas=areas(.1, 2),
                                    sample_interval_s=1, min_context_s=1)
    assert result.context_duration_s == pytest.approx(1.9)
    assert result.background_LA90_dB == 30
    expected = 10 * np.log10((.9 * 10**6 + 10**7) / 1.9)
    assert result.background_LAeq_dB == pytest.approx(expected)


def test_overview_only_spectra_are_used_and_missing_meter_is_explicit(tmp_path):
    path, _ = workspace(tmp_path, include_overview=True)
    (tmp_path / "P1_log.csv").unlink()
    output = export_annotations(path)
    spectral = read_export_section(output, "SPECTRAL")
    assert len(spectral) == 2
    assert list(spectral.data_resolution) == ["overview", "none"]
    assert spectral.loc[0, "63Hz"] == 55
    assert pd.isna(spectral.loc[1, "63Hz"])


def test_partial_log_uses_usable_overview_and_remains_explicit_when_no_overview(tmp_path):
    path, payload = workspace(tmp_path, include_overview=True)
    payload["appState"]["regions"]["byId"]["7"]["areas"] = areas(0, 4)
    path.write_text(json.dumps(payload), encoding="utf-8")
    output = export_annotations(path, tmp_path / "fallback.csv")
    overall = read_export_section(output, "OVERALL")
    assert overall.loc[0, "data_resolution"] == "overview"
    assert overall.loc[0, "LAeq_dB"] == 65
    payload["sourceConfigs"] = payload["sourceConfigs"][:1]
    path.write_text(json.dumps(payload), encoding="utf-8")
    output = export_annotations(path, tmp_path / "partial.csv")
    overall = read_export_section(output, "OVERALL")
    assert overall.loc[0, "data_resolution"] == "log"
    assert overall.loc[0, "coverage"] == .5
    assert "incomplete" in overall.loc[0, "missing_reasons"]


def test_spectral_resolution_is_independent_of_broadband_and_per_parameter(tmp_path):
    path, payload = workspace(tmp_path, include_overview=True)
    # Broadband log is complete but only covers half the region spectrally.
    source = tmp_path / "P1_log.csv"
    frame([60, 70], LAFmax=[65, 75], LZeq_63=[80, np.nan]).to_csv(source, index=False)
    output = export_annotations(path, tmp_path / "independent.csv")
    assert read_export_section(output, "OVERALL").loc[0, "data_resolution"] == "log"
    spectrum = read_export_section(output, "SPECTRAL")
    assert spectrum.loc[0, "data_resolution"] == "overview"
    assert spectrum.loc[0, "63Hz"] == 55
    assert spectrum.loc[0, "coverage"] == 1
    # A separate spectral-only source can provide complete log LZeq while
    # broadband falls back to overview. Another parameter remains overview.
    frame([np.nan, np.nan], LZeq_63=[40, 50]).to_csv(source, index=False)
    overview = tmp_path / "P1_summary.csv"
    frame([65, 65], step=300, LZeq_63=[55, 55], LZFmax_63=[75, 75]).to_csv(overview, index=False)
    output = export_annotations(path, tmp_path / "spectral-only.csv")
    assert read_export_section(output, "OVERALL").loc[0, "data_resolution"] == "overview"
    spectrum = read_export_section(output, "SPECTRAL")
    p1 = spectrum.loc[spectrum.meter == "P1"].set_index("parameter")
    assert p1.loc["LZeq", "data_resolution"] == "log"
    assert p1.loc["LZeq", "63Hz"] == pytest.approx(47.403627)
    assert p1.loc["LZFmax", "data_resolution"] == "overview"


def test_explicit_utc_survives_bad_and_naive_timestamps_in_same_summer_chunk(tmp_path):
    path = tmp_path / "mixed_log.csv"
    path.write_text("Datetime,LAeq\n2026-06-01T12:00:00Z,60\ninvalid,99\n"
                    "2026-06-01T12:00:01+00:00,70\n2026-06-01 13:00:02,65\n", encoding="utf-8")
    start = pd.Timestamp("2026-06-01T12:00:00Z").value / 1e6
    chunks = list(iter_source_windows(path, [(start, start + 3000)],
                                      options={"parser_type": "generic", "timezone": "Europe/London"}))
    assert len(chunks) == 1
    assert list(chunks[0].frame.LAeq) == [60, 70, 65]
    assert list(datetime_milliseconds(chunks[0].frame.Datetime)) == [start, start + 1000, start + 2000]


def test_standalone_regions_section_keeps_state_columns_and_does_not_consolidate_v2(tmp_path):
    path = tmp_path / "section only.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows([["[REGIONS]"],
            ["id", "category", "category_label", "note", "colour", "start", "end", "origin_meter", "areas", "P1", "P2"],
            [1, "custom", "Custom label", "Same note", "#112233", "2023-11-14 22:13:20", "2023-11-14 22:13:22", "P1", "", "present", "absent"],
            [2, "custom", "Custom label", "Same note", "#112233", "2023-11-14 22:13:20", "2023-11-14 22:13:22", "P2", "", "unchecked", "present"], []])
    restored = load_annotation_input(path)
    regions = restored["appState"]["regions"]
    assert len(regions["allIds"]) == 2
    assert regions["byId"]["1"]["meterStates"] == {"P1": "present", "P2": "absent"}
    assert regions["categories"]["byId"]["custom"]["label"] == "Custom label"
