"""LLM-oriented export: README, EVENTS, UTC/ISO columns, marker levels, JSON sibling,
suggestion filtering and read-failure propagation. Old sections must keep parsing."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from noise_survey_analysis.export.annotations import (
    JSON_SCHEMA, annotations_json_path, export_annotations, load_annotation_input, main, read_export_section,
)
from test_annotation_export import BASE, areas, frame, workspace


def sidecar(csv_path):
    return json.loads(annotations_json_path(csv_path).read_text(encoding="utf-8"))


def add_regions(path, payload, extra):
    byid = payload["appState"]["regions"]["byId"]
    for key, fields in extra.items():
        byid[str(key)] = {**byid["7"], "id": key, "areas": areas(0, 2), "note": f"note {key}", **fields}
        payload["appState"]["regions"]["allIds"].append(key)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_readme_is_first_section_and_notes_last_and_old_columns_survive(tmp_path):
    path, _ = workspace(tmp_path)
    output = export_annotations(path)
    import csv
    with output.open(encoding="utf-8-sig", newline="") as handle:
        markers = [row[0] for row in csv.reader(handle) if len(row) == 1 and row[0].startswith("[") and row[0].endswith("]")]
    assert markers[0] == "[README]" and markers[-1] == "[NOTES]"
    assert markers == ["[README]", "[REGIONS]", "[EVENTS]", "[OVERALL]", "[SPECTRAL]", "[MARKERS]", "[NOTES]"]
    readme = read_export_section(output, "README").set_index("key")["value"]
    for key in ("job", "exported", "timezone", "units", "resolution_policy", "coarse_resolution", "background_method", "section.EVENTS", "meter.P1"):
        assert key in readme.index, key
    assert "µPa" in readme["units"]
    assert "title=Garden" in readme["meter.P1"]
    regions = read_export_section(output, "REGIONS")
    for column in ("start", "end", "start_local", "end_local", "source_start_local", "source_end_local", "data_resolution", "LAeq_dB"):
        assert column in regions.columns
    for column in ("start_utc", "end_utc", "timezone", "source", "status", "confidence", "rationale", "coarse_resolution", "coarse_resolution_reason"):
        assert column in regions.columns
    assert regions.loc[0, "start"] == "2023-11-14 22:13:20.000"       # unchanged format
    assert regions.loc[0, "start_utc"] == "2023-11-14T22:13:20.000Z"
    assert regions.loc[0, "timezone"] == "UTC"
    assert regions.loc[0, "source"] == "user" and regions.loc[0, "status"] == ""
    # Existing consumers: sectioned import still works and restores the region.
    assert load_annotation_input(output)["appState"]["regions"]["byId"]["7"]["note"].startswith("Dog")


def test_events_section_has_one_row_per_region_with_per_meter_levels(tmp_path):
    path, _ = workspace(tmp_path)
    events = read_export_section(export_annotations(path), "EVENTS")
    assert len(events) == 1
    row = events.loc[0]
    assert row["id"] == 7 and row["category_label"] == "Custom category" and row["origin_meter"] == "P1"
    assert row["start_utc"] == "2023-11-14T22:13:20.000Z" and row["end_utc"] == "2023-11-14T22:13:22.000Z"
    assert row["start_local_iso"] == "2023-11-14T22:13:20.000+00:00"
    assert row["duration_s"] == 2
    assert row["P1__state"] == "present" and row["P2__state"] == "absent"
    assert row["P1__LAeq_dB"] == pytest.approx(67.403627)
    assert row["P1__resolution"] == "log" and row["P1__coverage"] == 1
    assert row["P1__coarse"] is np.False_ or row["P1__coarse"] == False  # noqa: E712
    assert pd.isna(row["P2__LAeq_dB"]) and row["P2__resolution"] == "none"
    for suffix in ("LAFmax_dB", "LAF90_dB", "bg_LA90_dB", "diff_dB"):
        assert f"P1__{suffix}" in events.columns


def test_bst_event_local_iso_carries_offset(tmp_path):
    path, payload = workspace(tmp_path)
    start = pd.Timestamp("2026-07-01 10:00:00", tz="UTC").value // 10**6
    payload["appState"]["regions"]["byId"]["7"]["areas"] = [{"start": start, "end": start + 2000}]
    payload["sourceConfigs"][0]["timezone"] = "Europe/London"
    path.write_text(json.dumps(payload), encoding="utf-8")
    row = read_export_section(export_annotations(path), "EVENTS").loc[0]
    assert row["start_utc"] == "2026-07-01T10:00:00.000Z"
    assert row["start_local_iso"] == "2026-07-01T11:00:00.000+01:00"
    assert row["timezone"] == "Europe/London"


def test_json_sibling_shape(tmp_path):
    path, _ = workspace(tmp_path)
    output = export_annotations(path, tmp_path / "out.csv")
    assert annotations_json_path(output) == tmp_path / "out.json"
    document = sidecar(output)
    assert document["schema"] == JSON_SCHEMA == "nsa-annotations/1"
    assert {"readme", "meters", "events", "markers", "units", "timezone"} <= set(document)
    assert [meter["id"] for meter in document["meters"]] == ["P1", "P2"]
    assert document["meters"][0]["title"] == "Garden" and document["meters"][0]["chart_offset_ms"] == 0
    event = document["events"][0]
    assert event["id"] == 7 and event["start_utc"].endswith("Z") and event["start_local_iso"].endswith("+00:00")
    level = event["levels"]["P1"]
    assert level["LAeq_dB"] == pytest.approx(67.403627) and level["coarse_resolution"] is False
    spectrum = level["spectra"]["LZeq"]
    assert spectrum["unit"] == "dB" and spectrum["labels"] == ["63Hz", "1000Hz"] and spectrum["bands_hz"] == [63, 1000]
    assert spectrum["levels_dB"][0] == pytest.approx(57.403627)
    assert event["levels"]["P2"]["LAeq_dB"] is None and event["levels"]["P2"]["state"] == "absent"
    assert document["readme"]["units"].startswith("All levels are dB re 20")


def test_json_sibling_never_overwrites_the_input_workspace(tmp_path):
    path, _ = workspace(tmp_path)
    before = path.read_text(encoding="utf-8")
    output = export_annotations(path, tmp_path / "workspace.csv")      # would map to workspace.json
    assert path.read_text(encoding="utf-8") == before
    assert (tmp_path / "workspace.nsa-annotations.json").exists() and output.exists()


def test_markers_carry_position_utc_and_levels(tmp_path):
    path, payload = workspace(tmp_path)
    payload["appState"]["markers"]["byId"]["1"].update({"timestamp": BASE + 1000, "positionId": "P1"})
    path.write_text(json.dumps(payload), encoding="utf-8")
    output = export_annotations(path)
    marker = read_export_section(output, "MARKERS").loc[0]
    assert marker["id"] == 1 and marker["note"] == "Marker"
    assert marker["position"] == "P1"
    assert marker["timestamp"] == "2023-11-14 22:13:21.000"
    assert marker["timestamp_utc"] == "2023-11-14T22:13:21.000Z"
    assert marker["timestamp_local_iso"] == "2023-11-14T22:13:21.000+00:00"
    assert marker["P1__LAeq_dB"] == pytest.approx(67.403627)
    assert marker["P1__LAFmax_dB"] == 75
    assert marker["P1__resolution"] == "log"
    assert pd.isna(marker["P2__LAeq_dB"])
    # Existing field survives; round trip restores the position.
    assert json.loads(marker["metrics"]) == {"P1": {"LAeq": 60}}
    assert load_annotation_input(output)["appState"]["markers"]["byId"]["1"]["positionId"] == "P1"
    entry = sidecar(output)["markers"][0]
    assert entry["position"] == "P1" and entry["levels"]["P1"]["LAeq_dB"] == pytest.approx(67.403627)
    assert entry["levels"]["P1"]["window_s"] == 10


def test_marker_without_position_has_blank_position(tmp_path):
    path, _ = workspace(tmp_path)
    marker = read_export_section(export_annotations(path), "MARKERS").loc[0]
    assert marker["position"] == "" and marker["timestamp_utc"].endswith("Z")


def test_marker_at_coarse_resolution_uses_containing_sample_and_is_flagged(tmp_path):
    path, payload = workspace(tmp_path, include_overview=True)
    (tmp_path / "P1_log.csv").unlink()
    payload["appState"]["markers"]["byId"]["1"]["timestamp"] = BASE + 10_000
    path.write_text(json.dumps(payload), encoding="utf-8")
    output = export_annotations(path)
    marker = read_export_section(output, "MARKERS").loc[0]
    assert marker["P1__resolution"] == "overview"
    assert marker["P1__LAeq_dB"] == 65
    assert marker["P1__coarse"] == True  # noqa: E712
    assert pd.isna(marker["P1__LAFmax_dB"])
    level = sidecar(output)["markers"][0]["levels"]["P1"]
    assert level["coarse_resolution"] is True and "longer than the event" in level["coarse_resolution_reason"]
    assert level["window_s"] == 300


def test_region_coarse_flag_is_exported(tmp_path):
    path, payload = workspace(tmp_path, include_overview=True)
    (tmp_path / "P1_log.csv").unlink()
    path.write_text(json.dumps(payload), encoding="utf-8")
    output = export_annotations(path)
    regions = read_export_section(output, "REGIONS")
    assert regions.loc[0, "coarse_resolution"] == True  # noqa: E712
    assert "5-min" in regions.loc[0, "coarse_resolution_reason"]
    events = read_export_section(output, "EVENTS")
    assert events.loc[0, "P1__coarse"] == True  # noqa: E712


def agent_fields(status, **extra):
    return {"source": "agent", "status": status, "rationale": "Looks like a van", "confidence": 0.82,
            "agent": {"name": "yamnet", "runId": "r1"}, **extra}


def test_proposed_and_rejected_are_excluded_by_default_and_rejected_only_in_json(tmp_path):
    path, payload = workspace(tmp_path)
    payload["appState"]["markers"]["byId"].update({
        "2": {"id": 2, "timestamp": BASE, "note": "prop marker", **agent_fields("proposed")},
        "3": {"id": 3, "timestamp": BASE, "note": "rej marker", **agent_fields("rejected")}})
    payload["appState"]["markers"]["allIds"] += [2, 3]
    add_regions(path, payload, {8: agent_fields("proposed"), 9: agent_fields("rejected"), 10: agent_fields("accepted")})
    output = export_annotations(path)
    for section in ("REGIONS", "EVENTS"):
        assert list(read_export_section(output, section)["id"]) == [7, 10], section
    assert set(read_export_section(output, "OVERALL")["region_id"]) == {7, 10}
    assert set(read_export_section(output, "SPECTRAL")["region_id"]) == {7, 10}
    assert list(read_export_section(output, "MARKERS")["id"]) == [1]
    accepted = read_export_section(output, "EVENTS").set_index("id").loc[10]
    assert accepted["source"] == "agent" and accepted["status"] == "accepted" and accepted["confidence"] == pytest.approx(0.82)
    document = sidecar(output)
    assert [event["id"] for event in document["events"]] == [7, 9, 10]
    rejected = next(event for event in document["events"] if event["id"] == 9)
    assert rejected["status"] == "rejected" and "rejected" in rejected["flagged"]
    assert rejected["agent"] == {"name": "yamnet", "runId": "r1"} and rejected["rationale"] == "Looks like a van"
    assert [marker["id"] for marker in document["markers"]] == [1, 3]
    assert "flagged" in document["markers"][1]


def test_include_proposed_adds_proposed_but_rejected_stay_json_only(tmp_path):
    path, payload = workspace(tmp_path)
    add_regions(path, payload, {8: agent_fields("proposed"), 9: agent_fields("rejected")})
    output = export_annotations(path, include_proposed=True)
    events = read_export_section(output, "EVENTS")
    assert list(events["id"]) == [7, 8]
    assert events.set_index("id").loc[8, "status"] == "proposed"
    assert read_export_section(output, "REGIONS").set_index("id").loc[8, "rationale"] == "Looks like a van"
    assert [event["id"] for event in sidecar(output)["events"]] == [7, 8, 9]
    assert "INCLUDED" in read_export_section(output, "README").set_index("key").loc["suggestions", "value"]


def test_proposed_region_does_not_remove_background_context_unless_included(tmp_path):
    path, payload = workspace(tmp_path)
    frame([30] * 100 + [60] * 10 + [30] * 100 + [90] * 10 + [30] * 100).to_csv(tmp_path / "P1_log.csv", index=False)
    payload["appState"]["regions"]["byId"]["7"]["areas"] = areas(100, 110)
    add_regions(path, payload, {8: agent_fields("proposed")})
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["appState"]["regions"]["byId"]["8"]["areas"] = areas(210, 220)
    path.write_text(json.dumps(payload), encoding="utf-8")

    def background(**options):
        out = export_annotations(path, tmp_path / f"bg{len(options)}.csv", background_window_s=120, **options)
        table = read_export_section(out, "OVERALL")
        return table.loc[(table.region_id == 7) & (table.meter == "P1"), "background_LAeq_dB"].iloc[0]

    # Unreviewed, the 90 dB event is still ordinary background; once included it is excluded from context.
    assert background() > background(include_proposed=True) + 5


def test_cli_include_proposed_flag(tmp_path, capsys):
    path, payload = workspace(tmp_path)
    add_regions(path, payload, {8: agent_fields("proposed")})
    out = tmp_path / "cli.csv"
    assert main([str(path), "--output", str(out)]) == 0
    assert list(read_export_section(out, "EVENTS")["id"]) == [7]
    assert main([str(path), "--output", str(out), "--include-proposed"]) == 0
    assert list(read_export_section(out, "EVENTS")["id"]) == [7, 8]


def test_source_read_failure_reaches_every_affected_row(tmp_path):
    path, payload = workspace(tmp_path)
    (tmp_path / "P1_log.csv").write_text("", encoding="utf-8")           # unreadable source
    payload["appState"]["markers"]["byId"]["1"]["positionId"] = "P1"
    path.write_text(json.dumps(payload), encoding="utf-8")
    output = export_annotations(path)
    overall = read_export_section(output, "OVERALL")
    p1 = overall.loc[overall.meter == "P1"].iloc[0]
    assert "Source read failed (P1_log.csv)" in p1["missing_reasons"]
    spectral = read_export_section(output, "SPECTRAL")
    assert all("Source read failed" in text for text in spectral.loc[spectral.meter == "P1", "missing_reasons"])
    assert "Source read failed" in read_export_section(output, "REGIONS").loc[0, "missing_reasons"]
    assert "P1: Source read failed" in read_export_section(output, "EVENTS").loc[0, "missing_reasons"]
    assert "P1: Source read failed" in read_export_section(output, "MARKERS").loc[0, "missing_reasons"]
    document = sidecar(output)
    assert any("Source read failed" in reason for reason in document["events"][0]["levels"]["P1"]["missing_reasons"])
    assert any("Source read failed" in reason for reason in document["markers"][0]["levels"]["P1"]["missing_reasons"])
    # P2 never had a source: it is not blamed on a read failure.
    assert "Source read failed" not in "".join(overall.loc[overall.meter == "P2", "missing_reasons"])
    assert read_export_section(output, "NOTES").set_index("key").index.str.startswith("source_error:P1").any()


def test_chart_offset_applies_to_marker_window(tmp_path):
    path, payload = workspace(tmp_path)
    payload["appState"]["view"]["positionChartOffsets"] = {"P1": 60_000}
    payload["appState"]["markers"]["byId"]["1"]["timestamp"] = BASE + 60_000 + 1000      # source time BASE+1 s
    payload["appState"]["regions"]["byId"]["7"]["areas"] = areas(60, 62)
    path.write_text(json.dumps(payload), encoding="utf-8")
    marker = read_export_section(export_annotations(path), "MARKERS").loc[0]
    assert marker["P1__LAeq_dB"] == pytest.approx(67.403627)
    assert load_annotation_input(path)["appState"]["view"] is not None
