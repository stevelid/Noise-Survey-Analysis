import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from noise_survey_analysis.core.utils import find_lowest_common_folder

logger = logging.getLogger(__name__)


def save_config_from_selected_sources(selected_sources: list) -> Path | None:
    """
    Save a configuration JSON derived from the selector's selected sources.
    Returns the full path to the saved config file, or None on failure.

    This function is intentionally independent of Bokeh so it can be reused
    from both the server path and CLI utilities.
    """
    try:
        # Extract file paths
        file_paths = [src.get('file_path') for src in selected_sources if src.get('file_path')]
        if not file_paths:
            logger.warning("No file paths provided in selected sources; skipping config save.")
            return None

        # Choose a base directory as the lowest common folder; if none (e.g., different drives),
        # fall back to the directory of the first file path
        base_dir = find_lowest_common_folder(file_paths)
        if not base_dir:
            try:
                base_dir = os.path.dirname(os.path.abspath(file_paths[0]))
            except Exception:
                base_dir = os.getcwd()

        # Try to infer a job number from the base_dir name or any file path
        job_num = None
        base_name = os.path.basename(base_dir)
        m = re.search(r"(\d{3,})", base_name)
        if m:
            job_num = m.group(1)
        else:
            # Fallback: look through file paths
            for p in file_paths:
                m2 = re.search(r"(\d{3,})", os.path.basename(p))
                if m2:
                    job_num = m2.group(1)
                    break
        if not job_num:
            job_num = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Build config payload
        config_data = {
            "version": "1.2",
            "created_at": datetime.now().isoformat(),
            "config_base_path": base_dir.replace('\\', '/'),
            "output_filename": f"{job_num}_survey_dashboard.html",
            "sources": []
        }

        for src in selected_sources:
            full_path = src.get('file_path')
            if not full_path:
                continue
            try:
                rel_path = os.path.relpath(full_path, base_dir)
            except ValueError:
                # Different drives; keep absolute
                rel_path = os.path.abspath(full_path)

            config_data["sources"].append({
                "path": rel_path.replace('\\', '/'),
                "position": src.get('position_name', '') or '',
                "type": src.get('data_type', 'unknown'),
                "parser_type": src.get('parser_type', 'auto')
            })

        # Determine config file path; overwrite if exists
        cfg_name = f"noise_survey_config_{job_num}.json"
        cfg_path = Path(base_dir) / cfg_name

        with open(cfg_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Configuration saved automatically to: {cfg_path}")
        return cfg_path
    except Exception as e:
        logger.error(f"Failed to auto-save configuration from selected sources: {e}", exc_info=True)
        return None
