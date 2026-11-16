"""
Audio playback handler for Noise Survey Analysis.

This module provides audio playback functionality that can be synchronized with visualizations.
Uses the VLC media player to play audio files synchronized with visualizations.
"""

import os
import time
import datetime
import threading
import re
import weakref
from typing import Callable, Optional, List, Tuple
import logging

# Lazy import VLC to allow static generation without python-vlc installed
try:
    import vlc
    _vlc_available = True
except ImportError:
    vlc = None
    _vlc_available = False

if not _vlc_available:
    class _DummyVLCState:
        Playing = 3
        Buffering = 4
        Paused = 5
        Ended = 6
        Stopped = 0
        Error = 7
    class _DummyVLC:
        State = _DummyVLCState
    vlc = _DummyVLC()

import pandas as pd # Make sure pandas is imported

# Configure Logging
logger = logging.getLogger(__name__)

from noise_survey_analysis.core import status_console

# Every handler in this server process that still owns a VLC player. All sessions
# play through the same speakers, and an abandoned session (refreshed or closed tab)
# lingers until Bokeh's unused-session-lifetime expires - so starting playback in one
# session pauses every other (see AudioPlaybackHandler._claim_exclusive_playback).
_live_handlers = weakref.WeakSet()
_live_handlers_lock = threading.RLock()

# Auto-advance tuning. VLC reports Ended at the true end of a file; the position check
# is a backstop for builds that go quiet without ever reporting it.
ROLLOVER_MARGIN_MS = 150
# Consecutive recordings are usually back to back (or a few ms apart). A bigger gap
# means the meter was not recording, so carrying on would play unrelated audio.
MAX_ROLLOVER_GAP_SECONDS = 2.0
# VLC's equalizer preamp is limited to +/-20 dB.
MAX_EQUALIZER_PREAMP_DB = 20.0


def decide_file_rollover(file_start, file_duration, position, vlc_ended, next_file,
                         max_gap_seconds=MAX_ROLLOVER_GAP_SECONDS,
                         margin_ms=ROLLOVER_MARGIN_MS):
    """
    Decide what the playback monitor should do for the file that is currently open.

    Pure so it can be tested without VLC.

    Args:
        file_start: timezone-aware start of the open file.
        file_duration: its duration in seconds.
        position: current playback datetime, or None if VLC has no position.
        vlc_ended: True when VLC reports the media Ended (or Stopped at its end).
        next_file: ``(path, start, duration)`` of the next recording, or None.

    Returns:
        ``(action, next_file, offset_seconds)`` where action is ``'continue'`` (still
        inside the file), ``'next'`` (open ``next_file`` at ``offset_seconds``) or
        ``'stop'`` (end of the audio: stop cleanly).
    """
    file_end = file_start + datetime.timedelta(seconds=file_duration)
    at_end = bool(vlc_ended)
    if not at_end and position is not None:
        at_end = position >= file_end - datetime.timedelta(milliseconds=margin_ms)
    if not at_end:
        return 'continue', None, 0.0
    if next_file is None:
        return 'stop', None, 0.0
    _, next_start, next_duration = next_file
    gap_seconds = (next_start - file_end).total_seconds()
    if gap_seconds > max_gap_seconds:
        return 'stop', None, 0.0
    # Recordings that overlap slightly: carry on from where the previous one ended.
    offset = max(0.0, -gap_seconds)
    if next_duration is not None and offset >= next_duration:
        return 'stop', None, 0.0
    return 'next', next_file, offset


class AudioPlaybackHandler:
    """
    Handles audio playback from audio files based on timestamp selection.
    Integrates with Bokeh charts for visualization of audio position.
    Uses Python-VLC bindings for reliable playback control.
    Includes a simple time lockout for the play method to prevent rapid successive calls.
    """

    # A play request this close before the first recording starts at that recording;
    # anything earlier has no audio.
    SNAP_TO_FIRST_FILE_TOLERANCE_SECONDS = 60.0

    def __init__(self, position_data: dict):
        """
        Initialize the audio playback handler. It now reads pre-processed,
        anchored audio file information directly from the position_data.

        Args:
            position_data (dict): The main data dictionary containing all positions,
                                  their dataframes, and audio paths.
        """
        self.file_info_by_position = {}
        self.current_position = None
        self.current_amplification = 0
        self._playback_rate = 1.0
        self._equalizer = None
        # Serialises transport changes (user commands vs. the monitor's file rollover).
        self._transport_lock = threading.RLock()

        # Core playback state (initialised regardless of VLC availability)
        self.vlc_instance = None
        self.player = None
        self._is_playing = False
        self.current_file = None
        self.media_start_time = None
        self.current_file_duration = None
        self.playback_monitor = None
        self.position_callback = None
        self.stop_monitor = False
        self.audio_available = False

        # Initialize VLC
        if not _vlc_available:
            logger.info("python-vlc not available. Audio will be disabled.")
            self.vlc_instance = self.player = None
            self.audio_available = False
        else:
            try:
                self.vlc_instance = vlc.Instance('--no-xlib', '--quiet')
                self.player = self.vlc_instance.media_player_new()
                if self.vlc_instance is None or self.player is None:
                    raise RuntimeError("Failed to initialize VLC instance or player.")
                self.audio_available = True
                with _live_handlers_lock:
                    _live_handlers.add(self)
            except Exception as e:
                logger.error(f"VLC initialization failed: {e}. Audio will be disabled.", exc_info=True)
                self.vlc_instance = self.player = None
                self.audio_available = False

        # --- NEW, SIMPLIFIED INITIALIZATION LOGIC ---
        logger.debug("AudioPlaybackHandler: Indexing pre-processed audio data...")
        for position_name, data_dict in position_data.items():
            if not getattr(data_dict, 'has_audio_files', False):
                continue

            audio_df = data_dict.audio_files_list
            
            # The DataManager should have already added the 'Datetime' column.
            if 'Datetime' not in audio_df.columns:
                logger.warning(f"Audio file list for '{position_name}' is missing anchored 'Datetime' column. Skipping audio for this position.")
                continue

            files_to_process = []
            for _, row in audio_df.iterrows():
                # The row['Datetime'] is now the correct, UTC-aware timestamp
                if pd.isna(row['Datetime']):
                    logger.warning(
                        "Skipping audio file without anchored datetime for '%s': %s",
                        position_name,
                        row.get('full_path'),
                    )
                    continue
                files_to_process.append((row['full_path'], row['Datetime'], row['duration_sec']))
            
            self.file_info_by_position[position_name] = files_to_process
            logger.debug(f"Indexed {len(files_to_process)} pre-anchored audio files for position '{position_name}'.")
            if files_to_process:
                first_start = files_to_process[0][1]
                last_start = files_to_process[-1][1]
                last_dur = files_to_process[-1][2]
                logger.debug(f"  Audio range for '{position_name}': {first_start} -> {last_start} + {last_dur}s")

    def set_current_position(self, position: str) -> bool:
        """
        Sets the active position to get audio from.
        """
        if position == self.current_position:
            return True

        if not self.audio_available:
            available = position in self.file_info_by_position
            if available:
                self.current_position = position
                logger.info(
                    "Audio playback is disabled; recording position '%s' without enabling playback.",
                    position,
                )
            else:
                logger.warning(
                    "Audio playback is disabled and no indexed audio files were found for position '%s'.",
                    position,
                )
                self.current_position = None
            return available

        if self._is_playing:
            self.stop()

        if position in self.file_info_by_position:
            self.current_position = position
            logger.info(f"Audio position set to '{position}'.")
            return True
        else:
            logger.warning(f"No indexed audio files found for position '{position}'.")
            self.current_position = None
            return False

    def _find_file_for_timestamp(self, timestamp: datetime.datetime, position: Optional[str] = None) -> Tuple[Optional[str], float, Optional[datetime.datetime], Optional[float]]:
        """Finds the correct audio file and offset for a timestamp in the current position."""
        # Use the provided position or fall back to the instance's current_position
        target_position = position if position is not None else self.current_position

        if not target_position or target_position not in self.file_info_by_position:
            logger.warning(f"No indexed audio files found for position '{target_position}'.")
            return None, 0, None, None

        # Sort files by start time to ensure correct chronological processing
        sorted_files = self.file_info_by_position[target_position]

        # Handle case where timestamp is None (play from beginning)
        if timestamp is None:
            if sorted_files:
                filepath, start_time, duration_sec = sorted_files[0]
                logger.info("No timestamp provided. Starting playback from the first audio file.")
                return filepath, 0, start_time, duration_sec
            else:
                logger.warning(f"Play called with no timestamp and no audio files available for position '{target_position}'.")
                return None, 0, None, None

        # Find the file that contains the timestamp
        for filepath, start_time, duration_sec in sorted_files:
            if duration_sec <= 0:
                logger.warning(f"Invalid duration for file: {os.path.basename(filepath)}. Skipping.")
                continue

            end_time = start_time + datetime.timedelta(seconds=duration_sec)

            # This comparison will now work because both 'start_time' and 'timestamp' are timezone-aware
            if start_time <= timestamp < end_time:
                offset = (timestamp - start_time).total_seconds()
                return filepath, offset, start_time, duration_sec
            elif timestamp < start_time: # If timestamp is before this file, and thus before all subsequent files
                # Just before the very first file: snap to its start. Further out there is
                # no audio for that time, and snapping would play an unrelated recording
                # (possibly days away) and drag the playback cursor out of the view.
                if filepath == sorted_files[0][0]:
                    if (start_time - timestamp).total_seconds() > self.SNAP_TO_FIRST_FILE_TOLERANCE_SECONDS:
                        logger.warning(f"Timestamp {timestamp} is before the first audio file ({start_time}) for position '{target_position}'. No audio at this time.")
                        return None, 0, None, None
                    logger.info(f"Timestamp {timestamp} is before the first audio file. Snapping to start of {os.path.basename(filepath)}.")
                    return filepath, 0, start_time, duration_sec
                else:
                    # If it's before this file but not the first, it means it falls in a gap or before any known file.
                    # This case should ideally not happen if data is contiguous, but handle it.
                    logger.warning(f"Timestamp {timestamp} falls in a gap before {os.path.basename(filepath)}. Cannot find exact match.")
                    return None, 0, None, None

        # If loop completes, timestamp is after all known files
        logger.warning(f"Timestamp {timestamp} is outside the playable range for position '{target_position}'.")
        return None, 0, None, None

    def play(self, timestamp: Optional[datetime.datetime], position_callback: Optional[Callable] = None) -> bool:
        """
        Play audio starting at the specified timestamp.
        If timestamp is None, plays from the start of the first available file.

        Parameters:
        timestamp: Datetime object for the desired playback position
        position_callback: Optional callback function to report playback position

        Returns:
        bool: True if playback was successfully initiated, False if an error occurred.
        """
        with self._transport_lock:
            return self._play_impl(timestamp, position_callback)

    def _play_impl(self, timestamp: Optional[datetime.datetime], position_callback: Optional[Callable] = None) -> bool:
        logger.debug(f"Play call proceeding. Timestamp: {timestamp}")

        if not self.audio_available or not self.player or not self.vlc_instance:
            logger.warning("Play requested but audio playback is unavailable.")
            self._is_playing = False
            return False

        self._claim_exclusive_playback()

        # Capture the transport state before any fallback teardown so status
        # reporting can distinguish a seek from a fresh play.
        was_playing = self._is_playing

        # Resolve the target before tearing anything down: this is a pure lookup over
        # the indexed file list, and knowing the target lets us skip the reload
        # entirely when it lands in the recording that is already open.
        filepath, offset_seconds, file_start_time, file_duration = self._find_file_for_timestamp(timestamp, self.current_position)
        if not filepath:
            logger.warning(f"No audio file found for timestamp: {timestamp} in position: {self.current_position or 'default'}")
            self._perform_stop_actions()
            self._is_playing = False # Ensure state is correct
            return False # Indicate failure

        # Fast path: the requested instant is inside the media already loaded, so seek
        # in place.  Reloading costs a monitor-thread join, a fresh media object and two
        # settling sleeps - well over half a second - for no change of source.
        if filepath == self.current_file and self.player.get_media() is not None:
            logger.debug(
                "Seeking within already-loaded media to %.2fs offset (no reload)",
                offset_seconds,
            )
            if position_callback:
                self.position_callback = position_callback
            if self._seek_within_current_media(offset_seconds):
                self._is_playing = True
                self._ensure_playback_monitor()
                position_info = f" ({self.current_position})" if self.current_position else ""
                when = timestamp.strftime('%d/%m %H:%M:%S') if timestamp is not None else 'start'
                status_console.event(
                    'audio',
                    f"{'seek' if was_playing else 'play'} {when}{position_info}  "
                    f"{os.path.basename(filepath)} +{offset_seconds:.1f}s",
                )
                return True
            logger.debug("In-place seek failed; falling back to a full reload.")

        # Stop existing playback cleanly before starting new playback.
        # This is the key to handling rapid switching between positions.
        self._perform_stop_actions()

        # Output the current file being played to terminal
        position_info = f" ({self.current_position})" if self.current_position else ""
        if self.current_file != filepath:
            logger.info(f"Playing file: {os.path.basename(filepath)}{position_info}")

        # A cross-file seek takes the reload path, so report the requested time
        # after the previous transport has been stopped.
        when = timestamp.strftime('%d/%m %H:%M:%S') if timestamp is not None else 'start'
        status_console.event(
            'audio',
            f"{'seek' if was_playing else 'play'} {when}{position_info}  "
            f"{os.path.basename(filepath)} +{offset_seconds:.1f}s",
        )

        return self._open_and_play(filepath, offset_seconds, file_start_time, file_duration, position_callback)

    def _open_and_play(self, filepath, offset_seconds, file_start_time, file_duration,
                       position_callback=None) -> bool:
        """
        Open ``filepath`` and start it ``offset_seconds`` in, then start the monitor.

        The caller has already stopped any previous transport. Shared by play() and the
        monitor's file rollover.
        """
        # Store current state
        self.current_file = filepath
        self.media_start_time = file_start_time
        self.position_callback = position_callback # Store latest callback
        self.current_file_duration = file_duration

        # Create a new media and set it to the player
        try:
            media = self.vlc_instance.media_new(filepath)
            if not media:
                logger.error(f"VLC failed to create media for: {filepath}")
                self._is_playing = False
                return False
            if offset_seconds and offset_seconds > 0:
                # Starting at the offset inside VLC avoids the audible blip from the
                # file's first moments and the unreliable play(); sleep; set_time() dance.
                media.add_option(f":start-time={offset_seconds:.3f}")
            self.player.set_media(media)
            media.release()

            # A new media resets the gain stage and playback rate in VLC; restore both.
            self._apply_gain()

            play_result = self.player.play()
            if play_result == -1:
                logger.error("VLC failed to play media.")
                self._is_playing = False
                return False

            self._reapply_playback_rate()
            self._verify_start_position(offset_seconds)
            self._reapply_playback_rate()

            final_state = self.player.get_state()
            if final_state not in [vlc.State.Playing, vlc.State.Buffering]:
                    logger.warning(f"VLC player not in Playing/Buffering state after play/seek (State: {final_state}).")

        except Exception as e:
            logger.error(f"Error during VLC media setup/play/seek: {e}", exc_info=True)
            self._is_playing = False
            return False # Indicate failure

        self._is_playing = True
        self._restart_playback_monitor()

        return True # Indicate successful initiation

    # How long to wait for VLC to report a position after play() before giving up.
    START_VERIFY_TIMEOUT_SECONDS = 0.5
    # A start position further than this from the request is treated as ignored.
    START_VERIFY_TOLERANCE_MS = 2000

    def _verify_start_position(self, offset_seconds: float) -> None:
        """
        Fall back to set_time() if VLC ignored ``:start-time`` and began near zero.

        Only matters for non-trivial offsets; polls rather than sleeping a fixed time so
        a normal start costs a few milliseconds.
        """
        if not offset_seconds or offset_seconds <= 1.0:
            return
        target_ms = int(offset_seconds * 1000)
        deadline = time.monotonic() + self.START_VERIFY_TIMEOUT_SECONDS
        current_ms = -1
        while time.monotonic() < deadline:
            try:
                current_ms = self.player.get_time()
            except Exception:
                current_ms = -1
            if isinstance(current_ms, (int, float)) and current_ms >= 0:
                break
            time.sleep(0.02)
        if isinstance(current_ms, (int, float)) and current_ms >= 0 \
                and abs(current_ms - target_ms) <= self.START_VERIFY_TOLERANCE_MS:
            return
        logger.debug("Start position %sms not honoured (VLC at %sms); seeking explicitly.", target_ms, current_ms)
        if self.player.set_time(target_ms) == -1:
            logger.warning(f"VLC failed to set time to {target_ms}ms.")

    def _claim_exclusive_playback(self):
        """Pause every other live handler so only this one is audible."""
        with _live_handlers_lock:
            others = [h for h in _live_handlers if h is not self]
            for other in others:
                try:
                    if other.pause():
                        logger.info("Paused audio from another session so this one can play.")
                except Exception as e:
                    logger.warning(f"Could not pause another session's audio: {e}")

    def _seek_within_current_media(self, offset_seconds: float) -> bool:
        """
        Move the already-loaded media to ``offset_seconds`` without reloading it.

        Returns False if VLC rejects the seek, so callers can fall back to a reload.
        """
        try:
            if self.player.set_time(int(offset_seconds * 1000)) == -1:
                logger.warning(f"VLC failed to set time to {int(offset_seconds * 1000)}ms.")
                return False
            if not self.player.is_playing():
                if self.player.play() == -1:
                    logger.error("VLC failed to resume playback after an in-place seek.")
                    return False
            return True
        except Exception as exc:
            logger.error(f"Error seeking within current media: {exc}", exc_info=True)
            return False

    def _restart_playback_monitor(self):
        """Stop any live monitor thread and start a fresh one."""
        if self.playback_monitor and self.playback_monitor.is_alive():
            # The monitor itself calls play() to roll over to the next file, so it can
            # reach here on its own thread; joining that would raise.  It breaks out of
            # its loop straight after this call either way.
            if self.playback_monitor is threading.current_thread():
                logger.debug("Monitor thread is restarting itself; skipping join.")
            else:
                logger.warning("Previous monitor thread still alive before starting new one.")
                self.stop_monitor = True  # Tell the old one to stop
                self.playback_monitor.join(0.5)  # wait a bit for it.

        self.stop_monitor = False  # Reset flag for new thread
        self.playback_monitor = threading.Thread(target=self._monitor_playback)
        self.playback_monitor.daemon = True
        self.playback_monitor.start()

    def _ensure_playback_monitor(self):
        """Start the monitor only if it is not already running (in-place seek path)."""
        monitor = self.playback_monitor
        if monitor and monitor.is_alive() and monitor is not threading.current_thread():
            self.stop_monitor = False
            return
        # No monitor, or the caller *is* the monitor (about to exit its loop): start fresh.
        self._restart_playback_monitor()

    def pause(self):
        if not self.audio_available or not self.player:
            logger.debug("Pause requested but audio playback is unavailable.")
            return False

        if self._is_playing and self.player.is_playing():
            self.player.pause()
            self._is_playing = False
            logger.info("Playback paused")
            status_console.event('audio', 'paused')
            return True
        return False

    def resume(self):
        # ... (implementation unchanged)
        if not self.audio_available or not self.player:
            logger.debug("Resume requested but audio playback is unavailable.")
            return False

        if not self._is_playing and self.player.get_media():
            if self.player.get_state() == vlc.State.Paused:
                 self._claim_exclusive_playback()
                 self.player.play()
                 self._is_playing = True
                 logger.info("Playback resumed")
                 status_console.event('audio', 'resumed')
                 return True
            else:
                 logger.warning(f"Cannot resume playback, player state is {self.player.get_state()}")
                 return False
        return False

    def stop(self):
        """
        Stop audio playback.
        (No change needed for lockout strategy, but uses helper)
        """
        if not self.audio_available or not self.player:
            logger.debug("Stop requested but audio playback is unavailable.")
            self._is_playing = False
            return False

        # No lockout specific logic needed here, just perform the stop
        return self._perform_stop_actions()

    def _perform_stop_actions(self) -> bool:
        """Helper to perform the actual player stop and thread join actions."""
        # Stop monitor thread first
        if self.playback_monitor and self.playback_monitor.is_alive():
            self.stop_monitor = True
            # The monitor reaches here via its own file-rollover play() call; a thread
            # cannot join itself, and it exits its loop immediately after regardless.
            if self.playback_monitor is threading.current_thread():
                logger.debug("Monitor thread is stopping itself; skipping join.")
            else:
                self.playback_monitor.join(0.5)
                if self.playback_monitor.is_alive():
                    logger.warning("Playback monitor thread did not stop cleanly.")

        if not self.audio_available or not self.player:
            self._is_playing = False
            return False

        # Stop VLC player
        was_playing_or_paused = self.player.is_playing() or self.player.get_state() == vlc.State.Paused
        try:
             self.player.stop()
        except Exception as e:
            logger.error(f"Error stopping VLC player: {e}")

        # Update state
        self._is_playing = False

        if was_playing_or_paused:
            logger.info("Playback stopped")
            status_console.event('audio', 'stopped')
            return True
        return False

    # --- get_current_position remains the same ---
    def get_current_position(self) -> Optional[datetime.datetime]:
        # ... (implementation unchanged)
        if not self.audio_available or not self.player:
            return None

        if not self.player.get_media() or not self.media_start_time:
            return None
        time_ms = self.player.get_time()
        if time_ms < 0:
            return None
        seconds = time_ms / 1000
        try:
            current_pos = self.media_start_time + datetime.timedelta(seconds=seconds)
            return current_pos
        except TypeError: # Handle case where media_start_time might be None unexpectedly
             logger.error("Cannot calculate current position, media_start_time is not set.")
             return None

    def release(self):
        """
        Properly releases all VLC resources.
        Should be called when the audio handler is no longer needed.
        """
        logger.info("Releasing VLC resources...")
        # Deregister first, under the lock, so no other session can pause this player
        # while it is being freed.
        with _live_handlers_lock:
            _live_handlers.discard(self)
        try:
            # Stop any ongoing playback first
            self.stop()
            
            # Release the player
            if self.player:
                self.player.release()
                logger.debug("VLC player released")
            
            # Release the VLC instance
            if self.vlc_instance:
                self.vlc_instance.release()
                logger.debug("VLC instance released")
            
            # Clear references
            self.player = None
            self.vlc_instance = None
            self._is_playing = False
            self.current_file = None
            self.media_start_time = None
            self.position_callback = None
            self.audio_available = False

            logger.info("VLC resources released successfully")
        except Exception as e:
            logger.error(f"Error releasing VLC resources: {e}", exc_info=True)
            # Don't re-raise - we want to continue cleanup even if release fails

    def _next_file_after(self, filepath):
        """The recording that follows ``filepath`` in the current position, or None."""
        files = self.file_info_by_position.get(self.current_position) or []
        for index, entry in enumerate(files):
            if entry[0] == filepath:
                for candidate in files[index + 1:]:
                    if candidate[2] and candidate[2] > 0:
                        return candidate
                return None
        return None

    def _advance_to_next_file(self, from_file, next_file, offset_seconds):
        """
        Roll playback over to ``next_file`` from the monitor thread.

        Returns True when the next file is playing, False when playback was stopped,
        and None when a user command currently owns the transport (try again).
        """
        if not self._transport_lock.acquire(blocking=False):
            return None
        try:
            if self.current_file != from_file or self.stop_monitor:
                # The user moved on while we were deciding; their command wins.
                return True
            path, start, duration = next_file
            self._perform_stop_actions()
            status_console.event(
                'audio',
                f"next file  {os.path.basename(path)} +{offset_seconds:.1f}s",
            )
            if self._open_and_play(path, offset_seconds, start, duration, self.position_callback):
                return True
            logger.warning("Monitor: could not start the next audio file; stopping playback.")
            self._is_playing = False
            return False
        finally:
            self._transport_lock.release()

    def _finish_playback(self):
        """Stop at the end of the available audio so the UI sees is_playing=False."""
        self._is_playing = False
        try:
            self.player.stop()
        except Exception as e:
            logger.error(f"Error stopping VLC player at end of audio: {e}")
        status_console.event('audio', 'end of audio')

    def _reapply_playback_rate(self):
        """Restore the user's playback rate after VLC resets it on a media change."""
        if abs(self._playback_rate - 1.0) < 0.0001:
            return
        try:
            self.player.set_rate(self._playback_rate)
        except Exception as e:
            logger.error(f"Error re-applying playback rate: {e}")

    def _apply_gain(self):
        """
        Apply ``current_amplification`` (dB) to the player.

        VLC's volume control is linear amplitude (200% is only +6 dB), so real gain
        comes from the audio equalizer's preamp, which is in dB (capped at +20). The
        software volume stays at 100% so the boost does not stack on top and clip.
        Anything above the preamp cap is made up with the volume control. If the
        equalizer is unavailable, fall back to the volume-only mapping.
        """
        if not self.audio_available or not self.player:
            return False
        db = float(self.current_amplification or 0)
        eq_class = getattr(vlc, 'AudioEqualizer', None)

        if db <= 0:
            if self._equalizer is not None:
                self._set_equalizer(None)
            self.player.audio_set_volume(100)
            return True

        if eq_class is not None:
            try:
                preamp = min(db, MAX_EQUALIZER_PREAMP_DB)
                equalizer = eq_class()
                equalizer.set_preamp(preamp)
                if self.player.set_equalizer(equalizer) == 0:
                    self._equalizer = equalizer  # keep a reference alive
                    extra_db = db - preamp
                    volume = int(round(100 * (10 ** (extra_db / 20.0)))) if extra_db > 0 else 100
                    self.player.audio_set_volume(min(volume, 400))
                    return True
                logger.warning("VLC rejected the equalizer; falling back to volume-based boost.")
            except Exception as e:
                logger.warning(f"VLC equalizer unavailable ({e}); falling back to volume-based boost.")
        else:
            logger.warning("python-vlc has no AudioEqualizer; falling back to volume-based boost (about +6 dB).")

        self._equalizer = None
        volume_map = {0: 100, 20: 200, 40: 400}
        return self.player.audio_set_volume(volume_map.get(int(db), 100)) == 0

    def _set_equalizer(self, equalizer):
        """Attach (or with None, detach) an equalizer, ignoring builds that lack support."""
        if getattr(vlc, 'AudioEqualizer', None) is None and equalizer is not None:
            return False
        try:
            result = self.player.set_equalizer(equalizer)
            self._equalizer = equalizer
            return result == 0
        except Exception as e:
            logger.debug(f"Could not change VLC equalizer: {e}")
            return False

    def _monitor_playback(self):
        if not self.audio_available or not self.player:
            return

        last_file = None
        last_pos = None
        while not self.stop_monitor and self.player.get_media():
            current_state = self.player.get_state()
            if current_state == vlc.State.Error:
                logger.debug("Monitor: Playback errored. Stopping monitor.")
                self._is_playing = False
                break
            vlc_finished = current_state in [vlc.State.Ended, vlc.State.Stopped]
            if not vlc_finished and current_state not in [vlc.State.Playing, vlc.State.Paused, vlc.State.Buffering]:
                 logger.debug(f"Monitor: Player in unexpected state: {current_state}")

            if last_file is None or self.current_file != last_file:
                logger.debug(f"Monitor: File changed to: {os.path.basename(self.current_file)}")
                last_file = self.current_file

            current_pos = self.get_current_position()
            if current_pos:
                last_pos = current_pos

            # A paused transport must not roll over just because it is parked near the end.
            if (self._is_playing or vlc_finished) and self.media_start_time and self.current_file_duration:
                current_file = self.current_file
                try:
                    action, next_file, offset = decide_file_rollover(
                        self.media_start_time,
                        self.current_file_duration,
                        current_pos or (last_pos if vlc_finished else None),
                        current_state == vlc.State.Ended,
                        self._next_file_after(current_file),
                    )
                except (TypeError, AttributeError) as e:
                    logger.error(f"Monitor: Error comparing datetimes for file end check: {e}.")
                    action, next_file, offset = 'continue', None, 0.0

                if action == 'next':
                    logger.debug(f"Monitor: Reached end of {os.path.basename(current_file)}; advancing to {os.path.basename(next_file[0])}.")
                    result = self._advance_to_next_file(current_file, next_file, offset)
                    if result is None:
                        # A user command holds the transport; look again shortly.
                        time.sleep(0.1)
                        continue
                    break  # a fresh monitor was started on success; otherwise playback stopped
                if action == 'stop' and (vlc_finished or current_pos is not None):
                    logger.info("Monitor: end of available audio reached; stopping playback.")
                    self._finish_playback()
                    break
                if vlc_finished:
                    # Stopped/Ended without us asking and not at a file end: nothing to wait for.
                    logger.debug(f"Monitor: Playback ended/stopped (State: {current_state}). Stopping monitor.")
                    self._is_playing = False
                    break
            elif vlc_finished:
                logger.debug(f"Monitor: Playback ended/stopped (State: {current_state}). Stopping monitor.")
                self._is_playing = False
                break

            if not current_pos:
                time.sleep(0.1)
                continue

            if self.position_callback:
                try:
                    self.position_callback(current_pos)
                except Exception as e:
                     logger.error(f"Error in position_callback: {e}", exc_info=True)
                     self.position_callback = None

            time.sleep(0.1)

    def set_playback_rate(self, rate: float) -> bool:
        if not self.audio_available or not self.player:
            logger.warning("Cannot change playback rate: Audio playback is unavailable.")
            return False

        if rate <= 0:
            logger.warning(f"Invalid playback rate: {rate}. Must be positive.")
            return False
        # Remember the rate so it survives the next media load (VLC resets it).
        self._playback_rate = float(rate)
        if not self.player.get_media():
            logger.warning("No media loaded; playback rate will apply when playback starts.")
            return False
        try:
            self.player.set_rate(rate)
            return True
        except Exception as e:
            logger.error(f"Error setting playback rate: {e}")
            return False

    def get_playback_rate(self) -> float:
        """The rate the user asked for (kept across media reloads)."""
        if not self.audio_available or not self.player:
            return 1.0
        return self._playback_rate

    def set_amplification(self, db_level: int) -> bool:
        """
        Apply a real gain of ``db_level`` dB (0 = off, 20 = the Boost toggle).

        Uses the VLC equalizer preamp (true dB, capped at +20 dB) and keeps software
        volume at 100%; see _apply_gain. The setting is re-applied whenever new media
        is opened. Falls back to the old volume-based boost if the equalizer is
        unavailable.

        Returns:
            bool: True if the gain was applied, False otherwise.
        """
        if not self.audio_available or not self.player:
            logger.warning("Cannot set amplification: Audio playback is unavailable.")
            return False

        self.current_amplification = db_level
        logger.info(f"Setting amplification to +{db_level}dB")
        return bool(self._apply_gain())

    def get_time(self):
        if not self.audio_available or not self.player:
            return 0
        return self.player.get_time()

    def is_playing(self) -> bool:
        """
        Returns whether audio is currently playing.
        
        Returns:
            bool: True if audio is playing, False otherwise
        """
        return self._is_playing
        
    def is_in_terminal_state(self) -> bool:
        """
        Checks if the player is in a terminal state (Ended, Stopped, Error).
        
        Returns:
            bool: True if in terminal state, False otherwise
        """
        if not self.audio_available or not self.player:
            return True

        try:
            current_state = self.player.get_state()
            return current_state in [vlc.State.Ended, vlc.State.Stopped, vlc.State.Error]
        except Exception as e:
            logger.error(f"Error checking player state: {e}")
            return True  # Assume terminal state on error
            
    def seek_to_time(self, timestamp: datetime.datetime, position_callback: Optional[Callable] = None, position: Optional[str] = None) -> bool:
        """
        Seeks to the specified timestamp, optimizing for seeking within the current file.
        Unlike play(), this method:
        1. Doesn't have a lockout mechanism for successive calls
        2. Avoids full stop/restart when seeking within the current file

        Parameters:
        timestamp: Datetime object for the desired seek position
        position_callback: Optional callback function to report playback position

        Returns:
        bool: True if seek was successful, False otherwise
        """
        if not self.audio_available or not self.player or not self.vlc_instance:
            logger.warning("Seek requested but audio playback is unavailable.")
            return False

        # Remember if the player is currently playing before we do anything.
        was_playing = self.is_playing()

        # Determine which position to use: the passed argument or the instance's current position
        position_to_use = position if position is not None else self.current_position
        
        # Find the correct file and offset for the timestamp
        filepath, offset_seconds, file_start_time, duration_sec = self._find_file_for_timestamp(timestamp, position_to_use)
        if not filepath:
            logger.warning(f"No audio file found for timestamp: {timestamp}")
            return False
            
        # Check if we're seeking within the current file
        if filepath == self.current_file and self.player.get_media():
            logger.debug(f"Seeking within current file to {offset_seconds:.2f}s offset")
            
            # Update the position callback if provided
            if position_callback:
                self.position_callback = position_callback
                
            if self.player.set_time(int(offset_seconds * 1000)) == -1:
                logger.warning(f"VLC failed to set time to {int(offset_seconds * 1000)}ms.")
                return False

            # If the *handler's* desired state is 'playing' but the *player* is not, resume playback.
            if self._is_playing and not self.player.is_playing():
                logger.info("Resuming playback after seek within same file")
                if self.player.play() == -1:
                    logger.error("VLC failed to resume playback after seek within same file.")
                    return False

            return True
        else:
            # Different file or no current media - use regular play method
            logger.debug(f"Seeking requires file change. Was playing: {was_playing}")

            play_initiated = self.play(timestamp, position_callback)

            return play_initiated
