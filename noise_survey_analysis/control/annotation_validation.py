"""Validation for the annotation commands of the control API.

These commands let an agent (an LLM, a classifier script) read, propose and edit regions and markers
in a running dashboard.  Everything the browser is asked to apply is validated here first, so the
browser only ever sees well-formed payloads.

Rules (shared by every command):

* Times are epoch milliseconds (a JSON number) or an ISO-8601 string that carries an explicit UTC
  offset (``Z`` or ``+01:00``).  A "naive" string such as ``2026-11-09T10:16:42`` is rejected because
  the dashboard cannot know which clock it was read from.  Numbers below 1e11 are rejected as
  probably being epoch seconds.
* ``start`` must be before ``end``.
* ``position`` must be one of the registered positions when the list is known.
* ``confidence`` is a number from 0 to 1 (or null).
* At most ``MAX_BATCH_ITEMS`` items per call.
* Items added by an agent default to ``status: "proposed"``; ``source`` is always ``"agent"``.
* Unknown keys are errors, so a typo is never silently ignored.

All functions raise ``ValueError`` with a message naming the offending item and field.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional, Sequence

MAX_BATCH_ITEMS: int = 500
MAX_NOTE_CHARS: int = 2000
MAX_RATIONALE_CHARS: int = 2000
MAX_MESSAGE_CHARS: int = 500
MAX_NAME_CHARS: int = 100

# Anything below this (about 1973 in epoch ms) is almost certainly epoch seconds.
MIN_PLAUSIBLE_EPOCH_MS: float = 1e11

STATUS_ON_ADD: frozenset[str] = frozenset({"proposed", "accepted"})
STATUS_ALL: frozenset[str] = frozenset({"proposed", "accepted", "rejected"})
TIME_BASES: frozenset[str] = frozenset({"source", "display"})
METER_STATES: frozenset[str] = frozenset({"present", "absent", "unchecked"})
LIST_KINDS: frozenset[str] = frozenset({"region", "marker"})
LIST_SOURCES: frozenset[str] = frozenset({"user", "agent"})

REGION_ADD_KEYS: frozenset[str] = frozenset({
    "position", "start", "end", "areas", "note", "category", "meter_states", "status",
    "rationale", "confidence", "client_ref", "color",
})
REGION_CHANGE_KEYS: frozenset[str] = frozenset({
    "start", "end", "areas", "note", "category", "meter_states", "status", "rationale",
    "confidence", "color",
})
MARKER_ADD_KEYS: frozenset[str] = frozenset({
    "timestamp", "position", "note", "status", "rationale", "confidence", "client_ref", "color",
})
MARKER_CHANGE_KEYS: frozenset[str] = frozenset({
    "timestamp", "position", "note", "status", "rationale", "confidence", "color",
})

_ISO_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2})(?::(\d{2})(?:[.,](\d{1,9}))?)?"
    r"(Z|z|[+-]\d{2}(?::?\d{2})?)$"
)
_COLOR_RE = re.compile(r"^(?:#[0-9a-fA-F]{3}|#[0-9a-fA-F]{4}|#[0-9a-fA-F]{6}|#[0-9a-fA-F]{8}|[a-zA-Z]+)$")


# ---------------------------------------------------------------------------
# Scalars
# ---------------------------------------------------------------------------

def parse_time_ms(value: Any, name: str = "time") -> float:
    """Return ``value`` as epoch milliseconds.

    Accepts a finite number (epoch ms) or an ISO-8601 string with an explicit UTC offset.
    """
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be epoch milliseconds or an ISO-8601 time with an offset, got {value!r}")
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{name} must be finite, got {value!r}")
        if number < MIN_PLAUSIBLE_EPOCH_MS:
            raise ValueError(
                f"{name} {value!r} is too small to be epoch milliseconds (looks like epoch seconds?)"
            )
        return number
    if isinstance(value, str):
        text = value.strip()
        match = _ISO_RE.match(text)
        if not match:
            has_clock = re.search(r"\d{2}:\d{2}", text) is not None
            if has_clock and re.match(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(?::\d{2}(?:[.,]\d+)?)?$", text):
                raise ValueError(
                    f"{name} {value!r} has no UTC offset; use e.g. '2026-11-09T10:16:42Z' or '+00:00'"
                )
            raise ValueError(
                f"{name} {value!r} is not an ISO-8601 time with an offset (e.g. 2026-11-09T10:16:42Z)"
            )
        year, month, day, hour, minute, second, fraction, offset = match.groups()
        micro = int((fraction or "0").ljust(6, "0")[:6])
        if offset in ("Z", "z"):
            tz = timezone.utc
        else:
            sign = -1 if offset[0] == "-" else 1
            digits = offset[1:].replace(":", "")
            off_hours = int(digits[:2])
            off_minutes = int(digits[2:4]) if len(digits) > 2 else 0
            if off_hours > 23 or off_minutes > 59:
                raise ValueError(f"{name} {value!r} has an invalid UTC offset")
            tz = timezone(sign * timedelta(hours=off_hours, minutes=off_minutes))
        try:
            moment = datetime(
                int(year), int(month), int(day), int(hour), int(minute), int(second or 0), micro, tzinfo=tz
            )
        except ValueError as exc:
            raise ValueError(f"{name} {value!r} is not a valid time: {exc}") from None
        return float(round(moment.timestamp() * 1000))
    raise ValueError(f"{name} must be epoch milliseconds or an ISO-8601 time with an offset, got {type(value).__name__}")


def _text(value: Any, name: str, limit: int, *, allow_empty: bool = True) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string, got {type(value).__name__}")
    if "\x00" in value:
        raise ValueError(f"{name} contains a NUL character")
    if len(value) > limit:
        raise ValueError(f"{name} is {len(value)} characters; the limit is {limit}")
    if not allow_empty and not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


def _confidence(value: Any, name: str = "confidence") -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number from 0 to 1 or null, got {value!r}")
    number = float(value)
    if not math.isfinite(number) or number < 0 or number > 1:
        raise ValueError(f"{name} must be from 0 to 1, got {value!r}")
    return number


def _status(value: Any, allowed: Iterable[str], name: str = "status") -> str:
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(f"{name} must be one of {sorted(allowed)}, got {value!r}")
    return value


def _color(value: Any, name: str = "color") -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str) or not _COLOR_RE.match(value.strip()):
        raise ValueError(f"{name} must be a hex colour such as '#e65100' or a plain CSS colour name")
    return value.strip()


def _position(value: Any, positions: Optional[Sequence[str]], name: str = "position") -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    value = value.strip()
    if positions and value not in positions:
        raise ValueError(f"{name} {value!r} is not a known position; known: {', '.join(positions)}")
    return value


def _ids(value: Any, name: str = "ids") -> list[int]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list of integer ids")
    if len(value) > MAX_BATCH_ITEMS:
        raise ValueError(f"{name} has {len(value)} items; the limit is {MAX_BATCH_ITEMS}")
    out: list[int] = []
    for item in value:
        out.append(_one_id(item, name))
    if len(set(out)) != len(out):
        raise ValueError(f"{name} contains duplicates")
    return out


def _one_id(value: Any, name: str = "id") -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    if isinstance(value, float) and (not math.isfinite(value) or value != int(value)):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    number = int(value)
    if number < 1:
        raise ValueError(f"{name} must be a positive integer, got {value!r}")
    return number


def _reject_unknown(item: dict, allowed: frozenset[str], label: str) -> None:
    unknown = sorted(set(item) - allowed)
    if unknown:
        raise ValueError(f"{label}: unknown field(s) {', '.join(unknown)}; allowed: {', '.join(sorted(allowed))}")


def _batch(value: Any, name: str) -> list[dict]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    if len(value) > MAX_BATCH_ITEMS:
        raise ValueError(f"{name} has {len(value)} items; the limit is {MAX_BATCH_ITEMS} per call")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{name}[{index}] must be an object")
    return value


def _time_basis(payload: dict) -> str:
    """``time_basis`` of a command: "source" (default) or "display"; see CONTROL_API.md."""
    value = payload.get("time_basis", "source")
    return _status(value, TIME_BASES, "time_basis")


def _basis_out(payload: dict, basis: str) -> dict[str, str]:
    """``{"time_basis": ...}`` only when the caller gave one; the browser defaults to "source"."""
    return {"time_basis": basis} if "time_basis" in payload else {}


def _reject_unknown_top(payload: dict, allowed: Iterable[str], command: str) -> None:
    unknown = sorted(set(payload) - set(allowed))
    if unknown:
        raise ValueError(f"{command}: unknown field(s) {', '.join(unknown)}")


# ---------------------------------------------------------------------------
# Agent identity
# ---------------------------------------------------------------------------

def validate_agent(value: Any) -> dict[str, Any]:
    """Return ``{"name": str, "runId": str | None}`` from a string or an object."""
    if isinstance(value, str):
        value = {"name": value}
    if not isinstance(value, dict):
        raise ValueError("agent is required: a name string or {\"name\": ..., \"run_id\": ...}")
    _reject_unknown(value, frozenset({"name", "run_id", "runId"}), "agent")
    name = _text(value.get("name"), "agent.name", MAX_NAME_CHARS, allow_empty=False).strip()
    run_id = value.get("run_id", value.get("runId"))
    if run_id is not None:
        run_id = _text(str(run_id) if isinstance(run_id, (int, float)) and not isinstance(run_id, bool) else run_id,
                       "agent.run_id", MAX_NAME_CHARS)
    return {"name": name, "runId": run_id}


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

def _areas(item: dict, label: str, time_range: Optional[tuple[float, float]]) -> list[dict[str, float]]:
    has_pair = "start" in item or "end" in item
    has_areas = "areas" in item
    if has_pair and has_areas:
        raise ValueError(f"{label}: give either start/end or areas, not both")
    if has_areas:
        raw = item["areas"]
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"{label}: areas must be a non-empty list of {{start, end}}")
        if len(raw) > 100:
            raise ValueError(f"{label}: areas has {len(raw)} entries; the limit is 100")
        pairs = []
        for index, area in enumerate(raw):
            if not isinstance(area, dict):
                raise ValueError(f"{label}: areas[{index}] must be an object")
            _reject_unknown(area, frozenset({"start", "end"}), f"{label}: areas[{index}]")
            pairs.append((area.get("start"), area.get("end"), f"{label}: areas[{index}]"))
    else:
        if "start" not in item or "end" not in item:
            raise ValueError(f"{label}: start and end (or areas) are required")
        pairs = [(item["start"], item["end"], label)]
    out = []
    for start_raw, end_raw, where in pairs:
        start = parse_time_ms(start_raw, f"{where} start")
        end = parse_time_ms(end_raw, f"{where} end")
        if start >= end:
            raise ValueError(f"{where}: start must be before end")
        _check_range(start, where, "start", time_range)
        _check_range(end, where, "end", time_range)
        out.append({"start": start, "end": end})
    return out


def _check_range(value: float, label: str, field: str, time_range: Optional[tuple[float, float]]) -> None:
    if time_range is None:
        return
    low, high = time_range
    if value < low or value > high:
        raise ValueError(f"{label}: {field} is outside the survey range")


def _meter_states(value: Any, positions: Optional[Sequence[str]], label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{label}: meter_states must be an object of position -> present|absent|unchecked")
    out = {}
    for key, state in value.items():
        _position(key, positions, f"{label}: meter_states key")
        out[key] = _status(state, METER_STATES, f"{label}: meter_states[{key}]")
    return out


def _common_fields(item: dict, label: str, out: dict, *, allow_status: Iterable[str]) -> None:
    if "note" in item:
        out["note"] = _text(item["note"], f"{label}: note", MAX_NOTE_CHARS)
    if "rationale" in item:
        out["rationale"] = _text(item["rationale"], f"{label}: rationale", MAX_RATIONALE_CHARS)
    if "confidence" in item:
        out["confidence"] = _confidence(item["confidence"], f"{label}: confidence")
    if "status" in item:
        out["status"] = _status(item["status"], allow_status, f"{label}: status")
    if "color" in item:
        out["color"] = _color(item["color"], f"{label}: color")


def _client_ref(item: dict, label: str, seen: set[str], out: dict) -> None:
    if "client_ref" in item and item["client_ref"] is not None:
        ref = _text(item["client_ref"], f"{label}: client_ref", MAX_NAME_CHARS, allow_empty=False)
        if ref in seen:
            raise ValueError(f"{label}: client_ref {ref!r} is used twice in this call")
        seen.add(ref)
        out["client_ref"] = ref


def validate_add_regions(payload: dict, positions: Optional[Sequence[str]] = None,
                         time_range: Optional[tuple[float, float]] = None) -> dict[str, Any]:
    _reject_unknown_top(payload, ("agent", "regions", "time_basis"), "add_regions")
    agent = validate_agent(payload.get("agent"))
    basis = _time_basis(payload)
    if basis == "display":
        time_range = None  # the survey range is source time
    items = _batch(payload.get("regions"), "regions")
    seen: set[str] = set()
    regions = []
    for index, item in enumerate(items):
        label = f"regions[{index}]"
        _reject_unknown(item, REGION_ADD_KEYS, label)
        out: dict[str, Any] = {"position": _position(item.get("position"), positions, f"{label}: position")}
        out["areas"] = _areas(item, label, time_range)
        _common_fields(item, label, out, allow_status=STATUS_ON_ADD)
        out.setdefault("status", "proposed")
        if "category" in item and item["category"] is not None:
            out["category"] = _text(item["category"], f"{label}: category", MAX_NAME_CHARS, allow_empty=False).strip()
        if "meter_states" in item:
            out["meter_states"] = _meter_states(item["meter_states"], positions, label)
        _client_ref(item, label, seen, out)
        regions.append(out)
    return {"agent": agent, "regions": regions, **_basis_out(payload, basis)}


def validate_update_region(payload: dict, positions: Optional[Sequence[str]] = None,
                           time_range: Optional[tuple[float, float]] = None) -> dict[str, Any]:
    _reject_unknown_top(payload, ("id", "changes", "time_basis"), "update_region")
    region_id = _one_id(payload.get("id"), "id")
    basis = _time_basis(payload)
    if basis == "display":
        time_range = None
    changes = payload.get("changes")
    if not isinstance(changes, dict) or not changes:
        raise ValueError("changes must be a non-empty object")
    label = "changes"
    _reject_unknown(changes, REGION_CHANGE_KEYS, label)
    out: dict[str, Any] = {}
    if "areas" in changes:
        if "start" in changes or "end" in changes:
            raise ValueError("changes: give either start/end or areas, not both")
        out["areas"] = _areas({"areas": changes["areas"]}, label, time_range)
    else:
        if "start" in changes:
            out["start"] = parse_time_ms(changes["start"], "changes: start")
            _check_range(out["start"], label, "start", time_range)
        if "end" in changes:
            out["end"] = parse_time_ms(changes["end"], "changes: end")
            _check_range(out["end"], label, "end", time_range)
        if "start" in out and "end" in out and out["start"] >= out["end"]:
            raise ValueError("changes: start must be before end")
    _common_fields(changes, label, out, allow_status=STATUS_ALL)
    if "category" in changes:
        out["category"] = _text(changes["category"], "changes: category", MAX_NAME_CHARS, allow_empty=False).strip()
    if "meter_states" in changes:
        out["meter_states"] = _meter_states(changes["meter_states"], positions, label)
    return {"id": region_id, "changes": out, **_basis_out(payload, basis)}


def validate_delete(payload: dict, command: str) -> dict[str, Any]:
    _reject_unknown_top(payload, ("ids", "force"), command)
    ids = _ids(payload.get("ids"))
    force = payload.get("force", False)
    if not isinstance(force, bool):
        raise ValueError("force must be a boolean")
    return {"ids": ids, "force": force}


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def validate_add_markers(payload: dict, positions: Optional[Sequence[str]] = None,
                         time_range: Optional[tuple[float, float]] = None) -> dict[str, Any]:
    _reject_unknown_top(payload, ("agent", "markers", "time_basis"), "add_markers")
    agent = validate_agent(payload.get("agent"))
    basis = _time_basis(payload)
    if basis == "display":
        time_range = None
    items = _batch(payload.get("markers"), "markers")
    seen: set[str] = set()
    markers = []
    stamps: set[float] = set()
    for index, item in enumerate(items):
        label = f"markers[{index}]"
        _reject_unknown(item, MARKER_ADD_KEYS, label)
        if "timestamp" not in item:
            raise ValueError(f"{label}: timestamp is required")
        out: dict[str, Any] = {"timestamp": parse_time_ms(item["timestamp"], f"{label}: timestamp")}
        _check_range(out["timestamp"], label, "timestamp", time_range)
        if out["timestamp"] in stamps:
            raise ValueError(f"{label}: timestamp repeats an earlier marker in this call")
        stamps.add(out["timestamp"])
        if item.get("position") is not None:
            out["position"] = _position(item["position"], positions, f"{label}: position")
        _common_fields(item, label, out, allow_status=STATUS_ON_ADD)
        out.setdefault("status", "proposed")
        _client_ref(item, label, seen, out)
        markers.append(out)
    return {"agent": agent, "markers": markers, **_basis_out(payload, basis)}


def validate_update_marker(payload: dict, positions: Optional[Sequence[str]] = None,
                           time_range: Optional[tuple[float, float]] = None) -> dict[str, Any]:
    _reject_unknown_top(payload, ("id", "changes", "time_basis"), "update_marker")
    marker_id = _one_id(payload.get("id"), "id")
    basis = _time_basis(payload)
    if basis == "display":
        time_range = None
    changes = payload.get("changes")
    if not isinstance(changes, dict) or not changes:
        raise ValueError("changes must be a non-empty object")
    _reject_unknown(changes, MARKER_CHANGE_KEYS, "changes")
    out: dict[str, Any] = {}
    if "timestamp" in changes:
        out["timestamp"] = parse_time_ms(changes["timestamp"], "changes: timestamp")
        _check_range(out["timestamp"], "changes", "timestamp", time_range)
    if "position" in changes:
        out["position"] = None if changes["position"] is None else _position(
            changes["position"], positions, "changes: position")
    _common_fields(changes, "changes", out, allow_status=STATUS_ALL)
    return {"id": marker_id, "changes": out, **_basis_out(payload, basis)}


# ---------------------------------------------------------------------------
# Read and navigate
# ---------------------------------------------------------------------------

def validate_list_annotations(payload: dict) -> dict[str, Any]:
    _reject_unknown_top(payload, ("kind", "status", "source", "start", "end", "time_basis"), "list_annotations")
    out: dict[str, Any] = _basis_out(payload, _time_basis(payload))
    if payload.get("kind") is not None:
        out["kind"] = _status(payload["kind"], LIST_KINDS, "kind")
    if payload.get("status") is not None:
        out["status"] = _status(payload["status"], STATUS_ALL, "status")
    if payload.get("source") is not None:
        out["source"] = _status(payload["source"], LIST_SOURCES, "source")
    if payload.get("start") is not None:
        out["start"] = parse_time_ms(payload["start"], "start")
    if payload.get("end") is not None:
        out["end"] = parse_time_ms(payload["end"], "end")
    if "start" in out and "end" in out and out["start"] >= out["end"]:
        raise ValueError("start must be before end")
    return out


def validate_show(payload: dict, positions: Optional[Sequence[str]] = None) -> dict[str, Any]:
    _reject_unknown_top(
        payload, ("region_id", "marker_id", "start", "end", "position", "parameter", "select", "message", "time_basis"), "show"
    )
    out: dict[str, Any] = _basis_out(payload, _time_basis(payload))
    targets = [name for name in ("region_id", "marker_id") if payload.get(name) is not None]
    has_window = payload.get("start") is not None or payload.get("end") is not None
    if len(targets) + (1 if has_window else 0) != 1:
        raise ValueError("show needs exactly one of region_id, marker_id, or start and end")
    if targets:
        out[targets[0]] = _one_id(payload[targets[0]], targets[0])
    else:
        if payload.get("start") is None or payload.get("end") is None:
            raise ValueError("show needs both start and end")
        out["start"] = parse_time_ms(payload["start"], "start")
        out["end"] = parse_time_ms(payload["end"], "end")
        if out["start"] >= out["end"]:
            raise ValueError("start must be before end")
    if payload.get("position") is not None:
        out["position"] = _position(payload["position"], positions)
    if payload.get("parameter") is not None:
        out["parameter"] = _text(payload["parameter"], "parameter", MAX_NAME_CHARS, allow_empty=False).strip()
    if "select" in payload:
        if not isinstance(payload["select"], bool):
            raise ValueError("select must be a boolean")
        out["select"] = payload["select"]
    if payload.get("message") is not None:
        out["message"] = _text(payload["message"], "message", MAX_MESSAGE_CHARS)
    return out


ANNOTATION_COMMANDS: frozenset[str] = frozenset({
    "list_annotations", "add_regions", "update_region", "delete_regions",
    "add_markers", "update_marker", "delete_markers", "show",
})

# Commands that change the dashboard; a missing acknowledgement must not be reported as success.
MUTATING_ANNOTATION_COMMANDS: frozenset[str] = frozenset({
    "add_regions", "update_region", "delete_regions", "add_markers", "update_marker", "delete_markers", "show",
})


def validate_annotation_command(command: str, payload: dict, positions: Optional[Sequence[str]] = None,
                                time_range: Optional[tuple[float, float]] = None) -> dict[str, Any]:
    """Dispatch to the validator for one annotation command."""
    positions = [p for p in (positions or []) if isinstance(p, str)] or None
    if command == "list_annotations":
        return validate_list_annotations(payload)
    if command == "add_regions":
        return validate_add_regions(payload, positions, time_range)
    if command == "update_region":
        return validate_update_region(payload, positions, time_range)
    if command == "delete_regions":
        return validate_delete(payload, command)
    if command == "add_markers":
        return validate_add_markers(payload, positions, time_range)
    if command == "update_marker":
        return validate_update_marker(payload, positions, time_range)
    if command == "delete_markers":
        return validate_delete(payload, command)
    if command == "show":
        return validate_show(payload, positions)
    raise ValueError(f"not an annotation command: {command!r}")
