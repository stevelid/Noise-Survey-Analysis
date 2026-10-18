"""Explicit, non-destructive annotation workspace migration shared by Python entry points."""
from __future__ import annotations

from copy import deepcopy
from math import isfinite
import re
from typing import Any

WORKSPACE_VERSION = 2
LEGACY_TIME_TOLERANCE_MS = 1
DEFAULT_CATEGORIES = [
    {"id": "dog-bark", "label": "Dog bark", "color": "#e65100"},
    {"id": "traffic", "label": "Traffic", "color": "#1976d2"},
    {"id": "plant", "label": "Plant", "color": "#388e3c"},
    {"id": "speech", "label": "Speech", "color": "#7b1fa2"},
    {"id": "other", "label": "Other", "color": "#1e88e5"},
]


def normalize_color(value: Any, fallback: str | None = None) -> str | None:
    text = value.strip() if isinstance(value, str) else ""
    return text if re.fullmatch(r"(?:#[\da-f]{3}|#[\da-f]{4}|#[\da-f]{6}|#[\da-f]{8}|[a-z]+)", text, re.I) else fallback


def normalize_catalog(catalog: Any = None) -> dict[str, Any]:
    if isinstance(catalog, list):
        incoming = catalog
    elif isinstance(catalog, dict) and isinstance(catalog.get("byId"), dict):
        incoming = [catalog["byId"].get(key) for key in catalog.get("allIds", catalog["byId"])]
    else:
        incoming = DEFAULT_CATEGORIES
    by_id = {}
    for item in incoming:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        identifier = item["id"].strip()
        if not identifier or identifier in {"__proto__", "constructor", "prototype"} or identifier in by_id:
            continue
        label = str(item.get("label") or item.get("name") or identifier).strip()
        by_id[identifier] = {"id": identifier, "label": label,
                             "color": normalize_color(item.get("color"), "#1e88e5")}
    if "other" not in by_id:
        by_id["other"] = DEFAULT_CATEGORIES[-1].copy()
    return {"byId": by_id, "allIds": list(by_id)}


def normalize_areas(region: dict[str, Any]) -> list[dict[str, float]]:
    """Return the sorted area union so migration never counts overlaps twice."""
    areas = []
    for area in region.get("areas") or [region]:
        try:
            start, end = float(area["start"]), float(area["end"])
        except (KeyError, TypeError, ValueError):
            continue
        if isfinite(start) and isfinite(end) and start != end:
            areas.append({"start": min(start, end), "end": max(start, end)})
    merged: list[dict[str, float]] = []
    for area in sorted(areas, key=lambda value: (value["start"], value["end"])):
        if merged and area["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], area["end"])
        else:
            merged.append(area.copy())
    return merged


def normalize_region(region: dict[str, Any], positions: list[str]) -> dict[str, Any] | None:
    origin = region.get("positionId")
    areas = normalize_areas(region)
    if not origin or not areas:
        return None
    states = region.get("meterStates") or {}
    normalized = {key: states.get(key, "unchecked") for key in dict.fromkeys([*positions, *states, origin])}
    normalized = {key: value if value in {"present", "absent", "unchecked"} else "unchecked"
                  for key, value in normalized.items()}
    normalized[origin] = "present"
    return {**deepcopy(region), "positionId": origin, "areas": areas,
            "start": areas[0]["start"], "end": areas[-1]["end"],
            "note": region.get("note") if isinstance(region.get("note"), str) else "",
            "color": normalize_color(region.get("color")), "categoryId": region.get("categoryId") or "other",
            "meterStates": normalized}


def consolidate_legacy_regions(regions: list[dict[str, Any]], positions: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Match against a fixed representative, preventing tolerance-chain drift."""
    groups: list[tuple[dict[str, Any], dict[str, Any], set[str]]] = []
    merged_count = 0
    for raw in regions:
        region = normalize_region(raw, positions)
        if region is None:
            continue
        note = " ".join(region["note"].split())
        color = str(region.get("color") or "").strip().lower()
        match = None
        for representative, combined, origins in groups:
            if region["positionId"] in origins or len(representative["areas"]) != len(region["areas"]):
                continue
            same_areas = all(abs(left[key] - right[key]) <= LEGACY_TIME_TOLERANCE_MS
                             for left, right in zip(representative["areas"], region["areas"])
                             for key in ("start", "end"))
            same_note = bool(note) and note == " ".join(representative["note"].split())
            same_color = bool(color) and color == str(representative.get("color") or "").strip().lower()
            if same_areas and (same_note or same_color):
                match = (combined, origins)
                break
        if match is None:
            groups.append((deepcopy(region), region, {region["positionId"]}))
            continue
        combined, origins = match
        origins.add(region["positionId"])
        combined["meterStates"][region["positionId"]] = "present"
        if region["note"] and region["note"] not in combined["note"].split("\n"):
            combined["note"] = "\n".join(filter(None, [combined["note"], region["note"]]))
        merged_count += 1
    return [combined for _, combined, _ in groups], merged_count


def migrate_workspace(payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
    """Upgrade v1; normalize v2; refuse unknown versions before changing any state."""
    if not isinstance(payload, dict) or not isinstance(payload.get("appState"), dict):
        raise ValueError("Workspace must contain an appState object")
    version = payload.get("version", 1)
    if version not in (1, 2):
        raise ValueError(f"Unsupported workspace version: {version}")
    result = deepcopy(payload)
    state = result["appState"]
    old_slice = state.get("regions") or {}
    regions = old_slice if isinstance(old_slice, list) else [
        old_slice.get("byId", {}).get(str(key), old_slice.get("byId", {}).get(key))
        for key in old_slice.get("allIds", list(old_slice.get("byId", {})))
    ]
    regions = [region for region in regions if isinstance(region, dict)]
    positions = list(state.get("view", {}).get("availablePositions", []))
    for source in result.get("sourceConfigs", []):
        position = source.get("position_name") or source.get("position") or source.get("positionId")
        if position and position not in positions:
            positions.append(position)
    for region in regions:
        for position in [region.get("positionId"), *(region.get("meterStates") or {})]:
            if position and position not in positions:
                positions.append(position)
    if version == 1:
        regions, merged_count = consolidate_legacy_regions(regions, positions)
    else:
        regions = [normalized for region in regions if (normalized := normalize_region(region, positions))]
        merged_count = 0
    metadata = old_slice if isinstance(old_slice, dict) else {}
    by_id = {}
    counter = 1
    for region in regions:
        try:
            identifier = int(region.get("id", counter))
        except (ValueError, TypeError):
            identifier = counter
        if identifier < 1 or str(identifier) in by_id:
            identifier = counter
        while str(identifier) in by_id:
            identifier += 1
        region["id"] = identifier
        by_id[str(identifier)] = region
        counter = max(counter, identifier + 1)
    categories = normalize_catalog(metadata.get("categories"))
    selected = metadata.get("selectedId")
    state["regions"] = {**metadata, "byId": by_id, "allIds": [value["id"] for value in by_id.values()],
                        "counter": counter, "categories": categories,
                        "selectedId": selected if str(selected) in by_id else next(iter(by_id.values()), {}).get("id"),
                        "addAreaTargetId": None, "isMergeModeActive": False,
                        "ghostMode": metadata.get("ghostMode", "selected")}
    result["version"] = WORKSPACE_VERSION
    return result, merged_count
