"""Sectioned annotation CSV IO and bounded full-resolution Python export.

Run ``python -m noise_survey_analysis.export.annotations workspace.json``.
REGIONS is the importable annotation table; metric sections are independent
tables. csv.reader handles quoted newlines before section markers are examined.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import io
import json
import math
from pathlib import Path
import re
import tempfile
from typing import Any

import pandas as pd

from ..core.annotation_metrics import (MetricResult, PreparedMeterData, SPECTRAL_COLUMN,
                                       background_intervals, compute_region_metrics,
                                       prepare_meter_data, spectral_provenance, union_intervals)
from ..core.annotation_windows import iter_source_windows
from ..core.annotation_workspace import DEFAULT_CATEGORIES, migrate_workspace

SECTIONS = ("README", "REGIONS", "EVENTS", "OVERALL", "SPECTRAL", "MARKERS", "NOTES")
FORMAT_VERSION = 2
JSON_SCHEMA = "nsa-annotations/1"
DEFAULT_TIMEZONE = "Europe/London"
COVERAGE_TOLERANCE = 1e-6
MARKER_HALF_WINDOW_S = 5.0
UNITS = "dB re 20 µPa"
# Agent suggestion lifecycle. Absent status means an ordinary user annotation.
EXCLUDED_BY_DEFAULT = ("proposed", "rejected")


def _records(path: str | Path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.reader(handle)


def read_export_section(path: str | Path, section: str) -> pd.DataFrame:
    """Read one table, stopping at its first blank record or next marker.

    Marker-like text inside quoted notes remains part of its CSV record. Values
    retain standard pandas type inference; empty sections return empty frames.
    Legacy unsectioned annotation CSV is exposed as REGIONS for convenience.
    """
    section = section.upper().strip("[]")
    active = False
    rows = []
    found_marker = False
    legacy = []
    for row in _records(path):
        is_marker = len(row) == 1 and row[0].strip().startswith("[") and row[0].strip().endswith("]")
        if is_marker:
            found_marker = True
            if active:
                break
            active = row[0].strip() == f"[{section}]"
            continue
        if active:
            if not row or not any(value.strip() for value in row):
                break
            rows.append(row)
        elif not found_marker:
            legacy.append(row)
    if not rows and not found_marker and section == "REGIONS":
        rows = [row for row in legacy if row and row[0] != "NSA annotations export"]
    if not rows:
        return pd.DataFrame()
    stream = io.StringIO()
    csv.writer(stream, lineterminator="\n").writerows(rows)
    stream.seek(0)
    semantic_text = ("note", "category", "category_label", "categoryId", "origin_meter", "positionId", "position_id",
                     "meter", "colour", "color", "state", "parameter", "data_resolution", "key", "value",
                     "position", "source", "status", "rationale", "agent", "timezone", "coarse_resolution_reason", "missing_reasons")
    # Numeric-looking notes and meter IDs are still text. Leave metric columns
    # inferable so the public helper remains convenient for pandas/Excel work.
    table = pd.read_csv(stream, keep_default_na=False, dtype={name: str for name in semantic_text})
    numeric = {"duration_s", "chart_offset_ms", "sample_interval_s", "coverage", "context_duration_s", "confidence"}
    for name in table.columns:
        if name in numeric or name.endswith("_dB") or name.endswith("__coverage") or re.fullmatch(r"\d+(?:\.\d+)?k?Hz", name):
            table[name] = pd.to_numeric(table[name], errors="coerce")
    return table


def _metadata(path: Path) -> dict:
    for row in _records(path):
        if len(row) == 1 and row[0].startswith("["):
            break
        if row and row[0] == "metadata" and len(row) > 1:
            return json.loads(row[1])
    return {}


def _timestamp_ms(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        stamp = pd.Timestamp(text)
        stamp = stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")
        return float(stamp.value / 1e6)


def _json_value(value: Any, default: Any):
    if not isinstance(value, str):
        return value if value is not None else default
    if not value.strip():
        return default
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def _provenance_from_row(row: dict) -> dict:
    """Agent-suggestion fields written by this exporter, restored only when non-blank."""
    result: dict[str, Any] = {}
    for key in ("source", "status", "rationale"):
        if row.get(key):
            result[key] = row[key]
    confidence = row.get("confidence")
    if confidence not in (None, ""):
        try:
            result["confidence"] = float(confidence)
        except (TypeError, ValueError):
            pass
    if row.get("agent"):
        result["agent"] = {"name": row["agent"]}
    return result


def load_annotation_input(input_path: str | Path | dict) -> dict:
    """Normalize workspace or annotation CSV into the explicit v2 workspace."""
    if isinstance(input_path, dict):
        return migrate_workspace(input_path)[0]
    path = Path(input_path)
    if path.suffix.lower() == ".json":
        return migrate_workspace(json.loads(path.read_text(encoding="utf-8-sig")))[0]
    metadata = _metadata(path)
    sectioned = any(row == ["[REGIONS]"] for row in _records(path))
    table = read_export_section(path, "REGIONS")
    meters = metadata.get("meters", [])
    meter_ids = [entry["id"] if isinstance(entry, dict) else str(entry) for entry in meters]
    if sectioned:
        annotation_fields = {"id", "category", "category_label", "category_ids", "note", "colour", "start", "end", "duration_s",
                             "origin_meter", "areas", "merge_sources", "merge_categories", "chart_offset_ms", "source_start", "source_end", "source_areas",
                             "data_resolution", "sample_interval_s", "coverage", "LAeq_dB", "LAFmax_dB",
                             "start_local", "end_local", "source_start_local", "source_end_local",
                             "start_utc", "end_utc", "timezone", "source", "status", "confidence", "rationale", "agent",
                             "coarse_resolution", "coarse_resolution_reason", "missing_reasons"}
        for column in table:
            if column not in annotation_fields and table[column].isin(("present", "absent", "unchecked")).any() and column not in meter_ids:
                meter_ids.append(column)
    regions, markers = [], []
    for row in table.to_dict("records"):
        kind = row.get("type", "region")
        if kind == "marker":
            markers.append({"id": row.get("id"), "timestamp": _timestamp_ms(row.get("start_utc") or row.get("start")),
                            "note": row.get("note", ""), "color": row.get("color") or None})
            continue
        origin = str(row.get("origin_meter") or row.get("positionId") or row.get("position_id") or "")
        if not origin:
            continue
        areas = _json_value(row.get("areas") or row.get("areas_json"), [])
        if isinstance(areas, dict):
            areas = [areas]
        areas = [{"start": _timestamp_ms(area.get("start", area.get("startUtc"))),
                  "end": _timestamp_ms(area.get("end", area.get("endUtc")))} for area in areas]
        if not areas:
            areas = [{"start": _timestamp_ms(row.get("start") or row.get("start_utc")),
                      "end": _timestamp_ms(row.get("end") or row.get("end_utc"))}]
        if origin not in meter_ids:
            meter_ids.append(origin)
        states = {meter: row.get(meter, "unchecked") for meter in meter_ids}
        states[origin] = "present"
        region = {"id": row.get("id"), "positionId": origin, "areas": areas,
                  "note": row.get("note", ""), "color": row.get("colour") or row.get("color") or None,
                  "categoryId": row.get("category") or row.get("categoryId") or "other", "meterStates": states,
                  "categoryIds": _json_value(row.get("category_ids"), None),
                  "mergeSources": _json_value(row.get("merge_sources"), None),
                  "mergeCategories": _json_value(row.get("merge_categories"), None)}
        region.update(_provenance_from_row(row))
        regions.append(region)
    marker_table = read_export_section(path, "MARKERS")
    for row in marker_table.to_dict("records"):
        marker = {"id": row.get("id"), "timestamp": _timestamp_ms(row.get("timestamp") or row.get("start")),
                  "note": row.get("note", ""), "color": row.get("colour") or row.get("color") or None,
                  "metrics": _json_value(row.get("metrics") or row.get("metrics_json"), {})}
        if row.get("position"):
            marker["positionId"] = row["position"]
        marker.update(_provenance_from_row(row))
        markers.append(marker)
    categories = metadata.get("categories") or [*DEFAULT_CATEGORIES, *[
        {"id": row.get("category"), "label": row.get("category_label") or row.get("category"), "color": "#1e88e5"}
        for row in table.to_dict("records") if row.get("category")]]
    version = metadata.get("version", 2 if sectioned else 1)
    workspace = {"version": version, "sourceConfigs": metadata.get("sourceConfigs", []),
                 "appState": {"view": {"availablePositions": meter_ids,
                     "positionChartOffsets": metadata.get("chart_offsets_ms", {
                         meter: float(value) * 1000 for meter, value in metadata.get("chart_offsets_seconds", {}).items()}),
                     "positionDisplayTitles": {entry["id"]: entry.get("title", entry["id"]) for entry in meters if isinstance(entry, dict)}},
                     "regions": {"byId": {str(i): region for i, region in enumerate(regions)},
                                 "allIds": list(range(len(regions))), "categories": categories},
                     "markers": {"byId": {str(marker.get("id", index + 1)): marker for index, marker in enumerate(markers)},
                                 "allIds": [marker.get("id", index + 1) for index, marker in enumerate(markers)]}}}
    return migrate_workspace(workspace)[0]


def _source_configs(configs: list | dict | str | Path | None, workspace: dict, base: Path) -> list[dict]:
    """Resolve portable configs without discarding source options or missing paths."""
    if isinstance(configs, (str, Path)):
        path = Path(configs).resolve()
        base = path.parent
        configs = json.loads(path.read_text(encoding="utf-8-sig"))
    if configs is None:
        configs = workspace.get("sourceConfigs", [])
    if isinstance(configs, dict):
        base = Path(configs.get("config_base_path") or base)
        configs = configs.get("sourceConfigs") or configs.get("sources", [])
    normalized = []
    for source in configs:
        if not source.get("enabled", True):
            continue
        source = dict(source)
        source["position_name"] = source.get("position_name") or source.get("position") or source.get("positionId")
        paths = source.get("file_paths") or ([source["path"]] if source.get("path") else [])
        source["file_paths"] = [str((base / path).resolve()) if not Path(path).is_absolute() else str(Path(path)) for path in paths]
        normalized.append(source)
    return normalized


def _config_offsets(configs) -> dict[str, float]:
    """Config setup uses seconds; the runtime/workspace store uses milliseconds."""
    if isinstance(configs, (str, Path)):
        configs = json.loads(Path(configs).read_text(encoding="utf-8-sig"))
    if not isinstance(configs, dict):
        return {}
    result = {}
    for meter, options in configs.get("positions", {}).items():
        if isinstance(options, dict) and "chart_offset_seconds" in options:
            result[meter] = float(options["chart_offset_seconds"]) * 1000
    return result


def _regions(workspace: dict) -> list[dict]:
    state = workspace["appState"]["regions"]
    return [state["byId"].get(str(key), state["byId"].get(key)) for key in state["allIds"]]


def _iso(milliseconds: float) -> str:
    return pd.Timestamp(milliseconds, unit="ms", tz="UTC").strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _local_iso(milliseconds: float, zone: str) -> str:
    """Naive wall-clock time in `zone`: the time basis of Svantek/NTi/Sentry log files."""
    return pd.Timestamp(milliseconds, unit="ms", tz="UTC").tz_convert(zone).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _meter_zone(sources: list[dict], meter: str) -> str:
    for source in sources:
        if source.get("position_name") == meter and source.get("timezone"):
            return source["timezone"]
    return DEFAULT_TIMEZONE


def _utc_iso(milliseconds: float) -> str:
    """ISO-8601 UTC instant with a Z suffix (unambiguous for LLM readers)."""
    return pd.Timestamp(milliseconds, unit="ms", tz="UTC").strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _local_offset_iso(milliseconds: float, zone: str) -> str:
    """ISO-8601 local wall-clock time carrying its UTC offset, e.g. 2026-06-01T11:00:00.000+01:00."""
    stamp = pd.Timestamp(milliseconds, unit="ms", tz="UTC").tz_convert(zone)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + stamp.strftime("%z")[:3] + ":" + stamp.strftime("%z")[3:]


def _status(item: dict) -> str:
    status = item.get("status")
    return status if status in ("proposed", "accepted", "rejected") else ""


def _confidence(item: dict):
    value = item.get("confidence")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def _agent_name(item: dict) -> str:
    agent = item.get("agent")
    return str(agent.get("name") or "") if isinstance(agent, dict) else str(agent or "")


def _provenance(item: dict) -> dict:
    return {"source": item.get("source") or "user", "status": _status(item), "confidence": _confidence(item),
            "rationale": item.get("rationale") or "", "agent": _agent_name(item)}


def _flag(value: bool | None) -> str:
    return "" if value is None else "true" if value else "false"


def _json_safe(value):
    """Recursively replace non-finite numbers with null so the file is strict JSON."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, float):
        return round(value, 6) if math.isfinite(value) else None
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        return _json_safe(value.item())
    return value


def annotations_json_path(csv_path: str | Path) -> Path:
    """Sibling JSON written beside the CSV (`name.csv` -> `name.json`)."""
    return Path(csv_path).with_suffix(".json")


def _value(value):
    if value is None or isinstance(value, float) and not math.isfinite(value):
        return ""
    if isinstance(value, float):
        return round(value, 6)
    return value


def _write_section(writer, name: str, columns: list[str], rows: list[dict]):
    writer.writerow([f"[{name}]"])
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_value(row.get(column)) for column in columns])
    writer.writerow([])


def _spectral_provenance(frame: pd.DataFrame | PreparedMeterData, parameter: str,
                         areas, offset_ms: float) -> tuple[float, float | None]:
    data = frame if isinstance(frame, PreparedMeterData) else prepare_meter_data(frame)
    return spectral_provenance(data, parameter, areas, offset_ms)


def _best_resolution(candidates: dict[str, tuple[Any, float]]) -> str | None:
    """Complete log first, then usable overview, then labelled partial log."""
    if "log" in candidates and candidates["log"][1] >= 1 - COVERAGE_TOLERANCE:
        return "log"
    if "overview" in candidates:
        return "overview"
    return "log" if "log" in candidates else None


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(text)
        except BaseException:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _config_dict(configs) -> dict:
    if isinstance(configs, (str, Path)):
        try:
            configs = json.loads(Path(configs).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return {}
    return configs if isinstance(configs, dict) else {}


def _job_label(workspace: dict, configs) -> str:
    config = _config_dict(configs)
    for key in ("job", "job_name", "job_number"):
        value = workspace.get(key) or config.get(key)
        if value:
            return str(value)
    base = config.get("config_base_path")
    if base:
        folder = Path(str(base))
        return folder.parent.name if re.fullmatch(r"\d+ Surveys", folder.name) and folder.parent.name else folder.name
    match = re.match(r"(\d{4,})", str(config.get("output_filename") or ""))
    return match.group(1) if match else ""


def _readme(workspace: dict, configs, meter_info: list[dict], exported: str, zone: str, background_window_s: float,
            min_context_s: float, include_all_resolutions: bool, include_proposed: bool) -> list[dict]:
    """Self-describing preamble for people and LLMs reading the CSV cold."""
    rows = [
        ("format", f"NSA annotations export, format={FORMAT_VERSION}; a sibling .json (schema {JSON_SCHEMA}) holds the same content nested."),
        ("job", _job_label(workspace, configs)),
        ("exported", exported),
        ("timezone", f"{zone}. *_utc columns are true UTC (ISO-8601 with Z). *_local_iso columns are local wall-clock time with a UTC offset "
                     "(BST = +01:00 in summer). Legacy start_local/end_local/source_*_local columns are naive local time as in the instrument log files."),
        ("units", f"All levels are {UNITS}. LAeq, LAFmax and LAF90 are A-weighted; spectral parameters keep their own weighting (e.g. LZeq). "
                  "Blank cell = not available (see missing_reasons)."),
        ("meters", f"{len(meter_info)} meter position(s); one column group per meter, prefixed with the meter id and a double underscore."),
    ]
    for info in meter_info:
        rows.append((f"meter.{info['id']}", f"title={info['title']}; chart_offset_s={info['chart_offset_s']:g} "
                     f"(display time = source time + offset; source_* columns remove it); timezone={info['timezone']}"))
    rows += [
        ("resolution_policy", "Per level, the best available resolution: complete 1 s (or finer) log first, otherwise 5-minute overview, otherwise a labelled "
                              "partial log. The resolution used is in data_resolution / {meter}__resolution. "
                              + ("Both resolutions are listed in OVERALL/SPECTRAL." if include_all_resolutions else "Only the best resolution is listed.")),
        ("coarse_resolution", "coarse=true means one data sample is longer than (or more than a third of) the event: the level is for the whole sample "
                              "interval, not for the event itself, and LAFmax is withheld. Treat such levels as an upper bound on context, not an event level."),
        ("background_method", f"Background = LA90 (duration-weighted 10th percentile) of the pooled {background_window_s:g} s before and after each event, "
                              f"excluding every event marked present at that meter; at least {min_context_s:g} s of usable context is needed. "
                              "diff_dB = event LAeq - background LA90. Overview data uses the logged LAF90 column where present (indicative)."),
        ("marker_levels", f"Marker LAeq/LAFmax use a +/-{MARKER_HALF_WINDOW_S:g} s window about the marker (per meter, after chart offset); at coarse "
                          "resolution the single sample containing the marker is used and {meter}__coarse is true."),
        ("suggestions", "source=agent items are suggestions. status=proposed (unreviewed) items are " +
                        ("INCLUDED in this file (include_proposed). " if include_proposed else "excluded from the CSV. ") +
                        "status=rejected items appear only in the JSON, flagged. Items with no status are the consultant's own."),
        ("read_failures", "If a meter's source file could not be read, every row for that meter says so in missing_reasons."),
        ("section.README", "This table."),
        ("section.REGIONS", "Importable annotation table, one row per region with geometry, per-meter present/absent/unchecked states and headline levels at the origin meter."),
        ("section.EVENTS", "Start here: one row per region with timing in UTC and local time and, per meter, state, LAeq, LAFmax, LAF90, background LA90, difference, resolution, coarse flag and coverage."),
        ("section.OVERALL", "Long-form broadband levels, one row per region and meter, with background context and missing_reasons."),
        ("section.SPECTRAL", "Long-form spectra, one row per region, meter and spectral parameter; band columns are centre frequencies in Hz, levels in dB."),
        ("section.MARKERS", "Point annotations with time, position and per-meter LAeq/LAFmax around the marker."),
        ("section.NOTES", "Method notes, source file list and chart offsets (key/value)."),
    ]
    return [{"key": key, "value": value} for key, value in rows]


def _marker_level(frames: dict[str, PreparedMeterData], stamp: float, meter: str, offset_ms: float) -> dict:
    """Levels around a marker from the already-prepared meter windows (no extra read).

    +/-MARKER_HALF_WINDOW_S about the marker; where one source sample is longer
    than that window the single sample containing the marker is used instead
    and flagged coarse (its LAeq is the whole interval, its LAFmax is withheld).
    """
    half_ms = MARKER_HALF_WINDOW_S * 1000
    results: dict[str, MetricResult] = {}
    windows: dict[str, float] = {}
    for resolution, data in frames.items():
        result = compute_region_metrics(data, [(stamp - half_ms, stamp + half_ms)], meter=meter,
                                        chart_offset_ms=offset_ms, resolution=resolution)
        windows[resolution] = MARKER_HALF_WINDOW_S * 2
        if result.coarse_resolution:
            result = compute_region_metrics(data, [(stamp - .5, stamp + .5)], meter=meter,
                                            chart_offset_ms=offset_ms, resolution=resolution)
            windows[resolution] = result.sample_interval_s or 0
        results[resolution] = result
    usable = {name: (result, result.coverage) for name, result in results.items() if result.LAeq_dB is not None}
    chosen = _best_resolution(usable)
    best = results[chosen] if chosen else results.get("log", results.get("overview"))
    if best is None:
        return {"data_resolution": "none", "sample_interval_s": None, "window_s": None, "coverage": 0.0,
                "LAeq_dB": None, "LAFmax_dB": None, "coarse_resolution": False, "coarse_resolution_reason": None,
                "missing_reasons": ["No source samples in requested windows"]}
    return {"data_resolution": best.data_resolution, "sample_interval_s": best.sample_interval_s,
            "window_s": windows.get(best.data_resolution), "coverage": best.coverage,
            "LAeq_dB": best.LAeq_dB, "LAFmax_dB": best.LAFmax_dB,
            "coarse_resolution": best.coarse_resolution, "coarse_resolution_reason": best.coarse_resolution_reason,
            "missing_reasons": list(best.missing_reasons)}


def export_annotations(input_path: str | Path | dict, output_path: str | Path | None = None,
                       source_configs=None, include_all_resolutions: bool = False,
                       background_window_s: float = 300, min_context_s: float = 60,
                       include_proposed: bool = False) -> Path:
    """Export best available metrics using complete source log windows.

    Overview fallback is explicit in every row. Broadband and each spectral
    parameter choose independently; requesting both resolutions is optional.

    A sibling ``<output>.json`` (schema ``nsa-annotations/1``) carries the same
    content nested for LLM readers. Agent suggestions with status ``proposed``
    are left out of the CSV (and JSON) unless ``include_proposed``; ``rejected``
    ones never appear in the CSV and appear in the JSON only, flagged.
    """
    workspace = load_annotation_input(input_path)
    base = Path(input_path).resolve().parent if not isinstance(input_path, dict) else Path.cwd()
    if output_path is None:
        if isinstance(input_path, dict):
            raise ValueError("output_path is required for an in-memory workspace")
        output_path = Path(input_path).with_suffix(".full-resolution.csv")
    output_path = Path(output_path).resolve()
    if not isinstance(input_path, dict) and output_path == Path(input_path).resolve():
        raise ValueError("Output must not overwrite annotation input")
    json_path = annotations_json_path(output_path)
    if not isinstance(input_path, dict) and json_path == Path(input_path).resolve():
        # `ws.json` -> `ws.csv` would otherwise overwrite the workspace with the sibling.
        json_path = output_path.with_name(output_path.stem + ".nsa-annotations.json")
    if not math.isfinite(background_window_s) or not math.isfinite(min_context_s) or background_window_s < 0 or min_context_s < 0:
        raise ValueError("Background window and minimum context must be finite and non-negative")
    sources = _source_configs(source_configs, workspace, base)
    state = workspace["appState"]
    regions = _regions(workspace)
    meters = list(dict.fromkeys([*state.get("view", {}).get("availablePositions", []),
                                *[source["position_name"] for source in sources if source.get("position_name")],
                                *[meter for region in regions for meter in region["meterStates"]]]))
    titles = state.get("view", {}).get("positionDisplayTitles", {})
    offsets = {**_config_offsets(source_configs), **state.get("view", {}).get("positionChartOffsets", {})}
    categories = state["regions"]["categories"]
    catalog = categories.get("byId", {}) if isinstance(categories, dict) else {entry["id"]: entry for entry in categories}
    overall, spectral, notes = [], [], []
    headline: dict[tuple, MetricResult] = {}
    bands: set[float] = set()
    parameters: set[str] = set()
    # Agent suggestions: unreviewed (proposed) regions must not shrink anyone's
    # background context, so only "pool" regions exclude time from it. Rejected
    # regions are still measured so the JSON can show what was declined.
    csv_regions = [r for r in regions if _status(r) not in EXCLUDED_BY_DEFAULT or (_status(r) == "proposed" and include_proposed)]
    pool = csv_regions
    csv_ids = {id(r) for r in csv_regions}
    work_regions = [r for r in regions if id(r) in csv_ids or _status(r) == "rejected"]
    markers_state = state.get("markers") or {}
    all_markers = markers_state if isinstance(markers_state, list) else markers_state.get("items", markers_state.get("markers", []))
    if not all_markers and isinstance(markers_state, dict) and "byId" in markers_state:
        all_markers = list(markers_state["byId"].values())
    all_markers = [m for m in all_markers if isinstance(m, dict)]
    csv_markers = [m for m in all_markers if _status(m) not in EXCLUDED_BY_DEFAULT or (_status(m) == "proposed" and include_proposed)]
    csv_marker_ids = {id(m) for m in csv_markers}
    work_markers = [m for m in all_markers if id(m) in csv_marker_ids or _status(m) == "rejected"]
    marker_times: dict[int, float] = {}
    for marker in work_markers:
        try:
            stamp = float(_timestamp_ms(marker.get("timestamp", marker.get("time"))))
        except (TypeError, ValueError):
            continue
        if math.isfinite(stamp):
            marker_times[id(marker)] = stamp
    marker_levels: dict[tuple[int, str], dict] = {}
    spectra_json: dict[tuple[str, str], dict] = defaultdict(dict)
    read_errors: dict[str, list[str]] = defaultdict(list)
    for meter in meters:
        offset_ms = float(offsets.get(meter, 0) or 0)
        contexts = {str(region["id"]): background_intervals(region, pool, meter, background_window_s) for region in work_regions}
        marker_windows = [(stamp - MARKER_HALF_WINDOW_S * 1000, stamp + MARKER_HALF_WINDOW_S * 1000) for stamp in marker_times.values()]
        windows = union_intervals([area for region in work_regions for area in [*(region.get("areas") or [region]), *contexts[str(region["id"])]]]
                                  + marker_windows)
        source_windows = [(start - offset_ms, end - offset_ms) for start, end in windows]
        # Only this meter's requested windows survive each bounded source scan.
        chunks: dict[str, list[pd.DataFrame]] = defaultdict(list)
        intervals: dict[str, list[float]] = defaultdict(list)
        for source in sources:
            if source.get("position_name") != meter or source.get("parser_type") in ("audio", "wav"):
                continue
            for path in source["file_paths"]:
                if Path(path).is_dir():
                    continue
                try:
                    for chunk in iter_source_windows(path, source_windows, options=source):
                        # Preserve both bounded window sets so each parameter
                        # can choose its own best available resolution.
                        for column in chunk.frame.columns:
                            match = SPECTRAL_COLUMN.match(str(column))
                            if match:
                                parameter, frequency, kilo = match.groups()
                                parameters.add(parameter)
                                bands.add(float(frequency) * (1000 if kilo else 1))
                        chunks[chunk.resolution].append(chunk.frame)
                        if chunk.sample_interval_s:
                            intervals[chunk.resolution].append(chunk.sample_interval_s)
                except (OSError, ValueError, ImportError) as error:
                    notes.append({"key": f"source_error:{meter}:{Path(path).name}", "value": str(error)})
                    # Every row for this meter inherits the failure, so a reader of
                    # one row cannot mistake missing levels for a quiet period.
                    read_errors[meter].append(f"Source read failed ({Path(path).name}): {error}")
        frames = {}
        for resolution in tuple(chunks):
            # Broadband and spectral NTi files share timestamps; combine their
            # columns without counting duplicate timestamps or losing spectra.
            combined = pd.concat(chunks.pop(resolution), ignore_index=True).sort_values("Datetime")
            grouped = combined.groupby("Datetime", sort=True).first().reset_index()
            # Release source chunks and the joined table before preparing the
            # numeric arrays, rather than retaining three copies during setup.
            del combined
            grouped.attrs["sample_interval_s"] = max(intervals[resolution]) if intervals[resolution] else None
            # The retained window set is prepared once for all this meter's
            # regions. No per-region sorting/copying or whole-file cache.
            frames[resolution] = prepare_meter_data(grouped)
            del grouped
        del chunks
        for marker in work_markers:
            stamp = marker_times.get(id(marker))
            if stamp is None:
                continue
            marker_levels[(id(marker), meter)] = _marker_level(frames, stamp, meter, offset_ms)
        for region in work_regions:
            results = {resolution: compute_region_metrics(frame, region.get("areas") or [region],
                    meter=meter, chart_offset_ms=offset_ms, resolution=resolution,
                    context_areas=contexts[str(region["id"])], min_context_s=min_context_s)
                       for resolution, frame in frames.items()}
            usable = {name: (result, result.coverage) for name, result in results.items() if result.LAeq_dB is not None}
            best_name = _best_resolution(usable)
            best = results[best_name] if best_name else results.get("log", results.get("overview"))
            if best is None:
                best = MetricResult("none", missing_reasons=["No source samples in requested windows"])
            headline[(str(region["id"]), meter)] = best
            common = {"region_id": region["id"], "category": region["categoryId"], "meter": meter,
                      "state": region["meterStates"].get(meter, "unchecked")}
            overall_results = [results[name] for name in ("log", "overview") if name in results] if include_all_resolutions else [best]
            for result in overall_results or [best]:
                values = result.as_dict()
                values.pop("spectra")
                values["missing_reasons"] = "; ".join(result.missing_reasons)
                values["background_dB"] = result.background_LA90_dB
                overall.append({**common, **values})
            meter_parameters = {parameter for result in results.values() for parameter in result.spectra}
            for parameter in sorted(meter_parameters):
                spectral_candidates = {}
                for resolution, result in results.items():
                    spectrum = result.spectra.get(parameter, {})
                    if not any(level is not None and math.isfinite(level) for level in spectrum.values()):
                        continue
                    coverage, period = _spectral_provenance(frames[resolution], parameter, region.get("areas") or [region], offset_ms)
                    spectral_candidates[resolution] = ((spectrum, period), coverage)
                best_spectral = _best_resolution(spectral_candidates)
                if best_spectral:
                    (best_spectrum, best_period), best_coverage = spectral_candidates[best_spectral]
                    ordered = sorted(best_spectrum.items())
                    spectra_json[(str(region["id"]), meter)][parameter] = {
                        "unit": "dB", "data_resolution": best_spectral, "sample_interval_s": best_period,
                        "coverage": best_coverage, "bands_hz": [frequency for frequency, _ in ordered],
                        "labels": [f"{frequency:g}Hz" for frequency, _ in ordered],
                        "levels_dB": [level for _, level in ordered]}
                selected = [name for name in ("log", "overview") if name in spectral_candidates] if include_all_resolutions else ([best_spectral] if best_spectral else [])
                for resolution in selected:
                    (spectrum, period), coverage = spectral_candidates[resolution]
                    spectral.append({**common, "parameter": parameter, "data_resolution": resolution,
                                     "sample_interval_s": period, "coverage": coverage,
                                     "missing_reasons": "Spectral area has incomplete finite-sample coverage" if coverage < 1 - COVERAGE_TOLERANCE else "",
                                     **{f"{frequency:g}Hz": level for frequency, level in spectrum.items()}})
        del frames
    # Missing-meter comparisons are useful evidence too. Complete the spectral
    # matrix after all meters have revealed their available parameter names.
    existing_spectra = {(str(row["region_id"]), row["meter"], row["parameter"]) for row in spectral}
    for row in overall:
        for parameter in sorted(parameters):
            key = (str(row["region_id"]), row["meter"], parameter)
            if key not in existing_spectra:
                spectral.append({**{name: row[name] for name in ("region_id", "category", "meter", "state")},
                                 "data_resolution": "none", "sample_interval_s": None, "coverage": 0,
                                 "parameter": parameter, "missing_reasons": "Spectral parameter unavailable at this meter/resolution"})
                existing_spectra.add(key)
    spectral.sort(key=lambda row: (str(row["region_id"]), meters.index(row["meter"]), row["parameter"], row["data_resolution"]))

    def with_errors(text: str, meter: str) -> str:
        """Append this meter's source-read failures to a missing_reasons cell."""
        return "; ".join([part for part in (text, *read_errors.get(meter, [])) if part])

    for row in (*overall, *spectral):
        if row["meter"] in read_errors:
            row["missing_reasons"] = with_errors(row.get("missing_reasons", ""), row["meter"])
    region_rows, event_rows, event_json = [], [], []
    default_zone = next((source["timezone"] for source in sources if source.get("timezone")), DEFAULT_TIMEZONE)
    for region in work_regions:
        origin = region["positionId"]
        offset_ms = float(offsets.get(origin, 0) or 0)
        areas = union_intervals(region.get("areas") or [region])
        zone = _meter_zone(sources, origin)
        result = headline.get((str(region["id"]), origin), MetricResult("none"))
        label = catalog.get(region["categoryId"], {}).get("label", region["categoryId"])
        provenance = _provenance(region)
        duration_s = sum(end - start for start, end in areas) / 1000
        event = {"id": region["id"], "category_label": label, "note": region.get("note", ""), **provenance,
                 "start_utc": _utc_iso(areas[0][0]), "end_utc": _utc_iso(areas[-1][1]),
                 "start_local_iso": _local_offset_iso(areas[0][0], zone), "end_local_iso": _local_offset_iso(areas[-1][1], zone),
                 "timezone": zone, "duration_s": duration_s, "origin_meter": origin}
        reasons, levels = [], {}
        for meter in meters:
            best = headline.get((str(region["id"]), meter), MetricResult("none", missing_reasons=["No source samples in requested windows"]))
            state_value = region["meterStates"].get(meter, "unchecked")
            event.update({f"{meter}__state": state_value, f"{meter}__LAeq_dB": best.LAeq_dB, f"{meter}__LAFmax_dB": best.LAFmax_dB,
                          f"{meter}__LAF90_dB": best.LAF90_dB, f"{meter}__bg_LA90_dB": best.background_LA90_dB,
                          f"{meter}__diff_dB": best.diff_from_background_dB, f"{meter}__resolution": best.data_resolution,
                          f"{meter}__coarse": _flag(best.coarse_resolution), f"{meter}__coverage": best.coverage})
            meter_reasons = [*best.missing_reasons, *read_errors.get(meter, [])]
            if meter == origin or state_value == "present" or meter in read_errors:
                reasons += [f"{meter}: {reason}" for reason in meter_reasons]
            levels[meter] = {"state": state_value, "data_resolution": best.data_resolution, "sample_interval_s": best.sample_interval_s,
                             "coverage": best.coverage, "LAeq_dB": best.LAeq_dB, "LAFmax_dB": best.LAFmax_dB, "LAF90_dB": best.LAF90_dB,
                             "background_LA90_dB": best.background_LA90_dB, "background_LAeq_dB": best.background_LAeq_dB,
                             "diff_dB": best.diff_from_background_dB, "context_duration_s": best.context_duration_s,
                             "percentile_method": best.percentile_method, "coarse_resolution": best.coarse_resolution,
                             "coarse_resolution_reason": best.coarse_resolution_reason, "missing_reasons": meter_reasons,
                             "spectra": spectra_json.get((str(region["id"]), meter), {})}
        event["missing_reasons"] = "; ".join(reasons)
        if id(region) in csv_ids:
            event_rows.append(event)
        if id(region) in csv_ids or _status(region) == "rejected":
            record = {**{key: value for key, value in event.items() if "__" not in key and key != "missing_reasons"},
                      "areas": [{"start_utc": _utc_iso(start), "end_utc": _utc_iso(end)} for start, end in areas],
                      "meter_states": dict(region["meterStates"]), "levels": levels}
            if isinstance(region.get("agent"), dict):
                record["agent"] = region["agent"]
            if _status(region) == "rejected":
                record["flagged"] = "rejected suggestion: do not treat as a real event"
            event_json.append(record)
        if id(region) not in csv_ids:
            continue
        region_rows.append({"id": region["id"], "category": region["categoryId"], "category_ids": json.dumps(region["categoryIds"]),
            "category_label": catalog.get(region["categoryId"], {}).get("label", region["categoryId"]),
            "note": region.get("note", ""), "colour": region.get("color"),
            "start": _iso(areas[0][0]), "end": _iso(areas[-1][1]),
            "duration_s": sum(end - start for start, end in areas) / 1000,
            "origin_meter": origin, "areas": json.dumps([{"start": start, "end": end} for start, end in areas]),
            "merge_sources": json.dumps(region["mergeSources"]) if region.get("mergeSources") else "",
            "merge_categories": json.dumps(region["mergeCategories"]) if region.get("mergeCategories") else "",
            **{meter: region["meterStates"].get(meter, "unchecked") for meter in meters},
            "chart_offset_ms": offset_ms, "source_start": _iso(areas[0][0] - offset_ms),
            "source_end": _iso(areas[-1][1] - offset_ms),
            "start_local": _local_iso(areas[0][0], zone), "end_local": _local_iso(areas[-1][1], zone),
            "source_start_local": _local_iso(areas[0][0] - offset_ms, zone), "source_end_local": _local_iso(areas[-1][1] - offset_ms, zone),
            "source_areas": json.dumps([{"start": start - offset_ms, "end": end - offset_ms} for start, end in areas]),
            "data_resolution": result.data_resolution, "sample_interval_s": result.sample_interval_s,
            "coverage": result.coverage, "LAeq_dB": result.LAeq_dB, "LAFmax_dB": result.LAFmax_dB,
            "start_utc": event["start_utc"], "end_utc": event["end_utc"], "timezone": zone, "source": provenance["source"],
            "status": provenance["status"], "confidence": provenance["confidence"], "rationale": provenance["rationale"],
            "agent": provenance["agent"], "coarse_resolution": _flag(result.coarse_resolution),
            "coarse_resolution_reason": result.coarse_resolution_reason or "",
            "missing_reasons": with_errors("; ".join(result.missing_reasons), origin)})
    exported = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    notes += [{"key": "exported", "value": exported}, {"key": "resolution_policy", "value": "Best available independently for overall levels and each spectral parameter: fully covered source log, otherwise usable overview, otherwise labelled partial log. Both available resolutions only when include_all_resolutions=true. Python reads complete source windows independently of viewport buffers."},
              {"key": "include_all_resolutions", "value": str(include_all_resolutions).lower()},
              {"key": "background_method", "value": f"Duration-weighted LA90 (inverse-CDF p10) of pooled {background_window_s:g}s before/after each area, excluding all regions present at the meter; minimum {min_context_s:g}s. LAeq reported for the identical usable context. Difference = region LAeq - context LA90."},
              {"key": "percentile_caveat", "value": "LAF90 from overview or 1 s data is indicative. Where fast-level samples are unavailable, percentiles of LAeq (or interval LAF90) are estimates, not reconstructed fast-level statistics."},
              {"key": "colour", "value": "Blank colour means category default; nonblank colour is a per-region override."},
              {"key": "time_basis", "value": "Date-times are UTC except the *_local columns, which are naive local wall-clock time (BST in summer) in the source timezone (default Europe/London) and match the instrument log files; use source_start_local/source_end_local to look up log rows. Metric resolution is in data_resolution (log or overview); source times subtract target-meter chart offset. Half-open intervals, duration weighted, overlapping areas/context counted once; nominal sample intervals do not bridge gaps."},
              {"key": "sources", "value": json.dumps(sources)}, {"key": "chart_offsets_ms", "value": json.dumps(offsets)}]
    marker_rows, marker_json = [], []
    for marker in work_markers:
        stamp = marker_times.get(id(marker))
        zone = _meter_zone(sources, marker["positionId"]) if marker.get("positionId") else default_zone
        provenance = _provenance(marker)
        row = {"id": marker.get("id"), "timestamp": _iso(marker.get("timestamp", marker.get("time", 0))),
               "note": marker.get("note", ""), "colour": marker.get("color"),
               "metrics": json.dumps(marker.get("metrics", marker.get("metricsByPosition", {}))),
               "timestamp_utc": _utc_iso(stamp) if stamp is not None else "",
               "timestamp_local_iso": _local_offset_iso(stamp, zone) if stamp is not None else "",
               "timezone": zone, "position": marker.get("positionId") or "", **provenance}
        levels = {}
        reasons = []
        for meter in meters:
            level = marker_levels.get((id(marker), meter))
            if level is None:
                continue
            level = {**level, "missing_reasons": [*level["missing_reasons"], *read_errors.get(meter, [])]}
            levels[meter] = level
            row.update({f"{meter}__LAeq_dB": level["LAeq_dB"], f"{meter}__LAFmax_dB": level["LAFmax_dB"],
                        f"{meter}__resolution": level["data_resolution"], f"{meter}__coarse": _flag(level["coarse_resolution"])})
            if meter in read_errors:
                reasons += [f"{meter}: {reason}" for reason in read_errors[meter]]
            elif level["LAeq_dB"] is None:
                reasons += [f"{meter}: {reason}" for reason in level["missing_reasons"]]
        row["missing_reasons"] = "; ".join(reasons)
        if id(marker) in csv_marker_ids:
            marker_rows.append(row)
        record = {"id": marker.get("id"), "timestamp_utc": row["timestamp_utc"], "timestamp_local_iso": row["timestamp_local_iso"],
                  "timezone": zone, "note": marker.get("note", ""), "position": marker.get("positionId") or None, **provenance,
                  "window_s": MARKER_HALF_WINDOW_S * 2, "levels": levels}
        if isinstance(marker.get("agent"), dict):
            record["agent"] = marker["agent"]
        if _status(marker) == "rejected":
            record["flagged"] = "rejected suggestion: do not treat as a real marker"
        marker_json.append(record)
    meter_info = [{"id": meter, "title": titles.get(meter, meter), "chart_offset_ms": float(offsets.get(meter, 0) or 0),
                   "chart_offset_s": float(offsets.get(meter, 0) or 0) / 1000, "timezone": _meter_zone(sources, meter),
                   "source_files": [Path(path).name for source in sources if source.get("position_name") == meter
                                    for path in source.get("file_paths", [])]} for meter in meters]
    readme = _readme(workspace, source_configs, meter_info, exported, default_zone, background_window_s, min_context_s,
                     include_all_resolutions, include_proposed)
    document = {"schema": JSON_SCHEMA, "exported": exported, "timezone": default_zone, "units": UNITS,
                "include_proposed": include_proposed, "readme": {item["key"]: item["value"] for item in readme},
                "meters": meter_info, "categories": categories, "events": event_json, "markers": marker_json}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic replace protects an existing export against partial worker failure.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8-sig", newline="", dir=output_path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["NSA annotations export", "format=2", f"exported={exported}", "resolution=best-available"])
            writer.writerow(["metadata", json.dumps({"version": 2, "categories": categories,
                "meters": [{"id": meter, "title": titles.get(meter, meter)} for meter in meters],
                "chart_offsets_ms": offsets, "sourceConfigs": sources})])
            writer.writerow([])
            _write_section(writer, "README", ["key", "value"], readme)
            _write_section(writer, "REGIONS", ["id", "category", "category_label", "category_ids", "note", "colour", "start", "end", "duration_s", "origin_meter", "areas", "merge_sources", "merge_categories", *meters,
                "chart_offset_ms", "source_start", "source_end", "source_areas", "data_resolution", "sample_interval_s", "coverage", "LAeq_dB", "LAFmax_dB",
                "start_local", "end_local", "source_start_local", "source_end_local",
                "start_utc", "end_utc", "timezone", "source", "status", "confidence", "rationale", "agent",
                "coarse_resolution", "coarse_resolution_reason", "missing_reasons"], region_rows)
            event_columns = ["id", "category_label", "note", "source", "status", "confidence", "agent", "start_utc", "end_utc",
                             "start_local_iso", "end_local_iso", "timezone", "duration_s", "origin_meter",
                             *[f"{meter}__{suffix}" for meter in meters for suffix in
                               ("state", "LAeq_dB", "LAFmax_dB", "LAF90_dB", "bg_LA90_dB", "diff_dB", "resolution", "coarse", "coverage")],
                             "missing_reasons"]
            _write_section(writer, "EVENTS", event_columns, event_rows)
            listed = {str(region["id"]) for region in csv_regions}
            _write_section(writer, "OVERALL", ["region_id", "category", "meter", "state", "data_resolution", "sample_interval_s", "coverage", "LAeq_dB", "LAFmax_dB", "LAF90_dB",
                "background_dB", "background_LA90_dB", "background_LAeq_dB", "diff_from_background_dB", "context_duration_s", "percentile_method", "missing_reasons"],
                [row for row in overall if str(row["region_id"]) in listed])
            _write_section(writer, "SPECTRAL", ["region_id", "category", "meter", "state", "parameter", "data_resolution", "sample_interval_s", "coverage", "missing_reasons", *[f"{frequency:g}Hz" for frequency in sorted(bands)]],
                [row for row in spectral if str(row["region_id"]) in listed])
            _write_section(writer, "MARKERS", ["id", "timestamp", "note", "colour", "metrics",
                "timestamp_utc", "timestamp_local_iso", "timezone", "position", "source", "status", "confidence", "rationale", "agent",
                *[f"{meter}__{suffix}" for meter in meters for suffix in ("LAeq_dB", "LAFmax_dB", "resolution", "coarse")],
                "missing_reasons"], marker_rows)
            _write_section(writer, "NOTES", ["key", "value"], notes)
        except BaseException:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    # The JSON is written first: a failure here leaves any previous CSV untouched.
    try:
        _atomic_write_text(json_path, json.dumps(_json_safe(document), indent=2, ensure_ascii=False, allow_nan=False))
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    try:
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--config", type=Path, help="Source config when annotation CSV lacks source metadata")
    parser.add_argument("--include-all-resolutions", action="store_true")
    parser.add_argument("--background-window-s", type=float, default=300)
    parser.add_argument("--min-context-s", type=float, default=60)
    parser.add_argument("--include-proposed", action="store_true",
                        help="Also export unreviewed (status=proposed) agent suggestions; rejected ones stay JSON-only")
    args = parser.parse_args(argv)
    try:
        result = export_annotations(args.input, args.output, args.config, args.include_all_resolutions,
                                    args.background_window_s, args.min_context_s, include_proposed=args.include_proposed)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Annotation export failed: {error}\n")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
