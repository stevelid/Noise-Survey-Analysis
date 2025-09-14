import logging
import re
from bokeh.plotting import curdoc
from bokeh.models import ColumnDataSource, Div
import sys
import json
import argparse
import os
from pathlib import Path
import threading
from datetime import datetime

# --- Project Root Setup ---
current_file = Path(__file__)
project_root = current_file.parent.parent
sys.path.insert(0, str(project_root))

from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.app_setup import load_config_and_prepare_sources
from noise_survey_analysis.core.utils import find_lowest_common_folder
from noise_survey_analysis.core.config_io import save_config_from_selected_sources
from noise_survey_analysis.export.static_export import generate_static_html
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler
from noise_survey_analysis.core.app_callbacks import AppCallbacks, session_destroyed
from noise_survey_analysis.visualization.dashBuilder import DashBuilder
from noise_survey_analysis.ui.data_source_selector import create_data_source_selector

# --- Configure Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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
        
        # Save a config derived from the user's selection and kick off static export in background
        try:
            cfg_path = save_config_from_selected_sources(source_configs)
            if cfg_path:
                logger.info(f"Auto-saved selector config to {cfg_path}. Starting static export in background...")
                threading.Thread(target=generate_static_html, args=(str(cfg_path),), daemon=True).start()
            else:
                logger.warning("Auto-save of selector config failed or returned no path; skipping static export.")
        except Exception as e:
            logger.error(f"Error during auto-save/config-based static export: {e}", exc_info=True)
        
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
        # Ensure config_path is a string (Bokeh passes bytes for --args)
        if isinstance(config_path, (bytes, bytearray)):
            try:
                config_path = config_path.decode('utf-8')
            except Exception:
                config_path = str(config_path)

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

def main():
    """Main entry point for command-line execution."""
    parser = argparse.ArgumentParser(description="Noise Survey Analysis Tool.")
    parser.add_argument(
        "--generate-static",
        type=str,
        metavar="CONFIG_PATH",
        help="Generate a static HTML report from the specified JSON configuration file."
    )
    # Note: --config for the live server is handled via Bokeh's `--args` mechanism.

    # This check prevents argparse from running when script is used by Bokeh server
    if "bokeh" not in " ".join(sys.argv):
        args = parser.parse_args()
        if args.generate_static:
            if os.path.exists(args.generate_static):
                generate_static_html(config_path=args.generate_static)
            else:
                logger.error(f"Configuration file not found: {args.generate_static}")
                sys.exit(1)
        else:
            print("No action specified. To generate a static report, use --generate-static CONFIG_PATH.")
            print("To run the live server, use: bokeh serve main.py")

# We determine the execution mode by checking for a session context.
doc = curdoc()
if doc.session_context:
    # Session context exists, so we're running as a Bokeh server app.
    logger.info("Bokeh session context found. Setting up live application.")
    args = doc.session_context.request.arguments
    config_file_path = args.get('config', [None])[0]
    if isinstance(config_file_path, (bytes, bytearray)):
        try:
            config_file_path = config_file_path.decode('utf-8')
        except Exception:
            config_file_path = str(config_file_path)
    create_app(doc, config_path=config_file_path)
else:
    # No session context, so we're running as a standalone script.
    # This block will be executed when running `python main.py ...`
    main()
