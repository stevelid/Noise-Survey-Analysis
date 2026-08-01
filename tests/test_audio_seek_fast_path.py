"""Audio seek must not reload media it already has open, or block the document thread."""
import datetime
import threading
import time
import unittest
from unittest.mock import MagicMock

from noise_survey_analysis.core.app_callbacks import AppCallbacks
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler


UTC = datetime.timezone.utc


def _build_handler(files):
    """An AudioPlaybackHandler with VLC stubbed out and a pre-seeded file index."""
    handler = AudioPlaybackHandler({})
    handler.audio_available = True
    handler.vlc_instance = MagicMock()
    handler.player = MagicMock()
    handler.player.set_time.return_value = 0
    handler.player.play.return_value = 0
    handler.player.is_playing.return_value = True
    # Keep the real monitor thread on numeric rails if it starts against this stub.
    handler.player.get_time.return_value = 0
    handler.player.get_media.return_value = None
    handler.player.get_state.return_value = 0
    handler.file_info_by_position = {"P1": files}
    handler.current_position = "P1"
    return handler


class AudioSeekFastPathTests(unittest.TestCase):
    def setUp(self):
        self.file_start = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        self.duration = 600.0  # 10 minutes
        self.files = [("/audio/rec_0000.wav", self.file_start, self.duration)]
        self.second_start = self.file_start + datetime.timedelta(seconds=self.duration)
        self.second_file = ("/audio/rec_0010.wav", self.second_start, self.duration)

    def test_seek_within_loaded_file_does_not_reload_media(self):
        handler = _build_handler(self.files)
        handler.current_file = "/audio/rec_0000.wav"
        handler.media_start_time = self.file_start
        handler.current_file_duration = self.duration
        handler.player.get_media.return_value = object()  # media already open
        # Pretend the monitor is already running so no real thread is spawned.
        handler.playback_monitor = MagicMock()
        handler.playback_monitor.is_alive.return_value = True

        target = self.file_start + datetime.timedelta(seconds=125)
        self.assertTrue(handler.play(target))

        handler.vlc_instance.media_new.assert_not_called()
        handler.player.set_media.assert_not_called()
        handler.player.stop.assert_not_called()
        handler.player.set_time.assert_called_once_with(125 * 1000)
        self.assertTrue(handler._is_playing)

    def test_seek_into_a_different_file_still_reloads(self):
        handler = _build_handler(self.files + [self.second_file])
        handler.current_file = "/audio/rec_0000.wav"
        handler.media_start_time = self.file_start
        handler.current_file_duration = self.duration

        target = self.second_start + datetime.timedelta(seconds=5)
        self.assertTrue(handler.play(target))

        handler.vlc_instance.media_new.assert_called_once_with("/audio/rec_0010.wav")
        self.assertEqual(handler.current_file, "/audio/rec_0010.wav")
        handler.stop_monitor = True

    def test_failed_in_place_seek_falls_back_to_reload(self):
        handler = _build_handler(self.files)
        handler.current_file = "/audio/rec_0000.wav"
        handler.media_start_time = self.file_start
        handler.current_file_duration = self.duration
        handler.player.get_media.return_value = object()  # media already open
        handler.player.set_time.return_value = -1  # VLC rejects the seek

        target = self.file_start + datetime.timedelta(seconds=30)
        self.assertTrue(handler.play(target))

        handler.vlc_instance.media_new.assert_called_once_with("/audio/rec_0000.wav")
        handler.stop_monitor = True

    def test_monitor_thread_restarting_itself_does_not_self_join(self):
        """File rollover runs play() on the monitor thread; joining itself would raise."""
        handler = _build_handler(self.files)
        handler.current_file = "/audio/rec_0000.wav"

        errors = []

        def on_monitor_thread():
            try:
                handler.playback_monitor = threading.current_thread()
                handler._perform_stop_actions()
                handler._restart_playback_monitor()
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)

        thread = threading.Thread(target=on_monitor_thread)
        thread.start()
        thread.join(5)

        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        handler.stop_monitor = True


class AudioCommandDispatchTests(unittest.TestCase):
    def test_control_command_does_not_run_on_the_calling_thread(self):
        """Blocking VLC work must be handed off, not run on Bokeh's IOLoop."""
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        started = threading.Event()
        release = threading.Event()
        ran_on = {}

        def slow_play(_timestamp):
            ran_on['thread'] = threading.current_thread()
            started.set()
            release.wait(5)

        audio_handler.play.side_effect = slow_play

        doc = MagicMock()
        callbacks = AppCallbacks(
            doc=doc,
            audio_handler=audio_handler,
            audio_control_source=MagicMock(),
            audio_status_source=MagicMock(),
        )

        caller = threading.current_thread()
        try:
            callbacks._handle_audio_control_command(
                'data', None,
                {'command': ['play'], 'position_id': ['P1'], 'value': [1704067200000]},
            )
            # The submit call must return without waiting for the blocking work.
            self.assertTrue(started.wait(5), "audio command never started")
            self.assertIsNot(ran_on['thread'], caller)
        finally:
            release.set()
            callbacks.cleanup()

    def test_commands_are_applied_in_order(self):
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        applied = []
        done = threading.Event()
        audio_handler.play.side_effect = lambda _ts: applied.append('play')

        def record_pause():
            applied.append('pause')
            done.set()

        audio_handler.pause.side_effect = record_pause

        callbacks = AppCallbacks(
            doc=MagicMock(),
            audio_handler=audio_handler,
            audio_control_source=MagicMock(),
            audio_status_source=MagicMock(),
        )
        try:
            callbacks._handle_audio_control_command(
                'data', None,
                {'command': ['play'], 'position_id': ['P1'], 'value': [1704067200000]},
            )
            callbacks._handle_audio_control_command(
                'data', None,
                {'command': ['pause'], 'position_id': ['P1'], 'value': [None]},
            )
            self.assertTrue(done.wait(5), "commands never completed")
            self.assertEqual(applied, ['play', 'pause'])
        finally:
            callbacks.cleanup()


class AudioCleanupLifecycleTests(unittest.TestCase):
    """VLC must not be released while a worker thread is still calling into it."""

    def _callbacks(self, audio_handler):
        return AppCallbacks(
            doc=MagicMock(),
            audio_handler=audio_handler,
            audio_control_source=MagicMock(),
            audio_status_source=MagicMock(),
        )

    @staticmethod
    def _play_command():
        return ('data', None,
                {'command': ['play'], 'position_id': ['P1'], 'value': [1704067200000]})

    def test_cleanup_waits_for_an_active_command_before_releasing_vlc(self):
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        started = threading.Event()
        finish = threading.Event()
        order = []

        def slow_play(_timestamp):
            order.append('play:start')
            started.set()
            finish.wait(5)
            order.append('play:end')

        audio_handler.play.side_effect = slow_play
        audio_handler.release.side_effect = lambda: order.append('release')

        callbacks = self._callbacks(audio_handler)
        callbacks._handle_audio_control_command(*self._play_command())
        self.assertTrue(started.wait(5), "command never started")

        # Release the command shortly after cleanup begins, so cleanup genuinely has to
        # wait rather than finding it already done.
        threading.Timer(0.2, finish.set).start()
        callbacks.cleanup()

        self.assertEqual(order, ['play:start', 'play:end', 'release'])

    def test_cleanup_cancels_queued_commands_and_never_touches_vlc(self):
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        started = threading.Event()
        finish = threading.Event()
        audio_handler.play.side_effect = lambda _ts: (started.set(), finish.wait(5))

        callbacks = self._callbacks(audio_handler)
        callbacks._handle_audio_control_command(*self._play_command())
        self.assertTrue(started.wait(5), "first command never started")

        # These queue behind the blocked command.
        for _ in range(3):
            callbacks._handle_audio_control_command(
                'data', None, {'command': ['pause'], 'position_id': ['P1'], 'value': [None]})

        threading.Timer(0.2, finish.set).start()
        callbacks.cleanup()

        # cleanup() returning is not by itself proof the queued commands were dropped -
        # without cancellation the worker would still be draining them. Give it a window
        # to misbehave in before asserting it did not.
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not audio_handler.pause.called:
            time.sleep(0.02)

        audio_handler.pause.assert_not_called()
        audio_handler.release.assert_called_once()

    def test_commands_submitted_after_cleanup_are_ignored(self):
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        callbacks = self._callbacks(audio_handler)
        callbacks.cleanup()

        callbacks._handle_audio_control_command(*self._play_command())

        audio_handler.play.assert_not_called()

    def test_cleanup_defers_release_when_a_command_outlives_the_grace_period(self):
        """A wedged command still owns the VLC player, so cleanup must not free it.

        Releasing on timeout would recreate the very race the grace period exists to
        avoid. Ownership passes to the command: whoever finishes last releases.
        """
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        started = threading.Event()
        let_it_finish = threading.Event()
        audio_handler.play.side_effect = lambda _ts: (started.set(), let_it_finish.wait(30))

        callbacks = self._callbacks(audio_handler)
        callbacks.AUDIO_SHUTDOWN_GRACE_SECONDS = 0.3
        callbacks._handle_audio_control_command(*self._play_command())
        self.assertTrue(started.wait(5), "command never started")

        try:
            began = time.monotonic()
            callbacks.cleanup()
            elapsed = time.monotonic() - began

            # Teardown is bounded by the grace period, not by the stuck command.
            self.assertLess(elapsed, 5)
            # ...and VLC is still alive, because the command is still using it.
            audio_handler.release.assert_not_called()
        finally:
            let_it_finish.set()

        # Once the command finally returns, it hands the resources back.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not audio_handler.release.called:
            time.sleep(0.02)
        audio_handler.release.assert_called_once()

    def test_a_command_that_never_finishes_leaves_vlc_alive(self):
        """Leaking a player beats freeing one a live thread is still calling into."""
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        started = threading.Event()
        wedged = threading.Event()
        audio_handler.play.side_effect = lambda _ts: (started.set(), wedged.wait(30))

        callbacks = self._callbacks(audio_handler)
        callbacks.AUDIO_SHUTDOWN_GRACE_SECONDS = 0.2
        callbacks._handle_audio_control_command(*self._play_command())
        self.assertTrue(started.wait(5), "command never started")

        try:
            callbacks.cleanup()
            time.sleep(0.4)
            audio_handler.release.assert_not_called()
        finally:
            wedged.set()

    def test_release_happens_exactly_once_when_a_deferred_command_finishes(self):
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        started = threading.Event()
        let_it_finish = threading.Event()
        audio_handler.play.side_effect = lambda _ts: (started.set(), let_it_finish.wait(30))

        callbacks = self._callbacks(audio_handler)
        callbacks.AUDIO_SHUTDOWN_GRACE_SECONDS = 0.2
        callbacks._handle_audio_control_command(*self._play_command())
        self.assertTrue(started.wait(5), "command never started")

        callbacks.cleanup()
        callbacks.cleanup()  # A second teardown must not double-release either.
        let_it_finish.set()

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not audio_handler.release.called:
            time.sleep(0.02)
        time.sleep(0.2)
        self.assertEqual(audio_handler.release.call_count, 1)

    def test_cleanup_from_the_worker_thread_does_not_deadlock(self):
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        callbacks = self._callbacks(audio_handler)
        finished = threading.Event()
        errors = []

        def cleanup_from_worker(_timestamp):
            try:
                callbacks.cleanup()
            except Exception as exc:  # pragma: no cover - failure path
                errors.append(exc)
            finally:
                finished.set()

        audio_handler.play.side_effect = cleanup_from_worker
        callbacks._handle_audio_control_command(*self._play_command())

        self.assertTrue(finished.wait(5), "cleanup deadlocked on its own executor")
        self.assertEqual(errors, [])

    def test_cleanup_is_safe_to_call_twice_and_releases_once(self):
        audio_handler = MagicMock()
        audio_handler.audio_available = True

        callbacks = self._callbacks(audio_handler)
        callbacks.cleanup()
        callbacks.cleanup()

        # Freeing a VLC player twice is its own hazard.
        self.assertEqual(audio_handler.release.call_count, 1)


if __name__ == "__main__":
    unittest.main()
