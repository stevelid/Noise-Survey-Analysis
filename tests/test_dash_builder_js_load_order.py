import unittest
from unittest.mock import patch

from noise_survey_analysis.visualization.dashBuilder import DashBuilder


class DashBuilderJsLoadOrderTests(unittest.TestCase):
    def test_history_module_loads_before_store(self):
        loaded = []

        def fake_load_js_file(file_name):
            loaded.append(file_name)
            return f"// {file_name}"

        with patch(
            "noise_survey_analysis.visualization.dashBuilder.load_js_file",
            side_effect=fake_load_js_file,
        ):
            DashBuilder()._load_all_js_files()

        self.assertIn("core/history.js", loaded)
        self.assertLess(loaded.index("core/history.js"), loaded.index("store.js"))


if __name__ == "__main__":
    unittest.main()
