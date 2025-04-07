# Initial placeholder for data processor tests 

import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import logging

# Import the modules/functions to test
try:
    from noise_survey_analysis.core.data_processors import (
        get_common_time_range,
        filter_by_time_range,
        synchronize_time_range
    )
except ImportError:
    # Fallback if the module structure is different
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from data_processors import (
        get_common_time_range,
        filter_by_time_range,
        synchronize_time_range
    )

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_dataframes():
    """Create sample DataFrames for testing time range functions."""
    # DataFrame 1: 2023-01-01 10:00:00 to 2023-01-01 11:00:00
    df1 = pd.DataFrame({
        'Datetime': pd.date_range(start='2023-01-01 10:00:00', periods=7, freq='10T'),
        'Value': [1, 2, 3, 4, 5, 6, 7]
    })
    
    # DataFrame 2: 2023-01-01 10:30:00 to 2023-01-01 11:30:00
    df2 = pd.DataFrame({
        'Datetime': pd.date_range(start='2023-01-01 10:30:00', periods=7, freq='10T'),
        'Value': [10, 20, 30, 40, 50, 60, 70]
    })
    
    # DataFrame 3: 2023-01-01 09:30:00 to 2023-01-01 10:30:00
    df3 = pd.DataFrame({
        'Datetime': pd.date_range(start='2023-01-01 09:30:00', periods=7, freq='10T'),
        'Value': [100, 200, 300, 400, 500, 600, 700]
    })
    
    return {
        'df1': df1,
        'df2': df2,
        'df3': df3
    }

@pytest.fixture
def nested_dataframes(sample_dataframes):
    """Create a nested dictionary of DataFrames."""
    return {
        'position1': {
            'source1': sample_dataframes['df1'],
            'source2': sample_dataframes['df2']
        },
        'position2': {
            'source3': sample_dataframes['df3']
        }
    }

@pytest.fixture
def empty_dataframe():
    """Create an empty DataFrame."""
    return pd.DataFrame(columns=['Datetime', 'Value'])

@pytest.fixture
def dataframe_without_datetime():
    """Create a DataFrame without a Datetime column."""
    return pd.DataFrame({
        'Time': pd.date_range(start='2023-01-01', periods=5),
        'Value': [1, 2, 3, 4, 5]
    })

# ============================================================
# Tests for get_common_time_range
# ============================================================

def test_get_common_time_range_flat_dict(sample_dataframes):
    """Test get_common_time_range with a flat dictionary of DataFrames."""
    # Expected common range: 2023-01-01 10:30:00 to 2023-01-01 10:30:00
    # (intersection of df1, df2, and df3)
    start, end = get_common_time_range(sample_dataframes)
    
    assert start == pd.Timestamp('2023-01-01 10:30:00')
    assert end == pd.Timestamp('2023-01-01 10:30:00')

def test_get_common_time_range_nested_dict(nested_dataframes):
    """Test get_common_time_range with a nested dictionary of DataFrames."""
    # Expected common range: 2023-01-01 10:30:00 to 2023-01-01 10:30:00
    # (intersection of all dataframes in the nested structure)
    start, end = get_common_time_range(nested_dataframes)
    
    assert start == pd.Timestamp('2023-01-01 10:30:00')
    assert end == pd.Timestamp('2023-01-01 10:30:00')

def test_get_common_time_range_partial_dict(sample_dataframes):
    """Test get_common_time_range with a subset of DataFrames."""
    # Only df1 and df2 - Expected: 2023-01-01 10:30:00 to 2023-01-01 11:00:00
    partial_dict = {'df1': sample_dataframes['df1'], 'df2': sample_dataframes['df2']}
    start, end = get_common_time_range(partial_dict)
    
    assert start == pd.Timestamp('2023-01-01 10:30:00')
    assert end == pd.Timestamp('2023-01-01 11:00:00')

def test_get_common_time_range_empty_df(empty_dataframe):
    """Test get_common_time_range with an empty DataFrame."""
    data = {'empty': empty_dataframe}
    start, end = get_common_time_range(data)
    
    # Should return None, None for empty DataFrames
    assert start is None
    assert end is None

def test_get_common_time_range_missing_datetime(dataframe_without_datetime):
    """Test get_common_time_range with a DataFrame missing the Datetime column."""
    data = {'no_datetime': dataframe_without_datetime}
    start, end = get_common_time_range(data)
    
    # Should return None, None if no DataFrame has the Datetime column
    assert start is None
    assert end is None

def test_get_common_time_range_mixed_frames(sample_dataframes, empty_dataframe, dataframe_without_datetime):
    """Test get_common_time_range with a mix of valid and invalid DataFrames."""
    mixed_data = {
        'valid1': sample_dataframes['df1'],
        'valid2': sample_dataframes['df2'],
        'empty': empty_dataframe,
        'no_datetime': dataframe_without_datetime
    }
    
    start, end = get_common_time_range(mixed_data)
    
    # Should still find the common range for valid DataFrames
    assert start == pd.Timestamp('2023-01-01 10:30:00')
    assert end == pd.Timestamp('2023-01-01 11:00:00')

def test_get_common_time_range_custom_column(sample_dataframes):
    """Test get_common_time_range with a custom datetime column name."""
    # Create DataFrames with a different column name
    df1 = sample_dataframes['df1'].rename(columns={'Datetime': 'CustomTime'})
    df2 = sample_dataframes['df2'].rename(columns={'Datetime': 'CustomTime'})
    
    custom_data = {'df1': df1, 'df2': df2}
    start, end = get_common_time_range(custom_data, column='CustomTime')
    
    assert start == pd.Timestamp('2023-01-01 10:30:00')
    assert end == pd.Timestamp('2023-01-01 11:00:00')

# ============================================================
# Tests for filter_by_time_range
# ============================================================

def test_filter_by_time_range_basic(sample_dataframes):
    """Test basic functionality of filter_by_time_range."""
    df = sample_dataframes['df1']
    
    # Filter to a specific range
    start_time = pd.Timestamp('2023-01-01 10:20:00')
    end_time = pd.Timestamp('2023-01-01 10:40:00')
    
    filtered_df = filter_by_time_range(df, start_time, end_time)
    
    # Should contain only rows within the range
    assert len(filtered_df) == 3
    assert filtered_df['Datetime'].min() == pd.Timestamp('2023-01-01 10:20:00')
    assert filtered_df['Datetime'].max() == pd.Timestamp('2023-01-01 10:40:00')

def test_filter_by_time_range_exact_match(sample_dataframes):
    """Test filter_by_time_range with start and end times that exactly match data points."""
    df = sample_dataframes['df1']
    
    # Filter to a range that exactly matches two data points
    start_time = pd.Timestamp('2023-01-01 10:10:00')
    end_time = pd.Timestamp('2023-01-01 10:20:00')
    
    filtered_df = filter_by_time_range(df, start_time, end_time)
    
    # Should contain exactly two rows
    assert len(filtered_df) == 2
    assert filtered_df['Datetime'].min() == pd.Timestamp('2023-01-01 10:10:00')
    assert filtered_df['Datetime'].max() == pd.Timestamp('2023-01-01 10:20:00')

def test_filter_by_time_range_no_matching_data(sample_dataframes):
    """Test filter_by_time_range with a time range that doesn't match any data."""
    df = sample_dataframes['df1']
    
    # Filter to a range outside of the data range
    start_time = pd.Timestamp('2023-01-01 12:00:00')
    end_time = pd.Timestamp('2023-01-01 12:30:00')
    
    filtered_df = filter_by_time_range(df, start_time, end_time)
    
    # Should return an empty DataFrame with the same columns
    assert len(filtered_df) == 0
    assert list(filtered_df.columns) == list(df.columns)

def test_filter_by_time_range_missing_column(dataframe_without_datetime):
    """Test filter_by_time_range with a DataFrame missing the Datetime column."""
    df = dataframe_without_datetime
    
    start_time = pd.Timestamp('2023-01-01 10:00:00')
    end_time = pd.Timestamp('2023-01-01 11:00:00')
    
    # Should return the original DataFrame unmodified and log a warning
    with patch('logging.Logger.warning') as mock_warn:
        filtered_df = filter_by_time_range(df, start_time, end_time)
        mock_warn.assert_called_once()
    
    # DataFrame should be unchanged
    assert len(filtered_df) == len(df)
    assert list(filtered_df.columns) == list(df.columns)

def test_filter_by_time_range_custom_column(sample_dataframes):
    """Test filter_by_time_range with a custom datetime column name."""
    # Create a DataFrame with a different column name
    df = sample_dataframes['df1'].rename(columns={'Datetime': 'CustomTime'})
    
    start_time = pd.Timestamp('2023-01-01 10:20:00')
    end_time = pd.Timestamp('2023-01-01 10:40:00')
    
    filtered_df = filter_by_time_range(df, start_time, end_time, column='CustomTime')
    
    # Should filter based on the custom column
    assert len(filtered_df) == 3
    assert filtered_df['CustomTime'].min() == pd.Timestamp('2023-01-01 10:20:00')
    assert filtered_df['CustomTime'].max() == pd.Timestamp('2023-01-01 10:40:00')

# ============================================================
# Tests for synchronize_time_range
# ============================================================

def test_synchronize_time_range_nested_dict(nested_dataframes):
    """Test synchronize_time_range with a nested dictionary of DataFrames."""
    # Mock the get_common_time_range function to return a fixed range
    common_start = pd.Timestamp('2023-01-01 10:20:00')
    common_end = pd.Timestamp('2023-01-01 10:40:00')
    
    with patch('noise_survey_analysis.core.data_processors.get_common_time_range', 
               return_value=(common_start, common_end)):
        result = synchronize_time_range(nested_dataframes)
    
    # Check that all DataFrames in the result were filtered to the mocked common range
    assert 'position1' in result
    assert 'position2' in result
    assert 'source1' in result['position1']
    assert 'source2' in result['position1']
    assert 'source3' in result['position2']
    
    # Check each DataFrame's time range
    df1 = result['position1']['source1']
    assert df1['Datetime'].min() == common_start
    assert df1['Datetime'].max() <= common_end
    
    df2 = result['position1']['source2']
    assert df2['Datetime'].min() >= common_start
    assert df2['Datetime'].max() <= common_end
    
    df3 = result['position2']['source3']
    assert df3['Datetime'].min() >= common_start
    assert df3['Datetime'].max() <= common_end

def test_synchronize_time_range_flat_dict(sample_dataframes):
    """Test synchronize_time_range with a flat dictionary of DataFrames."""
    # Create a flat dictionary (position: DataFrame)
    flat_dict = {
        'position1': sample_dataframes['df1'],
        'position2': sample_dataframes['df2'],
        'position3': sample_dataframes['df3']
    }
    
    # Mock the get_common_time_range function to return a fixed range
    common_start = pd.Timestamp('2023-01-01 10:20:00')
    common_end = pd.Timestamp('2023-01-01 10:40:00')
    
    with patch('noise_survey_analysis.core.data_processors.get_common_time_range', 
               return_value=(common_start, common_end)):
        result = synchronize_time_range(flat_dict)
    
    # Check that all DataFrames in the result were filtered to the mocked common range
    assert 'position1' in result
    assert 'position2' in result
    assert 'position3' in result
    
    # Check each DataFrame's time range
    df1 = result['position1']
    assert df1['Datetime'].min() == common_start
    assert df1['Datetime'].max() <= common_end
    
    df2 = result['position2']
    assert df2['Datetime'].min() >= common_start
    assert df2['Datetime'].max() <= common_end
    
    df3 = result['position3']
    assert df3['Datetime'].min() >= common_start
    assert df3['Datetime'].max() <= common_end

def test_synchronize_time_range_error_handling():
    """Test synchronize_time_range when get_common_time_range raises an error."""
    # Create a simple data structure
    data = {'position1': pd.DataFrame({'Datetime': [1, 2, 3]})}
    
    # Mock get_common_time_range to raise an exception
    with patch('noise_survey_analysis.core.data_processors.get_common_time_range', 
               side_effect=Exception("Test error")):
        # And also mock the logger to check it's called correctly
        with patch('noise_survey_analysis.core.data_processors.logger') as mock_logger:
            result = synchronize_time_range(data)
            
            # Check that error was logged
            mock_logger.error.assert_called_once()
            mock_logger.warning.assert_called_once()
    
    # Result should be the original data, unmodified
    assert result == data
    assert 'position1' in result
    assert list(result['position1'].columns) == ['Datetime'] 