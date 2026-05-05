"""Regression test for lazy VLC import in audio_handler.py."""
import sys
import unittest
from unittest.mock import patch


class AudioHandlerVlcOptionalTests(unittest.TestCase):
    def test_can_import_without_vlc_installed(self):
        """audio_handler must be importable when python-vlc is absent."""
        # Simulate python-vlc missing by hiding the vlc module
        with patch.dict(sys.modules, {"vlc": None}):
            # Remove cached module if already loaded
            modules_to_remove = [
                k for k in sys.modules.keys()
                if k.startswith("noise_survey_analysis.core.audio_handler")
            ]
            for mod in modules_to_remove:
                del sys.modules[mod]

            # This must not raise ImportError
            from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler

            handler = AudioPlaybackHandler({})
            # Audio state constants must exist even without vlc
            self.assertIsNotNone(handler)
            self.assertFalse(handler.audio_available)

    def test_vlc_state_constants_available_when_vlc_missing(self):
        """When VLC is unavailable, dummy state constants must still exist."""
        with patch.dict(sys.modules, {"vlc": None}):
            modules_to_remove = [
                k for k in sys.modules.keys()
                if k.startswith("noise_survey_analysis.core.audio_handler")
            ]
            for mod in modules_to_remove:
                del sys.modules[mod]

            from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler
            handler = AudioPlaybackHandler({})
            # Should not crash referencing audio state
            self.assertIsNotNone(handler)
            self.assertFalse(handler.audio_available)


if __name__ == "__main__":
    unittest.main()
