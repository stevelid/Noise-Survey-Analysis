import logging
from bokeh.plotting import curdoc
from bokeh.models import ColumnDataSource, Div
import sys
import json
import argparse
import os
from pathlib import Path
import threading

# --- Project Root Setup ---
current_file = Path(__file__)
project_root = current_file.parent.parent
sys.path.insert(0, str(project_root))

from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.audio_processor import AudioDataProcessor
from noise_survey_analysis.core.app_setup import load_config_and_prepare_sources
from noise_survey_analysis.core.config_io import save_config_from_selected_sources
from noise_survey_analysis.export.static_export import generate_static_html
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler
from noise_survey_analysis.core.app_callbacks import AppCallbacks, session_destroyed
from noise_survey_analysis.visualization.dashBuilder import DashBuilder
from noise_survey_analysis.ui.data_source_selector import create_data_source_selector


def _decode_argument_value(raw_value):
    """Decode Bokeh request argument values to plain strings."""
    if raw_value is None:
        return None

    # Bokeh wraps argument values in lists; accept plain values as well for safety
    if isinstance(raw_value, (list, tuple)):
        for candidate in raw_value:
            decoded = _decode_argument_value(candidate)
            if decoded is not None:
                return decoded
        return None

    if isinstance(raw_value, (bytes, bytearray)):
        try:
            return raw_value.decode('utf-8')
        except Exception:
            return raw_value.decode('utf-8', errors='ignore')

    return str(raw_value)


def _extract_request_argument(arguments, *names):
    """Return the first matching argument from a Bokeh request."""
    if not arguments:
        return None

    normalized_names = {name.lstrip('-').lower() for name in names if name}
    for raw_key, raw_value in arguments.items():
        if raw_key is None:
            continue
        if isinstance(raw_key, (bytes, bytearray)):
            key = raw_key.decode('utf-8', errors='ignore')
        else:
            key = str(raw_key)

        normalized_key = key.lstrip('-').lower()
        if '[' in normalized_key:
            normalized_key = normalized_key.split('[', 1)[0]
        if normalized_key in normalized_names:
            return _decode_argument_value(raw_value)

    return None


def _extract_argv_argument(*flags):
    """Fallback parser for command-line style flags from sys.argv."""
    if not sys.argv:
        return None

    for index, token in enumerate(sys.argv):
        for flag in flags:
            if not flag:
                continue
            if token == flag and index + 1 < len(sys.argv):
                return sys.argv[index + 1]
            if token.startswith(f"{flag}="):
                return token.split('=', 1)[1]

    return None


def _normalize_path(value):
    """Convert various argument representations into a filesystem path string."""
    if value is None:
        return None

    if isinstance(value, (bytes, bytearray)):
        try:
            value = value.decode('utf-8')
        except Exception:
            value = value.decode('utf-8', errors='ignore')

    value = str(value).strip()
    if not value:
        return None

    return os.path.expanduser(value)

# --- Configure Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_app(doc, config_path=None, state_path=None):
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
    
    initial_saved_workspace_state = None
    source_configs_from_state = None

    state_path = _normalize_path(state_path)
    if state_path:
        logger.info(f"Attempting to load workspace state file: {state_path}")
        try:
            with open(state_path, 'r', encoding='utf-8') as state_file:
                workspace_payload = json.load(state_file)

            if not isinstance(workspace_payload, dict):
                raise ValueError("Workspace file must contain a JSON object")

            state_payload = workspace_payload.get('appState')
            if isinstance(state_payload, dict):
                initial_saved_workspace_state = state_payload
            else:
                logger.warning("Workspace file missing 'appState'; state rehydration will be skipped.")

            configs_payload = workspace_payload.get('sourceConfigs')
            if isinstance(configs_payload, list) and configs_payload:
                source_configs_from_state = configs_payload
            else:
                if configs_payload:
                    logger.warning("Workspace file contains 'sourceConfigs' but it is not a non-empty list. Falling back to other sources.")
                else:
                    logger.warning("Workspace file does not include 'sourceConfigs'. Falling back to other sources.")
        except FileNotFoundError:
            logger.error(f"Workspace state file not found: {state_path}")
        except Exception as exc:
            logger.error(f"Failed to parse workspace state file '{state_path}': {exc}", exc_info=True)

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
            nonlocal initial_saved_workspace_state
            app_data = DataManager(source_configurations=source_configs)
            audio_processor = AudioDataProcessor()
            audio_processor.anchor_audio_files(app_data)
            audio_handler = AudioPlaybackHandler(position_data=app_data.get_all_position_data())
            audio_control_source = ColumnDataSource(data={'command': [], 'position_id': [], 'value': []}, name='audio_control_source')
            audio_status_source = ColumnDataSource(data={'is_playing': [False], 'current_time': [0], 'playback_rate': [1.0], 'current_file_duration': [0], 'current_file_start_time': [0], 'active_position_id': [None], 'volume_boost': [False]}, name='audio_status_source')
            app_callbacks = AppCallbacks(doc, audio_handler, audio_control_source, audio_status_source)
            doc.clear() # Clear the loading message
            dash_builder = DashBuilder(audio_control_source, audio_status_source)
            dash_builder.build_layout(
                doc,
                app_data,
                CHART_SETTINGS,
                source_configs=source_configs,
                saved_workspace_state=initial_saved_workspace_state,
            )
            doc.add_root(audio_control_source)
            doc.add_root(audio_status_source)
            app_callbacks.attach_callbacks()
            setattr(doc.session_context, '_app_callback_manager', app_callbacks)
            initial_saved_workspace_state = None

        doc.add_next_tick_callback(build_dashboard)
    
    if source_configs_from_state:
        doc.add_next_tick_callback(lambda: on_data_sources_selected(source_configs_from_state))
    else:
        config_path = _normalize_path(config_path)
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
    request_arguments = doc.session_context.request.arguments

    config_file_path = _extract_request_argument(request_arguments, 'config')
    state_file_path = _extract_request_argument(request_arguments, 'state', 'workspace', 'savedworkspace')

    if config_file_path is None:
        config_file_path = _extract_argv_argument('--config')

    if state_file_path is None:
        state_file_path = _extract_argv_argument('--state', '--workspace', '--savedworkspace')

    create_app(doc, config_path=config_file_path, state_path=state_file_path)
else:
    # No session context, so we're running as a standalone script.
    # This block will be executed when running `python main.py ...`
    main()
