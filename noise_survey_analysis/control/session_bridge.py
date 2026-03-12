"""Session bridge: holds the active Bokeh document and exposes typed operations.

All Bokeh model mutations are scheduled via ``doc.add_next_tick_callback`` so
they are applied on the Bokeh IO loop thread, avoiding concurrency issues when
called from the control server thread.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Optional

from .commands import ControlResult
from .validation import validate_viewport, validate_view_mode, validate_parameter

logger = logging.getLogger(__name__)


class SessionBridge:
    """Holds a reference to the active Bokeh ``doc`` and ``master_x_range``
    and exposes safe, typed control methods.

    This class is designed to be a singleton within the process—one instance
    is created per Bokeh application startup and updated when a new session
    connects.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._doc: Any = None  # bokeh.document.Document
        self._master_x_range: Any = None  # bokeh Range1d or DataRange1d
        self._param_select: Any = None  # Bokeh Select
        self._view_toggle: Any = None  # Bokeh Toggle
        self._control_state_source: Any = None  # ColumnDataSource
        self._automation_command_source: Any = None  # ColumnDataSource
        self._automation_result_source: Any = None  # ColumnDataSource
        # Pending result futures keyed by request_id
        self._pending: dict[str, threading.Event] = {}
        self._results: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Session registration
    # ------------------------------------------------------------------

    def register(
        self,
        doc: Any,
        master_x_range: Any = None,
        param_select: Any = None,
        view_toggle: Any = None,
        control_state_source: Any = None,
        automation_command_source: Any = None,
        automation_result_source: Any = None,
    ) -> None:
        """Register the active Bokeh document and optional model references.

        Safe to call from any thread; uses an internal lock.
        """
        with self._lock:
            self._doc = doc
            self._master_x_range = master_x_range
            self._param_select = param_select
            self._view_toggle = view_toggle
            self._control_state_source = control_state_source
            self._automation_command_source = automation_command_source
            self._automation_result_source = automation_result_source
        logger.info("SessionBridge: session registered (doc=%s)", type(doc).__name__)

    def unregister(self) -> None:
        """Clear the active session reference."""
        with self._lock:
            self._doc = None
            self._master_x_range = None
            self._param_select = None
            self._view_toggle = None
            self._control_state_source = None
            self._automation_command_source = None
            self._automation_result_source = None
        logger.info("SessionBridge: session unregistered")

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._doc is not None

    # ------------------------------------------------------------------
    # Backend-native commands (Bokeh range operations)
    # ------------------------------------------------------------------

    def get_status(self, request_id: str = "") -> ControlResult:
        """Return current session status."""
        with self._lock:
            active = self._doc is not None
            viewport: Optional[dict] = None
            parameter: Optional[str] = None
            view_mode: Optional[str] = None
            if active and self._master_x_range is not None:
                try:
                    viewport = {
                        "start": self._master_x_range.start,
                        "end": self._master_x_range.end,
                    }
                except Exception:
                    pass
            if active and self._param_select is not None:
                try:
                    parameter = str(self._param_select.value)
                except Exception:
                    pass
            if active and self._view_toggle is not None:
                try:
                    view_mode = "log" if bool(self._view_toggle.active) else "overview"
                except Exception:
                    pass

        return ControlResult.ok(
            message="active" if active else "no active session",
            data={
                "active": active,
                "viewport": viewport,
                "parameter": parameter,
                "view_mode": view_mode,
            },
            request_id=request_id,
        )

    def set_viewport(
        self,
        start: float,
        end: float,
        request_id: str = "",
    ) -> ControlResult:
        """Schedule a viewport range update on the Bokeh IO loop.

        Validates the range before scheduling.
        """
        try:
            start_f, end_f = validate_viewport(start, end)
        except ValueError as exc:
            return ControlResult.error(str(exc), request_id=request_id)

        with self._lock:
            doc = self._doc
            x_range = self._master_x_range

        if doc is None:
            return ControlResult.error("no active session", request_id=request_id)
        if x_range is None:
            return ControlResult.error(
                "master_x_range not registered", request_id=request_id
            )

        def _apply() -> None:
            try:
                x_range.start = start_f
                x_range.end = end_f
                logger.debug(
                    "SessionBridge.set_viewport: applied start=%s end=%s",
                    start_f, end_f,
                )
            except Exception as exc:
                logger.error("SessionBridge.set_viewport callback error: %s", exc)

        doc.add_next_tick_callback(_apply)
        return ControlResult.ok(
            message="Viewport update scheduled",
            data={"start": start_f, "end": end_f},
            request_id=request_id,
        )

    def fit_full_range(self, request_id: str = "") -> ControlResult:
        """Reset the viewport to show the full data range."""
        with self._lock:
            doc = self._doc
            x_range = self._master_x_range

        if doc is None:
            return ControlResult.error("no active session", request_id=request_id)

        def _apply() -> None:
            try:
                if x_range is not None and hasattr(x_range, "reset"):
                    x_range.reset()
                elif x_range is not None:
                    # For DataRange1d, clear explicit bounds to trigger auto-fit
                    if hasattr(x_range, "bounds"):
                        x_range.bounds = "auto"
            except Exception as exc:
                logger.error("SessionBridge.fit_full_range callback error: %s", exc)

        doc.add_next_tick_callback(_apply)
        return ControlResult.ok(message="Fit full range scheduled", request_id=request_id)

    def center_on_timestamp(
        self,
        timestamp: float,
        half_width_ms: float = 1_800_000,
        request_id: str = "",
    ) -> ControlResult:
        """Center the viewport on ``timestamp`` with total width ``2 * half_width_ms``."""
        start_f = timestamp - half_width_ms
        end_f = timestamp + half_width_ms
        try:
            start_f, end_f = validate_viewport(start_f, end_f)
        except ValueError as exc:
            return ControlResult.error(str(exc), request_id=request_id)

        return self.set_viewport(start_f, end_f, request_id=request_id)

    # ------------------------------------------------------------------
    # UI widget-backed commands
    # ------------------------------------------------------------------

    def set_parameter(
        self,
        value: str,
        request_id: str = "",
    ) -> ControlResult:
        """Set the global parameter selector on the active Bokeh document."""
        try:
            value = validate_parameter(value)
        except ValueError as exc:
            return ControlResult.error(str(exc), request_id=request_id)

        with self._lock:
            doc = self._doc
            control_state_source = self._control_state_source

        if doc is None:
            return ControlResult.error("no active session", request_id=request_id)
        if control_state_source is None:
            return ControlResult.error(
                "control_state_source not registered",
                request_id=request_id,
            )

        def _apply() -> None:
            try:
                current = dict(control_state_source.data or {})
                current["parameter"] = [value]
                current["updated_at"] = [int(time.time() * 1000)]
                control_state_source.data = current
                logger.debug("SessionBridge.set_parameter: applied value=%s", value)
            except Exception as exc:
                logger.error("SessionBridge.set_parameter callback error: %s", exc)

        doc.add_next_tick_callback(_apply)
        return ControlResult.ok(
            message=f"Parameter update scheduled: {value}",
            data={"parameter": value},
            request_id=request_id,
        )

    def set_view_mode(
        self,
        value: str,
        request_id: str = "",
    ) -> ControlResult:
        """Set the global log/overview toggle on the active Bokeh document."""
        try:
            value = validate_view_mode(value)
        except ValueError as exc:
            return ControlResult.error(str(exc), request_id=request_id)

        with self._lock:
            doc = self._doc
            control_state_source = self._control_state_source

        if doc is None:
            return ControlResult.error("no active session", request_id=request_id)
        if control_state_source is None:
            return ControlResult.error(
                "control_state_source not registered",
                request_id=request_id,
            )

        def _apply() -> None:
            try:
                current = dict(control_state_source.data or {})
                current["view_mode"] = [value]
                current["updated_at"] = [int(time.time() * 1000)]
                control_state_source.data = current
                logger.debug("SessionBridge.set_view_mode: applied value=%s", value)
            except Exception as exc:
                logger.error("SessionBridge.set_view_mode callback error: %s", exc)

        doc.add_next_tick_callback(_apply)
        return ControlResult.ok(
            message=f"View mode update scheduled: {value}",
            data={"view_mode": value},
            request_id=request_id,
        )

    def apply_workspace(
        self,
        path: Optional[str] = None,
        payload: Optional[dict] = None,
        request_id: str = "",
        timeout: float = 10.0,
    ) -> ControlResult:
        """Send an ``apply_workspace`` command through the JS automation bridge."""
        if path is not None:
            if not os.path.isfile(path):
                return ControlResult.error(
                    f"workspace file not found: {path!r}", request_id=request_id
                )
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    payload = json.load(fh)
            except Exception as exc:
                return ControlResult.error(
                    f"failed to read workspace file: {exc}", request_id=request_id
                )

        if payload is None:
            return ControlResult.error(
                "apply_workspace requires path or payload", request_id=request_id
            )

        return self._send_js_command(
            "apply_workspace",
            {"payload": payload},
            request_id=request_id,
            timeout=timeout,
        )

    def export_static_html(self, request_id: str = "") -> ControlResult:
        """Trigger a static HTML export through the session action source."""
        with self._lock:
            doc = self._doc

        if doc is None:
            return ControlResult.error("no active session", request_id=request_id)

        # Trigger via session_action_source by scheduling on the Bokeh loop.
        # The AppCallbacks handler picks this up.
        def _trigger() -> None:
            try:
                action_src = doc.get_model_by_name("session_action_source")
                if action_src is None:
                    logger.error(
                        "SessionBridge.export_static_html: session_action_source not found"
                    )
                    return
                action_src.data = {
                    "command": ["generate_static_html"],
                    "request_id": [request_id],
                    "payload": [None],
                }
            except Exception as exc:
                logger.error(
                    "SessionBridge.export_static_html callback error: %s", exc
                )

        doc.add_next_tick_callback(_trigger)
        return ControlResult.ok(
            message="Static HTML export requested", request_id=request_id
        )

    # ------------------------------------------------------------------
    # JS-bridge acknowledgement handling (workspace actions only)
    # ------------------------------------------------------------------

    def record_js_result(self, result_dict: dict) -> None:
        """Called by the Python-side ``automation_result_source`` on_change handler.

        Notifies any thread waiting on the corresponding ``request_id``.
        """
        request_id = str(result_dict.get("request_id", ""))
        with self._lock:
            event = self._pending.get(request_id)
        if event is not None:
            self._results[request_id] = result_dict
            event.set()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send_js_command(
        self,
        command: str,
        payload: dict,
        request_id: str,
        timeout: float,
    ) -> ControlResult:
        """Schedule ``command`` on the JS bridge and optionally wait for ack."""
        with self._lock:
            doc = self._doc
            cmd_source = self._automation_command_source

        if doc is None:
            return ControlResult.error("no active session", request_id=request_id)

        if cmd_source is None:
            return ControlResult.error(
                f"automation_command_source not registered; cannot send {command!r}",
                request_id=request_id,
            )

        event: Optional[threading.Event] = None

        if request_id:
            event = threading.Event()
            with self._lock:
                self._pending[request_id] = event

        def _send() -> None:
            try:
                cmd_source.data = {
                    "command": [command],
                    "request_id": [request_id],
                    "payload": [json.dumps(payload)],
                }
                logger.debug(
                    "SessionBridge: sent JS command %r (request_id=%s)",
                    command, request_id,
                )
            except Exception as exc:
                logger.error("SessionBridge._send_js_command callback error: %s", exc)

        doc.add_next_tick_callback(_send)

        if event is not None:
            got_result = event.wait(timeout=timeout)
            with self._lock:
                self._pending.pop(request_id, None)
            if got_result:
                result = self._results.pop(request_id, {})
                if result.get("success"):
                    return ControlResult.ok(
                        message=result.get("message", "OK"),
                        data=result.get("data"),
                        request_id=request_id,
                    )
                return ControlResult.error(
                    result.get("message", "Command failed"),
                    request_id=request_id,
                )
            # Timed out but treat as success (fire-and-forget with best-effort ack)
            logger.warning(
                "SessionBridge: JS ack timed out for %r (request_id=%s)",
                command, request_id,
            )
            return ControlResult.ok(
                message=f"{command} sent (ack timed out)",
                request_id=request_id,
            )

        return ControlResult.ok(
            message=f"{command} command scheduled",
            request_id=request_id,
        )
