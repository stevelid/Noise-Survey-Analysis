import os
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

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

    @unittest.skipUnless(
        os.name == 'nt',
        "Windows path semantics: os.path.commonpath does not treat '\\' as a separator elsewhere",
    )
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


class ToBokehMsTests(unittest.TestCase):
    """to_bokeh_ms takes a fast path for datetime64 input; it must stay exact.

    The reference implementation below is the one this replaced. Streaming calls this on
    every pan, and `pd.to_datetime` ran a heuristic that iterated the values.
    """

    @staticmethod
    def _reference(values):
        dt = pd.Series(pd.to_datetime(values, utc=True))
        return (
            dt.dt.tz_convert("UTC").dt.tz_localize(None)
            .astype("datetime64[ns]").astype("int64") // 10**6
        ).to_numpy()

    def _assert_matches_reference(self, values):
        expected = self._reference(values)
        actual = utils.to_bokeh_ms(values)
        self.assertIsInstance(actual, np.ndarray)
        self.assertEqual(actual.dtype, expected.dtype)
        np.testing.assert_array_equal(actual, expected)

    def test_matches_reference_for_timezone_aware_input(self):
        self._assert_matches_reference(
            pd.Series(pd.date_range("2024-01-01", periods=5, freq="1s", tz="UTC"))
        )

    def test_matches_reference_for_non_utc_timezone(self):
        self._assert_matches_reference(
            pd.Series(pd.date_range("2024-06-01", periods=5, freq="1s", tz="Europe/London"))
        )

    def test_matches_reference_for_naive_input(self):
        self._assert_matches_reference(
            pd.Series(pd.date_range("2024-01-01", periods=5, freq="1s"))
        )

    def test_matches_reference_for_index_and_ndarray(self):
        index = pd.date_range("2024-06-01", periods=5, freq="100ms", tz="UTC")
        self._assert_matches_reference(index)
        self._assert_matches_reference(pd.date_range("2024-06-01", periods=5, freq="1s").values)

    def test_matches_reference_for_non_nanosecond_units(self):
        self._assert_matches_reference(
            pd.Series(pd.date_range("2024-01-01", periods=4, freq="1s", tz="UTC").as_unit("us"))
        )

    def test_matches_reference_for_string_input(self):
        self._assert_matches_reference(
            pd.Series(["2024-01-01T00:00:00Z", "2024-01-01T00:00:01Z"])
        )

    def test_matches_reference_before_the_epoch(self):
        self._assert_matches_reference(
            pd.Series(pd.date_range("1960-01-01", periods=4, freq="1s", tz="UTC"))
        )

    def test_matches_reference_for_sub_millisecond_values(self):
        self._assert_matches_reference(
            pd.Series(pd.to_datetime(["2024-01-01 00:00:00.0004Z", "2024-01-01 00:00:00.0009Z"]))
        )

    def test_matches_reference_for_empty_and_missing_values(self):
        self._assert_matches_reference(pd.Series([], dtype="datetime64[ns, UTC]"))
        self._assert_matches_reference(
            pd.Series([pd.Timestamp("2024-01-01", tz="UTC"), pd.NaT])
        )
