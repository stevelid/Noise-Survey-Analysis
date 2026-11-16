"""Read regions and markers from a saved workspace file without a browser.

The dashboard autosaves ``<config_stem>.workspace.json`` beside the job config.  This module turns
that file into the same JSON shape the live ``list_annotations`` command returns, so an agent can
read the annotations of a job whether or not the dashboard is open.

Output record fields (snake_case, times are epoch ms plus ISO-8601 UTC strings):

* region: ``id, position, start, end, start_iso, end_iso, areas, note, category, category_label,
  categories, meter_states, color, source, status, rationale, confidence, agent, created_at,
  reviewed_at``
* marker: ``id, position, timestamp, timestamp_iso, note, color, source, status, rationale,
  confidence, agent, created_at, reviewed_at``

Items without ``source``/``status`` are ordinary user annotations: ``source: "user"`` and
``status: "accepted"``.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def workspace_path_for_config(config_path: str | Path) -> Path:
    """Return ``<config_stem>.workspace.json`` beside ``config_path``."""
    path = Path(config_path)
    return path.with_name(f"{path.stem}.workspace.json")


def _iso(ms: Any) -> Optional[str]:
    try:
        value = float(ms)
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc).isoformat(timespec="milliseconds").replace(
            "+00:00", "Z"
        )
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _agent(value: Any) -> Optional[dict]:
    if not isinstance(value, dict):
        return None
    return {"name": value.get("name"), "run_id": value.get("runId", value.get("run_id"))}


def _collection(slice_: Any) -> list[dict]:
    """Items of a ``{byId, allIds}`` slice (or a plain list) in stored order."""
    if isinstance(slice_, list):
        return [item for item in slice_ if isinstance(item, dict)]
    if not isinstance(slice_, dict):
        return []
    by_id = slice_.get("byId") or {}
    ids = slice_.get("allIds")
    if not isinstance(ids, list):
        ids = list(by_id.keys())
    out = []
    for item_id in ids:
        item = by_id.get(str(item_id), by_id.get(item_id))
        if isinstance(item, dict):
            out.append(item)
    return out


def _offset_ms(offsets: Optional[dict], position: Any) -> float:
    """Chart offset of ``position`` in ms (display time = source time + offset); 0 when unknown."""
    try:
        value = float((offsets or {}).get(position, 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if value == value and abs(value) != float("inf") else 0.0


def _minus(value: Any, offset: float) -> Any:
    return value - offset if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def region_to_api(region: dict, categories: Optional[dict] = None, offsets: Optional[dict] = None) -> dict[str, Any]:
    areas = [
        {"start": a.get("start"), "end": a.get("end")}
        for a in (region.get("areas") or [])
        if isinstance(a, dict)
    ] or [{"start": region.get("start"), "end": region.get("end")}]
    category_ids = region.get("categoryIds") or ([region.get("categoryId")] if region.get("categoryId") else [])
    catalog = (categories or {}).get("byId", {}) if isinstance(categories, dict) else {}
    category = category_ids[0] if category_ids else "other"
    offset = _offset_ms(offsets, region.get("positionId"))
    source_start, source_end = _minus(region.get("start"), offset), _minus(region.get("end"), offset)
    return {
        "id": region.get("id"),
        "position": region.get("positionId"),
        "start": region.get("start"),
        "end": region.get("end"),
        "start_iso": _iso(region.get("start")),
        "end_iso": _iso(region.get("end")),
        "source_start": source_start,
        "source_end": source_end,
        "source_start_iso": _iso(source_start),
        "source_end_iso": _iso(source_end),
        "areas": areas,
        "source_areas": [{"start": _minus(a["start"], offset), "end": _minus(a["end"], offset)} for a in areas],
        "note": region.get("note") or "",
        "category": category,
        "category_label": (catalog.get(category) or {}).get("label", category),
        "categories": category_ids or ["other"],
        "meter_states": region.get("meterStates") or {},
        "color": region.get("color"),
        "source": region.get("source") or "user",
        "status": region.get("status") or "accepted",
        "rationale": region.get("rationale"),
        "confidence": region.get("confidence"),
        "agent": _agent(region.get("agent")),
        "created_at": region.get("createdAt"),
        "reviewed_at": region.get("reviewedAt"),
    }


def marker_to_api(marker: dict, offsets: Optional[dict] = None) -> dict[str, Any]:
    source_timestamp = _minus(marker.get("timestamp"), _offset_ms(offsets, marker.get("positionId")))
    return {
        "id": marker.get("id"),
        "position": marker.get("positionId"),
        "timestamp": marker.get("timestamp"),
        "timestamp_iso": _iso(marker.get("timestamp")),
        "source_timestamp": source_timestamp,
        "source_timestamp_iso": _iso(source_timestamp),
        "note": marker.get("note") or "",
        "color": marker.get("color"),
        "source": marker.get("source") or "user",
        "status": marker.get("status") or "accepted",
        "rationale": marker.get("rationale"),
        "confidence": marker.get("confidence"),
        "agent": _agent(marker.get("agent")),
        "created_at": marker.get("createdAt"),
        "reviewed_at": marker.get("reviewedAt"),
    }


def _overlaps(item_start: Any, item_end: Any, start: Optional[float], end: Optional[float]) -> bool:
    try:
        low, high = float(item_start), float(item_end)
    except (TypeError, ValueError):
        return False
    if start is not None and high < start:
        return False
    if end is not None and low > end:
        return False
    return True


def annotations_from_workspace(
    workspace: dict,
    kind: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
    time_basis: str = "source",
) -> dict[str, Any]:
    """Return ``{positions, regions, markers, counts}`` from a parsed workspace payload.

    ``start``/``end`` are compared with the ``source_*`` times when ``time_basis`` is "source"
    (the default) or with the display times when it is "display"."""
    if time_basis not in ("source", "display"):
        raise ValueError("time_basis must be 'source' or 'display'")
    prefix = "source_" if time_basis == "source" else ""
    state = workspace.get("appState") if isinstance(workspace, dict) else None
    if not isinstance(state, dict):
        raise ValueError("workspace has no appState object")
    view = state.get("view") if isinstance(state.get("view"), dict) else {}
    regions_slice = state.get("regions")
    categories = regions_slice.get("categories") if isinstance(regions_slice, dict) else None
    offsets = view.get("positionChartOffsets") if isinstance(view.get("positionChartOffsets"), dict) else {}

    def wanted(record: dict) -> bool:
        return (status is None or record["status"] == status) and (source is None or record["source"] == source)

    regions: list[dict] = []
    markers: list[dict] = []
    if kind in (None, "region"):
        for raw in _collection(regions_slice):
            record = region_to_api(raw, categories, offsets)
            if wanted(record) and _overlaps(record[f"{prefix}start"], record[f"{prefix}end"], start, end):
                regions.append(record)
        regions.sort(key=lambda r: (r["start"] if isinstance(r["start"], (int, float)) else 0, r["id"] or 0))
    if kind in (None, "marker"):
        for raw in _collection(state.get("markers")):
            record = marker_to_api(raw, offsets)
            stamp = record[f"{prefix}timestamp"]
            if wanted(record) and _overlaps(stamp, stamp, start, end):
                markers.append(record)
        markers.sort(key=lambda m: (m["timestamp"] if isinstance(m["timestamp"], (int, float)) else 0, m["id"] or 0))

    def counts(items: list[dict]) -> dict[str, int]:
        out = {"proposed": 0, "accepted": 0, "rejected": 0}
        for item in items:
            out[item["status"]] = out.get(item["status"], 0) + 1
        return out

    return {
        "positions": list(view.get("availablePositions") or []),
        "position_chart_offsets": view.get("positionChartOffsets") or {},
        "saved_at": workspace.get("savedAt"),
        "regions": regions,
        "markers": markers,
        "counts": {"regions": counts(regions), "markers": counts(markers)},
    }


def load_annotations(
    config_path: Optional[str | Path] = None,
    workspace_path: Optional[str | Path] = None,
    **filters: Any,
) -> dict[str, Any]:
    """Load annotations for a job config (sibling autosave) or an explicit workspace file."""
    if workspace_path is None:
        if config_path is None:
            raise ValueError("give a config path or a workspace path")
        workspace_path = workspace_path_for_config(config_path)
    path = Path(workspace_path)
    if not path.is_file():
        raise FileNotFoundError(
            f"no saved workspace at {path} (the dashboard writes it after the first annotation change)"
        )
    with open(path, "r", encoding="utf-8-sig") as handle:
        workspace = json.load(handle)
    result = annotations_from_workspace(workspace, **filters)
    result["workspace_file"] = str(path)
    return result
