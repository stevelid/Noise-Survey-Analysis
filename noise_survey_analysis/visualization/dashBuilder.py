import logging
from bokeh.plotting import curdoc
from bokeh.layouts import column, LayoutDOM # Ensure column is imported
from bokeh.models import Div, ColumnDataSource # Import for assertions and error messages
import pandas as pd
import numpy as np  # Import numpy for array operations
import os
from bokeh.resources import CDN
from bokeh.embed import file_html  # Add import for standalone HTML generation
import logging
from bokeh.events import DocumentReady
from bokeh.models import CustomJS, ColumnDataSource
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
    ControlsComponent,
    RangeSelectorComponent,
    create_audio_controls_for_position
)
from noise_survey_analysis.core.data_processors import GlyphDataProcessor
from noise_survey_analysis.core.app_callbacks import AppCallbacks
from noise_survey_analysis.core.data_manager import DataManager, PositionData # Ensure PositionData is imported
from noise_survey_analysis.core.config import CHART_SETTINGS # Ensure CHART_SETTINGS is imported
from noise_survey_analysis.js.loader import load_js_file

logger = logging.getLogger(__name__)

class DashBuilder:
  
    """
    Builds the Bokeh dashboard layout, including charts, widgets, and interactions.
    Orchestrates the creation of visualization components and UI elements.
    """

    def __init__(self, 
                 app_callbacks: Optional[AppCallbacks] = None, 
                 audio_control_source: Optional[ColumnDataSource] = None, 
                 audio_status_source: Optional[ColumnDataSource] = None):
        """
        The constructor is lightweight. It only stores references to core handlers
        and initializes containers for the components it will create.

       Args:
            app_callbacks: An instance of AppCallbacks for backend logic. (Optional)
            audio_control_source: The shared CDS for sending commands. (Optional)
            audio_status_source: The shared CDS for receiving status. (Optional)
        """
        self.app_callbacks = app_callbacks
        self.audio_control_source = audio_control_source or ColumnDataSource(data={'command': [], 'position_id': [], 'value': []})
        self.audio_status_source = audio_status_source or ColumnDataSource(data={'is_playing': [False], 'current_time': [0],'playback_rate': [1.0], 'current_file_duration': [0], 'current_file_start_time': [0]})
        
        # These will be populated by the build process
        self.components: Dict[str, Dict[str, Any]] = {}
        self.shared_components: Dict[str, Any] = {}
        self.prepared_glyph_data: Dict[str, Dict[str, Any]] = {}

    def build_layout(self, doc, app_data: DataManager, chart_settings: dict):
        """
        The main public method that constructs the entire application layout.
        This is the primary entry point for this class.

        Args:
            doc: The Bokeh document to attach the final layout to.
            app_data: The complete, prepared data object from the DataManager.
            chart_settings: The global dictionary of chart settings.
        """
        print("INFO: DashboardBuilder: Starting UI construction...")

        # The sequence of operations is clear and logical
        prepared_glyph_data, available_params = self._prepare_glyph_data(app_data)

        self.prepared_glyph_data = prepared_glyph_data
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
    
    
    def _create_components(self, app_data: DataManager, prepared_glyph_data: dict, available_params: list, chart_settings: dict):
        """Step 2: Instantiates all component classes for each position."""
        logger.info("DashboardBuilder: Creating individual UI components...")

        self.shared_components['controls'] = ControlsComponent(available_params)
        controls_comp = self.shared_components['controls']
        
        self.shared_components['freq_bar'] = FrequencyBarComponent()

        first_position_processed = False
        # Create components for each position found in the data
        for position_name in app_data.positions():
            position_data_obj = app_data[position_name] # Get PositionData object
            position_specific_glyph_data = prepared_glyph_data.get(position_name, {})

            initial_mode = self._determine_initial_display_mode(position_data_obj)
            initial_param_spectrogram = chart_settings.get('default_spectral_parameter', 'LZeq')

            ts_component = TimeSeriesComponent(
                position_data_obj=position_data_obj,
                initial_display_mode=initial_mode
            )
            spec_component = SpectrogramComponent(
                position_data_obj=position_data_obj,
                position_glyph_data=position_specific_glyph_data,
                initial_display_mode=initial_mode,
                initial_param=initial_param_spectrogram
            )

            # Create audio controls if audio is available for this position
            audio_controls = None
            if position_data_obj.has_audio:
                audio_controls = create_audio_controls_for_position(position_name)

            self.components[position_name] = {
                'timeseries': ts_component,
                'spectrogram': spec_component,
                'audio_controls': audio_controls
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
        for position_name, comp_dict in self.components.items():
            ts_comp = comp_dict['timeseries']
            spec_comp = comp_dict['spectrogram']
            controls = self.shared_components['controls']
            freq_bar = self.shared_components['freq_bar']

            if master_x_range is None:
                master_x_range = ts_comp.figure.x_range
            
            ts_comp.figure.x_range = master_x_range
            spec_comp.figure.x_range = master_x_range

        #add callback to x_range ranges
        range_update_js = CustomJS(code="""
            if (window.NoiseSurveyApp && window.NoiseSurveyApp.interactions.onRangeUpdate) {
                window.NoiseSurveyApp.interactions.onRangeUpdate(cb_obj);
            } else {
                console.error('NoiseSurveyApp.interactions.onRangeUpdate not defined!');
            }
        """)
        master_x_range.js_on_change('end', range_update_js)


    def _assemble_and_add_layout(self, doc):
        """Step 4: Gets the .layout() from each component and assembles the final page."""
        print("INFO: DashboardBuilder: Assembling final Bokeh layout...")
        
        position_layouts = []
        for position_name, comp_dict in self.components.items():
            # Add audio controls to the timeseries layout if they exist
            ts_layout = comp_dict['timeseries'].layout()
            if comp_dict.get('audio_controls'):
                # This assumes the title is a Div and we can insert controls before it.
                # A more robust method might be needed if the layout structure changes.
                ts_figure = comp_dict['timeseries'].figure
                ts_figure.above.insert(0, comp_dict['audio_controls']['layout'])

            pos_layout = column(
                ts_layout,
                comp_dict['spectrogram'].layout(),
                name=f"layout_{position_name}"
            )
            position_layouts.append(pos_layout)

        controls_layout = self.shared_components['controls'].layout()
        # The final layout assembly
        final_layout = column(
            controls_layout, 
            self.shared_components['range_selector'].layout(), 
            *position_layouts, 
            self.shared_components['freq_bar'].layout() if 'freq_bar' in self.shared_components else Div(),
            name="main_layout"
        )

        doc.add_root(final_layout)
        doc.title = "Noise Survey Analysis Dashboard"

    def _initialize_javascript(self, doc):
        """Step 5: Gathers all models and sends them to the JavaScript front-end."""
        print("INFO: DashboardBuilder: Preparing and initializing JavaScript...")

        # This method builds the "bridge dictionary" of Python models
        js_models_for_args = self._assemble_js_bridge_dictionary()
        app_js_code = load_js_file('app.js') #the full app.js code

        js_code = f"""
            console.log("Bokeh document is ready. Initializing NoiseSurveyApp...");

            {app_js_code}

            setTimeout(() => {{
                console.log("This happened after 0.5 seconds (non-blocking).");
            

                const models = {{
                    charts: charts,
                    chartsSources: chartsSources,
                    timeSeriesSources: timeSeriesSources,
                    preparedGlyphData: preparedGlyphData,
                    uiPositionElements: uiPositionElements,
                    clickLines: clickLines,
                    hoverLines: hoverLines,
                    labels: labels,
                    hoverDivs: hoverDivs,
                    visibilityCheckBoxes: visibilityCheckBoxes,
                    barSource: barSource,
                    barChart: barChart,
                    paramSelect: paramSelect,
                    freqTableDiv: freqTableDiv,
                    audio_control_source: audio_control_source,
                    audio_status_source: audio_status_source,
                    audio_controls: audio_controls,
                }};

                console.log('[NoiseSurveyApp]', 'Models:', models);

                if (window.NoiseSurveyApp && typeof window.NoiseSurveyApp.init === 'function') {{
                    console.log('DEBUG: Found NoiseSurveyApp, calling init...');
                    window.NoiseSurveyApp.init(models, {{ enableKeyboardNavigation: true }});
                }} else {{
                    console.error('CRITICAL ERROR: NoiseSurveyApp.init not found. Check that app.js is loaded correctly.');
                }}
            }}, 500); // 500 milliseconds = 0.5 seconds
        """

        # Set up the DocumentReady callback, passing the python models dict to 'args'
        # The keys in this dict MUST match the variable names used in the JS code above.
        doc.js_on_event(DocumentReady, CustomJS(args=js_models_for_args, code=js_code))

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
            'preparedGlyphData': self.prepared_glyph_data,
            'uiPositionElements': {},
            'clickLines': [],
            'hoverLines': [],
            'labels': [],
            'hoverDivs': [],
            'visibilityCheckBoxes': self.shared_components['controls'].get_all_visibility_checkboxes(),
            'barSource': self.shared_components['freq_bar'].source,
            'barChart': self.shared_components['freq_bar'].figure,
            'freqTableDiv': self.shared_components['freq_bar'].table_div,  # Add the frequency table div for copy/paste functionality
            'paramSelect': self.shared_components['controls'].param_select,
            'audio_control_source': self.app_callbacks.audio_control_source if self.app_callbacks else None,
            'audio_status_source': self.app_callbacks.audio_status_source if self.app_callbacks else None,
            'audio_controls': {},
        }

        # Populate position-specific models
        for pos, comp_dict in self.components.items():

            js_models['timeSeriesSources'][pos] = {
                'overview': comp_dict['timeseries'].overview_source,
                'log': comp_dict['timeseries'].log_source,
            }
            
            js_models['chartsSources'].extend([comp_dict['timeseries'].source, comp_dict['spectrogram'].source])
            js_models['charts'].extend([comp_dict['timeseries'].figure, comp_dict['spectrogram'].figure])
            js_models['clickLines'].extend([comp_dict['timeseries'].tap_lines, comp_dict['spectrogram'].tap_lines])
            js_models['hoverLines'].extend([comp_dict['timeseries'].hover_line, comp_dict['spectrogram'].hover_line])
            # Note: Only timeseries has labels, spectrogram doesn't
            js_models['labels'].append(comp_dict['timeseries'].label)
            js_models['hoverDivs'].append(comp_dict['spectrogram'].hover_div)
            if comp_dict.get('audio_controls'):
                js_models['audio_controls'][pos] = comp_dict['audio_controls']
            if comp_dict.get('audio_controls'):
                js_models['audio_controls'][pos] = comp_dict['audio_controls']


        #Add RangeSelector tap and hover lines
        js_models['clickLines'].extend([self.shared_components['range_selector'].tap_lines])
        js_models['hoverLines'].extend([self.shared_components['range_selector'].hover_line])

        return js_models
    
    # Helper method
    def _determine_initial_display_mode(self, position_data: PositionData) -> str:
        if position_data.has_overview_totals:
            logger.debug(f"DashBuilder: Using overview_totals for {position_data.name}")
            return 'overview'
        elif position_data.has_log_totals:
            logger.debug(f"DashBuilder: Using log_totals for {position_data.name}")
            return 'log'
        # Fallback: if no totals, check for spectral data as a last resort
        elif position_data.has_log_spectral:
            logger.warning(f"DashBuilder: No totals data for {position_data.name}, but log spectral data found. Defaulting to 'log'.")
            return 'log'
        elif position_data.has_overview_spectral:
            logger.warning(f"DashBuilder: No totals data for {position_data.name}, but overview spectral data found. Defaulting to 'overview'.")
            return 'overview'
        
        logger.warning(f"DashBuilder: No plottable data found for {position_data.name}. Defaulting to 'overview'.")
        return 'overview'
