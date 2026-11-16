import os
import re
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

from noise_survey_analysis.core.utils import find_lowest_common_folder

logger = logging.getLogger(__name__)


def read_config_json(path: str | Path) -> Dict[str, Any]:
    """Read a job config as JSON. ``utf-8-sig`` so configs written by PowerShell (BOM) load."""
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)


_LEADING_JOB_NUMBER = re.compile(r'^(\d{4})(?!\d)')
_DATE_FOLDER = re.compile(r'^\d{4}[-_.]\d{2}[-_.]\d{2}')


def detect_job_number(base_dir: str, file_paths: List[str]) -> Optional[str]:
    """Job number from folder names: a leading 4-digit number (``6645 Surveys``, ``6645-4``)
    on the base folder or its nearest ancestors, then on the file names, then (last resort)
    the first digit run of 3+. Date-like names (``2026-11-04 ...``) are never taken as a job number."""
    def leading(name: str) -> Optional[str]:
        if _DATE_FOLDER.match(name):
            return None
        m = _LEADING_JOB_NUMBER.match(name)
        return m.group(1) if m else None

    folder = Path(base_dir)
    for candidate in [folder, *list(folder.parents)[:3]]:
        found = leading(candidate.name)
        if found:
            return found
    for p in file_paths:
        found = leading(os.path.basename(os.path.dirname(p))) or leading(os.path.basename(p))
        if found:
            return found
    for name in [os.path.basename(base_dir), *[os.path.basename(p) for p in file_paths]]:
        if _DATE_FOLDER.match(name):
            continue
        m = re.search(r"(\d{3,})", name)
        if m:
            return m.group(1)
    return None


def _norm_source_path(config_base: Optional[str], path: str) -> str:
    p = str(path or '').replace('\\', '/')
    if config_base and not os.path.isabs(p) and not re.match(r'^[A-Za-z]:', p):
        p = os.path.join(config_base, p)
    return os.path.normcase(os.path.normpath(p))


# Keys the generator/selector decides; everything else on an existing source is user setup.
_SOURCE_CORE_KEYS = ('path', 'position', 'type', 'parser_type')


def merge_config_with_existing(existing: Optional[Dict[str, Any]], new_config: Dict[str, Any]) -> tuple:
    """Merge a freshly built config into an existing one without wiping saved setup.

    * every top-level key of ``existing`` is kept (``positions`` offsets, ``default_view``,
      ``state_saved_at``, anything user-added) except those ``new_config`` owns
      (``version``, ``config_base_path``, ``sources``, ``_instructions``);
    * sources are matched by normalised absolute path: matched ones keep their extras
      (``timezone``, ``columns``, ``profile``, ``y_range``, ``display_title`` ...), new ones are
      added, ones that no longer exist are dropped.

    Returns ``(merged_config, changes)`` where ``changes`` is a list of readable lines.
    """
    if not isinstance(existing, dict):
        return new_config, []
    merged: Dict[str, Any] = dict(existing)
    for key in ('version', 'config_base_path', '_instructions', 'output_filename'):
        if key in new_config:
            merged[key] = new_config[key]
    merged.setdefault('created_at', new_config.get('created_at'))
    merged['updated_at'] = datetime.now().isoformat()

    old_base = existing.get('config_base_path')
    new_base = new_config.get('config_base_path')
    pool: Dict[str, List[Dict[str, Any]]] = {}
    for src in existing.get('sources') or []:
        if isinstance(src, dict) and src.get('path'):
            pool.setdefault(_norm_source_path(old_base, src['path']), []).append(src)

    changes: List[str] = []
    out_sources: List[Dict[str, Any]] = []
    for src in new_config.get('sources') or []:
        key = _norm_source_path(new_base, src.get('path', ''))
        old = pool.get(key, [])
        match = next((o for o in old if o.get('position') == src.get('position')), old[0] if old else None)
        if match is not None:
            old.remove(match)
            combined = dict(match)
            combined.update({k: src[k] for k in _SOURCE_CORE_KEYS if k in src})
            out_sources.append(combined)
        else:
            out_sources.append(src)
            changes.append(f"added   {src.get('position')}: {src.get('path')}")
    for leftovers in pool.values():
        for old in leftovers:
            changes.append(f"removed {old.get('position')}: {old.get('path')} (no longer found)")
    merged['sources'] = out_sources
    kept = [k for k in existing if k not in ('sources',) and k in merged]
    if kept:
        changes.append("kept existing: " + ", ".join(sorted(kept)))
    return merged, changes


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
        config = read_config_json(target)
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
        job_num = detect_job_number(base_dir, file_paths)
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

        # Never rewrite from scratch over an existing config: keep positions offsets,
        # default_view and per-source extras for sources that still exist.
        if cfg_path.exists():
            try:
                config_data, changes = merge_config_with_existing(read_config_json(cfg_path), config_data)
                for line in changes:
                    logger.info("Config merge: %s", line)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("Existing config %s unreadable (%s); writing a fresh one.", cfg_path, exc)

        tmp_path = cfg_path.with_suffix(cfg_path.suffix + '.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2)
        os.replace(tmp_path, cfg_path)

        logger.info(f"Configuration saved automatically to: {cfg_path}")
        return cfg_path
    except Exception as e:
        logger.error(f"Failed to auto-save configuration from selected sources: {e}", exc_info=True)
        return None
