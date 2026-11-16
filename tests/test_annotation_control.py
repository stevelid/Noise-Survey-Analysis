"""Annotation commands of the control API: validation, bridge round trip, HTTP route, offline CLI."""
import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from noise_survey_analysis import control_cli
from noise_survey_analysis.control.annotation_file import (
    annotations_from_workspace,
    load_annotations,
    workspace_path_for_config,
)
from noise_survey_analysis.control.annotation_validation import (
    MAX_BATCH_ITEMS,
    parse_time_ms,
    validate_annotation_command,
)
from noise_survey_analysis.control.commands import ALLOWED_COMMANDS
from noise_survey_analysis.control.control_server import ControlServer, _dispatch
from noise_survey_analysis.control.session_bridge import SessionBridge
from noise_survey_analysis.control.validation import validate_command_payload

POSITIONS = ["6645-4", "6645-5A", "6645-971-2"]
T0 = 1_794_219_402_000  # 2026-11-09T10:16:42Z
ISO = "2026-11-09T10:16:42Z"


def region(**overrides):
    item = {"position": "6645-4", "start": ISO, "end": "2026-11-09T10:17:02Z", "note": "Dog bark"}
    item.update(overrides)
    return item


class ParseTimeTests(unittest.TestCase):
    def test_epoch_ms_and_iso_with_offset_agree(self):
        self.assertEqual(parse_time_ms(T0), float(T0))
        self.assertEqual(parse_time_ms(ISO), float(T0))
        self.assertEqual(parse_time_ms("2026-11-09T10:16:42+00:00"), float(T0))
        self.assertEqual(parse_time_ms("2026-11-09T11:16:42+01:00"), float(T0))
        self.assertEqual(parse_time_ms("2026-11-09 10:16:42.500Z"), float(T0 + 500))
        self.assertEqual(parse_time_ms("2026-11-09T05:46:42-0430"), float(T0))

    def test_naive_times_are_rejected(self):
        for text in ("2026-11-09T10:16:42", "2026-11-09 10:16", "2026-11-09", "10:16:42Z", "yesterday"):
            with self.assertRaises(ValueError, msg=text):
                parse_time_ms(text)
        with self.assertRaisesRegex(ValueError, "no UTC offset"):
            parse_time_ms("2026-11-09T10:16:42")

    def test_bad_numbers_are_rejected(self):
        for value in (True, None, float("nan"), float("inf"), 1_794_219_402, [], {}):
            with self.assertRaises(ValueError, msg=repr(value)):
                parse_time_ms(value)
        with self.assertRaisesRegex(ValueError, "seconds"):
            parse_time_ms(1_794_219_402)

    def test_invalid_calendar_date_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_time_ms("2026-13-09T10:16:42Z")


class AddRegionsValidationTests(unittest.TestCase):
    def validate(self, payload, positions=POSITIONS):
        return validate_command_payload("add_regions", payload, positions=positions)

    def test_defaults_to_proposed_and_normalises_times(self):
        out = self.validate({"agent": "yamnet", "regions": [region(confidence=0.82, client_ref="a")]})
        self.assertEqual(out["agent"], {"name": "yamnet", "runId": None})
        item = out["regions"][0]
        self.assertEqual(item["status"], "proposed")
        self.assertEqual(item["areas"], [{"start": float(T0), "end": float(T0 + 20_000)}])
        self.assertEqual(item["confidence"], 0.82)
        self.assertEqual(item["client_ref"], "a")

    def test_agent_object_with_run_id(self):
        out = self.validate({"agent": {"name": "claude", "run_id": "r1"}, "regions": [region()]})
        self.assertEqual(out["agent"], {"name": "claude", "runId": "r1"})

    def test_areas_and_meter_states(self):
        item = region(meter_states={"6645-5A": "present"})
        del item["start"], item["end"]
        item["areas"] = [{"start": T0, "end": T0 + 1000}, {"start": T0 + 5000, "end": T0 + 9000}]
        out = self.validate({"agent": "a", "regions": [item]})
        self.assertEqual(len(out["regions"][0]["areas"]), 2)
        self.assertEqual(out["regions"][0]["meter_states"], {"6645-5A": "present"})

    def test_rejects_naive_time(self):
        with self.assertRaisesRegex(ValueError, "regions\\[0\\].*no UTC offset"):
            self.validate({"agent": "a", "regions": [region(start="2026-11-09T10:16:42")]})

    def test_rejects_start_not_before_end(self):
        with self.assertRaisesRegex(ValueError, "start must be before end"):
            self.validate({"agent": "a", "regions": [region(end=ISO)]})

    def test_rejects_oversize_batch(self):
        batch = [region(client_ref=str(i)) for i in range(MAX_BATCH_ITEMS + 1)]
        with self.assertRaisesRegex(ValueError, "limit is 500"):
            self.validate({"agent": "a", "regions": batch})
        self.validate({"agent": "a", "regions": batch[:MAX_BATCH_ITEMS]})

    def test_rejects_unknown_position_only_when_positions_known(self):
        with self.assertRaisesRegex(ValueError, "not a known position"):
            self.validate({"agent": "a", "regions": [region(position="6645-9")]})
        self.validate({"agent": "a", "regions": [region(position="6645-9")]}, positions=None)
        self.validate({"agent": "a", "regions": [region(position="6645-9")]}, positions=[])

    def test_rejects_unknown_meter_state_position(self):
        with self.assertRaisesRegex(ValueError, "not a known position"):
            self.validate({"agent": "a", "regions": [region(meter_states={"nope": "present"})]})

    def test_confidence_range_and_type(self):
        for bad in (-0.1, 1.01, "0.5", True, float("nan")):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.validate({"agent": "a", "regions": [region(confidence=bad)]})
        for ok in (0, 1, 0.5, None):
            self.validate({"agent": "a", "regions": [region(confidence=ok)]})

    def test_status_on_add_cannot_be_rejected(self):
        with self.assertRaises(ValueError):
            self.validate({"agent": "a", "regions": [region(status="rejected")]})
        out = self.validate({"agent": "a", "regions": [region(status="accepted")]})
        self.assertEqual(out["regions"][0]["status"], "accepted")

    def test_unknown_fields_and_missing_agent(self):
        with self.assertRaisesRegex(ValueError, "unknown field"):
            self.validate({"agent": "a", "regions": [region(starts=1)]})
        with self.assertRaisesRegex(ValueError, "agent is required"):
            self.validate({"regions": [region()]})
        with self.assertRaisesRegex(ValueError, "unknown field"):
            self.validate({"agent": "a", "regions": [region()], "extra": 1})

    def test_text_limits_and_duplicate_client_refs(self):
        with self.assertRaisesRegex(ValueError, "limit is 2000"):
            self.validate({"agent": "a", "regions": [region(rationale="x" * 2001)]})
        with self.assertRaisesRegex(ValueError, "used twice"):
            self.validate({"agent": "a", "regions": [region(client_ref="z"), region(client_ref="z")]})

    def test_time_range_context(self):
        rng = (float(T0) - 1000, float(T0) + 1000)
        with self.assertRaisesRegex(ValueError, "outside the survey range"):
            validate_command_payload("add_regions", {"agent": "a", "regions": [region()]},
                                     positions=POSITIONS, time_range=rng)


class OtherCommandValidationTests(unittest.TestCase):
    def test_every_annotation_command_is_allowed(self):
        for name in ("list_annotations", "add_regions", "update_region", "delete_regions",
                     "add_markers", "update_marker", "delete_markers", "show"):
            self.assertIn(name, ALLOWED_COMMANDS)

    def test_update_region(self):
        out = validate_command_payload(
            "update_region", {"id": 3, "changes": {"note": "x", "status": "accepted", "end": T0 + 5000}})
        self.assertEqual(out, {"id": 3, "changes": {"note": "x", "status": "accepted", "end": float(T0 + 5000)}})
        with self.assertRaises(ValueError):
            validate_command_payload("update_region", {"id": 3, "changes": {}})
        with self.assertRaises(ValueError):
            validate_command_payload("update_region", {"id": 3, "changes": {"position": "6645-4"}})
        with self.assertRaises(ValueError):
            validate_command_payload("update_region", {"id": 0, "changes": {"note": "x"}})
        with self.assertRaises(ValueError):
            validate_command_payload("update_region", {"id": 3, "changes": {"start": T0 + 9, "end": T0}})

    def test_delete(self):
        self.assertEqual(validate_command_payload("delete_regions", {"ids": [1, 2]}),
                         {"ids": [1, 2], "force": False})
        self.assertTrue(validate_command_payload("delete_markers", {"ids": [1], "force": True})["force"])
        for bad in ({"ids": []}, {"ids": [1, 1]}, {"ids": ["a"]}, {"ids": [1], "force": "yes"},
                    {"ids": list(range(1, 502))}):
            with self.assertRaises(ValueError, msg=str(bad)[:40]):
                validate_command_payload("delete_regions", bad)

    def test_markers(self):
        out = validate_command_payload(
            "add_markers",
            {"agent": "a", "markers": [{"timestamp": ISO, "position": "6645-4", "note": "n", "confidence": 0.4}]},
            positions=POSITIONS)
        self.assertEqual(out["markers"][0]["timestamp"], float(T0))
        self.assertEqual(out["markers"][0]["status"], "proposed")
        with self.assertRaisesRegex(ValueError, "no UTC offset"):
            validate_command_payload("add_markers", {"agent": "a", "markers": [{"timestamp": "2026-11-09T10:16"}]})
        with self.assertRaisesRegex(ValueError, "repeats"):
            validate_command_payload("add_markers", {"agent": "a", "markers": [{"timestamp": T0}, {"timestamp": T0}]})
        with self.assertRaises(ValueError):
            validate_command_payload("add_markers", {"agent": "a", "markers": [{"timestamp": T0, "position": "x"}]},
                                     positions=POSITIONS)
        self.assertEqual(
            validate_command_payload("update_marker", {"id": 2, "changes": {"status": "rejected"}})["changes"],
            {"status": "rejected"})

    def test_show_needs_exactly_one_target(self):
        self.assertEqual(validate_command_payload("show", {"region_id": 4, "message": "look"}),
                         {"region_id": 4, "message": "look"})
        out = validate_command_payload("show", {"start": ISO, "end": T0 + 60_000, "position": "6645-4"},
                                       positions=POSITIONS)
        self.assertEqual(out["end"], float(T0 + 60_000))
        for bad in ({}, {"region_id": 1, "marker_id": 2}, {"region_id": 1, "start": T0, "end": T0 + 1},
                    {"start": T0}, {"start": T0, "end": T0}, {"region_id": 1, "select": "yes"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                validate_command_payload("show", bad)

    def test_list_annotations(self):
        self.assertEqual(validate_command_payload("list_annotations", {}), {})
        out = validate_command_payload("list_annotations", {"kind": "region", "status": "proposed", "start": ISO})
        self.assertEqual(out, {"kind": "region", "status": "proposed", "start": float(T0)})
        with self.assertRaises(ValueError):
            validate_command_payload("list_annotations", {"kind": "classification"})

    def test_export_annotations_accepts_include_proposed(self):
        out = validate_command_payload("export_annotations", {"include_proposed": True})
        self.assertTrue(out["include_proposed"])
        self.assertNotIn("include_proposed", validate_command_payload("export_annotations", {}))
        with self.assertRaisesRegex(ValueError, "include_proposed"):
            validate_command_payload("export_annotations", {"include_proposed": "yes"})

    def test_direct_dispatch_function_rejects_foreign_commands(self):
        with self.assertRaises(ValueError):
            validate_annotation_command("status", {})


class _Doc:
    def add_next_tick_callback(self, callback):
        callback()


class _FakeBrowser:
    """Stands in for the dashboard tab: answers each command like the JS handlers would."""

    def __init__(self, bridge, responder=None):
        self.bridge = bridge
        self.responder = responder or (lambda command, payload: {"success": True, "message": "ok", "data": {}})
        self.received = []
        self._data = {}

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value
        command = value["command"][0]
        payload = json.loads(value["payload"][0])
        self.received.append((command, payload))
        self.bridge.record_js_result({"request_id": value["request_id"][0], **self.responder(command, payload)})


class BridgeRoundTripTests(unittest.TestCase):
    def make(self, responder=None, **context):
        bridge = SessionBridge()
        browser = _FakeBrowser(bridge, responder)
        bridge.register(_Doc(), automation_command_source=browser, **context)
        return bridge, browser

    def test_add_regions_round_trip_returns_handler_data(self):
        def responder(command, payload):
            return {"success": True, "message": "Added 1", "data": {"ids": [7], "by_client_ref": {"a": 7}}}

        bridge, browser = self.make(responder, positions=POSITIONS)
        payload = validate_command_payload(
            "add_regions", {"agent": "yamnet", "regions": [region(client_ref="a")]},
            positions=bridge.get_context("positions"))
        result = _dispatch(bridge, "add_regions", payload, "rid")
        self.assertTrue(result.success)
        self.assertEqual(result.data, {"ids": [7], "by_client_ref": {"a": 7}})
        command, sent = browser.received[0]
        self.assertEqual(command, "add_regions")
        self.assertEqual(sent["regions"][0]["status"], "proposed")
        self.assertEqual(sent["agent"]["name"], "yamnet")

    def test_failure_from_browser_is_failure(self):
        bridge, _ = self.make(lambda c, p: {"success": False, "message": "refused"})
        result = _dispatch(bridge, "delete_regions", {"ids": [1], "force": False}, "r")
        self.assertFalse(result.success)
        self.assertEqual(result.message, "refused")

    def test_no_browser_acknowledgement_is_failure_for_read_and_write(self):
        bridge = SessionBridge()

        class Silent:
            data = {}

        bridge.register(_Doc(), automation_command_source=Silent())
        for command, mutating in (("list_annotations", False), ("add_regions", True)):
            result = bridge.annotation_command(command, {}, timeout=0.05)
            self.assertFalse(result.success, command)
            if mutating:
                self.assertIn("may not have been applied", result.message)

    def test_no_session_is_failure(self):
        result = SessionBridge().annotation_command("list_annotations", {})
        self.assertFalse(result.success)
        self.assertIn("no active session", result.message)

    def test_bridge_refuses_other_commands(self):
        bridge, _ = self.make()
        self.assertFalse(bridge.annotation_command("status", {}).success)


class HttpRouteTests(unittest.TestCase):
    def setUp(self):
        self.bridge = SessionBridge()
        self.browser = _FakeBrowser(self.bridge, lambda c, p: {"success": True, "message": c, "data": {"echo": p}})
        self.bridge.register(_Doc(), automation_command_source=self.browser, positions=POSITIONS)
        self.server = ControlServer(self.bridge)
        with contextlib.redirect_stdout(io.StringIO()):
            self.server.start(port=0)
        self.addCleanup(self.server.stop)

    def post(self, command, payload):
        body = json.dumps({"command": command, "payload": payload}).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.port}/control", data=body, method="POST",
            headers={"Content-Type": "application/json", "X-Control-Token": self.server.token})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_valid_command_reaches_the_browser(self):
        status, body = self.post("add_regions", {"agent": "a", "regions": [region()]})
        self.assertEqual(status, 200)
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["echo"]["regions"][0]["areas"][0]["start"], float(T0))

    def test_registered_positions_are_enforced(self):
        status, body = self.post("add_regions", {"agent": "a", "regions": [region(position="zzz")]})
        self.assertEqual(status, 400)
        self.assertIn("not a known position", body["message"])
        self.assertEqual(self.browser.received, [])

    def test_naive_time_and_oversize_batch_are_400(self):
        status, _ = self.post("add_regions", {"agent": "a", "regions": [region(start="2026-11-09T10:16:42")]})
        self.assertEqual(status, 400)
        status, _ = self.post("add_regions", {"agent": "a", "regions": [region(client_ref=str(i)) for i in range(501)]})
        self.assertEqual(status, 400)


class WorkspaceFileTests(unittest.TestCase):
    WORKSPACE = {
        "version": 2,
        "savedAt": "2026-11-09T12:00:00Z",
        "appState": {
            "view": {"availablePositions": POSITIONS, "positionChartOffsets": {"6645-4": 0}},
            "regions": {
                "byId": {
                    "1": {"id": 1, "positionId": "6645-4", "start": T0, "end": T0 + 20_000, "note": "mine",
                          "categoryId": "plant", "categoryIds": ["plant"], "meterStates": {"6645-4": "present"},
                          "areas": [{"start": T0, "end": T0 + 20_000}]},
                    "2": {"id": 2, "positionId": "6645-5A", "start": T0 + 60_000, "end": T0 + 90_000,
                          "note": "dog", "categoryId": "dog", "categoryIds": ["dog"], "meterStates": {},
                          "areas": [{"start": T0 + 60_000, "end": T0 + 90_000}], "source": "agent",
                          "status": "proposed", "rationale": "Barks at 1 kHz", "confidence": 0.82,
                          "agent": {"name": "yamnet", "runId": "r1"}, "createdAt": "2026-11-09T11:00:00Z"},
                    "3": {"id": 3, "positionId": "6645-4", "start": T0 + 200_000, "end": T0 + 210_000,
                          "note": "no", "categoryId": "other", "source": "agent", "status": "rejected",
                          "areas": [{"start": T0 + 200_000, "end": T0 + 210_000}]},
                },
                "allIds": [1, 2, 3],
                "categories": {"byId": {"dog": {"id": "dog", "label": "Dog bark", "color": "#fff"}}, "allIds": ["dog"]},
            },
            "markers": {
                "byId": {"1": {"id": 1, "timestamp": T0 + 5000, "positionId": "6645-4", "note": "m",
                               "source": "agent", "status": "proposed", "confidence": 0.5}},
                "allIds": [1],
            },
        },
    }

    def test_annotations_from_workspace(self):
        out = annotations_from_workspace(self.WORKSPACE)
        self.assertEqual([r["id"] for r in out["regions"]], [1, 2, 3])
        self.assertEqual(out["regions"][0]["source"], "user")
        self.assertEqual(out["regions"][0]["status"], "accepted")
        suggestion = out["regions"][1]
        self.assertEqual(suggestion["category_label"], "Dog bark")
        self.assertEqual(suggestion["agent"], {"name": "yamnet", "run_id": "r1"})
        self.assertEqual(suggestion["start_iso"], "2026-11-09T10:17:42.000Z")
        self.assertEqual(out["counts"]["regions"], {"proposed": 1, "accepted": 1, "rejected": 1})
        self.assertEqual(out["markers"][0]["timestamp_iso"], "2026-11-09T10:16:47.000Z")
        self.assertEqual(out["positions"], POSITIONS)

    def test_filters(self):
        self.assertEqual([r["id"] for r in annotations_from_workspace(self.WORKSPACE, status="proposed")["regions"]], [2])
        self.assertEqual(annotations_from_workspace(self.WORKSPACE, kind="marker")["regions"], [])
        self.assertEqual(annotations_from_workspace(self.WORKSPACE, source="user")["markers"], [])
        windowed = annotations_from_workspace(self.WORKSPACE, start=T0 + 50_000, end=T0 + 100_000)
        self.assertEqual([r["id"] for r in windowed["regions"]], [2])

    def test_workspace_path_and_cli(self):
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "noise_survey_config_6645.json"
            config.write_text("{}", encoding="utf-8")
            expected = Path(folder) / "noise_survey_config_6645.workspace.json"
            self.assertEqual(workspace_path_for_config(config), expected)
            with self.assertRaises(FileNotFoundError):
                load_annotations(config_path=config)
            expected.write_text(json.dumps(self.WORKSPACE), encoding="utf-8")

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = control_cli.main(["annotations", "--config", str(config), "--status", "proposed"])
            self.assertEqual(code, 0)
            printed = json.loads(out.getvalue())
            self.assertEqual([r["id"] for r in printed["regions"]], [2])
            self.assertEqual(printed["workspace_file"], str(expected))

            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = control_cli.main(["annotations", "--config", str(Path(folder) / "missing.json")])
            self.assertEqual(code, 1)
            self.assertIn("no saved workspace", err.getvalue())

    def test_cli_requires_config_or_workspace(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(control_cli.main(["annotations"]), 2)

    def test_cli_rejects_naive_time_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "w.workspace.json"
            path.write_text(json.dumps(self.WORKSPACE), encoding="utf-8")
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                code = control_cli.main(["annotations", "--workspace", str(path), "--start", "2026-11-09T10:00:00"])
            self.assertEqual(code, 1)
            self.assertIn("no UTC offset", err.getvalue())


class CliLiveCommandTests(unittest.TestCase):
    def test_call_and_show_post_the_right_bodies(self):
        sent = []

        def fake_post(port, token, body):
            sent.append(body)
            return {"success": True, "message": "ok"}

        original = control_cli._post
        control_cli._post = fake_post
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                control_cli.main(["--port", "1", "--token", "t", "call", "list_annotations", "--payload",
                                  '{"status": "proposed"}'])
                control_cli.main(["--port", "1", "--token", "t", "show", "--region-id", "4", "--message", "Look"])
                control_cli.main(["--port", "1", "--token", "t", "show", "--start", ISO, "--end", "123"])
        finally:
            control_cli._post = original
        self.assertEqual(sent[0]["command"], "list_annotations")
        self.assertEqual(sent[0]["payload"], {"status": "proposed"})
        self.assertEqual(sent[1]["payload"], {"region_id": 4, "message": "Look"})
        self.assertEqual(sent[2]["payload"], {"start": ISO, "end": 123.0})


class TimeBasisTests(unittest.TestCase):
    def test_validation_accepts_and_passes_time_basis(self):
        out = validate_command_payload("add_regions", {"agent": "a", "time_basis": "display", "regions": [region()]},
                                       positions=POSITIONS)
        self.assertEqual(out["time_basis"], "display")
        self.assertNotIn("time_basis", validate_command_payload("add_regions", {"agent": "a", "regions": [region()]},
                                                                positions=POSITIONS))
        for command, payload in (("list_annotations", {}), ("show", {"start": T0, "end": T0 + 1}),
                                 ("update_region", {"id": 1, "changes": {"note": "x"}}),
                                 ("add_markers", {"agent": "a", "markers": [{"timestamp": T0}]})):
            self.assertEqual(validate_command_payload(command, {**payload, "time_basis": "source"})["time_basis"], "source")
            with self.assertRaises(ValueError):
                validate_command_payload(command, {**payload, "time_basis": "local"})

    def test_workspace_records_carry_source_times_and_filter_on_source_by_default(self):
        workspace = {"appState": {
            "view": {"availablePositions": ["P1"], "positionChartOffsets": {"P1": 2000}},
            "regions": {"byId": {"1": {"id": 1, "positionId": "P1", "start": T0 + 2000, "end": T0 + 3000,
                                       "areas": [{"start": T0 + 2000, "end": T0 + 3000}]}}, "allIds": [1]},
            "markers": {"byId": {"1": {"id": 1, "positionId": "P1", "timestamp": T0 + 2500}}, "allIds": [1]}}}
        out = annotations_from_workspace(workspace)
        self.assertEqual((out["regions"][0]["start"], out["regions"][0]["source_start"]), (T0 + 2000, T0))
        self.assertEqual(out["regions"][0]["source_areas"], [{"start": T0, "end": T0 + 1000}])
        self.assertEqual(out["markers"][0]["source_timestamp"], T0 + 500)
        self.assertEqual(len(annotations_from_workspace(workspace, start=T0, end=T0 + 100)["regions"]), 1)
        self.assertEqual(len(annotations_from_workspace(workspace, start=T0, end=T0 + 100, time_basis="display")["regions"]), 0)
        with self.assertRaises(ValueError):
            annotations_from_workspace(workspace, time_basis="local")


if __name__ == "__main__":
    unittest.main()
