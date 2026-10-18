"""Charts components extracted without changing Bokeh wiring."""

import numpy as np
from typing import Any, Dict, Optional
from bokeh.models import (
    BoxSelectTool,
    ColorBar,
    ColumnDataSource,
    CustomJS,
    CustomJSTickFormatter,
    DatetimeTicker,
    Div,
    FixedTicker,
    HoverTool,
    Label,
    LinearColorMapper,
    PanTool,
    Range1d,
    Span,
)
from noise_survey_analysis.core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS
from noise_survey_analysis.core.data_manager import PositionData
from bokeh.layouts import column
from bokeh.plotting import figure

from .shared import _datetime_series_to_bokeh_ms, logger


class TimeSeriesComponent:
    """
    A self-contained Time Series chart component for displaying broadband noise data.
    It can display either overview/summary data or log data for a given position.
    """
    def __init__(self, position_data_obj, initial_display_mode: str = 'log'):
        """
        Initializes the component.

        Args:
            position_data_obj: A PositionData object containing the data for the position.
            initial_display_mode: 'overview' or 'log'. Determines which data to show initially.
        """

        if not isinstance(position_data_obj, PositionData):
            raise ValueError("TimeSeriesComponent requires a valid PositionData object.")

        self.position_name = position_data_obj.name
        self.y_axis_label = getattr(position_data_obj, 'y_axis_label', None) or "Sound Level (dB)"
        self.y_range = getattr(position_data_obj, 'y_range', None)
        self._current_display_mode = initial_display_mode # 'overview' or 'log'
        self.chart_settings = CHART_SETTINGS
        self.name_id = f"{self.position_name}_timeseries"
        self.line_renderers = []
        self.has_log_data = (
            (position_data_obj.log_totals is not None and not position_data_obj.log_totals.empty)
            or bool(getattr(position_data_obj, 'log_file_paths', None))
        )
        
        #generate sources for the two view modes
        if position_data_obj.overview_totals is not None:
            overview_df = position_data_obj.overview_totals.copy()
            overview_df['Datetime'] = _datetime_series_to_bokeh_ms(overview_df['Datetime'])
            self.overview_source: ColumnDataSource = ColumnDataSource(data=overview_df)
        else:
            self.overview_source: ColumnDataSource = ColumnDataSource(data={})
        self.overview_source.name = f"source_{self.position_name}_timeseries_overview"
        
        if position_data_obj.log_totals is not None:
            log_df = position_data_obj.log_totals.copy()
            log_df['Datetime'] = _datetime_series_to_bokeh_ms(log_df['Datetime'])
            self.log_source: ColumnDataSource = ColumnDataSource(data=log_df)
        else:
            self.log_source: ColumnDataSource = ColumnDataSource(data={})
        self.log_source.name = f"source_{self.position_name}_timeseries_log"
        
        # Use overview data for initialization if available, otherwise use log data.
        # This ensures all columns are present for renderer creation.
        if position_data_obj.overview_totals is not None and not position_data_obj.overview_totals.empty:
            initial_source_data = self.overview_source.data
        else:
            initial_source_data = self.log_source.data

        self.source = ColumnDataSource(data=dict(initial_source_data))
        self.source.name = "source_" + self.name_id
        self.figure: figure = self._create_figure()
        self._update_plot_lines() # Add lines based on initial data
        self._configure_figure_formatting()

        #interative components
        self.tap_lines = Span(location=0, dimension='height', line_color='red', line_width=1, name=f"click_line_{self.name_id}")
        self.hover_line = Span(location=0, dimension='height', line_color='grey', line_width=1, line_dash='dashed', name=f"hoverline_{self.name_id}")
        self.label = Label(x=0, y=0, text="", text_font_size='10pt', background_fill_color="white", background_fill_alpha=0.6, text_baseline="top", visible=False, name=f"label_{self.name_id}")

        self.figure.add_layout(self.tap_lines)
        self.figure.add_layout(self.hover_line)
        self.figure.add_layout(self.label)
        self._attach_callbacks()
        
        


        logger.info(f"TimeSeriesComponent initialized for '{self.position_name}' in '{self._current_display_mode}' mode.")


    def _create_figure(self) -> figure:
        """Creates and configures the Bokeh figure for the time series plot."""
        title = f"{self.position_name} - Time History"

        pan_tool = PanTool(dimensions="width")
        box_select_tool = BoxSelectTool(dimensions="width")

        # Common tools for time series charts
        tools = [
            pan_tool,
            box_select_tool,
            "xzoom_in", "xzoom_out", "reset", "xwheel_zoom",
        ]
        
        fig_kwargs = {
            "height": self.chart_settings['low_freq_height'],
            "width": self.chart_settings['low_freq_width'],
            "title": title,
            "x_axis_type": "datetime",
            "x_axis_label": "Time",
            "y_axis_label": self.y_axis_label,
            "tools": tools,
            "active_drag": pan_tool,
            "active_scroll": "xwheel_zoom",
            "name": f"figure_{self.name_id}",
            "min_border_top": 55,
            "min_border_bottom": 50,
        }

        # Set y-range if specified in config
        configured_y_range = self.y_range if self.y_range is not None else self.chart_settings.get('timeseries_y_range')
        if configured_y_range:
            try:
                y_start, y_end = configured_y_range
                fig_kwargs['y_range'] = Range1d(y_start, y_end)
                logger.debug(f"Setting fixed y-range for {self.position_name} to {configured_y_range}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid time-series y-range for {self.position_name}: {configured_y_range}. Using auto-range. Error: {e}")

        p = figure(**fig_kwargs)
        p.toolbar.autohide = True
        p.toolbar.logo = None
                 
        return p

    def _update_plot_lines(self):
        """
        Adds or updates line renderers on the figure based on the current self.source.data.
        Clears existing line renderers first.
        """
        # Clear existing line renderers (important when switching data source)
        self.figure.renderers = [r for r in self.figure.renderers if not hasattr(r.glyph, 'line_color')]
        self.line_renderers = []
        
        colors = VISUALIZATION_SETTINGS['line_colors']
        
        if not self.source.data or 'Datetime' not in self.source.data:
            logger.warning(f"No data or 'Datetime' column in source for {self.position_name}. Cannot plot lines.")
            return
        
        for col in self.source.data.keys():
            if col == 'Datetime' or col == 'index': continue

            color = colors.get(col, "#%06x" % np.random.randint(0, 0xFFFFFF))
            line = self.figure.line(
                x='Datetime',
                y=col,
                source=self.source,
                line_width=self.chart_settings['line_width'],
                color=color,
                legend_label=col,
                name=col
            )
            self.line_renderers.append(line)
        
        # Update figure title based on current mode
        self.figure.title.text = f"{self.position_name} - Time History"

    def _configure_figure_formatting(self):
        """Configures the formatting for the figure."""
        self.figure.xaxis.formatter = CustomJSTickFormatter(args={"fig": self.figure}, code="""
            const d = new Date(tick);
            const xstart = fig.x_range.start;
            const xend = fig.x_range.end;
            const window_ms = (typeof xstart === 'number' && typeof xend === 'number') ? (xend - xstart) : Number.POSITIVE_INFINITY;
            const showSeconds = window_ms <= 15 * 60 * 1000; // show :ss when zoomed within 15 minutes

            const weekdayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
            const weekday = weekdayNames[d.getDay()];
            const dd = String(d.getDate()).padStart(2, '0');
            const mm = String(d.getMonth() + 1).padStart(2, '0');
            const yy = String(d.getFullYear()).slice(-2);
            const hh = String(d.getHours()).padStart(2, '0');
            const min = String(d.getMinutes()).padStart(2, '0');
            const ss = String(d.getSeconds()).padStart(2, '0');
            const base = `${weekday} ${dd}/${mm}/${yy} ${hh}:${min}`;
            return showSeconds ? `${base}:${ss}` : base;
        """)
        self.figure.xaxis.ticker = DatetimeTicker(desired_num_ticks=10) # Fewer ticks might be cleaner
        self.figure.yaxis.axis_label = self.y_axis_label

        self.figure.grid.grid_line_alpha = 0.3  # Set a default grid alpha
        self.figure.ygrid.band_fill_alpha = 0.1
        self.figure.ygrid.band_fill_color = "gray"

        #legend
        self.figure.legend.location = "top_right"
        self.figure.legend.click_policy = "hide"
        self.figure.legend.background_fill_alpha = 0.7

    def _attach_callbacks(self):
        """Creates and attaches all JS callbacks for this specific component."""
        tap_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleTap) {
                window.NoiseSurveyApp.eventHandlers.handleTap(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleTap not defined!');
                }
        """)
        self.figure.js_on_event('tap', tap_js)

        # Double-click event for adding markers
        double_click_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleDoubleClick) {
                window.NoiseSurveyApp.eventHandlers.handleDoubleClick(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleDoubleClick not defined!');
                }
        """)
        self.figure.js_on_event('doubletap', double_click_js)
        
        hover_js = CustomJS(code=f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleChartHover) {{
                window.NoiseSurveyApp.eventHandlers.handleChartHover(cb_data, 'figure_{self.name_id}');
                }}
        """)
        hover_tool = HoverTool(
            tooltips=None, # We use our own custom labels
            mode='vline',
            callback=hover_js,
            #renderers=self.line_renderers,
            name=f"hover_tool_{self.position_name}_timeseries"
        )
        self.figure.add_tools(hover_tool)

        selection_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleRegionBoxSelect) {
                    window.NoiseSurveyApp.eventHandlers.handleRegionBoxSelect(cb_obj);
                } else {
                    console.debug('NoiseSurveyApp.eventHandlers.handleRegionBoxSelect not defined!');
                }
        """)
        self.figure.js_on_event('selectiongeometry', selection_js)

    def layout(self):
        """
        Returns the Bokeh layout object for this component.
        """
        return column(
            self.figure,
            name=f"{self.name_id}_component"
        ) #in a column for consistency with spectrogram


class SpectrogramComponent:
    """
    A self-contained Spectrogram chart component for displaying spectral noise data.
    It can display either overview or log spectral data and switch between parameters.
    """
    def __init__(self, 
                 position_data_obj: PositionData, 
                 position_glyph_data: dict,
                 initial_display_mode: str = 'log', # 'overview' or 'log'
                 initial_param: Optional[str] = 'LZeq'):
        """
        Initializes the SpectrogramComponent.

        Args:
            position_data_obj: The PositionData object for this site.
            processor: An instance of GlyphDataProcessor to prepare data.
            chart_settings: Dictionary of chart settings.
            initial_display_mode: 'overview' or 'log'.
            initial_param: The spectral parameter to display initially (e.g., 'LZeq').
                           If None, uses chart_settings default or first available.
        """
        if not isinstance(position_data_obj, PositionData):
            raise ValueError("SpectrogramComponent requires a valid PositionData object.")
        if not isinstance(position_glyph_data, dict):
            raise ValueError("SpectrogramComponent requires a valid GlyphDataProcessor instance.")

        self.position_name = position_data_obj.name
        self.chart_settings = CHART_SETTINGS
        self._current_display_mode = initial_display_mode 
        self._current_param = initial_param
        self.name_id = f"{self.position_name}_spectrogram"
        
        # Create overview and log sources for reservoir streaming
        self.overview_source: ColumnDataSource = ColumnDataSource(data=dict())
        self.overview_source.name = f"source_{self.position_name}_spectrogram_overview"
        
        self.log_source: ColumnDataSource = ColumnDataSource(data=dict())
        self.log_source.name = f"source_{self.position_name}_spectrogram_log"
        
        #source and figure
        self.source: ColumnDataSource = ColumnDataSource(data=dict()) # Holds the [transposed_matrix]
        self.source.name = "source_" + self.name_id
        self.figure: figure = self._create_empty_figure() # Create a blank figure initially
        self.hover_div: Div = Div(text="<i>Hover over spectrogram for details</i>",
                                  name=f"{self.position_name}_spectrogram_hover_div",
                                  width=self.chart_settings['spectrogram_width'], height=40,
                                  styles={'font-size': '9pt', 'font-weight': 'bold', 'padding-left': '10px', 'text-align': 'center'},
                                  visible=False)
        self.image_glyph = None # Store the image glyph renderer
        self.update_plot(position_glyph_data, self._current_display_mode, self._current_param)

        #interactive components
        self.tap_lines = Span(location=0, dimension='height', line_color='red', line_width=1, name=f"click_line_{self.name_id}")
        self.hover_line = Span(location=0, dimension='height', line_color='grey', line_width=1, line_dash='dashed', name=f"hoverline_{self.name_id}")

        self.figure.add_layout(self.tap_lines)
        self.figure.add_layout(self.hover_line)
        self._attach_callbacks()

        logger.info(f"SpectrogramComponent initialized for '{self.position_name}'. Initial mode: '{self._current_display_mode}', Param: '{self._current_param}'")

    def _create_empty_figure(self) -> figure:
        """Creates a blank Bokeh figure as a placeholder."""
        title = f"{self.position_name} - Spectrogram"
        pan_tool = PanTool(dimensions="width")
        box_select_tool = BoxSelectTool(dimensions="width")

        p = figure(
            title=title,
            x_axis_type="datetime",
            y_axis_type="linear",
            height=self.chart_settings['spectrogram_height'],
            width=self.chart_settings['spectrogram_width'],
            tools=[pan_tool, box_select_tool, "xzoom_in", "xzoom_out", "reset", "xwheel_zoom"],
            active_drag=pan_tool,
            active_scroll=self.chart_settings['active_scroll'],
            name=f"figure_{self.name_id}",
            min_border_top=35,
            min_border_bottom=50,
        )
        p.toolbar.autohide = True
        p.toolbar.logo = None
        p.xaxis.formatter = CustomJSTickFormatter(args={"fig": p}, code="""
            const d = new Date(tick);
            const xstart = fig.x_range.start;
            const xend = fig.x_range.end;
            const window_ms = (typeof xstart === 'number' && typeof xend === 'number') ? (xend - xstart) : Number.POSITIVE_INFINITY;
            const showSeconds = window_ms <= 15 * 60 * 1000; // show :ss when zoomed within 15 minutes

            const weekdayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
            const weekday = weekdayNames[d.getDay()];
            const dd = String(d.getDate()).padStart(2, '0');
            const mm = String(d.getMonth() + 1).padStart(2, '0');
            const yy = String(d.getFullYear()).slice(-2);
            const hh = String(d.getHours()).padStart(2, '0');
            const min = String(d.getMinutes()).padStart(2, '0');
            const ss = String(d.getSeconds()).padStart(2, '0');
            const base = `${weekday} ${dd}/${mm}/${yy} ${hh}:${min}`;
            return showSeconds ? `${base}:${ss}` : base;
        """)
        p.xaxis.ticker = DatetimeTicker(desired_num_ticks=10) # Fewer ticks might be cleaner
        p.yaxis.axis_label = "Frequency (Hz)"
        p.xaxis.axis_label = "Time"
        p.xgrid.visible = False
        p.ygrid.visible = False
        p.visible = False
        return p

    def _update_figure_content(self, prepared_param_data: Dict[str, Any]):
        """Updates the figure with new data (image, axes, colorbar)."""
        param_name = self._current_param or "Unknown Param"
        self.figure.title.text = f"{self.position_name} - Spectrogram"

        # Extract data from prepared_param_data
        initial_data = prepared_param_data['initial_glyph_data']

        times_ms = np.array(prepared_param_data['times_ms'])
        n_freqs = prepared_param_data['n_freqs']
        frequency_labels = np.array(prepared_param_data['frequency_labels'])

        # Re-create numeric frequencies from labels for the tick formatter
        selected_frequencies_numeric = [float(label.split(' ')[0]) for label in frequency_labels]
        freq_indices = np.arange(n_freqs)
        
        # Update image source
        self.source.data = initial_data

        # Update x_range based on the full time range of the data available
        # This ensures the range selector and initial view are correct
        if times_ms.size > 0:
            self.figure.x_range.start = prepared_param_data['min_time']
            self.figure.x_range.end = prepared_param_data['max_time']
            if self.figure.x_range.start == self.figure.x_range.end:
                self.figure.x_range.end += 60000 # Add 1 min for single point
        else:
            self.figure.x_range.start = 0
            self.figure.x_range.end = 60000

        # Apply frequency range cropping from config settings
        min_freq_hz, max_freq_hz = self.chart_settings['spectrogram_freq_range_hz']
        
        # Find the frequency indices that fall within the display range
        visible_freq_indices = []
        visible_freq_labels = {}
        
        for i, freq in enumerate(selected_frequencies_numeric):
            if min_freq_hz <= freq <= max_freq_hz:
                visible_freq_indices.append(i)
                visible_freq_labels[i] = str(int(freq)) if freq >= 10 else f"{freq:.1f}"
        
        # Set y_range to show only the visible frequency range
        if visible_freq_indices:
            self.figure.y_range.start = visible_freq_indices[0] - 0.5
            self.figure.y_range.end = visible_freq_indices[-1] + 0.5
        else:
            # Fallback to full range if no frequencies match
            self.figure.y_range.start = -0.5
            self.figure.y_range.end = n_freqs - 0.5
        
        # Update Y-axis ticks and labels to show only visible frequencies
        self.figure.yaxis.ticker = FixedTicker(ticks=visible_freq_indices)
        self.figure.yaxis.major_label_overrides = visible_freq_labels
        
        # Update or create image glyph
        if self.image_glyph:
            self.figure.renderers.remove(self.image_glyph) # Remove old one
        
        min_val = prepared_param_data.get('min_val', 0)
        max_val = prepared_param_data.get('max_val', 100)
        
        self.image_glyph = self.figure.image(
            image='image', source=self.source,
            x=initial_data['x'][0], 
            y=initial_data['y'][0],
            dw=initial_data['dw'][0], 
            dh=initial_data['dh'][0],
            color_mapper=LinearColorMapper(palette=self.chart_settings['colormap'], 
                                          low=min_val, 
                                          high=max_val,
                                          nan_color='#00000000'), # Transparent NaN
            level="image", 
            name=f"{self.position_name}_{param_name}_image"
        )

        # create color bar
        self.color_bar = ColorBar(
            color_mapper=self.image_glyph.glyph.color_mapper,
            title=f'{param_name} (dB)', 
            location=(0,0), 
            title_standoff=12,
            border_line_color=None, 
            background_fill_alpha=0.7,
            major_label_text_font_size="8pt", 
            title_text_font_size="9pt"
        )
        #self.figure.add_layout(self.color_bar, 'right')
        
        self.figure.visible = True
        self.hover_div.visible = True

    def set_initial_x_range(self, x_range_start, x_range_end):
        """
        Sets the initial x-range of the spectrogram to match a specific range.
        Used to ensure spectrograms don't show padded data in the initial view.
        
        Args:
            x_range_start: Start value for x-range
            x_range_end: End value for x-range
        """
        if hasattr(self, 'figure') and hasattr(self.figure, 'x_range'):
            logger.debug(f"SpectrogramComponent '{self.position_name}': Setting initial x-range to {x_range_start}-{x_range_end}")
            self.figure.x_range.start = x_range_start
            self.figure.x_range.end = x_range_end
    
    def update_plot(self, position_glyph_data, display_mode: str, parameter: str):
        """
        Updates the spectrogram to show data for the specified mode and parameter.
        """
        logger.info(f"SpectrogramComponent '{self.position_name}': Updating to mode='{display_mode}', param='{parameter}'")
        
        mode_data_root = position_glyph_data.get(display_mode)
        if not mode_data_root:
            logger.warning(f"No prepared data for mode '{display_mode}' in {self.position_name}. Attempting to fall back to 'overview'.")
            mode_data_root = position_glyph_data.get('overview') # Attempt fallback
            if not mode_data_root:
                logger.error(f"Fallback to 'overview' also failed. No spectral data available for {self.position_name}.")
                self.figure.visible = False
                self.hover_div.visible = False
                return

        prepared_param_data = mode_data_root.get('prepared_params', {}).get(parameter)
        if not prepared_param_data:
            logger.warning(f"No prepared data for param '{parameter}' in mode '{display_mode}' for {self.position_name}.")
            # Try to fall back to another parameter if available in this mode
            available_params = mode_data_root.get('available_params', [])
            if available_params:
                fallback_param = available_params[0]
                logger.info(f"Falling back to parameter '{fallback_param}' for mode '{display_mode}'.")
                prepared_param_data = mode_data_root.get('prepared_params', {}).get(fallback_param)
                if prepared_param_data:
                    parameter = fallback_param # Update current parameter
                else:
                    self.figure.visible = False
                self.hover_div.visible = False
                return
            else:
                self.figure.visible = False
                self.hover_div.visible = False
                return

        self._current_display_mode = display_mode
        self._current_param = parameter
        self._update_figure_content(prepared_param_data)

    def _attach_callbacks(self):
        """Creates and attaches all JS callbacks for this specific component."""
        tap_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleTap) {
                window.NoiseSurveyApp.eventHandlers.handleTap(cb_obj);
                } else {
                    console.debug('NoiseSurveyApp.eventHandlers.handleTap not defined!');
                }
        """)
        self.figure.js_on_event('tap', tap_js)

        # Double-click event for adding markers
        double_click_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleDoubleClick) {
                window.NoiseSurveyApp.eventHandlers.handleDoubleClick(cb_obj);
                } else {
                    console.debug('NoiseSurveyApp.eventHandlers.handleDoubleClick not defined!');
                }
        """)
        self.figure.js_on_event('doubletap', double_click_js)

        hover_js = CustomJS(code=f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleChartHover) {{
                window.NoiseSurveyApp.eventHandlers.handleChartHover(cb_data, 'figure_{self.name_id}');
                }}
        """)
        hover_tool = HoverTool(
            tooltips=None, # We use our own custom labels
            mode='vline',
            callback=hover_js,
            name=f"hover_tool_{self.name_id}"
        )
        self.figure.add_tools(hover_tool)

        selection_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleRegionBoxSelect) {
                    window.NoiseSurveyApp.eventHandlers.handleRegionBoxSelect(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleRegionBoxSelect not defined!');
                }
        """)
        self.figure.js_on_event('selectiongeometry', selection_js)

    def layout(self):
        """Returns the Bokeh layout object for this component."""
        # The figure might be initially hidden if no data, visibility managed by update_plot
        return column(
            self.figure,
            self.hover_div,
            name=f"{self.name_id}_component"
        )
