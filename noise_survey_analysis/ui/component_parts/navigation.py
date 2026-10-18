"""Navigation components extracted without changing Bokeh wiring."""

import numpy as np
import pandas as pd
from typing import Any, Dict, Optional
from noise_survey_analysis.core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS
from bokeh.models import (
    ColumnDataSource,
    CustomJSTickFormatter,
    DatetimeTicker,
    Range1d,
    RangeTool,
    Span,
)
from bokeh.layouts import column
from bokeh.plotting import figure

from .shared import logger
from .charts import TimeSeriesComponent


class RangeSelectorComponent:
    """
    A component that provides a smaller overview chart with a RangeTool
    to control the x-range of an attached main time series chart.
    """
    def __init__(self, 
                 attached_timeseries_component: TimeSeriesComponent, 
                 chart_settings: Optional[Dict[str, Any]] = None):
        """
        Initializes the RangeSelectorComponent.

        Args:
            attached_timeseries_component (TimeSeriesComponent): The main time series component
                whose x-range will be controlled by this selector.
            chart_settings (Optional[Dict[str, Any]]): Custom settings for the selector.
        """
        if not isinstance(attached_timeseries_component, TimeSeriesComponent):
            raise ValueError("RangeSelectorComponent requires a valid TimeSeriesComponent instance.")

        self.name_id = "RangeSelector"
        self.settings = CHART_SETTINGS
        
        self.attached_timeseries_component = attached_timeseries_component
        self.source: ColumnDataSource = self._attach_to_timeseries(self.attached_timeseries_component)
        self.figure: figure = self._create_selector_figure(self.source)
        
        #interactive components
        self.tap_lines = Span(location=0, dimension='height', line_color='red', line_width=1, name=f"click_line_{self.name_id}")
        self.hover_line = Span(location=0, dimension='height', line_color='grey', line_width=1, line_dash='dashed', name=f"hoverline_{self.name_id}")
        self.figure.add_layout(self.tap_lines)
        self.figure.add_layout(self.hover_line)
    

    def _attach_to_timeseries(self, attached_timeseries_component: TimeSeriesComponent):
        """
        Attaches the range selector to a specific time series component.

        Args:
            attached_timeseries_component (TimeSeriesComponent): The time series component
                to which the range selector will be attached.
        """
        self.attached_chart_figure: figure = attached_timeseries_component.figure
        # The range selector uses the same data source as the main time series chart
        # or a specific overview DataFrame if the main chart switches between log/overview.
        # For simplicity here, we'll assume the attached component's source is suitable
        # or that it has a way to provide an overview_totals DataFrame.
        
        
        source = None
        if attached_timeseries_component.overview_source.data:
            overview_df = attached_timeseries_component.overview_source.data.copy()
            #overview_df['Datetime'] = overview_df['Datetime'].astype(np.int64) // 10**6 #convert to ms
            source = ColumnDataSource(overview_df)
            logger.debug(f"RangeSelector for '{attached_timeseries_component.position_name}' using its overview_totals.")
        elif attached_timeseries_component.log_source.data:
            log_df = attached_timeseries_component.log_source.data.copy()
            #log_df['Datetime'] = log_df['Datetime'].astype(np.int64) // 10**6 #convert to ms
            source = ColumnDataSource(log_df)
            logger.debug(f"RangeSelector for '{attached_timeseries_component.position_name}' using its log_totals.")
        else:
            logger.warning(f"No suitable data source found for RangeSelector attached to '{attached_timeseries_component.position_name}'. Selector will be empty.")
            # Create an empty source to prevent errors, figure will be blank
            source = ColumnDataSource(data={'Datetime': [], 'LAeq': []}) 

        return source
        
    

    def _create_selector_figure(self, source: ColumnDataSource) -> figure:
        x_start, x_end = None, None
        # Check if Datetime data exists and is not empty
        if 'Datetime' in source.data and len(source.data['Datetime']) > 0:
            # Convert to NumPy array for easier min/max if it's a list
            datetime_array = np.array(source.data['Datetime'])
            x_start = datetime_array.min()
            x_end = datetime_array.max()
            if x_start == x_end : # If only one data point or all same time
                x_end = x_start + 60000 # Default to 1 minute range
        else: # No data or empty Datetime
            now_ms = pd.Timestamp.now().value // 10**6 # Current time in ms
            x_start = now_ms - 3600000 # Default to 1 hour ago
            x_end = now_ms
        
        x_range_obj = Range1d(start=x_start, end=x_end)

        select_figure = figure(
            title="Drag handles to select time range",
            height=self.settings['range_selector_height'],
            width=self.settings['range_selector_width'],
            x_axis_type="datetime",
            x_range=x_range_obj, # Use the robustly created Range1d
            y_axis_type=None,
            tools="",
            toolbar_location=None,
            background_fill_color = "#efefef",
            name=self.name_id
        )

        # Metrics plotting also needs to be robust to empty source
        metrics_to_plot = []
        if 'Datetime' in source.data and len(source.data['Datetime']) > 0:
            # Check for other columns that are list-like and have matching length
            metrics = [
                col for col in source.data 
                if col != 'Datetime' and col != 'index' and 
                isinstance(source.data[col], (list, np.ndarray, pd.Series)) and 
                len(source.data[col]) == len(source.data['Datetime'])
            ]
            if not metrics:
                 logger.warning("No plottable metrics found in source for range selector.")
            else:
                 metrics_to_plot = metrics[:4] 

        colors = VISUALIZATION_SETTINGS['line_colors']
        for i, metric in enumerate(metrics_to_plot):
            color = colors.get(metric, "#cccccc") 
            select_figure.line('Datetime', metric, source=source, line_width=1, color=color, alpha=0.6)

        self.range_tool = RangeTool(x_range=self.attached_chart_figure.x_range)
        self.range_tool.overlay.fill_color = "navy"
        self.range_tool.overlay.fill_alpha = 0.2
        select_figure.add_tools(self.range_tool)

        select_figure.xaxis.formatter = CustomJSTickFormatter(code="""
            const d = new Date(tick);
            const weekday = d.toLocaleDateString(undefined, { weekday: 'short' });
            const date = d.toLocaleDateString(undefined, { day: '2-digit', month: '2-digit', year: '2-digit' });
            const time = d.toLocaleTimeString(undefined, { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
            return `${weekday} ${date} ${time}`;
        """)
        select_figure.xaxis.ticker = DatetimeTicker(desired_num_ticks=8)
        select_figure.grid.grid_line_color = None
        select_figure.yaxis.visible = False

        return select_figure

    def layout(self) -> figure:
        """
        Returns the Bokeh layout object (the figure itself) for this component.
        """
        return column(
            self.figure,
            name=f"{self.name_id}_component"
        ) #in a column for consistency with spectrogram
