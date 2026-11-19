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

from noise_survey_analysis.ui.theme import apply_theme
from noise_survey_analysis.ui.component_parts.html_side_panel import HtmlSidePanelComponent
from noise_survey_analysis.ui.components import (
    TimeSeriesComponent,
    SpectrogramComponent,
    FrequencyBarComponent,
    ComparisonFrequencyBarComponent,
    ControlsComponent,
    RangeSelectorComponent,
    SummaryTableComponent,
    create_audio_controls_for_position,
    create_position_title_and_offsets,
)
from noise_survey_analysis.core.data_processors import (
    GlyphDataProcessor,
    estimate_log_spectral_threshold_seconds,
)
from noise_survey_analysis.core.app_callbacks import AppCallbacks
from noise_survey_analysis.core.data_manager import DataManager, PositionData # Ensure PositionData is imported
from noise_survey_analysis.core.config import (
    CHART_SETTINGS,  # Ensure CHART_SETTINGS is imported
    UI_LAYOUT_SETTINGS,
    LOG_VIEW_MAX_VIEWPORT_SECONDS,
)
from noise_survey_analysis.js.manifest import JS_LOAD_ORDER
from noise_survey_analysis.visualization import static_payload
from noise_survey_analysis.core.weather import load_weather
from noise_survey_analysis.ui.component_parts.weather import WEATHER_BORDER_RIGHT, build_weather_chart

logger = logging.getLogger(__name__)

SIDE_PANEL_WIDTH = UI_LAYOUT_SETTINGS.get('side_panel_width', 320)

def load_js_file(file_name):
    """Loads a JavaScript file from the static/js directory."""
    # Correctly resolve the path to the static/js directory
    static_js_dir = os.path.join(os.path.dirname(__file__), '..', 'static', 'js')
    file_path = os.path.join(static_js_dir, file_name)
    with open(file_path, 'r', encoding='utf-8') as f:
        return f.read()

def apply_saved_position_order(names, saved_workspace_state):
    """Orders position names by a saved workspace's ``layout.positionOrder``.

    Accepts the payload with or without its ``appState`` wrapper. Unknown ids in the saved order are
    ignored and positions it does not mention keep their original order after the listed ones.
    """
    names = list(names)
    saved = saved_workspace_state if isinstance(saved_workspace_state, dict) else {}
    app_state = saved.get('appState') if isinstance(saved.get('appState'), dict) else saved
    layout = app_state.get('layout') if isinstance(app_state, dict) else None
    order = layout.get('positionOrder') if isinstance(layout, dict) else None
    if not isinstance(order, list) or not order:
        return names
    known = []
    for item in order:
        if isinstance(item, str) and item in names and item not in known:
            known.append(item)
    return known + [name for name in names if name not in known]


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
                     server_mode: bool = False,
                     position_offsets=None,
                     weather_config=None):
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
            weather_config: Optional site-wide weather CSV and interpretation settings.
        """
        logger.info("DashboardBuilder: Starting UI construction...")

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
        self._create_components(app_data, prepared_glyph_data, available_params, chart_settings,
                                position_offsets=position_offsets)
        self._wire_up_interactions()
        weather = load_weather(weather_config)
        x_range = self.shared_components.get('master_x_range')
        weather_chart = build_weather_chart(weather, x_range) if weather is not None and x_range is not None else None
        self._assemble_and_add_layout(doc, weather_chart)
        self._initialize_javascript(doc)

        logger.info("DashboardBuilder: Build complete.")

    # --- Private Helper Methods: The Step-by-Step Build Process ---

    def _prepare_glyph_data(self, app_data: DataManager) -> dict:
        """Step 1: Prepare glyph data for all positions."""
        logger.info("DashboardBuilder: Preparing glyph data for all positions.")
        
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

    # The payload helpers live in static_payload.py; these wrappers keep the old method names.
    @staticmethod
    def _to_list(value: Any) -> list:
        return static_payload.to_list(value)

    def _build_static_spectrogram_log_source_data(
        self,
        position_glyph_data: Dict[str, Any],
        preferred_param: str,
    ) -> Optional[Dict[str, list]]:
        return static_payload.build_static_spectrogram_log_source_data(position_glyph_data, preferred_param)

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
        # Remember which parameter is embedded here so preparedGlyphData does not carry it twice.
        if not hasattr(self, '_static_shared_params'):
            self._static_shared_params = {}
        self._static_shared_params[position_name] = (data.get('parameter') or [preferred_param])[0]
        logger.debug(
            "Static mode: pre-populated spectrogram log source for %s with keys=%s",
            position_name,
            list(data.keys()),
        )
    
    
    def _create_components(self, app_data: DataManager, prepared_glyph_data: dict, available_params: list, chart_settings: dict,
                           position_offsets=None):
        """Step 2: Instantiates all component classes for each position."""
        logger.info("DashboardBuilder: Creating individual UI components...")

        self.shared_components['controls'] = ControlsComponent(
            available_params,
            server_mode=getattr(self, 'server_mode', False)
        )
        controls_comp = self.shared_components['controls']
        
        self.shared_components['freq_bar'] = FrequencyBarComponent()

        all_positions = list(app_data.positions())
        self.shared_components['comparison_frequency'] = ComparisonFrequencyBarComponent()
        self.shared_components['summary_table'] = SummaryTableComponent(all_positions, ['LAeq', 'LAFmax', 'LAF90'])

        self.shared_components['html_side_panel'] = HtmlSidePanelComponent()

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
                # Narrow the 1 s line data (float32 levels) -- it dominates the line-chart payload.
                ts_component.log_source.data = static_payload.compact_timeseries_data(
                    dict(ts_component.log_source.data))

            # Create position title and offset controls for all positions
            # (Audio playback buttons are now global)
            _saved = (position_offsets or {}).get(position_name) or {}
            position_controls = create_position_title_and_offsets(
                position_id=position_name,
                display_title=position_name,  # Could use custom titles from config if available
                chart_offset_seconds=_saved.get('chart_offset_seconds', 0.0),
                audio_offset_seconds=_saved.get('audio_offset_seconds', 0.0),
                hover_div=spec_component.hover_div,
            )

            self.components[position_name] = {
                'timeseries': ts_component,
                'spectrogram': spec_component,
                'position_controls': position_controls,
                'has_audio': bool(getattr(position_data_obj, 'has_audio_files', False)),
                'has_log_spectral': position_data_obj.has_log_spectral,
                'log_spectral_threshold_seconds': estimate_log_spectral_threshold_seconds(
                    getattr(position_data_obj, 'log_file_paths', []),
                    chart_settings
                ),
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
        logger.info("DashboardBuilder: Wiring up interactions between components...")

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

                    master_x_range = Range1d(start=initial_start, end=initial_end, bounds=(initial_start, initial_end), min_interval=1000, max_interval=initial_end - initial_start, name="master_x_range")
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

                    master_x_range = Range1d(start=initial_start, end=initial_end, bounds=(initial_start, initial_end), min_interval=1000, max_interval=initial_end - initial_start, name="master_x_range")

                range_selector = self.shared_components.get('range_selector')
                if range_selector is not None and hasattr(range_selector, 'range_tool'):
                    range_selector.range_tool.x_range = master_x_range
            
            ts_comp.figure.x_range = master_x_range
            spec_comp.figure.x_range = master_x_range

        #add callback to x_range ranges
        if master_x_range is not None:
            self.shared_components['master_x_range'] = master_x_range
            range_update_js = CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleRangeUpdate) {
                    window.NoiseSurveyApp.eventHandlers.handleRangeUpdate(cb_obj);
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleRangeUpdate not defined!');
                }
            """)
            master_x_range.js_on_change('start', range_update_js)
            master_x_range.js_on_change('end', range_update_js)
        else:
            logger.warning("No master_x_range available; skipping range update callback.")


    def _assemble_and_add_layout(self, doc, weather_chart=None):
        """Step 4: Gets the .layout() from each component and assembles the final page."""
        logger.info("DashboardBuilder: Assembling final Bokeh layout...")

        position_layouts = {}
        for position_name, comp_dict in self.components.items():
            ts_layout = comp_dict['timeseries'].layout()
            spec_layout = comp_dict['spectrogram'].layout()
            header = comp_dict['position_controls']
            # Fixed 1600 px figures formerly pushed the sidebar off screen.
            # Stretch the chart column while preserving each plot's height.
            for chart in (comp_dict['timeseries'].figure, comp_dict['spectrogram'].figure):
                chart.width = None
                chart.sizing_mode = 'stretch_width'
                chart.min_width = 300
                if weather_chart is not None:
                    chart.min_border_right = WEATHER_BORDER_RIGHT
            for layout in (ts_layout, spec_layout, header['layout']):
                layout.sizing_mode = 'stretch_width'
                layout.margin = 0
                layout.styles = {**layout.styles, 'min-width': '0', 'overflow': 'visible'}

            # Header, time series, spectrogram. The loading banner is absolutely positioned over the
            # charts (position: relative on the box), so it takes no height.
            pos_layout = column(
                header['layout'],
                ts_layout,
                spec_layout,
                header['banner_div'],
                name=f"layout_{position_name}",
                styles={
                    "border": "1px solid #e2e8f0",
                    "border-radius": "8px",
                    "padding": "0",
                    "margin-bottom": "4px",
                    "background-color": "#ffffff",
                    "box-shadow": "0 1px 3px rgba(15, 23, 42, 0.08)",
                    "position": "relative",
                }
            )
            pos_layout.sizing_mode = 'stretch_width'
            pos_layout.margin = (0, 0, 4, 0)
            pos_layout.styles = {**pos_layout.styles, 'min-width': '0', 'overflow': 'visible'}
            position_layouts[position_name] = pos_layout

        self.shared_components['position_layouts'] = position_layouts
        ordered_names = apply_saved_position_order(
            list(position_layouts), getattr(self, 'saved_workspace_state', None))

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

        chart_rows = [position_layouts[name] for name in ordered_names]
        if weather_chart is not None:
            chart_rows.append(weather_chart)
            self.shared_components['range_selector'].figure.min_border_right = WEATHER_BORDER_RIGHT
        self.shared_components['weather_layout'] = weather_chart
        charts_stack_layout = column(*chart_rows, name="charts_stack_layout")
        charts_stack_layout.sizing_mode = 'stretch_width'
        charts_stack_layout.margin = 0
        charts_stack_layout.styles = {'min-width': '0', 'overflow': 'visible'}
        self.shared_components['charts_stack_layout'] = charts_stack_layout

        panel_toggle = Button(
            label="▾ Annotations", name="annotation_panel_toggle",
            sizing_mode="stretch_width", height=32, margin=0,
        )
        panel_toggle.js_on_click(CustomJS(code="""
            window.NoiseSurveyApp?.store?.dispatch(window.NoiseSurveyApp.actions.sidebarToggle());
        """))
        self.shared_components['annotation_panel_toggle'] = panel_toggle
        panel_body = self.shared_components['html_side_panel'].layout()
        summary_layout = self.shared_components['summary_table'].layout()

        # Both the tap-value summary and the active spectrum collapse as one group.
        frequency_dock_toggle = Button(
            label="▾ Table and spectrum", name="frequency_dock_toggle",
            sizing_mode="stretch_width", height=32, margin=0,
        )
        frequency_dock_toggle.js_on_click(CustomJS(code="""
            const app = window.NoiseSurveyApp;
            app?.store?.dispatch(app.features.layout.thunks.toggleFrequencyDockIntent());
        """))
        frequency_dock_inner = column(
            summary_layout, freq_bar_layout, comparison_frequency_layout,
            name="frequency_dock_inner", sizing_mode='stretch_width', margin=0,
            styles={
                'min-width': '0',
                'max-height': 'max(0px, var(--nsa-dock-available, calc(var(--nsa-sidebar-height, 85vh) * 0.44 - 32px)))',
                'overflow-y': 'auto',
                'overscroll-behavior-y': 'contain',
            },
        )
        frequency_dock_layout = column(
            frequency_dock_toggle, frequency_dock_inner,
            name="frequency_dock_layout", sizing_mode='stretch_width', margin=0,
            styles={'min-width': '0'},
        )
        self.shared_components['frequency_dock_toggle'] = frequency_dock_toggle
        self.shared_components['frequency_dock_layout'] = frequency_dock_layout
        self.shared_components['frequency_dock_inner'] = frequency_dock_inner

        sidebar_toggle = Button(
            label="Hide side panel", name="whole_sidebar_toggle",
            width=116, height=30, margin=0, align="end",
        )
        sidebar_toggle.js_on_click(CustomJS(code="""
            const app = window.NoiseSurveyApp;
            const collapsed = app?.store?.getState().layout?.sidePanelCollapsed;
            app?.store?.dispatch(app.actions.layoutSidePanelSet({collapsed: !collapsed}));
        """))
        side_panel_sections = column(
            panel_toggle,
            panel_body,
            frequency_dock_layout,
            name="side_panel_sections", sizing_mode="stretch_width",
            spacing=4, margin=0,
        )
        side_panel_container = column(
            sidebar_toggle, side_panel_sections,
            name="side_panel_container",
            width=SIDE_PANEL_WIDTH + 32,
            spacing=4,
            styles={
                'position': 'sticky',
                'top': 'var(--nsa-sidebar-top, 52px)',
                'align-self': 'flex-start',
                'min-width': '0',
                'overflow': 'visible',
            },
        )
        self.shared_components['whole_sidebar_toggle'] = sidebar_toggle
        self.shared_components['side_panel_sections'] = side_panel_sections
        self.shared_components['sidebar_toolbar'] = controls_layout
        for component in ('range_selector', 'freq_bar', 'comparison_frequency'):
            chart = self.shared_components[component].figure
            chart.width = None
            chart.sizing_mode = 'stretch_width'
        for layout in (controls_layout, range_selector_layout, freq_bar_layout, comparison_frequency_layout):
            layout.sizing_mode = 'stretch_width'
            layout.styles = {**layout.styles, 'overflow': 'visible', 'min-width': '0'}
        # The position boxes have a 1 px border; give the selector the same so frames line up exactly.
        range_selector_layout.margin = (0, 0, 4, 0)
        range_selector_layout.styles = {**range_selector_layout.styles, 'border': '1px solid transparent'}
        self.shared_components['side_panel_container'] = side_panel_container

        charts_page = column(range_selector_layout, charts_stack_layout,
                             name="charts_page", sizing_mode='stretch_width',
                             styles={'min-width': '0', 'overflow': 'visible'})
        chart_content_row = row(
            charts_page,
            side_panel_container,
            name="chart_content_row",
            spacing=12,
            styles={
                "align-items": "stretch",
            }
        )
        self.shared_components['chart_content_row'] = chart_content_row
        chart_content_row.sizing_mode = 'stretch_width'
        chart_content_row.styles = {**chart_content_row.styles, 'overflow': 'visible', 'min-width': '0'}

        main_layout = column(
            controls_layout,
            chart_content_row,
            self.js_init_trigger,
            name="main_layout",
        )

        final_layout = main_layout
        main_layout.sizing_mode = 'stretch_width'
        main_layout.styles = {'overflow': 'visible', 'min-width': '0'}

        apply_theme(final_layout)
        doc.add_root(final_layout)
        doc.title = "Noise Survey Analysis Dashboard"

    def _load_all_js_files(self):
        """Loads all JavaScript files in the correct order."""
        # The order lives in js/manifest.py (JS_LOAD_ORDER); it is critical for dependencies.
        js_files_order = JS_LOAD_ORDER

        all_js_code = []
        for file_name in js_files_order:
            logger.info(f"Loading JS file: {file_name}")
            all_js_code.append(load_js_file(file_name))
        
        return "\n\n".join(all_js_code)

    def _initialize_javascript(self, doc):
        """Step 5: Gathers all models and sends them to the JavaScript front-end."""
        logger.info("DashboardBuilder: Preparing and initializing JavaScript...")

        # This method builds the "bridge dictionary" of Python models
        js_models_for_args = self._assemble_js_bridge_dictionary()
        # No server behind this document (static export): annotations persist in the browser instead.
        if isinstance(js_models_for_args.get('config'), dict):
            js_models_for_args['config']['static_document'] = doc.session_context is None
            # Set by the static exporter when the 1 s spectrogram was averaged ("Log 5 s").
            js_models_for_args['config']['static_log_step_s'] = getattr(self, 'static_log_step_s', None)
        app_js_code = self._load_all_js_files() #the full app.js code

        init_js_code = f"""
            console.log("Bokeh document is ready. Initializing NoiseSurveyApp...");

            {app_js_code}

            // The 'all_models' variable is automatically created by BokehJS
            // because it was the key in our 'args' dictionary.
            // Its value is the entire dictionary of models we built in Python.
            const models = all_models;

                if (window.NoiseSurveyApp && window.NoiseSurveyApp.init && typeof window.NoiseSurveyApp.init.initialize === 'function') {{
                    console.log('DEBUG: Found NoiseSurveyApp, calling init...');
                    // Static exports embed quantised spectra; decode before the first render.
                    if (window.NoiseSurveyApp.session && typeof window.NoiseSurveyApp.session.decodeStaticPayload === 'function') {{
                        window.NoiseSurveyApp.session.decodeStaticPayload(models);
                    }}
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
            
            # One CustomJS model (so the ~850 KB bundle is serialised once) is attached to both
            # triggers. Whichever fires first runs it; the guard makes the second a no-op.
            init_callback = CustomJS(args=js_args, code=f"""
                if (!window.__bokeh_app_initialized) {{
                    window.__bokeh_app_initialized = true;
                    {init_js_code}
                }}
            """)

            # Primary: DocumentReady event (works when loading from workspace)
            doc.js_on_event(DocumentReady, init_callback)

            # Fallback: Direct execution on nextTick (works for fresh loads)
            self.js_init_trigger.js_on_change('visible', init_callback)
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
            'preparedGlyphData': (
                self.prepared_glyph_data if getattr(self, 'server_mode', False)
                else static_payload.compact_prepared_glyph_data(
                    self.prepared_glyph_data, getattr(self, '_static_shared_params', {}))
            ),
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
            'htmlSidePanel': self.shared_components['html_side_panel'].div,
            'uiPositionElements': {},
            'positionHasLogData': {},  # per-position flag: whether log data exists (even if not yet loaded)
            'positionHasLogSpectral': {},  # per-position flag: whether log spectrogram data exists
            'positionLogSpectralThresholdSeconds': {},  # per-position shared log switch threshold from deferred log metadata
            'positionHasAudio': {},
            'clickLines': [],
            'hoverLines': [],
            'labels': [],
            'hoverDivs': [],
            'visibilityCheckBoxes': self.shared_components['controls'].get_all_visibility_checkboxes(),
            'plotVisibilityMenu': self.shared_components['controls'].plot_visibility_menu,
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
            'sidePanelContainer': self.shared_components.get('side_panel_container'),
            'annotationPanelToggle': self.shared_components.get('annotation_panel_toggle'),
            'chartContentRow': self.shared_components.get('chart_content_row'),
            'comparisonFrequencyLayout': self.shared_components.get('comparison_frequency_layout'),
            'comparisonFrequencySource': self.shared_components['comparison_frequency'].source,
            'comparisonFrequencyFigure': self.shared_components['comparison_frequency'].figure,
            'comparisonFrequencyTable': self.shared_components['comparison_frequency'].table_div,
            'comparisonFrequencyPalette': self.shared_components['comparison_frequency'].palette,
            # Layout and navigation (WP1)
            'chartsStackLayout': self.shared_components.get('charts_stack_layout'),
            'weatherLayout': self.shared_components.get('weather_layout'),
            'positionLayouts': self.shared_components.get('position_layouts', {}),
            'rangeSelectorFigure': self.shared_components['range_selector'].figure,
            'sidebarToolbar': self.shared_components.get('sidebar_toolbar'),
            'wholeSidebarToggle': self.shared_components.get('whole_sidebar_toggle'),
            'sidePanelSections': self.shared_components.get('side_panel_sections'),
            'frequencyDockToggle': self.shared_components.get('frequency_dock_toggle'),
            'frequencyDockLayout': self.shared_components.get('frequency_dock_layout'),
            'frequencyDockInner': self.shared_components.get('frequency_dock_inner'),
            'layoutControls': self.shared_components['controls'].layout_controls,
        }

        # Populate position-specific models
        for pos, comp_dict in self.components.items():

            js_models['timeSeriesSources'][pos] = {
                'overview': comp_dict['timeseries'].overview_source,
                'log': comp_dict['timeseries'].log_source,
            }
            js_models['positionHasLogData'][pos] = comp_dict['timeseries'].has_log_data
            threshold_seconds = comp_dict.get('log_spectral_threshold_seconds')
            js_models['positionHasLogSpectral'][pos] = bool(
                comp_dict.get('has_log_spectral') or
                (threshold_seconds is not None)
            )
            js_models['positionLogSpectralThresholdSeconds'][pos] = threshold_seconds
            js_models['positionHasAudio'][pos] = bool(comp_dict.get('has_audio'))

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
