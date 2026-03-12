import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from noise_survey_analysis.export.static_export import generate_static_html


class StaticExportTests(unittest.TestCase):
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
