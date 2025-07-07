import logging
from re import L
from bokeh.plotting import curdoc
from bokeh.models import ColumnDataSource
from bokeh.io import output_file, save
from bokeh.document import Document
import sys
from pathlib import Path

# --- Project Root Setup ---
current_file = Path(__file__)
project_root = current_file.parent.parent
sys.path.insert(0, str(project_root))

from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler
from noise_survey_analysis.core.app_callbacks import AppCallbacks, session_destroyed
from noise_survey_analysis.visualization.dashBuilder import DashBuilder

# --- Configure Logging ---
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration for static file output ---
OUTPUT_FILENAME = "noise_survey_dashboard_static.html"


def generate_static_html():
    """
    Builds the dashboard layout and saves it as a standalone HTML file.
    This version will not have a live Python backend.
    """
    logger.info(f"--- Generating static HTML file: {OUTPUT_FILENAME} ---")
    
    # 1. Load Data (same as the server app)
    entry_file_path = r"G:\My Drive\Programing\example files\Noise Sentry\cricket nets 2A _2025_06_03__20h55m22s_2025_05_29__15h30m00s.csv"   

    svan_log_path = r"G:\My Drive\Programing\example files\Svan full data\L259_log.csv"
    svan_summary_path = r"G:\My Drive\Programing\example files\Svan full data\L259_summary.csv"

    nti_rta_log_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Log.txt"
    nti_123_log_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_123_Log.txt"
    nti_123_Rpt_Report_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_123_Rpt_Report.txt"
    nti_RTA_Rpt_Report_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Rpt_Report.txt"

    audio_dir = r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\5793-1"

    SOURCE_CONFIGURATIONS = [
            {"position_name": "SiteSvan", "file_paths": {svan_summary_path}, "enabled": False}, 
            {"position_name": "SiteSvan", "file_paths": {svan_log_path, svan_summary_path}, "enabled": False
            }, 
            {"position_name": "SiteNTi", "file_paths": {nti_rta_log_path, nti_123_log_path, nti_123_Rpt_Report_path, nti_RTA_Rpt_Report_path}, "parser_type_hint": "NTi", "enabled": True},
            {"position_name": "SiteNTi", "file_path": audio_dir, "enabled": True},
            {"position_name": "SiteMissing", "file_path": "nonexistent.csv", "enabled": False},
            {"position_name": "East", "file_paths": {r"G:\Shared drives\Venta\Jobs\5973 Norfolk Feather Site, Diss, Norfolk\5973 Surveys\5973 Norfolk Feather Site, Diss, Norfolk_summary.csv", 
                r"G:\Shared drives\Venta\Jobs\5973 Norfolk Feather Site, Diss, Norfolk\5973 Surveys\5973 Norfolk Feather Site, Diss, Norfolk_log.csv"}, "enabled": True}
        ]
    app_data = DataManager(source_configurations=SOURCE_CONFIGURATIONS)

    print("\nDataManager: Data loading complete.")
    for position_name, data in app_data.get_all_position_data().items():
        print(f"\n--- Position: {position_name} ---")
        if data.log_totals is not None:
            print(f"Log Totals DataFrame Shape: {data.log_totals.shape}")
            print("Log Totals DataFrame Columns:", data.log_totals.columns.tolist())
            print("Log Totals DataFrame Head:")
            print(data.log_totals.head(5)) # Print more rows
        else:
            print("Log Totals DataFrame: None")

        if data.log_spectral is not None:
            print(f"Log Spectral DataFrame Shape: {data.log_spectral.shape}")
            print("Log Spectral DataFrame Columns:", data.log_spectral.columns.tolist())
            print("Log Spectral DataFrame Head:")
            print(data.log_spectral.head(5)) # Print more rows
        else:
            print("Log Spectral DataFrame: None")

        if data.overview_totals is not None:
            print(f"Overview Totals DataFrame Shape: {data.overview_totals.shape}")
            print("Overview Totals DataFrame Columns:", data.overview_totals.columns.tolist())
            print("Overview Totals DataFrame Head:")
            print(data.overview_totals.head(5)) # Print more rows
        else:
            print("Overview Totals DataFrame: None")

        if data.overview_spectral is not None:
            print(f"Overview Spectral DataFrame Shape: {data.overview_spectral.shape}")
            print("Overview Spectral DataFrame Columns:", data.overview_spectral.columns.tolist())
            print("Overview Spectral DataFrame Head:")
            print(data.overview_spectral.head(5)) # Print more rows
        else:
            print("Overview Spectral DataFrame: None")

        if position_name == "SiteNTi":
            print("\n--- Detailed NTi Data Info ---")
            if data.log_totals is not None:
                print("NTi Log Totals DataFrame Info:")
                data.log_totals.info()
                print("\nNTi Log Totals DataFrame Describe:")
                print(data.log_totals.describe())
            if data.log_spectral is not None:
                print("\nNTi Log Spectral DataFrame Info:")
                data.log_spectral.info()
                print("\nNTi Log Spectral DataFrame Describe:")
                print(data.log_spectral.describe())
            if data.overview_totals is not None:
                print("NTi Overview Totals DataFrame Info:")
                data.overview_totals.info()
                print("\nNTi Overview Totals DataFrame Describe:")
                print(data.overview_totals.describe())
            if data.overview_spectral is not None:
                print("\nNTi Overview Spectral DataFrame Info:")
                data.overview_spectral.info()
                print("\nNTi Overview Spectral DataFrame Describe:")
                print(data.overview_spectral.describe())

    # 2. Instantiate builder WITHOUT backend components
    # The DashBuilder will use its default placeholder sources.
    dash_builder = DashBuilder(app_callbacks=None, 
                               audio_control_source=None, 
                               audio_status_source=None)

    # 3. Create a temporary document to build into
    static_doc = Document()

    # 4. Build the layout into the temporary document
    dash_builder.build_layout(static_doc, app_data, CHART_SETTINGS)

    # 5. Save the document to an HTML file
    try:
        output_file(OUTPUT_FILENAME, title="Noise Survey Dashboard")
        save(static_doc)
        logger.info(f"--- Static HTML file saved successfully to {OUTPUT_FILENAME} ---")
    except Exception as e:
        logger.error(f"Failed to save static HTML file: {e}", exc_info=True)


def create_app(doc):
    """
    This function is the entry point for the LIVE Bokeh server application.
    It sets up the data, backend logic, and UI.
    """
    logger.info("--- New client session started. Creating live application instance. ---")
    
    # 1. DATA LOADING
    entry_file_path = r"G:\My Drive\Programing\example files\Noise Sentry\cricket nets 2A _2025_06_03__20h55m22s_2025_05_29__15h30m00s.csv"   

    svan_log_path = r"G:\My Drive\Programing\example files\Svan full data\L259_log.csv"
    svan_summary_path = r"G:\My Drive\Programing\example files\Svan full data\L259_summary.csv"

    nti_rta_log_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Log.txt"
    nti_123_log_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_00_123_Log.txt"
    nti_123_Rpt_Report_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_00_123_Rpt_Report.txt"
    nti_RTA_Rpt_Report_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Rpt_Report.txt"

    audio_dir = r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\5793-1"

    SOURCE_CONFIGURATIONS = [
            {"position_name": "SiteSvan", "file_paths": {svan_summary_path}, "enabled": False}, 
            {"position_name": "SiteSvan", "file_paths": {svan_log_path, svan_summary_path}, "enabled": False
            }, 
            {"position_name": "SiteNTi", "file_paths": {nti_rta_log_path, nti_123_log_path, nti_123_Rpt_Report_path, nti_RTA_Rpt_Report_path}, "parser_type_hint": "NTi", "enabled": True},
            {"position_name": "SiteNTi", "file_path": audio_dir, "enabled": True},
            {"position_name": "SiteMissing", "file_path": "nonexistent.csv", "enabled": False},
            {"position_name": "East", "file_path": {r"G:\Shared drives\Venta\Jobs\5973 Norfolk Feather Site, Diss, Norfolk\5973 Surveys\5973 Norfolk Feather Site, Diss, Norfolk_summary.csv", 
                r"G:\Shared drives\Venta\Jobs\5973 Norfolk Feather Site, Diss, Norfolk\5973 Surveys\5973 Norfolk Feather Site, Diss, Norfolk_log.csv"}, "enabled": True},
        ]
    app_data = DataManager(source_configurations=SOURCE_CONFIGURATIONS)
    
    # 2. BACKEND HANDLER SETUP (for live interaction)
    logger.info("Setting up backend handlers for live session...")
    audio_handler = AudioPlaybackHandler(position_data=app_data.get_all_position_data())
    audio_control_source = ColumnDataSource(data={'command': [], 'position_id': [], 'value': []}, name='audio_control_source')
    audio_status_source = ColumnDataSource(data={'is_playing': [False], 'current_time': [0], 'playback_rate': [1.0], 'current_file_duration': [0], 'current_file_start_time': [0]}, name='audio_status_source')
    app_callbacks = AppCallbacks(doc, audio_handler, audio_control_source, audio_status_source)
    
    # 3. UI BUILD
    logger.info("Building dashboard UI for live session...")
    dash_builder = DashBuilder(app_callbacks, audio_control_source, audio_status_source)
    dash_builder.build_layout(doc, app_data, CHART_SETTINGS)
    
    # 4. FINAL WIRING
    logger.info("Attaching final callbacks for live session...")
    app_callbacks.attach_callbacks()
    doc.on_session_destroyed(session_destroyed)
    setattr(doc.session_context, '_app_callback_manager', app_callbacks)

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
    create_app(doc)