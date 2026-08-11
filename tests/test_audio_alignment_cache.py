import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from pandas.testing import assert_frame_equal

from noise_survey_analysis.core.audio_alignment_cache import (
    AudioAlignmentCache,
    build_audio_alignment_cache_key,
    build_source_fingerprint,
    capture_audio_alignment,
    restore_audio_alignment,
)


class _FakeAppData:
    def __init__(self, positions):
        self._positions = positions

    def positions(self):
        return list(self._positions)

    def __getitem__(self, position_name):
        return self._positions[position_name]


class AudioAlignmentCacheTests(unittest.TestCase):
    def test_key_changes_when_measurement_source_changes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "meter_log.csv"
            source_path.write_text("first", encoding="utf-8")
            configs = [
                {"position_name": "P1", "parser_type": "svan", "file_paths": [str(source_path)]}
            ]

            first_key = build_audio_alignment_cache_key(configs, {"search": 300})
            source_path.write_text("second and longer", encoding="utf-8")
            second_key = build_audio_alignment_cache_key(configs, {"search": 300})

            self.assertNotEqual(first_key, second_key)

    def test_source_fingerprint_is_stable_when_configs_are_reordered(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            first_path = Path(temporary_directory) / "first.csv"
            second_path = Path(temporary_directory) / "second.csv"
            first_path.write_text("first", encoding="utf-8")
            second_path.write_text("second", encoding="utf-8")
            configs = [
                {"position_name": "P1", "parser_type": "svan", "file_paths": [str(first_path)]},
                {"position_name": "P2", "parser_type": "nti", "file_paths": [str(second_path)]},
            ]

            first_key = build_source_fingerprint(configs)
            reordered_key = build_source_fingerprint(list(reversed(configs)))

            self.assertEqual(first_key, reordered_key)

    def test_audio_directory_key_tracks_only_audio_inputs(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            audio_directory = Path(temporary_directory)
            wav_path = audio_directory / "R1.WAV"
            wav_path.write_bytes(b"audio-one")
            unrelated_path = audio_directory / "notes.txt"
            unrelated_path.write_text("one", encoding="utf-8")
            configs = [
                {
                    "position_name": "P1",
                    "parser_type": "audio",
                    "file_paths": [str(audio_directory)],
                }
            ]

            first_key = build_audio_alignment_cache_key(configs, {})
            unrelated_path.write_text("changed", encoding="utf-8")
            unrelated_key = build_audio_alignment_cache_key(configs, {})
            wav_path.write_bytes(b"audio-two-is-different")
            changed_audio_key = build_audio_alignment_cache_key(configs, {})

            self.assertEqual(first_key, unrelated_key)
            self.assertNotEqual(first_key, changed_audio_key)

    def test_key_changes_when_alignment_settings_change(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_path = Path(temporary_directory) / "meter_log.csv"
            source_path.write_text("data", encoding="utf-8")
            configs = [
                {"position_name": "P1", "parser_type": "svan", "file_paths": [str(source_path)]}
            ]

            first_key = build_audio_alignment_cache_key(configs, {"search": 300})
            second_key = build_audio_alignment_cache_key(configs, {"search": 600})

            self.assertNotEqual(first_key, second_key)

    def test_snapshot_round_trip_restores_audio_metadata(self):
        original_frame = pd.DataFrame(
            {"filename": ["R1.WAV"], "start_time": [pd.Timestamp("2026-07-10T09:45:00Z")]}
        )
        source = _FakeAppData(
            {
                "P1": SimpleNamespace(has_audio_files=True, audio_files_list=original_frame),
                "P2": SimpleNamespace(has_audio_files=False, audio_files_list=None),
            }
        )
        snapshot = capture_audio_alignment(source)
        target = _FakeAppData(
            {
                "P1": SimpleNamespace(has_audio_files=True, audio_files_list=pd.DataFrame()),
                "P2": SimpleNamespace(has_audio_files=False, audio_files_list=None),
            }
        )

        restored = restore_audio_alignment(target, snapshot)

        self.assertTrue(restored)
        assert_frame_equal(target["P1"].audio_files_list, original_frame)

    def test_disk_cache_returns_independent_snapshots(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            cache_path = Path(temporary_directory) / "alignment.pkl"
            cache = AudioAlignmentCache(cache_path)
            frame = pd.DataFrame({"filename": ["R1.WAV"]})
            cache.put("audio-alignment-v1:test", {"P1": frame})

            reloaded = AudioAlignmentCache(cache_path)
            first = reloaded.get("audio-alignment-v1:test")
            first["P1"].loc[0, "filename"] = "changed.wav"
            second = reloaded.get("audio-alignment-v1:test")

            self.assertEqual(second["P1"].loc[0, "filename"], "R1.WAV")


if __name__ == "__main__":
    unittest.main()
