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

import numpy as np
import pandas as pd

from ..core.annotation_metrics import (MetricResult, SPECTRAL_COLUMN, background_intervals,
                                       compute_region_metrics, union_intervals, _sample_geometry, _weights)
from ..core.annotation_windows import iter_source_windows
from ..core.annotation_workspace import DEFAULT_CATEGORIES, migrate_workspace

SECTIONS = ("REGIONS", "OVERALL", "SPECTRAL", "MARKERS", "NOTES")
FORMAT_VERSION = 2
COVERAGE_TOLERANCE = 1e-6


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
                     "meter", "colour", "color", "state", "parameter", "data_resolution", "key", "value")
    # Numeric-looking notes and meter IDs are still text. Leave metric columns
    # inferable so the public helper remains convenient for pandas/Excel work.
    table = pd.read_csv(stream, keep_default_na=False, dtype={name: str for name in semantic_text})
    numeric = {"duration_s", "chart_offset_ms", "sample_interval_s", "coverage", "context_duration_s"}
    for name in table.columns:
        if name in numeric or name.endswith("_dB") or re.fullmatch(r"\d+(?:\.\d+)?k?Hz", name):
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
        annotation_fields = {"id", "category", "category_label", "note", "colour", "start", "end", "duration_s",
                             "origin_meter", "areas", "chart_offset_ms", "source_start", "source_end", "source_areas",
                             "data_resolution", "sample_interval_s", "coverage", "LAeq_dB", "LAFmax_dB"}
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
        regions.append({"id": row.get("id"), "positionId": origin, "areas": areas,
                        "note": row.get("note", ""), "color": row.get("colour") or row.get("color") or None,
                        "categoryId": row.get("category") or row.get("categoryId") or "other", "meterStates": states})
    marker_table = read_export_section(path, "MARKERS")
    for row in marker_table.to_dict("records"):
        markers.append({"id": row.get("id"), "timestamp": _timestamp_ms(row.get("timestamp") or row.get("start")),
                        "note": row.get("note", ""), "color": row.get("colour") or row.get("color") or None,
                        "metrics": _json_value(row.get("metrics") or row.get("metrics_json"), {})})
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


def _spectral_provenance(frame: pd.DataFrame, parameter: str, areas, offset_ms: float) -> tuple[float, float | None]:
    """Parameter coverage follows native band clocks, independently of LAeq."""
    source_areas = [(start - offset_ms, end - offset_ms) for start, end in union_intervals(areas)]
    duration_s = sum(end - start for start, end in source_areas) / 1000
    nominal = frame.attrs.get("sample_interval_s") or 0
    timestamps = frame["Datetime"].astype("int64").to_numpy() / 1e6
    keep = np.zeros(len(frame), dtype=bool)
    for start, end in source_areas:
        keep |= (timestamps < end) & (timestamps + nominal * 1000 > start)
    selected = frame.loc[keep]
    coverages, periods = [], []
    for name in frame:
        match = SPECTRAL_COLUMN.match(str(name))
        if not match or match.group(1) != parameter:
            continue
        finite = np.isfinite(pd.to_numeric(selected[name], errors="coerce").to_numpy(dtype=float))
        series = selected.loc[finite, ["Datetime"]].copy()
        if series.empty:
            coverages.append(0.0)
            continue
        period_column = f"__sample_interval_s:{name}"
        if period_column in selected:
            series["__sample_interval_s"] = selected.loc[series.index, period_column]
        elif "__sample_interval_s" in selected:
            series["__sample_interval_s"] = selected.loc[series.index, "__sample_interval_s"]
        native = pd.to_numeric(series.get("__sample_interval_s", pd.Series(dtype=float)), errors="coerce")
        native = native[np.isfinite(native) & (native > 0)]
        starts, ends, period = _sample_geometry(series, float(native.max()) if not native.empty else nominal or None)
        coverages.append(min(1.0, float(_weights(starts, ends, source_areas).sum()) / duration_s) if duration_s else 0.0)
        if period:
            periods.append(period)
    return min(coverages, default=0.0), max(periods, default=None)


def _best_resolution(candidates: dict[str, tuple[Any, float]]) -> str | None:
    """Complete log first, then usable overview, then labelled partial log."""
    if "log" in candidates and candidates["log"][1] >= 1 - COVERAGE_TOLERANCE:
        return "log"
    if "overview" in candidates:
        return "overview"
    return "log" if "log" in candidates else None


def export_annotations(input_path: str | Path | dict, output_path: str | Path | None = None,
                       source_configs=None, include_all_resolutions: bool = False,
                       background_window_s: float = 300, min_context_s: float = 60) -> Path:
    """Export best available metrics using complete source log windows.

    Overview fallback is explicit in every row. Broadband and each spectral
    parameter choose independently; requesting both resolutions is optional.
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
    for meter in meters:
        offset_ms = float(offsets.get(meter, 0) or 0)
        contexts = {str(region["id"]): background_intervals(region, regions, meter, background_window_s) for region in regions}
        windows = union_intervals([area for region in regions for area in [*(region.get("areas") or [region]), *contexts[str(region["id"])]]])
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
        frames = {}
        for resolution, parts in chunks.items():
            # Broadband and spectral NTi files share timestamps; combine their
            # columns without counting duplicate timestamps or losing spectra.
            combined = pd.concat(parts, ignore_index=True).sort_values("Datetime")
            frames[resolution] = combined.groupby("Datetime", sort=True).first().reset_index()
            frames[resolution].attrs["sample_interval_s"] = max(intervals[resolution]) if intervals[resolution] else None
        if chunks:
            del combined, parts
        del chunks
        for region in regions:
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
    region_rows = []
    for region in regions:
        origin = region["positionId"]
        offset_ms = float(offsets.get(origin, 0) or 0)
        areas = union_intervals(region.get("areas") or [region])
        result = headline.get((str(region["id"]), origin), MetricResult("none"))
        region_rows.append({"id": region["id"], "category": region["categoryId"],
            "category_label": catalog.get(region["categoryId"], {}).get("label", region["categoryId"]),
            "note": region.get("note", ""), "colour": region.get("color"),
            "start": _iso(areas[0][0]), "end": _iso(areas[-1][1]),
            "duration_s": sum(end - start for start, end in areas) / 1000,
            "origin_meter": origin, "areas": json.dumps([{"start": start, "end": end} for start, end in areas]),
            **{meter: region["meterStates"].get(meter, "unchecked") for meter in meters},
            "chart_offset_ms": offset_ms, "source_start": _iso(areas[0][0] - offset_ms),
            "source_end": _iso(areas[-1][1] - offset_ms),
            "source_areas": json.dumps([{"start": start - offset_ms, "end": end - offset_ms} for start, end in areas]),
            "data_resolution": result.data_resolution, "sample_interval_s": result.sample_interval_s,
            "coverage": result.coverage, "LAeq_dB": result.LAeq_dB, "LAFmax_dB": result.LAFmax_dB})
    exported = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    notes += [{"key": "exported", "value": exported}, {"key": "resolution_policy", "value": "Best available independently for overall levels and each spectral parameter: fully covered source log, otherwise usable overview, otherwise labelled partial log. Both available resolutions only when include_all_resolutions=true. Python reads complete source windows independently of viewport buffers."},
              {"key": "include_all_resolutions", "value": str(include_all_resolutions).lower()},
              {"key": "background_method", "value": f"Duration-weighted LA90 (inverse-CDF p10) of pooled {background_window_s:g}s before/after each area, excluding all regions present at the meter; minimum {min_context_s:g}s. LAeq reported for the identical usable context. Difference = region LAeq - context LA90."},
              {"key": "percentile_caveat", "value": "LAF90 from overview or 1 s data is indicative. Where fast-level samples are unavailable, percentiles of LAeq (or interval LAF90) are estimates, not reconstructed fast-level statistics."},
              {"key": "colour", "value": "Blank colour means category default; nonblank colour is a per-region override."},
              {"key": "time_basis", "value": "Date-times are UTC; source times subtract target-meter chart offset. Half-open intervals, duration weighted, overlapping areas/context counted once; nominal sample intervals do not bridge gaps."},
              {"key": "sources", "value": json.dumps(sources)}, {"key": "chart_offsets_ms", "value": json.dumps(offsets)}]
    markers_state = state.get("markers") or {}
    markers = markers_state if isinstance(markers_state, list) else markers_state.get("items", markers_state.get("markers", []))
    if not markers and isinstance(markers_state, dict) and "byId" in markers_state:
        markers = list(markers_state["byId"].values())
    marker_rows = [{"id": marker.get("id"), "timestamp": _iso(marker.get("timestamp", marker.get("time", 0))),
                    "note": marker.get("note", ""), "colour": marker.get("color"),
                    "metrics": json.dumps(marker.get("metrics", marker.get("metricsByPosition", {})))} for marker in markers]
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
            _write_section(writer, "REGIONS", ["id", "category", "category_label", "note", "colour", "start", "end", "duration_s", "origin_meter", "areas", *meters,
                "chart_offset_ms", "source_start", "source_end", "source_areas", "data_resolution", "sample_interval_s", "coverage", "LAeq_dB", "LAFmax_dB"], region_rows)
            _write_section(writer, "OVERALL", ["region_id", "category", "meter", "state", "data_resolution", "sample_interval_s", "coverage", "LAeq_dB", "LAFmax_dB", "LAF90_dB",
                "background_dB", "background_LA90_dB", "background_LAeq_dB", "diff_from_background_dB", "context_duration_s", "percentile_method", "missing_reasons"], overall)
            _write_section(writer, "SPECTRAL", ["region_id", "category", "meter", "state", "parameter", "data_resolution", "sample_interval_s", "coverage", "missing_reasons", *[f"{frequency:g}Hz" for frequency in sorted(bands)]], spectral)
            _write_section(writer, "MARKERS", ["id", "timestamp", "note", "colour", "metrics"], marker_rows)
            _write_section(writer, "NOTES", ["key", "value"], notes)
        except BaseException:
            handle.close()
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
    args = parser.parse_args(argv)
    try:
        result = export_annotations(args.input, args.output, args.config, args.include_all_resolutions,
                                    args.background_window_s, args.min_context_s)
    except (ValueError, OSError) as error:
        parser.exit(1, f"Annotation export failed: {error}\n")
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
