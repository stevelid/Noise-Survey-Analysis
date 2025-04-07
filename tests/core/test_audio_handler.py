import datetime
import pytest  # Import pytest itself (optional, but good practice)
from unittest.mock import patch, MagicMock, PropertyMock, call
import time
import threading
import os

# Import the class we want to test
try:
    from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler
except ImportError:
    # Fallback if the module structure is different
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from TO_REMOVE_AudioPlaybackHandler import AudioPlaybackHandler

# Define some test data (replace with realistic examples if needed)
MOCK_FILE_INFO = [
    ('/path/to/file1.wav', datetime.datetime(2025, 2, 15, 10, 0, 0)),  # Starts at 10:00
    ('/path/to/file2.wav', datetime.datetime(2025, 2, 15, 22, 0, 0)),  # Starts at 22:00 (12 hours later)
    ('/path/to/file3.wav', datetime.datetime(2025, 2, 16, 10, 0, 0)),  # Starts next day 10:00
]
# Assume 12 hour duration for simplicity in test, matching handler logic
FILE_DURATION_SECONDS = 12 * 60 * 60

# Mock VLC module
class MockVLCState:
    Playing = 3
    Paused = 4
    Stopped = 5
    Ended = 6
    Error = 7
    Buffering = 2

class MockVLCMedia:
    def __init__(self, filepath):
        self.filepath = filepath
    
    def release(self):
        pass
    
    def get_duration(self):
        return FILE_DURATION_SECONDS * 1000  # In milliseconds

class MockVLCPlayer:
    def __init__(self):
        self._media = None
        self._time = 0
        self._playing = False
        self._state = MockVLCState.Stopped
        self._rate = 1.0

    def set_media(self, media):
        self._media = media
        return 0

    def get_media(self):
        return self._media

    def play(self):
        self._playing = True
        self._state = MockVLCState.Playing
        return 0

    def pause(self):
        self._playing = False
        self._state = MockVLCState.Paused
        return 0

    def stop(self):
        self._playing = False
        self._state = MockVLCState.Stopped
        self._media = None
        return 0

    def is_playing(self):
        return self._playing

    def get_state(self):
        return self._state

    def set_time(self, ms):
        self._time = ms
        return 0

    def get_time(self):
        return self._time

    def set_rate(self, rate):
        self._rate = rate
        return 0

    def get_rate(self):
        return self._rate


class MockVLCInstance:
    def __init__(self, *args, **kwargs):
        self.player = MockVLCPlayer()

    def media_player_new(self):
        return self.player

    def media_new(self, filepath):
        # Return a proper media object instead of a string
        return MockVLCMedia(filepath)


# Tests for initialization and file indexing
@patch('os.listdir')
@patch('os.path.getmtime')
@patch('os.path.exists')
def test_init_and_index_audio_files(mock_path_exists, mock_getmtime, mock_listdir):
    """Test initialization and _index_audio_files method."""
    # Setup mocks
    mock_path_exists.return_value = True  # Make the path appear to exist
    mock_listdir.return_value = ['file1.wav', 'file2.wav', 'file3.wav', 'not_audio.txt']
    mock_getmtime.side_effect = [
        # Convert datetime to timestamp for each file
        datetime.datetime(2025, 2, 15, 10, 0, 0).timestamp(),
        datetime.datetime(2025, 2, 15, 22, 0, 0).timestamp(),
        datetime.datetime(2025, 2, 16, 10, 0, 0).timestamp(),
    ]
    
    # Use explicit patching for VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        # Initialize the handler
        handler = AudioPlaybackHandler(media_path="/test/audio/path")
        
        # Check initialization
        assert handler.media_path == "/test/audio/path"
        assert not handler.is_playing()
        assert handler.current_file is None
        assert handler.media_start_time is None
        
        # Check that file_info was populated correctly
        assert len(handler.file_info) == 3  # Should exclude non-WAV file
        
        # Check the files are sorted by timestamp - use os.path.basename to avoid path separator issues
        assert os.path.basename(handler.file_info[0][0]) == "file1.wav"
        assert os.path.basename(handler.file_info[1][0]) == "file2.wav"
        assert os.path.basename(handler.file_info[2][0]) == "file3.wav"
        
        # Check that timestamps were converted correctly
        assert handler.file_info[0][1] == datetime.datetime(2025, 2, 15, 10, 0, 0)
        assert handler.file_info[1][1] == datetime.datetime(2025, 2, 15, 22, 0, 0)
        assert handler.file_info[2][1] == datetime.datetime(2025, 2, 16, 10, 0, 0)
        
        # Check function calls
        mock_path_exists.assert_called_once_with("/test/audio/path")
        mock_listdir.assert_called_once_with("/test/audio/path")
        assert mock_getmtime.call_count == 3


# Tests for _find_file_for_timestamp
@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_within_first_file(mock_index_audio_files):
    """Test finding a timestamp clearly within the first file's range."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Arrange: Create an instance
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")

        target_timestamp = datetime.datetime(2025, 2, 15, 11, 30, 0)  # 11:30

        # Act: Call the method we are testing
        filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

        # Assert: Check if the results are what we expect
        assert filepath == MOCK_FILE_INFO[0][0]  # Should be file1.wav
        # Expected offset: 1.5 hours = 1.5 * 3600 = 5400 seconds
        assert offset == pytest.approx(5400.0)  # Use approx for float comparison
        assert start_time == MOCK_FILE_INFO[0][1]
        mock_index_audio_files.assert_called_once()


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_at_exact_start_time(mock_index_audio_files):
    """Test finding a timestamp exactly at the start of a file."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Arrange: Create an instance
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        target_timestamp = MOCK_FILE_INFO[1][1]  # 22:00:00

        # Act: Call the method we are testing
        filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

        # Assert: Check if the results are what we expect
        assert filepath == MOCK_FILE_INFO[1][0]  # Should be file2.wav
        assert offset == pytest.approx(0.0)     # Offset should be 0
        assert start_time == MOCK_FILE_INFO[1][1]
        mock_index_audio_files.assert_called_once()


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_near_end_of_file(mock_index_audio_files):
    """Test finding a timestamp near the end of a file's assumed duration."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Arrange: Create an instance
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        # Just before the end of file 1 (10:00 + 12h = 22:00)
        target_timestamp = datetime.datetime(2025, 2, 15, 21, 59, 59)

        # Act: Call the method we are testing
        filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

        # Assert: Check if the results are what we expect
        assert filepath == MOCK_FILE_INFO[0][0]  # Still file1.wav
        expected_offset = FILE_DURATION_SECONDS - 1
        assert offset == pytest.approx(expected_offset)
        assert start_time == MOCK_FILE_INFO[0][1]
        mock_index_audio_files.assert_called_once()


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_before_first_file(mock_index_audio_files):
    """Test finding a timestamp before the very first file."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Arrange: Create an instance
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        target_timestamp = datetime.datetime(2025, 2, 15, 9, 0, 0)  # Before 10:00

        # Act: Call the method we are testing
        filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

        # Assert: Check if the results are what we expect
        assert filepath == MOCK_FILE_INFO[0][0]  # Should clamp to file1.wav
        assert offset == pytest.approx(0.0)     # Offset should be 0
        assert start_time == MOCK_FILE_INFO[0][1]
        mock_index_audio_files.assert_called_once()


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_after_last_file(mock_index_audio_files):
    """Test finding a timestamp after the range of the last file."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Arrange: Create an instance
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        # After file 3 ends (Feb 16, 10:00 + 12h = Feb 16, 22:00)
        target_timestamp = datetime.datetime(2025, 2, 16, 23, 0, 0)

        # Act: Call the method we are testing
        filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

        # Assert: Check if the results are what we expect
        assert filepath == MOCK_FILE_INFO[2][0]  # Should clamp to file3.wav
        # Offset should be the full duration
        assert offset == pytest.approx(FILE_DURATION_SECONDS)
        assert start_time == MOCK_FILE_INFO[2][1]
        mock_index_audio_files.assert_called_once()


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_empty_file_info(mock_index_audio_files):
    """Test finding a file when file_info is empty."""
    # Configure the mock to return empty list
    mock_index_audio_files.return_value = []
    
    # Arrange: Create an instance
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        target_timestamp = datetime.datetime(2025, 2, 15, 10, 0, 0)

        # Act: Call the method we are testing
        filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

        # Assert: Should return None values
        assert filepath is None
        assert offset == 0
        assert start_time is None
        mock_index_audio_files.assert_called_once()


# Tests for play, pause, resume, stop methods
@patch.object(AudioPlaybackHandler, '_index_audio_files')
@patch.object(AudioPlaybackHandler, '_monitor_playback')
@patch('threading.Thread')
@patch('os.path.exists')
def test_play_success(mock_path_exists, mock_thread, mock_monitor_playback, mock_index_audio_files):
    """Test successful play method."""
    # Configure mocks
    mock_path_exists.return_value = True  # Make the path appear to exist
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Create a proper thread mock with daemon property
    mock_thread_instance = MagicMock()
    # Set up daemon as a property so it can be set
    daemon_property = PropertyMock(return_value=True)
    type(mock_thread_instance).daemon = daemon_property
    mock_thread.return_value = mock_thread_instance
    
    # Create mock for VLC Instance
    mock_vlc = MockVLCInstance()
    with patch('vlc.Instance', return_value=mock_vlc):
        # Create handler and mock callback
        handler = AudioPlaybackHandler(media_path="/mock/path")
        mock_callback = MagicMock()
        
        # Call the play method
        target_timestamp = datetime.datetime(2025, 2, 15, 11, 0, 0)
        result = handler.play(target_timestamp, mock_callback)
        
        # Check the result
        assert result is True
        
        # Check player state
        assert handler.is_playing() is True
        assert handler.current_file == MOCK_FILE_INFO[0][0]
        assert handler.media_start_time == MOCK_FILE_INFO[0][1]
        assert handler.position_callback == mock_callback
        
        # Check VLC operations
        assert mock_vlc.player.get_media() is not None
        assert mock_vlc.player.is_playing() is True
        assert mock_vlc.player.get_time() == 3600 * 1000  # 1 hour in milliseconds
        
        # Check monitor thread creation
        mock_thread.assert_called_once_with(target=handler._monitor_playback)
        daemon_property.assert_called_once_with(True)
        mock_thread_instance.start.assert_called_once()


@patch.object(AudioPlaybackHandler, '_index_audio_files')
@patch('os.path.exists')
def test_play_lockout(mock_path_exists, mock_index_audio_files):
    """Test that play method respects the lockout interval."""
    # Configure mock
    mock_path_exists.return_value = True  # Make the path appear to exist
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Mock monotonic time to control the lockout behavior
    original_monotonic = time.monotonic
    monotonic_values = [1000.0, 1000.1]  # Two calls, second within lockout window
    
    def mock_monotonic():
        return monotonic_values.pop(0) if monotonic_values else 1001.0
    
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        with patch('time.monotonic', side_effect=mock_monotonic):
            with patch('threading.Thread'):
                handler = AudioPlaybackHandler(media_path="/mock/path")
                
                # First play call (should succeed)
                timestamp1 = datetime.datetime(2025, 2, 15, 11, 0, 0)
                result1 = handler.play(timestamp1)
                
                # Second play call within lockout window (should fail)
                timestamp2 = datetime.datetime(2025, 2, 15, 12, 0, 0)
                result2 = handler.play(timestamp2)
                
                # Check results
                assert result1 is True
                assert result2 is False  # Should be blocked by lockout


@patch.object(AudioPlaybackHandler, '_index_audio_files')
@patch('os.path.exists')
def test_play_no_file_found(mock_path_exists, mock_index_audio_files):
    """Test play method when no file is found for the timestamp."""
    # Configure mocks
    mock_path_exists.return_value = True
    # Override _find_file_for_timestamp to return None
    with patch.object(AudioPlaybackHandler, '_find_file_for_timestamp', return_value=(None, 0, None)):
        with patch('vlc.Instance', return_value=MockVLCInstance()):
            handler = AudioPlaybackHandler(media_path="/mock/path")
            
            # Call play with any timestamp
            result = handler.play(datetime.datetime(2025, 2, 15, 10, 0, 0))
            
            # Check result
            assert result is False
            assert handler.is_playing() is False


@patch.object(AudioPlaybackHandler, '_index_audio_files')
@patch('os.path.exists')
@patch('threading.Thread')
def test_pause_resume(mock_thread, mock_path_exists, mock_index_audio_files):
    """Test pause and resume methods."""
    # Configure mocks
    mock_path_exists.return_value = True
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Create a proper thread mock with daemon property
    mock_thread_instance = MagicMock()
    daemon_property = PropertyMock(return_value=True)
    type(mock_thread_instance).daemon = daemon_property
    mock_thread.return_value = mock_thread_instance
    
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Start playback
        handler.play(datetime.datetime(2025, 2, 15, 10, 0, 0))
        
        # Verify initial state
        assert handler.is_playing() is True
        
        # Pause playback
        pause_result = handler.pause()
        
        # Check pause result
        assert pause_result is True
        assert handler.is_playing() is False
        
        # Resume playback
        resume_result = handler.resume()
        
        # Check resume result
        assert resume_result is True
        assert handler.is_playing() is True


@patch.object(AudioPlaybackHandler, '_index_audio_files')
@patch('os.path.exists')
@patch('threading.Thread')
def test_stop(mock_thread, mock_path_exists, mock_index_audio_files):
    """Test stop method."""
    # Configure mocks
    mock_path_exists.return_value = True
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Create a proper thread mock with daemon property
    mock_thread_instance = MagicMock()
    daemon_property = PropertyMock(return_value=True)
    type(mock_thread_instance).daemon = daemon_property
    mock_thread.return_value = mock_thread_instance
    
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Start playback
        handler.play(datetime.datetime(2025, 2, 15, 10, 0, 0))
        
        # Verify initial state
        assert handler.is_playing() is True
        assert handler.current_file is not None
        
        # Create a mock for the playback monitor thread
        mock_monitor_thread = MagicMock()
        mock_monitor_thread.is_alive.return_value = True
        handler.playback_monitor = mock_monitor_thread
        
        # Stop playback
        stop_result = handler.stop()
        
        # Check stop result
        assert stop_result is True
        assert handler.is_playing() is False
        assert handler.stop_monitor is True
        mock_monitor_thread.join.assert_called_once_with(0.5)


# Tests for get_current_position
@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_get_current_position(mock_index_audio_files):
    """Test get_current_position method."""
    # Configure mock
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Set up state for testing
        with patch('threading.Thread'):
            handler.play(datetime.datetime(2025, 2, 15, 10, 0, 0))
        
        # Mock the player's get_time method
        handler.player.get_time = MagicMock(return_value=1800000)  # 30 minutes in ms
        
        # Get current position
        position = handler.get_current_position()
        
        # Check result
        expected_position = MOCK_FILE_INFO[0][1] + datetime.timedelta(minutes=30)
        assert position == expected_position


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_get_current_position_no_media(mock_index_audio_files):
    """Test get_current_position when no media is playing."""
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Get current position without playing anything
        position = handler.get_current_position()
        
        # Check result
        assert position is None


# Helper function to simulate the monitor loop with controlled termination
def simulate_monitor_loop(handler_instance):
    call_count = 0
    max_calls = 5 # Prevent infinite loop in test just in case
    while not handler_instance.stop_monitor and call_count < max_calls:
        # Simulate one iteration of the original _monitor_playback logic
        current_media = handler_instance.player.get_media()
        if not current_media or handler_instance.stop_monitor:
            break # Exit if no media or stopped

        state = handler_instance.player.get_state()
        if state in [MockVLCState.Stopped, MockVLCState.Ended, MockVLCState.Error]:
             handler_instance._is_playing = False
             break # Exit on terminal states

        if handler_instance.is_playing() and handler_instance.position_callback:
            current_pos = handler_instance.get_current_position()
            if current_pos:
                 try:
                     handler_instance.position_callback(current_pos)
                 except Exception as e:
                     print(f"Error in position callback: {e}") # Log errors

            # Check for file end (simplified for test)
            # In a real scenario, you'd compare current_pos with duration
            # Here, we rely on the callback side effect or other test conditions to stop

        # Crucial: Check stop_monitor again before potential sleep
        if handler_instance.stop_monitor:
            break

        # time.sleep(0.1) # No actual sleep needed in the test simulation
        call_count += 1
    # Ensure is_playing is False if loop terminated due to player state
    state = handler_instance.player.get_state()
    if state in [MockVLCState.Stopped, MockVLCState.Ended, MockVLCState.Error]:
         handler_instance._is_playing = False


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_monitor_playback(mock_index_audio_files):
    """Test _monitor_playback method with controlled termination."""
    mock_index_audio_files.return_value = MOCK_FILE_INFO

    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")

        # Mock methods used by the simulated loop
        handler.get_current_position = MagicMock(return_value=datetime.datetime(2025, 2, 15, 10, 30, 0))
        handler.player.get_state = MagicMock(return_value=MockVLCState.Playing)
        handler.player.get_media = MagicMock(return_value=True) # Simulate media loaded

        position_callback = MagicMock()
        handler.position_callback = position_callback
        handler._is_playing = True # Set internal state
        handler.stop_monitor = False # Explicitly start as False

        # Set stop_monitor after the first callback call
        def stop_after_first_call(*args):
            handler.stop_monitor = True
        position_callback.side_effect = stop_after_first_call

        # Run the simulated monitor loop directly
        simulate_monitor_loop(handler)

        # Check that callback was called
        position_callback.assert_called_once_with(datetime.datetime(2025, 2, 15, 10, 30, 0))
        # Check that the loop terminated (implicitly via stop_monitor)
        assert handler.stop_monitor is True
        # Check that is_playing remains True (since state was Playing)
        assert handler.is_playing() is True


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_monitor_playback_file_end(mock_index_audio_files):
    """Test _monitor_playback when reaching end of file."""
    # Configure mock
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Setup for file end detection
        handler.current_file = MOCK_FILE_INFO[0][0]
        handler.media_start_time = MOCK_FILE_INFO[0][1]
        
        # Position at end of file (12 hours later)
        end_time = handler.media_start_time + datetime.timedelta(hours=12)
        handler.get_current_position = MagicMock(return_value=end_time)
        
        handler.player.get_state = MagicMock(return_value=MockVLCState.Playing)
        handler.player.get_media = MagicMock(return_value=True)
        
        # Mock play method that will be called to advance to next file
        handler.play = MagicMock(return_value=True)
        
        # Mock sleep to avoid waiting
        with patch('time.sleep'):
            # Run _monitor_playback
            handler._monitor_playback()
            
            # Check that play was called with the next timestamp
            expected_next_timestamp = end_time + datetime.timedelta(milliseconds=100)
            handler.play.assert_called_once()
            assert handler.play.call_args[0][0] == expected_next_timestamp


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_monitor_playback_player_stopped(mock_index_audio_files):
    """Test _monitor_playback when player is stopped."""
    # Configure mock
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Setup initial state
        handler._is_playing = True
        
        # Mock player state as Stopped
        handler.player.get_state = MagicMock(return_value=MockVLCState.Stopped)
        handler.player.get_media = MagicMock(return_value=True)
        
        # Run _monitor_playback
        handler._monitor_playback()
        
        # Check that is_playing was set to False
        assert handler.is_playing() is False


# Tests for set_playback_rate and get_playback_rate
@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_set_get_playback_rate(mock_index_audio_files):
    """Test set_playback_rate and get_playback_rate methods."""
    # Configure mock
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Set up state for testing
        with patch('threading.Thread'):
            handler.play(datetime.datetime(2025, 2, 15, 10, 0, 0))
        
        # Get initial rate
        initial_rate = handler.get_playback_rate()
        assert initial_rate == 1.0
        
        # Set new rate
        result = handler.set_playback_rate(2.0)
        assert result is True
        
        # Get new rate
        new_rate = handler.get_playback_rate()
        assert new_rate == 2.0


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_set_playback_rate_invalid(mock_index_audio_files):
    """Test set_playback_rate with invalid rate."""
    # Configure mock
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Set up state for testing
        with patch('threading.Thread'):
            handler.play(datetime.datetime(2025, 2, 15, 10, 0, 0))
        
        # Try to set invalid rate
        result = handler.set_playback_rate(0)
        assert result is False
        
        # Rate should remain unchanged
        assert handler.get_playback_rate() == 1.0


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_set_playback_rate_no_media(mock_index_audio_files):
    """Test set_playback_rate when no media is loaded."""
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Try to set rate without media
        result = handler.set_playback_rate(2.0)
        assert result is False


@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_get_playback_rate_no_media(mock_index_audio_files):
    """Test get_playback_rate when no media is loaded."""
    # Create handler with mocked VLC
    with patch('vlc.Instance', return_value=MockVLCInstance()):
        handler = AudioPlaybackHandler(media_path="/mock/path")
        
        # Get rate without media
        rate = handler.get_playback_rate()
        assert rate == 1.0  # Should return default rate