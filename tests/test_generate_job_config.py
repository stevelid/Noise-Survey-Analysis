import importlib
import os
import unittest
from unittest.mock import patch

import generate_job_config
import noise_survey_analysis.core.config as config


class GenerateJobConfigCliTests(unittest.TestCase):
    def _reload_modules(self):
        cfg = importlib.reload(config)
        generator = importlib.reload(generate_job_config)
        return cfg, generator

    def tearDown(self):
        self._reload_modules()

    def test_base_dir_defaults_to_portable_config_value(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg, generator = self._reload_modules()

        args = generator.build_parser().parse_args(["5882"])

        self.assertEqual(args.base_dir, cfg.DEFAULT_BASE_JOB_DIR)
        self.assertNotIn("G:/Shared drives/Venta/Jobs", args.base_dir)

    def test_base_dir_can_be_overridden_positionally(self):
        args = generate_job_config.build_parser().parse_args(["5882", r"D:\Jobs"])

        self.assertEqual(args.base_dir, r"D:\Jobs")


if __name__ == "__main__":
    unittest.main()
