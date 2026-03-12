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


if __name__ == "__main__":
    unittest.main()
