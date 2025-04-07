import os
import time
import datetime
import threading
from typing import Callable, Optional, List, Tuple
import vlc


class AudioPlaybackHandler:
    """
    Handles audio playback from WAV files based on timestamp selection.
    Integrates with Bokeh charts for visualization of audio position.
    Uses Python-VLC bindings for reliable playback control.
    """
    
    def __init__(self, audio_folder: str):
        """
        Initialize the audio playback handler.
        
        Args:
            audio_folder: Path to folder containing WAV files
        """
        self.audio_folder = audio_folder
        self.file_info = self._index_audio_files()
        self.vlc_instance = vlc.Instance('--no-xlib')
        self.player = self.vlc_instance.media_player_new()
        self.is_playing = False
        self.current_file = None
        self.current_file_start_time = None
        self.playback_monitor = None
        self.position_callback = None
        self.stop_monitor = False
        
    def _index_audio_files(self) -> List[Tuple[str, datetime.datetime]]:
        """
        Index all WAV files in the folder and their start times.
        
        Returns:
            List of tuples with (file_path, start_datetime)
        """
        file_info = []
        
        for filename in os.listdir(self.audio_folder):
            if filename.lower().endswith('.wav'):
                filepath = os.path.join(self.audio_folder, filename)
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
        
        Args:
            timestamp: Datetime object representing the requested playback point
            
        Returns:
            Tuple of (file_path, offset_in_seconds, file_start_time)
        """
        if not self.file_info:
            return None, 0, None
            
        # Each file is 12 hours long
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
        if timestamp < self.file_info[0][1]:
            return self.file_info[0][0], 0, self.file_info[0][1]
            
        # If timestamp is after last file, use the last file
        last_file, last_start = self.file_info[-1]
        last_end = last_start + datetime.timedelta(seconds=file_duration)
        if timestamp >= last_end:
            return last_file, file_duration, last_start
            
        return None, 0, None
    
    def play(self, timestamp: datetime.datetime, position_callback: Optional[Callable] = None):
        """
        Play audio starting at the specified timestamp.
        
        Args:
            timestamp: Datetime object for the desired playback position
            position_callback: Optional callback function to report playback position
        """
        # Stop any existing playback
        self.stop()
        
        # Find the correct file and offset
        filepath, offset_seconds, file_start_time = self._find_file_for_timestamp(timestamp)
        if not filepath:
            print(f"No audio file found for timestamp: {timestamp}")
            return
            
        # Store current state
        self.current_file = filepath
        self.current_file_start_time = file_start_time
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
        
    def pause(self):
        """
        Pause audio playback.
        """
        if self.is_playing:
            self.player.pause()
            self.is_playing = False
    
    def resume(self):
        """
        Resume paused audio playback.
        """
        if not self.is_playing and self.player.get_media():
            self.player.play()
            self.is_playing = True
    
    def stop(self):
        """
        Stop audio playback.
        """
        if self.playback_monitor and self.playback_monitor.is_alive():
            self.stop_monitor = True
            self.playback_monitor.join(1.0)  # Wait for thread to finish
        
        self.player.stop()
        self.is_playing = False
        self.current_file = None
        self.current_file_start_time = None
    
    def get_current_position(self) -> Optional[datetime.datetime]:
        """
        Get the current playback position as a datetime.
        
        Returns:
            Datetime object representing the current playback position or None if not playing
        """
        if not self.player.get_media() or not self.current_file_start_time:
            return None
            
        # Get the current time position in milliseconds
        time_ms = self.player.get_time()
        if time_ms < 0:  # VLC returns -1 if not available
            return None
            
        # Convert to seconds and add to the file start time
        seconds = time_ms / 1000
        current_pos = self.current_file_start_time + datetime.timedelta(seconds=seconds)
        
        return current_pos
    
    def _monitor_playback(self):
        """
        Monitor playback position and call the position callback if provided.
        """
        while not self.stop_monitor and self.player.get_media():
            # Check if playback is still active
            if self.player.get_state() in [vlc.State.Ended, vlc.State.Stopped, vlc.State.Error]:
                self.is_playing = False
                break
                
            if self.position_callback and self.player.is_playing():
                current_pos = self.get_current_position()
                if current_pos:
                    self.position_callback(current_pos)
            
            # Sleep to reduce CPU usage
            time.sleep(0.1)

    def is_playing(self):
        return self.is_playing

    def get_time(self):
        return self.player.get_time()


# Example of how to use this with Bokeh:
def integrate_with_bokeh(audio_folder):
    """
    Example of how to integrate this handler with Bokeh callbacks.
    
    Args:
        audio_folder: Path to folder containing WAV files
    """
    # Create the playback handler
    handler = AudioPlaybackHandler(audio_folder)
    
    # Example callback function for Bokeh tap event
    def on_bokeh_tap(timestamp):
        """Called when user clicks on the Bokeh chart"""
        # Convert timestamp to datetime (example)
        dt_timestamp = datetime.datetime.fromtimestamp(timestamp)
        
        # Example position callback function to update Bokeh span
        def update_position(current_pos):
            # This would be replaced with actual Bokeh span update code
            pass
        
        # Play audio at the selected position
        handler.play(dt_timestamp, update_position)
    
    # Example controls
    def pause_audio():
        handler.pause()
    
    def resume_audio():
        handler.resume()
    
    def stop_audio():
        handler.stop()
    
    # Return the handler and control functions
    return handler, on_bokeh_tap, pause_audio, resume_audio, stop_audio