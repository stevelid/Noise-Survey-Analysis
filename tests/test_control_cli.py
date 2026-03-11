"""Tests for noise_survey_analysis.control_cli"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from noise_survey_analysis.control_cli import (
    build_parser,
    main,
    _discover_server,
    _TOKEN_FILE_SUFFIX,
    _DEFAULT_PORT,
)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------

class TestBuildParser(unittest.TestCase):
    def _parse(self, args):
        return build_parser().parse_args(args)

    def test_status(self):
        args = self._parse(["status"])
        self.assertEqual(args.subcommand, "status")

    def test_set_viewport(self):
        args = self._parse(["set-viewport", "--start", "1710000000000", "--end", "1710003600000"])
        self.assertEqual(args.subcommand, "set-viewport")
        self.assertEqual(args.start, 1710000000000.0)
        self.assertEqual(args.end, 1710003600000.0)

    def test_set_parameter(self):
        args = self._parse(["set-parameter", "--value", "LAeq"])
        self.assertEqual(args.subcommand, "set-parameter")
        self.assertEqual(args.value, "LAeq")

    def test_set_view(self):
        args = self._parse(["set-view", "--value", "log"])
        self.assertEqual(args.subcommand, "set-view")
        self.assertEqual(args.value, "log")

    def test_set_view_choices(self):
        import argparse
        with self.assertRaises(SystemExit):
            self._parse(["set-view", "--value", "invalid"])

    def test_apply_workspace_path(self):
        args = self._parse(["apply-workspace", "--path", "/tmp/ws.json"])
        self.assertEqual(args.subcommand, "apply-workspace")
        self.assertEqual(args.path, "/tmp/ws.json")
        self.assertIsNone(args.inline)

    def test_apply_workspace_inline(self):
        args = self._parse(["apply-workspace", "--inline", '{"appState": {}}'])
        self.assertEqual(args.inline, '{"appState": {}}')
        self.assertIsNone(args.path)

    def test_apply_workspace_requires_path_or_inline(self):
        with self.assertRaises(SystemExit):
            self._parse(["apply-workspace"])

    def test_export_static_html(self):
        args = self._parse(["export-static-html"])
        self.assertEqual(args.subcommand, "export-static-html")

    def test_fit_full_range(self):
        args = self._parse(["fit-full-range"])
        self.assertEqual(args.subcommand, "fit-full-range")

    def test_center_on(self):
        args = self._parse(["center-on", "--timestamp", "1710000000000"])
        self.assertEqual(args.subcommand, "center-on")
        self.assertEqual(args.timestamp, 1710000000000.0)
        self.assertIsNone(args.half_width_ms)

    def test_center_on_with_half_width(self):
        args = self._parse(
            ["center-on", "--timestamp", "1710000000000", "--half-width-ms", "3600000"]
        )
        self.assertEqual(args.half_width_ms, 3600000.0)

    def test_explicit_port_and_token(self):
        args = self._parse(["--port", "9000", "--token", "abc", "status"])
        self.assertEqual(args.port, 9000)
        self.assertEqual(args.token, "abc")


# ---------------------------------------------------------------------------
# Token file discovery
# ---------------------------------------------------------------------------

class TestDiscoverServer(unittest.TestCase):
    def test_returns_defaults_when_no_file(self):
        token_path = os.path.join(tempfile.gettempdir(), _TOKEN_FILE_SUFFIX)
        if os.path.exists(token_path):
            os.unlink(token_path)
        port, token = _discover_server()
        self.assertEqual(port, _DEFAULT_PORT)
        self.assertEqual(token, "")

    def test_reads_token_file(self):
        token_path = os.path.join(tempfile.gettempdir(), _TOKEN_FILE_SUFFIX)
        expected_port = 9876
        expected_token = "my-secret-token"
        try:
            with open(token_path, "w") as fh:
                json.dump({"port": expected_port, "token": expected_token}, fh)
            port, token = _discover_server()
            self.assertEqual(port, expected_port)
            self.assertEqual(token, expected_token)
        finally:
            if os.path.exists(token_path):
                os.unlink(token_path)

    def test_handles_corrupt_token_file(self):
        token_path = os.path.join(tempfile.gettempdir(), _TOKEN_FILE_SUFFIX)
        try:
            with open(token_path, "w") as fh:
                fh.write("not valid json {{{")
            port, token = _discover_server()
            # Should fall back gracefully
            self.assertEqual(port, _DEFAULT_PORT)
            self.assertEqual(token, "")
        finally:
            if os.path.exists(token_path):
                os.unlink(token_path)


# ---------------------------------------------------------------------------
# main() integration with mocked HTTP
# ---------------------------------------------------------------------------

def _make_mock_response(data: dict, status: int = 200):
    """Create a mock urllib response."""
    body = json.dumps(data).encode("utf-8")
    mock = MagicMock()
    mock.read.return_value = body
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    return mock


class TestMainSubcommands(unittest.TestCase):
    def _run(self, argv, mock_response_data, expected_code=0):
        with patch(
            "noise_survey_analysis.control_cli.urllib.request.urlopen",
            return_value=_make_mock_response(mock_response_data),
        ):
            result = main(["--port", "8765", "--token", "tok"] + argv)
        self.assertEqual(result, expected_code)

    def test_status_success(self):
        self._run(["status"], {"success": True, "message": "active", "data": {"active": True}})

    def test_set_viewport_success(self):
        self._run(
            ["set-viewport", "--start", "1710000000000", "--end", "1710003600000"],
            {"success": True, "message": "Viewport update scheduled"},
        )

    def test_set_parameter_success(self):
        self._run(
            ["set-parameter", "--value", "LAeq"],
            {"success": True, "message": "set_parameter command scheduled"},
        )

    def test_set_view_success(self):
        self._run(
            ["set-view", "--value", "overview"],
            {"success": True, "message": "set_view_mode command scheduled"},
        )

    def test_export_static_html_success(self):
        self._run(
            ["export-static-html"],
            {"success": True, "message": "Static HTML export requested"},
        )

    def test_fit_full_range_success(self):
        self._run(["fit-full-range"], {"success": True, "message": "Fit full range scheduled"})

    def test_center_on_success(self):
        self._run(
            ["center-on", "--timestamp", "1710000000000"],
            {"success": True, "message": "Viewport update scheduled"},
        )

    def test_command_failure_returns_1(self):
        self._run(
            ["set-viewport", "--start", "1710000000000", "--end", "1710003600000"],
            {"success": False, "message": "no active session"},
            expected_code=1,
        )

    def test_apply_workspace_inline_valid_json(self):
        self._run(
            ["apply-workspace", "--inline", '{"appState": {}}'],
            {"success": True, "message": "apply_workspace command scheduled"},
        )

    def test_apply_workspace_inline_invalid_json_returns_2(self):
        with patch("noise_survey_analysis.control_cli.urllib.request.urlopen"):
            result = main(
                ["--port", "8765", "--token", "tok",
                 "apply-workspace", "--inline", "{bad json"]
            )
        self.assertEqual(result, 2)


if __name__ == "__main__":
    unittest.main()
