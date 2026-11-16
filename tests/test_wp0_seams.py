"""Tests for the WP0 extension points (JS manifest, static payload, session-action registry,
bridge context/send_command, single-embed JS bundle)."""
import unittest
import numpy as np
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from bokeh.events import DocumentReady
from bokeh.models import ColumnDataSource, CustomJS

from noise_survey_analysis.control.session_bridge import SessionBridge
from noise_survey_analysis.core import app_callbacks
from noise_survey_analysis.core.app_callbacks import AppCallbacks, register_session_action
from noise_survey_analysis.js.manifest import JS_LOAD_ORDER
from noise_survey_analysis.visualization import static_payload
from noise_survey_analysis.visualization.dashBuilder import DashBuilder

JS_DIR = Path(__file__).resolve().parent.parent / "noise_survey_analysis" / "static" / "js"


class ManifestTests(unittest.TestCase):
    def test_every_listed_file_exists_once(self):
        self.assertEqual(len(JS_LOAD_ORDER), len(set(JS_LOAD_ORDER)))
        for name in JS_LOAD_ORDER:
            self.assertTrue((JS_DIR / name).is_file(), name)

    def test_seam_definitions_load_before_their_users(self):
        order = JS_LOAD_ORDER.index
        self.assertLess(order("core/actions.js"), order("features/layout/layoutReducer.js"))
        for name in ("layoutReducer", "layoutSelectors", "layoutThunks"):
            self.assertLess(order(f"features/layout/{name}.js"), order("core/rootReducer.js"))
        self.assertLess(order("features/layout/layoutThunks.js"), order("thunks.js"))
        self.assertLess(order("core/keymap.js"), order("services/eventHandlers.js"))
        self.assertLess(order("services/session/sessionManager.js"), order("app.js"))

    def test_dash_builder_loads_exactly_the_manifest(self):
        loaded = []
        with patch(
            "noise_survey_analysis.visualization.dashBuilder.load_js_file",
            side_effect=lambda name: loaded.append(name) or f"// {name}",
        ):
            DashBuilder()._load_all_js_files()
        self.assertEqual(loaded, JS_LOAD_ORDER)

    def test_dash_builder_does_not_use_legacy_loader(self):
        import noise_survey_analysis.visualization.dashBuilder as module

        self.assertNotIn("noise_survey_analysis.js.loader", module.load_js_file.__module__)
        self.assertEqual(module.load_js_file.__module__, module.__name__)


class StaticPayloadTests(unittest.TestCase):
    PREPARED = {
        "log": {
            "prepared_params": {
                "LZeq": {
                    "times_ms": [1000, 2000],
                    "levels_flat_transposed": [40, 41, 50, 51],
                    "frequency_labels": ["63 Hz", "125 Hz"],
                    "frequencies_hz": [63, 125],
                    "n_times": 2,
                    "n_freqs": 2,
                    "chunk_time_length": 2,
                    "initial_glyph_data": {"x": [1000], "y": [-0.5], "dw": [1000], "dh": [2], "image": [[40, 41], [50, 51]]},
                }
            }
        }
    }

    def test_module_functions_match_dash_builder_wrappers(self):
        direct = static_payload.build_static_spectrogram_log_source_data(self.PREPARED, "LZeq")
        wrapped = DashBuilder()._build_static_spectrogram_log_source_data(self.PREPARED, "LZeq")
        # Payloads hold NumPy arrays, so compare key sets and column values explicitly.
        self.assertEqual(direct.keys(), wrapped.keys())
        for key in direct:
            self.assertTrue(all(np.array_equal(a, b) for a, b in zip(direct[key], wrapped[key])), key)
        self.assertEqual(direct["is_reservoir_payload"], [True])
        self.assertEqual(DashBuilder._to_list((1, 2)), static_payload.to_list((1, 2)))
        self.assertIsNone(static_payload.build_static_spectrogram_log_source_data({}, "LZeq"))


class SessionActionRegistryTests(unittest.TestCase):
    class Doc:
        def add_next_tick_callback(self, callback):
            callback()

        def get_model_by_name(self, name):
            return None

    def make(self):
        return AppCallbacks(
            self.Doc(), None, ColumnDataSource(data={}), ColumnDataSource(data={}),
            session_action_source=ColumnDataSource(data={"command": [None], "request_id": [None], "payload": [None]}),
            session_status_source=ColumnDataSource(data={}),
            streaming_enabled=False,
        )

    def test_built_in_actions_are_registered(self):
        for name in ("export_annotations", "save_setup_to_config", "generate_static_html"):
            self.assertIn(name, app_callbacks._SESSION_ACTIONS)

    def test_registered_handler_receives_callbacks_payload_and_request_id_and_command_is_cleared(self):
        seen = []

        def handler(callbacks, payload, request_id):
            seen.append((callbacks, payload, request_id))
            callbacks._publish_session_status("info", "done", done=True, request_id=request_id)

        register_session_action("test_custom", handler)
        try:
            instance = self.make()
            instance._handle_session_action_command(
                "data", {}, {"command": ["test_custom"], "request_id": ["r1"], "payload": [{"x": 1}]}
            )
            self.assertEqual(seen, [(instance, {"x": 1}, "r1")])
            self.assertEqual(instance.session_status_source.data["message"], ["done"])
            self.assertEqual(instance.session_action_source.data["command"], [None])
        finally:
            app_callbacks._SESSION_ACTIONS.pop("test_custom", None)

    def test_failing_handler_reports_error_and_unknown_action_warns(self):
        def boom(callbacks, payload, request_id):
            raise RuntimeError("bad")

        register_session_action("test_boom", boom)
        try:
            instance = self.make()
            instance._handle_session_action_command("data", {}, {"command": ["test_boom"], "request_id": ["r2"], "payload": [None]})
            self.assertEqual(instance.session_status_source.data["level"], ["error"])
            self.assertIn("bad", instance.session_status_source.data["message"][0])

            instance._handle_session_action_command("data", {}, {"command": ["nope"], "request_id": ["r3"], "payload": [None]})
            self.assertEqual(instance.session_status_source.data["level"], ["warning"])
            self.assertIn("Unhandled session action 'nope'", instance.session_status_source.data["message"][0])
        finally:
            app_callbacks._SESSION_ACTIONS.pop("test_boom", None)

    def test_register_validates_arguments(self):
        with self.assertRaises(ValueError):
            register_session_action("", lambda *a: None)
        with self.assertRaises(ValueError):
            register_session_action("x", None)


class _ImmediateDoc:
    def add_next_tick_callback(self, cb):
        cb()


class _Source:
    def __init__(self, bridge=None, result=None):
        self._data = {}
        self.bridge = bridge
        self.result = result
        self.sent = []

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, value):
        self._data = value
        self.sent.append(value)
        if self.bridge is not None and self.result is not None:
            self.bridge.record_js_result({"request_id": value["request_id"][0], **self.result})


class BridgeSeamTests(unittest.TestCase):
    def test_register_keeps_extra_context_and_unregister_clears_it(self):
        bridge = SessionBridge()
        doc = _ImmediateDoc()
        bridge.register(doc, positions=["P1", "P2"], config_path="C:/job/config.json")
        self.assertEqual(bridge.get_context("positions"), ["P1", "P2"])
        self.assertEqual(bridge.get_context("config_path"), "C:/job/config.json")
        self.assertIsNone(bridge.get_context("missing"))
        self.assertEqual(bridge.get_context("missing", 5), 5)
        bridge.register(doc)  # a new registration replaces the context
        self.assertIsNone(bridge.get_context("positions"))
        bridge.register(doc, positions=["P9"])
        bridge.unregister()
        self.assertIsNone(bridge.get_context("positions"))

    def test_send_command_returns_handler_data(self):
        bridge = SessionBridge()
        source = _Source(bridge, {"success": True, "message": "Counted.", "data": {"count": 3}})
        bridge.register(_ImmediateDoc(), automation_command_source=source)
        result = bridge.send_command("test_count", {"a": 1}, timeout=1)
        self.assertTrue(result.success)
        self.assertEqual(result.data, {"count": 3})
        self.assertEqual(source.sent[0]["command"], ["test_count"])
        self.assertEqual(source.sent[0]["payload"], ['{"a": 1}'])

    def test_send_command_timeout_is_failure_for_mutating_and_read_only(self):
        bridge = SessionBridge()
        bridge.register(_ImmediateDoc(), automation_command_source=_Source())
        mutating = bridge.send_command("change_it", {}, timeout=0.05)
        read_only = bridge.send_command("read_it", timeout=0.05, mutating=False)
        self.assertFalse(mutating.success)
        self.assertIn("may not have been applied", mutating.message)
        self.assertFalse(read_only.success)
        self.assertNotIn("may not have been applied", read_only.message)

    def test_existing_methods_use_send_command(self):
        bridge = SessionBridge()
        calls = []
        bridge.send_command = lambda *a, **k: calls.append((a, k)) or "sent"
        self.assertEqual(bridge.export_annotations({"p": 1}), "sent")
        self.assertEqual(calls[0][0][0], "export_annotations")


class SingleBundleTests(unittest.TestCase):
    def build(self, live):
        builder = DashBuilder()
        recorded = {"events": [], "changes": [], "ticks": []}
        doc = SimpleNamespace(
            session_context=object() if live else None,
            js_on_event=lambda event, cb: recorded["events"].append((event, cb)),
            add_next_tick_callback=lambda fn: recorded["ticks"].append(fn),
        )
        builder.js_init_trigger = SimpleNamespace(
            js_on_change=lambda attr, cb: recorded["changes"].append((attr, cb)), visible=False
        )
        with patch.object(DashBuilder, "_assemble_js_bridge_dictionary", return_value={}), \
                patch.object(DashBuilder, "_load_all_js_files", return_value="/*BUNDLE*/"):
            builder._initialize_javascript(doc)
        return recorded

    def test_live_server_attaches_one_callback_to_both_triggers(self):
        recorded = self.build(live=True)
        (event, ready_cb), = recorded["events"]
        (attr, trigger_cb), = recorded["changes"]
        self.assertIs(event, DocumentReady)
        self.assertEqual(attr, "visible")
        self.assertIs(ready_cb, trigger_cb)
        self.assertIsInstance(ready_cb, CustomJS)
        self.assertEqual(ready_cb.code.count("/*BUNDLE*/"), 1)
        self.assertIn("window.__bokeh_app_initialized", ready_cb.code)

    def test_static_export_uses_document_ready_only(self):
        recorded = self.build(live=False)
        self.assertEqual(len(recorded["events"]), 1)
        self.assertEqual(recorded["changes"], [])
        self.assertEqual(recorded["events"][0][1].code.count("/*BUNDLE*/"), 1)


if __name__ == "__main__":
    unittest.main()
