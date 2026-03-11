"""Tests for noise_survey_analysis.control.session_bridge.SessionBridge"""
import json
import os
import tempfile
import threading
import unittest

from noise_survey_analysis.control.session_bridge import SessionBridge


# ---------------------------------------------------------------------------
# Lightweight Bokeh document stub
# ---------------------------------------------------------------------------

class _FakeRange:
    """Minimal stub for a Bokeh Range1d / DataRange1d."""

    def __init__(self, start=0.0, end=1.0):
        self.start = start
        self.end = end
        self.bounds = None
        self._reset_called = False

    def reset(self):
        self._reset_called = True


class _ImmediateDoc:
    """Stub Bokeh document that executes next-tick callbacks immediately."""

    def __init__(self):
        self._callbacks = []
        self._models_by_name: dict = {}

    def add_next_tick_callback(self, cb):
        cb()
        return None

    def get_model_by_name(self, name):
        return self._models_by_name.get(name)


class _FakeCmdSource:
    """Stub ColumnDataSource for automation_command_source."""

    def __init__(self):
        self.data = {}


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestSessionBridgeRegistration(unittest.TestCase):
    def test_initially_not_active(self):
        bridge = SessionBridge()
        self.assertFalse(bridge.is_active)

    def test_register_makes_active(self):
        bridge = SessionBridge()
        doc = _ImmediateDoc()
        bridge.register(doc)
        self.assertTrue(bridge.is_active)

    def test_unregister_clears_active(self):
        bridge = SessionBridge()
        doc = _ImmediateDoc()
        bridge.register(doc)
        bridge.unregister()
        self.assertFalse(bridge.is_active)


class TestSessionBridgeStatus(unittest.TestCase):
    def test_status_no_session(self):
        bridge = SessionBridge()
        result = bridge.get_status()
        self.assertTrue(result.success)
        self.assertFalse(result.data["active"])

    def test_status_with_session_no_range(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc())
        result = bridge.get_status()
        self.assertTrue(result.success)
        self.assertTrue(result.data["active"])
        self.assertIsNone(result.data["viewport"])

    def test_status_with_range(self):
        bridge = SessionBridge()
        x_range = _FakeRange(start=1e12, end=2e12)
        bridge.register(_ImmediateDoc(), master_x_range=x_range)
        result = bridge.get_status()
        self.assertTrue(result.success)
        self.assertEqual(result.data["viewport"]["start"], 1e12)
        self.assertEqual(result.data["viewport"]["end"], 2e12)

    def test_status_echoes_request_id(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc())
        result = bridge.get_status(request_id="r-test")
        self.assertEqual(result.request_id, "r-test")


class TestSessionBridgeSetViewport(unittest.TestCase):
    def test_set_viewport_no_session(self):
        bridge = SessionBridge()
        result = bridge.set_viewport(1e12, 2e12)
        self.assertFalse(result.success)
        self.assertIn("no active session", result.message)

    def test_set_viewport_no_range(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc())
        result = bridge.set_viewport(1e12, 2e12)
        self.assertFalse(result.success)
        self.assertIn("master_x_range not registered", result.message)

    def test_set_viewport_applies(self):
        bridge = SessionBridge()
        x_range = _FakeRange(start=0, end=1)
        bridge.register(_ImmediateDoc(), master_x_range=x_range)
        result = bridge.set_viewport(1e12, 2e12)
        self.assertTrue(result.success)
        self.assertEqual(x_range.start, 1e12)
        self.assertEqual(x_range.end, 2e12)

    def test_set_viewport_invalid_range(self):
        bridge = SessionBridge()
        x_range = _FakeRange()
        bridge.register(_ImmediateDoc(), master_x_range=x_range)
        result = bridge.set_viewport(2e12, 1e12)  # reversed
        self.assertFalse(result.success)

    def test_set_viewport_returns_data(self):
        bridge = SessionBridge()
        x_range = _FakeRange()
        bridge.register(_ImmediateDoc(), master_x_range=x_range)
        result = bridge.set_viewport(1e12, 2e12)
        self.assertEqual(result.data["start"], 1e12)
        self.assertEqual(result.data["end"], 2e12)


class TestSessionBridgeCenterOnTimestamp(unittest.TestCase):
    def test_center_on_timestamp(self):
        bridge = SessionBridge()
        x_range = _FakeRange()
        bridge.register(_ImmediateDoc(), master_x_range=x_range)
        ts = 1_710_000_000_000.0
        half = 3_600_000.0
        result = bridge.center_on_timestamp(ts, half_width_ms=half)
        self.assertTrue(result.success)
        self.assertAlmostEqual(x_range.start, ts - half)
        self.assertAlmostEqual(x_range.end, ts + half)

    def test_center_on_timestamp_default_half_width(self):
        bridge = SessionBridge()
        x_range = _FakeRange()
        bridge.register(_ImmediateDoc(), master_x_range=x_range)
        ts = 1_710_000_000_000.0
        result = bridge.center_on_timestamp(ts)
        self.assertTrue(result.success)
        # Default half-width is 1_800_000 ms
        self.assertAlmostEqual(x_range.start, ts - 1_800_000)
        self.assertAlmostEqual(x_range.end, ts + 1_800_000)


class TestSessionBridgeFitFullRange(unittest.TestCase):
    def test_fit_full_range_no_session(self):
        bridge = SessionBridge()
        result = bridge.fit_full_range()
        self.assertFalse(result.success)

    def test_fit_full_range_with_reset(self):
        bridge = SessionBridge()
        x_range = _FakeRange()
        bridge.register(_ImmediateDoc(), master_x_range=x_range)
        result = bridge.fit_full_range()
        self.assertTrue(result.success)
        self.assertTrue(x_range._reset_called)

    def test_fit_full_range_no_range(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc())
        result = bridge.fit_full_range()
        # Should succeed (schedules callback even if no range)
        self.assertTrue(result.success)


class TestSessionBridgeJsBridgeFallback(unittest.TestCase):
    """When no automation_command_source is registered, JS commands succeed
    (fire-and-forget with a best-effort message)."""

    def test_set_parameter_no_session(self):
        bridge = SessionBridge()
        result = bridge.set_parameter("LAeq")
        self.assertFalse(result.success)

    def test_set_parameter_no_cmd_source_fires_without_error(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc())  # no cmd source
        result = bridge.set_parameter("LAeq", timeout=0.0)
        # With no cmd source a warning is logged but the call doesn't crash.
        # The implementation schedules the callback; since doc is immediate the
        # callback runs, logs a warning, and returns a "scheduled" success.
        self.assertTrue(result.success)

    def test_set_view_mode_invalid_rejects(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc())
        result = bridge.set_view_mode("bad_value", timeout=0.0)
        self.assertFalse(result.success)

    def test_set_view_mode_valid(self):
        bridge = SessionBridge()
        cmd_source = _FakeCmdSource()
        bridge.register(_ImmediateDoc(), automation_command_source=cmd_source)
        result = bridge.set_view_mode("overview", request_id="r1", timeout=0.0)
        self.assertTrue(result.success)
        self.assertEqual(cmd_source.data["command"], ["set_view_mode"])

    def test_set_parameter_valid_writes_cmd_source(self):
        bridge = SessionBridge()
        cmd_source = _FakeCmdSource()
        bridge.register(_ImmediateDoc(), automation_command_source=cmd_source)
        result = bridge.set_parameter("LAeq", request_id="r2", timeout=0.0)
        self.assertTrue(result.success)
        self.assertEqual(cmd_source.data["command"], ["set_parameter"])
        payload_raw = cmd_source.data["payload"][0]
        payload = json.loads(payload_raw)
        self.assertEqual(payload["value"], "LAeq")


class TestSessionBridgeApplyWorkspace(unittest.TestCase):
    def test_apply_workspace_no_path_or_payload(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc())
        result = bridge.apply_workspace()
        self.assertFalse(result.success)

    def test_apply_workspace_missing_file(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc())
        result = bridge.apply_workspace(path="/nonexistent/ws.json")
        self.assertFalse(result.success)

    def test_apply_workspace_from_file(self):
        bridge = SessionBridge()
        cmd_source = _FakeCmdSource()
        bridge.register(_ImmediateDoc(), automation_command_source=cmd_source)

        payload = {"appState": {"x": 1}, "sourceConfigs": []}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            json.dump(payload, fh)
            tmp_path = fh.name
        try:
            result = bridge.apply_workspace(path=tmp_path, request_id="r3", timeout=0.0)
            self.assertTrue(result.success)
        finally:
            os.unlink(tmp_path)

    def test_apply_workspace_inline_payload(self):
        bridge = SessionBridge()
        cmd_source = _FakeCmdSource()
        bridge.register(_ImmediateDoc(), automation_command_source=cmd_source)
        result = bridge.apply_workspace(
            payload={"appState": {"zoom": 1}}, request_id="r4", timeout=0.0
        )
        self.assertTrue(result.success)


class TestSessionBridgeJsAcknowledgement(unittest.TestCase):
    def test_record_js_result_notifies_waiting_thread(self):
        """record_js_result should unblock a waiting set_parameter call."""
        bridge = SessionBridge()
        cmd_source = _FakeCmdSource()
        doc = _ImmediateDoc()

        # Override add_next_tick_callback to be truly async so the thread waits
        call_events = []

        class _DelayedDoc:
            def add_next_tick_callback(self_, cb):
                # Don't call immediately; store it
                call_events.append(cb)
                return None

            def get_model_by_name(self_, name):
                return None

        delayed_doc = _DelayedDoc()
        bridge.register(delayed_doc, automation_command_source=cmd_source)

        results = []

        def _call():
            r = bridge.set_parameter("LAeq", request_id="ack-test", timeout=2.0)
            results.append(r)

        t = threading.Thread(target=_call)
        t.start()
        # Give the thread a moment to block on the event
        import time; time.sleep(0.05)
        # Simulate the JS sending back an ack
        bridge.record_js_result({
            "request_id": "ack-test",
            "success": True,
            "message": "Parameter updated",
        })
        t.join(timeout=3.0)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertEqual(results[0].message, "Parameter updated")

    def test_record_js_result_failure_ack(self):
        bridge = SessionBridge()
        cmd_source = _FakeCmdSource()

        class _DelayedDoc:
            def add_next_tick_callback(self_, cb):
                return None
            def get_model_by_name(self_, n):
                return None

        bridge.register(_DelayedDoc(), automation_command_source=cmd_source)
        results = []

        def _call():
            r = bridge.set_view_mode("log", request_id="fail-ack", timeout=2.0)
            results.append(r)

        t = threading.Thread(target=_call)
        t.start()
        import time; time.sleep(0.05)
        bridge.record_js_result({
            "request_id": "fail-ack",
            "success": False,
            "message": "Parameter not found",
        })
        t.join(timeout=3.0)
        self.assertFalse(results[0].success)
        self.assertIn("not found", results[0].message)


class TestSessionBridgeExportStaticHtml(unittest.TestCase):
    def test_export_static_html_no_session(self):
        bridge = SessionBridge()
        result = bridge.export_static_html()
        self.assertFalse(result.success)

    def test_export_static_html_triggers_action_source(self):
        bridge = SessionBridge()
        action_source = _FakeCmdSource()
        action_source.data = {}

        doc = _ImmediateDoc()
        doc._models_by_name["session_action_source"] = action_source
        bridge.register(doc)
        result = bridge.export_static_html(request_id="exp-1")
        self.assertTrue(result.success)
        self.assertEqual(action_source.data["command"], ["generate_static_html"])
        self.assertEqual(action_source.data["request_id"], ["exp-1"])


if __name__ == "__main__":
    unittest.main()
