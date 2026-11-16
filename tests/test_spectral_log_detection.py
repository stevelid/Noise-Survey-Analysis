"""Deferred-log spectral detection for multi-file positions (NTi XL2 broadband + RTA logs)."""
import os
import tempfile
import unittest

from noise_survey_analysis.core.data_processors import estimate_log_spectral_threshold_seconds

NTI_123_LOG = (
    "XL2 Sound Level Meter Broadband Logging:\t\tx_123_Log.txt\n"
    "# Broadband LOG Results \n"
    "\tDate        \tTime      \tTimer     \tLAeq_dt  \tLAFmax_dt\n"
    "\t[YYYY-MM-DD]\t[hh:mm:ss]\t[hh:mm:ss]\t[dB]     \t[dB]     \n"
    "\t2026-11-04  \t13:14:53  \t00:00:07  \t50.1     \t55.2     \n"
    "\t2026-11-04  \t13:14:54  \t00:00:06  \t50.3     \t55.0     \n"
    "\t2026-11-04  \t13:14:55  \t00:00:05  \t50.2     \t55.4     \n"
)

NTI_RTA_LOG = (
    "XL2 RTA Spectrum Logging:\t\tx_RTA_3rd_Log_00.txt\n"
    "# RTA LOG Results \n"
    "\t            \t          \t          \t         \tLZeq_dt  \tLZeq_dt  \tLZeq_dt  \tLZeq_dt  \tLZeq_dt  \tLZeq_dt\n"
    "\tDate        \tTime      \tTimer     \tBand [Hz]\t6.3      \t8.0      \t10.0     \t12.5     \t16.0     \t20.0\n"
    "\t[YYYY-MM-DD]\t[hh:mm:ss]\t[hh:mm:ss]\t         \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]\n"
    "\t2026-11-04  \t13:14:53  \t00:00:07  \t         \t58.7     \t50.2     \t50.3     \t45.1     \t40.4     \t45.3\n"
    "\t2026-11-04  \t13:14:54  \t00:00:06  \t         \t58.2     \t52.3     \t51.8     \t49.8     \t44.7     \t47.3\n"
    "\t2026-11-04  \t13:14:55  \t00:00:05  \t         \t53.3     \t55.0     \t49.9     \t45.3     \t45.2     \t44.3\n"
)


class SpectralLogDetectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.broadband = os.path.join(self.tmp.name, "x_123_Log.txt")
        self.rta = os.path.join(self.tmp.name, "x_RTA_3rd_Log_00.txt")
        with open(self.broadband, "w", encoding="utf-8") as fh:
            fh.write(NTI_123_LOG)
        with open(self.rta, "w", encoding="utf-8") as fh:
            fh.write(NTI_RTA_LOG)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rta_log_after_broadband_log_is_detected(self):
        files = [{"file_path": self.broadband}, {"file_path": self.rta}]
        self.assertIsNotNone(estimate_log_spectral_threshold_seconds(files))

    def test_broadband_only_has_no_spectral_log(self):
        self.assertIsNone(estimate_log_spectral_threshold_seconds([{"file_path": self.broadband}]))


if __name__ == "__main__":
    unittest.main()
