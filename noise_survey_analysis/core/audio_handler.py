"""
Audio playback handler for Noise Survey Analysis.

This module provides audio playback functionality that can be synchronized with visualizations.
Uses the VLC media player to play audio files synchronized with visualizations.
"""

import os
import time
import datetime
import threading
from typing import Callable, Optional, List, Tuple
import logging
import vlc

# Configure Logging
logger = logging.getLogger(__name__)

class AudioPlaybackHandler:
    """
    Handles audio playback from audio files based on timestamp selection.
    Integrates with Bokeh charts for visualization of audio position.
    Uses Python-VLC bindings for reliable playback control.
    Includes a simple time lockout for the play method to prevent rapid successive calls.
    """

    def __init__(self, media_path: str, play_lockout_interval: float = 0.2): # Interval in seconds (e.g., 200ms)
        """
        Initialize the audio playback handler.

        Parameters:
        media_path (str): Path to the directory containing audio files
        play_lockout_interval (float): Minimum time in seconds required between successful play executions.
        """
        self.media_path = media_path
        self.file_info = self._index_audio_files()
        self.vlc_instance = vlc.Instance('--no-xlib')
        self.player = self.vlc_instance.media_player_new()
        self.is_playing = False
        self.current_file = None
        self.media_start_time = None
        self.playback_monitor = None
        self.position_callback = None
        self.stop_monitor = False

        # --- Time Lockout attributes ---
        self.play_lockout_interval = play_lockout_interval
        self._last_play_execution_start_time: float = 0.0 # Use monotonic time
        self._play_lock = threading.Lock() # To protect check-and-update

        logger.info(f"Found {len(self.file_info)} audio files in {media_path}")
        logger.info(f"Play lockout interval set to {self.play_lockout_interval * 1000} ms")

    # --- _index_audio_files remains the same ---
    def _index_audio_files(self) -> List[Tuple[str, datetime.datetime]]:
        # ... (implementation unchanged)
        file_info = []

        if not os.path.exists(self.media_path):
            logger.warning(f"Media path does not exist: {self.media_path}")
            return file_info

        for filename in os.listdir(self.media_path):
            if filename.lower().endswith(('.wav', '.mp3', '.ogg')):
                filepath = os.path.join(self.media_path, filename)
                mod_time = os.path.getmtime(filepath)
                start_datetime = datetime.datetime.fromtimestamp(mod_time)
                file_info.append((filepath, start_datetime))

        file_info.sort(key=lambda x: x[1])
        return file_info


    # --- _find_file_for_timestamp remains the same ---
    def _find_file_for_timestamp(self, timestamp: datetime.datetime) -> Tuple[Optional[str], float, Optional[datetime.datetime]]:
        # ... (implementation unchanged)
        if not self.file_info:
            return None, 0, None
        file_duration = 12 * 60 * 60
        for i, (filepath, start_time) in enumerate(self.file_info):
            end_time = start_time + datetime.timedelta(seconds=file_duration)
            if start_time <= timestamp < end_time:
                offset = (timestamp - start_time).total_seconds()
                return filepath, offset, start_time
            if i < len(self.file_info) - 1:
                next_start = self.file_info[i+1][1]
                if end_time <= timestamp < next_start:
                    return filepath, file_duration, start_time
        if self.file_info and timestamp < self.file_info[0][1]:
            return self.file_info[0][0], 0, self.file_info[0][1]
        if self.file_info:
            last_file, last_start = self.file_info[-1]
            last_end = last_start + datetime.timedelta(seconds=file_duration)
            if timestamp >= last_end:
                return last_file, file_duration, last_start
        return None, 0, None


    def play(self, timestamp: datetime.datetime, position_callback: Optional[Callable] = None) -> bool:
        """
        Play audio starting at the specified timestamp, subject to a time lockout.
        If called too soon after a previous successful execution, it will be blocked.

        Parameters:
        timestamp: Datetime object for the desired playback position
        position_callback: Optional callback function to report playback position

        Returns:
        bool: True if playback was successfully initiated, False if blocked by lockout or an error occurred.
        """
        # Use a lock to ensure the check and update of the lockout time is atomic
        with self._play_lock:
            now = time.monotonic() # Use monotonic clock for interval checks

            # --- Lockout Check ---
            if now < self._last_play_execution_start_time + self.play_lockout_interval:
                logger.debug(f"Play call blocked by lockout ({(self._last_play_execution_start_time + self.play_lockout_interval - now):.3f}s remaining)")
                return False # Blocked

            # --- Update Lockout Time ---
            # Record the start time of *this* execution attempt *before* starting long operations
            self._last_play_execution_start_time = now
            logger.debug(f"Play call proceeding. Timestamp: {timestamp}") # Use regular logger

            # --- Start of Original Core Play Logic (modified slightly) ---
            # Stop existing playback cleanly
            self._perform_stop_actions() # Use helper

            # Find the correct file and offset
            filepath, offset_seconds, file_start_time = self._find_file_for_timestamp(timestamp)
            if not filepath:
                logger.warning(f"No audio file found for timestamp: {timestamp}")
                self.is_playing = False # Ensure state is correct
                return False # Indicate failure

            # Output the current file being played to terminal
            if self.current_file != filepath:
                 logger.info(f"Playing file: {os.path.basename(filepath)}")
                 print(f"Now playing: {os.path.basename(filepath)}")

            # Store current state
            self.current_file = filepath
            self.media_start_time = file_start_time
            self.position_callback = position_callback # Store latest callback

            # Create a new media and set it to the player
            try:
                media = self.vlc_instance.media_new(filepath)
                if not media:
                    logger.error(f"VLC failed to create media for: {filepath}")
                    self.is_playing = False
                    return False
                self.player.set_media(media)
                media.release()

                # Start playback
                play_result = self.player.play()
                if play_result == -1:
                    logger.error("VLC failed to play media.")
                    self.is_playing = False
                    return False

                # Wait briefly for state update
                time.sleep(0.05)

                # Set the time position (in milliseconds) after starting play
                set_time_result = self.player.set_time(int(offset_seconds * 1000))
                if set_time_result == -1:
                    logger.warning(f"VLC failed to set time to {int(offset_seconds * 1000)}ms.")
                    # Playback might continue from beginning, but consider it 'initiated'

                # Short pause for VLC processing
                time.sleep(0.05)
                final_state = self.player.get_state()
                if final_state not in [vlc.State.Playing, vlc.State.Buffering]:
                     logger.warning(f"VLC player not in Playing/Buffering state after play/seek (State: {final_state}).")
                     # Decide if this constitutes a failure
                     # return False # Optional: Treat this as failure

            except Exception as e:
                logger.error(f"Error during VLC media setup/play/seek: {e}", exc_info=True)
                self.is_playing = False
                return False # Indicate failure

            self.is_playing = True
            self.stop_monitor = False

            # Start the monitor thread (ensure previous one is stopped)
            if self.playback_monitor and self.playback_monitor.is_alive():
                 logger.warning("Previous monitor thread still alive before starting new one.")
                 self.stop_monitor = True
                 self.playback_monitor.join(0.1)

            self.stop_monitor = False # Reset flag for new thread
            self.playback_monitor = threading.Thread(target=self._monitor_playback)
            self.playback_monitor.daemon = True
            self.playback_monitor.start()

            return True # Indicate successful initiation
            # --- End of Original Core Play Logic ---

    def pause(self):
        # ... (implementation unchanged)
        if self.is_playing and self.player.is_playing():
            self.player.pause()
            self.is_playing = False
            logger.info("Playback paused")
            return True
        return False

    def resume(self):
        # ... (implementation unchanged)
        if not self.is_playing and self.player.get_media():
            if self.player.get_state() == vlc.State.Paused:
                 self.player.play()
                 self.is_playing = True
                 logger.info("Playback resumed")
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
        # No lockout specific logic needed here, just perform the stop
        return self._perform_stop_actions()

    def _perform_stop_actions(self) -> bool:
        """Helper to perform the actual player stop and thread join actions."""
        # Stop monitor thread first
        monitor_stopped = False
        if self.playback_monitor and self.playback_monitor.is_alive():
            self.stop_monitor = True
            self.playback_monitor.join(0.5)
            if not self.playback_monitor.is_alive():
                monitor_stopped = True
            else:
                logger.warning("Playback monitor thread did not stop cleanly.")
        else:
            monitor_stopped = True

        # Stop VLC player
        was_playing_or_paused = self.player.is_playing() or self.player.get_state() == vlc.State.Paused
        try:
             self.player.stop()
        except Exception as e:
            logger.error(f"Error stopping VLC player: {e}")

        # Update state
        self.is_playing = False

        if was_playing_or_paused:
            logger.info("Playback stopped")
            return True
        return False

    # --- get_current_position remains the same ---
    def get_current_position(self) -> Optional[datetime.datetime]:
        # ... (implementation unchanged)
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


    # --- _monitor_playback remains the same (uses self.play which is now locked out) ---
    def _monitor_playback(self):
        # ... (implementation unchanged)
        last_file = self.current_file
        while not self.stop_monitor and self.player.get_media():
            current_state = self.player.get_state()
            if current_state in [vlc.State.Ended, vlc.State.Stopped, vlc.State.Error]:
                logger.info(f"Monitor: Playback ended/stopped/errored (State: {current_state}). Stopping monitor.")
                self.is_playing = False
                break
            if current_state not in [vlc.State.Playing, vlc.State.Paused, vlc.State.Buffering]:
                 logger.debug(f"Monitor: Player in unexpected state: {current_state}")

            current_pos = self.get_current_position()
            if current_pos and self.media_start_time:
                try:
                    # Use >= for comparison robustness
                    file_end_time = self.media_start_time + datetime.timedelta(hours=12)
                    if current_pos >= file_end_time:
                         logger.info(f"Monitor: Reached end of assumed 12h file duration for {os.path.basename(self.current_file)}. Attempting to play next part.")
                         next_timestamp = current_pos + datetime.timedelta(milliseconds=100)
                         # Call the main play method (which includes the lockout)
                         if not self.play(next_timestamp, self.position_callback):
                              logger.warning("Monitor: Lockout prevented automatic transition to next file.")
                         # Exit this monitor thread regardless, play starts a new one if successful
                         break
                except TypeError as e:
                     logger.error(f"Monitor: Error comparing datetimes for file end check: {e}.")

                if self.position_callback:
                    try:
                        self.position_callback(current_pos)
                    except Exception as e:
                         logger.error(f"Error in position_callback: {e}", exc_info=True)
                         self.position_callback = None

                if self.current_file != last_file:
                    logger.info(f"Monitor: File changed to: {os.path.basename(self.current_file)}")
                    last_file = self.current_file
            time.sleep(0.1)

    # --- set_playback_rate remains the same ---
    def set_playback_rate(self, rate: float) -> bool:
        # ... (implementation unchanged)
        if not self.player.get_media():
            logger.warning("Cannot change playback rate: No media loaded")
            return False
        if rate <= 0:
            logger.warning(f"Invalid playback rate: {rate}. Must be positive.")
            return False
        try:
            result = self.player.set_rate(rate)
            if result == 0:
                 current_rate = self.player.get_rate()
                 logger.info(f"Playback rate set to {current_rate}x")
                 return True
            else:
                 logger.error(f"VLC failed to set playback rate (returned {result})")
                 return False
        except Exception as e:
            logger.error(f"Error setting playback rate: {e}")
            return False

    # --- get_playback_rate remains the same ---
    def get_playback_rate(self) -> float:
        # ... (implementation unchanged)
        if not self.player.get_media():
            return 1.0
        try:
            return self.player.get_rate()
        except:
            return 1.0