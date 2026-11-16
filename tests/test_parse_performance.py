"""Regression tests for the fast NTi reader and the deferred (single-pass) log merge.

The optimised paths must give exactly what the original line-based reader and the
per-file merge gave.
"""
import os
import tempfile
import unittest

import pandas as pd

from noise_survey_analysis.core.data_manager import PositionData
from noise_survey_analysis.core.data_parsers import NTiFileParser, ParsedData

BANDS = ['6.3', '8.0', '10.0', '12.5', '16.0', '20.0', '25.0', '31.5']
HEAD = (
    "XL2 {kind} Logging:\t\tx\n----\n\n\n# Hardware Configuration\n\tDevice Info:    \tXL2, SNo. A2A-1\n"
    "\n# Measurement Setup\n\tLog-Interval:   \t00:00:01\n\n# Time\n\tStart:          \t2026-11-04, 13:39:54\n\n"
)
FOOT = "\n# {title} over whole log period\n\tnot available in repeat timer modes\n\n#CheckSum\n\tABCDEF\n"


def _bb_rows(start, n):
    out = []
    for i in range(n):
        t = start + pd.Timedelta(seconds=i)
        out.append(f"{t:%Y-%m-%d}  \t{t:%H:%M:%S}  \t00:00:05  \t{40 + i % 7}.{i % 10}\t{41 + i % 5}.1\t"
                   f"{50 + i % 9}.3\t30.0\t60.0\t---/---\t        \t        ")
    return out


def _rta_rows(start, n):
    out = []
    for i in range(n):
        t = start + pd.Timedelta(seconds=i)
        vals = "\t".join(f"{20 + (i + j) % 30}.{j}" for j in range(len(BANDS)))
        out.append(f"{t:%Y-%m-%d}  \t{t:%H:%M:%S}  \t00:00:05  \t         \t{vals}")
    return out


def write_bb(path, rows):
    head = (HEAD.format(kind="Broadband") + "# Broadband LOG Results\n"
            "\tDate        \tTime      \tTimer     \tLAeq_dt \tLAeq    \tLAFmax_dt\tLAFmin_dt\tLCPKmax_dt\tLow(eq/peak)\tOverload\tPause   \n"
            "\t[YYYY-MM-DD]\t[hh:mm:ss]\t[hh:mm:ss]\t[dB]    \t[dB]    \t[dB]     \t[dB]     \t[dB]      \t            \t        \t        \n")
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        fh.write(head + "\n".join("\t" + r if False else r for r in rows) + "\n" + FOOT.format(title="Broadband LOG Results"))


def write_rta(path, rows, split_tail=None, split_head=None):
    n = len(BANDS)
    head = (HEAD.format(kind="RTA Spectrum") + "# RTA LOG Results \n"
            "\t            \t          \t          \t         \t" + "\t".join(["LZeq_dt  "] * n) + "\n"
            "\tDate        \tTime      \tTimer     \tBand [Hz]\t" + "\t".join(f"{b:9s}" for b in BANDS) + "\n"
            "\t[YYYY-MM-DD]\t[hh:mm:ss]\t[hh:mm:ss]\t         \t" + "\t".join(["[dB]     "] * n) + "\n")
    body = "\n".join(rows)
    with open(path, 'w', encoding='utf-8', newline='') as fh:
        if split_head is not None:  # continuation file: starts mid-row, after the header
            fh.write(head + split_head + "\n" + body + "\n" + FOOT.format(title="RTA LOG Results"))
        else:
            fh.write(head + body + ("" if split_tail else "\n") + (split_tail or "") + FOOT.format(title="RTA LOG Results"))


class FastNTiReaderTests(unittest.TestCase):
    def _parse_both(self, path):
        old, new = NTiFileParser(), NTiFileParser()
        old.FAST_PATH_MIN_BYTES = 1 << 62   # never fast
        new.FAST_PATH_MIN_BYTES = 0         # always fast
        new._FAST_CHUNK_BYTES = 2000        # force several parallel chunks
        return old.parse(path), new.parse(path)

    def _assert_equal(self, a: ParsedData, b: ParsedData):
        self.assertEqual(a.metadata.get('error'), b.metadata.get('error'))
        self.assertEqual(a.data_profile, b.data_profile)
        self.assertEqual(a.spectral_data_type, b.spectral_data_type)
        self.assertEqual(a.sample_period_seconds, b.sample_period_seconds)
        self.assertEqual(a.metadata.get('hardware_config'), b.metadata.get('hardware_config'))
        for name in ('totals_df', 'spectral_df'):
            da, db = getattr(a, name), getattr(b, name)
            if da is None or db is None:
                self.assertIsNone(da); self.assertIsNone(db)
                continue
            pd.testing.assert_frame_equal(da, db, check_exact=True)

    def test_broadband_log_matches_original_reader(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "2026-11-04_SLM_001_123_Log.txt")
            write_bb(p, _bb_rows(pd.Timestamp("2026-11-04 13:40:00"), 600))
            old, new = self._parse_both(p)
            self.assertIsNone(old.metadata.get('error'))
            self.assertEqual(len(old.totals_df), 600)
            self._assert_equal(old, new)

    def test_split_rta_parts_match_original_reader(self):
        with tempfile.TemporaryDirectory() as d:
            t0 = pd.Timestamp("2026-11-04 13:40:00")
            rows0 = _rta_rows(t0, 400)
            rows1 = _rta_rows(t0 + pd.Timedelta(seconds=401), 300)
            # part 00 ends in the middle of a row; part 01 begins with the rest of it
            p0 = os.path.join(d, "2026-11-04_SLM_001_RTA_3rd_Log_00.txt")
            p1 = os.path.join(d, "2026-11-04_SLM_001_RTA_3rd_Log_01.txt")
            write_rta(p0, rows0, split_tail=_rta_rows(t0 + pd.Timedelta(seconds=400), 1)[0][:60])
            write_rta(p1, rows1, split_head="0.5     \t18.9     \t17.5")
            for p in (p0, p1):
                old, new = self._parse_both(p)
                self.assertIsNone(old.metadata.get('error'))
                self.assertIsNotNone(old.spectral_df)
                self._assert_equal(old, new)

    def test_unrecognised_layout_falls_back_to_original_error(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "2026-11-04_SLM_001_123_Log.txt")
            with open(p, 'w', encoding='utf-8') as fh:
                fh.write("junk\n" * 50)
            old, new = self._parse_both(p)
            self.assertEqual(old.metadata.get('error'), new.metadata.get('error'))
            self.assertTrue(new.metadata.get('error'))


class DatetimeFallbackTests(unittest.TestCase):
    def test_rows_outside_sample_in_other_format_still_parse(self):
        base = pd.Timestamp("2026-11-04 13:00:00")
        vals = [f"{base + pd.Timedelta(seconds=i):%Y-%m-%d %H:%M:%S}" for i in range(2000)]
        vals[1500] = "2026-11-04 13:25:00.5"
        vals[1700] = "garbage"
        out = NTiFileParser._to_datetime_fast(pd.Series(vals, dtype=object))
        self.assertEqual(out.iloc[1500], pd.Timestamp("2026-11-04 13:25:00.5"))
        self.assertTrue(pd.isna(out.iloc[1700]))
        self.assertEqual(int(out.isna().sum()), 1)
        self.assertEqual(out.iloc[0], base)


class DeferredMergeTests(unittest.TestCase):
    @staticmethod
    def _parsed(path, start, n, period, value, profile='log'):
        df = pd.DataFrame({
            'Datetime': [start + pd.Timedelta(seconds=period * i) for i in range(n)],
            'LAeq': [float(value)] * n,
        })
        sp = df.copy()
        sp['LZeq_8'] = value + 1.0
        return ParsedData(totals_df=df, spectral_df=sp, original_file_path=path, parser_type='NTi',
                          data_profile=profile, sample_period_seconds=float(period))

    def test_deferred_merge_equals_per_file_merge(self):
        t0 = pd.Timestamp("2026-01-01 10:00:00", tz='UTC')
        specs = [
            ("c.txt", t0 + pd.Timedelta(seconds=1000), 50, 1, 3),                       # later, after a real gap
            ("a.txt", t0, 100, 1, 1),
            ("b.txt", t0 + pd.Timedelta(seconds=95), 20, 1, 2),                          # overlaps a.txt: duplicates
            ("d.txt", t0 + pd.Timedelta(seconds=5000), 10, 60, 4),                       # different period
        ]
        seq, dfr = PositionData("S"), PositionData("D")
        for s in specs:
            seq.add_parsed_file_data(self._parsed(*s))
        for s in specs:
            dfr.add_parsed_file_data(self._parsed(*s), defer_merge=True)
        self.assertIsNone(dfr.log_totals)  # nothing merged yet
        dfr.flush_pending_merges()
        pd.testing.assert_frame_equal(seq.log_totals, dfr.log_totals, check_exact=True)
        pd.testing.assert_frame_equal(seq.log_spectral, dfr.log_spectral, check_exact=True)
        self.assertGreater(seq.log_totals['LAeq'].isna().sum(), 0)  # gap markers were produced


if __name__ == '__main__':
    unittest.main()
