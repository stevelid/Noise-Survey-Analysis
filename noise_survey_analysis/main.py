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

from noise_survey_analysis.core.config import CHART_SETTINGS, STREAMING_ENABLED
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.audio_processor import AudioDataProcessor
from noise_survey_analysis.core.app_setup import load_config_and_prepare_sources
from noise_survey_analysis.core.config_io import save_config_from_selected_sources
from noise_survey_analysis.export.static_export import generate_static_html
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler
from noise_survey_analysis.core.app_callbacks import AppCallbacks, session_destroyed
from noise_survey_analysis.core.server_data_handler import ServerDataHandler
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

# --- Process-level cache for parsed data ---
# This cache persists across Bokeh sessions AND module reloads to avoid re-parsing the same files
# Bokeh's autoreload feature reloads modules, so we use a singleton pattern with a lock file
import sys
import tempfile
import pickle
from pathlib import Path

class DataManagerCache:
    """Singleton cache that survives module reloads by storing state in a file."""
    
    _instance = None
    _cache_file = Path(tempfile.gettempdir()) / 'noise_survey_datamanager_cache.pkl'
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._data = {}
            cls._instance._load_from_disk()
        return cls._instance
    
    def _load_from_disk(self):
        """Load cache from disk if it exists."""
        try:
            if self._cache_file.exists():
                with open(self._cache_file, 'rb') as f:
                    self._data = pickle.load(f)
                logger.debug(f"Loaded {len(self._data)} cached entries from disk")
        except Exception as e:
            logger.warning(f"Failed to load cache from disk: {e}")
            self._data = {}
    
    def _save_to_disk(self):
        """Save cache to disk."""
        try:
            with open(self._cache_file, 'wb') as f:
                pickle.dump(self._data, f)
        except Exception as e:
            logger.warning(f"Failed to save cache to disk: {e}")
    
    def __contains__(self, key):
        return key in self._data
    
    def __getitem__(self, key):
        return self._data[key]
    
    def __setitem__(self, key, value):
        self._data[key] = value
        self._save_to_disk()
    
    def __len__(self):
        return len(self._data)
    
    def keys(self):
        return self._data.keys()

_data_manager_cache = DataManagerCache()

def _get_cache_key(source_configs):
    """Generate a cache key from source configurations."""
    if not source_configs:
        logger.debug("_get_cache_key: No source configs provided, returning None")
        return None
    try:
        # Create a stable key from sorted file paths
        key_parts = []
        logger.debug(f"_get_cache_key: Processing {len(source_configs)} source configs")
        for idx, config in enumerate(sorted(source_configs, key=lambda x: x.get('position_name', ''))):
            position = config.get('position_name', '')
            logger.debug(f"  Config {idx}: position='{position}', keys={list(config.keys())}")

            # Handle both file_path (singular, from workspace) and file_paths (plural, from selector)
            if isinstance(config.get('file_path'), str):
                # Single file path (workspace format)
                paths = [config.get('file_path')]
                logger.debug(f"    Using single file_path: {paths[0][:80]}...")
            elif 'file_paths' in config:
                # Multiple file paths (selector format)
                paths = config.get('file_paths', set())
                logger.debug(f"    Found file_paths (type: {type(paths).__name__})")
                if isinstance(paths, set):
                    paths = sorted(list(paths))
                elif isinstance(paths, list):
                    paths = sorted(paths)
                else:
                    paths = []
                logger.debug(f"    After sorting: {len(paths)} paths")
            else:
                paths = []
                logger.debug(f"    No file_path or file_paths found!")

            # Normalize paths for consistent comparison
            normalized_paths = [os.path.normpath(os.path.abspath(p)) for p in paths]
            key_part = f"{position}:{','.join(normalized_paths)}"
            key_parts.append(key_part)
            logger.debug(f"    Key part length: {len(key_part)}")

        cache_key = '|'.join(key_parts)
        logger.info(f"Generated cache key (length: {len(cache_key)}, first 100 chars): {cache_key[:100]}...")
        return cache_key
    except Exception as e:
        logger.error(f"Failed to generate cache key: {e}", exc_info=True)
        return None


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
    current_job_number = None

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

    def on_data_sources_selected(source_configs, skip_static_export=False, job_number=None):
        """Callback when data sources are selected from the selector.
        
        Args:
            source_configs: List of source configuration dictionaries
            skip_static_export: If True, skip generating static HTML (used when loading from existing config/workspace)
            job_number: Optional job number/identifier to display in the dashboard
        """
        nonlocal current_job_number
        current_job_number = job_number
        logger.info(f"Data sources selected, building dashboard... (job_number={job_number})")
        
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
        # Skip this if we're loading from an existing config/workspace (it's likely already been generated)
        if not skip_static_export:
            try:
                cfg_path = save_config_from_selected_sources(source_configs)
                if cfg_path:
                    logger.info(f"Auto-saved selector config to {cfg_path}. Starting static export in background...")
                    threading.Thread(target=generate_static_html, args=(str(cfg_path),), daemon=True).start()
                else:
                    logger.warning("Auto-save of selector config failed or returned no path; skipping static export.")
            except Exception as e:
                logger.error(f"Error during auto-save/config-based static export: {e}", exc_info=True)
        else:
            logger.info("Skipping static export (loading from existing config/workspace).")
        
        # This function will run after the loading screen is displayed.
        def build_dashboard():
            nonlocal initial_saved_workspace_state
            
            # Check cache for existing DataManager
            logger.info("=" * 80)
            logger.info("CACHE LOOKUP STARTING")
            logger.info("=" * 80)

            cache_key = _get_cache_key(source_configs)

            logger.info(f"Cache lookup results:")
            logger.info(f"  Generated cache_key: {'<None>' if cache_key is None else f'{len(cache_key)} chars'}")
            logger.info(f"  Cache currently has {len(_data_manager_cache)} entries")

            if len(_data_manager_cache) > 0:
                logger.info(f"  Existing cache keys:")
                for idx, existing_key in enumerate(_data_manager_cache.keys()):
                    logger.info(f"    [{idx}] Length: {len(existing_key)}, First 100 chars: {existing_key[:100]}...")

            if cache_key:
                cache_match = cache_key in _data_manager_cache
                logger.info(f"  Cache key match result: {cache_match}")
                if not cache_match and len(_data_manager_cache) > 0:
                    # Compare keys to find differences
                    for existing_key in _data_manager_cache.keys():
                        if len(cache_key) == len(existing_key):
                            logger.info(f"  Length matches existing key, comparing characters...")
                            diff_positions = [i for i in range(len(cache_key)) if cache_key[i] != existing_key[i]]
                            if len(diff_positions) < 20:  # Only log if small number of differences
                                logger.info(f"    Character differences at positions: {diff_positions[:10]}")
                        else:
                            logger.info(f"  Length mismatch: generated={len(cache_key)}, existing={len(existing_key)}")

            if cache_key and cache_key in _data_manager_cache:
                logger.info("✓✓✓ CACHE HIT! Using cached DataManager ✓✓✓")
                logger.info("=" * 80)
                app_data = _data_manager_cache[cache_key]
            else:
                logger.info("✗✗✗ CACHE MISS! Creating new DataManager ✗✗✗")
                if cache_key is None:
                    logger.warning("  Reason: cache_key is None")
                elif len(_data_manager_cache) == 0:
                    logger.info("  Reason: Cache is empty (first run)")
                else:
                    logger.warning("  Reason: cache_key doesn't match any existing keys")
                logger.info("=" * 80)

                app_data = DataManager(source_configurations=source_configs)
                if cache_key:
                    _data_manager_cache[cache_key] = app_data
                    logger.info(f"✓ Stored DataManager in cache with key length: {len(cache_key)}")
            
            audio_processor = AudioDataProcessor()
            audio_processor.anchor_audio_files(app_data)
            audio_handler = AudioPlaybackHandler(position_data=app_data.get_all_position_data())
            audio_control_source = ColumnDataSource(data={'command': [], 'position_id': [], 'value': []}, name='audio_control_source')
            audio_status_source = ColumnDataSource(data={'is_playing': [False], 'current_time': [0], 'playback_rate': [1.0], 'current_file_duration': [0], 'current_file_start_time': [0], 'active_position_id': [None], 'volume_boost': [False], 'current_file_name': ['']}, name='audio_status_source')
            app_callbacks = AppCallbacks(doc, audio_handler, audio_control_source, audio_status_source)
            doc.clear() # Clear the loading message
            dash_builder = DashBuilder(audio_control_source, audio_status_source)
            dash_builder.build_layout(
                doc,
                app_data,
                CHART_SETTINGS,
                source_configs=source_configs,
                saved_workspace_state=initial_saved_workspace_state,
                job_number=current_job_number,
                server_mode=STREAMING_ENABLED,
            )
            doc.add_root(audio_control_source)
            doc.add_root(audio_status_source)
            if STREAMING_ENABLED:
                server_data_handler = ServerDataHandler(doc, app_data, CHART_SETTINGS)
                app_callbacks.set_server_data_handler(server_data_handler)
            app_callbacks.attach_callbacks()
            setattr(doc.session_context, '_app_callback_manager', app_callbacks)
            initial_saved_workspace_state = None

        doc.add_next_tick_callback(build_dashboard)
    
    if source_configs_from_state:
        doc.add_next_tick_callback(lambda: on_data_sources_selected(source_configs_from_state, skip_static_export=True))
    else:
        config_path = _normalize_path(config_path)
        if config_path:
            logger.info(f"Attempting to load data directly from config file: {config_path}")
            
            # Check if this is actually a workspace file (contains both sourceConfigs and appState)
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    file_content = json.load(f)
                
                # If it has both sourceConfigs and appState, treat it as a workspace file
                if isinstance(file_content, dict) and 'sourceConfigs' in file_content and 'appState' in file_content:
                    logger.info("Detected workspace file format. Extracting sourceConfigs and appState.")
                    source_configs_from_state = file_content.get('sourceConfigs')
                    state_payload = file_content.get('appState')
                    if isinstance(state_payload, dict):
                        initial_saved_workspace_state = state_payload
                    if source_configs_from_state:
                        doc.add_next_tick_callback(lambda: on_data_sources_selected(source_configs_from_state, skip_static_export=True))
                    else:
                        logger.error("Workspace file has no sourceConfigs. Falling back to selector.")
                        selector = create_data_source_selector(doc, on_data_sources_selected)
                        doc.add_root(selector.get_layout())
                else:
                    # Regular config file - use the existing loader
                    _, source_configs, loaded_job_number = load_config_and_prepare_sources(config_path=config_path)
                    if source_configs is not None:
                        doc.add_next_tick_callback(lambda: on_data_sources_selected(source_configs, skip_static_export=True, job_number=loaded_job_number))
                    else:
                        logger.error(f"Failed to load from config file {config_path}. Falling back to selector.")
                        selector = create_data_source_selector(doc, on_data_sources_selected)
                        doc.add_root(selector.get_layout())
            except Exception as e:
                logger.error(f"Error reading config/workspace file {config_path}: {e}", exc_info=True)
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
    
    # Handle positional argument from bokeh serve --args "path/to/config.json"
    if config_file_path is None and len(sys.argv) > 1:
        # Check if first argument after script name looks like a config file path
        potential_config = sys.argv[1]
        if potential_config and not potential_config.startswith('-'):
            if os.path.exists(potential_config) or potential_config.endswith('.json'):
                config_file_path = potential_config
                logger.info(f"Using positional argument as config path: {config_file_path}")

    create_app(doc, config_path=config_file_path, state_path=state_file_path)
else:
    # No session context, so we're running as a standalone script.
    # This block will be executed when running `python main.py ...`
    main()
