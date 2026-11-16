"""Navigation components extracted without changing Bokeh wiring."""

import numpy as np
import pandas as pd
from typing import Any, Dict, Optional
from noise_survey_analysis.core.config import (
    CHART_SETTINGS,
    FRAME_BORDER_LEFT,
    FRAME_BORDER_RIGHT,
    VISUALIZATION_SETTINGS,
)
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
from .charts import TimeSeriesComponent, build_time_axis_formatter, AXIS_FONT_SIZE
from bokeh.models import NoOverlap

MAX_TRACE_POINTS = 2000


def decimate_minmax(x, y, max_points: int = MAX_TRACE_POINTS):
    """Min/max decimation: keeps each bucket's lowest and highest finite sample (in time order) so
    peaks survive. Returns (x, y) arrays with at most ``max_points`` points."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    finite = np.isfinite(x) & np.isfinite(y)
    x, y = x[finite], y[finite]
    if x.size <= max_points:
        return x, y
    buckets = max(1, max_points // 2)
    edges = np.linspace(0, x.size, buckets + 1).astype(int)
    xs, ys = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        if hi <= lo:
            continue
        seg = y[lo:hi]
        i_min, i_max = lo + int(np.argmin(seg)), lo + int(np.argmax(seg))
        for idx in sorted({i_min, i_max}):
            xs.append(x[idx])
            ys.append(y[idx])
    return np.asarray(xs), np.asarray(ys)


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
            title=None,
            height=self.settings['range_selector_height'],
            width=self.settings['range_selector_width'],
            x_axis_type="datetime",
            x_range=x_range_obj, # Use the robustly created Range1d
            y_axis_type=None,
            tools="",
            toolbar_location=None,
            background_fill_color = "#efefef",
            min_border_left=FRAME_BORDER_LEFT,
            min_border_right=FRAME_BORDER_RIGHT,
            min_border_top=2,
            min_border_bottom=2,
            name=self.name_id
        )

        # One decimated LAeq trace on an explicit y range, so the strip is never empty or scaled by
        # a stray outlier. Falls back to the first numeric column when there is no LAeq.
        trace_x, trace_y = np.array([]), np.array([])
        trace_name = None
        if 'Datetime' in source.data and len(source.data['Datetime']) > 0:
            for candidate in ('LAeq', 'LAeq_dt', 'LAFmax', 'LAFmax_dt'):
                if candidate in source.data and len(source.data[candidate]) == len(source.data['Datetime']):
                    trace_name = candidate
                    break
            if trace_name is None:
                for col in source.data:
                    if col in ('Datetime', 'index'):
                        continue
                    values = source.data[col]
                    if isinstance(values, (list, np.ndarray, pd.Series)) and len(values) == len(source.data['Datetime']):
                        trace_name = col
                        break
        if trace_name is not None:
            try:
                trace_x, trace_y = decimate_minmax(source.data['Datetime'], source.data[trace_name])
            except (TypeError, ValueError) as exc:
                logger.warning(f"Range selector trace could not be built: {exc}")
        if trace_y.size:
            y_lo, y_hi = float(np.nanmin(trace_y)), float(np.nanmax(trace_y))
            pad = max(2.0, (y_hi - y_lo) * 0.1)
            select_figure.y_range = Range1d(y_lo - pad, y_hi + pad)
        else:
            select_figure.y_range = Range1d(0, 100)
        self.trace_source = ColumnDataSource(data={'Datetime': trace_x, 'level': trace_y}, name='range_selector_trace_source')
        colors = VISUALIZATION_SETTINGS['line_colors']
        select_figure.line('Datetime', 'level', source=self.trace_source, line_width=1,
                           color=colors.get(trace_name, '#2563eb'), alpha=0.8)

        self.range_tool = RangeTool(x_range=self.attached_chart_figure.x_range)
        self.range_tool.overlay.fill_color = "navy"
        self.range_tool.overlay.fill_alpha = 0.2
        select_figure.add_tools(self.range_tool)

        select_figure.xaxis.formatter = build_time_axis_formatter(select_figure)
        select_figure.xaxis.ticker = DatetimeTicker(desired_num_ticks=8)
        select_figure.xaxis.major_label_policy = NoOverlap()
        select_figure.xaxis.major_label_text_font_size = AXIS_FONT_SIZE
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
