import os
import re
import logging
from pathlib import Path
from typing import Optional

from bokeh.document import Document
from bokeh.embed import file_html
from bokeh.resources import CDN, INLINE

from noise_survey_analysis.core.app_setup import load_config_and_prepare_sources
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.visualization.dashBuilder import DashBuilder

logger = logging.getLogger(__name__)


def generate_static_html(config_path: str, resources: str = "CDN") -> Optional[Path]:
    """
    Builds the dashboard layout from a config file and saves it as a standalone HTML file.

    Args:
        config_path: Path to the saved JSON config (as produced by the selector or provided manually)
        resources: 'CDN' (default) or 'INLINE' to control Bokeh resource embedding

    Returns:
        pathlib.Path to the written HTML on success, or None on failure.
    """
    try:
        logger.info(f"--- Generating static HTML from config: {config_path} ---")

        # Load config and prepare sources once.
        loaded_filename, source_configs = load_config_and_prepare_sources(config_path=config_path)
        if source_configs is None:
            logger.error("Could not load source configurations. Aborting static generation.")
            return None

        # Determine output filename from config path
        config_filename = Path(config_path).name
        job_number_match = re.search(r"(\d+)", config_filename)
        if job_number_match:
            job_number = job_number_match.group(1)
            output_filename = f"{job_number}_survey_dashboard.html"
        else:
            # Fallback to the name specified inside the config file, or a default.
            output_filename = loaded_filename or "default_dashboard.html"
            logger.warning(
                f"Could not find job number in '{config_filename}'. Falling back to filename: {output_filename}"
            )

        # The output directory is the same as the config file's directory.
        output_dir = Path(config_path).parent
        output_full_path = output_dir / output_filename

        logger.info(f"Output will be saved to: {output_full_path}")

        # 1. Load Data
        app_data = DataManager(source_configurations=source_configs)

        # 2. Instantiate builder (no audio for static version)
        dash_builder = DashBuilder(audio_control_source=None, audio_status_source=None)

        # 3. Create and build document
        static_doc = Document()
        dash_builder.build_layout(static_doc, app_data, CHART_SETTINGS)

        # 4. Save the document using file_html (works under bokeh serve and CLI)
        try:
            res = CDN if str(resources).upper() == "CDN" else INLINE
            html = file_html(static_doc, res, title="Noise Survey Dashboard")
            with open(output_full_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"--- Static HTML file saved successfully to {output_full_path} ---")
            return output_full_path
        except Exception as e:
            logger.error(f"Failed to save static HTML file: {e}", exc_info=True)
            return None

    except Exception as e:
        logger.error(f"Static export failed: {e}", exc_info=True)
        return None
