"""
Centralized configuration for Noise Survey Analysis.

This module contains all configuration settings used throughout the application.
Previously, these settings were scattered across different files.
"""

import json
import logging
import os

logger = logging.getLogger(__name__)


def _get_env_text(name, default=''):
    """Return a stripped environment value, or default when unset/blank."""
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def _load_default_data_sources():
    """Load optional default data sources without hardcoding local paths."""
    inline_json = _get_env_text('NOISE_SURVEY_DEFAULT_DATA_SOURCES_JSON')
    if inline_json:
        try:
            parsed = json.loads(inline_json)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Ignoring invalid NOISE_SURVEY_DEFAULT_DATA_SOURCES_JSON: %s",
                exc,
            )
        else:
            if isinstance(parsed, list):
                return parsed
            logger.warning(
                "Ignoring NOISE_SURVEY_DEFAULT_DATA_SOURCES_JSON because it is not a list"
            )

    config_path = _get_env_text('NOISE_SURVEY_DEFAULT_DATA_SOURCES_FILE')
    if config_path:
        try:
            with open(config_path, 'r', encoding='utf-8') as config_file:
                parsed = json.load(config_file)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Ignoring NOISE_SURVEY_DEFAULT_DATA_SOURCES_FILE %r: %s",
                config_path,
                exc,
            )
        else:
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                for key in ('sourceConfigs', 'sources', 'data_sources'):
                    sources = parsed.get(key)
                    if isinstance(sources, list):
                        return sources
            logger.warning(
                "Ignoring NOISE_SURVEY_DEFAULT_DATA_SOURCES_FILE %r because it "
                "does not contain a data-source list",
                config_path,
            )

    return []

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
    # Initial figure heights. With "Fit rows to window" on, static/js/services/layout/layoutRenderer.js
    # resizes the time series and spectrograms to fill the browser window; these are the starting
    # values (and, with the fit off, the fixed heights).
    'low_freq_height': 150,
    'low_freq_width': 1600,
    'high_freq_height': 170,
    'high_freq_width': 1600,
    'spectrogram_height': 124,
    'spectrogram_width': 1600,
    'spectrogram_log_window_min_step_ms': 100,
    'spectrogram_log_window_min_ms': 15 * 60 * 1000,
    'spectrogram_log_window_max_step_ms': 1000,
    'spectrogram_log_window_max_ms': 60 * 60 * 1000,
    'sync_charts': True,
    'tools': 'xzoom_in,xzoom_out,xpan,reset,xwheel_zoom,xbox_select',  # X-axis only tools
    'active_scroll': 'xwheel_zoom',
    'line_width': 1,
    'colormap': 'Turbo256',
    'active_drag': 'xpan',
    'range_selector_width': 1600,
    'range_selector_height': 44,
    'y_range': (0, 100),
    'auto_y_range': False,
    # Set the y-axis range for timeseries charts.
    # An empty list [] enables auto-ranging.
    # Example: [20, 100]
    'timeseries_y_range': [20, 100],
    'frequency_log_scale': False,
    'frequency_bar_height': 170,
    'frequency_bar_width': 352,  # docked in the sidebar column; the figure stretches to the dock
    'default_spectral_param': 'LZeq',  # Default parameter to show for spectrograms
}

# Plot-frame borders shared by every time-domain figure (time series, spectrogram, range selector)
# and the frequency figure. Bokeh's min_border_* is only a minimum, so these are guaranteed to
# exceed the width of the y-axis tick labels (8pt, no axis label); the frame left and right edges
# are therefore identical in all figures and the time axes line up vertically. Do not use
# frame_width, it fights stretch_width. Tested in tests/test_wp1_layout.py.
FRAME_BORDER_LEFT = 56
FRAME_BORDER_RIGHT = 12

# Compact layout metrics (px). The JS fit (layoutRenderer.js / layoutMath.js) mirrors the
# minimums; STRIP_HEIGHT is the collapsed spectrogram.
LAYOUT_SETTINGS = {
    'toolbar_height': 48,
    'range_selector_height': 44,
    'position_header_height': 24,
    'spectrogram_strip_height': 26,
    'timeseries_min_height': 110,
    'spectrogram_min_height': 80,
    'fixed_timeseries_height': 220,   # used when the rows cannot fit the window (4+ positions)
    'fixed_spectrogram_height': 160,
    'timeseries_share': 0.55,
    'frequency_dock_chart_height': 170,
    'axis_font_size': '8pt',
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

# Log view threshold - switch from overview to log when viewport shows fewer than this many overview points
# User can configure this via the UI. Default: 50 overview points triggers log view.
# This translates to roughly 50 seconds of data at 1-second overview resolution.
LOG_VIEW_THRESHOLD_POINTS = 50

# Hard cap for log viewport width (seconds), after adaptive point-based scaling.
# Keeps streaming bounded for very low sample-rate datasets.
LOG_VIEW_MAX_VIEWPORT_SECONDS = 86400

# --- Step-size-aware streaming limits ---
# Target row budget for log streaming (visible points only, excludes buffer).
# At 100ms sample period: 36000 rows = 60 minutes visible.
# At 1s sample period: 36000 rows = 10 hours visible.
LOG_VIEW_TARGET_ROWS = 36000

# Min/max viewport bounds (seconds) regardless of sample period.
LOG_VIEW_MIN_VIEWPORT_SECONDS = 60  # At least 1 minute
LOG_VIEW_MAX_VIEWPORT_SECONDS_HIGH_RATE = 3600  # Max 1 hour for high-rate data

# Buffer multiplier as fraction of viewport (reduced for high-rate data).
# Old: 0.5 (50% each side). New: adaptive based on sample period.
LOG_VIEW_BUFFER_FRACTION_DEFAULT = 0.5
LOG_VIEW_BUFFER_FRACTION_HIGH_RATE = 0.1  # 10% buffer for data faster than 1s
LOG_VIEW_HIGH_RATE_THRESHOLD_SECONDS = 1.0  # Sample periods <= this are "high rate"

# --- Default base directory for job files ---
# Venta jobs always live on the Venta shared drive, which Google Drive syncs to
# every machine, normally as G:. The drive letter is the only thing that varies,
# so try the usual one first and then look for the same folder on any other
# drive before giving up. NOISE_SURVEY_BASE_JOB_DIR overrides all of this.
VENTA_JOBS_SUBPATH = os.path.join('Shared drives', 'Venta', 'Jobs')
VENTA_JOBS_DIR = os.path.join('G:' + os.sep, VENTA_JOBS_SUBPATH)


def _find_venta_jobs_dir():
    """Locate the Venta Jobs folder, falling back to the expected G: path."""
    if os.path.isdir(VENTA_JOBS_DIR):
        return VENTA_JOBS_DIR

    for letter in 'GHIJKLMNOPQRSTUVWXYZDE':
        candidate = os.path.join(letter + ':' + os.sep, VENTA_JOBS_SUBPATH)
        if os.path.isdir(candidate):
            logger.info("Venta Jobs folder found on %s:", letter)
            return candidate

    # Nothing mounted. Return the expected path anyway rather than silently
    # dropping the user somewhere unrelated - the missing drive is the problem
    # worth showing them.
    logger.warning(
        "Venta Jobs folder not found. Is Google Drive running? Expected: %s",
        VENTA_JOBS_DIR,
    )
    return VENTA_JOBS_DIR


DEFAULT_BASE_JOB_DIR = _get_env_text(
    'NOISE_SURVEY_BASE_JOB_DIR',
    _find_venta_jobs_dir(),
)

# --- General Application Settings ---
GENERAL_SETTINGS = {
    # Define the base path where corresponding audio/video media files might be found.
    # This path should correspond to the root directory containing media files,
    # which are typically expected to be named similarly to the survey data files.
    "media_path": _get_env_text('NOISE_SURVEY_MEDIA_PATH'),

    # TODO: Add other general settings like logging level, default theme, etc.
    # "log_level": "INFO", # Example: DEBUG, INFO, WARNING, ERROR
}

# --- Audio playback backend ---
# 'vlc'     server-side playback through python-vlc (default for the live dashboard).
# 'browser' the dashboard fetches 60 s PCM clips from the localhost media server
#           (core/media_server.py) and plays them in the page (real gain, instant
#           position switching). Static HTML always plays clips in the browser.
# The Audio backend toggle next to the Boost button changes this per tab at run time;
# NOISE_SURVEY_AUDIO_BACKEND sets the starting value.
AUDIO_BACKENDS = ('vlc', 'browser')


def _resolve_audio_backend(raw):
    value = str(raw or '').strip().lower()
    return value if value in AUDIO_BACKENDS else 'vlc'


AUDIO_BACKEND = _resolve_audio_backend(_get_env_text('NOISE_SURVEY_AUDIO_BACKEND', 'vlc'))
# Length of one browser-playback chunk, and how long a refreshed or closed tab keeps its
# session (data copies, VLC, workers) before the server releases it.
AUDIO_CLIP_SECONDS = 60.0


def _env_seconds(name, default):
    try:
        return max(0.0, float(_get_env_text(name, str(default))))
    except ValueError:
        return float(default)


# A session whose browser has been gone this long is released (its data copy, VLC player and
# workers), instead of lingering for Bokeh's 5-minute unused-session lifetime. 0 disables.
STALE_SESSION_RELEASE_SECONDS = _env_seconds('NOISE_SURVEY_STALE_SESSION_RELEASE_SECONDS', 20.0)

# --- Audio anchoring settings ---
AUDIO_ANCHORING_SETTINGS = {
    # Minimum gap (seconds) to consider measurement data disjoint.
    'min_gap_seconds': 300,
    # Multiplier on median sample interval to detect disjoint segments.
    'gap_multiplier': 5,
    # Maximum time delta (hours) to match an audio file to a measurement segment.
    'max_match_hours': 12,
    # Warning threshold (hours) for low-confidence audio-to-segment matches.
    'warning_match_hours': 2,
    # Tolerance for duration vs. segment length comparisons (seconds).
    'duration_tolerance_seconds': 300,
    # Verify/refine proposed anchors by comparing short audio RMS envelopes
    # with the logger broadband series.
    'correlation_enabled': True,
    # Keep the search bounded, but allow for meter/audio clock errors a little
    # beyond five minutes. Job 6461 had a genuine +313 s offset which the old
    # +/-300 s limit missed by 13 seconds.
    'correlation_search_seconds': 600,
    'correlation_window_seconds': 300,
    'correlation_max_windows': 3,
    'correlation_min_score': 0.80,
    'correlation_max_lag_spread_seconds': 2,
    # Sub-second adjustments are more likely to be bin-edge effects than a
    # real clock error. Keep them as QA metadata without shifting playback.
    'correlation_min_apply_seconds': 2,
}

# Automatic clock alignment between different monitoring positions. This is
# deliberately conservative: nearby meters can still record substantially
# different sound, so offsets are only applied when several independent
# high-information windows agree closely.
METER_ALIGNMENT_SETTINGS = {
    'enabled': True,
    'search_seconds': 300,
    'window_seconds': 600,
    'max_windows': 8,
    'candidate_step_seconds': 300,
    'min_overlap_seconds': 1800,
    'min_window_score': 0.55,
    'min_window_margin': 0.03,
    'min_accepted_windows': 3,
    'min_median_score': 0.70,
    'max_lag_spread_seconds': 2.0,
    'max_drift_seconds': 2.0,
}

# --- New Data Source Configuration ---
# A list of dictionaries, where each dictionary defines a data source file.
DEFAULT_DATA_SOURCES = _load_default_data_sources()
# Configuration dictionary (for backward compatibility)
CONFIG = {
    'chart_settings': CHART_SETTINGS,
    'visualization': VISUALIZATION_SETTINGS,
    'processing': PROCESSING_SETTINGS,
    'ui_layout': UI_LAYOUT_SETTINGS,
    # Avoid putting DEFAULT_DATA_SOURCES in here unless absolutely necessary
    # for old code. It's better managed separately.
}
