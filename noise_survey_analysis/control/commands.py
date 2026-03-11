"""Command and result dataclasses for the hybrid control system."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Safe allowlist of commands that may be issued via the control API.
ALLOWED_COMMANDS: frozenset[str] = frozenset({
    "status",
    "set_viewport",
    "center_on_timestamp",
    "fit_full_range",
    "set_parameter",
    "set_view_mode",
    "apply_workspace",
    "export_static_html",
})

# Valid view mode values.
ALLOWED_VIEW_MODES: frozenset[str] = frozenset({"log", "overview"})

# Maximum size (bytes) accepted for a command payload JSON body.
MAX_PAYLOAD_BYTES: int = 1_048_576  # 1 MiB


@dataclass
class ControlCommand:
    """A typed command sent to the control server or JS bridge.

    Attributes:
        command: One of the names in ``ALLOWED_COMMANDS``.
        request_id: Caller-supplied opaque identifier echoed in the result.
        payload: Optional command-specific parameters (dict).
    """

    command: str
    request_id: str = ""
    payload: Optional[dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "request_id": self.request_id,
            "payload": self.payload or {},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlCommand":
        if not isinstance(data, dict):
            raise ValueError("Command must be a JSON object")
        command = data.get("command")
        if not command or not isinstance(command, str):
            raise ValueError("Missing or invalid 'command' field")
        return cls(
            command=command,
            request_id=str(data.get("request_id", "")),
            payload=data.get("payload") or {},
        )


@dataclass
class ControlResult:
    """Structured result returned by every control command.

    Attributes:
        success: Whether the command completed successfully.
        message: Human-readable description of the outcome.
        data: Optional structured result data.
        request_id: Echoed from the originating ``ControlCommand``.
    """

    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
    request_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "data": self.data,
            "request_id": self.request_id,
        }

    @classmethod
    def ok(
        cls,
        message: str = "OK",
        data: Optional[dict[str, Any]] = None,
        request_id: str = "",
    ) -> "ControlResult":
        return cls(success=True, message=message, data=data, request_id=request_id)

    @classmethod
    def error(
        cls,
        message: str,
        request_id: str = "",
    ) -> "ControlResult":
        return cls(success=False, message=message, request_id=request_id)
