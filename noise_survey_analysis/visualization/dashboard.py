import logging
import pandas as pd
import numpy as np
from bokeh.plotting import figure # Ensure figure is imported if used directly
from bokeh.layouts import column, row, gridplot, Spacer, LayoutDOM, Row
from bokeh.models import ColumnDataSource, Div, Spacer as BokehSpacer, RangeSlider, Tabs, TabPanel, CustomJS, Button
from bokeh.events import Tap, DocumentReady
from bokeh.io import curdoc
# Import necessary components from within the visualization package
from .visualization_components import (
    create_TH_chart, create_log_chart, make_image_spectrogram,
    create_frequency_bar_chart, link_x_ranges
)
from .interactive import (
    create_range_selector, add_hover_interaction, add_tap_interaction,
    initialize_global_js
)
# Import UI component creation functions
from ..ui.controls import create_playback_controls, create_parameter_selector, create_position_play_button
# Import spectral data processing
from ..core.data_processors import prepare_spectral_image_data
from ..core.data_loaders import extract_spectral_parameters
from ..js.loader import get_combined_js
logger = logging.getLogger(__name__)

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

        # Internal state to store created models
        self.bokeh_models = {
            # Charts and Sources
            'all_charts': [],                  # List of all Bokeh Figure objects
            'time_series_charts': [],          # Charts with a time-based x-axis 
            'all_sources': {},                 # Dictionary of {source_key: ColumnDataSource}
            
            # Interactive Elements
            'click_lines': {},                 # Vertical lines for clicked positions
            'labels': {},                      # Text labels for data at clicked positions
            'range_selectors': {},             # Range selectors for zooming time series
            'playback_source': None,           # Data source for playback position
            
            # UI Controls
            'playback_controls': {},           # Play/pause buttons
            'param_select': None,              # Dropdown for spectral parameter selection
            'param_holder': None,              # Hidden Div holding selected parameter
            
            # Frequency Analysis
            'freq_bar_chart': None,            # Frequency bar chart
            'freq_bar_source': None,           # Data source for frequency bar chart
            'freq_bar_x_range': None,          # X range for frequency bar chart
            
            # Spectral Data
            'spectral_param_charts': {},       # Position and parameter specific data
                                              # Structure: {
                                              #   position: {
                                              #     'available_params': [...],  # List of available params
                                              #     'current_param': 'LZeq',    # Currently selected param
                                              #     'prepared_data': {          # Pre-processed data by param
                                              #       'LZeq': {...},
                                              #       'LAF90': {...}
                                              #     }
                                              #   }
                                              # }
            'test_js_button': None,           # Button to manually trigger JS init
            
            # JavaScript Integration
            'charts_for_js': [],              # Charts that need JS interactions
        }
        
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
        if has_spectral:
            freq_analysis_section = self._create_frequency_analysis_section()
        
        # --- 6. Add interactions after all charts are created ---
        self._add_interactions()
        
        # --- 7. Assemble the Main Layout ---
        # Order: Title at top, followed by controls, then range selector,
        # then all position charts, and frequency analysis at the bottom.
        layout_components = []
        
        # Add title
        layout_components.append(title_div)
        
        # Add the Test JS Button at the top
        test_button = self.bokeh_models.get('test_js_button')
        if test_button:
             layout_components.append(test_button)
             logger.debug("Test JS Init button added to the top of the layout.")
        
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
            test_button = self.bokeh_models.get('test_js_button')
            if test_button:
                test_button.js_on_click(js_init_callback)
                logger.info("JavaScript initialization callback also attached to test button's click event.")
        
        logger.info("Dashboard build complete.")
        return main_layout

    def _create_shared_components(self):
        """Creates components shared across positions."""
        logger.debug("Creating shared components (playback source, freq bar chart, hover div)...")
        # Playback Source
        self.bokeh_models['playback_source'] = ColumnDataSource(data={'current_time': [0]}, name='playback_source')

        # Seek Command Source - For sending seek commands from JS to Python
        self.bokeh_models['seek_command_source'] = ColumnDataSource(data={'target_time': [None]}, name='seek_command_source')
        
        # Play Request Source - For handling position play button requests from JS to Python
        self.bokeh_models['play_request_source'] = ColumnDataSource(data={'position': [None], 'time': [None]}, name='play_request_source')

        # Test JS Button for manual initialization if needed
        self.bokeh_models['test_js_button'] = Button(
            label="Initialize JS", 
            button_type="success", 
            name="init_js_button"
        )
        logger.debug("Created test_js_button for manual JS initialization.")

        # Frequency Bar Chart & Source (created even if no spectral data initially)
        # This assumes create_frequency_bar_chart returns chart, source, x_range
        (self.bokeh_models['freq_bar_chart'],
         self.bokeh_models['freq_bar_source'],
         self.bokeh_models['freq_bar_x_range']) = create_frequency_bar_chart(
             title="Frequency Slice",
             height=self.chart_settings.get("frequency_bar_height", 200)
        )
        if self.bokeh_models['freq_bar_chart']:
             
             # Store the source in all_sources as well for consistency if needed elsewhere
             self.bokeh_models['all_sources']["frequency_bar"] = self.bokeh_models['freq_bar_source']
        else:
             logger.error("Failed to create shared frequency bar chart.")


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
        
        # Store position play buttons in a dictionary
        position_play_buttons = {}
        
        # Import necessary function
        from ..ui.controls import create_position_play_button

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
                
                # If position has audio, create a play button for it
                if has_audio and self.audio_handler_available:
                    # Create a play button for this position
                    position_play_button = create_position_play_button(position, self.audio_handler_available)
                    
                    # Store in models for access in callbacks
                    if 'position_play_buttons' not in self.bokeh_models:
                        self.bokeh_models['position_play_buttons'] = {}
                    self.bokeh_models['position_play_buttons'][position] = position_play_button
                    
                    # Create a row with the header and play button
                    header_row = Row(
                        children=[position_header, position_play_button],
                        css_classes=["position-header-row"],
                        name=f"{position}_header_row"
                    )
                    all_elements.append(header_row)
                else:
                    # Just add the header without a play button
                    all_elements.append(position_header)
                
                # Add charts and hover info
                all_elements.extend(position_charts)
                if hover_info_div is not None:
                    all_elements.append(hover_info_div)
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
                self.bokeh_models['all_sources'][source_key] = source
                self.bokeh_models['all_charts'].append(chart)
                self.bokeh_models['time_series_charts'].append(chart)
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
        if position not in self.bokeh_models['spectral_param_charts']:
            self.bokeh_models['spectral_param_charts'][position] = {}
        
        # Store available parameters for JavaScript parameter switching
        self.bokeh_models['spectral_param_charts'][position]['available_params'] = position_spectral_params

        # Determine default parameter
        default_param = self.chart_settings.get("default_spectral_param", "LZeq")
        if default_param not in position_spectral_params:
            selected_default_param = position_spectral_params[0]
            logger.warning(f"Default param '{default_param}' not in {position_spectral_params} for {position}, using '{selected_default_param}'.")
        else:
            selected_default_param = default_param
            
        # Store which parameter is currently displayed
        self.bokeh_models['spectral_param_charts'][position]['current_param'] = selected_default_param
        
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
        self.bokeh_models['spectral_param_charts'][position]['prepared_data'] = prepared_data_by_param
                
        # Check if we have prepared data for the default parameter
        if selected_default_param not in prepared_data_by_param:
            logger.error(f"Failed to prepare data for default parameter {selected_default_param}")
            return None, True, None # We've prepared some data, just not the default
            
        # Create the spectrogram figure ONLY for the default parameter
        chart, source, hover_info_div = make_image_spectrogram(
            param=selected_default_param,
            df=None,
            bar_source=self.bokeh_models['freq_bar_source'],
            bar_x_range=self.bokeh_models['freq_bar_x_range'],
            position=position,
            title=chart_title_base,
            height=self.chart_settings["spectrogram_height"],
            prepared_data=prepared_data_by_param[selected_default_param]
        )

        if chart and source:
            chart.name = source_key
            # Store in the standard collections
            self.bokeh_models['all_sources'][source_key] = source
            self.bokeh_models['all_charts'].append(chart)
            self.bokeh_models['time_series_charts'].append(chart)
            
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
            chart_source = self.bokeh_models['all_sources'].get(chart_source_key)
            
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
        chart_source = self.bokeh_models['all_sources'].get(chart_source_key)
        
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
            self.bokeh_models['range_selectors']['shared'] = range_selector
            self.bokeh_models['time_series_charts'].append(range_selector)
            self.bokeh_models['all_charts'].append(range_selector)
            
            logger.debug(f"Created shared range selector, attached to chart with longest range: {chart_source_key}")
            return range_selector
        except Exception as e:
            logger.error(f"Failed to create shared range selector: {e}", exc_info=True)
            return None

    def _create_frequency_analysis_section(self) -> LayoutDOM:
        """
        Creates the layout for the shared frequency analysis components.
        
        Assembles the frequency bar chart into a row layout
        with an appropriate header. This section shows frequency slices when
        users hover over or click on spectrograms.
        
        Returns:
            LayoutDOM: Column layout containing the frequency analysis section if
                     components are available, None otherwise
        """
        if self.bokeh_models.get('freq_bar_chart'):
            freq_header = Div(
                text="<h2 style='margin-top: 30px; margin-bottom: 10px; border-bottom: 1px solid #ddd;'>Frequency Analysis</h2>",
                sizing_mode="stretch_width"
            )
            logger.debug("Created frequency analysis section layout.")
            return column(freq_header, self.bokeh_models['freq_bar_chart'], sizing_mode="stretch_width")
        else:
            logger.error("Shared frequency components (bar chart) are missing. Cannot create section.")
            return None


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
        self.bokeh_models['playback_controls'] = create_playback_controls(self.audio_handler_available)
        # Arrange playback buttons in a row

        # Spectral Parameter Selector (only if spectral parameters were found)
        spectral_params = sorted(list(self._all_spectral_params))
        if spectral_params:
            # Determine default parameter
            default_param = self.chart_settings.get("default_spectral_param", "LZeq")
            if default_param not in spectral_params:
                default_param = spectral_params[0] # Fallback to first available

            # create_parameter_selector returns (Select widget, hidden Div widget)
            param_select_widget, param_holder_div = create_parameter_selector(spectral_params, default_param)
            self.bokeh_models['param_select'] = param_select_widget
            self.bokeh_models['param_holder'] = param_holder_div

            control_elements.append(self.bokeh_models['param_select'])
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


    def _add_interactions(self) -> None:
        """
        Adds interactive elements to charts for user interaction.
        
        This method:
        1. Links x-ranges of time series charts for synchronized panning/zooming
        2. Adds hover interactions for displaying data values and updating frequency charts
        3. Adds tap interactions for persistent vertical lines and labels
        
        The interaction components are stored in the bokeh_models dictionary for 
        later access by JavaScript callbacks.
        
        Returns:
            None
        """
        logger.info("Adding interactions...")

        # --- Link X-Ranges --- (same code as before)
        if self.visualization_settings.get("link_x_ranges", True) and len(self.bokeh_models['time_series_charts']) > 1:
            try:
                link_x_ranges(self.bokeh_models['time_series_charts'])
                logger.debug("X-ranges linked for all time series charts.")
            except Exception as e:
                logger.error(f"Failed to link x-ranges: {e}", exc_info=True)
        else:
             logger.debug("Skipping x-range linking (disabled in settings or < 2 time series charts).")

        # --- Prepare for Hover and Tap Interactions ---
        if not self.bokeh_models['time_series_charts']:
            logger.warning("No time series charts found to add interactions to.")
            return

        # Fetch all necessary models ONCE
        charts_to_interact = self.bokeh_models['time_series_charts']
        if 'range_selectors' in self.bokeh_models and 'shared' in self.bokeh_models['range_selectors'] and self.bokeh_models['range_selectors']['shared']:
            charts_to_interact.append(self.bokeh_models['range_selectors']['shared'])
        all_sources = self.bokeh_models['all_sources']
        bar_source = self.bokeh_models.get('freq_bar_source')
        bar_x_range = self.bokeh_models.get('freq_bar_x_range')
        param_holder = self.bokeh_models.get('param_holder')
        
        # Get spectral sources from position_param_charts instead of directly
        spectral_sources = {}
        for position, params_data in self.bokeh_models.get('spectral_param_charts', {}).items():
            source_key = f"{position}_spectral"
            if source_key in all_sources:
                spectral_sources[position] = all_sources[source_key]

        # Check if essential components for spectral hover/tap are present if spectral data exists
        has_spectral = spectral_sources and any(spectral_sources.values())
        if has_spectral and (not bar_source or not bar_x_range or not param_holder):
            logger.warning("Spectral data exists, but some components required for full spectral hover/tap interaction "
                           "(bar_source, bar_x_range, param_holder) are missing. Interactions might be limited.")

        # --- Add Hover Interaction ---
        try:
            logger.debug(f"Adding hover interactions to {len(charts_to_interact)} charts...")
            add_hover_interaction(
                 charts=charts_to_interact,
                 sources=all_sources,
                 bar_source=bar_source,
                 bar_x_range=bar_x_range,
                 selected_param_holder=param_holder,
                 all_positions_spectral_data=spectral_sources
            )
            logger.info("Hover interactions added.")
        except Exception as e:
            logger.error(f"Failed to add hover interactions: {e}", exc_info=True)


        # --- Add Tap Interaction ---
        try:
            logger.debug(f"Adding tap interactions to {len(charts_to_interact)} charts...")
            click_lines_list, labels_list = add_tap_interaction(
                 charts=charts_to_interact,
                 sources=all_sources,
                 bar_source=bar_source,
                 bar_x_range=bar_x_range,
                 selected_param_holder=param_holder,
                 all_positions_spectral_data=spectral_sources
            )
            # Store the returned LISTS directly using the original keys
            self.bokeh_models['click_lines'] = click_lines_list
            self.bokeh_models['labels'] = labels_list
            logger.info(f"Tap interactions added. Found {len(click_lines_list)} click lines/labels.")

        except Exception as e:
            logger.error(f"Failed to add tap interactions: {e}", exc_info=True)

        logger.info("All interactions processed.") # General message covering both 