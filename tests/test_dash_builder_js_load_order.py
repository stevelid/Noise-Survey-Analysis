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
        processing_order = [
            "processors/common.js", "processors/line.js", "processors/spectral.js",
            "processors/frequency.js", "data-processors.js",
        ]
        indices = [loaded.index(name) for name in processing_order]
        self.assertEqual(indices, sorted(indices))
        for dependency, consumer in [
            ("features/regions/annotationMetrics.js", "features/regions/regionUtils.js"),
            ("services/session/annotationCsv.js", "services/session/sessionManager.js"),
            ("features/annotations/panelSelectors.js", "core/rootReducer.js"),
            ("features/annotations/panelSelectors.js", "features/annotations/panelThunks.js"),
            ("features/annotations/panelThunks.js", "services/panels/htmlPanelEvents.js"),
            ("services/panels/htmlPanelEvents.js", "services/panels/htmlPanelRenderer.js"),
            ("services/panels/htmlPanelRenderer.js", "services/renderers.js"),
            ("services/panels/htmlPanelEvents.js", "app.js"),
        ]:
            self.assertLess(loaded.index(dependency), loaded.index(consumer))


if __name__ == "__main__":
    unittest.main()
