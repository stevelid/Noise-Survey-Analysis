import json
import struct
import tempfile
import unittest
import wave
from pathlib import Path

import pandas as pd

from noise_survey_analysis.core.data_parsers import AudioFileParser


class AudioFileParserTests(unittest.TestCase):
    @staticmethod
    def _write_tiny_wav(path: Path) -> None:
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(100)
            wav_file.writeframes(struct.pack("<100h", *([0] * 100)))

    def test_parser_uses_svl_audio_index_before_filesystem_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            wav_path = directory / "R1.WAV"
            self._write_tiny_wav(wav_path)
            (directory / "L1_audio_index.json").write_text(
                json.dumps({
                    "version": 1,
                    "files": [{
                        "filename": "R1.WAV",
                        "logger_record_index": 0,
                        "start_time": "2026-06-24T13:15:00.000",
                    }],
                }),
                encoding="utf-8",
            )

            parsed = AudioFileParser(timezone="Europe/London").parse(str(directory))
            row = parsed.totals_df.iloc[0]

            self.assertEqual(row["anchor_source"], "svl_wave_marker")
            self.assertEqual(row["Datetime"], pd.Timestamp("2026-06-24T12:15:00Z"))
            self.assertEqual(row["recorded_start_time"], pd.Timestamp("2026-06-24T12:15:00Z"))

    def test_decodes_riff_info_fields(self):
        def field(name: bytes, value: bytes) -> bytes:
            payload = value + b"\x00"
            return name + struct.pack("<I", len(payload)) + payload + (b"\x00" if len(payload) & 1 else b"")

        payload = b"INFO" + field(b"ICRD", b"2026-06-24") + field(
            b"ICMT",
            b"Ch.1: 108.31dB, 20uPa 13:15:00 125",
        )

        decoded = AudioFileParser._decode_riff_info(payload)

        self.assertEqual(decoded["ICRD"], "2026-06-24")
        self.assertIn("13:15:00 125", decoded["ICMT"])


if __name__ == "__main__":
    unittest.main()
