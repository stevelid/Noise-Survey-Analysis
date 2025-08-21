import logging
from re import L
from bokeh.plotting import curdoc
from bokeh.models import ColumnDataSource, Div
from bokeh.io import output_file, save
from bokeh.document import Document
import sys
import json
import argparse
import os
from pathlib import Path

# --- Project Root Setup ---
current_file = Path(__file__)
project_root = current_file.parent.parent
sys.path.insert(0, str(project_root))

from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.app_setup import load_config_and_prepare_sources
from noise_survey_analysis.core.utils import find_lowest_common_folder
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler
from noise_survey_analysis.core.app_callbacks import AppCallbacks, session_destroyed
from noise_survey_analysis.visualization.dashBuilder import DashBuilder
from noise_survey_analysis.ui.data_source_selector import create_data_source_selector

# --- Configure Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)



def generate_static_html():
    """
    Builds the dashboard layout and saves it as a standalone HTML file.
    """
    output_filename, source_configs = load_config_and_prepare_sources()
    if source_configs is None:
        logger.error("Could not load source configurations. Aborting static generation.")
        return

    # Determine output directory based on source file locations
    all_file_paths = []
    for config in source_configs:
        if config.get("enabled", True):
            all_file_paths.extend(list(config.get('file_paths', set())))

    output_dir = project_root
    if all_file_paths:
        common_folder = find_lowest_common_folder(all_file_paths)
        if common_folder:
            output_dir = Path(common_folder)
            logger.info(f"Common source directory found. Setting output location to: {output_dir}")
        else:
            logger.info("No common source directory found. Using default project directory for output.")
    
    output_full_path = output_dir / output_filename

    logger.info(f"--- Generating static HTML file: {output_full_path} ---")
    
    # 1. Load Data
    app_data = DataManager(source_configurations=source_configs)

    # 2. Instantiate builder
    dash_builder = DashBuilder(audio_control_source=None, audio_status_source=None)

    # 3. Create and build document
    static_doc = Document()
    dash_builder.build_layout(static_doc, app_data, CHART_SETTINGS)

    # 4. Save the document
    try:
        output_file(output_full_path, title="Noise Survey Dashboard")
        save(static_doc)
        logger.info(f"--- Static HTML file saved successfully to {output_full_path} ---")
    except Exception as e:
        logger.error(f"Failed to save static HTML file: {e}", exc_info=True)


def create_app(doc, config_path=None):
    """
    This function is the entry point for the LIVE Bokeh server application.
    """
    # Configure logging for Bokeh server environment
    # Bokeh pre-configures logging, so we need explicit handlers to ensure visibility
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
    
    logger.setLevel(logging.DEBUG)
    logging.getLogger().setLevel(logging.DEBUG)  # Ensure root logger allows DEBUG messages
    logger.propagate = False  # Prevent duplicate output
    
    logger.info("--- New client session started. Creating live application instance. ---")
    
    def on_data_sources_selected(source_configs):
        """Callback when data sources are selected from the selector."""
        logger.info("Data sources selected, building dashboard...")
        
        # Clear current layout
        doc.clear()
        
        # Display a "Loading..." message while the backend processes data.
        loading_div = Div(
            text="""<h1 style='text-align:center; color:#555;'>Loading Survey Data...</h1>
                    <p style='text-align:center; color:#888;'>This may take a moment for large surveys.</p>""",
            width=800, align='center',
            styles={'margin': 'auto', 'padding-top': '100px'}
        )
        doc.add_root(loading_div)
        
        # This function will run after the loading screen is displayed.
        def build_dashboard():
            app_data = DataManager(source_configurations=source_configs)
            audio_handler = AudioPlaybackHandler(position_data=app_data.get_all_position_data())
            audio_control_source = ColumnDataSource(data={'command': [], 'position_id': [], 'value': []}, name='audio_control_source')
            audio_status_source = ColumnDataSource(data={'is_playing': [False], 'current_time': [0], 'playback_rate': [1.0], 'current_file_duration': [0], 'current_file_start_time': [0], 'active_position_id': [None], 'volume_boost': [False]}, name='audio_status_source')
            app_callbacks = AppCallbacks(doc, audio_handler, audio_control_source, audio_status_source)
            doc.clear() # Clear the loading message
            dash_builder = DashBuilder(audio_control_source, audio_status_source)
            dash_builder.build_layout(doc, app_data, CHART_SETTINGS)
            doc.add_root(audio_control_source)
            doc.add_root(audio_status_source)
            app_callbacks.attach_callbacks()
            setattr(doc.session_context, '_app_callback_manager', app_callbacks)

        doc.add_next_tick_callback(build_dashboard)
    
    if config_path:
        logger.info(f"Attempting to load data directly from config file: {config_path}")
        _, source_configs = load_config_and_prepare_sources(config_path=config_path)
        if source_configs is not None:
            # Use a next tick callback to ensure the document is fully ready
            doc.add_next_tick_callback(lambda: on_data_sources_selected(source_configs))
        else:
            logger.error(f"Failed to load from config file {config_path}. Falling back to selector.")
            # Fallback to selector if config loading fails
            selector = create_data_source_selector(doc, on_data_sources_selected)
            doc.add_root(selector.get_layout())
    else:
        # Show data source selector initially if no config path is provided
        logger.info("No config file provided. Showing data source selector...")
        selector = create_data_source_selector(doc, on_data_sources_selected)
        doc.add_root(selector.get_layout())
    doc.on_session_destroyed(session_destroyed)

    logger.info("--- Live application setup complete for this session. ---")
    


# ==============================================================================
# MAIN EXECUTION BLOCK
# ==============================================================================

# This script can be run in two ways:
# 1. Directly with `python main.py`: This will generate a static HTML file of
#    the dashboard without a live backend.
# 2. With `bokeh serve main.py`: This will run a live server application.

# We determine the execution mode by checking for a session context.
doc = curdoc()
if doc.session_context is None:
    # No session context, so we're running as a standalone script.
    logger.info("No Bokeh session context found. Generating static HTML file.")
    generate_static_html()
else:
    # Session context exists, so we're running as a Bokeh server app.
    logger.info("Bokeh session context found. Setting up live application.")
    # --- Argument Parsing for Live App ---
    # We use this approach to get args without interfering with Bokeh's own CLI args.
    args = doc.session_context.request.arguments
    config_file_path = args.get('config', [None])[0]

    create_app(doc, config_path=config_file_path)
