"""Compatibility imports for the feature-specific Bokeh UI components.

Implementations live in component_parts; existing dashboard and external imports
continue to use this module. Bokeh callback bodies are kept in their features.
"""

# Preserve the names historically imported from this compatibility module.
# Implementations in component_parts use only their own narrow dependencies.
import logging
import pandas as pd
import numpy as np
import pytz
from typing import Optional, Dict, Any, List

from bokeh.plotting import figure
from bokeh.models import (
    ColumnDataSource,
    DatetimeTickFormatter,
    DatetimeTicker,
    FixedTicker,
    CustomJSTickFormatter,
    FactorRange,
    Range1d,
    LabelSet,
    HoverTool,
    NumeralTickFormatter,

    RangeTool,
    Span,
    Label,
    CustomJS,
    Tap,
    Toggle,
    Spinner,
    Slider,
    Button,
    Dropdown,
    Select,
    CheckboxGroup,
    ColorBar,
    ColorPicker,
    DataTable,
    NumberFormatter,
    Div,
    HTMLTemplateFormatter,
    LinearColorMapper,
    TableColumn,
    TextAreaInput,
    PanTool,
    BoxSelectTool,
    Tabs,
    TabPanel,
)
from bokeh.layouts import column, Row, Column
from bokeh.palettes import Category10


from noise_survey_analysis.core.config import (
    CHART_SETTINGS,
    VISUALIZATION_SETTINGS,
    UI_LAYOUT_SETTINGS,
)
from noise_survey_analysis.core.data_manager import PositionData
from noise_survey_analysis.core.utils import to_bokeh_ms
from noise_survey_analysis.core.data_processors import GlyphDataProcessor

from noise_survey_analysis.ui.component_parts.shared import (
    SIDE_PANEL_WIDTH,
    _datetime_series_to_bokeh_ms,
    logger,
)
from noise_survey_analysis.ui.component_parts.regions_panel import RegionPanelComponent
from noise_survey_analysis.ui.component_parts.markers_panel import MarkerPanelComponent
from noise_survey_analysis.ui.component_parts.classifications_panel import ClassificationPanelComponent
from noise_survey_analysis.ui.component_parts.side_panel import SidePanelComponent
from noise_survey_analysis.ui.component_parts.charts import (
    TimeSeriesComponent,
    SpectrogramComponent,
)
from noise_survey_analysis.ui.component_parts.controls import ControlsComponent
from noise_survey_analysis.ui.component_parts.navigation import RangeSelectorComponent
from noise_survey_analysis.ui.component_parts.frequency import (
    FrequencyBarComponent,
    ComparisonFrequencyBarComponent,
)
from noise_survey_analysis.ui.component_parts.comparison import ComparisonPanelComponent
from noise_survey_analysis.ui.component_parts.audio import (
    create_audio_controls_for_position,
    create_position_title_and_offsets,
)
from noise_survey_analysis.ui.component_parts.summary import SummaryTableComponent


if __name__ == '__main__':
    # This part is for standalone testing of the component, not for the main Bokeh app
    logging.basicConfig(level=logging.DEBUG)

    # Create dummy PositionData for testing
    dummy_pos_name = "TestSite"
    
    # Dummy Overview Data
    overview_data = {
        'Datetime': pd.to_datetime(['2023-01-01 10:00:00', '2023-01-01 10:05:00', '2023-01-01 10:10:00']),
        'LAeq': [50.1, 52.3, 51.5],
        'LAFmax': [60.5, 65.1, 62.3],
        'LAF10': [55.2, 58.1, 56.0],
        'LAF90': [45.3, 46.8, 46.0]
    }
    dummy_overview_df = pd.DataFrame(overview_data)

    # Dummy Log Data (more granular)
    log_datetimes = pd.date_range(start='2023-01-01 10:00:00', end='2023-01-01 10:10:00', freq='10S')
    log_data = {
        'Datetime': log_datetimes,
        'LAeq': [50 + i*0.1 + (i%3) for i in range(len(log_datetimes))],
        'LAFmax': [60 + i*0.2 - (i%2) for i in range(len(log_datetimes))],
        # LAF10 and LAF90 are less common in raw logs, often calculated over periods
    }
    dummy_log_df = pd.DataFrame(log_data)

    class DummyPositionData:
        def __init__(self, name):
            self.name = name
            self.overview_totals = None
            self.log_totals = None
        @property
        def has_overview_totals(self): return self.overview_totals is not None and not self.overview_totals.empty
        @property
        def has_log_totals(self): return self.log_totals is not None and not self.log_totals.empty
            
    test_position_data = DummyPositionData(dummy_pos_name)
    test_position_data.overview_totals = dummy_overview_df
    test_position_data.log_totals = dummy_log_df

    # Test with overview first
    print("\n--- Testing TimeSeriesComponent with Overview Data ---")
    ts_component_overview = TimeSeriesComponent(test_position_data, initial_display_mode='overview')
    
    # Test switching to log data
    print("\n--- Switching TimeSeriesComponent to Log Data ---")
    ts_component_overview.switch_data_mode('log')
    # At this point, ts_component_overview.figure should now show log data
    # You would typically add this to a Bokeh document to view it:
    # from bokeh.io import show
    # show(ts_component_overview.layout())

    # Test initializing directly with log data
    print("\n--- Testing TimeSeriesComponent with Log Data Initially ---")
    ts_component_log = TimeSeriesComponent(test_position_data, initial_display_mode='log')
    # show(ts_component_log.layout())

    # Test fallback if preferred mode is unavailable
    test_position_data_log_only = DummyPositionData("LogOnlySite")
    test_position_data_log_only.log_totals = dummy_log_df
    print("\n--- Testing Fallback (Overview requested, only Log available) ---")
    ts_fallback = TimeSeriesComponent(test_position_data_log_only, initial_display_mode='overview')
    assert ts_fallback._current_display_mode == 'log' # Should have fallen back to log
    print(f"Component for LogOnlySite is in '{ts_fallback._current_display_mode}' mode.")


    print("\nComponent testing complete.")
