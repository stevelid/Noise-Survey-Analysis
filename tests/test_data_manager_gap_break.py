"""
test_data_manager_gap_break.py

Tests for the gap-break marker insertion in PositionData's totals merge path
(_merge_totals_with_gap_break / _insert_gap_break_rows in data_manager.py).

Background: when multiple source files are merged into one position's totals
series (e.g. several Svan/Svantek spot-measurement segments, or a multi-file
NTi log), the merged line must NOT connect straight across a real stop/start
gap between separate recordings - Bokeh's line glyph should break there
instead. Genuinely contiguous multi-file logs (files that abut with no real
gap) must stay connected as before.

All tests are pure in-memory - no real survey files needed.
"""
import unittest

import pandas as pd

from noise_survey_analysis.core.data_manager import PositionData


def _nan_rows(df: pd.DataFrame) -> pd.Series:
    data_cols = [c for c in df.columns if c != 'Datetime']
    return df[data_cols].isna().all(axis=1)


class TestGapBreakMerge(unittest.TestCase):
    def test_contiguous_files_do_not_get_a_break(self):
        """Two files that abut exactly (next file starts one sample period
        after the previous file's last sample) must merge into one
        unbroken series - e.g. NTi's own multi-file hourly log rollovers."""
        pos = PositionData("TEST")
        t0 = pd.Timestamp("2026-01-01 10:00:00")

        df_a = pd.DataFrame({
            'Datetime': [t0 + pd.Timedelta(seconds=i) for i in range(100)],
            'LAeq': [50.0] * 100,
        })
        df_b = pd.DataFrame({
            'Datetime': [t0 + pd.Timedelta(seconds=100 + i) for i in range(100)],
            'LAeq': [51.0] * 100,
        })

        merged = pos._merge_totals_with_gap_break('log', None, df_a, 1.0)
        merged = pos._merge_totals_with_gap_break('log', merged, df_b, 1.0)

        self.assertEqual(len(merged), 200)
        self.assertEqual(_nan_rows(merged).sum(), 0)

    def test_real_gap_between_files_gets_a_break(self):
        """A materially-sized stop/start gap between two separate files
        (e.g. Svan spot-measurement segments) must produce a NaN marker row
        so Bokeh breaks the line rather than interpolating across it."""
        pos = PositionData("TEST")
        t0 = pd.Timestamp("2026-01-01 10:00:00")

        df_a = pd.DataFrame({
            'Datetime': [t0 + pd.Timedelta(seconds=i) for i in range(100)],
            'LAeq': [50.0] * 100,
        })
        # Starts 5 minutes after file A ends - a real gap, not a continuation.
        gap_start = t0 + pd.Timedelta(seconds=100) + pd.Timedelta(minutes=5)
        df_b = pd.DataFrame({
            'Datetime': [gap_start + pd.Timedelta(seconds=i) for i in range(50)],
            'LAeq': [52.0] * 50,
        })

        merged = pos._merge_totals_with_gap_break('log', None, df_a, 1.0)
        merged = pos._merge_totals_with_gap_break('log', merged, df_b, 1.0)

        nan_mask = _nan_rows(merged)
        self.assertEqual(nan_mask.sum(), 1)
        marker_time = merged.loc[nan_mask, 'Datetime'].iloc[0]
        # Marker must sit strictly between the two segments.
        self.assertGreater(marker_time, df_a['Datetime'].iloc[-1])
        self.assertLess(marker_time, df_b['Datetime'].iloc[0])
        self.assertEqual(len(merged), 151)  # 100 + 50 + 1 marker

    def test_out_of_order_file_arrival_still_detects_the_gap(self):
        """File processing order is not guaranteed to be chronological (e.g.
        an mtime-based directory scan can list a later file first). Gap
        detection is recomputed on the fully time-sorted series each merge,
        so it must still find the real gap regardless of arrival order."""
        pos = PositionData("TEST")
        t0 = pd.Timestamp("2026-01-01 10:00:00")

        df_a = pd.DataFrame({
            'Datetime': [t0 + pd.Timedelta(seconds=i) for i in range(100)],
            'LAeq': [50.0] * 100,
        })
        gap_start = t0 + pd.Timedelta(seconds=100) + pd.Timedelta(minutes=5)
        df_b = pd.DataFrame({
            'Datetime': [gap_start + pd.Timedelta(seconds=i) for i in range(50)],
            'LAeq': [52.0] * 50,
        })

        # File B (chronologically later) is merged first.
        merged = pos._merge_totals_with_gap_break('log', None, df_b, 1.0)
        merged = pos._merge_totals_with_gap_break('log', merged, df_a, 1.0)

        self.assertEqual(_nan_rows(merged).sum(), 1)

    def test_short_spot_check_segments_like_svan_job_6507(self):
        """Regression check modelled on job 6507 position 971-2: a long
        continuous background file followed by several short single-row
        summary segments a few minutes apart, each a separate meter
        stop/start. Every materially-sized gap between segments should get
        a break; only the sub-tolerance near-instant restarts may be
        merged straight through."""
        pos = PositionData("TEST")
        t0 = pd.Timestamp("2026-08-06 09:45:00")

        # Background: many 300s (5 min) periods, like a Svan summary file.
        background = pd.DataFrame({
            'Datetime': [t0 + pd.Timedelta(seconds=300 * i) for i in range(30)],
            'LAeq': [55.0] * 30,
        })
        bg_end = background['Datetime'].iloc[-1]

        # Nine short spot checks, ~2-8 minutes apart, one row each.
        spot_starts = [
            bg_end + pd.Timedelta(minutes=12, seconds=18),
            bg_end + pd.Timedelta(minutes=15, seconds=18),
            bg_end + pd.Timedelta(minutes=19, seconds=4),
            bg_end + pd.Timedelta(minutes=22),
            bg_end + pd.Timedelta(minutes=26, seconds=10),
            bg_end + pd.Timedelta(minutes=31, seconds=46),
            bg_end + pd.Timedelta(minutes=48, seconds=14),
        ]
        spots = [
            pd.DataFrame({'Datetime': [s], 'LAeq': [60.0]}) for s in spot_starts
        ]

        merged = pos._merge_totals_with_gap_break('overview', None, background, 300.0)
        for spot in spots:
            merged = pos._merge_totals_with_gap_break('overview', merged, spot, None)

        nan_mask = _nan_rows(merged)
        # Background -> first spot check, and each subsequent spot-to-spot
        # boundary, are all several minutes - well outside the ~30s
        # tolerance around the 300s nominal period - so every boundary here
        # should be flagged.
        self.assertEqual(nan_mask.sum(), len(spot_starts))


if __name__ == '__main__':
    unittest.main()
