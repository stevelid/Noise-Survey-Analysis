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
    Button,
    Select,
    CheckboxGroup,
    ColorBar,
    Div,
    LinearColorMapper,
    PanTool,
    BoxSelectTool,
)
from bokeh.layouts import column, Row, Column
from bokeh.palettes import Category10

from matplotlib.figure import Figure

from noise_survey_analysis.core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS
from noise_survey_analysis.core.data_manager import PositionData
from noise_survey_analysis.core.data_processors import GlyphDataProcessor


logger = logging.getLogger(__name__)


def create_region_panel_div() -> Div:
    """Create the static container for the region analysis panel."""
    return Div(
        text="<div class='region-panel-empty'>No regions defined.</div>",
        width=320,
        height=500,
        name="region_panel_div",
        css_classes=["region-panel-container"], # Use a list of strings
        styles={
            "border": "1px solid #ccc",
            "padding": "8px",
            "overflow-y": "auto",
            "background-color": "#fafafa"
        }
    )

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
        self._current_display_mode = initial_display_mode # 'overview' or 'log'
        self.chart_settings = CHART_SETTINGS
        self.name_id = f"{self.position_name}_timeseries"
        self.line_renderers = []
        self.has_log_data = position_data_obj.log_totals is not None and not position_data_obj.log_totals.empty
        
        #generate sources for the two view modes
        if position_data_obj.overview_totals is not None:
            overview_df = position_data_obj.overview_totals.copy()
            overview_df['Datetime'] = overview_df['Datetime'].values.astype(np.int64) // 10**6 #convert to ms
            self.overview_source: ColumnDataSource = ColumnDataSource(data=overview_df)
        else:
            self.overview_source: ColumnDataSource = ColumnDataSource(data={})
        
        if position_data_obj.log_totals is not None:
            log_df = position_data_obj.log_totals.copy()
            log_df['Datetime'] = log_df['Datetime'].values.astype(np.int64) // 10**6 #convert to ms
            self.log_source: ColumnDataSource = ColumnDataSource(data=log_df)
        else:
            self.log_source: ColumnDataSource = ColumnDataSource(data={})
        
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
        self.label = Label(x=0, y=0, text="", text_font_size='10pt', background_fill_color="white", background_fill_alpha=0.6, text_baseline="middle", visible=False, name=f"label_{self.name_id}")
        
        # Marker lines - initially empty list, will be populated dynamically
        self.marker_lines = []  # List of Span objects for markers

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
            "y_axis_label": "Sound Level (dB)",
            "tools": tools,
            "active_drag": pan_tool,
            "active_scroll": "xwheel_zoom",
            "name": f"figure_{self.name_id}"
        }

        # Set y-range if specified in config
        if self.chart_settings.get('timeseries_y_range'):
            try:
                y_start, y_end = self.chart_settings['timeseries_y_range']
                fig_kwargs['y_range'] = Range1d(y_start, y_end)
                logger.debug(f"Setting fixed y-range for {self.position_name} to {self.chart_settings['timeseries_y_range']}")
            except (ValueError, TypeError) as e:
                logger.warning(f"Invalid 'timeseries_y_range' format: {self.chart_settings['timeseries_y_range']}. Using auto-range. Error: {e}")

        p = figure(**fig_kwargs)
                
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
        self.figure.yaxis.axis_label = "Sound Level (dB)"

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
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleTap) {
                window.NoiseSurveyApp.eventHandlers.handleTap(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleTap not defined!');
                }
        """)
        self.figure.js_on_event('tap', tap_js)

        # Double-click event for adding markers
        double_click_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleDoubleClick) {
                window.NoiseSurveyApp.eventHandlers.handleDoubleClick(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleDoubleClick not defined!');
                }
        """)
        self.figure.js_on_event('doubletap', double_click_js)
        
        hover_js = CustomJS(code=f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleChartHover) {{
                window.NoiseSurveyApp.eventHandlers.handleChartHover(cb_data, 'figure_{self.name_id}');
                }} else {{
                    console.error('NoiseSurveyApp.eventHandlers.handleChartHover not defined!');
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
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleRegionBoxSelect) {
                    window.NoiseSurveyApp.eventHandlers.handleRegionBoxSelect(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleRegionBoxSelect not defined!');
                }
        """)
        self.figure.js_on_event('selectiongeometry', selection_js)

    def layout(self):
        """
        Returns the Bokeh layout object for this component.
        """
        return column(self.figure, name=f"{self.name_id}_component") #in a column for consistency with spectrogram


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
        
        #source and figure
        self.source: ColumnDataSource = ColumnDataSource(data=dict()) # Holds the [transposed_matrix]
        self.source.name = "source_" + self.name_id
        self.figure: Figure = self._create_empty_figure() # Create a blank figure initially
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
        
        # Marker lines - initially empty list, will be populated dynamically
        self.marker_lines = []  # List of Span objects for markers

        self.figure.add_layout(self.tap_lines)
        self.figure.add_layout(self.hover_line)
        self._attach_callbacks()

        logger.info(f"SpectrogramComponent initialized for '{self.position_name}'. Initial mode: '{self._current_display_mode}', Param: '{self._current_param}'")

    def _create_empty_figure(self) -> Figure:
        """Creates a blank Bokeh figure as a placeholder."""
        title = f"{self.position_name} - Spectrogram"
        pan_tool = PanTool(dimensions="width")
        box_select_tool = BoxSelectTool(dimensions="width")

        p = figure(
            title=title,
            x_axis_type="datetime",
            y_axis_type="linear",
            height=self.chart_settings['spectrogram_height'],
            width=self.chart_settings['spectrogram_width'], # Use width for initial sizing
            tools=[pan_tool, box_select_tool, "xzoom_in", "xzoom_out", "reset", "xwheel_zoom"],
            active_drag=pan_tool,
            active_scroll=self.chart_settings['active_scroll'],
            name=f"figure_{self.name_id}"
        )
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
        #p.xaxis.axis_label = "Time"
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
        self.figure.yaxis.ticker = visible_freq_indices
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
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleTap) {
                window.NoiseSurveyApp.eventHandlers.handleTap(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleTap not defined!');
                }
        """)
        self.figure.js_on_event('tap', tap_js)

        # Double-click event for adding markers
        double_click_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleDoubleClick) {
                window.NoiseSurveyApp.eventHandlers.handleDoubleClick(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleDoubleClick not defined!');
                }
        """)
        self.figure.js_on_event('doubletap', double_click_js)

        hover_js = CustomJS(code=f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleChartHover) {{
                window.NoiseSurveyApp.eventHandlers.handleChartHover(cb_data, 'figure_{self.name_id}');
                }} else {{
                    console.error('NoiseSurveyApp.eventHandlers.handleChartHover not defined!');
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
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleRegionBoxSelect) {
                    window.NoiseSurveyApp.eventHandlers.handleRegionBoxSelect(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleRegionBoxSelect not defined!');
                }
        """)
        self.figure.js_on_event('selectiongeometry', selection_js)

    def layout(self):
        """Returns the Bokeh layout object for this component."""
        # The figure might be initially hidden if no data, visibility managed by update_plot
        return column(self.figure, self.hover_div, name=f"{self.name_id}_component")


class ControlsComponent:
    """A component that provides global controls for the dashboard."""
    def __init__(self, available_params: List[str]): # Would take DataManager to access all positions' info
        
        self.available_params = available_params
        self.visibility_checkboxes: Dict[str, list] = {} # Key: position_name, Value: list of (chart_name, checkbox_widget) tuples
        self.position_order: List[str] = []  # Track order of positions as checkboxes are added
        self.visibility_layout = None
        
        self.view_toggle = self.add_view_type_selector()
        self.hover_toggle = self.add_hover_toggle()
        self.clear_markers_button = self.add_clear_markers_button()
        self.param_select = self.add_parameter_selector(available_params)
        self.start_comparison_button = self.add_start_comparison_button()

        logger.info("ControlsComponent initialized.")


    def add_view_type_selector(self):
        toggle = Toggle(
            label="Log View Enabled", 
            button_type="primary", 
            width=150,
            name="global_view_toggle",
            active=True
        )
        
        toggle.js_on_change("active", CustomJS(args={"toggle_widget": toggle}, code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleViewToggle) {
                window.NoiseSurveyApp.eventHandlers.handleViewToggle(cb_obj.active, toggle_widget); // Pass the toggle widget itself
            } else {
                console.error('window.NoiseSurveyApp.eventHandlers.handleViewToggle function not found!');
            }"""))
        return toggle

    def add_hover_toggle(self):
        toggle = Toggle(
            label="Hover Enabled", 
            button_type="success", 
            width=130,
            name="global_hover_toggle",
            active=True
        )
        
        toggle.js_on_change("active", CustomJS(args={"toggle_widget": toggle}, code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleHoverToggle) {
                window.NoiseSurveyApp.eventHandlers.handleHoverToggle(cb_obj.active, toggle_widget); // Pass the toggle widget itself
            } else {
                console.error('window.NoiseSurveyApp.eventHandlers.handleHoverToggle function not found!');
            }"""))
        return toggle
    
    def add_clear_markers_button(self):
        button = Button(
            label="Clear All Markers", 
            button_type="warning", 
            width=140,
            name="clear_markers_button"
        )
        
        button.js_on_event("button_click", CustomJS(code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.clearAllMarkers) {
                window.NoiseSurveyApp.eventHandlers.clearAllMarkers();
            } else {
                console.error('window.NoiseSurveyApp.eventHandlers.clearAllMarkers function not found!');
            }"""))
        return button

    def add_parameter_selector(self, available_params: List[str]):
        select = Select(
            options=available_params,
            value="LZeq",
            width=150,
            name="global_parameter_selector"
        )
        select.js_on_change("value", CustomJS(args={"select_widget": select}, code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleParameterChange) {
                window.NoiseSurveyApp.eventHandlers.handleParameterChange(cb_obj.value, select_widget); // Pass the select widget itself
            } else {
                console.error('window.NoiseSurveyApp.eventHandlers.handleParameterChange function not found!');
            }""")) #active for overview, inactive for log
        return select

    def add_start_comparison_button(self):
        button = Button(
            label="Start Comparison",
            button_type="primary",
            width=160,
            name="start_comparison_button"
        )
        button.js_on_event("button_click", CustomJS(code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleStartComparison) {
                window.NoiseSurveyApp.eventHandlers.handleStartComparison();
            } else {
                console.error('NoiseSurveyApp.eventHandlers.handleStartComparison not defined!');
            }"""))
        return button

    def add_visibility_checkbox(self, chart_name: str, chart_label: str, initial_state: bool = True):
        """
        Adds a visibility checkbox for a specific chart.
        Called by DashBuilder after chart components are created.
        """
        # The chart_name is expected to be in the format 'figure_Position_chart-type', e.g., 'figure_East_timeseries'
        try:
            position_name = chart_name.split('_')[1]
        except IndexError:
            logger.warning(f"Could not determine position from chart name: '{chart_name}'. Grouping as 'unknown'.")
            position_name = "unknown"

        checkbox = CheckboxGroup(labels=[chart_label], active=[0] if initial_state else [], width=150, name=f"visibility_{chart_name}")
        
        if position_name not in self.visibility_checkboxes:
            self.visibility_checkboxes[position_name] = []
            # Track the order positions are added (preserves config file order)
            if position_name not in self.position_order:
                self.position_order.append(position_name)
        self.visibility_checkboxes[position_name].append((chart_name, checkbox))

        # --- Attach JS Callback ---
        checkbox_js_callback = CustomJS(args=dict(chart_name=chart_name),code=f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleVisibilityChange) {{
                window.NoiseSurveyApp.eventHandlers.handleVisibilityChange(cb_obj, chart_name);
                }} else {{
                    console.error('NoiseSurveyApp.eventHandlers.handleVisibilityChange not defined!');
                }}
            """)
        checkbox.js_on_change("active", checkbox_js_callback)
        
    def _build_visibility_layout(self):
        """Builds the layout for visibility checkboxes, grouping them by position into a 2xP grid."""
        if not self.visibility_checkboxes:
            self.visibility_layout = Div(text="") # Empty div if no checkboxes
            return

        position_columns = []
        # Use the order positions were added (preserves config file order)
        for position_name in self.position_order:
            checkboxes = self.visibility_checkboxes[position_name]
            # Sort checkboxes to ensure TS is above Spec, assuming consistent naming
            # 'timeseries' comes before 'spectrogram' alphabetically.
            sorted_checkboxes = sorted(checkboxes, key=lambda item: item[0])
            checkbox_widgets = [widget for name, widget in sorted_checkboxes]
            
            # Create a vertical column for each position's checkboxes
            position_column = Column(*checkbox_widgets, name=f"visibility_col_{position_name}")
            position_columns.append(position_column)
        
        # Arrange the vertical columns in a horizontal row that can wrap on smaller screens
        self.visibility_layout = Row(
            *position_columns,
            name="visibility_controls_row",
            sizing_mode="scale_width",
            styles={
                "flex-wrap": "wrap",
                "gap": "8px"
            }
        )


    def layout(self):
        # Ensure visibility layout is built before returning the main layout
        if self.visibility_layout is None:
            self._build_visibility_layout()

        # Main controls row (parameter select, view toggle, hover toggle, clear markers button, comparison button)
        main_controls_row = Row(
            self.param_select,
            self.view_toggle,
            self.hover_toggle,
            self.clear_markers_button,
            self.start_comparison_button,
            sizing_mode="scale_width", # Or "stretch_width"
            name="main_controls_row",
            styles={
                "flex-wrap": "wrap",
                "gap": "8px"
            }
        )

        # Return a column containing the main controls stacked above the visibility controls
        return column(
            main_controls_row,
            self.visibility_layout,
            name="controls_component_layout",
            sizing_mode="scale_width",
            styles={
                "gap": "12px"
            }
        )

    def get_all_visibility_checkboxes(self) -> list:
        """Returns a flat list of all checkbox widgets."""
        all_checkboxes = []
        for position_checkboxes in self.visibility_checkboxes.values():
            all_checkboxes.extend([widget for name, widget in position_checkboxes])
        return all_checkboxes
        

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
        self.figure: Figure = self._create_selector_figure(self.source)
        
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
        self.attached_chart_figure: Figure = attached_timeseries_component.figure
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
        
    

    def _create_selector_figure(self, source: ColumnDataSource) -> Figure:
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

        range_tool = RangeTool(x_range=self.attached_chart_figure.x_range)
        range_tool.overlay.fill_color = "navy"
        range_tool.overlay.fill_alpha = 0.2
        select_figure.add_tools(range_tool)

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

    def layout(self) -> Figure:
        """
        Returns the Bokeh layout object (the figure itself) for this component.
        """
        return column(self.figure, name=f"{self.name_id}_component") #in a column for consistency with spectrogram

class FrequencyBarComponent:
    """
    A self-contained component for displaying frequency levels as a bar chart
    for a specific time slice, typically updated via JavaScript interactions
    from other components like a spectrogram. Includes a table below the chart
    to allow for easy data copying.
    """
    def __init__(self, chart_settings: Optional[Dict[str, Any]] = None):
        """
        Initializes the FrequencyBarComponent.

        Args:
            chart_settings (Optional[Dict[str, Any]]): A dictionary of settings
                to override the default appearance and behavior of the chart.
        """
        self.settings = CHART_SETTINGS
        
        # Initial empty data structure. JavaScript will populate this.
        # 'frequency_labels' should be strings (e.g., "63 Hz", "1 kHz")
        # 'levels' should be numeric dB values.
        initial_data = {
            'frequency_labels': ['31.5 Hz', '40 Hz', '50 Hz', '63 Hz', '80 Hz', '100 Hz', '125 Hz', '160 Hz', '200 Hz', 
            '250 Hz', '315 Hz', '400 Hz', '500 Hz', '630 Hz', '800 Hz', '1000 Hz', '1250 Hz', '1600 Hz', '2000 Hz'], # More complete example initial factors
            'levels': [0] * 19 # Match the number of labels
        } 
        
        self.source: ColumnDataSource = ColumnDataSource(data=initial_data, name="frequency_bar_source")
        # The FactorRange is crucial for categorical x-axis. It must be initialized with
        # the factors that will appear on the x-axis. JS will update source.data,
        # and if the factors change, x_range.factors also needs updating.
        self.x_range: FactorRange = FactorRange(factors=initial_data['frequency_labels'])
        
        # Add a Div component to hold the HTML table for copying data
        self.table_div = Div(name="frequency_table_div", width=self.settings.get('frequency_bar_width', 800))
        
        self.figure: Figure = self._create_figure()
        
        # Initialize the table with empty data
        self._update_table(initial_data['levels'], initial_data['frequency_labels'])
        
        logger.info("FrequencyBarComponent initialized.")

    def _create_figure(self) -> Figure:
        """Creates and configures the Bokeh figure for the bar chart."""
        
        p = figure(
            title="Frequency Slice",
            height=self.settings['high_freq_height'],
            width=self.settings['frequency_bar_width'], # Initial width, sizing_mode handles final
            x_range=self.x_range, # Use the FactorRange instance
            x_axis_label='Frequency Band', # Suffix (Hz) implied by labels
            y_axis_label='Level (dB)',
            tools="pan,wheel_zoom,box_zoom,reset,save", # Standard tools
            name="frequency_bar_chart" # For identification
        )

        # Add vertical bars
        p.vbar(
            x='frequency_labels',
            top='levels',
            width=0.8,
            source=self.source,
            fill_color="#6baed6",
            line_color="white",
            legend_label="Level" # Simple legend
        )

        # Add labels above bars to show the level
        labels = LabelSet(
            x='frequency_labels',
            y='levels',
            text='levels',
            level='glyph',
            x_offset=0,
            y_offset=5,
            source=self.source,
            text_align='center',
            text_font_size='8pt',
            text_color='black',
            text_baseline='bottom'
        )
        p.add_layout(labels)

        # Configure y-range
        if not self.settings['auto_y_range']:
            try:
                p.y_range = Range1d(*self.settings['y_range'])
            except Exception as e:
                 logger.warning(f"Invalid y_range configuration for Frequency Bar: {self.settings['y_range']}. Using auto-range. Error: {e}")
        
        p.yaxis.formatter = NumeralTickFormatter(format="0.0") # Format y-axis ticks

        # Add hover tool
        hover = HoverTool(tooltips=[
            ("Frequency", "@frequency_labels"), # @column_name refers to ColumnDataSource columns
            ("Level", "@levels{0.1f} dB")     # Format level to one decimal place
        ])
        p.add_tools(hover)

        # Styling
        p.xaxis.major_label_orientation = 0.8
        p.xaxis.major_label_text_font_size = "8pt" # Smaller for potentially many labels
        p.grid.grid_line_alpha = 0.3
        p.xaxis.axis_label_text_font_size = "10pt"
        p.yaxis.axis_label_text_font_size = "10pt"
        
        # Hide the default legend if only one series, or customize
        p.legend.visible = False 
        # If you had multiple vbar calls for different parameters, you might enable legend:
        # p.legend.location = "top_right"
        # p.legend.click_policy = "hide"

        return p

    def layout(self):
        """
        Returns the Bokeh layout object for this component, including both the chart and table div.
        """
        return column(self.figure, self.table_div)

    def _update_table(self, levels: List[float], labels: List[str]):
        """
        Updates the HTML table with frequency data for copying.
        
        Args:
            levels (List[float]): List of level values to display in the table.
            labels (List[str]): List of frequency band labels to display in the table.
        """
        if not labels or not levels:
            self.table_div.text = "<p>No frequency data available</p>"
            return
        
        table_html = """
        <style>
            .freq-html-table { border-collapse: collapse; width: 100%; font-size: 0.9em; table-layout: fixed; }
            .freq-html-table th, .freq-html-table td { border: 1px solid #ddd; padding: 6px; text-align: center; white-space: nowrap; }
            .freq-html-table th { background-color: #f2f2f2; font-weight: bold; }
        </style>
        <table class="freq-html-table"><tr>"""
        
        # Add header row with frequency labels
        for label in labels:
            table_html += f"<th title=\"{label}\">{label}</th>"
        table_html += "</tr><tr>"
        
        # Add data row with level values
        for level in levels:
            level_num = float(level) if level is not None else float('nan')
            level_text = 'N/A' if np.isnan(level_num) else f"{level_num:.1f}"
            table_html += f"<td>{level_text}</td>"
        table_html += "</tr></table>"
        
        self.table_div.text = table_html
        logger.debug("Frequency table HTML updated.")

    def update_data(self, frequency_labels: List[str], levels: List[float]):
        """
        Public method to update the data in the bar chart and the associated table.
        This would typically be called by JavaScript via a CustomJS callback
        or by Python code if interactions are Python-driven.

        Args:
            frequency_labels (List[str]): New list of frequency band labels.
            levels (List[float]): Corresponding list of level values.
        """
        if len(frequency_labels) != len(levels):
            logger.error("Frequency labels and levels must have the same length for update.")
            return

        self.source.data = {'frequency_labels': frequency_labels, 'levels': levels}
        self.x_range.factors = frequency_labels # CRITICAL: Update factors for categorical axis
        
        # Update the table with the new data
        self._update_table(levels, frequency_labels)
        
        logger.debug(f"FrequencyBarComponent data updated. Factors: {frequency_labels[:5]}..., Levels: {levels[:5]}...")


class ComparisonPanelComponent:
    """Container for comparison mode controls and placeholders."""

    def __init__(self, position_ids: Optional[List[str]] = None):
        self.position_ids: List[str] = list(position_ids or [])

        instructions_html = (
            "<div class='comparison-panel-instructions'>"
            "<h3>Comparison Mode</h3>"
            "<p>Select the positions you want to include. Drag on a chart to choose a time slice.</p>"
            "</div>"
        )
        self.instructions_div = Div(
            text=instructions_html,
            width=320,
            name="comparison_panel_instructions",
            styles={"margin-bottom": "8px"}
        )

        labels = [str(position_id) for position_id in self.position_ids]
        self.position_selector = CheckboxGroup(
            labels=labels,
            active=list(range(len(labels))),
            width=300,
            name="comparison_position_selector"
        )
        self.position_selector.js_on_change(
            "active",
            CustomJS(
                args={"positionIds": self.position_ids},
                code="""
                    if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleComparisonPositionsChange) {
                        const selected = cb_obj.active
                            .map(index => positionIds[index])
                            .filter(id => id !== undefined && id !== null);
                        window.NoiseSurveyApp.eventHandlers.handleComparisonPositionsChange(selected);
                    } else {
                        console.error('NoiseSurveyApp.eventHandlers.handleComparisonPositionsChange not defined!');
                    }
                """
            )
        )

        metrics_table_html = """
            <style>
                .comparison-metrics-table { width: 100%; border-collapse: collapse; font-size: 12px; }
                .comparison-metrics-table th, .comparison-metrics-table td {
                    border: 1px solid #ddd;
                    padding: 4px 6px;
                    text-align: center;
                }
                .comparison-metrics-table th {
                    background-color: #f5f5f5;
                    font-weight: 600;
                }
                .comparison-metrics-table__placeholder {
                    font-style: italic;
                    color: #666;
                }
            </style>
            <table class="comparison-metrics-table">
                <thead>
                    <tr>
                        <th>Position</th>
                        <th>Duration</th>
                        <th>LAeq</th>
                        <th>LAFmax</th>
                        <th>LA90</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td class="comparison-metrics-table__placeholder" colspan="5">Select a time slice to populate metrics.</td>
                    </tr>
                </tbody>
            </table>
        """
        self.metrics_table_div = Div(
            text=metrics_table_html,
            width=320,
            height=220,
            name="comparison_metrics_div",
            styles={
                "border": "1px solid #ccc",
                "padding": "12px",
                "background-color": "#fafafa",
                "overflow-y": "auto"
            }
        )

        self.make_regions_button = Button(
            label="Make Region(s)",
            button_type="primary",
            width=150,
            name="comparison_make_regions_button",
            disabled=True
        )
        self.make_regions_button.js_on_event(
            "button_click",
            CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleComparisonMakeRegions) {
                    window.NoiseSurveyApp.eventHandlers.handleComparisonMakeRegions();
                } else {
                    console.info('Comparison region creation will be implemented in a future update.');
                }
            """)
        )

        self.finish_button = Button(
            label="Finish Comparison",
            button_type="success",
            width=150,
            name="comparison_finish_button",
            disabled=True
        )
        self.finish_button.js_on_event(
            "button_click",
            CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleFinishComparison) {
                    window.NoiseSurveyApp.eventHandlers.handleFinishComparison();
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleFinishComparison not defined!');
                }
            """)
        )

        buttons_row = Row(
            self.make_regions_button,
            self.finish_button,
            name="comparison_panel_buttons",
            sizing_mode="scale_width"
        )

        self.container = Column(
            self.instructions_div,
            self.position_selector,
            self.metrics_table_div,
            buttons_row,
            name="comparison_panel_layout",
            sizing_mode="stretch_width"
        )
        self.container.visible = False

    def layout(self):
        return self.container


class ComparisonFrequencyBarComponent:
    """Multi-series frequency comparison chart."""

    def __init__(self, width: Optional[int] = None):
        chart_width = width or CHART_SETTINGS.get('frequency_bar_width', 800)
        initial_data = {
            'x': [],
            'level': [],
            'position': [],
            'color': []
        }
        self.source = ColumnDataSource(data=initial_data, name="comparison_frequency_source")
        self.x_range = FactorRange(factors=[])
        self.palette = Category10[10]
        self.figure = self._create_figure(chart_width)
        self.table_div = Div(
            text=self._empty_table_html(),
            width=chart_width,
            name="comparison_frequency_table",
            styles={
                "border": "1px solid #ccc",
                "padding": "12px",
                "background-color": "#fafafa",
                "margin-top": "8px"
            }
        )

        self.container = column(self.figure, self.table_div, name="comparison_frequency_layout")
        self.container.visible = False

    def _empty_table_html(self) -> str:
        return """
            <table class="comparison-frequency-table" style="width:100%; border-collapse: collapse; font-size:12px;">
                <thead>
                    <tr>
                        <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Position</th>
                        <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Spectrum</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td colspan="2" style="border:1px solid #ddd; padding:6px; text-align:center; font-style:italic; color:#666;">
                            Select a time slice to view averaged spectra.
                        </td>
                    </tr>
                </tbody>
            </table>
        """

    def _create_figure(self, chart_width: int):
        p = figure(
            title="Comparison Spectrum",
            height=CHART_SETTINGS.get('high_freq_height', 300),
            width=chart_width,
            x_range=self.x_range,
            x_axis_label='Frequency Band',
            y_axis_label='Level (dB)',
            tools="pan,wheel_zoom,box_zoom,reset,save",
            name="comparison_frequency_chart"
        )

        p.vbar(
            x='x',
            top='level',
            width=0.8,
            source=self.source,
            fill_color='color',
            line_color='color',
            legend_field='position'
        )

        p.legend.location = "top_left"
        p.legend.click_policy = "hide"
        p.xaxis.major_label_orientation = 0.8
        p.xaxis.major_label_text_font_size = "8pt"
        p.yaxis.formatter = NumeralTickFormatter(format="0.0")

        hover = HoverTool(tooltips=[
            ("Position", "@position"),
            ("Frequency", "@x{safe}"),
            ("Level", "@level{0.1f} dB")
        ])
        p.add_tools(hover)

        return p

    def layout(self):
        return self.container

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

def create_audio_controls_for_position(position_id: str) -> dict:
    """
    Creates a dictionary of Bokeh widgets for controlling audio playback for a single position.

    Args:
        position_id (str): The identifier for the measurement position (e.g., 'SW', 'N').

    Returns:
        dict: A dictionary containing the Bokeh widgets ('play_toggle', 'playback_rate_button', 
              'volume_boost_button') and their containing 'layout'.
    """
    # Play/Pause Toggle Button
    play_toggle = Toggle(
        label="Play", 
        button_type="success", 
        width=80,
        name=f"play_toggle_{position_id}"
    )

    play_toggle_callback = CustomJS(
        args=dict(position_id=position_id, button=play_toggle),
        code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.togglePlayPause) {
                // Call the togglePlayPause handler with the new toggle state so the thunk can validate the intent
                window.NoiseSurveyApp.eventHandlers.togglePlayPause({ positionId: position_id, isActive: button.active });
            } else {
                console.error('NoiseSurveyApp.eventHandlers.togglePlayPause function not found!');
            }
        """
    )
    play_toggle.js_on_change('active', play_toggle_callback)

    # Playback Rate Button
    playback_rate_button = Button(
        label="1.0x",
        width=60,
        name=f"playback_rate_{position_id}"
    )
    playback_rate_button.js_on_click(CustomJS(
        args=dict(position_id=position_id),
        code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handlePlaybackRateChange) {
                window.NoiseSurveyApp.eventHandlers.handlePlaybackRateChange({ positionId: position_id });
            } else {
                console.error('NoiseSurveyApp.eventHandlers.handlePlaybackRateChange function not found!');
            }
        """
    ))

    # Volume Boost Toggle Button
    volume_boost_button = Toggle(
        label="Boost",
        width=70,
        name=f"volume_boost_{position_id}",
        active=False # Default to off
    )
    volume_boost_button.js_on_change('active', CustomJS(
        args=dict(position_id=position_id, button=volume_boost_button),
        code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle) {
                window.NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle({ positionId: position_id, isBoostActive: button.active });
            } else {
                console.error('NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle function not found!');
            }
        """
    ))

    # Layout for the controls
    controls_layout = Row(
        play_toggle, 
        playback_rate_button, 
        volume_boost_button,
        name=f"audio_controls_{position_id}"
    )

    logger.debug(f"Audio controls created for position '{position_id}'.")
    return {
        "play_toggle": play_toggle,
        "playback_rate_button": playback_rate_button,
        "volume_boost_button": volume_boost_button,
        "layout": controls_layout
    }

class SummaryTableComponent:
    """
    A component that displays a summary table of parameter values for all 
    positions at a specific tapped timestamp. The content is entirely 
    controlled by JavaScript.
    """
    def __init__(self, position_names: List[str], parameters: List[str], compact: bool = True):
        self.settings = CHART_SETTINGS
        self.position_names = position_names
        self.parameters = parameters
        self.compact = compact
        
    
        initial_html = self._create_initial_html()

        self.summary_div = Div(
            text = initial_html,
            name = "summary_table_div",
            width=self.settings.get('low_freq_width', 1200) # Match the width of the charts
        )

        logger.info(f"SummaryTableComponent initialized with {len(parameters)} parameters, compact={compact}.")

    def _create_initial_html(self) -> str:
        """Generates the initial HTML for the table with a placeholder message."""
        # Responsive styling based on compact mode
        font_size = "0.8em" if self.compact else "0.9em"
        padding = "4px" if self.compact else "8px"
        margin_bottom = "10px" if self.compact else "20px"
        
        style = f"""
        <style>
            .summary-html-table {{ border-collapse: collapse; width: 100%; font-size: {font_size}; table-layout: fixed; margin-top: 10px; margin-bottom: {margin_bottom};}}
            .summary-html-table th, .summary-html-table td {{ border: 1px solid #ddd; padding: {padding}; text-align: center; }}
            .summary-html-table th {{ background-color: #f2f2f2; font-weight: bold; }}
            .summary-html-table .position-header {{ text-align: left; font-weight: bold; }}
            .summary-html-table .placeholder {{ color: #888; font-style: italic; }}
            .summary-html-table .timestamp-info {{ background-color: #f9f9f9; font-size: 0.85em; color: #666; }}
        </style>
        """
        
        header_row = "".join(f"<th>{param}</th>" for param in self.parameters)
        
        placeholder_row = f"<td class='placeholder' colspan='{len(self.parameters) + 1}'>Tap on a time series chart to populate this table.</td>"

        table_html = f"""
        {style}
        <table class="summary-html-table">
            <thead>
                <tr>
                    <th class="position-header">Position</th>
                    {header_row}
                </tr>
            </thead>
            <tbody>
                <tr>
                    {placeholder_row}
                </tr>
            </tbody>
        </table>
        """
        return table_html

    def layout(self):
        """Returns the Bokeh layout object for this component."""
        return self.summary_div