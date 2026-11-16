"""Regression tests for the data-loading robustness work: gap markers across mixed-period
measurements, NTi split logs, parse-error handling, DST fallback, parse cache hygiene and
config merging."""
import json
import logging
import os
import tempfile
import time
import unittest
from pathlib import Path

import pandas as pd

import generate_job_config
from noise_survey_analysis.core import parsed_data_cache as pdc
from noise_survey_analysis.core.config_io import (
    detect_job_number,
    merge_config_with_existing,
    read_config_json,
    save_config_from_selected_sources,
)
from noise_survey_analysis.core.data_manager import DataManager, PositionData
from noise_survey_analysis.core.data_parsers import (
    NoiseParserFactory,
    NTiFileParser,
    ParsedData,
    is_nti_log_filename,
    localize_naive_to_utc,
    nti_log_sort_key,
)


def _nan_rows(df):
    return df[[c for c in df.columns if c != 'Datetime']].isna().all(axis=1)


class MixedPeriodGapTests(unittest.TestCase):
    def test_two_measurements_with_different_periods_get_one_marker_not_one_per_row(self):
        """6645-4 regression: a short 6 s test run followed by a 5 min deployment used to
        produce a NaN marker after EVERY real row (global mode period was 6 s)."""
        pos = PositionData("P")
        t0 = pd.Timestamp("2026-11-04 13:39:54", tz="UTC")
        short = pd.DataFrame({'Datetime': [t0, t0 + pd.Timedelta(seconds=6)], 'LAeq': [49.2, 46.8]})
        start2 = pd.Timestamp("2026-11-04 13:40:16", tz="UTC")
        times = [start2] + [pd.Timestamp("2026-11-04 13:45:00", tz="UTC") + pd.Timedelta(minutes=5 * i) for i in range(50)]
        long = pd.DataFrame({'Datetime': times, 'LAeq': [50.0] * len(times)})

        merged = pos._merge_totals_with_gap_break('overview', None, short, 6.0)
        merged = pos._merge_totals_with_gap_break('overview', merged, long, 300.0)

        self.assertEqual(int(_nan_rows(merged).sum()), 1)               # only the real gap
        self.assertEqual(int(merged["LAeq"].notna().sum()), 53)
        self.assertEqual(int(merged['Datetime'].duplicated().sum()), 0)
        marker = merged.loc[_nan_rows(merged), 'Datetime'].iloc[0]
        self.assertTrue(short['Datetime'].iloc[-1] < marker < start2)

    def test_first_file_wins_for_duplicate_timestamps(self):
        pos = PositionData("P")
        t = pd.Timestamp("2026-01-01 10:00:00")
        a = pd.DataFrame({'Datetime': [t], 'LAeq': [1.0]})
        b = pd.DataFrame({'Datetime': [t], 'LAeq': [2.0]})
        merged = pos._merge_df(a, b)
        self.assertEqual(merged['LAeq'].tolist(), [1.0])


class NtiSplitLogTests(unittest.TestCase):
    def test_filename_helper(self):
        for name in ("x_SLM_000_RTA_3rd_Log.txt", "x_SLM_000_RTA_3rd_Log_00.txt", "x_123_LOG_12.TXT"):
            self.assertTrue(is_nti_log_filename(name), name)
        for name in ("x_123_Rpt_Report.txt", "x_123_Report.txt", "x_log.csv", "x_Log_final.txt"):
            self.assertFalse(is_nti_log_filename(name), name)
        names = ["a_Log_10.txt", "a_Log_01.txt", "a_Log.txt", "a_Log_02.txt"]
        self.assertEqual(sorted(names, key=nti_log_sort_key),
                         ["a_Log.txt", "a_Log_01.txt", "a_Log_02.txt", "a_Log_10.txt"])

    def test_generator_and_factory_recognise_split_logs(self):
        self.assertEqual(generate_job_config.detect_source_type("2026-11-04_SLM_000_RTA_3rd_Log_01.txt"), ("NTi", "nti"))
        self.assertEqual(generate_job_config.detect_source_type("2026-11-04_SLM_000_123_Log_00.txt"), ("NTi", "nti"))
        parser = NoiseParserFactory.get_parser("C:/x/2026-11-04_SLM_000_RTA_3rd_Log_00.txt")
        self.assertIsInstance(parser, NTiFileParser)

    def _write_part(self, path, rows):
        lines = [
            "XL2 Broadband Logging:\t\tx", "----", "", "# Hardware Configuration",
            "\tDevice Info:    \tXL2", "", "# Measurement Setup", "\tProfile:        \tFull mode", "",
            "# Time", "\tStart:          \t2026-11-04, 13:14:52", "",
            "# Broadband LOG Results",
            "\tDate        \tTime      \tTimer     \tLAeq_dt \tLAFmax_dt",
            "\t[YYYY-MM-DD]\t[hh:mm:ss]\t[hh:mm:ss]\t[dB]    \t[dB]",
        ]
        for ts, v in rows:
            lines.append(f"\t2026-11-04  \t{ts}  \t00:00:01  \t{v}    \t{v + 1}")
        lines += ["", "#CheckSum", "\tABC"]
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_split_parts_parse_as_log_and_merge_in_time_order(self):
        with tempfile.TemporaryDirectory() as d:
            p0 = os.path.join(d, "2026-11-04_SLM_000_123_Log_00.txt")
            p1 = os.path.join(d, "2026-11-04_SLM_000_123_Log_01.txt")
            self._write_part(p0, [("13:14:53", 50.0), ("13:14:54", 51.0)])
            self._write_part(p1, [("13:14:55", 52.0), ("13:14:56", 53.0)])
            parsed = NTiFileParser().parse(p1)
            self.assertEqual(parsed.data_profile, 'log')
            self.assertFalse(parsed.metadata.get('error'))
            dm = DataManager(use_cache=False)
            for path in (p1, p0):   # deliberately out of order
                dm.add_source_file(path, "P")
            dm["P"].load_log_data_lazy(dm.parser_factory, use_cache=False)
            log = dm["P"].log_totals
            self.assertEqual(log['LAeq'].tolist(), [50.0, 51.0, 52.0, 53.0])
            self.assertTrue(log['Datetime'].is_monotonic_increasing)


class LoadErrorTests(unittest.TestCase):
    def test_parse_error_is_a_failed_file_not_a_loaded_one(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "2026-11-04_SLM_000_123_Rpt_Report.txt")
            Path(bad).write_text("not an NTi file\n", encoding="utf-8")
            dm = DataManager(use_cache=False)
            with self.assertLogs("noise_survey_analysis.core.data_manager", level="ERROR") as logs:
                dm.add_source_file(bad, "P")
            pos = dm["P"]
            self.assertEqual(pos.load_status, 'failed')
            self.assertEqual(len(pos.load_errors), 1)
            self.assertIn("Rpt_Report", pos.load_errors[0]['file_name'])
            self.assertEqual(len(logs.records), 1)                      # one line
            self.assertIn("Rpt_Report", logs.output[0])
            self.assertEqual(dm.load_errors[0]['position'], "P")
            self.assertEqual(pos.loaded_file_paths, [])

    def test_one_bad_file_does_not_abort_the_rest(self):
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "2026-11-04_SLM_000_123_Rpt_Report.txt")
            Path(good).write_text("\n".join([
                "XL2 Broadband Reporting:", "", "# Broadband Results",
                "\tStart       \t          \tStop        \t          \t        \t        ",
                "\tDate       \tTime      \tDate        \tTime      \tLAeq    \tLAFmax  ",
                "\t[YYYY-MM-DD]\t[hh:mm:ss]\t[YYYY-MM-DD]\t[hh:mm:ss]\t[dB]    \t[dB]    ",
                "\t2026-11-04  \t13:40:00  \t2026-11-04  \t13:45:00  \t50.0    \t60.0    ",
                "", "#CheckSum", "\tAB", ""]), encoding="utf-8")
            missing = os.path.join(d, "vanished_log.csv")
            dm = DataManager(use_cache=False)
            with self.assertLogs("noise_survey_analysis.core.data_manager", level="ERROR"):
                dm.load_from_configs([
                    {"position_name": "P", "file_paths": [missing, good]},
                ])
            pos = dm["P"]
            self.assertTrue(pos.has_overview_totals)
            self.assertEqual(pos.load_status, 'partial')
            self.assertEqual([e['file_name'] for e in pos.load_errors], ["vanished_log.csv"])


class DstFallbackTests(unittest.TestCase):
    def test_autumn_backwards_step_resolves_by_row_order_and_keeps_every_row(self):
        times = pd.to_datetime(['2026-10-25 01:10', '2026-10-25 01:50', '2026-10-25 01:20',
                                '2026-10-25 01:40', '2026-10-25 02:30'])
        out = localize_naive_to_utc(pd.Series(times), "Europe/London")
        self.assertEqual(out.tolist(), [pd.Timestamp(t, tz="UTC") for t in (
            '2026-10-25 00:10', '2026-10-25 00:50', '2026-10-25 01:20', '2026-10-25 01:40', '2026-10-25 02:30')])

    def test_autumn_single_pass_rules(self):
        with self.assertLogs("noise_survey_analysis.core.data_parsers", level="WARNING") as logs:
            starts_before = localize_naive_to_utc(
                pd.Series(pd.to_datetime(['2026-10-25 00:30', '2026-10-25 01:15'])), "Europe/London")
        self.assertIn("1 row(s)", logs.output[0])   # fallback reports how many rows it resolved
        self.assertEqual(starts_before.iloc[1], pd.Timestamp('2026-10-25 00:15', tz='UTC'))
        starts_inside = localize_naive_to_utc(
            pd.Series(pd.to_datetime(['2026-10-25 01:15', '2026-10-25 02:30'])), "Europe/London")
        self.assertEqual(starts_inside.iloc[0], pd.Timestamp('2026-10-25 01:15', tz='UTC'))

    def test_spring_forward_nonexistent_rows_are_kept_distinct(self):
        out = localize_naive_to_utc(
            pd.Series(pd.to_datetime(['2026-03-29 01:10', '2026-03-29 01:20'])), "Europe/London")
        self.assertEqual(out.nunique(), 2)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = (pdc.ParsedDataCache._instance, pdc.ParsedDataCache._cache_dir)
        pdc.ParsedDataCache._instance = None
        pdc.ParsedDataCache._cache_dir = Path(self._tmp.name) / "cache"

    def tearDown(self):
        pdc.ParsedDataCache._instance, pdc.ParsedDataCache._cache_dir = self._orig
        self._tmp.cleanup()

    def _data(self):
        return ParsedData(totals_df=pd.DataFrame({"Datetime": [1], "LAeq": [1.0]}), original_file_path="x", parser_type="g")

    def test_version_in_key_lazy_load_and_atomic_write(self):
        f = Path(self._tmp.name) / "a.csv"
        f.write_text("x")
        cache = pdc.ParsedDataCache()
        key_v2 = cache._get_cache_key(str(f))
        old = pdc.PARSER_CACHE_VERSION
        try:
            pdc.PARSER_CACHE_VERSION = old + 1
            self.assertNotEqual(key_v2, cache._get_cache_key(str(f)))
        finally:
            pdc.PARSER_CACHE_VERSION = old
        cache.put(str(f), self._data())
        self.assertEqual(list(cache._cache_dir.glob("*.tmp*")), [])
        pdc.ParsedDataCache._instance = None
        fresh = pdc.ParsedDataCache()
        self.assertEqual(len(fresh._cache), 0)               # nothing unpickled at start-up
        self.assertIsNotNone(fresh.get(str(f)))               # loaded on demand
        self.assertEqual(len(fresh._cache), 1)

    def test_old_entries_are_evicted(self):
        f = Path(self._tmp.name) / "a.csv"
        f.write_text("x")
        cache = pdc.ParsedDataCache()
        cache.put(str(f), self._data())
        pkl = next(cache._cache_dir.glob("*.pkl"))
        old = time.time() - 31 * 24 * 3600
        os.utime(pkl, (old, old))
        cache._evict_disk_entries()
        self.assertFalse(pkl.exists())

    def test_size_cap_evicts_least_recently_used_first(self):
        f1, f2 = Path(self._tmp.name) / "1.csv", Path(self._tmp.name) / "2.csv"
        f1.write_text("x"); f2.write_text("y")
        cache = pdc.ParsedDataCache()
        cache.put(str(f1), self._data()); cache.put(str(f2), self._data())
        pkls = sorted(cache._cache_dir.glob("*.pkl"), key=lambda p: p.stat().st_mtime)
        os.utime(pkls[0], (time.time() - 100, time.time() - 100))
        orig = pdc.CACHE_MAX_TOTAL_BYTES
        try:
            pdc.CACHE_MAX_TOTAL_BYTES = pkls[1].stat().st_size + 1
            cache._evict_disk_entries()
        finally:
            pdc.CACHE_MAX_TOTAL_BYTES = orig
        self.assertFalse(pkls[0].exists())
        self.assertTrue(pkls[1].exists())


class ConfigMergeTests(unittest.TestCase):
    def test_merge_keeps_setup_for_existing_sources_adds_new_drops_vanished(self):
        existing = {
            "config_base_path": "C:/Jobs/6645 surveys", "created_at": "old",
            "positions": {"P1": {"chart_offset_seconds": 3.5}},
            "default_view": {"start": 1.0},
            "sources": [
                {"path": "P1/a_log.csv", "position": "P1", "type": "Svan", "parser_type": "svan",
                 "timezone": "UTC", "columns": ["LAeq"], "display_title": "North"},
                {"path": "P1/gone.csv", "position": "P1", "type": "Svan", "parser_type": "svan"},
            ],
        }
        new = {
            "config_base_path": "C:/Jobs/6645 Surveys", "version": "1.2",
            "sources": [
                {"path": "p1/a_log.csv", "position": "P1", "type": "Svan", "parser_type": "svan"},
                {"path": "P1/b_log.csv", "position": "P1", "type": "Svan", "parser_type": "svan"},
            ],
        }
        merged, changes = merge_config_with_existing(existing, new)
        self.assertEqual(merged['positions'], existing['positions'])
        self.assertEqual(merged['default_view'], existing['default_view'])
        self.assertEqual([s['path'] for s in merged['sources']], ["p1/a_log.csv", "P1/b_log.csv"])
        self.assertEqual(merged['sources'][0]['timezone'], "UTC")
        self.assertEqual(merged['sources'][0]['display_title'], "North")
        self.assertTrue(any(c.startswith("added") and "b_log" in c for c in changes))
        self.assertTrue(any(c.startswith("removed") and "gone" in c for c in changes))

    def test_job_number_prefers_leading_four_digits_and_ignores_dates(self):
        self.assertEqual(detect_job_number("C:/Jobs/6645 Chickerell/6645 Surveys/6645-4", []), "6645")
        self.assertEqual(detect_job_number("C:/Jobs/6645 X/2026-11-04 survey", []), "6645")
        self.assertEqual(detect_job_number("C:/x/survey 2026", ["C:/x/6301-2/a.csv"]), "6301")

    def test_read_config_json_accepts_bom(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "c.json"
            p.write_bytes(b'\xef\xbb\xbf' + json.dumps({"sources": []}).encode())
            self.assertEqual(read_config_json(p), {"sources": []})

    def test_save_from_selected_sources_preserves_existing_setup(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "6645 Surveys"
            root.mkdir()
            a = root / "L1_log.csv"; a.write_text("x")
            cfg = root / "noise_survey_config_6645.json"
            cfg.write_text(json.dumps({
                "config_base_path": str(root).replace("\\", "/"),
                "positions": {"L1": {"audio_offset_seconds": 2.0}},
                "sources": [{"path": "L1_log.csv", "position": "L1", "type": "Svan", "parser_type": "svan",
                             "y_range": [20, 90]}],
            }), encoding="utf-8")
            out = save_config_from_selected_sources(
                [{"position_name": "L1", "file_path": str(a), "parser_type": "svan", "data_type": "Svan"}])
            self.assertEqual(out, cfg)
            data = read_config_json(cfg)
            self.assertEqual(data['positions']['L1']['audio_offset_seconds'], 2.0)
            self.assertEqual(data['sources'][0]['y_range'], [20, 90])


if __name__ == "__main__":
    unittest.main()
