import os
import tempfile
import time
import unittest
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from noise_survey_analysis.core.data_parsers import ParsedData
from noise_survey_analysis.core.parsed_data_cache import ParsedDataCache


class ParsedDataCacheTests(unittest.TestCase):
    def setUp(self):
        self._original_instance = ParsedDataCache._instance
        self._original_cache_dir = ParsedDataCache._cache_dir
        self._temp_dir = tempfile.TemporaryDirectory()
        ParsedDataCache._instance = None
        ParsedDataCache._cache_dir = Path(self._temp_dir.name) / "cache"
        self.cache = ParsedDataCache()

    def tearDown(self):
        self.cache.clear()
        ParsedDataCache._instance = self._original_instance
        ParsedDataCache._cache_dir = self._original_cache_dir
        self._temp_dir.cleanup()

    def _make_parsed_data(self):
        return ParsedData(
            totals_df=pd.DataFrame({"Datetime": [1, 2], "LAeq": [50.0, 52.0]}),
            spectral_df=pd.DataFrame({"Datetime": [1, 2], "LZeq_100": [60.0, 61.0]}),
            original_file_path="sample.csv",
            parser_type="generic",
        )

    def test_put_get_and_stats_round_trip(self):
        file_path = Path(self._temp_dir.name) / "sample.csv"
        file_path.write_text("sample", encoding="utf-8")
        parsed_data = self._make_parsed_data()

        self.cache.put(str(file_path), parsed_data)
        cached = self.cache.get(str(file_path))

        self.assertIsNotNone(cached)
        assert_frame_equal(cached.totals_df, parsed_data.totals_df)
        assert_frame_equal(cached.spectral_df, parsed_data.spectral_df)

        stats = self.cache.get_stats()
        self.assertEqual(stats["entry_count"], 1)
        self.assertGreater(stats["estimated_memory_mb"], 0)
        self.assertTrue(any(self.cache._cache_dir.glob("*.pkl")))

    def test_get_invalidates_stale_entries_when_file_changes(self):
        file_path = Path(self._temp_dir.name) / "stale.csv"
        file_path.write_text("before", encoding="utf-8")
        self.cache.put(str(file_path), self._make_parsed_data())

        file_path.write_text("after change", encoding="utf-8")
        current_stat = file_path.stat()
        os.utime(file_path, (current_stat.st_atime, current_stat.st_mtime + 5))

        cached = self.cache.get(str(file_path))

        self.assertIsNone(cached)
        self.assertEqual(self.cache.get_stats()["entry_count"], 0)

    def test_clear_removes_memory_and_disk_entries(self):
        file_path = Path(self._temp_dir.name) / "clear.csv"
        file_path.write_text("sample", encoding="utf-8")
        self.cache.put(str(file_path), self._make_parsed_data())
        self.assertTrue(any(self.cache._cache_dir.glob("*.pkl")))

        self.cache.clear()

        self.assertEqual(self.cache.get_stats()["entry_count"], 0)
        self.assertFalse(any(self.cache._cache_dir.glob("*.pkl")))

    def test_return_all_columns_produces_different_cache_entries(self):
        file_path = Path(self._temp_dir.name) / "profile.csv"
        file_path.write_text("sample", encoding="utf-8")

        # First parse: limited columns
        limited = ParsedData(
            totals_df=pd.DataFrame({"Datetime": [1, 2], "LAeq": [50.0, 52.0]}),
            spectral_df=pd.DataFrame({"Datetime": [1, 2], "LZeq_100": [60.0, 61.0]}),
            original_file_path=str(file_path),
            parser_type="generic",
        )
        self.cache.put(str(file_path), limited, return_all_columns=False)
        cached_limited = self.cache.get(str(file_path), return_all_columns=False)
        self.assertIsNotNone(cached_limited)

        # Second parse: all columns (different data)
        full = ParsedData(
            totals_df=pd.DataFrame({
                "Datetime": [1, 2],
                "LAeq": [50.0, 52.0],
                "LAFmax": [55.0, 57.0],
                "CustomCol": [1, 2]
            }),
            spectral_df=pd.DataFrame({"Datetime": [1, 2], "LZeq_100": [60.0, 61.0]}),
            original_file_path=str(file_path),
            parser_type="generic",
        )
        self.cache.put(str(file_path), full, return_all_columns=True)
        cached_full = self.cache.get(str(file_path), return_all_columns=True)
        self.assertIsNotNone(cached_full)

        # The two cached entries must be distinct
        self.assertIn("CustomCol", cached_full.totals_df.columns)
        self.assertNotIn("CustomCol", cached_limited.totals_df.columns)

        # Requesting with opposite profile should not cross-contaminate
        cached_limited_again = self.cache.get(str(file_path), return_all_columns=False)
        self.assertNotIn("CustomCol", cached_limited_again.totals_df.columns)


if __name__ == "__main__":
    unittest.main()
