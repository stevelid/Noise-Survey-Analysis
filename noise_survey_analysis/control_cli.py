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
    nsa-ctl annotations --config noise_survey_config_6645.json      # offline, from the autosave file
    nsa-ctl call add_regions --payload-file suggestions.json        # live: propose regions
    nsa-ctl show --region-id 12 --message "Check this one"

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
import uuid
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
            with open(path, "r", encoding="utf-8-sig") as fh:
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
    # A fresh id per invocation: the browser ignores a command whose request_id
    # repeats the previous one, so a constant id made every second run a no-op.
    body = dict(body)
    body["request_id"] = f"{body.get('request_id') or 'cli'}-{uuid.uuid4().hex[:8]}"
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

    annotations = sub.add_parser("export-annotations", help="Queue a full-resolution annotation CSV export")
    annotations.add_argument("--output", required=True, help="Destination CSV path on the server")
    annotations.add_argument("--include-all-resolutions", action="store_true",
                             help="Include overview rows in addition to full-resolution log rows")
    annotations.add_argument("--background-window-s", type=float, default=300,
                             help="Context duration before and after each area (seconds; default 300)")
    annotations.add_argument("--min-context-s", type=float, default=60,
                             help="Minimum usable pooled context (seconds; default 60)")

    # annotations (offline: reads the autosaved workspace file)
    ann = sub.add_parser(
        "annotations",
        help="Print regions and markers as JSON from <config_stem>.workspace.json (no browser needed)",
    )
    ann.add_argument("--config", help="Job config JSON; reads the .workspace.json file beside it")
    ann.add_argument("--workspace", help="Read this workspace file instead of the config's sibling")
    ann.add_argument("--kind", choices=["region", "marker"], help="Only regions or only markers")
    ann.add_argument("--status", choices=["proposed", "accepted", "rejected"], help="Only this review status")
    ann.add_argument("--source", choices=["user", "agent"], help="Only user or agent annotations")
    ann.add_argument("--start", help="Only items ending after this time (epoch ms or ISO-8601 with offset)")
    ann.add_argument("--end", help="Only items starting before this time (epoch ms or ISO-8601 with offset)")
    ann.add_argument("--time-basis", choices=["source", "display"], default="source",
                     help="Time basis of --start/--end: source (true time in the data files, default) or display (chart axis)")

    # call (live: any control command with a JSON payload)
    call = sub.add_parser(
        "call",
        help="Send any control command with a JSON payload, e.g. add_regions, list_annotations, show",
    )
    call.add_argument("command", help="Command name, e.g. add_regions")
    call_grp = call.add_mutually_exclusive_group()
    call_grp.add_argument("--payload", help="Inline JSON payload")
    call_grp.add_argument("--payload-file", help="Path to a JSON file holding the payload ('-' for stdin)")

    # show (live)
    show = sub.add_parser("show", help="Scroll the dashboard to a region, marker or time window")
    show_grp = show.add_mutually_exclusive_group(required=True)
    show_grp.add_argument("--region-id", type=int)
    show_grp.add_argument("--marker-id", type=int)
    show_grp.add_argument("--start", help="Window start (epoch ms or ISO-8601 with offset); needs --end")
    show.add_argument("--end", help="Window end (epoch ms or ISO-8601 with offset)")
    show.add_argument("--position", help="Position to scroll to")
    show.add_argument("--time-basis", choices=["source", "display"], default=None,
                      help="Time basis of --start/--end: source (default) or display (chart axis)")
    show.add_argument("--message", help="Toast text shown in the dashboard")
    show.add_argument("--no-select", action="store_true", help="Do not select the region or marker")

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


def _cmd_export_annotations(args: argparse.Namespace, port: int, token: str) -> int:
    result = _post(port, token, {
        "command": "export_annotations", "request_id": "cli-export-annotations",
        "payload": {"output_path": os.path.abspath(args.output),
                    "include_all_resolutions": args.include_all_resolutions,
                    "background_window_s": args.background_window_s,
                    "min_context_s": args.min_context_s},
    })
    _print_result(result)
    return 0 if result.get("success") else 1


def _time_arg(text: Optional[str]) -> Any:
    """Command-line time: a bare number is epoch ms, anything else is passed on as ISO-8601."""
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return text


def _control_module(name: str):
    """Import ``control.<name>`` whether this file runs as a module or as a plain script."""
    import importlib

    if __package__:
        return importlib.import_module(f".control.{name}", __package__)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    return importlib.import_module(f"noise_survey_analysis.control.{name}")


def _cmd_annotations(args: argparse.Namespace, port: int, token: str) -> int:
    load_annotations = _control_module("annotation_file").load_annotations
    parse_time_ms = _control_module("annotation_validation").parse_time_ms

    if not args.config and not args.workspace:
        print("Error: --config or --workspace is required", file=sys.stderr)
        return 2
    try:
        filters: dict[str, Any] = {"kind": args.kind, "status": args.status, "source": args.source,
                                   "time_basis": getattr(args, "time_basis", "source")}
        if args.start is not None:
            filters["start"] = parse_time_ms(_time_arg(args.start), "--start")
        if args.end is not None:
            filters["end"] = parse_time_ms(_time_arg(args.end), "--end")
        result = load_annotations(config_path=args.config, workspace_path=args.workspace, **filters)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_call(args: argparse.Namespace, port: int, token: str) -> int:
    payload: Any = {}
    try:
        if args.payload_file:
            text = sys.stdin.read() if args.payload_file == "-" else open(
                args.payload_file, "r", encoding="utf-8-sig").read()
            payload = json.loads(text)
        elif args.payload:
            payload = json.loads(args.payload)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Error: could not read the payload: {exc}", file=sys.stderr)
        return 2
    result = _post(port, token, {"command": args.command, "request_id": f"cli-{args.command}", "payload": payload})
    _print_result(result)
    return 0 if result.get("success") else 1


def _cmd_show(args: argparse.Namespace, port: int, token: str) -> int:
    payload: dict[str, Any] = {}
    if args.region_id is not None:
        payload["region_id"] = args.region_id
    elif args.marker_id is not None:
        payload["marker_id"] = args.marker_id
    else:
        if args.end is None:
            print("Error: --start needs --end", file=sys.stderr)
            return 2
        payload["start"] = _time_arg(args.start)
        payload["end"] = _time_arg(args.end)
        if getattr(args, "time_basis", None):
            payload["time_basis"] = args.time_basis
    if args.position:
        payload["position"] = args.position
    if args.message:
        payload["message"] = args.message
    if args.no_select:
        payload["select"] = False
    result = _post(port, token, {"command": "show", "request_id": "cli-show", "payload": payload})
    _print_result(result)
    return 0 if result.get("success") else 1


_HANDLERS = {
    "annotations": _cmd_annotations,
    "call": _cmd_call,
    "show": _cmd_show,
    "status": _cmd_status,
    "set-viewport": _cmd_set_viewport,
    "set-parameter": _cmd_set_parameter,
    "set-view": _cmd_set_view,
    "apply-workspace": _cmd_apply_workspace,
    "export-static-html": _cmd_export_static,
    "export-annotations": _cmd_export_annotations,
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
