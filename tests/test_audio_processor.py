import unittest
from dataclasses import dataclass

import pandas as pd

from noise_survey_analysis.core.audio_processor import AudioDataProcessor


@dataclass
class FakePositionData:
    has_audio_files: bool = True
    has_log_totals: bool = False
    has_overview_totals: bool = False
    log_totals: pd.DataFrame | None = None
    overview_totals: pd.DataFrame | None = None
    audio_files_list: pd.DataFrame | None = None


class FakeAppData:
    def __init__(self, positions):
        self._positions = positions

    def positions(self):
        return list(self._positions.keys())

    def __getitem__(self, item):
        return self._positions[item]


class AudioProcessorTests(unittest.TestCase):
    def setUp(self):
        self.processor = AudioDataProcessor()

    def test_collect_measurement_times_merges_and_sorts_log_and_overview(self):
        position = FakePositionData(
            has_log_totals=True,
            has_overview_totals=True,
            log_totals=pd.DataFrame(
                {"Datetime": [pd.Timestamp("2024-01-01T00:02:00Z"), pd.Timestamp("2024-01-01T00:00:00Z")]}
            ),
            overview_totals=pd.DataFrame(
                {"Datetime": [pd.Timestamp("2024-01-01T00:01:00Z"), pd.NaT]}
            ),
        )

        result = self.processor._collect_measurement_times(position)

        self.assertEqual(
            list(result),
            [
                pd.Timestamp("2024-01-01T00:00:00Z"),
                pd.Timestamp("2024-01-01T00:01:00Z"),
                pd.Timestamp("2024-01-01T00:02:00Z"),
            ],
        )

    def test_split_measurement_segments_breaks_on_large_gaps(self):
        times = pd.Series(
            [
                pd.Timestamp("2024-01-01T00:00:00Z"),
                pd.Timestamp("2024-01-01T00:01:00Z"),
                pd.Timestamp("2024-01-01T00:02:00Z"),
                pd.Timestamp("2024-01-01T00:20:00Z"),
                pd.Timestamp("2024-01-01T00:21:00Z"),
            ]
        )

        segments = self.processor._split_measurement_segments(times)

        self.assertEqual(
            segments,
            [
                {
                    "start": pd.Timestamp("2024-01-01T00:00:00Z"),
                    "end": pd.Timestamp("2024-01-01T00:02:00Z"),
                },
                {
                    "start": pd.Timestamp("2024-01-01T00:20:00Z"),
                    "end": pd.Timestamp("2024-01-01T00:21:00Z"),
                },
            ],
        )

    def test_anchor_audio_files_to_segments_sets_confidence_and_warnings(self):
        segments = [
            {
                "start": pd.Timestamp("2024-01-01T00:00:00Z"),
                "end": pd.Timestamp("2024-01-01T00:10:00Z"),
            },
            {
                "start": pd.Timestamp("2024-01-01T02:00:00Z"),
                "end": pd.Timestamp("2024-01-01T02:10:00Z"),
            },
        ]
        audio_df = pd.DataFrame(
            [
                {
                    "filename": "close.wav",
                    "modified_time": pd.Timestamp("2024-01-01T00:05:00Z"),
                    "duration_sec": 60,
                },
                {
                    "filename": "far.wav",
                    "modified_time": pd.Timestamp("2024-01-01T05:00:00Z"),
                    "duration_sec": 60,
                },
                {
                    "filename": "missing.wav",
                    "modified_time": pd.NaT,
                    "duration_sec": 10,
                },
            ]
        )

        anchored = self.processor._anchor_audio_files_to_segments(audio_df, segments, "P1")

        self.assertEqual(anchored.loc[0, "Datetime"], pd.Timestamp("2024-01-01T00:04:00Z"))
        self.assertEqual(anchored.loc[0, "anchor_confidence"], "high")
        self.assertEqual(anchored.loc[0, "segment_index"], 0)

        self.assertEqual(anchored.loc[1, "Datetime"], pd.Timestamp("2024-01-01T04:59:00Z"))
        self.assertEqual(anchored.loc[1, "anchor_confidence"], "medium")
        self.assertIn("far from segment start", anchored.loc[1, "anchor_warning"])
        self.assertEqual(anchored.loc[1, "segment_index"], 1)

        self.assertTrue(pd.isna(anchored.loc[2, "Datetime"]))
        self.assertEqual(anchored.loc[2, "anchor_warning"], "missing modified time")

    def test_anchor_audio_files_updates_position_audio_list_end_to_end(self):
        position = FakePositionData(
            has_audio_files=True,
            has_log_totals=True,
            log_totals=pd.DataFrame(
                {
                    "Datetime": [
                        pd.Timestamp("2024-01-01T00:00:00Z"),
                        pd.Timestamp("2024-01-01T00:01:00Z"),
                        pd.Timestamp("2024-01-01T00:02:00Z"),
                    ]
                }
            ),
            audio_files_list=pd.DataFrame(
                [
                    {
                        "filename": "match.wav",
                        "modified_time": pd.Timestamp("2024-01-01T00:02:30Z"),
                        "duration_sec": 30,
                    },
                    {
                        "filename": "too_far.wav",
                        "modified_time": pd.Timestamp("2024-01-02T00:00:00Z"),
                        "duration_sec": 30,
                    },
                ]
            ),
        )
        app_data = FakeAppData({"P1": position})

        self.processor.anchor_audio_files(app_data)

        anchored = position.audio_files_list
        self.assertEqual(anchored.loc[0, "Datetime"], pd.Timestamp("2024-01-01T00:02:00Z"))
        self.assertEqual(anchored.loc[0, "anchor_confidence"], "high")
        self.assertTrue(pd.isna(anchored.loc[1, "Datetime"]))
        self.assertIn("no close measurement segment", anchored.loc[1, "anchor_warning"])

    def test_explicit_recorded_start_takes_precedence_over_modified_time(self):
        segments = [{
            "start": pd.Timestamp("2024-06-01T09:00:00Z"),
            "end": pd.Timestamp("2024-06-01T10:00:00Z"),
        }]
        audio_df = pd.DataFrame([{
            "filename": "R1.WAV",
            "recorded_start_time": pd.Timestamp("2024-06-01T09:10:00.250Z"),
            "modified_time": pd.Timestamp("2024-06-01T09:40:05Z"),
            "duration_sec": 1800,
            "anchor_source": "svl_wave_marker+embedded_wav_metadata",
            "anchor_confidence": "high",
        }])

        anchored = self.processor._anchor_audio_files_to_segments(audio_df, segments, "P1")

        self.assertEqual(anchored.loc[0, "Datetime"], pd.Timestamp("2024-06-01T09:10:00.250Z"))
        self.assertEqual(
            anchored.loc[0, "anchor_source"],
            "svl_wave_marker+embedded_wav_metadata",
        )

    def test_bounded_correlation_recovers_known_offset(self):
        envelope = pd.Series(
            [40 + ((index * 17) % 23) + (index % 5) for index in range(120)],
            dtype=float,
        ).to_numpy()
        nominal_start = pd.Timestamp("2024-01-01T12:00:00Z")
        true_lag = 17
        measurement_index = pd.date_range(
            nominal_start - pd.Timedelta(minutes=5),
            periods=720,
            freq="s",
        )
        measurement = pd.Series(float("nan"), index=measurement_index)
        aligned_index = pd.date_range(
            nominal_start + pd.Timedelta(seconds=true_lag),
            periods=len(envelope),
            freq="s",
        )
        measurement.loc[aligned_index] = envelope

        result = self.processor._find_bounded_correlation_lag(
            envelope,
            nominal_start,
            measurement,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["lag_seconds"], true_lag)
        self.assertGreater(result["score"], 0.999)

    def test_bounded_correlation_covers_offset_just_over_five_minutes(self):
        envelope = pd.Series(
            [45 + ((index * 19) % 31) + (index % 7) for index in range(180)],
            dtype=float,
        ).to_numpy()
        nominal_start = pd.Timestamp("2026-06-30T12:30:00Z")
        true_lag = 313
        measurement_index = pd.date_range(
            nominal_start - pd.Timedelta(minutes=10),
            periods=1500,
            freq="s",
        )
        measurement = pd.Series(float("nan"), index=measurement_index)
        aligned_index = pd.date_range(
            nominal_start + pd.Timedelta(seconds=true_lag),
            periods=len(envelope),
            freq="s",
        )
        measurement.loc[aligned_index] = envelope

        result = self.processor._find_bounded_correlation_lag(
            envelope,
            nominal_start,
            measurement,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["lag_seconds"], true_lag)
        self.assertGreater(result["score"], 0.999)


if __name__ == "__main__":
    unittest.main()
