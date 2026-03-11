"""Localhost-only HTTP control server.

Listens on ``127.0.0.1:<port>`` and dispatches typed commands to the active
``SessionBridge``.  The server is disabled unless explicitly started with an
opt-in port number.

Security model
--------------
* Binds only to ``127.0.0.1`` — never ``0.0.0.0``.
* Requires explicit opt-in via ``ControlServer.start(port=...)``.
* Generates a random session token on startup; callers must supply it via the
  ``X-Control-Token`` request header or a ``token`` field in the JSON body.
* Accepts only ``application/json`` bodies up to ``MAX_PAYLOAD_BYTES``.
* Only commands in ``ALLOWED_COMMANDS`` are dispatched.
"""
from __future__ import annotations

import json
import logging
import secrets
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional
from urllib.parse import urlparse

from .commands import ALLOWED_COMMANDS, ControlCommand, ControlResult, MAX_PAYLOAD_BYTES
from .session_bridge import SessionBridge
from .validation import validate_command_payload

logger = logging.getLogger(__name__)

# Token file name written to the system temp directory for CLI discovery.
_TOKEN_FILE_SUFFIX = "nsa_control_token.txt"


class _ControlHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the control server."""

    # Injected by ControlServer._make_handler
    bridge: SessionBridge
    token: str

    def log_message(self, fmt: str, *args: Any) -> None:  # type: ignore[override]
        logger.debug("ControlServer: " + fmt, *args)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path != "/control":
            self._send_json(404, {"success": False, "message": "Not found"})
            return

        # --- Read and size-check the body ---
        length_str = self.headers.get("Content-Length", "")
        try:
            content_length = int(length_str) if length_str else 0
        except ValueError:
            self._send_json(400, {"success": False, "message": "Invalid Content-Length"})
            return

        if content_length > MAX_PAYLOAD_BYTES:
            self._send_json(
                413,
                {
                    "success": False,
                    "message": f"Payload too large (max {MAX_PAYLOAD_BYTES} bytes)",
                },
            )
            return

        raw_body = self.rfile.read(content_length) if content_length else b""

        # --- Parse JSON ---
        try:
            body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError as exc:
            self._send_json(400, {"success": False, "message": f"Invalid JSON: {exc}"})
            return

        # --- Token check ---
        header_token = self.headers.get("X-Control-Token", "")
        body_token = str(body.get("token", "")) if isinstance(body, dict) else ""
        supplied_token = header_token or body_token
        if not secrets.compare_digest(supplied_token, self.token):
            self._send_json(401, {"success": False, "message": "Unauthorized"})
            return

        # --- Parse command ---
        try:
            cmd = ControlCommand.from_dict(body)
        except ValueError as exc:
            self._send_json(400, {"success": False, "message": str(exc)})
            return

        # --- Validate payload ---
        try:
            validated_payload = validate_command_payload(cmd.command, cmd.payload or {})
        except ValueError as exc:
            self._send_json(400, {"success": False, "message": str(exc)})
            return

        # --- Dispatch ---
        result = _dispatch(self.bridge, cmd.command, validated_payload, cmd.request_id)
        status = 200 if result.success else 500
        self._send_json(status, result.to_dict())

    def do_GET(self) -> None:  # noqa: N802
        """Simple status endpoint (no token required)."""
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path == "/health":
            self._send_json(
                200,
                {"status": "ok", "active": self.bridge.is_active},
            )
        else:
            self._send_json(404, {"success": False, "message": "Not found"})

    def _send_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _dispatch(
    bridge: SessionBridge,
    command: str,
    payload: dict,
    request_id: str,
) -> ControlResult:
    """Map a validated command to the appropriate ``SessionBridge`` method."""
    try:
        if command == "status":
            return bridge.get_status(request_id=request_id)

        if command == "set_viewport":
            return bridge.set_viewport(
                payload["start"], payload["end"], request_id=request_id
            )

        if command == "center_on_timestamp":
            kwargs: dict[str, Any] = {"request_id": request_id}
            if "half_width_ms" in payload:
                kwargs["half_width_ms"] = payload["half_width_ms"]
            return bridge.center_on_timestamp(payload["timestamp"], **kwargs)

        if command == "fit_full_range":
            return bridge.fit_full_range(request_id=request_id)

        if command == "set_parameter":
            return bridge.set_parameter(payload["value"], request_id=request_id)

        if command == "set_view_mode":
            return bridge.set_view_mode(payload["value"], request_id=request_id)

        if command == "apply_workspace":
            path = payload.get("path")
            inline = payload.get("payload")
            return bridge.apply_workspace(
                path=path, payload=inline, request_id=request_id
            )

        if command == "export_static_html":
            return bridge.export_static_html(request_id=request_id)

        return ControlResult.error(
            f"command {command!r} is not yet implemented", request_id=request_id
        )
    except Exception as exc:
        logger.exception("ControlServer: unexpected error dispatching %r", command)
        return ControlResult.error(
            f"internal error: {exc}", request_id=request_id
        )


class ControlServer:
    """Manages the lifecycle of the localhost control HTTP server.

    Usage::

        bridge = SessionBridge()
        server = ControlServer(bridge)
        token = server.start(port=8765)   # starts in background thread
        # ...
        server.stop()
    """

    def __init__(self, bridge: SessionBridge) -> None:
        self._bridge = bridge
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._token: str = ""

    @property
    def token(self) -> str:
        return self._token

    @property
    def port(self) -> Optional[int]:
        if self._server is not None:
            return self._server.server_address[1]
        return None

    @property
    def is_running(self) -> bool:
        return self._server is not None and self._thread is not None and self._thread.is_alive()

    def start(self, port: int = 8765) -> str:
        """Start the control server on ``127.0.0.1:<port>``.

        Returns the generated session token (also printed to stdout).
        Raises ``RuntimeError`` if the server is already running.
        """
        if self.is_running:
            raise RuntimeError("ControlServer is already running")

        self._token = secrets.token_hex(16)
        handler_cls = self._make_handler()
        self._server = HTTPServer(("127.0.0.1", port), handler_cls)

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="nsa-control-server",
            daemon=True,
        )
        self._thread.start()

        logger.info(
            "ControlServer: listening on http://127.0.0.1:%d — token: %s",
            port,
            self._token,
        )
        print(f"[NSA Control] Listening on http://127.0.0.1:{port}")
        print(f"[NSA Control] Session token: {self._token}")

        # Write token to a temp file for CLI auto-discovery
        self._write_token_file(port)

        return self._token

    def stop(self) -> None:
        """Shut down the control server gracefully."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self._delete_token_file()
        logger.info("ControlServer: stopped")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _make_handler(self) -> type:
        bridge = self._bridge
        token = self._token

        class Handler(_ControlHandler):
            pass

        Handler.bridge = bridge  # type: ignore[attr-defined]
        Handler.token = token  # type: ignore[attr-defined]
        return Handler

    def _write_token_file(self, port: int) -> None:
        import os, tempfile

        path = os.path.join(tempfile.gettempdir(), _TOKEN_FILE_SUFFIX)
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"port": port, "token": self._token}, fh)
            logger.debug("ControlServer: token file written to %s", path)
        except Exception as exc:
            logger.warning("ControlServer: could not write token file: %s", exc)

    def _delete_token_file(self) -> None:
        import os, tempfile

        path = os.path.join(tempfile.gettempdir(), _TOKEN_FILE_SUFFIX)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as exc:
            logger.warning("ControlServer: could not delete token file: %s", exc)
