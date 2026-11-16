import re
import unittest

from noise_survey_analysis.export.static_export import _with_export_id


class ExportIdTests(unittest.TestCase):
    def test_meta_tag_is_added_inside_head_and_depends_on_content(self):
        one = _with_export_id("<html><head><meta charset='utf-8'></head><body>one</body></html>")
        two = _with_export_id("<html><head><meta charset='utf-8'></head><body>two</body></html>")
        pattern = r'<head>\s*<meta name="nsa-export-id" content="([0-9a-f]{12})">'
        first, second = re.search(pattern, one), re.search(pattern, two)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first.group(1), second.group(1))

    def test_same_content_gives_the_same_id(self):
        html = "<html><head></head><body>x</body></html>"
        self.assertEqual(_with_export_id(html), _with_export_id(html))

    def test_html_without_head_is_left_alone(self):
        self.assertEqual(_with_export_id("<p>x</p>"), "<p>x</p>")


if __name__ == "__main__":
    unittest.main()
