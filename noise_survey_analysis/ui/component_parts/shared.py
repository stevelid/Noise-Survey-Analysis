"""Small shared dependencies for the feature-specific Bokeh components."""

import logging

import numpy as np

from noise_survey_analysis.core.config import UI_LAYOUT_SETTINGS
from noise_survey_analysis.core.utils import to_bokeh_ms

# Retain the original logger name so existing log filters keep working.
logger = logging.getLogger('noise_survey_analysis.ui.components')
SIDE_PANEL_WIDTH = UI_LAYOUT_SETTINGS.get('side_panel_width', 320)


def _datetime_series_to_bokeh_ms(values) -> np.ndarray:
    """Convert datetimes to Bokeh datetime milliseconds independent of numpy unit."""
    return to_bokeh_ms(values)
