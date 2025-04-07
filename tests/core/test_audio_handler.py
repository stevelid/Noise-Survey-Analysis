import datetime
import pytest # Import pytest itself (optional, but good practice)
from unittest.mock import patch # Use unittest.mock for patching attributes

# Import the class we want to test
# Adjust the path if your structure is slightly different
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler

# Define some test data (replace with realistic examples if needed)
MOCK_FILE_INFO = [
    ('/path/to/file1.wav', datetime.datetime(2025, 2, 15, 10, 0, 0)), # Starts at 10:00
    ('/path/to/file2.wav', datetime.datetime(2025, 2, 15, 22, 0, 0)), # Starts at 22:00 (12 hours later)
    ('/path/to/file3.wav', datetime.datetime(2025, 2, 16, 10, 0, 0)), # Starts next day 10:00
]
# Assume 12 hour duration for simplicity in test, matching handler logic
FILE_DURATION_SECONDS = 12 * 60 * 60

# Test function names MUST start with 'test_'
@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_within_first_file(mock_index_audio_files):
    """Test finding a timestamp clearly within the first file's range."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    # Arrange: Create an instance
    handler = AudioPlaybackHandler(media_path="/mock/path")

    target_timestamp = datetime.datetime(2025, 2, 15, 11, 30, 0) # 11:30

    # Act: Call the method we are testing
    filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

    # Assert: Check if the results are what we expect
    assert filepath == MOCK_FILE_INFO[0][0] # Should be file1.wav
    # Expected offset: 1.5 hours = 1.5 * 3600 = 5400 seconds
    assert offset == pytest.approx(5400.0) # Use approx for float comparison
    assert start_time == MOCK_FILE_INFO[0][1]
    mock_index_audio_files.assert_called_once()

@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_at_exact_start_time(mock_index_audio_files):
    """Test finding a timestamp exactly at the start of a file."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    handler = AudioPlaybackHandler(media_path="/mock/path")
    target_timestamp = MOCK_FILE_INFO[1][1] # 22:00:00

    filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

    assert filepath == MOCK_FILE_INFO[1][0] # Should be file2.wav
    assert offset == pytest.approx(0.0)     # Offset should be 0
    assert start_time == MOCK_FILE_INFO[1][1]
    mock_index_audio_files.assert_called_once()

@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_near_end_of_file(mock_index_audio_files):
    """Test finding a timestamp near the end of a file's assumed duration."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    handler = AudioPlaybackHandler(media_path="/mock/path")
    # Just before the end of file 1 (10:00 + 12h = 22:00)
    target_timestamp = datetime.datetime(2025, 2, 15, 21, 59, 59)

    filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

    assert filepath == MOCK_FILE_INFO[0][0] # Still file1.wav
    expected_offset = FILE_DURATION_SECONDS - 1
    assert offset == pytest.approx(expected_offset)
    assert start_time == MOCK_FILE_INFO[0][1]
    mock_index_audio_files.assert_called_once()

@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_before_first_file(mock_index_audio_files):
    """Test finding a timestamp before the very first file."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    handler = AudioPlaybackHandler(media_path="/mock/path")
    target_timestamp = datetime.datetime(2025, 2, 15, 9, 0, 0) # Before 10:00

    filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

    assert filepath == MOCK_FILE_INFO[0][0] # Should clamp to file1.wav
    assert offset == pytest.approx(0.0)     # Offset should be 0
    assert start_time == MOCK_FILE_INFO[0][1]
    mock_index_audio_files.assert_called_once()

@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_after_last_file(mock_index_audio_files):
    """Test finding a timestamp after the range of the last file."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO
    
    handler = AudioPlaybackHandler(media_path="/mock/path")
    # After file 3 ends (Feb 16, 10:00 + 12h = Feb 16, 22:00)
    target_timestamp = datetime.datetime(2025, 2, 16, 23, 0, 0)

    filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

    assert filepath == MOCK_FILE_INFO[2][0] # Should clamp to file3.wav
    # Offset should be the full duration
    assert offset == pytest.approx(FILE_DURATION_SECONDS)
    assert start_time == MOCK_FILE_INFO[2][1]
    mock_index_audio_files.assert_called_once()

# Example using patching if you didn't want to set handler.file_info directly
@patch.object(AudioPlaybackHandler, '_index_audio_files')
def test_find_file_with_patched_index(mock_index_audio_files):
    """Test using patching to provide file_info."""
    # Configure the mock return value
    mock_index_audio_files.return_value = MOCK_FILE_INFO

    # Create instance *after* patching (or patch instance directly)
    # The path doesn't matter as _index_audio_files is mocked
    handler = AudioPlaybackHandler(media_path="/mock/path")

    target_timestamp = datetime.datetime(2025, 2, 15, 15, 0, 0) # 15:00

    filepath, offset, start_time = handler._find_file_for_timestamp(target_timestamp)

    assert filepath == MOCK_FILE_INFO[0][0]
    assert offset == pytest.approx(5 * 3600) # 5 hours offset
    assert start_time == MOCK_FILE_INFO[0][1]
    mock_index_audio_files.assert_called_once() # Verify the mocked method was called