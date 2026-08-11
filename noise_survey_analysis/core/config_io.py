import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from noise_survey_analysis.core.utils import find_lowest_common_folder

logger = logging.getLogger(__name__)


def _extract_source_file_paths(source: Dict[str, Any]) -> List[str]:
    """Return a deduplicated list of file paths from a source config."""
    paths: List[str] = []
    seen = set()

    single_path = source.get('file_path')
    if isinstance(single_path, str):
        normalized = single_path.strip()
        if normalized and normalized not in seen:
            paths.append(normalized)
            seen.add(normalized)

    multi_paths = source.get('file_paths')
    if isinstance(multi_paths, str):
        normalized = multi_paths.strip()
        if normalized and normalized not in seen:
            paths.append(normalized)
            seen.add(normalized)
    elif isinstance(multi_paths, (list, tuple, set)):
        for path_value in multi_paths:
            if not isinstance(path_value, str):
                continue
            normalized = path_value.strip()
            if not normalized or normalized in seen:
                continue
            paths.append(normalized)
            seen.add(normalized)

    return paths


def save_state_to_config(
    config_path: str | Path,
    positions: Optional[Dict[str, Dict[str, float]]] = None,
    default_view: Optional[Dict[str, Any]] = None,
) -> Path | None:
    """Merge durable setup state into an existing config file.

    Only the ``positions`` and ``default_view`` blocks are touched. The
    ``sources`` array and every other key are read back and rewritten intact,
    because this file is the job's source-of-truth for what data gets loaded
    and it lives in the shared job folder.

    The write goes to a temporary file in the same directory and is then moved
    over the original, so an interrupted save cannot leave a job with a
    half-written config.

    Returns the config path on success, or None on failure.
    """
    target = Path(config_path)
    try:
        with open(target, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if not isinstance(config, dict):
            logger.error("Config at %s is not a JSON object; refusing to write state.", target)
            return None
    except (FileNotFoundError, json.JSONDecodeError, OSError) as exc:
        logger.error("Cannot read config at %s to merge state: %s", target, exc)
        return None

    if positions:
        merged = config.get('positions')
        if not isinstance(merged, dict):
            merged = {}
        for name, entry in positions.items():
            if not isinstance(entry, dict):
                continue
            existing = merged.get(name) if isinstance(merged.get(name), dict) else {}
            updated = dict(existing)
            for key in ('chart_offset_seconds', 'audio_offset_seconds'):
                if key in entry:
                    try:
                        updated[key] = round(float(entry[key]), 4)
                    except (TypeError, ValueError):
                        continue
            if updated:
                merged[str(name)] = updated
        config['positions'] = merged

    if default_view:
        view_block = {}
        for key in ('start', 'end'):
            if default_view.get(key) is not None:
                try:
                    view_block[key] = float(default_view[key])
                except (TypeError, ValueError):
                    continue
        for key in ('view', 'param'):
            value = default_view.get(key)
            if isinstance(value, str) and value.strip():
                view_block[key] = value.strip()
        if view_block:
            config['default_view'] = view_block

    config['state_saved_at'] = datetime.now().isoformat()

    tmp_path = target.with_suffix(target.suffix + '.tmp')
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
        os.replace(tmp_path, target)
    except OSError as exc:
        logger.error("Failed to write config state to %s: %s", target, exc)
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except OSError:
            pass
        return None

    logger.info(
        "Saved setup state to %s (%d position offset(s), default_view=%s).",
        target, len(positions or {}), bool(default_view),
    )
    return target


def save_config_from_selected_sources(selected_sources: list) -> Path | None:
    """
    Save a configuration JSON derived from the selector's selected sources.
    Returns the full path to the saved config file, or None on failure.

    This function is intentionally independent of Bokeh so it can be reused
    from both the server path and CLI utilities.
    """
    try:
        # Extract file paths
        file_paths: List[str] = []
        for src in selected_sources:
            if not isinstance(src, dict):
                continue
            file_paths.extend(_extract_source_file_paths(src))

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
            if not isinstance(src, dict):
                continue
            position_name = src.get('position_name') or src.get('position') or ''
            parser_type = src.get('parser_type') or src.get('parser_type_hint') or 'auto'
            data_type = src.get('data_type') or src.get('type') or 'unknown'

            for full_path in _extract_source_file_paths(src):
                try:
                    rel_path = os.path.relpath(full_path, base_dir)
                except ValueError:
                    # Different drives; keep absolute
                    rel_path = os.path.abspath(full_path)

                config_data["sources"].append({
                    "path": rel_path.replace('\\', '/'),
                    "position": position_name,
                    "type": data_type,
                    "parser_type": parser_type
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
