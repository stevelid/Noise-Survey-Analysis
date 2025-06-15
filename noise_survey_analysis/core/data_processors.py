"""
Data processing utilities for Noise Survey Analysis.

This module contains functions for processing, synchronizing, and filtering data.
"""

import logging
import pandas as pd
import numpy as np

# Import necessary configuration
try:
    from .config import CHART_SETTINGS, REQUIRED_SPECTRAL_PREFIXES
except ImportError: # Fallback for different execution contexts
    from noise_survey_analysis.core.config import CHART_SETTINGS, REQUIRED_SPECTRAL_PREFIXES

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

def prepare_spectral_image_data(df, param, chart_settings):
    """
    Process spectral data from a DataFrame into the format needed for image spectrogram visualization.
    This function extracts the matrix preparation logic from make_image_spectrogram.
    
    Args:
        df (pd.DataFrame): DataFrame with frequency data. Must contain 'Datetime'.
        param (str): Base parameter name (e.g., 'LZeq').
        chart_settings (dict): Configuration for chart appearance.
    
    Returns:
        dict: A dictionary containing all processed data needed for visualization, or None if processing fails.
              The dictionary includes:
              - frequencies: NumPy array of frequency values
              - frequency_labels: List of formatted frequency labels
              - times_ms: NumPy array of times in milliseconds
              - times_dt: NumPy array of datetime objects
              - levels_matrix: Original matrix of shape (n_times, n_freqs)
              - levels_matrix_transposed: Transposed matrix of shape (n_freqs, n_times) for image glyph
              - freq_indices: NumPy array of frequency indices
              - min_val, max_val: Value range for color mapping
    """
    logger.debug(f"Preparing spectral image data for parameter: {param}")
    
    if df is None or df.empty:
        logger.warning(f"Empty DataFrame provided for spectral data preparation: {param}")
        return None
        
    if 'Datetime' not in df.columns:
        logger.error(f"Missing 'Datetime' column for spectral data preparation: {param}")
        return None
        
    if not pd.api.types.is_datetime64_any_dtype(df['Datetime']):
        df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')
        df.dropna(subset=['Datetime'], inplace=True)
        if df.empty:
            logger.warning("No valid dates after conversion in spectral data")
            return None
    
    # --- Get band slicing settings ---
    lower_band_idx = chart_settings.get('lower_freq_band', 0)
    upper_band_idx = chart_settings.get('upper_freq_band', -1)
    
    # --- Find and Sort Frequency Columns ---
    freq_cols_found = []
    all_frequencies = []
    for col in df.columns:
        if col.startswith(param + '_') and col.split('_')[-1].replace('.', '', 1).isdigit():
            try:
                freq = float(col.split('_')[-1])
                freq_cols_found.append(col)
                all_frequencies.append(freq)
            except (ValueError, IndexError):
                continue
    
    if not freq_cols_found:
        logger.error(f"No frequency columns found for parameter '{param}'")
        return None
    
    sorted_indices = np.argsort(all_frequencies)
    frequencies = np.array(all_frequencies)[sorted_indices]
    freq_columns = np.array(freq_cols_found)[sorted_indices]
    
    # --- Apply Band Slicing ---
    if upper_band_idx is None or upper_band_idx == -1:
        upper_band_idx = len(frequencies)
    
    selected_frequencies = frequencies[lower_band_idx:upper_band_idx]
    selected_freq_columns = freq_columns[lower_band_idx:upper_band_idx]
    
    if len(selected_frequencies) == 0:
        logger.error(f"No frequencies after band slicing for '{param}'")
        return None
    
    n_freqs = len(selected_frequencies)
    frequency_labels_str = [(str(int(f)) if f >= 10 else f"{f:.1f}") + " Hz" for f in selected_frequencies]
    
    # --- Prepare Data for `image` Glyph ---
    levels_matrix = df[selected_freq_columns].values  # Shape: (n_times, n_freqs)
    times_dt = df['Datetime'].values
    n_times = len(times_dt)
    
    if n_times == 0:
        logger.warning(f"No time points for spectral data: {param}")
        return None
    
    # Convert times to milliseconds epoch (numeric) for x coordinate
    times_ms = pd.to_datetime(times_dt).astype('int64') // 10**6
    
    # Y coordinate: Use simple linear indices [0, 1, ..., n_freqs-1]
    freq_indices = np.arange(n_freqs)
    
    # Handle NaNs in the data matrix
    valid_levels = levels_matrix[~np.isnan(levels_matrix)]
    if len(valid_levels) > 0:
        min_val = np.min(valid_levels)
        max_val = np.max(valid_levels)
        nan_replace_val = min_val - 20  # Choose a value clearly outside range
    else:  # All NaNs?
        min_val, max_val = 0, 100
        nan_replace_val = -100
    
    # Replace NaNs with out-of-range value for visualization
    levels_matrix_clean = np.nan_to_num(levels_matrix, nan=nan_replace_val)
    
    # Transpose for Bokeh image glyph - shape: (n_freqs, n_times)
    levels_matrix_transposed = levels_matrix_clean.T

    x = times_ms[0]
    y = -0.5
    dw = times_ms[-1] - times_ms[0] if n_times > 1 else 60000
    dh = n_freqs
    
    # Return all data needed for visualization
    return {
        'frequencies': selected_frequencies,
        'frequency_labels': frequency_labels_str,
        'times_ms': times_ms,
        'times_dt': times_dt,
        'levels_matrix': levels_matrix_clean,  # Original shape (n_times, n_freqs)
        'levels_matrix_transposed': levels_matrix_transposed,  # Shape (n_freqs, n_times)
        'freq_indices': freq_indices,
        'min_val': min_val,
        'max_val': max_val,
        'n_times': n_times,
        'n_freqs': n_freqs,
        'x': x,
        'y': y,
        'dw': dw,
        'dh': dh
    } 