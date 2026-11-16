"""A closed tab's session is released about 20 s after its browser went away."""
import unittest
from unittest.mock import MagicMock, patch

from noise_survey_analysis.core.app_callbacks import AppCallbacks, session_destroyed


def _callbacks(connection_count=1, media_token=None):
    doc = MagicMock()
    doc.session_context.session.connection_count = connection_count
    handler = MagicMock()
    handler.audio_available = False
    callbacks = AppCallbacks(
        doc=doc,
        audio_handler=handler,
        audio_control_source=MagicMock(),
        audio_status_source=MagicMock(),
        streaming_enabled=False,
        server_data_handler=MagicMock(),
        media_token=media_token,
    )
    callbacks.STALE_RELEASE_SECONDS = 20.0
    return callbacks, doc, handler


class StaleSessionReleaseTests(unittest.TestCase):
    def setUp(self):
        patcher = patch("noise_survey_analysis.core.status_console.event")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_connected_session_is_never_released(self):
        callbacks, _, _ = _callbacks(connection_count=1)
        for now in (0.0, 100.0, 1000.0):
            self.assertFalse(callbacks._release_if_stale(now=now))

    def test_released_after_grace_period(self):
        callbacks, doc, handler = _callbacks(connection_count=0)
        data_handler = callbacks.server_data_handler
        hook = MagicMock()
        callbacks.release_hooks.append(hook)

        self.assertFalse(callbacks._release_if_stale(now=100.0))   # starts the clock
        self.assertFalse(callbacks._release_if_stale(now=119.0))
        self.assertTrue(callbacks._release_if_stale(now=120.5))

        data_handler.cleanup.assert_called_once()
        handler.release.assert_called_once()
        hook.assert_called_once()
        self.assertIsNone(callbacks.server_data_handler)
        doc.clear.assert_called_once()
        # Later ticks do nothing more.
        self.assertTrue(callbacks._release_if_stale(now=500.0))
        hook.assert_called_once()

    def test_reconnect_inside_grace_period_resets_the_clock(self):
        callbacks, doc, _ = _callbacks(connection_count=0)
        session = doc.session_context.session
        callbacks._release_if_stale(now=0.0)
        callbacks._release_if_stale(now=15.0)
        session.connection_count = 1                     # the tab came back
        self.assertFalse(callbacks._release_if_stale(now=16.0))
        session.connection_count = 0
        self.assertFalse(callbacks._release_if_stale(now=30.0))
        self.assertFalse(callbacks._release_if_stale(now=45.0))   # only 15 s since it left again
        doc.clear.assert_not_called()
        self.assertTrue(callbacks._release_if_stale(now=50.5))

    def test_session_destroyed_after_release_is_a_no_op(self):
        callbacks, doc, handler = _callbacks(connection_count=0)
        callbacks._release_if_stale(now=0.0)
        callbacks._release_if_stale(now=21.0)
        handler.release.assert_called_once()
        doc.session_context._app_callback_manager = callbacks
        session_destroyed(doc.session_context)
        handler.release.assert_called_once()

    def test_disabled_with_zero(self):
        callbacks, _, _ = _callbacks(connection_count=0)
        callbacks.STALE_RELEASE_SECONDS = 0
        self.assertFalse(callbacks._release_if_stale(now=0.0))
        self.assertFalse(callbacks._release_if_stale(now=10_000.0))

    def test_media_token_is_unregistered_on_cleanup(self):
        callbacks, _, _ = _callbacks(media_token="tok123")
        with patch("noise_survey_analysis.core.media_server.unregister_session") as unregister:
            callbacks.cleanup()
        unregister.assert_called_once_with("tok123")
        self.assertIsNone(callbacks.media_token)


if __name__ == "__main__":
    unittest.main()
