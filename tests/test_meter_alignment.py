import unittest

import numpy as np
import pandas as pd

from noise_survey_analysis.core.meter_alignment import MeterAlignmentProcessor


class MeterAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.processor = MeterAlignmentProcessor({
            'search_seconds': 60,
            'window_seconds': 300,
            'max_windows': 6,
            'candidate_step_seconds': 120,
            'min_overlap_seconds': 1200,
            'min_window_score': 0.70,
            'min_window_margin': 0.05,
            'min_accepted_windows': 3,
            'min_median_score': 0.90,
            'max_lag_spread_seconds': 1.0,
            'max_drift_seconds': 1.0,
        })

    @staticmethod
    def _series(values, offset_seconds=0):
        index = pd.date_range(
            pd.Timestamp('2026-01-01T00:00:00Z') + pd.Timedelta(seconds=offset_seconds),
            periods=len(values),
            freq='s',
        )
        return pd.Series(values, index=index)

    def test_recovers_consistent_offset_across_multiple_windows(self):
        rng = np.random.default_rng(6461)
        values = rng.normal(55.0, 4.0, 4 * 3600)
        reference = self._series(values)
        target = self._series(values, offset_seconds=17)

        result = self.processor.estimate_offset(reference, target)

        self.assertTrue(result['accepted'])
        self.assertEqual(result['estimated_lag_seconds'], 17.0)
        self.assertEqual(result['chart_offset_seconds'], -17.0)
        self.assertGreaterEqual(result['windows_accepted'], 3)
        self.assertGreater(result['median_score'], 0.99)

    def test_rejects_unrelated_position_signals(self):
        first_rng = np.random.default_rng(1)
        second_rng = np.random.default_rng(2)
        reference = self._series(first_rng.normal(55.0, 4.0, 4 * 3600))
        target = self._series(second_rng.normal(55.0, 4.0, 4 * 3600))

        result = self.processor.estimate_offset(reference, target)

        self.assertFalse(result['accepted'])
        self.assertEqual(result['chart_offset_seconds'], 0.0)
        self.assertIn('distinctive enough', result['reason'])


if __name__ == '__main__':
    unittest.main()
