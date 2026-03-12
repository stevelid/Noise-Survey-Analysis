import unittest
from unittest.mock import MagicMock, patch

from noise_survey_analysis.core import utils


class FakeDoc:
    def __init__(self):
        self.roots = []

    def add_root(self, root):
        self.roots.append(root)


class UtilsTests(unittest.TestCase):
    def test_add_error_to_doc_adds_escaped_error_div(self):
        doc = FakeDoc()

        added = utils.add_error_to_doc(doc, "Failed to load", ValueError("<bad> input"))

        self.assertTrue(added)
        self.assertEqual(len(doc.roots), 1)
        self.assertIn("Error: Failed to load", doc.roots[0].text)
        self.assertIn("&lt;bad&gt; input", doc.roots[0].text)

    def test_add_error_to_doc_returns_false_if_document_add_fails(self):
        doc = MagicMock()
        doc.add_root.side_effect = RuntimeError("no document")

        added = utils.add_error_to_doc(doc, "Boom")

        self.assertFalse(added)

    def test_find_lowest_common_folder_returns_common_directory(self):
        paths = [
            r"C:\data\job\file1.csv",
            r"C:\data\job\sub\file2.csv",
        ]

        common = utils.find_lowest_common_folder(paths)

        self.assertEqual(common, r"C:\data\job")

    def test_find_lowest_common_folder_returns_none_when_commonpath_fails(self):
        with patch("noise_survey_analysis.core.utils.os.path.commonpath", side_effect=ValueError):
            self.assertIsNone(utils.find_lowest_common_folder([r"C:\a.txt", r"D:\b.txt"]))


if __name__ == "__main__":
    unittest.main()
