import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from noise_survey_analysis.core.data_loaders import (
    scan_directory_for_sources,
    summarize_scanned_sources,
)


class DemoFileParser:
    pass


class DataLoaderTests(unittest.TestCase):
    def test_scan_directory_detects_audio_directory_once_and_sums_sizes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_dir = root / "Position A"
            audio_dir.mkdir()
            first = audio_dir / "first.wav"
            second = audio_dir / "second.WAV"
            first.write_bytes(b"1234")
            second.write_bytes(b"12")

            with patch(
                "noise_survey_analysis.core.data_loaders.NoiseParserFactory.get_parser",
                return_value=None,
            ):
                sources = scan_directory_for_sources(str(root))

            self.assertEqual(len(sources), 1)
            source = sources[0]
            self.assertEqual(source["position_name"], "Position A")
            self.assertEqual(source["file_path"], str(audio_dir))
            self.assertEqual(source["display_path"], "Position A/first.wav")
            self.assertEqual(source["data_type"], "Audio")
            self.assertEqual(source["parser_type"], "audio")
            self.assertEqual(source["file_size"], "2 .wav files")
            self.assertEqual(source["file_size_bytes"], 6)

    def test_scan_directory_detects_valid_config_and_skips_invalid_config_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid = root / "noise_survey_config_1234.json"
            invalid = root / "noise_survey_config_bad.json"
            valid.write_text(
                json.dumps(
                    {
                        "job_number": "1234",
                        "sources": [{"position_name": "P1"}, {"position_name": "P2"}],
                    }
                ),
                encoding="utf-8",
            )
            invalid.write_text(json.dumps({"job_number": "bad", "sources": {}}), encoding="utf-8")

            with patch(
                "noise_survey_analysis.core.data_loaders.NoiseParserFactory.get_parser",
                return_value=None,
            ):
                sources = scan_directory_for_sources(str(root))

            self.assertEqual(len(sources), 1)
            source = sources[0]
            self.assertEqual(source["position_name"], "Config (1234)")
            self.assertEqual(source["data_type"], "Config")
            self.assertEqual(source["parser_type"], "config")
            self.assertEqual(source["config_source_count"], 2)
            self.assertEqual(source["display_path"], "noise_survey_config_1234.json")

    def test_scan_directory_uses_parser_metadata_and_cleans_position_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "P1_summary"
            data_dir.mkdir()
            file_path = data_dir / "overview.csv"
            file_path.write_text("a,b\n1,2\n", encoding="utf-8")

            with patch(
                "noise_survey_analysis.core.data_loaders.NoiseParserFactory.get_parser",
                return_value=DemoFileParser(),
            ):
                sources = scan_directory_for_sources(str(root))

            self.assertEqual(len(sources), 1)
            source = sources[0]
            self.assertEqual(source["position_name"], "P1")
            self.assertEqual(source["display_path"], "P1_summary/overview.csv")
            self.assertEqual(source["data_type"], "Demo")
            self.assertEqual(source["parser_type"], "demo")
            self.assertEqual(source["enabled"], True)
            self.assertTrue(source["file_size"].endswith("KB"))
            self.assertGreater(source["file_size_bytes"], 0)

    def test_summarize_scanned_sources_counts_types_per_position(self):
        summary = summarize_scanned_sources(
            [
                {"position_name": "P1", "data_type": "Audio"},
                {"position_name": "P1", "data_type": "Audio"},
                {"position_name": "P1", "data_type": "Demo"},
                {"position_name": "P2", "data_type": "Config"},
                {},
            ]
        )

        self.assertEqual(summary["P1"]["Audio"], 2)
        self.assertEqual(summary["P1"]["Demo"], 1)
        self.assertEqual(summary["P2"]["Config"], 1)
        self.assertEqual(summary["Unknown Position"]["Unknown Type"], 1)


if __name__ == "__main__":
    unittest.main()
