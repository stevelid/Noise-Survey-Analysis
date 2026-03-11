"""Tests for noise_survey_analysis.control.control_server.ControlServer"""
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error

from noise_survey_analysis.control.commands import ControlResult
from noise_survey_analysis.control.session_bridge import SessionBridge
from noise_survey_analysis.control.control_server import ControlServer, _dispatch


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

class _FakeRange:
    def __init__(self, start=0.0, end=1.0):
        self.start = start
        self.end = end

    def reset(self):
        pass


class _ImmediateDoc:
    def __init__(self):
        self._models: dict = {}

    def add_next_tick_callback(self, cb):
        cb()

    def get_model_by_name(self, name):
        return self._models.get(name)


# ---------------------------------------------------------------------------
# _dispatch unit tests (no HTTP)
# ---------------------------------------------------------------------------

class TestDispatch(unittest.TestCase):
    def _bridge_with_range(self):
        bridge = SessionBridge()
        x_range = _FakeRange(start=0, end=1)
        bridge.register(_ImmediateDoc(), master_x_range=x_range)
        return bridge, x_range

    def test_dispatch_status(self):
        bridge, _ = self._bridge_with_range()
        result = _dispatch(bridge, "status", {}, "r1")
        self.assertTrue(result.success)

    def test_dispatch_set_viewport(self):
        bridge, x_range = self._bridge_with_range()
        result = _dispatch(bridge, "set_viewport", {"start": 1e12, "end": 2e12}, "r2")
        self.assertTrue(result.success)
        self.assertEqual(x_range.start, 1e12)
        self.assertEqual(x_range.end, 2e12)

    def test_dispatch_fit_full_range(self):
        bridge, _ = self._bridge_with_range()
        result = _dispatch(bridge, "fit_full_range", {}, "r3")
        self.assertTrue(result.success)

    def test_dispatch_center_on_timestamp(self):
        bridge, x_range = self._bridge_with_range()
        ts = 1_710_000_000_000.0
        result = _dispatch(
            bridge, "center_on_timestamp",
            {"timestamp": ts, "half_width_ms": 3_600_000},
            "r4",
        )
        self.assertTrue(result.success)
        self.assertAlmostEqual(x_range.start, ts - 3_600_000)
        self.assertAlmostEqual(x_range.end, ts + 3_600_000)

    def test_dispatch_unknown_command_returns_error(self):
        bridge, _ = self._bridge_with_range()
        result = _dispatch(bridge, "nonexistent_cmd", {}, "r5")
        self.assertFalse(result.success)

    def test_dispatch_export_static_html(self):
        bridge = SessionBridge()
        action_src_data = {}

        class _FakeSrc:
            data = action_src_data

        doc = _ImmediateDoc()
        doc._models["session_action_source"] = _FakeSrc()
        bridge.register(doc)
        result = _dispatch(bridge, "export_static_html", {}, "r6")
        self.assertTrue(result.success)


# ---------------------------------------------------------------------------
# ControlServer lifecycle tests
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Find an available localhost port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _post(port: int, token: str, body: dict, timeout: int = 5) -> dict:
    raw = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/control",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Control-Token": token,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read())


def _get(port: int, path: str, timeout: int = 5) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read())


class TestControlServerLifecycle(unittest.TestCase):
    def test_start_and_stop(self):
        bridge = SessionBridge()
        server = ControlServer(bridge)
        port = _free_port()
        token = server.start(port=port)
        self.assertTrue(server.is_running)
        self.assertIsNotNone(token)
        self.assertEqual(server.port, port)
        server.stop()
        self.assertFalse(server.is_running)

    def test_start_twice_raises(self):
        bridge = SessionBridge()
        server = ControlServer(bridge)
        port = _free_port()
        server.start(port=port)
        try:
            with self.assertRaises(RuntimeError):
                server.start(port=_free_port())
        finally:
            server.stop()

    def test_health_endpoint(self):
        bridge = SessionBridge()
        server = ControlServer(bridge)
        port = _free_port()
        server.start(port=port)
        try:
            resp = _get(port, "/health")
            self.assertEqual(resp["status"], "ok")
            self.assertFalse(resp["active"])
        finally:
            server.stop()

    def test_health_shows_active_when_session_registered(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc())
        server = ControlServer(bridge)
        port = _free_port()
        server.start(port=port)
        try:
            resp = _get(port, "/health")
            self.assertTrue(resp["active"])
        finally:
            server.stop()


class TestControlServerAuth(unittest.TestCase):
    def setUp(self):
        self.bridge = SessionBridge()
        x_range = _FakeRange(start=0, end=1)
        self.bridge.register(_ImmediateDoc(), master_x_range=x_range)
        self.server = ControlServer(self.bridge)
        self.port = _free_port()
        self.token = self.server.start(port=self.port)

    def tearDown(self):
        self.server.stop()

    def test_valid_token_in_header(self):
        result = _post(self.port, self.token, {"command": "status", "request_id": "t1"})
        self.assertTrue(result["success"])

    def test_token_in_body(self):
        body = {"command": "status", "request_id": "t2", "token": self.token}
        result = _post(self.port, "", body)
        self.assertTrue(result["success"])

    def test_wrong_token_rejected(self):
        result = _post(self.port, "wrong-token", {"command": "status"})
        self.assertFalse(result["success"])
        self.assertIn("Unauthorized", result.get("message", ""))

    def test_missing_token_rejected(self):
        result = _post(self.port, "", {"command": "status"})
        self.assertFalse(result["success"])


class TestControlServerCommands(unittest.TestCase):
    def setUp(self):
        self.x_range = _FakeRange(start=0, end=1)
        self.bridge = SessionBridge()
        self.bridge.register(_ImmediateDoc(), master_x_range=self.x_range)
        self.server = ControlServer(self.bridge)
        self.port = _free_port()
        self.token = self.server.start(port=self.port)

    def tearDown(self):
        self.server.stop()

    def _post(self, body):
        return _post(self.port, self.token, body)

    def test_status_command(self):
        result = self._post({"command": "status", "request_id": "s1"})
        self.assertTrue(result["success"])
        self.assertTrue(result["data"]["active"])

    def test_set_viewport_command(self):
        result = self._post({
            "command": "set_viewport",
            "request_id": "sv1",
            "payload": {"start": 1e12, "end": 2e12},
        })
        self.assertTrue(result["success"])
        self.assertAlmostEqual(self.x_range.start, 1e12)
        self.assertAlmostEqual(self.x_range.end, 2e12)

    def test_set_viewport_invalid_range(self):
        result = self._post({
            "command": "set_viewport",
            "payload": {"start": 2e12, "end": 1e12},
        })
        self.assertFalse(result["success"])

    def test_fit_full_range_command(self):
        result = self._post({"command": "fit_full_range"})
        self.assertTrue(result["success"])

    def test_unknown_command_rejected(self):
        result = self._post({"command": "eval_js", "payload": {}})
        self.assertFalse(result["success"])

    def test_missing_command_field(self):
        result = self._post({"payload": {}})
        self.assertFalse(result["success"])

    def test_404_for_unknown_path(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/unknown",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "X-Control-Token": self.token,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
            self.assertFalse(data["success"])
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 404)

    def test_center_on_timestamp(self):
        ts = 1_710_000_000_000.0
        result = self._post({
            "command": "center_on_timestamp",
            "payload": {"timestamp": ts, "half_width_ms": 1_800_000},
        })
        self.assertTrue(result["success"])
        self.assertAlmostEqual(self.x_range.start, ts - 1_800_000)
        self.assertAlmostEqual(self.x_range.end, ts + 1_800_000)


class TestControlServerTokenFile(unittest.TestCase):
    def test_token_file_written_on_start_and_deleted_on_stop(self):
        bridge = SessionBridge()
        server = ControlServer(bridge)
        port = _free_port()
        server.start(port=port)
        # Token file should exist
        token_path = os.path.join(tempfile.gettempdir(), "nsa_control_token.txt")
        self.assertTrue(os.path.isfile(token_path))
        with open(token_path) as fh:
            data = json.load(fh)
        self.assertEqual(data["port"], port)
        self.assertEqual(data["token"], server.token)
        server.stop()
        self.assertFalse(os.path.isfile(token_path))


if __name__ == "__main__":
    unittest.main()
