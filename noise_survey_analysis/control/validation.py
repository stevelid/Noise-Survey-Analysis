"""Shared validation rules for URL deep-link params and control commands.

All functions raise ``ValueError`` with a descriptive message on invalid input
and return the normalised value on success.  The same rules are used by both the
URL startup layer and the runtime CLI/API layer.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Optional

from .commands import ALLOWED_COMMANDS, ALLOWED_VIEW_MODES, MAX_PAYLOAD_BYTES, ControlCommand


# ---------------------------------------------------------------------------
# Low-level validators
# ---------------------------------------------------------------------------

def validate_timestamp_ms(value: Any, name: str = "timestamp") -> float:
    """Return ``value`` as a float epoch-millisecond timestamp.

    Raises ``ValueError`` if the value is not a finite positive number.
    """
    try:
        ts = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(ts):
        raise ValueError(f"{name} must be a finite number, got {ts}")
    if ts < 0:
        raise ValueError(f"{name} must be a non-negative epoch-ms value, got {ts}")
    return ts


def validate_viewport(start: Any, end: Any) -> tuple[float, float]:
    """Validate and return ``(start, end)`` epoch-ms viewport bounds.

    Rules:
    - Both values must be finite numbers.
    - ``end`` must be strictly greater than ``start``.
    """
    start_f = validate_timestamp_ms(start, "start")
    end_f = validate_timestamp_ms(end, "end")
    if end_f <= start_f:
        raise ValueError(
            f"end ({end_f}) must be greater than start ({start_f})"
        )
    return start_f, end_f


def validate_view_mode(value: Any) -> str:
    """Return the validated view mode string.

    Allowed values: ``"log"`` or ``"overview"``.
    """
    if not isinstance(value, str):
        raise ValueError(f"view mode must be a string, got {type(value).__name__!r}")
    normalised = value.strip().lower()
    if normalised not in ALLOWED_VIEW_MODES:
        allowed = ", ".join(sorted(ALLOWED_VIEW_MODES))
        raise ValueError(f"view mode must be one of {{{allowed}}}, got {value!r}")
    return normalised


def validate_parameter(value: Any, available: Optional[list[str]] = None) -> str:
    """Return the validated acoustic parameter name.

    If ``available`` is provided the parameter must appear in that list.
    Otherwise just checks the value is a non-empty string.
    """
    if not isinstance(value, str):
        raise ValueError(f"parameter must be a string, got {type(value).__name__!r}")
    stripped = value.strip()
    if not stripped:
        raise ValueError("parameter must not be empty")
    if available is not None:
        if stripped not in available:
            raise ValueError(
                f"parameter {stripped!r} is not in the available set: {available!r}"
            )
    return stripped


def validate_workspace_path(path: Any) -> str:
    """Return an absolute, expanded file path that exists and is readable."""
    if not isinstance(path, str):
        raise ValueError(f"workspace path must be a string, got {type(path).__name__!r}")
    expanded = os.path.expanduser(path.strip())
    if not expanded:
        raise ValueError("workspace path must not be empty")
    if not os.path.isfile(expanded):
        raise ValueError(f"workspace file not found: {expanded!r}")
    return expanded


def validate_workspace_payload(payload: Any) -> dict:
    """Return a validated workspace payload dict.

    Accepts either a ``str`` (JSON text) or a ``dict``.  The resulting dict
    must contain at least one of ``appState`` or ``sourceConfigs``.
    """
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ValueError(f"workspace payload is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("workspace payload must be a JSON object")
    if "appState" not in payload and "sourceConfigs" not in payload:
        raise ValueError(
            "workspace payload must contain 'appState' and/or 'sourceConfigs'"
        )
    return payload


def validate_body_size(body: bytes | str) -> None:
    """Raise ``ValueError`` if the request body exceeds ``MAX_PAYLOAD_BYTES``."""
    size = len(body) if isinstance(body, (bytes, bytearray)) else len(body.encode())
    if size > MAX_PAYLOAD_BYTES:
        raise ValueError(
            f"request body too large: {size} bytes (max {MAX_PAYLOAD_BYTES})"
        )


# ---------------------------------------------------------------------------
# Command-level validator
# ---------------------------------------------------------------------------

def validate_command_payload(command: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Validate the payload for a specific command.

    Returns the (possibly normalised) payload dict on success.
    Raises ``ValueError`` describing the problem on failure.
    """
    if command not in ALLOWED_COMMANDS:
        allowed = ", ".join(sorted(ALLOWED_COMMANDS))
        raise ValueError(f"unknown command {command!r}; allowed: {allowed}")

    payload = payload or {}

    if command == "set_viewport":
        start, end = validate_viewport(payload.get("start"), payload.get("end"))
        return {"start": start, "end": end}

    if command == "center_on_timestamp":
        ts = validate_timestamp_ms(payload.get("timestamp"), "timestamp")
        half_width_ms = payload.get("half_width_ms")
        result: dict[str, Any] = {"timestamp": ts}
        if half_width_ms is not None:
            hw = float(half_width_ms)
            if not math.isfinite(hw) or hw <= 0:
                raise ValueError("half_width_ms must be a positive finite number")
            result["half_width_ms"] = hw
        return result

    if command == "set_parameter":
        value = validate_parameter(payload.get("value"))
        return {"value": value}

    if command == "set_view_mode":
        value = validate_view_mode(payload.get("value"))
        return {"value": value}

    if command == "apply_workspace":
        # Accept either a file path or an inline payload
        path = payload.get("path")
        inline = payload.get("payload")
        if path is not None:
            validated_path = validate_workspace_path(path)
            return {"path": validated_path}
        if inline is not None:
            validated_payload = validate_workspace_payload(inline)
            return {"payload": validated_payload}
        raise ValueError("apply_workspace requires either 'path' or 'payload'")

    # Commands with no required payload: status, fit_full_range, export_static_html
    return {}


# ---------------------------------------------------------------------------
# URL / request deep-link parameter parser
# ---------------------------------------------------------------------------

def parse_deep_link_params(
    raw: dict[str, Any],
    available_params: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Parse and validate URL deep-link startup parameters.

    Accepts a dict of raw string values (e.g. from ``request.arguments``).
    Returns a dict containing only the valid, normalised overrides that were
    present.  Missing or invalid parameters are silently dropped (a warning
    should be logged by the caller).

    Supported keys: ``start``, ``end``, ``param``, ``view``.

    Viewport overrides (``start`` / ``end``) are only included in the result
    when *both* values are present and valid together.
    """
    result: dict[str, Any] = {}
    errors: dict[str, str] = {}

    # --- view mode ---
    raw_view = _get_first(raw, "view")
    if raw_view is not None:
        try:
            result["view"] = validate_view_mode(raw_view)
        except ValueError as exc:
            errors["view"] = str(exc)

    # --- parameter ---
    raw_param = _get_first(raw, "param")
    if raw_param is not None:
        try:
            result["param"] = validate_parameter(raw_param, available=available_params)
        except ValueError as exc:
            errors["param"] = str(exc)

    # --- viewport (both start and end required) ---
    raw_start = _get_first(raw, "start")
    raw_end = _get_first(raw, "end")
    if raw_start is not None or raw_end is not None:
        # Only apply if both are present
        if raw_start is None:
            errors["start"] = "start is required when end is provided"
        elif raw_end is None:
            errors["end"] = "end is required when start is provided"
        else:
            try:
                start_f, end_f = validate_viewport(raw_start, raw_end)
                result["start"] = start_f
                result["end"] = end_f
            except ValueError as exc:
                errors["viewport"] = str(exc)

    result["_errors"] = errors
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_first(mapping: dict, key: str) -> Optional[str]:
    """Return the first decoded string value for ``key`` from a Bokeh-style
    arguments dict (values may be lists of bytes or plain strings)."""
    raw = mapping.get(key)
    if raw is None:
        return None
    if isinstance(raw, (list, tuple)):
        for item in raw:
            decoded = _decode(item)
            if decoded is not None:
                return decoded
        return None
    return _decode(raw)


def _decode(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("utf-8", errors="ignore")
    return str(value) if value != "" else None
