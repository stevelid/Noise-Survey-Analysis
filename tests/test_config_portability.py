import importlib
import json
import os
import unittest
from unittest.mock import patch

import noise_survey_analysis.core.config as config


class ConfigPortabilityTests(unittest.TestCase):
    def _reload_config(self):
        return importlib.reload(config)

    def tearDown(self):
        self._reload_config()

    def test_defaults_do_not_embed_venta_paths(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = self._reload_config()

        values = [
            cfg.DEFAULT_BASE_JOB_DIR,
            cfg.GENERAL_SETTINGS.get("media_path", ""),
            json.dumps(cfg.DEFAULT_DATA_SOURCES),
        ]
        for value in values:
            self.assertNotIn("G:\\", value)
            self.assertNotIn("Shared drives\\Venta", value)
            self.assertNotIn("My Drive\\Programing", value)
        self.assertEqual(cfg.DEFAULT_DATA_SOURCES, [])

    def test_base_job_dir_and_media_path_can_be_set_by_environment(self):
        with patch.dict(
            os.environ,
            {
                "NOISE_SURVEY_BASE_JOB_DIR": r"D:\Jobs",
                "NOISE_SURVEY_MEDIA_PATH": r"D:\Media",
            },
            clear=True,
        ):
            cfg = self._reload_config()

        self.assertEqual(cfg.DEFAULT_BASE_JOB_DIR, r"D:\Jobs")
        self.assertEqual(cfg.GENERAL_SETTINGS["media_path"], r"D:\Media")

    def test_default_data_sources_can_be_loaded_from_environment_json(self):
        source = {
            "position_name": "P1",
            "file_path": r"D:\data\summary.csv",
            "parser_type": "svan",
            "enabled": True,
        }
        with patch.dict(
            os.environ,
            {"NOISE_SURVEY_DEFAULT_DATA_SOURCES_JSON": json.dumps([source])},
            clear=True,
        ):
            cfg = self._reload_config()

        self.assertEqual(cfg.DEFAULT_DATA_SOURCES, [source])


if __name__ == "__main__":
    unittest.main()
