"""Tests for noise_survey_analysis.control.commands"""
import unittest

from noise_survey_analysis.control.commands import (
    ALLOWED_COMMANDS,
    ALLOWED_VIEW_MODES,
    MAX_PAYLOAD_BYTES,
    ControlCommand,
    ControlResult,
)


class TestAllowedConstants(unittest.TestCase):
    def test_allowed_commands_not_empty(self):
        self.assertGreater(len(ALLOWED_COMMANDS), 0)

    def test_core_commands_present(self):
        for cmd in ("status", "set_viewport", "set_parameter", "set_view_mode",
                    "apply_workspace", "export_static_html", "fit_full_range",
                    "center_on_timestamp"):
            self.assertIn(cmd, ALLOWED_COMMANDS)

    def test_unsafe_commands_absent(self):
        for cmd in ("eval_js", "set_raw_state", "dispatch_action"):
            self.assertNotIn(cmd, ALLOWED_COMMANDS)

    def test_allowed_view_modes(self):
        self.assertIn("log", ALLOWED_VIEW_MODES)
        self.assertIn("overview", ALLOWED_VIEW_MODES)

    def test_max_payload_bytes_reasonable(self):
        self.assertGreater(MAX_PAYLOAD_BYTES, 0)
        self.assertLessEqual(MAX_PAYLOAD_BYTES, 10 * 1024 * 1024)  # <= 10 MiB


class TestControlCommand(unittest.TestCase):
    def test_basic_creation(self):
        cmd = ControlCommand(command="status")
        self.assertEqual(cmd.command, "status")
        self.assertEqual(cmd.request_id, "")
        self.assertEqual(cmd.payload, {})

    def test_to_dict(self):
        cmd = ControlCommand(command="set_parameter", request_id="r1", payload={"value": "LAeq"})
        d = cmd.to_dict()
        self.assertEqual(d["command"], "set_parameter")
        self.assertEqual(d["request_id"], "r1")
        self.assertEqual(d["payload"], {"value": "LAeq"})

    def test_from_dict_minimal(self):
        cmd = ControlCommand.from_dict({"command": "status"})
        self.assertEqual(cmd.command, "status")
        self.assertEqual(cmd.request_id, "")
        self.assertEqual(cmd.payload, {})

    def test_from_dict_full(self):
        cmd = ControlCommand.from_dict({
            "command": "set_viewport",
            "request_id": "abc",
            "payload": {"start": 1e12, "end": 2e12},
        })
        self.assertEqual(cmd.command, "set_viewport")
        self.assertEqual(cmd.request_id, "abc")
        self.assertEqual(cmd.payload["start"], 1e12)

    def test_from_dict_missing_command(self):
        with self.assertRaises(ValueError):
            ControlCommand.from_dict({"request_id": "r1"})

    def test_from_dict_non_dict(self):
        with self.assertRaises(ValueError):
            ControlCommand.from_dict("not a dict")

    def test_from_dict_empty_command(self):
        with self.assertRaises(ValueError):
            ControlCommand.from_dict({"command": ""})

    def test_roundtrip(self):
        original = ControlCommand(
            command="set_view_mode", request_id="xyz", payload={"value": "log"}
        )
        restored = ControlCommand.from_dict(original.to_dict())
        self.assertEqual(restored.command, original.command)
        self.assertEqual(restored.request_id, original.request_id)
        self.assertEqual(restored.payload, original.payload)


class TestControlResult(unittest.TestCase):
    def test_ok_factory(self):
        r = ControlResult.ok(message="Done", data={"x": 1}, request_id="r1")
        self.assertTrue(r.success)
        self.assertEqual(r.message, "Done")
        self.assertEqual(r.data, {"x": 1})
        self.assertEqual(r.request_id, "r1")

    def test_error_factory(self):
        r = ControlResult.error("Something went wrong", request_id="r2")
        self.assertFalse(r.success)
        self.assertEqual(r.message, "Something went wrong")
        self.assertIsNone(r.data)
        self.assertEqual(r.request_id, "r2")

    def test_to_dict_success(self):
        r = ControlResult.ok("OK", data={"start": 1e12}, request_id="r3")
        d = r.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["message"], "OK")
        self.assertEqual(d["data"]["start"], 1e12)
        self.assertEqual(d["request_id"], "r3")

    def test_to_dict_error(self):
        r = ControlResult.error("fail", request_id="r4")
        d = r.to_dict()
        self.assertFalse(d["success"])
        self.assertEqual(d["request_id"], "r4")
        self.assertIsNone(d["data"])

    def test_ok_defaults(self):
        r = ControlResult.ok()
        self.assertTrue(r.success)
        self.assertEqual(r.message, "OK")
        self.assertIsNone(r.data)
        self.assertEqual(r.request_id, "")


if __name__ == "__main__":
    unittest.main()
