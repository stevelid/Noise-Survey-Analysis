"""Tests for noise_survey_analysis.control.validation"""
import math
import unittest

from noise_survey_analysis.control.validation import (
    validate_timestamp_ms,
    validate_viewport,
    validate_view_mode,
    validate_parameter,
    validate_workspace_path,
    validate_workspace_payload,
    validate_body_size,
    validate_command_payload,
    parse_deep_link_params,
)


# ---------------------------------------------------------------------------
# validate_timestamp_ms
# ---------------------------------------------------------------------------

class TestValidateTimestampMs(unittest.TestCase):
    def test_valid_float(self):
        self.assertEqual(validate_timestamp_ms(1_710_000_000_000), 1_710_000_000_000.0)

    def test_valid_int_string(self):
        self.assertEqual(validate_timestamp_ms("1710000000000"), 1_710_000_000_000.0)

    def test_zero_is_valid(self):
        self.assertEqual(validate_timestamp_ms(0), 0.0)

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            validate_timestamp_ms(-1)

    def test_rejects_nan(self):
        with self.assertRaises(ValueError):
            validate_timestamp_ms(math.nan)

    def test_rejects_inf(self):
        with self.assertRaises(ValueError):
            validate_timestamp_ms(math.inf)

    def test_rejects_none(self):
        with self.assertRaises(ValueError):
            validate_timestamp_ms(None)

    def test_rejects_non_numeric_string(self):
        with self.assertRaises(ValueError):
            validate_timestamp_ms("not_a_number")

    def test_custom_name_in_error(self):
        with self.assertRaises(ValueError) as ctx:
            validate_timestamp_ms(None, name="myts")
        self.assertIn("myts", str(ctx.exception))


# ---------------------------------------------------------------------------
# validate_viewport
# ---------------------------------------------------------------------------

class TestValidateViewport(unittest.TestCase):
    def test_valid_range(self):
        start, end = validate_viewport(1_000_000, 2_000_000)
        self.assertEqual(start, 1_000_000.0)
        self.assertEqual(end, 2_000_000.0)

    def test_rejects_equal_start_end(self):
        with self.assertRaises(ValueError):
            validate_viewport(1_000_000, 1_000_000)

    def test_rejects_end_before_start(self):
        with self.assertRaises(ValueError):
            validate_viewport(2_000_000, 1_000_000)

    def test_rejects_invalid_start(self):
        with self.assertRaises(ValueError):
            validate_viewport("bad", 2_000_000)

    def test_rejects_invalid_end(self):
        with self.assertRaises(ValueError):
            validate_viewport(1_000_000, "bad")

    def test_coerces_strings(self):
        start, end = validate_viewport("1710000000000", "1710003600000")
        self.assertLess(start, end)


# ---------------------------------------------------------------------------
# validate_view_mode
# ---------------------------------------------------------------------------

class TestValidateViewMode(unittest.TestCase):
    def test_log(self):
        self.assertEqual(validate_view_mode("log"), "log")

    def test_overview(self):
        self.assertEqual(validate_view_mode("overview"), "overview")

    def test_case_insensitive(self):
        self.assertEqual(validate_view_mode("LOG"), "log")
        self.assertEqual(validate_view_mode("Overview"), "overview")

    def test_whitespace_stripped(self):
        self.assertEqual(validate_view_mode("  log  "), "log")

    def test_rejects_invalid(self):
        with self.assertRaises(ValueError):
            validate_view_mode("timeline")

    def test_rejects_non_string(self):
        with self.assertRaises(ValueError):
            validate_view_mode(42)

    def test_error_message_includes_allowed(self):
        with self.assertRaises(ValueError) as ctx:
            validate_view_mode("bad")
        msg = str(ctx.exception)
        self.assertIn("log", msg)
        self.assertIn("overview", msg)


# ---------------------------------------------------------------------------
# validate_parameter
# ---------------------------------------------------------------------------

class TestValidateParameter(unittest.TestCase):
    def test_valid_param_no_list(self):
        self.assertEqual(validate_parameter("LAeq"), "LAeq")

    def test_whitespace_stripped(self):
        self.assertEqual(validate_parameter("  LCeq  "), "LCeq")

    def test_valid_param_in_list(self):
        result = validate_parameter("LAeq", available=["LAeq", "LCeq", "LZeq"])
        self.assertEqual(result, "LAeq")

    def test_rejects_param_not_in_list(self):
        with self.assertRaises(ValueError):
            validate_parameter("LZeq", available=["LAeq", "LCeq"])

    def test_rejects_empty_string(self):
        with self.assertRaises(ValueError):
            validate_parameter("")

    def test_rejects_whitespace_only(self):
        with self.assertRaises(ValueError):
            validate_parameter("   ")

    def test_rejects_non_string(self):
        with self.assertRaises(ValueError):
            validate_parameter(123)


# ---------------------------------------------------------------------------
# validate_workspace_payload
# ---------------------------------------------------------------------------

class TestValidateWorkspacePayload(unittest.TestCase):
    def test_dict_with_app_state(self):
        result = validate_workspace_payload({"appState": {"x": 1}})
        self.assertIn("appState", result)

    def test_dict_with_source_configs(self):
        result = validate_workspace_payload({"sourceConfigs": []})
        self.assertIn("sourceConfigs", result)

    def test_dict_with_both_keys(self):
        payload = {"appState": {}, "sourceConfigs": []}
        result = validate_workspace_payload(payload)
        self.assertEqual(result, payload)

    def test_json_string_input(self):
        import json
        raw = json.dumps({"appState": {"zoom": 1.0}})
        result = validate_workspace_payload(raw)
        self.assertIn("appState", result)

    def test_rejects_missing_required_keys(self):
        with self.assertRaises(ValueError):
            validate_workspace_payload({"other": "value"})

    def test_rejects_invalid_json_string(self):
        with self.assertRaises(ValueError):
            validate_workspace_payload("{not json}")

    def test_rejects_list(self):
        with self.assertRaises(ValueError):
            validate_workspace_payload([{"appState": {}}])


# ---------------------------------------------------------------------------
# validate_body_size
# ---------------------------------------------------------------------------

class TestValidateBodySize(unittest.TestCase):
    def test_accepts_small_body(self):
        validate_body_size(b"hello")  # should not raise

    def test_rejects_oversized_body(self):
        from noise_survey_analysis.control.commands import MAX_PAYLOAD_BYTES
        with self.assertRaises(ValueError):
            validate_body_size(b"x" * (MAX_PAYLOAD_BYTES + 1))

    def test_accepts_string_body(self):
        validate_body_size("hello world")  # should not raise


# ---------------------------------------------------------------------------
# validate_command_payload
# ---------------------------------------------------------------------------

class TestValidateCommandPayload(unittest.TestCase):
    def test_status_no_payload_required(self):
        result = validate_command_payload("status", {})
        self.assertEqual(result, {})

    def test_fit_full_range_no_payload(self):
        result = validate_command_payload("fit_full_range", {})
        self.assertEqual(result, {})

    def test_export_static_html_no_payload(self):
        result = validate_command_payload("export_static_html", {})
        self.assertEqual(result, {})

    def test_set_viewport_valid(self):
        result = validate_command_payload("set_viewport", {"start": 1e12, "end": 2e12})
        self.assertAlmostEqual(result["start"], 1e12)
        self.assertAlmostEqual(result["end"], 2e12)

    def test_set_viewport_rejects_bad_range(self):
        with self.assertRaises(ValueError):
            validate_command_payload("set_viewport", {"start": 2e12, "end": 1e12})

    def test_set_viewport_missing_start(self):
        with self.assertRaises(ValueError):
            validate_command_payload("set_viewport", {"end": 2e12})

    def test_set_parameter_valid(self):
        result = validate_command_payload("set_parameter", {"value": "LAeq"})
        self.assertEqual(result["value"], "LAeq")

    def test_set_parameter_empty_rejects(self):
        with self.assertRaises(ValueError):
            validate_command_payload("set_parameter", {"value": ""})

    def test_set_view_mode_valid(self):
        result = validate_command_payload("set_view_mode", {"value": "log"})
        self.assertEqual(result["value"], "log")

    def test_set_view_mode_invalid(self):
        with self.assertRaises(ValueError):
            validate_command_payload("set_view_mode", {"value": "timeline"})

    def test_center_on_timestamp_valid(self):
        result = validate_command_payload(
            "center_on_timestamp", {"timestamp": 1710000000000}
        )
        self.assertEqual(result["timestamp"], 1710000000000.0)

    def test_center_on_timestamp_with_half_width(self):
        result = validate_command_payload(
            "center_on_timestamp",
            {"timestamp": 1710000000000, "half_width_ms": 3600000},
        )
        self.assertEqual(result["half_width_ms"], 3600000.0)

    def test_center_on_timestamp_bad_half_width(self):
        with self.assertRaises(ValueError):
            validate_command_payload(
                "center_on_timestamp",
                {"timestamp": 1710000000000, "half_width_ms": -1},
            )

    def test_apply_workspace_path(self):
        import tempfile, os, json
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as fh:
            json.dump({"appState": {}}, fh)
            tmp_path = fh.name
        try:
            result = validate_command_payload("apply_workspace", {"path": tmp_path})
            self.assertEqual(result["path"], tmp_path)
        finally:
            os.unlink(tmp_path)

    def test_apply_workspace_path_missing_file(self):
        with self.assertRaises(ValueError):
            validate_command_payload(
                "apply_workspace", {"path": "/nonexistent/workspace.json"}
            )

    def test_apply_workspace_inline_payload(self):
        result = validate_command_payload(
            "apply_workspace", {"payload": {"appState": {"x": 1}}}
        )
        self.assertIn("payload", result)

    def test_apply_workspace_no_path_or_payload(self):
        with self.assertRaises(ValueError):
            validate_command_payload("apply_workspace", {})

    def test_unknown_command_raises(self):
        with self.assertRaises(ValueError):
            validate_command_payload("eval_js", {})


# ---------------------------------------------------------------------------
# parse_deep_link_params
# ---------------------------------------------------------------------------

class TestParseDeepLinkParams(unittest.TestCase):
    def test_empty_input(self):
        result = parse_deep_link_params({})
        self.assertNotIn("start", result)
        self.assertNotIn("end", result)
        self.assertNotIn("view", result)
        self.assertNotIn("param", result)

    def test_valid_all_params(self):
        result = parse_deep_link_params({
            "start": "1710000000000",
            "end": "1710003600000",
            "view": "overview",
            "param": "LAeq",
        })
        self.assertAlmostEqual(result["start"], 1710000000000.0)
        self.assertAlmostEqual(result["end"], 1710003600000.0)
        self.assertEqual(result["view"], "overview")
        self.assertEqual(result["param"], "LAeq")
        self.assertEqual(result.get("_errors", {}), {})

    def test_valid_view_only(self):
        result = parse_deep_link_params({"view": "log"})
        self.assertEqual(result["view"], "log")
        self.assertNotIn("start", result)

    def test_valid_param_only(self):
        result = parse_deep_link_params({"param": "LCeq"})
        self.assertEqual(result["param"], "LCeq")

    def test_invalid_view_mode_captured_in_errors(self):
        result = parse_deep_link_params({"view": "3d"})
        self.assertNotIn("view", result)
        self.assertIn("view", result["_errors"])

    def test_invalid_param_with_available_list(self):
        result = parse_deep_link_params(
            {"param": "ZZZ"}, available_params=["LAeq", "LCeq"]
        )
        self.assertNotIn("param", result)
        self.assertIn("param", result["_errors"])

    def test_only_start_no_end_captured_in_errors(self):
        result = parse_deep_link_params({"start": "1710000000000"})
        self.assertNotIn("start", result)
        self.assertIn("end", result["_errors"])

    def test_only_end_no_start_captured_in_errors(self):
        result = parse_deep_link_params({"end": "1710003600000"})
        self.assertNotIn("end", result)
        self.assertIn("start", result["_errors"])

    def test_invalid_viewport_range_captured_in_errors(self):
        result = parse_deep_link_params({
            "start": "1710003600000",
            "end": "1710000000000",
        })
        self.assertNotIn("start", result)
        self.assertIn("viewport", result["_errors"])

    def test_bokeh_style_list_values(self):
        # Bokeh wraps argument values in lists of bytes
        result = parse_deep_link_params({
            "view": [b"log"],
            "param": [b"LAeq"],
        })
        self.assertEqual(result["view"], "log")
        self.assertEqual(result["param"], "LAeq")

    def test_param_validated_against_available_list(self):
        result = parse_deep_link_params(
            {"param": "LAeq"}, available_params=["LAeq", "LCeq"]
        )
        self.assertEqual(result["param"], "LAeq")

    def test_mixed_valid_and_invalid(self):
        result = parse_deep_link_params({
            "view": "overview",
            "param": "INVALID",
            "start": "1710000000000",
            "end": "1710003600000",
        }, available_params=["LAeq"])
        self.assertEqual(result["view"], "overview")
        self.assertNotIn("param", result)
        self.assertAlmostEqual(result["start"], 1710000000000.0)
        self.assertAlmostEqual(result["end"], 1710003600000.0)


if __name__ == "__main__":
    unittest.main()
