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
    'frequency_bar_height': 360
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
    'sync_ranges': True,
}

# Processing settings
PROCESSING_SETTINGS = {
    'default_resample': '1T',
    'smooth_window': 3,
}

# --- New Data Source Configuration ---
# A list of dictionaries, where each dictionary defines a data source file.
DEFAULT_DATA_SOURCES = [
    {
        "position_name": "NTi1",  # User-friendly name for the measurement position
        "file_path": r"G:\Shared drives\Venta\Jobs\5772 Field Farm, Somerford Keynes\5772 Surveys\5772-1\2025-03-28_SLM_000_123_Log.txt",
        "parser_type": "nti", # Specifies which parser class to use
        "enabled": True         # Flag to easily include/exclude this file
    },
        {
        "position_name": "NTi1",  # User-friendly name for the measurement position
        "file_path": r"G:\Shared drives\Venta\Jobs\5772 Field Farm, Somerford Keynes\5772 Surveys\5772-1\2025-03-28_SLM_000_RTA_3rd_Log.txt",
        "parser_type": "nti", # Specifies which parser class to use
        "enabled": True         # Flag to easily include/exclude this file
    },
    {
        "position_name": "NTi2",
        "file_path": r"G:\Shared drives\Venta\Jobs\5772 Field Farm, Somerford Keynes\5772 Surveys\5772-2\2025-03-28_SLM_000_123_Log.txt",
        "parser_type": "nti",
        "enabled": True
    },    {
        "position_name": "NTi2",
        "file_path": r"G:\Shared drives\Venta\Jobs\5772 Field Farm, Somerford Keynes\5772 Surveys\5772-2\2025-03-28_SLM_000_123_RTA_3rd_Log.txt",
        "parser_type": "nti",
        "enabled": True
    },
    {
        "position_name": "NTi3", # Same position name for related NTi files
        "file_path": r"G:\Shared drives\Venta\Jobs\5772 Field Farm, Somerford Keynes\5772 Surveys\5772-3\2025-03-28_SLM_000_123_Log.txt",
        "parser_type": "nti",
        "enabled": True
    },
        {
        "position_name": "NTi3", # Same position name for related NTi files
        "file_path": r"G:\Shared drives\Venta\Jobs\5772 Field Farm, Somerford Keynes\5772 Surveys\5772-3\2025-03-28_SLM_000_123_RTA_3rd_Log.txt",
        "parser_type": "nti",
        "enabled": True
    },
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