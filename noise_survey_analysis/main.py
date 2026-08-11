import logging
from bokeh.plotting import curdoc
from bokeh.models import ColumnDataSource, Div
import sys
import json
import argparse
import copy
import os
import pandas as pd
from pathlib import Path
import tempfile
import threading

# --- Project Root Setup ---
current_file = Path(__file__)
project_root = current_file.parent.parent
sys.path.insert(0, str(project_root))

from noise_survey_analysis.core.config import AUDIO_ANCHORING_SETTINGS, CHART_SETTINGS, STREAMING_ENABLED
from noise_survey_analysis.core.audio_alignment_cache import (
    AudioAlignmentCache,
    build_audio_alignment_cache_key,
    build_source_fingerprint,
    capture_audio_alignment,
    restore_audio_alignment,
)
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.audio_processor import AudioDataProcessor
from noise_survey_analysis.core.app_setup import load_config_and_prepare_sources, load_config_extras
from noise_survey_analysis.core.config_io import save_config_from_selected_sources, save_state_to_config
from noise_survey_analysis.export.static_export import generate_static_html
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler
from noise_survey_analysis.core.app_callbacks import AppCallbacks, session_destroyed
from noise_survey_analysis.core.server_data_handler import ServerDataHandler
from noise_survey_analysis.visualization.dashBuilder import DashBuilder
from noise_survey_analysis.ui.data_source_selector import create_data_source_selector
from noise_survey_analysis.ui.theme import apply_theme
from noise_survey_analysis.control.validation import parse_deep_link_params
from noise_survey_analysis.control.session_bridge import SessionBridge
from noise_survey_analysis.control.control_server import ControlServer
from noise_survey_analysis.core.session_startup import schedule_when_client_connected
from noise_survey_analysis.core import status_console

# Process-level singletons for the control system.
_session_bridge = SessionBridge()
_control_server: ControlServer | None = None


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
# Two tiers. The console shows only the startup summary, the rolling status
# pane, and warnings/errors, so a slow viewport stream stays readable. Full
# detail always goes to the log file, so nothing is lost for debugging.
#
#   NOISE_SURVEY_LOG_LEVEL   detail written to the log file  (default DEBUG)
#   NOISE_SURVEY_LOG_FILE    override the log file location
#   NOISE_SURVEY_VERBOSE=1   also send that full detail to the console
_log_level_str = os.environ.get('NOISE_SURVEY_LOG_LEVEL', 'DEBUG').upper()
_log_level = getattr(logging, _log_level_str, logging.DEBUG)
_verbose_console = os.environ.get('NOISE_SURVEY_VERBOSE', '').strip().lower() in ('1', 'true', 'yes')
_log_file_path = os.environ.get('NOISE_SURVEY_LOG_FILE') or os.path.join(
    tempfile.gettempdir(), 'noise_survey_analysis.log'
)


def _configure_logging():
    """Wire up the file handler and the console/status-pane handler once."""
    root = logging.getLogger()
    if getattr(root, '_noise_survey_configured', False):
        return
    root.setLevel(logging.DEBUG)

    for existing in list(root.handlers):
        root.removeHandler(existing)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    try:
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            _log_file_path, maxBytes=5_000_000, backupCount=3, encoding='utf-8'
        )
        file_handler.setLevel(_log_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception as exc:  # pragma: no cover - falls back to console only
        print(f"Could not open log file {_log_file_path}: {exc}")

    if _verbose_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(_log_level)
        console_handler.setFormatter(formatter)
    else:
        # Warnings and errors become events in the status pane; writing them
        # straight to stdout would corrupt the pane's cursor arithmetic.
        console_handler = status_console.StatusConsoleHandler()
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
    root.addHandler(console_handler)

    # Bokeh and Tornado are chatty at INFO and say nothing we need on console.
    for noisy in ('bokeh', 'tornado', 'urllib3', 'matplotlib'):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root._noise_survey_configured = True


_configure_logging()
logger = logging.getLogger(__name__)

# --- Process-level cache for parsed data ---
# This cache persists across Bokeh sessions AND module reloads to avoid re-parsing the same files
# Bokeh's autoreload feature reloads modules, so we use a singleton pattern with a lock file
import sys
import tempfile
import pickle
from pathlib import Path

DATA_MANAGER_CACHE_VERSION = "datamanager-v2"


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
                    loaded = pickle.load(f)
                if isinstance(loaded, dict):
                    self._data = {
                        key: value
                        for key, value in loaded.items()
                        if isinstance(key, str)
                        and key.startswith(f"{DATA_MANAGER_CACHE_VERSION}:")
                    }
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
_audio_alignment_cache = AudioAlignmentCache()


def _load_logs_needed_for_audio_alignment(app_data):
    """Load deferred logger data only for positions that contain audio."""
    for position_name in app_data.positions():
        position_data = app_data[position_name]
        if not getattr(position_data, 'has_audio_files', False):
            continue
        log_paths = getattr(position_data, 'log_file_paths', None) or []
        already_loaded = bool(getattr(position_data, '_log_data_loaded', False))
        if not log_paths or already_loaded:
            continue
        try:
            logger.info("Loading deferred log data for audio alignment: %s", position_name)
            position_data.load_log_data_lazy(app_data.parser_factory, app_data.use_cache)
        except Exception as exc:
            logger.warning(
                "Could not load deferred log data for audio alignment at '%s': %s",
                position_name,
                exc,
                exc_info=True,
            )


def _build_audio_availability_data(app_data):
    """Build equal-length audio availability and alignment metadata columns."""
    positions = list(app_data.positions())
    data = {
        'position_id': positions,
        'has_audio': [],
        'anchor_source': [],
        'anchor_confidence': [],
        'anchor_warning': [],
        'correlation_offset_sec': [],
        'correlation_score': [],
    }
    for position_name in positions:
        position_data = app_data[position_name]
        data['has_audio'].append(bool(getattr(position_data, 'has_audio_files', False)))
        audio_files = getattr(position_data, 'audio_files_list', None)
        first_audio = audio_files.iloc[0] if audio_files is not None and not audio_files.empty else None
        for field_name in ('anchor_source', 'anchor_confidence', 'anchor_warning'):
            value = first_audio.get(field_name) if first_audio is not None and field_name in audio_files.columns else ''
            data[field_name].append('' if value is None or pd.isna(value) else str(value))
        for field_name in ('correlation_offset_sec', 'correlation_score'):
            value = first_audio.get(field_name) if first_audio is not None and field_name in audio_files.columns else float('nan')
            data[field_name].append(float(value) if value is not None and not pd.isna(value) else float('nan'))
    return data

def _get_cache_key(source_configs):
    """Generate a cache key from source configurations."""
    try:
        source_fingerprint = build_source_fingerprint(source_configs)
        if source_fingerprint is None:
            logger.debug("_get_cache_key: No source configs provided, returning None")
            return None
        cache_key = f"{DATA_MANAGER_CACHE_VERSION}:{source_fingerprint}"
        logger.info(f"Generated cache key (length: {len(cache_key)}, first 100 chars): {cache_key[:100]}...")
        return cache_key
    except Exception as e:
        logger.error(f"Failed to generate cache key: {e}", exc_info=True)
        return None


def create_app(doc, config_path=None, state_path=None, create_static=False,
               startup_overrides=None):
    """
    This function is the entry point for the LIVE Bokeh server application.

    Args:
        startup_overrides: Optional dict with validated deep-link overrides.
            Supported keys: ``start`` (float), ``end`` (float),
            ``param`` (str), ``view`` (str).  These override workspace/default
            state at startup (applied after workspace restore).
    """
    # Bokeh reconfigures logging when it starts a session, so re-assert ours.
    _configure_logging()
    if not create_static:
        status_console.install()

    logger.info("--- New client session started. Creating live application instance. ---")

    _overrides: dict = startup_overrides or {}
    if _overrides:
        _ov_errors = _overrides.pop("_errors", {})
        if _ov_errors:
            logger.warning("Deep-link parameter errors ignored at startup: %s", _ov_errors)
        logger.info("Deep-link startup overrides: %s", _overrides)

    # Durable setup state saved into the config alongside the source list.
    # The config supplies the baseline; anything given in the URL wins, so a
    # deep link can still point someone at a specific window without editing
    # the job's saved defaults.
    _extras_path = _normalize_path(config_path)
    _config_extras = load_config_extras(_extras_path) if _extras_path else {'positions': {}, 'default_view': {}}
    _saved_offsets = _config_extras.get('positions') or {}
    for _key, _value in (_config_extras.get('default_view') or {}).items():
        _overrides.setdefault(_key, _value)

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
            text="""<h1 style='text-align:center; color:#334155; font-weight:600;'>Loading Survey Data...</h1>
                    <p style='text-align:center; color:#64748b;'>This may take a moment for large surveys.</p>""",
            width=800, align='center',
            styles={'margin': 'auto', 'padding-top': '100px'}
        )
        doc.add_root(apply_theme(loading_div))
        
        # Save a config derived from the user's selection and kick off static export in background
        # Only create static HTML if explicitly requested via --create-static flag
        if create_static and not skip_static_export:
            try:
                # If a config file was already provided, use it directly rather than re-saving
                if config_path:
                    cfg_path = config_path
                    logger.info(f"Using existing config for static export: {cfg_path}")
                else:
                    cfg_path = save_config_from_selected_sources(source_configs)
                if cfg_path:
                    logger.info(f"Starting static export in background from: {cfg_path}")
                    threading.Thread(target=generate_static_html, args=(str(cfg_path),), daemon=True).start()
                else:
                    logger.warning("Auto-save of selector config failed or returned no path; skipping static export.")
            except Exception as e:
                logger.error(f"Error during auto-save/config-based static export: {e}", exc_info=True)
        else:
            if skip_static_export:
                logger.info("Skipping static export (loading from existing config/workspace).")
            if not create_static:
                logger.info("Skipping static export (use --create-static to generate static HTML).")
        
        # This function will run after the loading screen is displayed.
        def build_dashboard():
            nonlocal initial_saved_workspace_state
            
            # Check cache for existing DataManager
            cache_key = _get_cache_key(source_configs)
            logger.debug("Cache lookup: key=%s, %d entries held",
                         '<None>' if cache_key is None else f'{len(cache_key)} chars',
                         len(_data_manager_cache))
            if cache_key and len(_data_manager_cache) > 0 and cache_key not in _data_manager_cache:
                # Near-miss keys are the usual cause of an unexpected re-parse.
                for existing_key in _data_manager_cache.keys():
                    if len(cache_key) == len(existing_key):
                        diffs = [i for i in range(len(cache_key)) if cache_key[i] != existing_key[i]]
                        logger.debug("  near-miss key, differs at %s", diffs[:10])
                    else:
                        logger.debug("  key length mismatch: %d vs %d", len(cache_key), len(existing_key))

            cache_hit = bool(cache_key and cache_key in _data_manager_cache)
            if cache_hit:
                logger.info("Parse cache HIT; reusing cached DataManager.")
                # Every Bokeh session mutates its DataManager while streaming.
                # Keep the shared cache pristine and give the session an isolated copy.
                app_data = copy.deepcopy(_data_manager_cache[cache_key])
            else:
                logger.info("Parse cache MISS; creating new DataManager.")
                status_console.start_phase('load', 'Parsing survey files')
                app_data = DataManager(source_configurations=source_configs)
                status_console.end_phase('Parsed survey files', category='ok')
                if cache_key:
                    # Cache only the lightweight initial DataManager. Audio alignment
                    # may hydrate hundreds of MB of deferred log arrays below.
                    _data_manager_cache[cache_key] = copy.deepcopy(app_data)
                    logger.debug("Stored DataManager in cache (key length %d)", len(cache_key))

            alignment_cache_key = build_audio_alignment_cache_key(
                source_configs,
                AUDIO_ANCHORING_SETTINGS,
            )
            alignment_snapshot = _audio_alignment_cache.get(alignment_cache_key)
            if alignment_snapshot is not None and restore_audio_alignment(app_data, alignment_snapshot):
                logger.info("Audio alignment cache HIT; reusing anchored audio metadata.")
            else:
                logger.info("Audio alignment cache MISS; computing alignment once.")
                # The live dashboard normally defers large log files until the user
                # zooms in. Audio alignment is the exception: its bounded envelope
                # check needs the same meter's 1-second broadband log.
                status_console.start_phase('audio', 'Anchoring audio to survey clock')
                _load_logs_needed_for_audio_alignment(app_data)
                audio_processor = AudioDataProcessor()
                audio_processor.anchor_audio_files(app_data)
                _audio_alignment_cache.put(
                    alignment_cache_key,
                    capture_audio_alignment(app_data),
                )
                status_console.end_phase('Audio anchored', category='ok')

            status_console.write_block(
                status_console.build_startup_summary(
                    app_data,
                    config_path=config_path,
                    job_number=current_job_number,
                    cache_hit=cache_hit,
                )
            )
            audio_handler = AudioPlaybackHandler(position_data=app_data.get_all_position_data())
            audio_control_source = ColumnDataSource(data={'command': [], 'position_id': [], 'value': []}, name='audio_control_source')
            audio_status_source = ColumnDataSource(data={'is_playing': [False], 'current_time': [0], 'playback_rate': [1.0], 'current_file_duration': [0], 'current_file_start_time': [0], 'active_position_id': [None], 'volume_boost': [False], 'current_file_name': ['']}, name='audio_status_source')
            audio_availability_source = ColumnDataSource(
                data=_build_audio_availability_data(app_data),
                name='audio_availability_source',
            )
            session_action_source = ColumnDataSource(
                data={'command': [None], 'request_id': [None], 'payload': [None]},
                name='session_action_source'
            )
            session_status_source = ColumnDataSource(
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
            control_state_source = ColumnDataSource(
                data={
                    'parameter': [None],
                    'view_mode': [None],
                    'updated_at': [0],
                },
                name='control_state_source'
            )
            automation_command_source = ColumnDataSource(
                data={'command': [None], 'request_id': [None], 'payload': [None]},
                name='automation_command_source'
            )
            automation_result_source = ColumnDataSource(
                data={
                    'request_id': [None],
                    'success': [False],
                    'message': [''],
                    'data': [None],
                    'updated_at': [0],
                },
                name='automation_result_source'
            )

            def handle_static_export_request(payload=None, request_id=None):
                logger.info(f"Session static export requested (request_id={request_id})")
                try:
                    cfg_path = save_config_from_selected_sources(source_configs)
                    if not cfg_path:
                        return {
                            'success': False,
                            'message': 'Static HTML export failed: unable to build a config from the current data sources.',
                            'output_path': '',
                        }

                    output_path = generate_static_html(config_path=str(cfg_path), resources='INLINE')
                    if output_path:
                        output_path_str = str(output_path)
                        return {
                            'success': True,
                            'message': f'Static HTML export complete: {output_path_str}',
                            'output_path': output_path_str,
                        }

                    return {
                        'success': False,
                        'message': 'Static HTML export failed. Check server logs for details.',
                        'output_path': '',
                    }
                except Exception as exc:
                    logger.error(f"Session static export failed (request_id={request_id}): {exc}", exc_info=True)
                    return {
                        'success': False,
                        'message': f'Static HTML export failed: {exc}',
                        'output_path': '',
                    }

            def handle_save_setup_request(payload=None, request_id=None):
                """Write the current offsets and view back into the job's config."""
                if not _extras_path:
                    return {
                        'success': False,
                        'message': 'No config file is attached to this session, so there is nothing to save into. '
                                   'Open the dashboard with ?config=... to enable this.',
                        'output_path': '',
                    }
                try:
                    positions = {}
                    for position_id in app_data.positions():
                        entry = {}
                        for prefix, key in (
                            ('chart_offset_spinner', 'chart_offset_seconds'),
                            ('audio_offset_spinner', 'audio_offset_seconds'),
                        ):
                            spinner = doc.get_model_by_name(f"{prefix}_{position_id}")
                            if spinner is not None and spinner.value is not None:
                                entry[key] = float(spinner.value)
                        if entry:
                            positions[position_id] = entry

                    default_view = {}
                    x_range = doc.get_model_by_name('master_x_range')
                    if x_range is not None and x_range.start is not None and x_range.end is not None:
                        default_view['start'] = float(x_range.start)
                        default_view['end'] = float(x_range.end)
                    param_select = doc.get_model_by_name('global_parameter_selector')
                    if param_select is not None and getattr(param_select, 'value', None):
                        default_view['param'] = str(param_select.value)

                    saved = save_state_to_config(_extras_path, positions, default_view)
                    if not saved:
                        return {
                            'success': False,
                            'message': 'Could not write to the config file. Check server logs and file permissions.',
                            'output_path': '',
                        }

                    offsets_desc = ', '.join(
                        f"{pos}: {entry.get('chart_offset_seconds', 0):+.1f}s"
                        for pos, entry in positions.items()
                    ) or 'no offsets'
                    status_console.event('ok', f"Saved setup to config ({offsets_desc})")
                    return {
                        'success': True,
                        'message': f'Saved offsets and current view to {os.path.basename(str(saved))}.',
                        'output_path': str(saved),
                    }
                except Exception as exc:
                    logger.error(f"Saving setup to config failed (request_id={request_id}): {exc}", exc_info=True)
                    return {'success': False, 'message': f'Saving setup failed: {exc}', 'output_path': ''}

            app_callbacks = AppCallbacks(
                doc,
                audio_handler,
                audio_control_source,
                audio_status_source,
                session_action_source=session_action_source,
                session_status_source=session_status_source,
                static_export_request_handler=handle_static_export_request,
                save_setup_request_handler=handle_save_setup_request,
            )
            doc.clear() # Clear the loading message
            dash_builder = DashBuilder(
                audio_control_source,
                audio_status_source,
                session_action_source=session_action_source,
                session_status_source=session_status_source,
                control_state_source=control_state_source,
                automation_command_source=automation_command_source,
                automation_result_source=automation_result_source,
            )
            dash_builder.build_layout(
                doc,
                app_data,
                CHART_SETTINGS,
                source_configs=source_configs,
                saved_workspace_state=initial_saved_workspace_state,
                job_number=current_job_number,
                server_mode=STREAMING_ENABLED,
                position_offsets=_saved_offsets,
            )
            doc.add_root(audio_control_source)
            doc.add_root(audio_status_source)
            doc.add_root(audio_availability_source)
            doc.add_root(session_action_source)
            doc.add_root(session_status_source)
            doc.add_root(control_state_source)
            doc.add_root(automation_command_source)
            doc.add_root(automation_result_source)
            if STREAMING_ENABLED:
                server_data_handler = ServerDataHandler(doc, app_data, CHART_SETTINGS)
                app_callbacks.set_server_data_handler(server_data_handler)
            app_callbacks.attach_callbacks()
            setattr(doc.session_context, '_app_callback_manager', app_callbacks)
            initial_saved_workspace_state = None

            # --- Register session with the control bridge ---
            try:
                master_x_range = doc.get_model_by_name('master_x_range')
                param_select = doc.get_model_by_name('global_parameter_selector')
                view_toggle = doc.get_model_by_name('global_view_toggle')
                control_state_source = doc.get_model_by_name('control_state_source')
                automation_command_source = doc.get_model_by_name('automation_command_source')
                automation_result_source = doc.get_model_by_name('automation_result_source')
                _session_bridge.register(
                    doc,
                    master_x_range=master_x_range,
                    param_select=param_select,
                    view_toggle=view_toggle,
                    control_state_source=control_state_source,
                    automation_command_source=automation_command_source,
                    automation_result_source=automation_result_source,
                )

                def _handle_automation_result(attr, old, new):
                    try:
                        request_id = new.get('request_id', [None])[0]
                        if not request_id:
                            return

                        payload_raw = new.get('data', [None])[0]
                        payload = payload_raw
                        if isinstance(payload_raw, str) and payload_raw:
                            try:
                                payload = json.loads(payload_raw)
                            except Exception:
                                payload = payload_raw

                        _session_bridge.record_js_result({
                            'request_id': str(request_id),
                            'success': bool(new.get('success', [False])[0]),
                            'message': str(new.get('message', [''])[0] or ''),
                            'data': payload,
                        })
                    except Exception as _result_exc:
                        logger.warning("Could not process automation result payload: %s", _result_exc)

                automation_result_source.on_change('data', _handle_automation_result)
            except Exception as _exc:
                logger.warning("Could not register session bridge: %s", _exc)

            # Saved offsets are applied at widget construction (see
            # position_offsets on build_layout above), so nothing to do here.
            for _position_id in _saved_offsets:
                if _position_id not in set(app_data.positions()):
                    logger.warning(
                        "Config holds offsets for '%s', which is not in this data set; "
                        "the position may have been renamed since it was saved.",
                        _position_id,
                    )

            # --- Apply deep-link startup overrides ---
            _start_override = _overrides.get('start')
            _end_override = _overrides.get('end')
            if _start_override is not None and _end_override is not None:
                _session_bridge.set_viewport(_start_override, _end_override)

            _view_override = _overrides.get('view')
            if _view_override is not None:
                _session_bridge.set_view_mode(_view_override)

            _param_override = _overrides.get('param')
            if _param_override is not None:
                _session_bridge.set_parameter(_param_override)

        schedule_when_client_connected(doc, build_dashboard)
    
    # IMPORTANT: Add loading div synchronously BEFORE any async callbacks
    # This ensures the document has content when the initial HTTP response is sent
    loading_div = Div(
        text="""<h1 style='text-align:center; color:#334155; font-weight:600; margin-top:100px;'>Initializing Dashboard...</h1>
                <p style='text-align:center; color:#64748b;'>Loading survey data, please wait...</p>""",
        width=800, align='center',
        styles={'margin': 'auto', 'padding-top': '100px'}
    )
    doc.add_root(apply_theme(loading_div))

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
                        doc.add_next_tick_callback(lambda: on_data_sources_selected(source_configs_from_state, skip_static_export=not create_static))
                    else:
                        logger.error("Workspace file has no sourceConfigs. Falling back to selector.")
                        doc.clear()  # Remove loading div
                        selector = create_data_source_selector(doc, on_data_sources_selected)
                        doc.add_root(apply_theme(selector.get_layout()))
                else:
                    # Regular config file - use the existing loader
                    _, source_configs, loaded_job_number = load_config_and_prepare_sources(config_path=config_path)
                    if source_configs is not None:
                        doc.add_next_tick_callback(lambda: on_data_sources_selected(source_configs, skip_static_export=not create_static, job_number=loaded_job_number))
                    else:
                        logger.error(f"Failed to load from config file {config_path}. Falling back to selector.")
                        doc.clear()  # Remove loading div
                        selector = create_data_source_selector(doc, on_data_sources_selected)
                        doc.add_root(apply_theme(selector.get_layout()))
            except Exception as e:
                logger.error(f"Error reading config/workspace file {config_path}: {e}", exc_info=True)
                doc.clear()  # Remove loading div
                selector = create_data_source_selector(doc, on_data_sources_selected)
                doc.add_root(apply_theme(selector.get_layout()))
        else:
            # Show data source selector initially if no config path is provided
            logger.info("No config file provided. Showing data source selector...")
            doc.clear()  # Remove loading div
            selector = create_data_source_selector(doc, on_data_sources_selected)
            doc.add_root(apply_theme(selector.get_layout()))
    def _on_session_destroyed(
        session_context,
        _session_destroyed=session_destroyed,
        _bridge=_session_bridge,
    ):
        _session_destroyed(session_context)
        _bridge.unregister()

    doc.on_session_destroyed(_on_session_destroyed)

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
    
    # Check for --create-static flag
    create_static = _extract_request_argument(request_arguments, 'create-static', 'create_static') is not None
    if not create_static:
        create_static = _extract_argv_argument('--create-static', '--create_static') is not None
    if not create_static:
        create_static = '--create-static' in sys.argv or '--create_static' in sys.argv

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

    # --- Deep-link startup overrides ---
    _deep_link_overrides = parse_deep_link_params(request_arguments)
    _dl_errors = _deep_link_overrides.get('_errors', {})
    if _dl_errors:
        logger.warning("Deep-link URL parameter validation errors: %s", _dl_errors)

    # --- Optional control server startup (first session only) ---
    _raw_control_port = _extract_argv_argument('--control-port', '--control_port')
    if _raw_control_port is not None:
        if _control_server is None or not _control_server.is_running:
            try:
                _control_port_int = int(_raw_control_port)
                _control_server = ControlServer(_session_bridge)
                _control_server.start(port=_control_port_int)
            except Exception as _cs_exc:
                logger.error("Failed to start control server: %s", _cs_exc)

    create_app(
        doc,
        config_path=config_file_path,
        state_path=state_file_path,
        create_static=create_static,
        startup_overrides=_deep_link_overrides,
    )
else:
    # No session context, so we're running as a standalone script.
    # This block will be executed when running `python main.py ...`
    main()
