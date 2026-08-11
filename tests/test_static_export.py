import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from noise_survey_analysis.export.static_export import generate_static_html
from noise_survey_analysis.visualization.dashBuilder import DashBuilder


class StaticExportTests(unittest.TestCase):
    def test_static_spectrogram_payload_is_marked_as_full_local_reservoir(self):
        prepared = {
            "log": {
                "prepared_params": {
                    "LZeq": {
                        "times_ms": [1000, 2000, 3000, 4000],
                        "levels_flat_transposed": [40, 41, 42, 43, 50, 51, 52, 53],
                        "frequency_labels": ["63 Hz", "125 Hz"],
                        "frequencies_hz": [63, 125],
                        "n_times": 4,
                        "n_freqs": 2,
                        "chunk_time_length": 2,
                        "time_step": 1000,
                        "min_val": 40,
                        "max_val": 53,
                        "min_time": 1000,
                        "max_time": 4000,
                        "initial_glyph_data": {
                            "x": [1000],
                            "y": [-0.5],
                            "dw": [2000],
                            "dh": [2],
                            "image": [[40, 41], [50, 51]],
                        },
                    }
                }
            }
        }

        payload = DashBuilder()._build_static_spectrogram_log_source_data(prepared, "LZeq")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["parameter"], ["LZeq"])
        self.assertEqual(payload["is_reservoir_payload"], [True])
        self.assertEqual(payload["n_times"], [4])
        self.assertEqual(len(payload["times_ms"][0]), 4)

    def test_generate_static_html_uses_job_number_filename_and_writes_output(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "job_config.json"
            config_path.write_text("{}", encoding="utf-8")

            fake_audio_processor = MagicMock()
            fake_builder = MagicMock()

            with patch(
                "noise_survey_analysis.export.static_export.load_config_and_prepare_sources",
                return_value=("ignored.html", [{"position_name": "P1"}], "4321"),
            ), patch(
                "noise_survey_analysis.export.static_export.DataManager",
                return_value=MagicMock(),
            ) as data_manager_cls, patch(
                "noise_survey_analysis.export.static_export.AudioDataProcessor",
                return_value=fake_audio_processor,
            ), patch(
                "noise_survey_analysis.export.static_export.DashBuilder",
                return_value=fake_builder,
            ), patch(
                "noise_survey_analysis.export.static_export.file_html",
                return_value="<html>ok</html>",
            ):
                output_path = generate_static_html(str(config_path))

            expected_path = Path(temp_dir) / "4321_survey_dashboard.html"
            self.assertEqual(output_path, expected_path)
            self.assertEqual(expected_path.read_text(encoding="utf-8"), "<html>ok</html>")
            data_manager_cls.assert_called_once_with(source_configurations=[{"position_name": "P1"}])
            fake_audio_processor.anchor_audio_files.assert_called_once()
            fake_builder.build_layout.assert_called_once()

    def test_generate_static_html_falls_back_to_job_number_in_config_filename(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "9876_saved_config.json"
            config_path.write_text("{}", encoding="utf-8")

            with patch(
                "noise_survey_analysis.export.static_export.load_config_and_prepare_sources",
                return_value=("fallback.html", [], None),
            ), patch(
                "noise_survey_analysis.export.static_export.DataManager",
                return_value=MagicMock(),
            ), patch(
                "noise_survey_analysis.export.static_export.AudioDataProcessor",
                return_value=MagicMock(),
            ), patch(
                "noise_survey_analysis.export.static_export.DashBuilder",
                return_value=MagicMock(),
            ), patch(
                "noise_survey_analysis.export.static_export.file_html",
                return_value="<html>ok</html>",
            ):
                output_path = generate_static_html(str(config_path))

            self.assertEqual(output_path, Path(temp_dir) / "9876_survey_dashboard.html")

    def test_generate_static_html_returns_none_when_config_loading_fails(self):
        with patch(
            "noise_survey_analysis.export.static_export.load_config_and_prepare_sources",
            return_value=(None, None, None),
        ):
            self.assertIsNone(generate_static_html("missing.json"))


if __name__ == "__main__":
    unittest.main()
