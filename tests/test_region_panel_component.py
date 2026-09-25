"""Layout checks for the region side panel."""

import unittest

from noise_survey_analysis.ui.components import RegionPanelComponent


class RegionPanelLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.panel = RegionPanelComponent()
        self.detail_children = self.panel.detail_layout.children

    def test_navigation_and_note_sit_directly_under_the_region_list(self) -> None:
        names = [child.name for child in self.detail_children[:4]]
        self.assertEqual(
            names,
            [
                self.panel.region_table.name,
                "region_navigation_actions",
                "region_note_input",
                "region_note_status_div",
            ],
        )

    def test_centre_and_back_share_one_row(self) -> None:
        navigation_row = self.detail_children[1]
        self.assertEqual(
            navigation_row.children,
            [self.panel.center_region_button, self.panel.back_to_previous_view_button],
        )
        self.assertEqual(self.panel.back_to_previous_view_button.label, "Back (B)")

    def test_note_reports_drafts_and_commits(self) -> None:
        note_input = self.panel.note_input
        self.assertTrue(note_input.js_property_callbacks.get("change:value"))
        self.assertTrue(note_input.js_property_callbacks.get("change:value_input"))
        self.assertIn("saveRegionNoteIntent", note_input.js_property_callbacks["change:value"][0].code)
        self.assertIn(
            "updateRegionNoteDraftIntent",
            note_input.js_property_callbacks["change:value_input"][0].code,
        )


if __name__ == "__main__":
    unittest.main()
