"""
Data processing utilities for Noise Survey Analysis.

This module contains functions for processing, synchronizing, and filtering data.
"""

import logging
import pandas as pd

# Configure Logging
logger = logging.getLogger(__name__)

def get_common_time_range(dataframes, column='Datetime'):
    """
    Find the common time range across multiple dataframes, handling nested dictionaries.
    
    Parameters:
    dataframes (dict): dict of DataFrames or nested dicts containing DataFrames to analyze
    column (str): Name of the datetime column
    
    Returns:
    tuple: (start_time, end_time) as pandas Timestamps
    """
    start_times = []
    end_times = []
    
    def process_item(item):
        if isinstance(item, dict):
            # If it's a dictionary, recursively process its values
            for value in item.values():
                process_item(value)
        elif hasattr(item, 'columns'):  # Check if it's a DataFrame-like object
            if column in item.columns and not item.empty:
                start_times.append(item[column].min())
                end_times.append(item[column].max())
    
    # Process the input dictionary
    process_item(dataframes)
    
    if not start_times or not end_times:
        return None, None
    
    common_start = max(start_times)
    common_end = min(end_times)
    
    return common_start, common_end

def filter_by_time_range(df, start_time, end_time, column='Datetime'):
    """
    Filter a DataFrame to a specific time range.
    
    Parameters:
    df (pd.DataFrame): DataFrame to filter
    start_time (pd.Timestamp): Start time
    end_time (pd.Timestamp): End time
    column (str): Name of the datetime column
    
    Returns:
    pd.DataFrame: Filtered DataFrame
    """
    if column not in df.columns:
        logger.warning(f"Column {column} not found in DataFrame")
        return df
    
    return df[(df[column] >= start_time) & (df[column] <= end_time)]

def synchronize_time_range(position_data):
    """
    Find common time range and synchronize data across all positions.
    
    Parameters:
    position_data (dict): Dictionary of loaded data by position
    
    Returns:
    dict: Dictionary of filtered data by position
    """
    try:
        common_start, common_end = get_common_time_range(position_data)
        logger.info(f"Common time range: {common_start} to {common_end}")
        
        # Filter data to common time range, allowing nested dictionaries
        for position in position_data:
            if isinstance(position_data[position], dict):
                for key, df in position_data[position].items():
                    if isinstance(df, pd.DataFrame) and 'Datetime' in df.columns:
                        position_data[position][key] = filter_by_time_range(df, common_start, common_end)
            else:
                position_data[position] = filter_by_time_range(position_data[position], common_start, common_end)
    except Exception as e:
        logger.error(f"Error determining common time range: {e}")
        logger.warning("Disabling chart synchronization")
    
    return position_data 