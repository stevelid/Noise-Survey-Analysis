"""Hybrid control module for the Noise Survey Analysis app.

Provides:
- URL deep-link parameter parsing and validation
- A localhost-only runtime control HTTP server
- A session bridge that exposes typed operations on the active Bokeh session
- Command and result dataclasses
"""
from .commands import (
    ControlCommand,
    ControlResult,
    ALLOWED_COMMANDS,
    ALLOWED_VIEW_MODES,
)
from .validation import (
    validate_viewport,
    validate_view_mode,
    validate_parameter,
    validate_command_payload,
    parse_deep_link_params,
)
from .session_bridge import SessionBridge
from .control_server import ControlServer

__all__ = [
    "ControlCommand",
    "ControlResult",
    "ALLOWED_COMMANDS",
    "ALLOWED_VIEW_MODES",
    "validate_viewport",
    "validate_view_mode",
    "validate_parameter",
    "validate_command_payload",
    "parse_deep_link_params",
    "SessionBridge",
    "ControlServer",
]
