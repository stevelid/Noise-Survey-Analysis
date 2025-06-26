import logging
from bokeh.plotting import curdoc
from bokeh.layouts import LayoutDOM
from bokeh.models import Div, ColumnDataSource # Import for assertions and error messages
import pandas as pd
import numpy as np  # Import numpy for array operations
import os
from bokeh.resources import CDN
from bokeh.embed import file_html  # Add import for standalone HTML generation
import logging

import sys
from pathlib import Path
current_file = Path(__file__)
project_root = current_file.parent.parent  # Go up to "Noise Survey Analysis"
sys.path.insert(0, str(project_root))

from noise_survey_analysis.core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS
from noise_survey_analysis.core.data_manager import DataManager, PositionData
from noise_survey_analysis.core.data_processors import GlyphDataProcessor
from noise_survey_analysis.visualization.dashBuilder import DashBuilder

logger = logging.getLogger(__name__)

# ==============================================================================
# 1. SETUP
# ==============================================================================
print("--- Application Start ---")

OUTPUT_FILENAME = "noise_survey_analysis.html"

# ==============================================================================
# 2. DATA LOADING
# ==============================================================================
print("--- Loading Data ---")

# Load data from a configuration file or directory

sentry_file_path = r"G:\My Drive\Programing\example files\Noise Sentry\cricket nets 2A _2025_06_03__20h55m22s_2025_05_29__15h30m00s.csv"   

svan_log_path = r"G:\My Drive\Programing\example files\Svan full data\L259_log.csv"
svan_summary_path = r"G:\My Drive\Programing\example files\Svan full data\L259_summary.csv"

nti_rta_log_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Log.txt"
nti_123_log_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_00_123_Log.txt"
nti_123_Rpt_Report_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_00_123_Rpt_Report.txt"
nti_RTA_Rpt_Report_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Rpt_Report.txt"

audio_dir = r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\5793-1"

SOURCE_CONFIGURATIONS = [
        {"position_name": "SiteSvan", "file_paths": {svan_summary_path}, "enabled": False}, 
        {"position_name": "SiteSvan", "file_paths": {svan_log_path, svan_summary_path}, "enabled": True}, 
        {"position_name": "SiteNTi", "file_paths": {nti_rta_log_path, nti_123_log_path}, "parser_type_hint": "NTi", "enabled": False},
        {"position_name": "SiteNti", "file_path": audio_dir, "enabled": False},
        {"position_name": "SiteMissing", "file_path": "nonexistent.csv", "enabled": False}
    ]
app_data = DataManager(source_configurations=SOURCE_CONFIGURATIONS)

# ==============================================================================
# 3. UI COMPONENT CREATION
# ==============================================================================

print("--- Creating UI Components ---")

# Create a Bokeh document
doc = curdoc()

DashBuilder(None).build_layout(doc, app_data, CHART_SETTINGS)

# Save the document to an HTML file
try:
    with open(OUTPUT_FILENAME, "w", encoding="utf-8") as f:
        # file_html generates a complete HTML document from the Bokeh layout
        html = file_html(doc, CDN, "Noise Survey Dashboard")
        f.write(html)
    print(f"Successfully generated {OUTPUT_FILENAME}. Open this file in your browser.")
except Exception as e:
    print(f"ERROR: Could not generate HTML file. Reason: {e}")

print("--- Application End ---")




