import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from noise_survey_analysis.js import loader


class JsLoaderTests(unittest.TestCase):
    def test_load_js_file_returns_content_and_missing_file_returns_empty_string(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "app.js").write_text("console.log('app');", encoding="utf-8")

            with patch.object(loader, "JS_DIR", str(temp_path)):
                self.assertEqual(loader.load_js_file("app.js"), "console.log('app');")
                self.assertEqual(loader.load_js_file("missing.js"), "")

    def test_get_combined_js_concatenates_expected_sections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            files = {
                "app.js": "APP();",
                "core.js": "CORE();",
                "charts.js": "CHARTS();",
                "audio.js": "AUDIO();",
                "frequency.js": "FREQ();",
            }
            for name, content in files.items():
                (temp_path / name).write_text(content, encoding="utf-8")

            with patch.object(loader, "JS_DIR", str(temp_path)):
                combined = loader.get_combined_js()

            self.assertIn("// APP JS\nAPP();", combined)
            self.assertIn("// CORE JS\nCORE();", combined)
            self.assertIn("// CHARTS JS\nCHARTS();", combined)
            self.assertIn("// AUDIO JS\nAUDIO();", combined)
            self.assertIn("// FREQUENCY JS\nFREQ();", combined)


if __name__ == "__main__":
    unittest.main()
