import logging
from bokeh.plotting import curdoc
from bokeh.layouts import column, row, LayoutDOM # Ensure column is imported
from bokeh.models import Div, ColumnDataSource, CustomJS, Button, Range1d # Import for assertions and error messages
from bokeh.models import Panel
import pandas as pd
import numpy as np  # Import numpy for array operations
import os
from bokeh.resources import CDN
from bokeh.embed import file_html  # Add import for standalone HTML generation
import logging
import os
from bokeh.events import DocumentReady
from typing import Dict, Any, Optional

import sys
from pathlib import Path
current_file = Path(__file__)
project_root = current_file.parent.parent  # Go up to "Noise Survey Analysis"
sys.path.insert(0, str(project_root))

from noise_survey_analysis.ui.components import (
    TimeSeriesComponent,
    SpectrogramComponent,
    FrequencyBarComponent,
    ComparisonFrequencyBarComponent,
    ControlsComponent,
    RangeSelectorComponent,
    SummaryTableComponent,
    ComparisonPanelComponent,
    create_audio_controls_for_position,
    create_position_title_and_offsets,
    RegionPanelComponent,
    MarkerPanelComponent,
    SidePanelComponent,
)
from noise_survey_analysis.core.data_processors import GlyphDataProcessor
from noise_survey_analysis.core.app_callbacks import AppCallbacks
from noise_survey_analysis.core.data_manager import DataManager, PositionData # Ensure PositionData is imported
from noise_survey_analysis.core.config import (
    CHART_SETTINGS,  # Ensure CHART_SETTINGS is imported
    UI_LAYOUT_SETTINGS,
    LOG_VIEW_MAX_VIEWPORT_SECONDS,
)
from noise_survey_analysis.js.loader import load_js_file

logger = logging.getLogger(__name__)

SIDE_PANEL_WIDTH = UI_LAYOUT_SETTINGS.get('side_panel_width', 320)

def load_js_file(file_name):
    """Loads a JavaScript file from the static/js directory."""
    # Correctly resolve the path to the static/js directory
    static_js_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'js')
    file_path = os.path.join(static_js_dir, file_name)
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

class DashBuilder:
  
    """
    Builds the Bokeh dashboard layout, including charts, widgets, and interactions.
    Orchestrates the creation of visualization components and UI elements.
    """

    def __init__(self, 
                 audio_control_source: Optional[ColumnDataSource] = None, 
                 audio_status_source: Optional[ColumnDataSource] = None,
                 session_action_source: Optional[ColumnDataSource] = None,
                 session_status_source: Optional[ColumnDataSource] = None,
                 control_state_source: Optional[ColumnDataSource] = None,
                 automation_command_source: Optional[ColumnDataSource] = None,
                 automation_result_source: Optional[ColumnDataSource] = None):
        """
        The constructor is lightweight. It only stores references to core handlers
        and initializes containers for the components it will create.

       Args:
            audio_control_source: The shared CDS for sending commands. (Optional)
            audio_status_source: The shared CDS for receiving status. (Optional)
            session_action_source: Shared CDS for JS->Python session commands. (Optional)
            session_status_source: Shared CDS for Python->JS session status updates. (Optional)
            control_state_source: Shared CDS for desired simple UI control state. (Optional)
            automation_command_source: Shared CDS for Python->JS automation commands. (Optional)
            automation_result_source: Shared CDS for JS->Python automation acknowledgements. (Optional)
        """ 
        self.audio_control_source = audio_control_source or ColumnDataSource(data={'command': [], 'position_id': [], 'value': []})
        self.audio_status_source = audio_status_source or ColumnDataSource(data={
            'is_playing': [False], 
            'current_time': [0], 
            'playback_rate': [1.0], 
            'current_file_duration': [0], 
            'current_file_start_time': [0],
            'active_position_id': [None],
            'volume_boost': [False],
            'current_file_name': ['']
            })
        self.session_action_source = session_action_source or ColumnDataSource(
            data={'command': [None], 'request_id': [None], 'payload': [None]},
            name='session_action_source'
        )
        self.session_status_source = session_status_source or ColumnDataSource(
            data={
                'request_id': [None],
                'level': ['info'],
                'message': [''],
                'output_path': [''],
                'done': [False],
                'updated_at': [0],
            },
            name='session_status_source'
        )
        self.control_state_source = control_state_source or ColumnDataSource(
            data={
                'parameter': [None],
                'view_mode': [None],
                'updated_at': [0],
            },
            name='control_state_source'
        )
        self.automation_command_source = automation_command_source or ColumnDataSource(
            data={'command': [None], 'request_id': [None], 'payload': [None]},
            name='automation_command_source'
        )
        self.automation_result_source = automation_result_source or ColumnDataSource(
            data={
                'request_id': [None],
                'success': [False],
                'message': [''],
                'data': [None],
                'updated_at': [0],
            },
            name='automation_result_source'
        )
        
        # These will be populated by the build process
        self.components: Dict[str, Dict[str, Any]] = {}
        self.shared_components: Dict[str, Any] = {}
        self.prepared_glyph_data: Dict[str, Dict[str, Any]] = {}
        self.position_display_titles: Dict[str, str] = {}

    def build_layout(self, doc, app_data: DataManager, chart_settings: dict,
                     source_configs=None,
                     saved_workspace_state=None,
                     job_number=None,
                     server_mode: bool = False):
        """
        The main public method that constructs the entire application layout.
        This is the primary entry point for this class.

        Args:
            doc: The Bokeh document to attach the final layout to.
            app_data: The complete, prepared data object from the DataManager.
            chart_settings: The global dictionary of chart settings.
            source_configs: List of source configuration dictionaries.
            saved_workspace_state: Optional saved workspace state to restore.
            job_number: Optional job number/identifier to display in the dashboard title.
        """
        print("INFO: DashboardBuilder: Starting UI construction...")

        # The sequence of operations is clear and logical
        self.server_mode = bool(server_mode)
        if not self.server_mode:
            self._load_deferred_log_data_for_static(app_data)
        prepared_glyph_data, available_params = self._prepare_glyph_data(app_data)

        self.prepared_glyph_data = prepared_glyph_data
        self.source_configs = source_configs or []
        self.job_number = job_number
        self.position_display_titles = self._extract_position_display_titles(self.source_configs)
        self.saved_workspace_state = saved_workspace_state
        self._create_components(app_data, prepared_glyph_data, available_params, chart_settings)
        self._wire_up_interactions()
        self._assemble_and_add_layout(doc)
        self._initialize_javascript(doc)

        print("INFO: DashboardBuilder: Build complete.")

    # --- Private Helper Methods: The Step-by-Step Build Process ---

    def _prepare_glyph_data(self, app_data: DataManager) -> dict:
        """Step 1: Prepare glyph data for all positions."""
        print("INFO: DashboardBuilder: Preparing glyph data for all positions.")
        
        processor = GlyphDataProcessor()
        all_prepared_glyph_data = {}
        available_params = set()

        for position_name in app_data.positions():
            position_data = app_data[position_name]
            all_prepared_glyph_data[position_name] = processor.prepare_all_spectral_data(position_data)
            
            try:
                available_params.update(all_prepared_glyph_data[position_name]['overview']['available_params'])
                available_params.update(all_prepared_glyph_data[position_name]['log']['available_params'])
            except KeyError: pass

        # Convert back to a list when returning if needed
        return all_prepared_glyph_data, list(available_params)

    def _extract_position_display_titles(self, source_configs: Optional[list]) -> Dict[str, str]:
        titles: Dict[str, str] = {}
        if not source_configs:
            return titles

        for config in source_configs:
            if not isinstance(config, dict):
                continue
            position = config.get('position_name') or config.get('position')
            raw_title = config.get('display_title') or config.get('display_name')
            if not position or not isinstance(raw_title, str):
                continue
            stripped = raw_title.strip()
            if not stripped:
                continue
            titles.setdefault(position, stripped)

        return titles

    def _load_deferred_log_data_for_static(self, app_data: DataManager) -> None:
        """
        Static exports need log datasets embedded up front because no server
        callbacks will stream them after load.
        """
        loaded_positions = 0
        for position_name in app_data.positions():
            position_data = app_data[position_name]
            log_paths = getattr(position_data, 'log_file_paths', None) or []
            already_loaded = bool(getattr(position_data, '_log_data_loaded', False))
            if not log_paths or already_loaded:
                continue

            try:
                logger.info("Static mode: loading deferred log data for %s", position_name)
                position_data.load_log_data_lazy(app_data.parser_factory, app_data.use_cache)
                loaded_positions += 1
            except Exception as exc:
                logger.error("Failed to load deferred log data for %s: %s", position_name, exc, exc_info=True)

        if loaded_positions:
            logger.info("Static mode: loaded deferred log data for %d position(s).", loaded_positions)

    @staticmethod
    def _to_list(value: Any) -> list:
        if value is None:
            return []
        if hasattr(value, 'tolist'):
            value = value.tolist()
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        return [value]

    def _build_static_spectrogram_log_source_data(
        self,
        position_glyph_data: Dict[str, Any],
        preferred_param: str,
    ) -> Optional[Dict[str, list]]:
        log_mode_data = position_glyph_data.get('log') if isinstance(position_glyph_data, dict) else None
        prepared_params = log_mode_data.get('prepared_params', {}) if isinstance(log_mode_data, dict) else {}
        if not prepared_params:
            return None

        param_to_use = preferred_param if preferred_param in prepared_params else next(iter(prepared_params.keys()), None)
        if not param_to_use:
            return None

        prepared = prepared_params.get(param_to_use)
        if not isinstance(prepared, dict):
            return None

        initial_glyph_data = prepared.get('initial_glyph_data') or {}
        image_values = initial_glyph_data.get('image') or []
        if not image_values:
            return None

        image_matrix = image_values[0]
        image_matrix_list = self._to_list(image_matrix)
        levels_flat_list = self._to_list(prepared.get('levels_flat_transposed'))

        return {
            'levels_flat_transposed': [levels_flat_list],
            'times_ms': [self._to_list(prepared.get('times_ms'))],
            'frequency_labels': [self._to_list(prepared.get('frequency_labels'))],
            'frequencies_hz': [self._to_list(prepared.get('frequencies_hz'))],
            'n_times': [int(prepared.get('n_times', 0))],
            'n_freqs': [int(prepared.get('n_freqs', 0))],
            'chunk_time_length': [int(prepared.get('chunk_time_length', 0))],
            'time_step': [prepared.get('time_step', 0)],
            'min_val': [prepared.get('min_val', 0)],
            'max_val': [prepared.get('max_val', 100)],
            'min_time': [prepared.get('min_time', 0)],
            'max_time': [prepared.get('max_time', 0)],
            'initial_glyph_data_x': [self._to_list(initial_glyph_data.get('x'))],
            'initial_glyph_data_y': [self._to_list(initial_glyph_data.get('y'))],
            'initial_glyph_data_dw': [self._to_list(initial_glyph_data.get('dw'))],
            'initial_glyph_data_dh': [self._to_list(initial_glyph_data.get('dh'))],
            'initial_glyph_data_image': [image_matrix_list],
        }

    def _populate_static_log_sources(
        self,
        position_name: str,
        spectrogram_component: SpectrogramComponent,
        position_glyph_data: Dict[str, Any],
        preferred_param: str,
    ) -> None:
        data = self._build_static_spectrogram_log_source_data(position_glyph_data, preferred_param)
        if not data:
            return

        spectrogram_component.log_source.data = data
        logger.debug(
            "Static mode: pre-populated spectrogram log source for %s with keys=%s",
            position_name,
            list(data.keys()),
        )
    
    
    def _create_components(self, app_data: DataManager, prepared_glyph_data: dict, available_params: list, chart_settings: dict):
        """Step 2: Instantiates all component classes for each position."""
        logger.info("DashboardBuilder: Creating individual UI components...")

        self.shared_components['controls'] = ControlsComponent(
            available_params,
            server_mode=getattr(self, 'server_mode', False)
        )
        controls_comp = self.shared_components['controls']
        
        self.shared_components['freq_bar'] = FrequencyBarComponent()

        all_positions = list(app_data.positions())
        self.shared_components['comparison_panel'] = ComparisonPanelComponent(all_positions)
        self.shared_components['comparison_frequency'] = ComparisonFrequencyBarComponent()
        self.shared_components['summary_table'] = SummaryTableComponent(all_positions, ['LAeq', 'LAFmax', 'LAF90'])

        region_panel_div = RegionPanelComponent()
        marker_panel_div = MarkerPanelComponent()
        side_panel = SidePanelComponent(region_panel_div, marker_panel_div)

        self.shared_components['region_panel'] = region_panel_div
        self.shared_components['marker_panel'] = marker_panel_div
        self.shared_components['side_panel'] = side_panel

        first_position_processed = False
        # Create components for each position found in the data
        for position_name in app_data.positions():
            position_data_obj = app_data[position_name] # Get PositionData object
            display_position_data = self._build_position_display_data(position_data_obj)
            position_specific_glyph_data = prepared_glyph_data.get(position_name, {})

            initial_mode = self._determine_initial_display_mode(position_data_obj)
            initial_param_spectrogram = chart_settings.get('default_spectral_parameter', 'LZeq')

            ts_component = TimeSeriesComponent(
                position_data_obj=display_position_data,
                initial_display_mode=initial_mode
            )
            spec_component = SpectrogramComponent(
                position_data_obj=display_position_data,
                position_glyph_data=position_specific_glyph_data,
                initial_display_mode=initial_mode,
                initial_param=initial_param_spectrogram
            )

            if not self.server_mode:
                self._populate_static_log_sources(
                    position_name=position_name,
                    spectrogram_component=spec_component,
                    position_glyph_data=position_specific_glyph_data,
                    preferred_param=initial_param_spectrogram,
                )

            # Create position title and offset controls for all positions
            # (Audio playback buttons are now global)
            position_controls = create_position_title_and_offsets(
                position_id=position_name,
                display_title=position_name  # Could use custom titles from config if available
            )

            self.components[position_name] = {
                'timeseries': ts_component,
                'spectrogram': spec_component,
                'position_controls': position_controls
            }

            controls_comp.add_visibility_checkbox(
                chart_name=ts_component.figure.name,
                chart_label=f"{position_name} TS",
                initial_state=ts_component.figure.visible
            )
            controls_comp.add_visibility_checkbox(
                chart_name=spec_component.figure.name,
                chart_label=f"{position_name} Spec",
                initial_state=spec_component.figure.visible
            )

            if not first_position_processed and hasattr(ts_component, 'figure'):
                self.shared_components['range_selector'] = RangeSelectorComponent(attached_timeseries_component=ts_component)
                logger.info(f"RangeSelectorComponent linked to TimeSeries figure of {position_name}.")
                first_position_processed = True
        
        if not first_position_processed:
            logger.warning("RangeSelectorComponent could not be linked to any TimeSeries figure as no positions were processed or no figure was available.")
            # RangeSelectorComponent will not be added to shared_components in this case


    def _build_position_components(self, position_data):
        """Builds the charts for a single position."""
        
        
    
    def _wire_up_interactions(self):
        """Step 3: Handles the logic that connects components to each other."""
        print("INFO: DashboardBuilder: Wiring up interactions between components...")

        master_x_range = None
        
        # Compute global min/max time across all positions to set initial viewport
        global_min_time = None
        global_max_time = None
        
        for position_name, comp_dict in self.components.items():
            ts_comp = comp_dict['timeseries']
            
            # Extract time range from overview and log sources
            for source in [ts_comp.overview_source, ts_comp.log_source]:
                if source and source.data and 'Datetime' in source.data:
                    datetime_data = source.data['Datetime']
                    if len(datetime_data) > 0:
                        source_min = min(datetime_data)
                        source_max = max(datetime_data)
                        
                        if global_min_time is None or source_min < global_min_time:
                            global_min_time = source_min
                        if global_max_time is None or source_max > global_max_time:
                            global_max_time = source_max
        
        
        # Wire up all charts to share the same x_range
        for position_name, comp_dict in self.components.items():
            ts_comp = comp_dict['timeseries']
            spec_comp = comp_dict['spectrogram']
            controls = self.shared_components['controls']
            freq_bar = self.shared_components['freq_bar']

            if master_x_range is None:
                if self.server_mode:
                    if global_min_time is not None and global_max_time is not None:
                        logger.info(f"Setting master_x_range: start={global_min_time}, end={global_max_time}")
                        initial_start = global_min_time
                        initial_end = global_max_time
                    else:
                        logger.warning("Using default Bokeh auto-range for initial viewport")
                        initial_start = ts_comp.figure.x_range.start
                        initial_end = ts_comp.figure.x_range.end

                    if initial_start is None or initial_end is None:
                        initial_start = 0
                        initial_end = 60000
                    elif initial_start == initial_end:
                        initial_end = initial_start + 60000

                    master_x_range = Range1d(start=initial_start, end=initial_end, name="master_x_range")
                    logger.debug(
                        "Created explicit master_x_range for server_mode=%s: type=%s start=%s end=%s",
                        self.server_mode,
                        type(master_x_range).__name__,
                        master_x_range.start,
                        master_x_range.end,
                    )
                else:
                    # Use an explicit Range1d in static mode so scripted zoom updates persist.
                    if global_min_time is not None and global_max_time is not None:
                        logger.info(f"Setting master_x_range: start={global_min_time}, end={global_max_time}")
                        initial_start = global_min_time
                        initial_end = global_max_time
                    else:
                        logger.warning("Using default Bokeh auto-range for initial viewport")
                        initial_start = ts_comp.figure.x_range.start
                        initial_end = ts_comp.figure.x_range.end

                    if initial_start is None or initial_end is None:
                        initial_start = 0
                        initial_end = 60000
                    elif initial_start == initial_end:
                        initial_end = initial_start + 60000

                    master_x_range = Range1d(start=initial_start, end=initial_end, name="master_x_range")

                range_selector = self.shared_components.get('range_selector')
                if range_selector is not None and hasattr(range_selector, 'range_tool'):
                    range_selector.range_tool.x_range = master_x_range
            
            ts_comp.figure.x_range = master_x_range
            spec_comp.figure.x_range = master_x_range

        #add callback to x_range ranges
        if master_x_range is not None:
            range_update_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers.handleRangeUpdate) {
                    window.NoiseSurveyApp.eventHandlers.handleRangeUpdate(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleRangeUpdate not defined!');
                }
            """)
            master_x_range.js_on_change('end', range_update_js)
        else:
            logger.warning("No master_x_range available; skipping range update callback.")


    def _assemble_and_add_layout(self, doc):
        """Step 4: Gets the .layout() from each component and assembles the final page."""
        print("INFO: DashboardBuilder: Assembling final Bokeh layout...")
        
        position_layouts = []
        for position_name, comp_dict in self.components.items():
            # Add position title and offset controls above the timeseries
            ts_layout = comp_dict['timeseries'].layout()
            ts_layout_with_controls = column(
                comp_dict['position_controls']['layout'],
                ts_layout
            )

            pos_layout = column(
                ts_layout_with_controls,
                comp_dict['spectrogram'].layout(),
                name=f"layout_{position_name}",
                styles={
                    "border": "1px solid #d7dde5",
                    "border-radius": "10px",
                    "padding": "8px 10px",
                    "margin-bottom": "10px",
                    "background-color": "#ffffff",
                    "box-shadow": "0 1px 3px rgba(15, 23, 42, 0.08)",
                }
            )
            position_layouts.append(pos_layout)
        
        # Create the JS initialization trigger Div
        self.js_init_trigger = Div(
            text="", width=0, height=0, visible=False, name="js_init_trigger"
        )

        controls_layout = self.shared_components['controls'].layout()
        range_selector_layout = self.shared_components['range_selector'].layout()

        freq_bar_layout = self.shared_components['freq_bar'].layout() if 'freq_bar' in self.shared_components else Div()
        freq_bar_layout.name = "frequency_bar_layout"
        self.shared_components['freq_bar_layout'] = freq_bar_layout

        comparison_frequency_layout = self.shared_components['comparison_frequency'].layout()
        comparison_frequency_layout.visible = False
        self.shared_components['comparison_frequency_layout'] = comparison_frequency_layout

        main_layout = column(
            controls_layout,
            range_selector_layout,
            *position_layouts,
            freq_bar_layout,
            comparison_frequency_layout,
            self.shared_components['summary_table'].layout(),
            self.js_init_trigger,
            name="main_layout",
        )

        region_panel_layout = self.shared_components['region_panel'].layout()
        region_panel_layout.name = "region_panel_layout"
        region_panel_layout.visible = True
        self.shared_components['region_panel_layout'] = region_panel_layout

        marker_panel_layout = self.shared_components['marker_panel'].layout()
        marker_panel_layout.name = "marker_panel_layout"
        marker_panel_layout.visible = True
        self.shared_components['marker_panel_layout'] = marker_panel_layout

        comparison_panel_layout = self.shared_components['comparison_panel'].layout()
        comparison_panel_layout.visible = False
        comparison_panel_layout.name = "comparison_panel_layout"
        self.shared_components['comparison_panel_layout'] = comparison_panel_layout

        side_panel_tabs = self.shared_components['side_panel'].layout()
        side_panel_tabs.visible = True
        self.shared_components['side_panel_tabs'] = side_panel_tabs

        side_panel_container = column(
            side_panel_tabs,
            comparison_panel_layout,
            name="side_panel_container",
            width=SIDE_PANEL_WIDTH + 32,
        )
        self.shared_components['side_panel_container'] = side_panel_container

        final_layout = row(
            main_layout,
            side_panel_container,
            name="root_layout",
        )

        doc.add_root(final_layout)
        doc.title = "Noise Survey Analysis Dashboard"

    def _load_all_js_files(self):
        """Loads all JavaScript files in the correct order."""
        # Define the order in which JS files should be loaded
        # This order is critical for dependencies to be met before they are used.
        js_files_order = [
                # 1. State Management Core (in dependency order)
                'core/actions.js',
                'features/view/viewResolution.js',
                'features/view/viewReducer.js',
                'features/view/viewSelectors.js',
                'features/view/viewThunks.js',
                'features/interaction/interactionReducer.js',
                'features/markers/markersReducer.js',
                'features/markers/markersSelectors.js',
                'features/markers/markersThunks.js',
                'features/regions/regionReducer.js',
                'features/regions/regionSelectors.js',
                'features/regions/regionUtils.js',
                'features/regions/regionThunks.js',
                'features/interaction/interactionThunks.js',
                'features/audio/audioReducer.js',
                'features/audio/audioThunks.js',
                'core/rootReducer.js',
                'store.js',           # Creates the store, needs rootReducer
                'init.js',            # Creates app.init and reInitializeStore, needs store

                # 2. Core setup and utilities
                'utils.js',
                'comparison-metrics.js',
                'thunks.js',

                # 3. Application modules
                'chart-classes.js',   # Defines Chart classes, needed by registry
                'registry.js',        # Defines the model/controller registry
                'data-processors.js', # (No hard dependencies on others)
                'services/markers/markerPanelRenderer.js',
                'services/regions/regionPanelRenderer.js',
                'services/renderers/controlWidgetsRenderer.js',
                'services/renderers.js',
                'services/session/sessionManager.js',
                'services/eventHandlers/viewEventHandlers.js',
                'services/eventHandlers.js',

                # 4. Main application entry point (loads last)
                'app.js'              # Wires everything together, attaches app.init.initialize
            ]

        all_js_code = []
        for file_name in js_files_order:
            print(f"INFO: Loading JS file: {file_name}")
            all_js_code.append(load_js_file(file_name))
        
        return "\n\n".join(all_js_code)

    def _initialize_javascript(self, doc):
        """Step 5: Gathers all models and sends them to the JavaScript front-end."""
        print("INFO: DashboardBuilder: Preparing and initializing JavaScript...")

        # This method builds the "bridge dictionary" of Python models
        js_models_for_args = self._assemble_js_bridge_dictionary()
        app_js_code = self._load_all_js_files() #the full app.js code

        init_js_code = f"""
            console.log("Bokeh document is ready. Initializing NoiseSurveyApp...");

            {app_js_code}

            // The 'all_models' variable is automatically created by BokehJS
            // because it was the key in our 'args' dictionary.
            // Its value is the entire dictionary of models we built in Python.
            const models = all_models;

                if (window.NoiseSurveyApp && typeof window.NoiseSurveyApp.init.initialize === 'function') {{
                    console.log('DEBUG: Found NoiseSurveyApp, calling init...');
                    window.NoiseSurveyApp.init.initialize(models);
                }} else {{
                    console.error('CRITICAL ERROR: NoiseSurveyApp.init not found. Check that app.js is loaded correctly.');
                }}
            """

        js_args = {'all_models': js_models_for_args}
        
        # We use different JS initialization methods for live vs. static modes.
        is_live_server = doc.session_context is not None

        if is_live_server:
            # For live server, use a more reliable initialization approach:
            # Attach the callback to DocumentReady AND use a timeout as fallback
            logger.debug("Initializing JS for LIVE SERVER using DocumentReady + nextTick fallback.")
            
            # Primary: DocumentReady event (works when loading from workspace)
            doc.js_on_event(DocumentReady, CustomJS(args=js_args, code=f"""
                if (!window.__bokeh_app_initialized) {{
                    window.__bokeh_app_initialized = true;
                    {init_js_code}
                }}
            """))
            
            # Fallback: Direct execution on nextTick (works for fresh loads)

            self.js_init_trigger.js_on_change('visible', CustomJS(args=js_args, code=f"""
                if (!window.__bokeh_app_initialized) {{
                    window.__bokeh_app_initialized = true;
                    {init_js_code}
                }}
            """))
            doc.add_next_tick_callback(lambda: setattr(self.js_init_trigger, 'visible', True))
        else:
            # For static HTML, DocumentReady is the correct and only trigger
            logger.debug("Initializing JS for STATIC HTML using DocumentReady event.")
            doc.js_on_event(DocumentReady, CustomJS(args=js_args, code=init_js_code))

        #trigger_source = ColumnDataSource(data={'trigger': [0]}, name='js_init_trigger')
        #trigger_source.js_on_change('data', CustomJS(args=js_models_for_args, code=js_code))
        #doc.add_root(trigger_source)
        #doc.add_timeout_callback(lambda: trigger_source.data.update({'trigger': [1]}), 1000)

    def _assemble_js_bridge_dictionary(self) -> dict:
        """Creates the dictionary of all models needed by app.js."""
        
        js_models = {
            'charts': [],
            'chartsSources': [],
            'timeSeriesSources': {},
            'spectrogramSources': {},
            'preparedGlyphData': self.prepared_glyph_data,
            'config': {
                'spectrogram_freq_range_hz': CHART_SETTINGS.get('spectrogram_freq_range_hz'),
                'freq_bar_freq_range_hz': CHART_SETTINGS.get('freq_bar_freq_range_hz'),
                'freq_table_freq_range_hz': CHART_SETTINGS.get('freq_table_freq_range_hz'),
                'log_view_max_viewport_seconds': LOG_VIEW_MAX_VIEWPORT_SECONDS,
                'server_mode': getattr(self, 'server_mode', False),
            },
            'sourceConfigs': getattr(self, 'source_configs', []),
            'jobNumber': getattr(self, 'job_number', None),
            'positionDisplayTitles': getattr(self, 'position_display_titles', {}),
            'savedWorkspaceState': getattr(self, 'saved_workspace_state', None),
            'uiPositionElements': {},
            'positionHasLogData': {},  # per-position flag: whether log data exists (even if not yet loaded)
            'clickLines': [],
            'hoverLines': [],
            'labels': [],
            'hoverDivs': [],
            'visibilityCheckBoxes': self.shared_components['controls'].get_all_visibility_checkboxes(),
            'barSource': self.shared_components['freq_bar'].source,
            'barChart': self.shared_components['freq_bar'].figure,
            'freqTableDiv': self.shared_components['freq_bar'].table_div,  # Add the frequency table div for copy/paste functionality
            'summaryTableDiv': self.shared_components['summary_table'].summary_div,
            'paramSelect': self.shared_components['controls'].param_select,
            'logThresholdSpinner': self.shared_components['controls'].log_threshold_spinner_widget,
            'viewToggle': self.shared_components['controls'].view_toggle,
            'hoverToggle': self.shared_components['controls'].hover_toggle,
            'viewStatusChip': self.shared_components['controls'].status_chips['view_status_chip'],
            'focusStatusChip': self.shared_components['controls'].status_chips['focus_status_chip'],
            'sessionMenu': self.shared_components['controls'].session_menu,
            'sessionActionSource': self.session_action_source,
            'sessionStatusSource': self.session_status_source,
            'controlStateSource': self.control_state_source,
            'automationCommandSource': self.automation_command_source,
            'automationResultSource': self.automation_result_source,
            #'audio_control_source': self.audio_control_source,
            #'audio_status_source': self.audio_status_source,
            'globalAudioControls': self.shared_components['controls'].global_audio_controls,
            'positionControls': {},
            'components': {},
            'frequencyBarLayout': self.shared_components.get('freq_bar_layout'),
            'regionPanelLayout': self.shared_components.get('region_panel_layout'),
            'markerPanelLayout': self.shared_components.get('marker_panel_layout'),
            'comparisonPanelLayout': self.shared_components.get('comparison_panel_layout'),
            'sidePanelTabs': self.shared_components.get('side_panel_tabs'),
            'sidePanelContainer': self.shared_components.get('side_panel_container'),
            'comparisonPositionSelector': self.shared_components['comparison_panel'].position_selector,
            'comparisonPositionIds': self.shared_components['comparison_panel'].position_ids,
            'comparisonFinishButton': self.shared_components['comparison_panel'].finish_button,
            'comparisonMakeRegionsButton': self.shared_components['comparison_panel'].make_regions_button,
            'comparisonSliceInfoDiv': self.shared_components['comparison_panel'].slice_info_div,
            'comparisonMetricsDiv': self.shared_components['comparison_panel'].metrics_table_div,
            'comparisonFrequencyLayout': self.shared_components.get('comparison_frequency_layout'),
            'comparisonFrequencySource': self.shared_components['comparison_frequency'].source,
            'comparisonFrequencyFigure': self.shared_components['comparison_frequency'].figure,
            'comparisonFrequencyTable': self.shared_components['comparison_frequency'].table_div,
            'comparisonFrequencyPalette': self.shared_components['comparison_frequency'].palette,
            'regionPanelDiv': self.shared_components['region_panel'].container,
            'regionPanelSource': self.shared_components['region_panel'].region_source,
            'regionPanelTable': self.shared_components['region_panel'].region_table,
            'regionPanelMessageDiv': self.shared_components['region_panel'].message_div,
            'regionPanelCreationIndicatorDiv': self.shared_components['region_panel'].creation_indicator_div,
            'regionPanelDetail': self.shared_components['region_panel'].detail_layout,
            'regionPanelCopyButton': self.shared_components['region_panel'].copy_button,
            'regionPanelDeleteButton': self.shared_components['region_panel'].delete_button,
            'regionPanelAddAreaButton': self.shared_components['region_panel'].add_area_button,
            'regionPanelMergeButton': self.shared_components['region_panel'].merge_button,
            'regionPanelMergeSelect': self.shared_components['region_panel'].merge_select,
            'regionPanelSplitButton': self.shared_components['region_panel'].split_button,
            'regionPanelColorPicker': self.shared_components['region_panel'].color_picker,
            'regionPanelNoteInput': self.shared_components['region_panel'].note_input,
            'regionPanelMetricsDiv': self.shared_components['region_panel'].metrics_div,
            'regionPanelFrequencyCopyButton': self.shared_components['region_panel'].frequency_copy_button,
            'regionPanelFrequencyTableDiv': self.shared_components['region_panel'].frequency_table_div,
            'regionPanelSpectrumDiv': self.shared_components['region_panel'].spectrum_div,
            'regionVisibilityToggle': self.shared_components['region_panel'].visibility_toggle,
            'regionAutoDayNightButton': self.shared_components['region_panel'].auto_daynight_button,
            'markerPanelDiv': self.shared_components['marker_panel'].container,
            'markerPanelSource': self.shared_components['marker_panel'].marker_source,
            'markerPanelTable': self.shared_components['marker_panel'].marker_table,
            'markerPanelMessageDiv': self.shared_components['marker_panel'].message_div,
            'markerPanelDetail': self.shared_components['marker_panel'].detail_layout,
            'markerPanelColorPicker': self.shared_components['marker_panel'].color_picker,
            'markerPanelNoteInput': self.shared_components['marker_panel'].note_input,
            'markerPanelMetricsDiv': self.shared_components['marker_panel'].metrics_div,
            'markerPanelCopyButton': self.shared_components['marker_panel'].copy_button,
            'markerPanelDeleteButton': self.shared_components['marker_panel'].delete_button,
            'markerPanelAddAtTapButton': self.shared_components['marker_panel'].add_at_tap_button,
            'markerVisibilityToggle': self.shared_components['marker_panel'].visibility_toggle,
        }

        # Populate position-specific models
        for pos, comp_dict in self.components.items():

            js_models['timeSeriesSources'][pos] = {
                'overview': comp_dict['timeseries'].overview_source,
                'log': comp_dict['timeseries'].log_source,
            }
            js_models['positionHasLogData'][pos] = comp_dict['timeseries'].has_log_data

            js_models['spectrogramSources'][pos] = {
                'overview': comp_dict['spectrogram'].overview_source,
                'log': comp_dict['spectrogram'].log_source,
            }

            ts_comp = comp_dict['timeseries']
            spec_comp = comp_dict['spectrogram']
            
            js_models['chartsSources'].extend([ts_comp.source, spec_comp.source])
            js_models['charts'].extend([ts_comp.figure, spec_comp.figure])
            js_models['clickLines'].extend([ts_comp.tap_lines, spec_comp.tap_lines])
            js_models['hoverLines'].extend([ts_comp.hover_line, spec_comp.hover_line])
            # Note: Only timeseries has labels, spectrogram doesn't
            js_models['labels'].append(ts_comp.label)
            js_models['hoverDivs'].append(spec_comp.hover_div)
            
            # Add position-specific controls (title and offsets)
            if comp_dict.get('position_controls'):
                js_models['positionControls'][pos] = comp_dict['position_controls']


        #Add RangeSelector tap and hover lines
        js_models['clickLines'].extend([self.shared_components['range_selector'].tap_lines])
        js_models['hoverLines'].extend([self.shared_components['range_selector'].hover_line])

        return js_models
    
    # Helper method
    def _determine_initial_display_mode(self, position_data: PositionData) -> str:
        if self.server_mode and (position_data.has_overview_totals or position_data.has_overview_spectral):
            logger.debug(f"DashBuilder: Forcing 'overview' mode for {position_data.name} in server mode.")
            return 'overview'
        if position_data.has_overview_totals:
            logger.debug(f"DashBuilder: Defaulting to 'overview' view for {position_data.name} as overview data is available.")
            return 'overview'
        elif position_data.has_log_totals:
            logger.debug(f"DashBuilder: Defaulting to 'log' view for {position_data.name} as only log data is available.")
            return 'log'
        # Fallback: if no totals, check for spectral data as a last resort
        elif position_data.has_overview_spectral:
            logger.warning(f"DashBuilder: No totals data for {position_data.name}, but overview spectral data found. Defaulting to 'overview'.")
            return 'overview'
        elif position_data.has_log_spectral:
            logger.warning(f"DashBuilder: No totals data for {position_data.name}, but log spectral data found. Defaulting to 'log'.")
            return 'log'
        
        logger.warning(f"DashBuilder: No plottable data found for {position_data.name}. Defaulting to 'overview'.")
        return 'overview'

    def _build_position_display_data(self, position_data_obj: PositionData) -> PositionData:
        # Preserve full-resolution data in both server and static modes.
        return position_data_obj
