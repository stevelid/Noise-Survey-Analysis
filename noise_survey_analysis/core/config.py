"""
Centralized configuration for Noise Survey Analysis.

This module contains all configuration settings used throughout the application.
Previously, these settings were scattered across different files.
"""

REQUIRED_BROADBAND_METRICS = [
    'LAeq',
    'LAF90',
    'LAF10',
    'LAFmax',
    'LAFmax_dt', # From NTi Log
    'LAeq_dt',   # From NTi Log
]

# Define the prefixes for spectral parameters required
REQUIRED_SPECTRAL_PREFIXES = [
    'LZeq',
    'LZF90',
    'LZFmax',
]


# Chart settings
CHART_SETTINGS = {
    'lower_freq_band': 6,
    'upper_freq_band': -10,
    'low_freq_height': 360,      
    'low_freq_width': 1600,      
    'high_freq_height': 360,     
    'high_freq_width': 1600,      
    'spectrogram_height': 360,   
    'spectrogram_width': 1600,    
    'sync_charts': True,
    'tools': 'xzoom_in,xzoom_out,xpan,reset,xwheel_zoom',  # X-axis only tools
    'active_scroll': 'xwheel_zoom',
    'line_width': 1,
    'colormap': 'Turbo256',
    'active_drag': 'xpan',
    'range_selector_width': 1600,
    'range_selector_height': 150,
    'y_range': (0, 100),
    'auto_y_range': False,
    'frequency_log_scale': False,
    'frequency_bar_height': 360,
    'frequency_bar_width': 1600,
    'default_spectral_param': 'LZeq',  # Default parameter to show for spectrograms
}

# Visualization settings
VISUALIZATION_SETTINGS = {
    'default_title': 'Sound Level Analysis',
    'line_colors': {
        'LAeq': '#0000FF',  # Blue (adjusted to match example)
        'LAF90': '#008000', # Green (adjusted to match example as LA90)
        'LAF10': '#FFA500', # Orange
        'LAFmax': '#FF0000', # Red
        'LAFmax_dt': '#FF0000', # Red
        'LAeq_dt': '#0000FF',  # Blue (adjusted to match example)
    },
    'show_grid': True,
    'sync_ranges': True, # Whether to synchronize the x-ranges of the charts to be the same size (equal to shortest time range)
}

# Processing settings
PROCESSING_SETTINGS = {
    'default_resample': '1S',
    'smooth_window': 3,
}

# Default base directory for job files
DEFAULT_BASE_JOB_DIR = "G:\\Shared drives\\Venta\\Jobs"

# --- General Application Settings ---
GENERAL_SETTINGS = {
    # Define the base path where corresponding audio/video media files might be found.
    # This path should correspond to the root directory containing media files,
    # which are typically expected to be named similarly to the survey data files.
    # TODO: Update this path to the correct location for your system or make it configurable.
    "media_path": r"G:\Shared drives\Venta\Jobs\5924 44 Grafton Road, London\5924 Surveys\5924-3",

    # TODO: Add other general settings like logging level, default theme, etc.
    # "log_level": "INFO", # Example: DEBUG, INFO, WARNING, ERROR
}

# --- New Data Source Configuration ---
# A list of dictionaries, where each dictionary defines a data source file.
DEFAULT_DATA_SOURCES = [
    {
        "position_name": "svan",  # User-friendly name for the measurement position
        "file_path": r"G:\Shared drives\Venta\Jobs\5792 Swyncombe Field, Padel Courts\5792 Surveys\971-2\L251_summary.csv",
        "parser_type": "svan", # Specifies which parser class to use
        "enabled": True         # Flag to easily include/exclude this file
    }
]
# Configuration dictionary (for backward compatibility)
CONFIG = {
    'chart_settings': CHART_SETTINGS,
    'visualization': VISUALIZATION_SETTINGS,
    'processing': PROCESSING_SETTINGS
    # Avoid putting DEFAULT_DATA_SOURCES in here unless absolutely necessary
    # for old code. It's better managed separately.
}

# Add logger for config module if used elsewhere
import logging
logger = logging.getLogger(__name__) 