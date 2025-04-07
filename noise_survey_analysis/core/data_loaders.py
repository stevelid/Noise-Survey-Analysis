"""
Data loading utilities for Noise Survey Analysis.

This module provides functions for loading noise survey data from different file formats.
It serves as a wrapper around the original data_parsers functions.
"""

import logging
import pandas as pd
import os

# Import the original parsers (temporarily keep using the original file)
from data_parsers import read_in_noise_sentry_file, read_in_Svan_file, read_NTi

# Import configuration
from noise_survey_analysis.core.config import CONFIG, DEFAULT_FILE_PATHS, DEFAULT_FILE_TYPES

# Configure Logging
logger = logging.getLogger(__name__)

def define_file_paths_and_types(file_paths=None, file_types=None):
    """
    Define file paths and parser types for noise survey data.
    
    Parameters:
    file_paths (dict, optional): Dictionary of file paths to analyze.
                               Keys are position names, values are file paths.
    file_types (dict, optional): Dictionary specifying parser to use for each position.
                               Keys are position names, values are parser types ('sentry', 'nti', 'svan').
    
    Returns:
    tuple: (file_paths, file_types) - Dictionaries with file paths and parser types
    """
    if file_paths is None:
        file_paths = DEFAULT_FILE_PATHS.copy()
    
    if file_types is None:
        file_types = DEFAULT_FILE_TYPES.copy()
    
    return file_paths, file_types

def load_data(file_paths, file_types):
    """
    Load all data using the specified parsers.
    
    Parameters:
    file_paths (dict): Dictionary of file paths
    file_types (dict): Dictionary of parser types
    
    Returns:
    dict: Dictionary of loaded data by position
    """
    position_data = {}
    for position, path in file_paths.items():
        try:
            # Check if the file exists
            if not os.path.exists(path):
                logger.error(f"File not found: {path}")
                continue
                
            # Use explicitly specified parser
            parser_type = file_types.get(position, '').lower()
            
            if parser_type == 'sentry':
                logger.info(f"Loading {position} with Noise Sentry parser")
                position_data[position] = read_in_noise_sentry_file(path)
            elif parser_type == 'nti':
                logger.info(f"Loading {position} with NTi parser")
                position_data[position] = read_NTi(path) # may return a dictionary of dataframes
            elif parser_type == 'svan':
                logger.info(f"Loading {position} with Svan parser")
                position_data[position] = read_in_Svan_file(path) # may return a dictionary of dataframes
            else:
                logger.info(f"No parser specified for {position}. Guessing based on file extension.")
                # Guess parser based on file extension
                if path.endswith('.csv'):
                    position_data[position] = read_in_noise_sentry_file(path)
                elif path.endswith('.xlsx'):
                    position_data[position] = read_in_Svan_file(path)
                else:
                    # Assume NTi if no recognizable extension
                    position_data[position] = read_NTi(path)
                    
        except Exception as e:
            logger.error(f"Error loading data for {position}: {e}")
    
    return position_data

def examine_data(position_data):
    """
    Examine the loaded data structure and print summaries.
    
    Parameters:
    position_data (dict): Dictionary of loaded data by position
    """
    for position, data in position_data.items():
        print(f"\n=== Position: {position} ===")
        
        if isinstance(data, pd.DataFrame):
            print(f"DataFrame with shape: {data.shape}")
            print(f"Columns: {data.columns.tolist()}")
            print(f"Date range: {data['Datetime'].min()} to {data['Datetime'].max()}")
        elif isinstance(data, dict):
            print(f"Dictionary with keys: {list(data.keys())}")
            for key, df in data.items():
                if isinstance(df, pd.DataFrame):
                    print(f"  - {key}: DataFrame with shape {df.shape}")
                    if 'Datetime' in df.columns:
                        print(f"    Date range: {df['Datetime'].min()} to {df['Datetime'].max()}")

# Future improvement: Implement a FileSelector class for interactive file selection
class FileSelector:
    """
    Class for interactive file selection (placeholder for future implementation).
    """
    
    def __init__(self):
        """Initialize the file selector."""
        pass
    
    def select_files(self):
        """
        Show a file selection dialog and return selected files.
        
        Returns:
        dict: Dictionary of selected files by position
        """
        # This would be implemented in Phase 2
        return DEFAULT_FILE_PATHS.copy() 