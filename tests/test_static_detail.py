import unittest

import numpy as np
import pandas as pd

from noise_survey_analysis.visualization import static_payload as sp


class FakePosition:
    def __init__(self, totals=None, spectral=None):
        self.log_totals = totals
        self.log_spectral = spectral
        self.log_file_paths = [{"file_path": "x"}]
        self._log_data_loaded = False


class FakeData:
    def __init__(self, positions):
        self._p = positions

    def positions(self):
        return list(self._p)

    def __getitem__(self, key):
        return self._p[key]


def totals(n=3600, start="2026-01-01 00:00:00"):
    return pd.DataFrame({"Datetime": pd.date_range(start, periods=n, freq="s"),
                         "LAeq": np.linspace(40, 60, n), "LAFmax": np.linspace(50, 70, n)})


class QuantisationTests(unittest.TestCase):
    def test_integer_spectra_round_trip_exactly(self):
        levels = np.array([-5, 0, 37, 90, 120], dtype=np.int16)
        codes, offset, step = sp.quantize_levels(levels)
        self.assertEqual(codes.dtype, np.uint8)
        self.assertTrue(np.array_equal(sp.dequantize_levels(codes, offset, step), levels.astype(np.float32)))

    def test_float_spectra_use_half_db_grid_with_bounded_error(self):
        rng = np.random.default_rng(1)
        levels = rng.uniform(20, 100, 5000).astype(np.float32)
        codes, offset, step = sp.quantize_levels(levels)
        self.assertEqual(step, 0.5)
        error = np.abs(sp.dequantize_levels(codes, offset, step) - levels)
        self.assertLessEqual(float(error.max()), 0.25 + 1e-4)

    def test_wide_range_widens_the_step_and_nan_maps_to_lowest(self):
        levels = np.array([0.0, 300.0, np.nan], dtype=np.float32)
        codes, offset, step = sp.quantize_levels(levels)
        self.assertGreater(step, 0.5)
        self.assertEqual(int(codes[2]), 0)
        self.assertLessEqual(abs(float(sp.dequantize_levels(codes, offset, step)[1]) - 300.0), step / 2 + 1e-4)


class StaticSourceTests(unittest.TestCase):
    PREPARED = {"log": {"prepared_params": {"LZeq": {
        "times_ms": [1000, 2000], "levels_flat_transposed": np.array([40, 41, 50, 51], dtype=np.int16),
        "frequency_labels": ["63", "125"], "frequencies_hz": [63, 125], "n_times": 2, "n_freqs": 2,
        "chunk_time_length": 2, "initial_glyph_data": {"x": [1000], "y": [-0.5], "dw": [1000], "dh": [2],
                                                        "image": [np.array([40, 41, 50, 51])]}}}}}

    def test_compact_payload_is_binary_quantised_and_has_no_image_copy(self):
        data = sp.build_static_spectrogram_log_source_data(self.PREPARED, "LZeq")
        self.assertEqual(data["levels_flat_transposed"][0].dtype, np.uint8)
        self.assertEqual(data["times_ms"][0].dtype, np.float64)
        self.assertNotIn("initial_glyph_data_image", data)
        self.assertEqual(data["quant_step_db"], [1.0])
        decoded = sp.dequantize_levels(data["levels_flat_transposed"][0], data["quant_offset_db"][0], data["quant_step_db"][0])
        self.assertEqual(decoded.tolist(), [40, 41, 50, 51])

    def test_compact_prepared_dedupes_the_shared_parameter_and_leaves_input_alone(self):
        prepared = {"P1": dict(self.PREPARED)}
        compact = sp.compact_prepared_glyph_data(prepared, {"P1": "LZeq"})
        entry = compact["P1"]["log"]["prepared_params"]["LZeq"]
        self.assertTrue(entry["shared_with_log_source"])
        self.assertIsNone(entry["levels_flat_transposed"])
        self.assertNotIn("image", entry["initial_glyph_data"])
        original = prepared["P1"]["log"]["prepared_params"]["LZeq"]
        self.assertIsNotNone(original["levels_flat_transposed"])
        self.assertIn("image", original["initial_glyph_data"])
        other = sp.compact_prepared_glyph_data(prepared, {})["P1"]["log"]["prepared_params"]["LZeq"]
        self.assertEqual(other["levels_flat_transposed"].dtype, np.uint8)

    def test_timeseries_columns_narrow_but_datetime_keeps_precision(self):
        out = sp.compact_timeseries_data({"Datetime": np.arange(3, dtype=np.float64), "LAeq": np.ones(3),
                                          "index": np.arange(3, dtype=np.int64)})
        self.assertEqual(out["Datetime"].dtype, np.float64)
        self.assertEqual(out["LAeq"].dtype, np.float32)
        self.assertEqual(out["index"].dtype, np.int32)


class LinesModeTests(unittest.TestCase):
    def spectral(self, n, start="1970-01-01 00:00:00", columns=60):
        frame = totals(n, start).rename(columns={"LAeq": "LZeq_63", "LAFmax": "LZFmax_63"})
        frame["LZeq_63"] = 60.0
        for i in range(columns):
            frame[f"LZeq_{i}"] = 50.0
        return frame

    def test_energy_average_is_uniform_and_max_columns_take_max(self):
        frame = self.spectral(12, columns=0)
        frame.loc[0, "LZeq_63"] = 70.0
        frame["LZFmax_63"] = np.arange(12, dtype=float)
        out = sp.average_spectral_in_time(frame, 3)
        self.assertEqual(len(out), 4)
        self.assertEqual(len(out["Datetime"].diff().dropna().unique()), 1)
        self.assertAlmostEqual(out["LZeq_63"].iloc[0], 10 * np.log10((10 ** 7 + 2 * 10 ** 6) / 3), places=6)
        self.assertEqual(out["LZFmax_63"].tolist(), [2.0, 5.0, 8.0, 11.0])

    def test_auto_order_full_then_lines_then_regions(self):
        mb = 1024 * 1024
        data = FakeData({"P1": FakePosition(totals(200_000), self.spectral(200_000))})
        parts = sp.estimate_static_parts(data)
        full = sp.estimate_bytes_for_step(parts, None)
        finest = sp.estimate_bytes_for_step(parts, 2)
        coarsest = sp.estimate_bytes_for_step(parts, 30)
        self.assertGreater(full, finest)
        self.assertGreater(finest, coarsest)
        self.assertEqual(sp.plan_static_detail("auto", data, max_mb=full / mb + 1)["mode"], "full")
        plan = sp.plan_static_detail("auto", data, max_mb=(finest - 1) / mb)
        self.assertEqual(plan["mode"], "lines")
        self.assertIn(plan["step_s"], (3, 5, 10, 15, 30))
        self.assertLessEqual(plan["estimate_bytes"], (finest - 1))
        self.assertEqual(sp.plan_static_detail("auto", data, max_mb=(coarsest - 1) / mb)["mode"], "regions")
        self.assertEqual(sp.plan_static_detail("lines", data, max_mb=1)["step_s"], 30)

    def test_lines_mode_keeps_all_1s_totals_and_averages_spectral(self):
        position = FakePosition(totals(600), self.spectral(600, columns=0))
        sp.apply_static_detail(FakeData({"P1": position}), "lines", [], step_s=5)
        self.assertEqual(len(position.log_totals), 600)
        self.assertEqual(len(position.log_spectral), 120)


class DetailDecisionTests(unittest.TestCase):
    def test_estimate_grows_with_rows_and_columns(self):
        small, _ = sp.estimate_static_bytes(FakeData({"P1": FakePosition(totals(100))}))
        big, per = sp.estimate_static_bytes(FakeData({"P1": FakePosition(totals(1_000_000), totals(1_000_000))}))
        self.assertGreater(big, small)
        self.assertGreater(per["P1"], 10_000_000)

    def test_auto_picks_full_under_and_regions_over_threshold(self):
        mb = 1024 * 1024
        self.assertEqual(sp.choose_static_detail("auto", 100 * mb)[0], "full")
        mode, why = sp.choose_static_detail("auto", 400 * mb)
        self.assertEqual(mode, "regions")
        self.assertIn("400", why)
        self.assertEqual(sp.choose_static_detail("overview", 1)[0], "overview")
        self.assertEqual(sp.choose_static_detail("full", 999 * mb)[0], "full")
        with self.assertRaises(ValueError):
            sp.choose_static_detail("bogus", 1)

    def test_windows_cover_regions_and_markers_and_skip_rejected(self):
        state = {"regions": {"byId": {
                    "1": {"areas": [{"start": 1_000_000, "end": 1_060_000}]},
                    "2": {"areas": [{"start": 1_100_000, "end": 1_120_000}], "status": "rejected"}}},
                 "markers": {"byId": {"1": {"timestamp": 5_000_000}}}}
        windows = sp.collect_detail_windows(state, region_pad_s=10, marker_pad_s=5)
        self.assertEqual(windows, [(990_000, 1_070_000), (4_995_000, 5_005_000)])

    def test_regions_mode_keeps_rows_in_windows_breaks_lines_and_drops_spectral(self):
        frame = totals(3600, "1970-01-01 00:00:00")  # epoch ms == row index * 1000
        position = FakePosition(frame, frame.copy())
        data = FakeData({"P1": position})
        summary = sp.apply_static_detail(data, "regions", [(100_000, 200_000), (1_000_000, 1_010_000)])
        kept = position.log_totals
        self.assertIsNone(position.log_spectral)
        self.assertEqual(position.log_file_paths, [])
        real = kept.dropna(subset=["LAeq"])
        self.assertEqual(len(real), 101 + 11)
        self.assertEqual(int(kept["LAeq"].isna().sum()), 1)  # one break between the two windows
        self.assertEqual(summary["P1"]["log_spectral_rows"], 0)

    def test_chart_offset_shifts_the_windows_into_data_time(self):
        frame = totals(3600, "1970-01-01 00:00:00")
        position = FakePosition(frame, None)
        # Annotation drawn at display 100-110 s with the chart shifted +50 s => data 50-60 s.
        sp.apply_static_detail(FakeData({"P1": position}), "regions", [(100_000, 110_000)], {"P1": 50_000.0})
        first = position.log_totals["Datetime"].iloc[0]
        self.assertEqual(first, pd.Timestamp("1970-01-01 00:00:50"))

    def test_overview_mode_removes_all_log_data(self):
        position = FakePosition(totals(10), totals(10))
        sp.apply_static_detail(FakeData({"P1": position}), "overview", [])
        self.assertIsNone(position.log_totals)
        self.assertIsNone(position.log_spectral)


if __name__ == "__main__":
    unittest.main()
