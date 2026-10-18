"""Migration preserves event identity and consolidates only legacy cross-meter copies."""
import unittest
from copy import deepcopy

from noise_survey_analysis.core.annotation_workspace import migrate_workspace


class AnnotationWorkspaceTests(unittest.TestCase):
    def workspace(self, version=1):
        return {"version": version, "sourceConfigs": [], "appState": {
            "view": {"availablePositions": ["P1", "P2", "P3"]},
            "regions": {"allIds": [1, 2], "selectedId": 1, "byId": {
                "1": {"id": 1, "positionId": "P1", "start": 1000, "end": 2000,
                      "note": "Dog", "color": "#e65100"},
                "2": {"id": 2, "positionId": "P2", "start": 1001, "end": 2001,
                      "note": "Dog", "color": "#e65100"},
            }},
        }}

    def test_v1_merges_copies_without_mutating_input(self):
        original = self.workspace()
        before = deepcopy(original)
        result, merged = migrate_workspace(original)
        self.assertEqual(original, before)
        self.assertEqual(result["version"], 2)
        self.assertEqual(merged, 1)
        region = result["appState"]["regions"]["byId"]["1"]
        self.assertEqual(region["meterStates"], {"P1": "present", "P2": "present", "P3": "unchecked"})
        self.assertEqual(region["color"], "#e65100")

    def test_v2_does_not_deduplicate_intentionally_distinct_events(self):
        result, merged = migrate_workspace(self.workspace(2))
        self.assertEqual(merged, 0)
        self.assertEqual(len(result["appState"]["regions"]["allIds"]), 2)

    def test_tolerance_and_same_origin_guard(self):
        original = self.workspace()
        original["appState"]["regions"]["byId"]["2"]["start"] = 1002
        self.assertEqual(migrate_workspace(original)[1], 0)
        original = self.workspace()
        original["appState"]["regions"]["byId"]["2"]["positionId"] = "P1"
        self.assertEqual(migrate_workspace(original)[1], 0)

    def test_unknown_version_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported workspace version"):
            migrate_workspace(self.workspace(42))


if __name__ == "__main__":
    unittest.main()
