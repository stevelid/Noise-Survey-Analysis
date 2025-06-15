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
        self.default_media_path = media_path
        self.current_media_path = media_path
        # Dictionary to store file info for each media path
        self.media_path_file_info = {}
        self.file_info = self._index_audio_files(media_path)
        self.media_path_file_info[media_path] = self.file_info
        
        # Dictionary to store position-specific audio paths
        self.position_media_paths = {}
        self.current_position = None

        # Initialize VLC instance
        try:
            self.vlc_instance = vlc.Instance('--no-xlib', '--quiet')
        except Exception as e:
             logger.error(f"Failed to initialize VLC instance: {e}", exc_info=True)
             raise RuntimeError(f"Failed to initialize VLC instance: {e}. "
                                "Ensure VLC is installed correctly and accessible.") from e

        # Check if instance creation was successful
        if self.vlc_instance is None:
            logger.error("VLC instance creation returned None. Cannot initialize player.")
            raise RuntimeError("VLC instance creation returned None. "
                               "Ensure VLC is installed, accessible, and architecture matches Python.")

        # Now create the player
        try:
            self.player = self.vlc_instance.media_player_new()
            if self.player is None:
                 logger.error("Failed to create VLC media player from instance.")
                 raise RuntimeError("Failed to create VLC media player. Check VLC installation.")
        except Exception as e:
             logger.error(f"Failed to create VLC media player: {e}", exc_info=True)
             raise RuntimeError(f"Failed to create VLC media player: {e}") from e

        self._is_playing = False
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

    def add_position_media_path(self, position: str, media_path: str) -> bool:
        """
        Add a position-specific media path to the handler.
        
        Parameters:
        position (str): Position identifier (e.g., 'SW', 'SE')
        media_path (str): Path to the directory containing audio files for this position
        
        Returns:
        bool: True if the media path was added successfully, False otherwise
        """
        if not position or not media_path:
            logger.warning(f"Invalid position or media path: position='{position}', path='{media_path}'")
            return False
            
        if not os.path.exists(media_path):
            logger.warning(f"Media path does not exist for position '{position}': {media_path}")
            return False
            
        # Index audio files in this directory
        file_info = self._index_audio_files(media_path)
        if not file_info:
            logger.warning(f"No audio files found in media path for position '{position}': {media_path}")
            return False
            
        # Store the path and file info
        self.position_media_paths[position] = media_path
        self.media_path_file_info[media_path] = file_info
        logger.info(f"Added media path for position '{position}': {media_path} with {len(file_info)} audio files")
        return True
    
    def set_current_position(self, position: str) -> bool:
        """
        Set the current position for audio playback.
        
        Parameters:
        position (str): Position identifier (e.g., 'SW', 'SE')
        
        Returns:
        bool: True if the position was set successfully, False otherwise
        """
        # If this position isn't different from current, no need to change
        if position == self.current_position:
            return True
            
        # If we're currently playing, stop
        if self._is_playing:
            self._perform_stop_actions()
            
        # Check if we have a media path for this position
        if position in self.position_media_paths:
            media_path = self.position_media_paths[position]
            self.current_media_path = media_path
            self.file_info = self.media_path_file_info[media_path]
            self.current_position = position
            logger.info(f"Set current position to '{position}' with media path: {media_path}")
            return True
        else:
            # Fall back to default media path
            self.current_media_path = self.default_media_path
            self.file_info = self.media_path_file_info[self.default_media_path]
            self.current_position = None
            logger.warning(f"No media path found for position '{position}', using default path: {self.default_media_path}")
            return False

    # --- _index_audio_files remains the same but now takes path as a parameter ---
    def _index_audio_files(self, path: str) -> List[Tuple[str, datetime.datetime]]:
        file_info = []

        if not os.path.exists(path):
            logger.warning(f"Media path does not exist: {path}")
            return file_info

        for filename in os.listdir(path):
            # Filter files by _Audio_ pattern for consistency
            if "_Audio_" in filename and filename.lower().endswith('.wav'):
                filepath = os.path.join(path, filename)
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

            # Find the correct file and offset using the current position's file_info
            filepath, offset_seconds, file_start_time = self._find_file_for_timestamp(timestamp)
            if not filepath:
                logger.warning(f"No audio file found for timestamp: {timestamp} in position: {self.current_position or 'default'}")
                self._is_playing = False # Ensure state is correct
                return False # Indicate failure

            # Output the current file being played to terminal
            if self.current_file != filepath:
                position_info = f" (position: {self.current_position})" if self.current_position else ""
                logger.info(f"Playing file: {os.path.basename(filepath)}{position_info}")
                print(f"Now playing: {os.path.basename(filepath)}{position_info}")

            # Store current state
            self.current_file = filepath
            self.media_start_time = file_start_time
            self.position_callback = position_callback # Store latest callback

            # Create a new media and set it to the player
            try:
                media = self.vlc_instance.media_new(filepath)
                if not media:
                    logger.error(f"VLC failed to create media for: {filepath}")
                    self._is_playing = False
                    return False
                self.player.set_media(media)
                media.release()

                # Start playback
                play_result = self.player.play()
                if play_result == -1:
                    logger.error("VLC failed to play media.")
                    self._is_playing = False
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
                self._is_playing = False
                return False # Indicate failure

            self._is_playing = True
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
        if self._is_playing and self.player.is_playing():
            self.player.pause()
            self._is_playing = False
            logger.info("Playback paused")
            return True
        return False

    def resume(self):
        # ... (implementation unchanged)
        if not self._is_playing and self.player.get_media():
            if self.player.get_state() == vlc.State.Paused:
                 self.player.play()
                 self._is_playing = True
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
        self._is_playing = False

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

    def release(self):
        """
        Properly releases all VLC resources.
        Should be called when the audio handler is no longer needed.
        """
        logger.info("Releasing VLC resources...")
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
            
            logger.info("VLC resources released successfully")
        except Exception as e:
            logger.error(f"Error releasing VLC resources: {e}", exc_info=True)
            # Don't re-raise - we want to continue cleanup even if release fails

    # --- _monitor_playback remains the same (uses self.play which is now locked out) ---
    def _monitor_playback(self):
        # ... (implementation unchanged)
        last_file = self.current_file
        while not self.stop_monitor and self.player.get_media():
            current_state = self.player.get_state()
            if current_state in [vlc.State.Ended, vlc.State.Stopped, vlc.State.Error]:
                logger.info(f"Monitor: Playback ended/stopped/errored (State: {current_state}). Stopping monitor.")
                self._is_playing = False
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

    def get_time(self):
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
        if not self.player:
            return True
            
        try:
            current_state = self.player.get_state()
            return current_state in [vlc.State.Ended, vlc.State.Stopped, vlc.State.Error]
        except Exception as e:
            logger.error(f"Error checking player state: {e}")
            return True  # Assume terminal state on error
            
    def seek_to_time(self, timestamp: datetime.datetime, position_callback: Optional[Callable] = None) -> bool:
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
        # Find the correct file and offset for the timestamp
        filepath, offset_seconds, file_start_time = self._find_file_for_timestamp(timestamp)
        if not filepath:
            logger.warning(f"No audio file found for timestamp: {timestamp}")
            return False
            
        # Check if we're seeking within the current file
        if filepath == self.current_file and self.player.get_media():
            logger.debug(f"Seeking within current file to {offset_seconds:.2f}s offset")
            
            # Update the position callback if provided
            if position_callback:
                self.position_callback = position_callback
                
            # Set the time position in milliseconds
            set_time_result = self.player.set_time(int(offset_seconds * 1000))
            if set_time_result == -1:
                logger.warning(f"VLC failed to set time to {int(offset_seconds * 1000)}ms.")
                return False
                
            # If the player was paused, keep it paused
            was_playing = self.player.is_playing()
            
            # Short pause for VLC processing
            time.sleep(0.05)
            
            if not was_playing and self._is_playing:
                # If we were supposed to be playing but weren't, ensure we're playing
                play_result = self.player.play()
                if play_result == -1:
                    logger.error("VLC failed to resume playback after seek.")
                    return False
                    
            return True
        else:
            # Different file or no current media - use regular play method
            logger.debug(f"Seeking requires file change, using full play method")
            return self.play(timestamp, position_callback)