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

    def test_media_path_and_data_sources_do_not_embed_local_paths(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = self._reload_config()

        values = [
            cfg.GENERAL_SETTINGS.get("media_path", ""),
            json.dumps(cfg.DEFAULT_DATA_SOURCES),
        ]
        for value in values:
            self.assertNotIn("G:\\", value)
            self.assertNotIn("Shared drives\\Venta", value)
            self.assertNotIn("My Drive\\Programing", value)
        self.assertEqual(cfg.DEFAULT_DATA_SOURCES, [])

    def test_base_job_dir_defaults_to_the_venta_jobs_folder(self):
        # Deliberately not portable: every machine that runs this has the Venta
        # shared drive synced, and the file selector should open there rather
        # than in the user's home folder.
        with patch.dict(os.environ, {}, clear=True):
            cfg = self._reload_config()

        self.assertTrue(
            cfg.DEFAULT_BASE_JOB_DIR.endswith(os.path.join("Shared drives", "Venta", "Jobs")),
            f"Expected the Venta Jobs folder, got {cfg.DEFAULT_BASE_JOB_DIR!r}",
        )

    def test_base_job_dir_falls_back_to_the_expected_path_when_no_drive_is_mounted(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("os.path.isdir", return_value=False):
                cfg = self._reload_config()

            # Showing the expected location is more useful than silently
            # dropping the user somewhere unrelated.
            self.assertEqual(cfg.DEFAULT_BASE_JOB_DIR, cfg.VENTA_JOBS_DIR)

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
