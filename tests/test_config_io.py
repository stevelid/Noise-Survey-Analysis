import json
import tempfile
import unittest
from pathlib import Path

from noise_survey_analysis.core.config_io import save_config_from_selected_sources


class ConfigIoTests(unittest.TestCase):
    def test_save_config_supports_grouped_file_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_a = root / "overview.csv"
            file_b = root / "log.csv"
            file_a.write_text("a", encoding="utf-8")
            file_b.write_text("b", encoding="utf-8")

            cfg_path = save_config_from_selected_sources([
                {
                    "position_name": "P1",
                    "file_paths": [str(file_a), str(file_b)],
                    "parser_type": "auto",
                    "data_type": "unknown",
                }
            ])

            self.assertIsNotNone(cfg_path)
            self.assertTrue(Path(cfg_path).exists())

            config_data = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
            sources = config_data.get("sources", [])
            self.assertEqual(len(sources), 2)
            self.assertEqual({entry.get("position") for entry in sources}, {"P1"})
            self.assertEqual({entry.get("parser_type") for entry in sources}, {"auto"})

    def test_save_config_supports_file_path_and_parser_hint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            file_a = root / "single.csv"
            file_a.write_text("a", encoding="utf-8")

            cfg_path = save_config_from_selected_sources([
                {
                    "position": "P2",
                    "file_path": str(file_a),
                    "parser_type_hint": "generic",
                    "type": "totals",
                }
            ])

            self.assertIsNotNone(cfg_path)
            config_data = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
            sources = config_data.get("sources", [])
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0].get("position"), "P2")
            self.assertEqual(sources[0].get("parser_type"), "generic")
            self.assertEqual(sources[0].get("type"), "totals")


if __name__ == "__main__":
    unittest.main()
