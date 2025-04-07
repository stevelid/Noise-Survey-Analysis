"""
Visualization dashboard for noise survey analysis.

This module contains the DashboardBuilder class which orchestrates 
the creation and layout of visualization components for the dashboard.
"""

import logging
import pandas as pd
import numpy as np
import traceback
from bokeh.plotting import figure
from bokeh.io import curdoc
from bokeh.models import (
    ColumnDataSource, Button, Select, Div, Toggle, CheckboxGroup, Range1d,
    Slider, RangeSlider, CustomJS, Panel, Tabs, RadioButtonGroup, LayoutDOM,
    TableColumn, DataTable
)
from bokeh.layouts import column, row, gridplot
from ..core.data_loaders import extract_spectral_parameters
from ..core.data_processors import prepare_spectral_image_data
from .visualization_components import (
    create_TH_chart, create_log_chart, make_image_spectrogram, 
    create_frequency_bar_chart, create_range_selector, link_x_ranges,
    add_vertical_line_and_hover
)
from ..ui.controls import create_position_play_button, create_playback_controls, create_parameter_selector

# --- Setup Logger ---
logger = logging.getLogger(__name__)


class BokehModelsAdapter:
    """
    Adapter class for Bokeh models dictionary to support transition from flat to hierarchical structure.
    
    This class implements the adapter pattern to:
    1. Provide backward compatibility with the flat dictionary structure
    2. Support the new hierarchical structure for better organization
    3. Log warnings when legacy keys are accessed to help identify code that needs updating
    
    Usage:
        self.bokeh_models = BokehModelsAdapter()
        
        # Old style access will still work but log warnings
        self.bokeh_models['all_charts'].append(chart)
        
        # New style access is preferred
        self.bokeh_models['charts']['all'].append(chart)
    """
    def __init__(self):
        """Initialize the adapter with the new hierarchical structure."""
        # New hierarchical structure
        self._data = {
            'charts': {
                'all': [],                    # All Bokeh Figure objects
                'time_series': [],            # Time-based charts for synchronization
                'for_js_interaction': []      # Charts requiring JS callbacks
            },
            
            'sources': {
                'data': {},                   # Main data sources by key
                'playback': {                 # Playback-related sources
                    'position': None,         # Current playback position 
                    'seek_command': None,     # For sending seek commands
                    'play_request': None      # For play requests from JS
                },
                'frequency': {                # Frequency analysis sources
                    'bar': None,              # For frequency bar chart
                    'table': None             # For frequency data table
                }
            },
            
            'ui': {
                'position_elements': {},      # UI elements by position
                'controls': {                 # UI controls
                    'playback': {},           # Play/pause buttons
                    'parameter': {            # Parameter selection
                        'select': None,       # Dropdown for parameter selection
                        'holder': None        # Hidden div for selected parameter
                    },
                    'init_js': None           # Button to initialize JS
                },
                'visualization': {            # Visual elements
                    'click_lines': {},        # Vertical lines for clicked positions
                    'labels': {},             # Text labels for data points
                    'range_selectors': {}     # Range selectors for zooming
                }
            },
            
            'frequency_analysis': {           # Frequency analysis components 
                'bar_chart': {                # Bar chart components
                    'figure': None,           # The bar chart figure
                    'x_range': None           # X range for the chart
                }
            },
            
            'spectral_data': {                # Spectral data by position
                # 'position_name': {
                #     'available_params': [],   # Available spectral parameters
                #     'current_param': 'LZeq',  # Currently selected parameter
                #     'prepared_data': {        # Pre-processed data by parameter
                #         'param_name': {...}   # Detailed parameter data
                #     }
                # }
            }
        }
        
        # Mapping from legacy (flat) keys to new hierarchical structure
        # Using references to the actual objects in the new structure
        self._legacy_mapping = {
            # Charts and Sources
            'all_charts': self._data['charts']['all'],
            'time_series_charts': self._data['charts']['time_series'],
            'all_sources': self._data['sources']['data'],
            'charts_for_js': self._data['charts']['for_js_interaction'],
            'position_elements': self._data['ui']['position_elements'],
            
            # Interactive Elements
            'click_lines': self._data['ui']['visualization']['click_lines'],
            'labels': self._data['ui']['visualization']['labels'],
            'range_selectors': self._data['ui']['visualization']['range_selectors'],
            'playback_source': self._data['sources']['playback']['position'],
            'seek_command_source': self._data['sources']['playback']['seek_command'],
            'play_request_source': self._data['sources']['playback']['play_request'],
            
            # UI Controls
            'playback_controls': self._data['ui']['controls']['playback'],
            'param_select': self._data['ui']['controls']['parameter']['select'],
            'param_holder': self._data['ui']['controls']['parameter']['holder'],
            'init_js_button': self._data['ui']['controls']['init_js'],
            
            # Frequency Analysis
            'freq_bar_chart': self._data['frequency_analysis']['bar_chart']['figure'],
            'freq_bar_source': self._data['sources']['frequency']['bar'],
            'freq_bar_x_range': self._data['frequency_analysis']['bar_chart']['x_range'],
            'freq_table_source': self._data['sources']['frequency']['table'],
            
            # Spectral Data - special case, direct use of old structure for compatibility
            'spectral_param_charts': self._data['spectral_data']
        }
        
        # Tracking of legacy keys that have been accessed
        self._accessed_legacy_keys = set()
    
    def __getitem__(self, key):
        """
        Override dictionary access to support both old and new structure.
        Logs a warning when legacy keys are accessed.
        """
        # Check if it's a legacy key access
        if key in self._legacy_mapping:
            if key not in self._accessed_legacy_keys:
                # Log warning with stack trace to identify the calling code
                logger.warning(f"LEGACY ACCESS: Accessing bokeh_models with legacy key '{key}'. "
                               f"Consider using the new hierarchical structure.")
                # Get a short stack trace (3 levels) to identify where the legacy access is coming from
                stack = traceback.extract_stack(limit=3)
                caller = stack[-2]  # The caller of this method
                logger.warning(f"Called from: {caller.filename}:{caller.lineno} in {caller.name}")
                # Add to set of accessed keys to avoid duplicate warnings
                self._accessed_legacy_keys.add(key)
            
            # Return the value from the legacy mapping
            return self._legacy_mapping[key]
        
        # Regular access to the new structure
        return self._data[key]
    
    def __setitem__(self, key, value):
        """
        Override dictionary item setting to support both old and new structure.
        Logs a warning when legacy keys are accessed.
        """
        # Check if it's a legacy key access
        if key in self._legacy_mapping:
            if key not in self._accessed_legacy_keys:
                # Log warning with stack trace to identify the calling code
                logger.warning(f"LEGACY ACCESS: Setting bokeh_models with legacy key '{key}'. "
                               f"Consider using the new hierarchical structure.")
                # Get a short stack trace (3 levels) to identify where the legacy access is coming from
                stack = traceback.extract_stack(limit=3)
                caller = stack[-2]  # The caller of this method
                logger.warning(f"Called from: {caller.filename}:{caller.lineno} in {caller.name}")
                # Add to set of accessed keys to avoid duplicate warnings
                self._accessed_legacy_keys.add(key)
            
            # Update in the legacy mapping
            # This is a special case as some values are direct references (lists, dicts)
            # and others are actual values (None, objects)
            if isinstance(self._legacy_mapping[key], list) and isinstance(value, list):
                self._legacy_mapping[key][:] = value  # Update in-place for lists
            elif isinstance(self._legacy_mapping[key], dict) and isinstance(value, dict):
                self._legacy_mapping[key].clear()
                self._legacy_mapping[key].update(value)  # Update in-place for dicts
            else:
                # For direct value updates, update both the legacy mapping and the actual location
                self._legacy_mapping[key] = value
                
                # Also update the actual location in the hierarchical structure
                # This is where we need to handle each legacy key specifically
                if key == 'playback_source':
                    self._data['sources']['playback']['position'] = value
                elif key == 'seek_command_source':
                    self._data['sources']['playback']['seek_command'] = value
                elif key == 'play_request_source':
                    self._data['sources']['playback']['play_request'] = value
                elif key == 'param_select':
                    self._data['ui']['controls']['parameter']['select'] = value
                elif key == 'param_holder':
                    self._data['ui']['controls']['parameter']['holder'] = value
                elif key == 'init_js_button':
                    self._data['ui']['controls']['init_js'] = value
                elif key == 'freq_bar_chart':
                    self._data['frequency_analysis']['bar_chart']['figure'] = value
                elif key == 'freq_bar_source':
                    self._data['sources']['frequency']['bar'] = value
                elif key == 'freq_bar_x_range':
                    self._data['frequency_analysis']['bar_chart']['x_range'] = value
                elif key == 'freq_table_source':
                    self._data['sources']['frequency']['table'] = value
        else:
            # Regular access to the new structure
            self._data[key] = value
    
    def __contains__(self, key):
        """Support 'in' operator for both legacy and new keys."""
        return key in self._legacy_mapping or key in self._data
    
    def keys(self):
        """Return all keys (both legacy and new structure)."""
        return set(self._legacy_mapping.keys()).union(self._data.keys())
    
    def get(self, key, default=None):
        """Support get() method for both legacy and new keys."""
        if key in self:
            return self[key]
        return default
    
    def items(self):
        """
        Return items from the new structure, plus any legacy items
        that don't have a 1:1 mapping to the new structure.
        """
        # Start with items from the new structure
        items_dict = dict(self._data)
        
        # Add legacy items that might have direct values
        for key, value in self._legacy_mapping.items():
            if isinstance(value, (list, dict)):
                # Skip references to mutable collections that are already in the new structure
                continue
            items_dict[key] = value
            
        return items_dict.items()

class DashboardBuilder:
    """
    Builds the Bokeh dashboard layout, including charts, widgets, and interactions.
    Orchestrates the creation of visualization components and UI elements.
    
    This builder class handles the entire process of:
    1. Loading and processing data
    2. Creating charts and visualizations
    3. Setting up UI controls and interactions
    4. Assembling the final layout
    5. Setting up JavaScript interactions
    
    The builder maintains its state in the bokeh_models dictionary, which collects
    all created Bokeh objects for later use in layouts and JavaScript callbacks.
    """
    def __init__(self, position_data: dict, chart_settings: dict, visualization_settings: dict, audio_handler_available: bool):
        """
        Initializes the DashboardBuilder.

        Args:
            position_data (dict): Dictionary containing processed data for each position.
                                 Expected structure:
                                 {
                                     'Position1': {
                                         'overview': DataFrame,  # Time series data for overview
                                         'log': DataFrame,       # Logging data with timestamps
                                         'spectral': DataFrame   # Spectral data with frequencies
                                     },
                                     'Position2': { ... }
                                 }
            chart_settings (dict): Configuration for chart appearance (heights, etc.).
            visualization_settings (dict): Configuration for visualization behavior.
            audio_handler_available (bool): Flag indicating if audio playback is enabled.
        """
        self.position_data = position_data
        self.chart_settings = chart_settings
        self.visualization_settings = visualization_settings
        self.audio_handler_available = audio_handler_available

        # Use the new adapter class for bokeh_models to support transition from flat to hierarchical structure
        self.bokeh_models = BokehModelsAdapter()
        
        # Collect all available spectral parameters across all positions
        self._all_spectral_params = set()

    def build(self) -> LayoutDOM:
        """
        Builds and returns the complete dashboard layout.
        
        This method orchestrates the creation of all charts, widgets, and interactive
        components, assembling them into a coherent layout. The process includes:
        
        1. Creating shared components like frequency bar charts
        2. Building charts for each measurement position
        3. Creating a shared range selector for time navigation
        4. Adding UI controls for playback and parameter selection
        5. Setting up interactions like hover, click, and parameter switching
        6. Initializing JavaScript integration
        7. Assembling all components into the final layout
        
        Returns:
            LayoutDOM: The main dashboard layout object ready to be rendered in a Bokeh document
        """
        logger.info("Building dashboard...")
        
        # --- 1. Create Layout Components ---
        # Create shared components first (playback source, frequency bar chart, hover info div)
        self._create_shared_components()
        
        # Create the title div
        title_div = Div(
            text=f"<h1>Noise Survey Dashboard</h1>",
            sizing_mode="stretch_width"
        )
        
        # --- 2. Create charts for all positions ---
        # This populates: all_charts, time_series_charts,
        # spectral_param_charts, _all_spectral_params
        chart_elements, time_series_charts, has_spectral = self._create_position_charts()
        
        # --- 3. Create shared range selector if we have time series charts ---
        range_selector = None
        if time_series_charts:
            range_selector = self._create_shared_range_selector(time_series_charts)
        
        # --- 4. Create Controls Area (Playback, Parameter Selection) ---
        controls_area = self._create_controls_area()
        
        # --- 5. Create Frequency Analysis Section if needed ---
        freq_analysis_section = None
        freq_data_table = None
        if has_spectral:
            freq_analysis_section = self._create_frequency_analysis_section()
            freq_data_table = self._create_frequency_data_table()
        
        # --- 6. Add interactions after all charts are created ---
        self._add_interactions()
        
        # --- 7. Create Initialize JS button at the bottom of the page ---
        init_JS_button = self.bokeh_models['ui']['controls']['init_js']
        
        # --- 8. Assemble the Main Layout ---
        # Order: Title at top, followed by controls, then range selector,
        # then all position charts, and frequency analysis at the bottom.
        layout_components = []
        
        # Add title
        layout_components.append(title_div)
        
        # Add controls area with playback and param selection
        if controls_area:
            layout_components.append(controls_area)
        
        # Add range selector if it exists
        if range_selector:
            layout_components.append(range_selector)
        
        # Add all the chart elements
        if chart_elements:
            layout_components.extend(chart_elements)
        
        # Add frequency analysis row if it exists
        if freq_analysis_section:
            layout_components.append(freq_analysis_section)
            
        # Add frequency data table if it exists
        if freq_data_table:
            layout_components.append(freq_data_table)
        
        # Add the Initialize JS button at the bottom
        if init_JS_button:
            footer_div = Div(text="<div style='margin-top: 20px;'></div>", sizing_mode="stretch_width")
            layout_components.append(footer_div)
            layout_components.append(init_JS_button)
            logger.debug("Initialize JS button added to the bottom of the layout.")
        
        # Create the main column layout
        main_layout = column(
            *layout_components
        )
        
        # --- 8. Initialize JavaScript ---
        # Import here to avoid circular import
        from .interactive import initialize_global_js
        
        # Call initialize_global_js with bokeh_models
        js_init_callback = initialize_global_js(bokeh_models=self.bokeh_models)
        
        # Attach JS init callback using a data source change to trigger it
        if js_init_callback:
            # Create a trigger source
            from bokeh.models import ColumnDataSource
            trigger_source = ColumnDataSource(data={'trigger': [0]}, name='js_init_trigger')
            
            # Add debug logging to the callback
            debug_callback = CustomJS(args={'callback': js_init_callback}, code="""
                console.log('DEBUG: Trigger source changed, about to execute initialization...');
                callback.execute();
                console.log('DEBUG: Initialization callback executed');
            """)
            
            # Create callback that watches the trigger source
            trigger_source.js_on_change('data', debug_callback)
            
            # Make sure trigger source is added to document
            curdoc().add_root(trigger_source)
            
            # Schedule the data change after a short delay
            curdoc().add_timeout_callback(
                lambda: trigger_source.data.update({'trigger': [1]}), 
                1000  # Increased delay to 1 second
            )
            logger.info("JavaScript initialization scheduled via data source trigger.")
            
            # Also attach to the test button for manual triggering if needed
            init_JS_button = self.bokeh_models['ui']['controls']['init_js']
            if init_JS_button:
                init_JS_button.js_on_click(js_init_callback)
                logger.info("JavaScript initialization callback also attached to test button's click event.")
        
        logger.info("Dashboard build complete.")
        return main_layout

    def _create_shared_components(self):
        """Creates components shared across positions."""
        logger.debug("Creating shared components (playback source, freq bar chart, hover div)...")
        # Playback Source
        self.bokeh_models['sources']['playback']['position'] = ColumnDataSource(data={'current_time': [0]}, name='playback_source')

        # Seek Command Source - For sending seek commands from JS to Python
        self.bokeh_models['sources']['playback']['seek_command'] = ColumnDataSource(data={'target_time': [None]}, name='seek_command_source')
        
        # Play Request Source - For handling position play button requests from JS to Python
        self.bokeh_models['sources']['playback']['play_request'] = ColumnDataSource(data={'position': [None], 'time': [None]}, name='play_request_source')

        # Init JS Button for manual initialization if needed
        self.bokeh_models['ui']['controls']['init_js'] = Button(
            label="Initialize JS", 
            button_type="success", 
            name="init_js_button",
            width=150
        )
        logger.debug("Created init_js_button for manual JS initialization.")
        
        # Create a data source for frequency data table
        self.bokeh_models['sources']['frequency']['table'] = ColumnDataSource(
            data={
                'frequency': [],
                'value': []
            },
            name='freq_table_source'
        )
        logger.debug("Created frequency table data source.")

        # Frequency Bar Chart & Source (created even if no spectral data initially)
        # This assumes create_frequency_bar_chart returns chart, source, x_range
        (self.bokeh_models['frequency_analysis']['bar_chart']['figure'],
         self.bokeh_models['sources']['frequency']['bar'],
         self.bokeh_models['frequency_analysis']['bar_chart']['x_range']) = create_frequency_bar_chart(
             title="Frequency Slice",
             height=self.chart_settings.get("frequency_bar_height", 200)
        )
        if self.bokeh_models['frequency_analysis']['bar_chart']['figure']:
             
             # Store the source in all_sources as well for consistency if needed elsewhere
             self.bokeh_models['sources']['data']["frequency_bar"] = self.bokeh_models['sources']['frequency']['bar']
             
             # Connect the bar chart source to the table source with a callback
             #self._connect_freq_chart_to_table() #DEBUG, disconnecting the callback to avoid overwriting the table with the bar chart data for now!
        else:
             logger.error("Failed to create shared frequency bar chart.")
    
    def _connect_freq_chart_to_table(self):
        """
        Connects the frequency bar chart data source to the frequency table data source
        using a JavaScript callback.
        """
        freq_bar_source = self.bokeh_models['sources']['frequency']['bar']
        freq_table_source = self.bokeh_models['sources']['frequency']['table']
        selected_param_holder = self.bokeh_models['ui']['controls']['parameter']['holder']
        
        if freq_bar_source and freq_table_source:
            # Create callback to update table when bar chart data changes
            update_table_callback = CustomJS(
                args={
                    'table_source': freq_table_source,
                    'bar_source': freq_bar_source,
                    'param_holder': selected_param_holder
                },
                code="""
                // Get the current data from the bar chart
                const data = cb_obj.data;
                const x = data['x'];
                const top = data['top'];
                
                // Get the current parameter if available
                let param_name = 'Value';
                if (param_holder && param_holder.text) {
                    param_name = param_holder.text;
                }
                
                // Transform data into a single row with frequency headers
                // First, create an object with one entry per frequency
                const frequency_data = {};
                
                // Format all frequencies as column names
                for (let i = 0; i < x.length; i++) {
                    const freq = x[i];
                    let freq_label;
                    
                    if (freq < 1000) {
                        freq_label = freq.toFixed(0) + ' Hz';
                    } else {
                        freq_label = (freq/1000).toFixed(1) + ' kHz';
                    }
                    
                    frequency_data[freq_label] = top[i].toFixed(1);
                }
                
                // Update the table source with a structure where each column is a frequency
                // and we only have a single row of values
                const table_data = { 'value': ['dB'] };  // The row header
                
                // Add each frequency as a column
                Object.keys(frequency_data).forEach(freq => {
                    table_data[freq] = [frequency_data[freq]];
                });
                
                // Update the table source
                table_source.data = table_data;
                """
            )
            
            # Attach callback to the bar chart source
            freq_bar_source.js_on_change('data', update_table_callback)
            logger.debug("Connected frequency bar chart to frequency table with JS callback")
        else:
            logger.warning("Could not connect frequency bar to table - sources not available")
    
    def _create_frequency_data_table(self) -> LayoutDOM:
        """
        Creates a data table for displaying frequency analysis values in a format
        easy to copy to Excel. Displays as a single row with frequencies as column headers.
        
        Returns:
            LayoutDOM: Layout containing the data table with frequency values
        """
        logger.debug("Creating frequency data table...")
        
        # Get sources
        freq_table_source = self.bokeh_models['sources']['frequency']['table']
        
        if not freq_table_source:
            logger.error("Frequency table source is missing, cannot create table")
            return None
        
        # Initialize with dummy data - will be replaced by the callback
        freq_table_source.data = {
            'value': ['dB'],
            '31.5 Hz': ['--'],
            '63 Hz': ['--'],
            '125 Hz': ['--'],
            '250 Hz': ['--'],
            '500 Hz': ['--'],
            '1000 Hz': ['--'],
            '2000 Hz': ['--'],
            '4000 Hz': ['--'],
            '8000 Hz': ['--']
        }
        
        # Create table columns - one for the row header and one for each frequency
        table_columns = [
            TableColumn(field="value", title="")  # Row header column
        ]
        
        # Add a column for each dummy frequency (will be replaced by callback)
        for freq in ['31.5 Hz', '63 Hz', '125 Hz', '250 Hz', '500 Hz', '1000 Hz', '2000 Hz', '4000 Hz', '8000 Hz']:
            table_columns.append(TableColumn(field=freq, title=freq))
        
        # Create the data table
        data_table = DataTable(
            source=freq_table_source,
            columns=table_columns,
            width=800,  # Wider to accommodate more columns
            height=100,  # Shorter since we only have one row
            index_position=None,
            selectable=True,
            name="frequency_data_table",
            sizing_mode="fixed"
        )
        
        # Create table header with CSS styling
        table_header = Div(
            text="""<div style="background-color: #f9f9f9; padding: 10px; margin-top: 20px; border-radius: 5px 5px 0 0;">
                  <h3 style="margin-top: 0; margin-bottom: 5px;">Frequency Data Table</h3>
                  </div>""",
            width=800,
            sizing_mode="fixed"
        )
        
        # Create help text with CSS styling
        help_text = Div(
            text="""<div style="background-color: #f9f9f9; padding: 10px; border-radius: 0 0 5px 5px;">
                  <p style="margin-top: 5px; margin-bottom: 0; font-size: 0.9em; color: #666;">
                  Click and drag to select values, then copy (Ctrl+C) and paste into Excel.
                  </p></div>""",
            width=800,
            sizing_mode="fixed"
        )
        
        # Add a wrapper div for the table itself to maintain styling consistency
        table_wrapper = Div(
            text="""<div style="background-color: #f9f9f9; padding: 0 10px;"></div>""",
            width=800,
            height=1,
            sizing_mode="fixed"
        )
        
        # Arrange in a layout without unsupported attributes
        table_layout = column(
            table_header,
            table_wrapper,
            data_table,
            help_text,
            spacing=0,
            css_classes=["freq-data-table-container"]
        )
        
        logger.info("Created frequency data table with frequencies as column headers")
        return table_layout

    def _create_position_charts(self) -> tuple[list, list, bool]:
        """
        Creates charts for each position in the dataset.
        
        Iterates through each position in the position_data dictionary and creates
        the appropriate charts (overview, log, spectral) based on available data.
        Groups charts by position and assembles them into a coherent layout.
        
        Returns:
            tuple:
                - list: All UI elements (headers, charts) to include in the final layout
                - list: All time series charts for linking time axes and interactions
                - bool: Flag indicating if any spectral data was found
        """
        logger.info("Creating charts for all positions...")
        all_elements = [] # All UI chart elements to include in the final layout
        all_position_time_series_charts = [] # Collect all time series charts across positions
        has_any_spectral = False

        chart_creators = {
            'overview': (self._create_overview_chart, create_TH_chart, self.chart_settings["low_freq_height"], "Overview"),
            'log': (self._create_overview_chart, create_log_chart, self.chart_settings["high_freq_height"], "Log Data"),
        }
               
        # Store UI elements by position for visibility toggling
        self.bokeh_models['ui']['position_elements'] = {}
        
        # All UI control functions are imported at the top of the file

        for position, data_dict in self.position_data.items():
            position_charts = []
            position_time_series_charts = []
            
            # Create charts for each standard data type
            for data_key, creator_info in chart_creators.items():
                creator_method, chart_func, height, title = creator_info
                chart = creator_method(position, data_dict, data_key, chart_func, height, title)
                if chart:
                    position_charts.append(chart)
                    position_time_series_charts.append(chart)
            
            # Create Spectral Chart
            spectral_chart, position_has_spectral, hover_info_div = self._create_spectral_chart(position, data_dict)
            if position_has_spectral:
                has_any_spectral = True # Mark if *any* position had spectral
            if spectral_chart:
                position_charts.append(spectral_chart)
                position_time_series_charts.append(spectral_chart)
                

            # Add the position's charts to the overall list if any were created
            if position_charts:
                # Check if this position has audio data
                has_audio = 'audio' in data_dict and data_dict['audio'] is not None
                
                # Create header components
                position_header_text = f"<h2 style='margin-top: 20px; margin-bottom: 10px; border-bottom: 1px solid #ddd; display: inline-block;'>{position}</h2>"
                position_header = Div(
                    text=position_header_text,
                    sizing_mode="stretch_width",
                    css_classes=["position-header"]
                )
                
                # Initialize position elements container if not exists
                if position not in self.bokeh_models['ui']['position_elements']:
                    self.bokeh_models['ui']['position_elements'][position] = {
                        'header': None,
                        'header_row': None,
                        'charts': {},
                        'hover_div': None
                    }
                
                # If position has audio, create a play button for it
                if has_audio and self.audio_handler_available:
                    # Create a play button for this position
                    position_play_button = create_position_play_button(position, self.audio_handler_available)
                    
                    # Store in models for access in callbacks
                    if 'position_buttons' not in self.bokeh_models['ui']['controls']['playback']:
                        self.bokeh_models['ui']['controls']['playback']['position_buttons'] = {}
                    self.bokeh_models['ui']['controls']['playback']['position_buttons'][position] = position_play_button
                    
                    # Create a row with the header and play button
                    header_row = row(
                        children=[position_header, position_play_button],
                        css_classes=["position-header-row"],
                        name=f"{position}_header_row"
                    )
                    all_elements.append(header_row)
                    
                    # Store header row for visibility toggling
                    self.bokeh_models['ui']['position_elements'][position]['header_row'] = header_row
                    self.bokeh_models['ui']['position_elements'][position]['header'] = position_header
                else:
                    # Just add the header without a play button
                    all_elements.append(position_header)
                    
                # Add charts and hover info to list of elements
                for chart in position_charts:
                    chart_name = chart.name
                    chart_type = chart_name.split('_')[1]  # Get the type from chart name e.g., "position_overview"
                    self.bokeh_models['ui']['position_elements'][position]['charts'][chart_type] = chart
                    
                all_elements.extend(position_charts)
                
                if hover_info_div is not None:
                    all_elements.append(hover_info_div)
                    self.bokeh_models['ui']['position_elements'][position]['hover_div'] = hover_info_div
                    
                all_position_time_series_charts.extend(position_time_series_charts)
                logger.debug(f"Collected charts for position {position}")
            else:
                 logger.warning(f"No charts generated for position {position}, skipping.")

        logger.info(f"Finished collecting position charts. Total time series charts: {len(all_position_time_series_charts)}")
        return all_elements, all_position_time_series_charts, has_any_spectral

    def _create_overview_chart(self, position: str, data_dict: dict, data_key: str, 
                              creator_func, height: int, base_title: str) -> figure:
        """
        Creates a single overview or log chart for a position.
        
        Args:
            position (str): Position identifier (e.g., 'NE', 'SW')
            data_dict (dict): Data dictionary for this position
            data_key (str): Key to access the data in the dictionary ('overview' or 'log')
            creator_func (callable): Function to create the chart (create_TH_chart or create_log_chart)
            height (int): Height of the chart in pixels
            base_title (str): Base title string for the chart
            
        Returns:
            figure: Bokeh figure object if created successfully, None otherwise
        """
        df = data_dict.get(data_key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            source_key = f"{position}_{data_key}"
            chart_title = f"{position} - {base_title}"
            chart, source = creator_func(df, title=chart_title, height=height)
            if chart and source:
                chart.name = source_key # Essential for JS lookup
                self.bokeh_models['sources']['data'][source_key] = source
                self.bokeh_models['charts']['all'].append(chart)
                self.bokeh_models['charts']['time_series'].append(chart)
                logger.debug(f"Created {data_key} chart for {position}")
                return chart # Return the created chart
            else:
                logger.error(f"Failed to create {data_key} chart for {position}")
        else:
            logger.info(f"No {data_key} data found or DataFrame empty for {position}")
        return None # Return None if chart creation failed

    def _create_spectral_chart(self, position: str, data_dict: dict) -> tuple[figure, bool, Div]:
        """
        Creates the spectral chart for a position and prepares data for all parameters.
        
        This method:
        1. Extracts the spectral DataFrame for the position
        2. Identifies all available spectral parameters
        3. Prepares data for all parameters upfront
        4. Creates a chart using the default parameter's data
        5. Stores all prepared data in the bokeh_models for JS parameter switching
        
        Args:
            position (str): Position identifier (e.g., 'NE', 'SW')
            data_dict (dict): Data dictionary for this position
            
        Returns:
            tuple:
                - figure: Bokeh figure object if created successfully, None otherwise
                - bool: Flag indicating if any spectral data was found (True) or not (False)
        """
        spectral_df = data_dict.get('spectral')
        if not isinstance(spectral_df, pd.DataFrame) or spectral_df.empty:
            logger.info(f"No spectral data found or DataFrame empty for {position}")
            return None, False, None # Return None chart, False for has_spectral, None for hover_info_div
            
        source_key = f"{position}_spectral" # Base key
        chart_title_base = f"{position} - Spectral Data"
        
        # Find available parameters using the helper function
        position_spectral_params = extract_spectral_parameters(spectral_df)

        if not position_spectral_params:
            logger.warning(f"No suitable spectral parameters found in data for {position}")
            return None, False, None

        # Update the global set of all spectral params found
        self._all_spectral_params.update(position_spectral_params)
        
        # Initialize the param chart structure for this position
        if position not in self.bokeh_models['spectral_data']:
            self.bokeh_models['spectral_data'][position] = {}
        
        # Store available parameters for JavaScript parameter switching
        self.bokeh_models['spectral_data'][position]['available_params'] = position_spectral_params

        # Determine default parameter
        default_param = self.chart_settings.get("default_spectral_param", "LZeq")
        if default_param not in position_spectral_params:
            selected_default_param = position_spectral_params[0]
            logger.warning(f"Default param '{default_param}' not in {position_spectral_params} for {position}, using '{selected_default_param}'.")
        else:
            selected_default_param = default_param
            
        # Store which parameter is currently displayed
        self.bokeh_models['spectral_data'][position]['current_param'] = selected_default_param
        
        # Prepare data for ALL parameters upfront
        logger.info(f"Preparing data for all {len(position_spectral_params)} parameters for position {position}")
        prepared_data_by_param = {}
        
        for param in position_spectral_params:
            # Pre-process the data for each parameter
            param_data = prepare_spectral_image_data(spectral_df, param, self.chart_settings)
            if param_data:
                prepared_data_by_param[param] = param_data
                logger.debug(f"Prepared data for {position} - {param}")
            else:
                logger.error(f"Failed to prepare data for {position} - {param}")
                
        # Store all prepared data
        self.bokeh_models['spectral_data'][position]['prepared_data'] = prepared_data_by_param
                
        # Check if we have prepared data for the default parameter
        if selected_default_param not in prepared_data_by_param:
            logger.error(f"Failed to prepare data for default parameter {selected_default_param}")
            return None, True, None # We've prepared some data, just not the default
            
        # Create the spectrogram figure ONLY for the default parameter
        chart, source, hover_info_div = make_image_spectrogram(
            param=selected_default_param,
            df=None,
            bar_source=self.bokeh_models['sources']['frequency']['bar'],
            bar_x_range=self.bokeh_models['frequency_analysis']['bar_chart']['x_range'],
            position=position,
            title=chart_title_base,
            height=self.chart_settings["spectrogram_height"],
            prepared_data=prepared_data_by_param[selected_default_param]
        )

        if chart and source:
            chart.name = source_key
            # Store in the standard collections
            self.bokeh_models['sources']['data'][source_key] = source
            self.bokeh_models['charts']['all'].append(chart)
            self.bokeh_models['charts']['time_series'].append(chart)
            
            logger.info(f"Created spectral chart for {position} with default parameter {selected_default_param}")
            logger.info(f"Stored data for {len(prepared_data_by_param)} parameters for position {position}")
            return chart, True, hover_info_div # Return created chart, True for has_spectral, hover_info_div
        else:
            logger.error(f"Failed to create spectral chart figure for {position} with parameter {selected_default_param}")
            return None, True, None # Return None chart, True for has_spectral, None for hover_info_div
            
    def _create_shared_range_selector(self, time_series_charts: list) -> RangeSlider:
        """
        Creates a single shared range selector for all time series charts.
        
        The range selector allows users to zoom the time axis of all charts simultaneously.
        It attaches to the chart with the longest time series but affects all linked charts.
        It also sets the global min/max x values from all charts as the x-axis limits.
        
        Args:
            time_series_charts (list): List of time series charts to link with the range selector
            
        Returns:
            RangeSlider: Bokeh RangeSlider object if created successfully, None otherwise
        """
        if not time_series_charts:
            logger.warning("No time series charts found, cannot create range selector.")
            return None

        # Find the chart with the longest time series and calculate global min/max
        longest_chart = None
        longest_range = None
        global_min_x = None
        global_max_x = None
        
        for chart in time_series_charts:
            chart_source_key = chart.name
            chart_source = self.bokeh_models['sources']['data'].get(chart_source_key)
            
            if not chart_source:
                logger.warning(f"Could not find source '{chart_source_key}' for range calculation")
                continue
                
            df = chart_source.to_df()
            if 'Datetime' not in df.columns:
                logger.warning(f"Chart {chart_source_key} has no Datetime column, skipping")
                continue
                
            # Calculate range
            min_x = df['Datetime'].min()
            max_x = df['Datetime'].max()
            
            # Update global min/max
            if global_min_x is None or min_x < global_min_x: global_min_x = min_x
            if global_max_x is None or max_x > global_max_x: global_max_x = max_x
                
            # Check if this is the longest range
            time_range = max_x - min_x
            if longest_range is None or time_range > longest_range:
                longest_range = time_range
                longest_chart = chart
        
        if not longest_chart:
            logger.warning("Could not determine longest chart, using first chart as fallback")
            longest_chart = time_series_charts[0]
            
        chart_source_key = longest_chart.name
        chart_source = self.bokeh_models['sources']['data'].get(chart_source_key)
        
        if not chart_source:
            logger.error(f"Could not find source '{chart_source_key}' for shared range selector")
            return None

        try:
            # Create range selector using the chart with the longest time series
            range_selector = create_range_selector(
                attached_chart=longest_chart,
                source=chart_source
            )
            
            # Set the x_range to the global min/max
            if global_min_x != float('inf') and global_max_x != float('-inf'):
                longest_chart.x_range.start = global_min_x
                longest_chart.x_range.end = global_max_x
                logger.debug(f"Set global x range: {global_min_x} to {global_max_x}")
            
            range_selector.name = 'shared_range_selector'
            self.bokeh_models['ui']['visualization']['range_selectors']['shared'] = range_selector
            self.bokeh_models['charts']['time_series'].append(range_selector)
            self.bokeh_models['charts']['all'].append(range_selector)
            
            logger.debug(f"Created shared range selector, attached to chart with longest range: {chart_source_key}")
            return range_selector
        except Exception as e:
            logger.error(f"Failed to create shared range selector: {e}", exc_info=True)
            return None

    def _create_frequency_analysis_section(self):
        """Creates the frequency analysis section with bar chart.
                Assembles the frequency bar chart into a row layout
        with an appropriate header. This section shows frequency slices when
        users hover over or click on spectrograms.
        
        Returns:
            LayoutDOM: Column layout containing the frequency analysis section if
                     components are available, None otherwise
        """
        logger.debug("Creating frequency analysis section...")
        
        # Create frequency header
        freq_header = Div(
            text="<h2>Frequency Analysis</h2>",
            sizing_mode="stretch_width"
        )
        
        # Return the column with frequency chart
        if self.bokeh_models['frequency_analysis']['bar_chart']['figure']:
            return column(freq_header, self.bokeh_models['frequency_analysis']['bar_chart']['figure'], sizing_mode="stretch_width")
        return column(freq_header, sizing_mode="stretch_width")

    def _create_controls_area(self) -> LayoutDOM:
        """
        Creates the main control bar layout containing UI elements.
        
        Assembles playback controls (play/pause buttons) and spectral parameter
        selection dropdown into a single row layout. The controls allow users
        to interact with audio playback and switch between different spectral parameters.
        
        Returns:
            LayoutDOM: Row layout containing the control elements
        """
        logger.debug("Creating controls area...")
        control_elements = []

        # Playback Controls
        # create_playback_controls returns a dict of models {'play_button': Button, ...}
        self.bokeh_models['ui']['controls']['playback'] = create_playback_controls(self.audio_handler_available)
        
        # Arrange playback buttons in a row
        if self.audio_handler_available:
            playback_buttons = [
                self.bokeh_models['ui']['controls']['playback'].get('play_button'),
                self.bokeh_models['ui']['controls']['playback'].get('pause_button')
            ]
            # Filter out None values
            playback_buttons = [btn for btn in playback_buttons if btn is not None]
            if playback_buttons:
                playback_row = row(*playback_buttons, spacing=5)
                control_elements.append(playback_row)
                logger.debug("Playback controls added to controls area.")

        # Create visibility controls for charts
        visibility_controls = self._create_chart_visibility_controls()
        if visibility_controls:
            control_elements.append(visibility_controls)
            logger.debug("Chart visibility controls added to controls area.")

        # Spectral Parameter Selector (only if spectral parameters were found)
        spectral_params = sorted(list(self._all_spectral_params))
        if spectral_params:
            # Determine default parameter
            default_param = self.chart_settings.get("default_spectral_param", "LZeq")
            if default_param not in spectral_params:
                default_param = spectral_params[0] # Fallback to first available

            # create_parameter_selector returns (Select widget, hidden Div widget)
            param_select_widget, param_holder_div = create_parameter_selector(spectral_params, default_param)
            self.bokeh_models['ui']['controls']['parameter']['select'] = param_select_widget
            self.bokeh_models['ui']['controls']['parameter']['holder'] = param_holder_div

            control_elements.append(self.bokeh_models['ui']['controls']['parameter']['select'])
            # The param_holder is hidden, but needs to be available.
            # It should be added explicitly to the doc roots in app.py if not referenced by layout.
            logger.debug(f"Parameter selector added to controls area. Params: {spectral_params}")
        else:
            logger.debug("No spectral parameters found across all positions, skipping parameter selector creation.")

        # Assemble controls layout (e.g., in a row with spacers for alignment)
        # Using Spacer to push controls apart might be useful depending on desired look
        # Example: row(playback_row, Spacer(width=50), param_select_widget_if_exists)
        controls_layout = row(*control_elements, sizing_mode="stretch_width") # Simple row for now
        logger.info("Controls area layout created.")
        return controls_layout

    def _create_chart_visibility_controls(self) -> LayoutDOM:
        """
        Creates checkboxes to toggle chart visibility grouped by position.
        
        Returns:
            LayoutDOM: Layout containing visibility control checkboxes
        """
        logger.debug("Creating chart visibility controls...")
        
        # Dictionary to store chart types available for each position
        position_chart_types = {}
        
        # Collect chart types for each position
        for position, data_dict in self.position_data.items():
            chart_types = []
            if isinstance(data_dict.get('overview'), pd.DataFrame) and not data_dict.get('overview').empty:
                chart_types.append('overview')
            if isinstance(data_dict.get('log'), pd.DataFrame) and not data_dict.get('log').empty:
                chart_types.append('log')
            if isinstance(data_dict.get('spectral'), pd.DataFrame) and not data_dict.get('spectral').empty:
                chart_types.append('spectral')
            
            if chart_types:
                position_chart_types[position] = chart_types
                logger.debug(f"Position '{position}' has chart types: {chart_types}")
        
        if not position_chart_types:
            logger.warning("No positions with charts found for visibility controls.")
            return None
        
        # Log positions in position_elements for debugging
        logger.debug(f"Positions in position_elements: {list(self.bokeh_models['ui']['position_elements'].keys())}")
        
        # Store checkbox groups for JavaScript callbacks
        self.bokeh_models['ui']['controls']['visibility'] = {}
        
        # Create a header for all visibility controls
        visibility_header = Div(
            text="<div style='font-weight: bold; margin-bottom: 5px;'>Chart Visibility</div>",
            width=100
        )
        
        # Create a container for position controls in a single row
        position_controls_row = []
        
        # Helper function to truncate position names
        def truncate_position_name(position, max_length=20):
            if len(position) <= max_length:
                return position
            # Truncate and add ellipsis
            return position[:max_length-3] + "..."
        
        # Create controls for each position in a single row
        for position in sorted(position_chart_types.keys()):
            logger.debug(f"Processing visibility controls for position: '{position}'")
            chart_types = position_chart_types[position]
            
            # Get the actual charts for this position
            position_elements = self.bokeh_models['ui']['position_elements'].get(position, {})
            position_charts = position_elements.get('charts', {})
            
            if not position_charts:
                logger.warning(f"No charts found for position '{position}' in position_elements")
                # Create controls anyway - don't skip positions
            
            # Create a checkbox group for this position's chart types
            checkbox_labels = [f"{t.capitalize()}" for t in chart_types]
            checkbox_group = CheckboxGroup(
                labels=checkbox_labels,
                active=list(range(len(chart_types))),  # All charts active by default
                name=f"{position}_visibility",
                width=120
            )
            
            # Store the checkbox group with position and chart type information
            self.bokeh_models['ui']['controls']['visibility'][position] = {
                'widget': checkbox_group,
                'chart_types': chart_types
            }
            
            # Add position label with truncated name and checkboxes to the row
            truncated_position = truncate_position_name(position)
            position_label = Div(
                text=f"<div style='font-weight: bold;' title='{position}'>{truncated_position}</div>",
                width=85  # Increased width to accommodate truncated names better
            )
            
            position_control = row(position_label, checkbox_group, spacing=5)
            position_controls_row.append(position_control)
            logger.debug(f"Added visibility control UI for position: '{position}'")
            
            # Add the visibility callback for this position's checkbox group
            self._add_position_checkbox_callback(position, checkbox_group, chart_types)
        
        # Check if any controls were created
        if not position_controls_row:
            logger.warning("No position controls were created")
            return None
            
        # Arrange all controls in a row layout with clean spacing
        visibility_layout = column(
            visibility_header,
            Div(text="<div style='margin-top: 8px;'></div>", sizing_mode="stretch_width"),
            row(*position_controls_row, spacing=10),
            css_classes=["visibility-controls"],
            background="#f5f5f5",
            margin=(0, 0, 10, 0)
        )
        
        logger.info(f"Created visibility controls for {len(position_chart_types)} positions.")
        return visibility_layout

    def _add_position_checkbox_callback(self, position, checkbox_group, chart_types):
        """
        Adds JavaScript callback to handle chart visibility toggling for a position.
        
        Args:
            position (str): Position identifier
            checkbox_group (CheckboxGroup): The checkbox widget for this position
            chart_types (list): List of chart types for this position
        """
        logger.debug(f"Setting up chart visibility toggle callback for position '{position}'...")
        
        # Get position elements from the stored references
        position_elements = self.bokeh_models['ui']['position_elements'].get(position, {})
        position_header = position_elements.get('header')
        position_header_row = position_elements.get('header_row')
        position_charts = position_elements.get('charts', {})
        hover_div = position_elements.get('hover_div')
        
        # Log available chart types for debugging
        logger.debug(f"Available chart types for position '{position}': {chart_types}")
        logger.debug(f"Position charts found: {list(position_charts.keys()) if position_charts else 'None'}")
        
        # Build args dictionary for the checkbox group callback
        checkbox_args = {}
        
        # Add header elements to args if they exist
        if position_header:
            checkbox_args['header'] = position_header
            logger.debug(f"Added header for position '{position}' to callback args")
        if position_header_row:
            checkbox_args['header_row'] = position_header_row
            logger.debug(f"Added header_row for position '{position}' to callback args")
        if hover_div:
            checkbox_args['hover_div'] = hover_div
            logger.debug(f"Added hover_div for position '{position}' to callback args")
        
        # Add charts that exist to args
        missing_charts = []
        for chart_type in chart_types:
            chart = position_charts.get(chart_type)
            if chart:
                checkbox_args[f'chart_{chart_type}'] = chart
                logger.debug(f"Added chart '{chart_type}' for position '{position}' to callback args")
            else:
                missing_charts.append(chart_type)
        
        if missing_charts:
            logger.warning(f"Some charts for position '{position}' not found: {missing_charts}")
        
        # If there are no charts or UI elements to control, don't add a callback
        if len(checkbox_args) <= 1:  # Only debug_position is present
            logger.warning(f"No charts or UI elements to control for position '{position}', skipping callback")
            return
            
        # Store position in JavaScript callback for clarity
        checkbox_args['debug_position'] = position
                
        # Create JavaScript callback for the checkbox group
        checkbox_callback_code = """
        // Get the active indices from the checkbox group
        const active_indices = cb_obj.active;
        const chart_types = %s;
        const position = debug_position;
        
        console.log(`Toggling visibility for position: ${position}`);
        console.log(`Active indices: ${active_indices}`);
        console.log(`Chart types: ${chart_types}`);
        
        // Track if any charts are visible
        let any_visible = active_indices.length > 0;
        
        // Update visibility for each chart type
        chart_types.forEach((type, index) => {
            const chart_var = 'chart_' + type;
            console.log(`Looking for chart variable: ${chart_var}`);
            
            // Check if this chart exists in our args
            if (typeof window[chart_var] === 'undefined' && 
                typeof eval('typeof ' + chart_var) === 'undefined') {
                console.log(`Chart not found for type: ${type}, skipping`);
                return; // Skip this chart
            }
            
            try {
                const chart = eval(chart_var);
                if (chart) {
                    // Check if this chart type is in the active list
                    const is_visible = active_indices.includes(index);
                    console.log(`Setting ${type} chart visibility to: ${is_visible}`);
                    chart.visible = is_visible;
                }
            } catch (error) {
                console.error(`Error toggling chart ${type}:`, error);
            }
        });
        
        // Toggle position header visibility - only show if at least one chart is visible
        if (header_row) {
            console.log(`Setting header_row visibility to: ${any_visible}`);
            header_row.visible = any_visible;
        } else if (header) {
            console.log(`Setting header visibility to: ${any_visible}`);
            header.visible = any_visible;
        }
        
        // Toggle hover div visibility if it exists
        if (hover_div) {
            console.log(`Setting hover_div visibility to: ${any_visible}`);
            hover_div.visible = any_visible;
        }
        """ % chart_types
        
        js_callback = CustomJS(args=checkbox_args, code=checkbox_callback_code)
        checkbox_group.js_on_change('active', js_callback)
        logger.debug(f"Added visibility toggle callback for position '{position}' with {len(checkbox_args)} args")

    def _add_interactions(self) -> None:
        """Adds hover and tap interactions to the charts."""
        logger.debug("Adding interactions (hover, tap)...")
        
        # Link x ranges if option is enabled
        if self.visualization_settings.get("link_x_ranges", True) and len(self.bokeh_models['charts']['time_series']) > 1:
            logger.debug("Linking x ranges of time series charts...")
            link_x_ranges(self.bokeh_models['charts']['time_series'])
        
        # Add hover and tap interactions for positioning time indicators
        # Skip if no time series charts
        if not self.bokeh_models['charts']['time_series']:
            logger.warning("No time series charts available for interactions")
            return
        
        # Collect all charts that should have interactions
        charts_to_interact = self.bokeh_models['charts']['time_series']
        if self.bokeh_models['ui']['visualization']['range_selectors'].get('shared'):
            charts_to_interact.append(self.bokeh_models['ui']['visualization']['range_selectors']['shared'])
        
        all_sources = self.bokeh_models['sources']['data']
        bar_source = self.bokeh_models['sources']['frequency']['bar']
        bar_x_range = self.bokeh_models['frequency_analysis']['bar_chart']['x_range']
        param_holder = self.bokeh_models['ui']['controls']['parameter']['holder']
        
        # Get spectral param charts for hover
        for position, params_data in self.bokeh_models['spectral_data'].items():
            pass  # Just iterating to validate
        
        # --- Add Interactions ---
        from .interactive import add_hover_interaction, add_tap_interaction
        
        # Add hover interaction
        add_hover_interaction(
            charts=charts_to_interact,
            sources=all_sources,
            bar_source=bar_source,
            bar_x_range=bar_x_range,
            hover_info_div=None,
            selected_param_holder=param_holder,
            all_positions_spectral_data=self.bokeh_models['spectral_data']
        )
        
        # Add tap interaction
        click_lines_list, labels_list = add_tap_interaction(
            charts=charts_to_interact,
            sources=all_sources,
            bar_source=bar_source,
            bar_x_range=bar_x_range,
            hover_info_div=None,
            selected_param_holder=param_holder,
            all_positions_spectral_data=self.bokeh_models['spectral_data']
        )
        
        # Store in bokeh_models for JS access
        self.bokeh_models['ui']['visualization']['click_lines'] = click_lines_list
        self.bokeh_models['ui']['visualization']['labels'] = labels_list
        
        logger.debug(f"Added interaction elements: {len(click_lines_list)} click lines, {len(labels_list)} labels")

    def add_chart(self, chart):
        """Add a chart to the builder's collection."""
        logger.debug("Adding chart to collections")
        if chart:
            self.bokeh_models['charts']['all'].append(chart)