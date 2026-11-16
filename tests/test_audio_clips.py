import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf

from noise_survey_analysis.export import audio_clips


class Position:
    def __init__(self, files):
        self.audio_files_list = files


class Data:
    def __init__(self, positions):
        self._p = positions

    def positions(self):
        return list(self._p)

    def __getitem__(self, key):
        return self._p[key]


class AudioClipTests(unittest.TestCase):
    def test_clip_is_16k_mono_pcm16_and_long_regions_are_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "a.wav"
            sf.write(str(wav), np.random.default_rng(0).uniform(-0.2, 0.2, (48000 * 120, 2)).astype("float32"), 48000)
            start = pd.Timestamp("1970-01-01 00:00:00")
            files = pd.DataFrame({"full_path": [str(wav)], "Datetime": [start], "duration_sec": [120.0]})
            data = Data({"P1": Position(files)})
            state = {"regions": {"byId": {
                "1": {"areas": [{"start": 10_000, "end": 40_000}]},
                "2": {"areas": [{"start": 0, "end": 90_000}]}}}}
            out = audio_clips.write_region_clips(data, state, Path(tmp) / "x_clips")
            self.assertEqual(list(out), ["1"])
            self.assertEqual(out["1"]["P1"], "x_clips/region_1_P1.wav")
            info = sf.info(str(Path(tmp) / "x_clips" / "region_1_P1.wav"))
            self.assertEqual((info.samplerate, info.channels, info.subtype), (16000, 1, "PCM_16"))
            self.assertAlmostEqual(info.duration, 30.0, delta=0.05)


class AudioClipTimingTests(unittest.TestCase):
    def _two_files(self, tmp):
        """Two consecutive 20 s files: constant 0.25 then constant 0.5."""
        rate = 16000
        a, b = Path(tmp) / "a.wav", Path(tmp) / "b.wav"
        sf.write(str(a), np.full(rate * 20, 0.25, dtype="float32"), rate)
        sf.write(str(b), np.full(rate * 20, 0.5, dtype="float32"), rate)
        t0 = pd.Timestamp("1970-01-01 00:00:00")
        return pd.DataFrame({"full_path": [str(a), str(b)],
                             "Datetime": [t0, t0 + pd.Timedelta(seconds=20)],
                             "duration_sec": [20.0, 20.0]})

    def _first_sample(self, tmp, name):
        samples, rate = sf.read(str(Path(tmp) / name / "region_1_P1.wav"))
        return float(samples[rate])  # one second in

    def test_region_spanning_two_files_is_stitched(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Data({"P1": Position(self._two_files(tmp))})
            state = {"regions": {"byId": {"1": {"areas": [{"start": 15_000, "end": 25_000}]}}}}
            out = audio_clips.write_region_clips(data, state, Path(tmp) / "c")
            samples, rate = sf.read(str(Path(tmp) / "c" / "region_1_P1.wav"))
            self.assertAlmostEqual(len(samples) / rate, 10.0, delta=0.05)
            self.assertAlmostEqual(float(samples[rate]), 0.25, delta=0.01)       # 1 s in: file one
            self.assertAlmostEqual(float(samples[rate * 9]), 0.5, delta=0.01)    # 9 s in: file two
            self.assertIn("P1", out["1"])

    def test_audio_offset_is_added_to_the_chart_offset(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Data({"P1": Position(self._two_files(tmp))})
            state = {"regions": {"byId": {"1": {"areas": [{"start": 22_000, "end": 26_000}]}}}}
            # chart offset 2 s only: data 20-24 s is file two
            audio_clips.write_region_clips(data, state, Path(tmp) / "c", {"P1": 2000.0}, {"P1": 0.0})
            self.assertAlmostEqual(self._first_sample(tmp, "c"), 0.5, delta=0.01)
            # plus a 4 s audio offset: data 16-20 s is file one
            audio_clips.write_region_clips(data, state, Path(tmp) / "d", {"P1": 2000.0}, {"P1": 4000.0})
            self.assertAlmostEqual(self._first_sample(tmp, "d"), 0.25, delta=0.01)

    def test_meters_marked_absent_get_no_clip(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = self._two_files(tmp)
            data = Data({"P1": Position(files), "P2": Position(files)})
            state = {"regions": {"byId": {"1": {"positionId": "P1", "areas": [{"start": 1_000, "end": 5_000}],
                                                "meterStates": {"P2": "absent"}}}}}
            out = audio_clips.write_region_clips(data, state, Path(tmp) / "c")
            self.assertEqual(list(out["1"]), ["P1"])


if __name__ == "__main__":
    unittest.main()
