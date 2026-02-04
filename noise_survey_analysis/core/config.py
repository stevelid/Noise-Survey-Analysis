"""
Centralized configuration for Noise Survey Analysis.

This module contains all configuration settings used throughout the application.
Previously, these settings were scattered across different files.
"""

import logging

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
    # Defines the master frequency range to be prepared in Python and sent to the browser.
    'data_prep_freq_range_hz': [20, 20000],

    # Defines the default visible frequency range for the spectrogram display.
    'spectrogram_freq_range_hz': [31, 2000],
    
    # Defines the frequency range for the interactive bar chart.
    'freq_bar_freq_range_hz': [20, 10000],

    # Defines the frequency range for the detailed data table.
    'freq_table_freq_range_hz': [20, 10000],
    'low_freq_height': 360,
    'low_freq_width': 1600,
    'high_freq_height': 360,
    'high_freq_width': 1600,
    'spectrogram_height': 360,
    'spectrogram_width': 1600,
    'sync_charts': True,
    'tools': 'xzoom_in,xzoom_out,xpan,reset,xwheel_zoom,xbox_select',  # X-axis only tools
    'active_scroll': 'xwheel_zoom',
    'line_width': 1,
    'colormap': 'Turbo256',
    'active_drag': 'xpan',
    'range_selector_width': 1600,
    'range_selector_height': 150,
    'y_range': (0, 100),
    'auto_y_range': False,
    # Set the y-axis range for timeseries charts.
    # An empty list [] enables auto-ranging.
    # Example: [20, 100]
    'timeseries_y_range': [20, 100],
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

# General UI layout settings
UI_LAYOUT_SETTINGS = {
    'side_panel_width': 320,
}

# Processing settings
PROCESSING_SETTINGS = {
    'default_resample': '1S',
    'smooth_window': 3,
}

# Streaming / Lite data settings
LITE_TARGET_POINTS = 5000
STREAMING_ENABLED = True
STREAMING_DEBOUNCE_MS = 200
STREAMING_VIEWPOINT_MULTIPLIER = 3

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
    },
    {
        "position_name": "nti_log",
        "file_path": r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_123_Log.txt",
        "parser_type": "nti",
        "enabled": True
    },
    {
        "position_name": "nti_rpt_report",
        "file_path": r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_123_Rpt_Report.txt",
        "parser_type": "nti",
        "enabled": True
    },
    {
        "position_name": "nti_rta_log",
        "file_path": r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Log.txt",
        "parser_type": "nti",
        "enabled": True
    },
    {
        "position_name": "nti_rta_rpt_report",
        "file_path": r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Rpt_Report.txt",
        "parser_type": "nti",
        "enabled": True
    }
]
# Configuration dictionary (for backward compatibility)
CONFIG = {
    'chart_settings': CHART_SETTINGS,
    'visualization': VISUALIZATION_SETTINGS,
    'processing': PROCESSING_SETTINGS,
    'ui_layout': UI_LAYOUT_SETTINGS,
    # Avoid putting DEFAULT_DATA_SOURCES in here unless absolutely necessary
    # for old code. It's better managed separately.
}

# Add logger for config module if used elsewhere
logger = logging.getLogger(__name__)
