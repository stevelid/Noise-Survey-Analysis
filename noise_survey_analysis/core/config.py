"""
Centralized configuration for Noise Survey Analysis.

This module contains all configuration settings used throughout the application.
Previously, these settings were scattered across different files.
"""

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
    'sync_charts': False,
    'tools': 'xzoom_in,xzoom_out,xpan,reset,xwheel_zoom',  # X-axis only tools
    'active_scroll': 'xwheel_zoom',
    'line_width': 1,
    'colormap': 'Turbo256',
    'active_drag': 'xpan',
    'range_selector_width': 1600,
    'range_selector_height': 150,
    'y_range': (0, 100),
    'auto_y_range': False,
    'frequency_log_scale': True
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

# Default file paths (these can be overridden by the user)
DEFAULT_FILE_PATHS = {
    'SW': r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\NS4A\5793 Alton Road, Ross-on-wye_2025_02_21__17h20m41s_2025_02_15__10h45m00s.csv",
    'N': r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\NS7\5793 Alton Road, Ross-on-wye_2025_02_21__17h34m02s_2025_02_15__10h50m00s.csv",
    'SE': r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\5793-1\2025-02-15_SLM_000_123_Rpt_Report.txt"
}

# Default file types
DEFAULT_FILE_TYPES = {
    'SW': 'sentry',  # Noise Sentry (low frequency data only)
    'N': 'sentry',   # Noise Sentry (low frequency data only)
    'SE': 'nti'      # NTi (may have low, high frequency, and spectral data)
}

# Configuration dictionary (for backward compatibility)
CONFIG = {
    'chart_settings': CHART_SETTINGS,
    'visualization': VISUALIZATION_SETTINGS,
    'processing': PROCESSING_SETTINGS
} 