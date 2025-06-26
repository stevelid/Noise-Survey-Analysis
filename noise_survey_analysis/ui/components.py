
# Add the project root to Python path


import pandas as pd
import numpy as np
import logging
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, NumeralTickFormatter, DatetimeTickFormatter, Legend, DatetimeTicker
from bokeh.palettes import Category10  # Using a standard palette
from typing import Optional, Dict, Any, List
from bokeh.models import ColorBar, Div, LinearColorMapper
from bokeh.layouts import column
from matplotlib.figure import Figure
from bokeh.plotting import figure
from bokeh.models import (
    ColumnDataSource, 
    FactorRange, 
    Range1d, 
    LabelSet, 
    HoverTool,
    NumeralTickFormatter, # For y-axis formatting
    RangeTool,
    Span,
    Label,
    CustomJS,
    Tap,
    Toggle,
    Select, 
    Row,
    Column,
    CheckboxGroup)
from bokeh.palettes import Category10 # Or any other palette


import sys
from pathlib import Path
current_file = Path(__file__)
project_root = current_file.parent.parent.parent  # Go up to "Noise Survey Analysis"
sys.path.insert(0, str(project_root))

from noise_survey_analysis.core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS
from noise_survey_analysis.core.data_manager import PositionData
from noise_survey_analysis.core.data_processors import GlyphDataProcessor


logger = logging.getLogger(__name__)

class TimeSeriesComponent:
    """
    A self-contained Time Series chart component for displaying broadband noise data.
    It can display either overview/summary data or log data for a given position.
    """
    def __init__(self, position_data_obj, initial_display_mode: str = 'overview'):
        """
        Initializes the component.

        Args:
            position_data_obj: A PositionData object containing the data for the position.
            initial_display_mode: 'overview' or 'log'. Determines which data to show initially.
        """

        if not isinstance(position_data_obj, PositionData):
            raise ValueError("TimeSeriesComponent requires a valid PositionData object.")

        #self.position_data = position_data_obj #commented out as it is not used, to remove once confirmed. 
        self.position_name = position_data_obj.name
        self._current_display_mode = initial_display_mode # 'overview' or 'log'
        self.chart_settings = CHART_SETTINGS
        self.name_id = f"{self.position_name}_timeseries"
        self.line_renderers = []
        
        #generate sources for the two view modes
        if position_data_obj['overview_totals'] is not None:
            overview_df = position_data_obj.overview_totals.copy()
            overview_df['Datetime'] = overview_df['Datetime'].values.astype(np.int64) // 10**6 #convert to ms
            self.overview_source: ColumnDataSource = ColumnDataSource(data=overview_df)
        else:
            self.overview_source: ColumnDataSource = ColumnDataSource(data={})
        
        if position_data_obj['log_totals'] is not None:
            log_df = position_data_obj.log_totals.copy()
            log_df['Datetime'] = log_df['Datetime'].values.astype(np.int64) // 10**6 #convert to ms
            self.log_source: ColumnDataSource = ColumnDataSource(data=log_df)
        else:
            self.log_source: ColumnDataSource = ColumnDataSource(data={})
        
        #source and figure
        #make a copy of the source data to prevent overwriting the source when the data is updated
        self.source = ColumnDataSource(data=dict(self.overview_source.data)) if self._current_display_mode == 'overview' else ColumnDataSource(data=dict(self.log_source.data))
        #self.source = ColumnDataSource(data={'Datetime': [], 'LAeq': [], 'LAFmax': [], 'LAF10': [],'LAF90': []}) #dont set this to the overview or log source as it overwrite the source when the data is updated
        self.source.name = "source_" + self.name_id
        self.figure: figure = self._create_figure()
        self._update_plot_lines() # Add lines based on initial data
        self._configure_figure_formatting()

        #interative components
        self.tap_lines = Span(location=0, dimension='height', line_color='red', line_width=1, name=f"click_line_{self.name_id}")
        self.hover_line = Span(location=0, dimension='height', line_color='grey', line_width=1, line_dash='dashed', name=f"hover_line_{self.name_id}")
        self.label = Label(x=0, y=0, text="", text_font_size='10pt', background_fill_color="white", background_fill_alpha=0.6, text_baseline="middle", visible=False, name=f"label_{self.name_id}")

        self.figure.add_layout(self.tap_lines)
        self.figure.add_layout(self.hover_line)
        self.figure.add_layout(self.label)
        self._attach_callbacks()
        
        


        logger.info(f"TimeSeriesComponent initialized for '{self.position_name}' in '{self._current_display_mode}' mode.")


    def _create_figure(self) -> figure:
        """Creates and configures the Bokeh figure for the time series plot."""
        title_suffix = "Overview" if self._current_display_mode == 'overview' else "Log"
        title = f"Time History: {self.position_name} ({title_suffix})"

        # Common tools for time series charts
        tools = self.chart_settings['tools']
        
        p = figure(
            height=self.chart_settings['low_freq_height'],
            width=self.chart_settings['low_freq_width'],
            title=title,
            x_axis_type="datetime",
            x_axis_label="Time",
            y_axis_label="Sound Level (dB)",
            tools=tools,
            active_drag="xpan",
            active_scroll="xwheel_zoom",
            name=f"figure_{self.name_id}" # For identification
        )
                
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
        title_suffix = "Overview" if self._current_display_mode == 'overview' else "Log"
        self.figure.title.text = f"Time History: {self.position_name} ({title_suffix})"

    def _configure_figure_formatting(self):
        """Configures the formatting for the figure."""
        self.figure.xaxis.formatter = DatetimeTickFormatter(days="%a %d/%m/%y", hours="%H:%M:%S") # Simplified formats
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
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.interactions.onTap) {
                window.NoiseSurveyApp.interactions.onTap(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.interactions.onTap not defined!');
                }
        """)
        self.figure.js_on_event('tap', tap_js)

        hover_js = CustomJS(code=f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.interactions.onHover) {{
                window.NoiseSurveyApp.interactions.onHover(cb_data, 'figure_{self.name_id}');
                }} else {{
                    console.error('NoiseSurveyApp.interactions.onHover not defined!');
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
                 initial_display_mode: str = 'overview', # 'overview' or 'log'
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

        #self.position_data = position_data_obj #commented out as it is not used, to remove once confirmed. 
        self.position_name = position_data_obj.name
        #self.position_glyph_data = position_glyph_data #commented out as it is not used, to remove once confirmed. 
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
                                  styles={'font-size': '9pt', 'font-weight': 'bold', 'padding-left': '10px', 'text-align': 'center'})
        self.image_glyph = None # Store the image glyph renderer
        self.update_plot(position_glyph_data, self._current_display_mode, self._current_param)

        #interactive components
        self.tap_lines = Span(location=0, dimension='height', line_color='red', line_width=1, name=f"click_line_{self.name_id}")
        self.hover_line = Span(location=0, dimension='height', line_color='grey', line_width=1, line_dash='dashed', name=f"hover_line_{self.name_id}")

        self.figure.add_layout(self.tap_lines)
        self.figure.add_layout(self.hover_line)
        self._attach_callbacks()

        logger.info(f"SpectrogramComponent initialized for '{self.position_name}'. Initial mode: '{self._current_display_mode}', Param: '{self._current_param}'")

    def _create_empty_figure(self) -> Figure:
        """Creates a blank Bokeh figure as a placeholder."""
        title = f"Spectrogram: {self.position_name}"
        p = figure(
            title=title,
            x_axis_type="datetime",
            y_axis_type="linear",
            height=self.chart_settings['spectrogram_height'],
            width=self.chart_settings['spectrogram_width'], # Use width for initial sizing
            tools=self.chart_settings['tools'],
            active_drag=self.chart_settings['active_drag'],
            active_scroll=self.chart_settings['active_scroll'],
            name=f"figure_{self.name_id}"
        )
        p.xaxis.formatter = DatetimeTickFormatter(days="%a %d/%m/%y", hours="%H:%M:%S") # Simplified formats
        p.xaxis.ticker = DatetimeTicker(desired_num_ticks=10) # Fewer ticks might be cleaner
        p.yaxis.axis_label = "Frequency (Hz)"
        #p.xaxis.axis_label = "Time"
        p.xgrid.visible = False
        p.ygrid.visible = False
        p.visible = False # Initially hidden if no data
        return p

    def _update_figure_content(self, prepared_param_data: Dict[str, Any]):
        """Updates the figure with new data (image, axes, colorbar)."""
        param_name = self._current_param or "Unknown Param"
        mode_name = self._current_display_mode.replace("_spectral","").title()
        self.figure.title.text = f"Spectrogram: {self.position_name} - {param_name} ({mode_name})"

        # Extract data from prepared_param_data
        times_ms = np.array(prepared_param_data['times_ms'])
        n_times = prepared_param_data['n_times']
        n_freqs = prepared_param_data['n_freqs']
        freq_indices = np.array(prepared_param_data['freq_indices'])
        selected_frequencies = np.array(prepared_param_data['frequencies_numeric'])
        
        transposed_matrix = np.array(prepared_param_data['levels_matrix']).T
        
        # Update image source
        self.source.data = {'image': [transposed_matrix]}

        # Update x_range (numeric ms for figure, Bokeh handles datetime axis)
        self.figure.x_range.start = times_ms[0] if n_times > 0 else 0
        self.figure.x_range.end = times_ms[-1] if n_times > 0 else (times_ms[0] + 60000 if n_times >0 else 60000) # Add 1 min if only one point
        if self.figure.x_range.start == self.figure.x_range.end and n_times > 0: # Single time point
            self.figure.x_range.end = self.figure.x_range.start + 60000 # Make it 1 minute wide

        # Update y_range (categorical based on indices)
        self.figure.y_range.start = -0.5
        self.figure.y_range.end = n_freqs - 0.5
        
        # Update Y-axis ticks and labels
        self.figure.yaxis.ticker = freq_indices.tolist()
        self.figure.yaxis.major_label_overrides = {
            int(i): (str(int(freq)) if freq >=10 else f"{freq:.1f}") # No " Hz" for brevity
            for i, freq in enumerate(selected_frequencies)
        }
        
        # Update or create image glyph
        if self.image_glyph:
            self.figure.renderers.remove(self.image_glyph) # Remove old one
        
        self.image_glyph = self.figure.image(
            image='image', source=self.source,
            x=prepared_param_data['x_coord'], 
            y=prepared_param_data['y_coord'],
            dw=prepared_param_data['dw_val'], 
            dh=prepared_param_data['dh_val'],
            color_mapper=LinearColorMapper(palette=self.chart_settings['colormap'], 
                                          low=prepared_param_data['min_val'], 
                                          high=prepared_param_data['max_val'],
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

    def update_plot(self, position_glyph_data, display_mode: str, parameter: str):
        """
        Updates the spectrogram to show data for the specified mode and parameter.
        """
        logger.info(f"SpectrogramComponent '{self.position_name}': Updating to mode='{display_mode}', param='{parameter}'")
        
        mode_data_root = position_glyph_data.get(display_mode)
        if not mode_data_root:
            logger.warning(f"No prepared data for mode '{display_mode}' in {self.position_name}.")
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
                    self.figure.visible = False; self.hover_div.visible = False; return
            else:
                self.figure.visible = False; self.hover_div.visible = False; return

        self._current_display_mode = display_mode
        self._current_param = parameter
        self._update_figure_content(prepared_param_data)

    def _attach_callbacks(self):
        """Creates and attaches all JS callbacks for this specific component."""
        tap_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.interactions.onTap) {
                window.NoiseSurveyApp.interactions.onTap(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.interactions.onTap not defined!');
                }
        """)
        self.figure.js_on_event('tap', tap_js)

        hover_js = CustomJS(code=f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.interactions.onHover) {{
                window.NoiseSurveyApp.interactions.onHover(cb_data, 'figure_{self.name_id}');
                }} else {{
                    console.error('NoiseSurveyApp.interactions.onHover not defined!');
                }}
        """)
        hover_tool = HoverTool(
            tooltips=None, # We use our own custom labels
            mode='vline',
            callback=hover_js,
            name=f"hover_tool_{self.name_id}"
        )
        self.figure.add_tools(hover_tool)

    def layout(self):
        """Returns the Bokeh layout object for this component."""
        # The figure might be initially hidden if no data, visibility managed by update_plot
        return column(self.figure, self.hover_div, name=f"{self.name_id}_component")


class ControlsComponent:
    """A component that provides global controls for the dashboard."""
    def __init__(self, available_params: List[str]): # Would take DataManager to access all positions' info
        
        self.available_params = available_params
        self.visibility_checkboxes_map: Dict[str, Toggle] = {} # Key: chart_name, Value: Checkbox/Toggle widget
        self.visibility_layout = None
        
        self.view_toggle = self.add_view_type_selector()
        self.param_select = self.add_parameter_selector(available_params)

        logger.info("ControlsComponent initialized.")


    def add_view_type_selector(self):
        toggle = Toggle(
            label="Switch to Log Data", 
            button_type="primary", 
            width=150,
            name="global_view_toggle"
        )
        
        toggle.js_on_change("active", CustomJS(args={"toggle_widget": toggle}, code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.handleViewToggle) {
                window.NoiseSurveyApp.handleViewToggle(cb_obj.active, toggle_widget); // Pass the toggle widget itself
            } else {
                console.error('window.NoiseSurveyApp.handleViewToggle function not found!');
            }""")) #active for overview, inactive for log
        return toggle

    def add_parameter_selector(self, available_params: List[str]):
        select = Select(
            options=available_params,
            value="LZeq",
            width=150,
            name="global_parameter_selector"
        )
        select.js_on_change("value", CustomJS(args={"select_widget": select}, code="""if (window.NoiseSurveyApp && window.NoiseSurveyApp.handleParameterChange) {
                window.NoiseSurveyApp.handleParameterChange(cb_obj.value, select_widget); // Pass the select widget itself
            } else {
                console.error('window.NoiseSurveyApp.handleParameterChange function not found!');
            }""")) #active for overview, inactive for log
        return select

    def add_visibility_checkbox(self, chart_name: str, chart_label: str, initial_state: bool = True):
        """
        Adds a visibility checkbox for a specific chart.
        Called by DashBuilder after chart components are created.
        """
        # Use Toggle to match your component's current implementation
        # If you switch to Checkbox in components, use Checkbox(label=chart_label, active=initial_state, name=f"visibility_cb_{chart_name}")
        checkbox = CheckboxGroup(labels=[chart_label], active=[0] if initial_state else [], name=f"{chart_name.replace("figure_", "checkbox_")}", width=150) # Adjust width as needed

        # --- Attach JS Callback ---
        checkbox_js_callback = CustomJS(args=dict(chart_name=chart_name),code=f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.interactions.onVisibilityChange) {{
                window.NoiseSurveyApp.interactions.onVisibilityChange(cb_obj, chart_name);
                }} else {{
                    console.error('NoiseSurveyApp.interactions.onVisibilityChange not defined!');
                }}
            """)
        checkbox.js_on_change("active", checkbox_js_callback)
        self.visibility_checkboxes_map[chart_name] = checkbox

    def _build_visibility_layout(self):
        """Builds the row layout for visibility checkboxes."""
        if not self.visibility_checkboxes_map:
            self.visibility_layout = Div(text="") # Empty div if no checkboxes
            return

        checkbox_widgets = list(self.visibility_checkboxes_map.values())
        self.visibility_layout = Row(*checkbox_widgets, name="visibility_controls_row", sizing_mode="scale_width")


    def layout(self):
        # Ensure visibility layout is built before returning the main layout
        if self.visibility_layout is None:
            self._build_visibility_layout()

        # Main controls row (parameter select, view toggle)
        main_controls_row = Row(
            self.param_select,
            self.view_toggle,
            sizing_mode="scale_width", # Or "stretch_width"
            name="main_controls_row"
        )

        # Return a column containing the main controls and then the visibility controls
        return Row(main_controls_row, self.visibility_layout, name="controls_component_layout")

    def get_all_visibility_checkboxes(self) -> list:
        return list(self.visibility_checkboxes_map.values())
        

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
        self.hover_line = Span(location=0, dimension='height', line_color='grey', line_width=1, line_dash='dashed', name=f"hover_line_{self.name_id}")
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
        if source.data['Datetime'].all() and len(source.data['Datetime']) > 0:
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
        if source.data['Datetime'].all() and len(source.data['Datetime']) > 0:
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

        select_figure.xaxis.formatter = DatetimeTickFormatter(days="%a %d/%m/%y", hours="%H:%M:%S")
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
    from other components like a spectrogram.
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
        
        self.figure: Figure = self._create_figure()
        
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

    def layout(self) -> Figure:
        """
        Returns the Bokeh layout object (the figure itself) for this component.
        """
        return self.figure

    def update_data(self, frequency_labels: List[str], levels: List[float]):
        """
        Public method to update the data in the bar chart.
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
        logger.debug(f"FrequencyBarComponent data updated. Factors: {frequency_labels[:5]}..., Levels: {levels[:5]}...")

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