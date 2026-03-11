"""nsa-ctl — command-line client for the Noise Survey Analysis control server.

Usage examples::

    nsa-ctl status
    nsa-ctl set-viewport --start 1710000000000 --end 1710001800000
    nsa-ctl set-parameter --value LAeq
    nsa-ctl set-view --value overview
    nsa-ctl apply-workspace --path C:/path/workspace.json
    nsa-ctl export-static-html
    nsa-ctl fit-full-range
    nsa-ctl center-on --timestamp 1710000900000
    nsa-ctl center-on --timestamp 1710000900000 --half-width-ms 3600000

The CLI discovers the server port and token automatically from the temp file
written by the server on startup.  You can also supply them explicitly via
``--port`` and ``--token``.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.request
import urllib.error
from typing import Any, Optional

_TOKEN_FILE_SUFFIX = "nsa_control_token.txt"
_DEFAULT_PORT = 8765


# ---------------------------------------------------------------------------
# Token / port discovery
# ---------------------------------------------------------------------------

def _discover_server() -> tuple[int, str]:
    """Read port and token from the temp file written by the server.

    Returns ``(port, token)`` or ``(DEFAULT_PORT, "")`` if not found.
    """
    path = os.path.join(tempfile.gettempdir(), _TOKEN_FILE_SUFFIX)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            port = int(data.get("port", _DEFAULT_PORT))
            token = str(data.get("token", ""))
            return port, token
        except Exception:
            pass
    return _DEFAULT_PORT, ""


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _post(port: int, token: str, body: dict) -> dict[str, Any]:
    """POST ``body`` to the control server and return the parsed JSON response."""
    url = f"http://127.0.0.1:{port}/control"
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=raw,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(raw)),
            "X-Control-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_bytes = exc.read()
        try:
            return json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return {"success": False, "message": f"HTTP {exc.code}: {body_bytes.decode('utf-8', errors='replace')}"}
    except urllib.error.URLError as exc:
        return {"success": False, "message": f"Connection failed: {exc.reason}"}


def _get(port: int, path: str) -> dict[str, Any]:
    """GET request (used for /health)."""
    url = f"http://127.0.0.1:{port}{path}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"success": False, "message": str(exc)}


# ---------------------------------------------------------------------------
# Sub-command implementations
# ---------------------------------------------------------------------------

def _cmd_status(args: argparse.Namespace, port: int, token: str) -> int:
    result = _post(port, token, {"command": "status", "request_id": "cli-status"})
    _print_result(result)
    return 0 if result.get("success") else 1


def _cmd_set_viewport(args: argparse.Namespace, port: int, token: str) -> int:
    body = {
        "command": "set_viewport",
        "request_id": "cli-set-viewport",
        "payload": {"start": args.start, "end": args.end},
    }
    result = _post(port, token, body)
    _print_result(result)
    return 0 if result.get("success") else 1


def _cmd_set_parameter(args: argparse.Namespace, port: int, token: str) -> int:
    body = {
        "command": "set_parameter",
        "request_id": "cli-set-parameter",
        "payload": {"value": args.value},
    }
    result = _post(port, token, body)
    _print_result(result)
    return 0 if result.get("success") else 1


def _cmd_set_view(args: argparse.Namespace, port: int, token: str) -> int:
    body = {
        "command": "set_view_mode",
        "request_id": "cli-set-view",
        "payload": {"value": args.value},
    }
    result = _post(port, token, body)
    _print_result(result)
    return 0 if result.get("success") else 1


def _cmd_apply_workspace(args: argparse.Namespace, port: int, token: str) -> int:
    payload: dict[str, Any] = {}
    if args.path:
        payload["path"] = args.path
    elif args.inline:
        try:
            payload["payload"] = json.loads(args.inline)
        except json.JSONDecodeError as exc:
            print(f"Error: --inline is not valid JSON: {exc}", file=sys.stderr)
            return 2
    else:
        print("Error: --path or --inline is required", file=sys.stderr)
        return 2

    body = {
        "command": "apply_workspace",
        "request_id": "cli-apply-workspace",
        "payload": payload,
    }
    result = _post(port, token, body)
    _print_result(result)
    return 0 if result.get("success") else 1


def _cmd_export_static(args: argparse.Namespace, port: int, token: str) -> int:
    body = {
        "command": "export_static_html",
        "request_id": "cli-export-static",
    }
    result = _post(port, token, body)
    _print_result(result)
    return 0 if result.get("success") else 1


def _cmd_fit_full_range(args: argparse.Namespace, port: int, token: str) -> int:
    body = {
        "command": "fit_full_range",
        "request_id": "cli-fit-full-range",
    }
    result = _post(port, token, body)
    _print_result(result)
    return 0 if result.get("success") else 1


def _cmd_center_on(args: argparse.Namespace, port: int, token: str) -> int:
    payload: dict[str, Any] = {"timestamp": args.timestamp}
    if args.half_width_ms is not None:
        payload["half_width_ms"] = args.half_width_ms
    body = {
        "command": "center_on_timestamp",
        "request_id": "cli-center-on",
        "payload": payload,
    }
    result = _post(port, token, body)
    _print_result(result)
    return 0 if result.get("success") else 1


def _print_result(result: dict) -> None:
    print(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nsa-ctl",
        description="Control a running Noise Survey Analysis session.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Control server port (default: auto-discovered or {_DEFAULT_PORT})",
    )
    parser.add_argument(
        "--token",
        type=str,
        default=None,
        help="Session token (default: auto-discovered from temp file)",
    )

    sub = parser.add_subparsers(dest="subcommand", required=True)

    # status
    sub.add_parser("status", help="Query the current session status")

    # set-viewport
    vp = sub.add_parser("set-viewport", help="Set the viewport to a time range")
    vp.add_argument("--start", type=float, required=True, help="Start epoch-ms")
    vp.add_argument("--end", type=float, required=True, help="End epoch-ms")

    # set-parameter
    sp = sub.add_parser("set-parameter", help="Set the active acoustic parameter")
    sp.add_argument("--value", required=True, help="Parameter name, e.g. LAeq")

    # set-view
    sv = sub.add_parser("set-view", help="Set the view mode")
    sv.add_argument("--value", required=True, choices=["log", "overview"])

    # apply-workspace
    aw = sub.add_parser("apply-workspace", help="Apply a saved workspace")
    aw_grp = aw.add_mutually_exclusive_group(required=True)
    aw_grp.add_argument("--path", help="Path to a workspace JSON file")
    aw_grp.add_argument("--inline", help="Inline workspace JSON string")

    # export-static-html
    sub.add_parser("export-static-html", help="Trigger static HTML export")

    # fit-full-range
    sub.add_parser("fit-full-range", help="Reset the viewport to the full data range")

    # center-on
    co = sub.add_parser("center-on", help="Center viewport on a timestamp")
    co.add_argument("--timestamp", type=float, required=True, help="Epoch-ms timestamp")
    co.add_argument(
        "--half-width-ms",
        type=float,
        default=None,
        dest="half_width_ms",
        help="Half width in ms (default: 1 800 000 = 30 min)",
    )

    return parser


_HANDLERS = {
    "status": _cmd_status,
    "set-viewport": _cmd_set_viewport,
    "set-parameter": _cmd_set_parameter,
    "set-view": _cmd_set_view,
    "apply-workspace": _cmd_apply_workspace,
    "export-static-html": _cmd_export_static,
    "fit-full-range": _cmd_fit_full_range,
    "center-on": _cmd_center_on,
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve port / token
    disc_port, disc_token = _discover_server()
    port = args.port if args.port is not None else disc_port
    token = args.token if args.token is not None else disc_token

    handler = _HANDLERS.get(args.subcommand)
    if handler is None:
        print(f"Unknown subcommand: {args.subcommand}", file=sys.stderr)
        return 2

    return handler(args, port, token)


if __name__ == "__main__":
    sys.exit(main())
