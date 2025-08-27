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
from typing import Callable, Optional, List, Tuple
import logging
import vlc
import pandas as pd # Make sure pandas is imported

# Configure Logging
logger = logging.getLogger(__name__)

class AudioPlaybackHandler:
    """
    Handles audio playback from audio files based on timestamp selection.
    Integrates with Bokeh charts for visualization of audio position.
    Uses Python-VLC bindings for reliable playback control.
    Includes a simple time lockout for the play method to prevent rapid successive calls.
    """

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

        # Initialize VLC
        try:
            self.vlc_instance = vlc.Instance('--no-xlib', '--quiet')
            self.player = self.vlc_instance.media_player_new()
            if self.vlc_instance is None or self.player is None:
                raise RuntimeError("Failed to initialize VLC instance or player.")
        except Exception as e:
            logger.error(f"VLC initialization failed: {e}. Audio will be disabled.", exc_info=True)
            self.vlc_instance = self.player = None
            return

        self._is_playing = False
        self.current_file = None
        self.media_start_time = None
        self.current_file_duration = None
        self.playback_monitor = None
        self.position_callback = None
        self.stop_monitor = False

        # --- NEW, SIMPLIFIED INITIALIZATION LOGIC ---
        logger.info("AudioPlaybackHandler: Indexing pre-processed audio data...")
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
                files_to_process.append((row['full_path'], row['Datetime'], row['duration_sec']))
            
            self.file_info_by_position[position_name] = files_to_process
            logger.info(f"Indexed {len(files_to_process)} pre-anchored audio files for position '{position_name}'.")

    def set_current_position(self, position: str) -> bool:
         """
         Sets the active position to get audio from.
         """
         if position == self.current_position:
             return True
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
                # If the timestamp is before the very first file, snap to the start of the first file
                if filepath == sorted_files[0][0]:
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
        logger.debug(f"Play call proceeding. Timestamp: {timestamp}")

        # Stop existing playback cleanly before starting new playback.
        # This is the key to handling rapid switching between positions.
        self._perform_stop_actions()

        # Find the correct file and offset using the current position's file_info
        filepath, offset_seconds, file_start_time, file_duration = self._find_file_for_timestamp(timestamp, self.current_position)
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
        self.current_file_duration = file_duration

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
                self.stop_monitor = True # Tell the old one to stop
                self.playback_monitor.join(0.5) # wait a bit for it. 

        self.stop_monitor = False # Reset flag for new thread
        self.playback_monitor = threading.Thread(target=self._monitor_playback)
        self.playback_monitor.daemon = True
        self.playback_monitor.start()

        return True # Indicate successful initiation
        # --- End of Original Core Play Logic ---

    def pause(self):
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

    def _monitor_playback(self):
        last_file = None
        while not self.stop_monitor and self.player.get_media():
            current_state = self.player.get_state()
            if current_state in [vlc.State.Ended, vlc.State.Stopped, vlc.State.Error]:
                logger.info(f"Monitor: Playback ended/stopped/errored (State: {current_state}). Stopping monitor.")
                self._is_playing = False
                break
            if current_state not in [vlc.State.Playing, vlc.State.Paused, vlc.State.Buffering]:
                 logger.debug(f"Monitor: Player in unexpected state: {current_state}")

            if last_file is None or self.current_file != last_file:
                logger.info(f"Monitor: File changed to: {os.path.basename(self.current_file)}")
                last_file = self.current_file

            current_pos = self.get_current_position()
            
            if not current_pos:
                time.sleep(0.1)
                continue
            try:    
                file_end_time = self.media_start_time + datetime.timedelta(seconds=self.current_file_duration)
                #check if we are within 200ms of the end
                if current_pos >= (file_end_time - datetime.timedelta(milliseconds=200)):
                     logger.info(f"Monitor: Reached end of file duration for {os.path.basename(self.current_file)}. Attempting to play next part.")
                     next_timestamp = current_pos + datetime.timedelta(milliseconds=100)
                     # Call the main play method (which includes the lockout)
                     if not self.play(next_timestamp, self.position_callback):
                          logger.warning("Monitor: Lockout prevented automatic transition to next file.")
                     # Exit this monitor thread regardless, play starts a new one if successful
                     break
            except (TypeError, AttributeError) as e:
                 logger.error(f"Monitor: Error comparing datetimes for file end check: {e}.")

            if self.position_callback:
                try:
                    self.position_callback(current_pos)
                except Exception as e:
                     logger.error(f"Error in position_callback: {e}", exc_info=True)
                     self.position_callback = None

            time.sleep(0.1)

    def set_playback_rate(self, rate: float) -> bool:
        if not self.player.get_media():
            logger.warning("Cannot change playback rate: No media loaded")
            return False
        if rate <= 0:
            logger.warning(f"Invalid playback rate: {rate}. Must be positive.")
            return False
        try:
            self.player.set_rate(rate)
            return True
        except Exception as e:
            logger.error(f"Error setting playback rate: {e}")
            return False

    def get_playback_rate(self) -> float:
        if not self.player.get_media():
            return 1.0
        try:
            return self.player.get_rate()
        except:
            return 1.0

    def set_amplification(self, db_level: int) -> bool:
        """
        Sets the audio player's volume based on a dB gain level.
        A simple mapping is used: 0dB -> 100%, +20dB -> 200%, +40dB -> 400%.
        Note: This requires the VLC software volume to be enabled.

        Args:
            db_level (int): The desired amplification in dB (0, 20, or 40).

        Returns:
            bool: True if the volume was set successfully, False otherwise.
        """
        if not self.player:
            logger.warning("Cannot set amplification: player not available.")
            return False

        # Simple mapping from dB gain to a percentage for VLC's set_volume
        volume_map = {0: 100, 20: 200, 40: 400}
        volume_percent = volume_map.get(db_level, 100) # Default to 100% (0dB)

        logger.info(f"Setting amplification to +{db_level}dB (VLC Volume: {volume_percent}%)")
        if self.player.audio_set_volume(volume_percent) == 0:
            self.current_amplification = db_level
            return True
        return False

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
                
            # Set the time position in milliseconds
            set_time_result = self.player.set_time(int(offset_seconds * 1000))
            if set_time_result == -1:
                logger.warning(f"VLC failed to set time to {int(offset_seconds * 1000)}ms.")
                return False
                
            # If the *handler's* desired state is 'playing' but the *player* is not, resume playback.
            if self._is_playing and not self.player.is_playing():
                logger.info("Resuming playback after seek within same file")
                play_result = self.player.play()
                if play_result == -1:
                    logger.error("VLC failed to resume playback after seek within same file.")
                    return False
                    
            return True
        else:
            # Different file or no current media - use regular play method
            logger.debug(f"Seeking requires file change. Was playing: {was_playing}")

            play_initiated = self.play(timestamp, position_callback)

            return play_initiated