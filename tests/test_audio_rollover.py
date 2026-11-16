"""Auto-advance across audio files, real dB boost, rate persistence, start position, coalescing."""
import datetime
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

from noise_survey_analysis.core import audio_handler as ah
from noise_survey_analysis.core.app_callbacks import AppCallbacks
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler, decide_file_rollover

UTC = datetime.timezone.utc
T0 = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)


def _td(seconds):
    return datetime.timedelta(seconds=seconds)


class DecideFileRolloverTests(unittest.TestCase):
    def setUp(self):
        self.next_file = ("/a/rec_1.wav", T0 + _td(600), 600.0)

    def test_mid_file_continues(self):
        action, nxt, _ = decide_file_rollover(T0, 600.0, T0 + _td(300), False, self.next_file)
        self.assertEqual((action, nxt), ('continue', None))

    def test_near_end_advances_to_back_to_back_file_from_its_start(self):
        action, nxt, offset = decide_file_rollover(T0, 600.0, T0 + _td(599.9), False, self.next_file)
        self.assertEqual(action, 'next')
        self.assertEqual(nxt, self.next_file)
        self.assertEqual(offset, 0.0)

    def test_vlc_ended_advances_even_without_a_position(self):
        action, nxt, _ = decide_file_rollover(T0, 600.0, None, True, self.next_file)
        self.assertEqual((action, nxt), ('next', self.next_file))

    def test_small_gap_is_bridged(self):
        later = ("/a/rec_1.wav", T0 + _td(601.5), 600.0)
        action, nxt, offset = decide_file_rollover(T0, 600.0, None, True, later)
        self.assertEqual((action, nxt, offset), ('next', later, 0.0))

    def test_large_gap_stops_cleanly(self):
        later = ("/a/rec_1.wav", T0 + _td(700), 600.0)
        self.assertEqual(decide_file_rollover(T0, 600.0, None, True, later)[0], 'stop')

    def test_last_file_stops(self):
        self.assertEqual(decide_file_rollover(T0, 600.0, None, True, None)[0], 'stop')

    def test_overlapping_next_file_starts_where_previous_ended(self):
        overlapping = ("/a/rec_1.wav", T0 + _td(599), 600.0)
        action, _, offset = decide_file_rollover(T0, 600.0, None, True, overlapping)
        self.assertEqual(action, 'next')
        self.assertAlmostEqual(offset, 1.0)


def _handler(files):
    handler = AudioPlaybackHandler({})
    handler.audio_available = True
    handler.vlc_instance = MagicMock()
    handler.player = MagicMock()
    handler.player.set_time.return_value = 0
    handler.player.play.return_value = 0
    handler.player.is_playing.return_value = True
    handler.player.get_time.return_value = 0
    handler.player.get_media.return_value = None
    handler.player.get_state.return_value = 0
    handler.player.set_equalizer.return_value = 0
    handler.player.audio_set_volume.return_value = 0
    handler.file_info_by_position = {"P1": files}
    handler.current_position = "P1"
    return handler


FILES = [
    ("/a/rec_0.wav", T0, 600.0),
    ("/a/rec_1.wav", T0 + _td(600), 600.0),
    ("/a/rec_2.wav", T0 + _td(5000), 600.0),
]


class MonitorRolloverTests(unittest.TestCase):
    def _open_first_file(self, handler):
        handler.current_file = "/a/rec_0.wav"
        handler.media_start_time = T0
        handler.current_file_duration = 600.0
        handler._is_playing = True
        handler.player.get_media.return_value = object()

    def test_advance_opens_next_file_and_restarts_monitor_on_the_monitor_thread(self):
        handler = _handler(FILES)
        self._open_first_file(handler)
        handler._restart_playback_monitor = MagicMock()
        result = {}

        def run():
            handler.playback_monitor = threading.current_thread()
            result['ok'] = handler._advance_to_next_file("/a/rec_0.wav", FILES[1], 0.0)

        t = threading.Thread(target=run)
        t.start()
        t.join(5)

        self.assertTrue(result['ok'])
        handler.vlc_instance.media_new.assert_called_once_with("/a/rec_1.wav")
        self.assertEqual(handler.current_file, "/a/rec_1.wav")
        self.assertEqual(handler.media_start_time, FILES[1][1])
        self.assertTrue(handler._is_playing)
        handler._restart_playback_monitor.assert_called_once()

    def test_ensure_monitor_restarts_when_caller_is_the_monitor(self):
        handler = _handler(FILES)
        handler._restart_playback_monitor = MagicMock()

        def run():
            handler.playback_monitor = threading.current_thread()
            handler._ensure_playback_monitor()

        t = threading.Thread(target=run)
        t.start()
        t.join(5)
        handler._restart_playback_monitor.assert_called_once()

    def test_advance_is_deferred_while_a_user_command_holds_the_transport(self):
        handler = _handler(FILES)
        self._open_first_file(handler)
        acquired = threading.Event()
        release = threading.Event()

        def hold():
            with handler._transport_lock:
                acquired.set()
                release.wait(5)

        holder = threading.Thread(target=hold)
        holder.start()
        acquired.wait(5)
        try:
            self.assertIsNone(handler._advance_to_next_file("/a/rec_0.wav", FILES[1], 0.0))
            handler.vlc_instance.media_new.assert_not_called()
        finally:
            release.set()
            holder.join(5)

    def test_advance_yields_to_a_user_change_of_file(self):
        handler = _handler(FILES)
        self._open_first_file(handler)
        handler.current_file = "/a/rec_2.wav"  # user jumped elsewhere meanwhile
        handler._advance_to_next_file("/a/rec_0.wav", FILES[1], 0.0)
        handler.vlc_instance.media_new.assert_not_called()

    def test_monitor_loop_rolls_over_when_vlc_reports_ended(self):
        handler = _handler(FILES)
        self._open_first_file(handler)
        handler.player.get_state.return_value = ah.vlc.State.Ended
        handler.player.get_time.return_value = 599900
        handler._advance_to_next_file = MagicMock(return_value=True)

        handler._monitor_playback()

        handler._advance_to_next_file.assert_called_once_with("/a/rec_0.wav", FILES[1], 0.0)

    def test_monitor_loop_stops_cleanly_across_a_large_gap(self):
        handler = _handler(FILES)
        handler.current_file = "/a/rec_1.wav"
        handler.media_start_time = FILES[1][1]
        handler.current_file_duration = 600.0
        handler._is_playing = True
        handler.player.get_media.return_value = object()
        handler.player.get_state.return_value = ah.vlc.State.Ended
        handler.player.get_time.return_value = 599900

        with patch.object(ah.status_console, 'event'):
            handler._monitor_playback()

        self.assertFalse(handler._is_playing)
        handler.player.stop.assert_called()
        handler.vlc_instance.media_new.assert_not_called()

    def test_paused_transport_near_the_end_does_not_roll_over(self):
        handler = _handler(FILES)
        self._open_first_file(handler)
        handler._is_playing = False
        handler.player.get_state.return_value = ah.vlc.State.Paused
        handler.player.get_time.return_value = 599950
        handler._advance_to_next_file = MagicMock()

        def stop_soon():
            time.sleep(0.25)
            handler.stop_monitor = True

        threading.Thread(target=stop_soon).start()
        handler._monitor_playback()
        handler._advance_to_next_file.assert_not_called()


class GainTests(unittest.TestCase):
    def test_boost_uses_equalizer_preamp_and_unity_volume(self):
        handler = _handler(FILES)
        eq = MagicMock()
        fake_vlc = MagicMock()
        fake_vlc.AudioEqualizer.return_value = eq
        with patch.object(ah, 'vlc', fake_vlc):
            self.assertTrue(handler.set_amplification(20))
        eq.set_preamp.assert_called_once_with(20.0)
        handler.player.set_equalizer.assert_called_once_with(eq)
        handler.player.audio_set_volume.assert_called_with(100)

    def test_gain_above_preamp_cap_is_topped_up_with_volume(self):
        handler = _handler(FILES)
        eq = MagicMock()
        fake_vlc = MagicMock()
        fake_vlc.AudioEqualizer.return_value = eq
        with patch.object(ah, 'vlc', fake_vlc):
            handler.set_amplification(26)
        eq.set_preamp.assert_called_once_with(20.0)
        volume = handler.player.audio_set_volume.call_args.args[0]
        self.assertAlmostEqual(volume, 200, delta=2)  # +6 dB of linear volume

    def test_boost_off_detaches_equalizer(self):
        handler = _handler(FILES)
        fake_vlc = MagicMock()
        with patch.object(ah, 'vlc', fake_vlc):
            handler.set_amplification(20)
            handler.player.set_equalizer.reset_mock()
            handler.set_amplification(0)
        handler.player.set_equalizer.assert_called_once_with(None)
        handler.player.audio_set_volume.assert_called_with(100)

    def test_falls_back_to_volume_when_equalizer_missing(self):
        handler = _handler(FILES)

        class NoEqualizerVlc:
            State = ah.vlc.State

        with patch.object(ah, 'vlc', NoEqualizerVlc()):
            handler.set_amplification(20)
        handler.player.audio_set_volume.assert_called_with(200)

    def test_gain_is_reapplied_when_new_media_opens(self):
        handler = _handler(FILES)
        eq = MagicMock()
        fake_vlc = MagicMock()
        fake_vlc.AudioEqualizer.return_value = eq
        fake_vlc.State = ah.vlc.State
        with patch.object(ah, 'vlc', fake_vlc):
            handler.set_amplification(20)
            handler.player.set_equalizer.reset_mock()
            handler._restart_playback_monitor = MagicMock()
            handler._open_and_play("/a/rec_1.wav", 0.0, FILES[1][1], 600.0)
        handler.player.set_equalizer.assert_called_once_with(eq)


class RateAndStartPositionTests(unittest.TestCase):
    def test_rate_is_reapplied_after_media_reload(self):
        handler = _handler(FILES)
        handler.player.get_media.return_value = object()
        handler.set_playback_rate(2.0)
        handler.player.set_rate.reset_mock()
        handler._restart_playback_monitor = MagicMock()
        handler._open_and_play("/a/rec_1.wav", 0.0, FILES[1][1], 600.0)
        handler.player.set_rate.assert_called_with(2.0)
        self.assertEqual(handler.get_playback_rate(), 2.0)

    def test_rate_set_before_any_media_is_remembered(self):
        handler = _handler(FILES)
        self.assertFalse(handler.set_playback_rate(1.5))
        self.assertEqual(handler.get_playback_rate(), 1.5)

    def test_start_offset_is_passed_as_media_option_not_sleep_and_seek(self):
        handler = _handler(FILES)
        handler._restart_playback_monitor = MagicMock()
        media = MagicMock()
        handler.vlc_instance.media_new.return_value = media
        handler.player.get_time.return_value = 125000  # VLC honoured :start-time
        with patch.object(ah.time, 'sleep') as sleep:
            handler._open_and_play("/a/rec_0.wav", 125.0, T0, 600.0)
        media.add_option.assert_called_once_with(":start-time=125.000")
        handler.player.set_time.assert_not_called()
        sleep.assert_not_called()

    def test_set_time_fallback_when_start_time_ignored(self):
        handler = _handler(FILES)
        handler._restart_playback_monitor = MagicMock()
        handler.player.get_time.return_value = 40  # VLC started near zero
        handler._open_and_play("/a/rec_0.wav", 125.0, T0, 600.0)
        handler.player.set_time.assert_called_once_with(125000)

    def test_zero_offset_adds_no_media_option(self):
        handler = _handler(FILES)
        handler._restart_playback_monitor = MagicMock()
        media = MagicMock()
        handler.vlc_instance.media_new.return_value = media
        handler._open_and_play("/a/rec_0.wav", 0.0, T0, 600.0)
        media.add_option.assert_not_called()


class CommandCoalescingTests(unittest.TestCase):
    def test_only_the_latest_pending_play_runs(self):
        audio_handler = MagicMock()
        audio_handler.audio_available = True
        audio_handler.current_position = "P1"

        first_started = threading.Event()
        release = threading.Event()
        played = []

        def slow_play(ts):
            played.append(ts)
            first_started.set()
            release.wait(5)

        audio_handler.play.side_effect = slow_play
        callbacks = AppCallbacks(
            doc=MagicMock(), audio_handler=audio_handler,
            audio_control_source=MagicMock(), audio_status_source=MagicMock(),
        )
        try:
            def send(ms):
                callbacks._handle_audio_control_command(
                    'data', None, {'command': ['play'], 'position_id': ['P1'], 'value': [ms]})

            send(1704067200000)
            self.assertTrue(first_started.wait(5))
            for ms in (1704067201000, 1704067202000, 1704067203000):
                send(ms)
            release.set()

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and len(played) < 2:
                time.sleep(0.02)
            time.sleep(0.2)
            self.assertEqual(len(played), 2)
            self.assertEqual(int(played[-1].timestamp() * 1000), 1704067203000)
        finally:
            release.set()
            callbacks.cleanup()


if __name__ == "__main__":
    unittest.main()
