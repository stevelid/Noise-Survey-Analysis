"""A refreshed or closed tab must not leave its session's audio playing."""
import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from noise_survey_analysis.core import audio_handler as audio_module
from noise_survey_analysis.core.app_callbacks import AppCallbacks, session_destroyed
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler


UTC = datetime.timezone.utc
FILE_START = datetime.datetime(2024, 1, 1, tzinfo=UTC)


def _build_handler():
    """A live handler with VLC stubbed out, registered like a real one."""
    handler = AudioPlaybackHandler({})
    handler.audio_available = True
    handler.vlc_instance = MagicMock()
    handler.player = MagicMock()
    handler.player.set_time.return_value = 0
    handler.player.play.return_value = 0
    handler.player.is_playing.return_value = True
    handler.player.get_time.return_value = 0
    handler.player.get_media.return_value = object()
    handler.player.get_state.return_value = 0
    handler.file_info_by_position = {"P1": [("/audio/rec.wav", FILE_START, 600.0)]}
    handler.current_position = "P1"
    handler.current_file = "/audio/rec.wav"
    handler.media_start_time = FILE_START
    handler.playback_monitor = MagicMock()
    handler.playback_monitor.is_alive.return_value = True
    with audio_module._live_handlers_lock:
        audio_module._live_handlers.add(handler)
    return handler


def _build_callbacks(handler, connection_count):
    doc = MagicMock()
    doc.session_context.session.connection_count = connection_count
    return AppCallbacks(
        doc=doc,
        audio_handler=handler,
        audio_control_source=MagicMock(),
        audio_status_source=MagicMock(),
        streaming_enabled=False,
    )


class ExclusivePlaybackTests(unittest.TestCase):
    def setUp(self):
        self.status_event = patch("noise_survey_analysis.core.audio_handler.status_console.event")
        self.status_event.start()
        self.addCleanup(self.status_event.stop)

    def test_playing_in_one_session_pauses_another(self):
        old_session = _build_handler()
        new_session = _build_handler()
        self.addCleanup(old_session.release)
        self.addCleanup(new_session.release)
        old_session._is_playing = True

        self.assertTrue(new_session.play(FILE_START + datetime.timedelta(seconds=30)))

        old_session.player.pause.assert_called_once()
        self.assertFalse(old_session.is_playing())
        new_session.player.pause.assert_not_called()

    def test_released_handler_is_not_touched_by_other_sessions(self):
        released = _build_handler()
        player = released.player
        released.release()
        player.reset_mock()

        other = _build_handler()
        self.addCleanup(other.release)
        other.play(FILE_START)

        player.pause.assert_not_called()
        self.assertNotIn(released, audio_module._live_handlers)


class DisconnectedSessionTests(unittest.TestCase):
    def _tick(self, callbacks, times):
        for _ in range(times):
            callbacks._periodic_update_audio_status()

    def test_audio_pauses_shortly_after_the_browser_disconnects(self):
        handler = _build_handler()
        handler._is_playing = True
        callbacks = _build_callbacks(handler, connection_count=0)
        self.addCleanup(callbacks.cleanup)

        self._tick(callbacks, AppCallbacks.DISCONNECTED_PAUSE_TICKS - 1)
        callbacks._audio_command_executor.submit(lambda: None).result(timeout=5)
        handler.player.pause.assert_not_called()

        self._tick(callbacks, 1)
        callbacks._audio_command_executor.submit(lambda: None).result(timeout=5)
        handler.player.pause.assert_called_once()
        self.assertFalse(handler.is_playing())

    def test_connected_session_keeps_playing(self):
        handler = _build_handler()
        handler._is_playing = True
        callbacks = _build_callbacks(handler, connection_count=1)
        self.addCleanup(callbacks.cleanup)

        self._tick(callbacks, AppCallbacks.DISCONNECTED_PAUSE_TICKS * 3)
        callbacks._audio_command_executor.submit(lambda: None).result(timeout=5)
        handler.player.pause.assert_not_called()

    def test_session_destroyed_stops_and_releases_the_player(self):
        handler = _build_handler()
        handler._is_playing = True
        player = handler.player
        callbacks = _build_callbacks(handler, connection_count=0)
        context = SimpleNamespace(id="s1", _app_callback_manager=callbacks)

        with patch("noise_survey_analysis.core.audio_handler.status_console.event"):
            session_destroyed(context)

        player.stop.assert_called()
        player.release.assert_called_once()
        self.assertFalse(handler.is_playing())
        self.assertNotIn(handler, audio_module._live_handlers)


if __name__ == "__main__":
    unittest.main()
