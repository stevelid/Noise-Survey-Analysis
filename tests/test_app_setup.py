import json
import tempfile
import unittest
from pathlib import Path

from noise_survey_analysis.core.app_setup import load_config_and_prepare_sources


class AppSetupTests(unittest.TestCase):
    def test_loads_workspace_file_and_filters_disabled_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "workspace.json"
            config_path.write_text(
                json.dumps(
                    {
                        "output_filename": "dashboard.html",
                        "job_number": "1234",
                        "sourceConfigs": [
                            {"position_name": "P1", "enabled": True, "file_paths": ["a.csv"]},
                            {"position_name": "P2", "enabled": False, "file_paths": ["b.csv"]},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            output_filename, sources, job_number = load_config_and_prepare_sources(str(config_path))

            self.assertEqual(output_filename, "dashboard.html")
            self.assertEqual(job_number, "1234")
            self.assertEqual(sources, [{"position_name": "P1", "enabled": True, "file_paths": ["a.csv"]}])

    def test_groups_relative_sources_by_position_and_preserves_display_title(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            data_dir = root / "data"
            config_dir = root / "configs"
            data_dir.mkdir()
            config_dir.mkdir()

            file_a = data_dir / "overview.csv"
            file_b = data_dir / "log.csv"
            file_a.write_text("overview", encoding="utf-8")
            file_b.write_text("log", encoding="utf-8")

            config_path = config_dir / "job_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "output_filename": "dashboard.html",
                        "job_number": "5678",
                        "sources": [
                            {
                                "position": "P1",
                                "path": "../data/overview.csv",
                                "parser_type": "auto",
                                "display_title": " Living Room ",
                            },
                            {
                                "position": "P1",
                                "path": "../data/log.csv",
                                "parser_type": "auto",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            output_filename, sources, job_number = load_config_and_prepare_sources(str(config_path))

            self.assertEqual(output_filename, "dashboard.html")
            self.assertEqual(job_number, "5678")
            self.assertEqual(len(sources), 1)
            source = sources[0]
            self.assertEqual(source["position_name"], "P1")
            self.assertEqual(source["parser_type"], "auto")
            self.assertEqual(source["display_title"], "Living Room")
            self.assertEqual(source["file_paths"], {str(file_a.resolve()), str(file_b.resolve())})

    def test_missing_or_invalid_config_returns_nones(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing.json"
            self.assertEqual(load_config_and_prepare_sources(str(missing_path)), (None, None, None))

            invalid_path = Path(temp_dir) / "invalid.json"
            invalid_path.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_config_and_prepare_sources(str(invalid_path)), (None, None, None))


if __name__ == "__main__":
    unittest.main()
