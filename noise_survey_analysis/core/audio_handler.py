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
    """
    
    def __init__(self, media_path: str):
        """
        Initialize the audio playback handler.
        
        Parameters:
        media_path (str): Path to the directory containing audio files
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
        
        logger.info(f"Found {len(self.file_info)} audio files in {media_path}")
        
    def _index_audio_files(self) -> List[Tuple[str, datetime.datetime]]:
        """
        Index all audio files in the folder and their start times.
        
        Returns:
            List of tuples with (file_path, start_datetime)
        """
        file_info = []
        
        if not os.path.exists(self.media_path):
            logger.warning(f"Media path does not exist: {self.media_path}")
            return file_info
            
        for filename in os.listdir(self.media_path):
            if filename.lower().endswith(('.wav', '.mp3', '.ogg')):
                filepath = os.path.join(self.media_path, filename)
                # Get modified time as start time
                mod_time = os.path.getmtime(filepath)
                start_datetime = datetime.datetime.fromtimestamp(mod_time)
                file_info.append((filepath, start_datetime))
        
        # Sort by start time
        file_info.sort(key=lambda x: x[1])
        return file_info
    
    def _find_file_for_timestamp(self, timestamp: datetime.datetime) -> Tuple[Optional[str], float, Optional[datetime.datetime]]:
        """
        Find the appropriate audio file and offset for the given timestamp.
        
        Parameters:
            timestamp: Datetime object representing the requested playback point
            
        Returns:
            Tuple of (file_path, offset_in_seconds, file_start_time)
        """
        if not self.file_info:
            return None, 0, None
            
        # Each file is assumed to be 12 hours long
        file_duration = 12 * 60 * 60  # in seconds
        
        for i, (filepath, start_time) in enumerate(self.file_info):
            # Calculate end time of this file
            end_time = start_time + datetime.timedelta(seconds=file_duration)
            
            # Check if timestamp falls within this file's time range
            if start_time <= timestamp < end_time:
                # Calculate offset within the file
                offset = (timestamp - start_time).total_seconds()
                return filepath, offset, start_time
                
            # Check if timestamp is between this file and the next one
            if i < len(self.file_info) - 1:
                next_start = self.file_info[i+1][1]
                if end_time <= timestamp < next_start:
                    # timestamp falls in a gap, use the end of the current file
                    return filepath, file_duration, start_time
        
        # If timestamp is before first file, use start of first file
        if self.file_info and timestamp < self.file_info[0][1]:
            return self.file_info[0][0], 0, self.file_info[0][1]
            
        # If timestamp is after last file, use the last file
        if self.file_info:
            last_file, last_start = self.file_info[-1]
            last_end = last_start + datetime.timedelta(seconds=file_duration)
            if timestamp >= last_end:
                return last_file, file_duration, last_start
            
        return None, 0, None
    
    def play(self, timestamp: datetime.datetime, position_callback: Optional[Callable] = None):
        """
        Play audio starting at the specified timestamp.
        
        Parameters:
            timestamp: Datetime object for the desired playback position
            position_callback: Optional callback function to report playback position
        
        Returns:
            bool: True if playback started successfully, False otherwise
        """
        # Stop any existing playback
        self.stop()
        
        # Find the correct file and offset
        filepath, offset_seconds, file_start_time = self._find_file_for_timestamp(timestamp)
        if not filepath:
            logger.warning(f"No audio file found for timestamp: {timestamp}")
            return False
            
        # Output the current file being played to terminal
        if self.current_file != filepath:
            logger.info(f"Playing file: {os.path.basename(filepath)}")
            print(f"Now playing: {os.path.basename(filepath)}")
            
        # Store current state
        self.current_file = filepath
        self.media_start_time = file_start_time
        self.position_callback = position_callback
        
        # Create a new media and set it to the player
        media = self.vlc_instance.media_new(filepath)
        self.player.set_media(media)
        
        # Start playback
        self.player.play()
        
        # Wait for the player to start
        time.sleep(0.1)
        
        # Set the time position (in milliseconds)
        self.player.set_time(int(offset_seconds * 1000))
        
        self.is_playing = True
        self.stop_monitor = False
        
        # Start the monitor thread to track position
        self.playback_monitor = threading.Thread(target=self._monitor_playback)
        self.playback_monitor.daemon = True
        self.playback_monitor.start()
        
        return True
    
    def pause(self):
        """
        Pause audio playback.
        
        Returns:
            bool: True if paused successfully, False otherwise
        """
        if self.is_playing and self.player.is_playing():
            self.player.pause()
            self.is_playing = False
            logger.info("Playback paused")
            return True
        return False
    
    def resume(self):
        """
        Resume paused audio playback.
        
        Returns:
            bool: True if resumed successfully, False otherwise
        """
        if not self.is_playing and self.player.get_media():
            self.player.play()
            self.is_playing = True
            logger.info("Playback resumed")
            return True
        return False
    
    def stop(self):
        """
        Stop audio playback.
        
        Returns:
            bool: True if stopped successfully, False otherwise
        """
        if self.playback_monitor and self.playback_monitor.is_alive():
            self.stop_monitor = True
            self.playback_monitor.join(1.0)  # Wait for thread to finish
        
        was_playing = self.is_playing
        self.player.stop()
        self.is_playing = False
        self.current_file = None
        self.media_start_time = None
        
        if was_playing:
            logger.info("Playback stopped")
            return True
        return False
    
    def get_current_position(self) -> Optional[datetime.datetime]:
        """
        Get the current playback position as a datetime.
        
        Returns:
            datetime.datetime: Current playback position as a datetime, or None if not playing
        """
        if not self.player.get_media() or not self.media_start_time:
            return None
            
        # Get the current time position in milliseconds
        time_ms = self.player.get_time()
        if time_ms < 0:  # VLC returns -1 if not available
            return None
            
        # Convert to seconds and add to the file start time
        seconds = time_ms / 1000
        current_pos = self.media_start_time + datetime.timedelta(seconds=seconds)
        
        return current_pos
    
    def _monitor_playback(self):
        """
        Monitor playback position and call the position callback if provided.
        Also track when playback moves to a new file.
        """
        last_file = self.current_file
        
        while not self.stop_monitor and self.player.get_media():
            # Check if playback is still active
            if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped, vlc.State.Error]:
                self.is_playing = False
                break
            
            # Get current position
            current_pos = self.get_current_position()
            
            if current_pos:
                # Check if we need to move to the next file
                if current_pos > self.media_start_time + datetime.timedelta(hours=12):
                    # Find the next file and continue playback
                    next_timestamp = current_pos + datetime.timedelta(seconds=1)
                    self.play(next_timestamp, self.position_callback)
                
                # Call position callback if provided
                if self.position_callback:
                    self.position_callback(current_pos)
                
                # Check if file has changed
                if self.current_file != last_file:
                    logger.info(f"Now playing: {os.path.basename(self.current_file)}")
                    print(f"Now playing: {os.path.basename(self.current_file)}")
                    last_file = self.current_file
            
            # Sleep to reduce CPU usage
            time.sleep(0.1) 