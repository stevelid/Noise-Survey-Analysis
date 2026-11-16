import hashlib
import os
import re
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from bokeh.document import Document
from bokeh.embed import file_html
from bokeh.resources import CDN, INLINE

from noise_survey_analysis.core.app_setup import load_config_and_prepare_sources, load_config_extras
from noise_survey_analysis.core.data_manager import DataManager
from noise_survey_analysis.core.audio_processor import AudioDataProcessor
from noise_survey_analysis.core.config import CHART_SETTINGS
from noise_survey_analysis.core.workspace_autosave import read_workspace_autosave
from noise_survey_analysis.visualization import static_payload
from noise_survey_analysis.visualization.dashBuilder import DashBuilder

logger = logging.getLogger(__name__)


def _with_export_id(html: str) -> str:
    """Bake a content hash into the page. The browser keys its saved edits on it, so edits made
    on an older export cannot shadow a newer one."""
    export_id = hashlib.sha1(html.encode('utf-8')).hexdigest()[:12]
    tag = f'<meta name="nsa-export-id" content="{export_id}">'
    stamped, count = re.subn(r'(<head[^>]*>)', lambda m: m.group(1) + '\n    ' + tag, html, count=1)
    return stamped if count else html


def _app_state_from(workspace: Any) -> Optional[Dict[str, Any]]:
    """Accept a full workspace payload (``{'appState': ...}``) or a bare app state."""
    if not isinstance(workspace, dict):
        return None
    inner = workspace.get('appState')
    if isinstance(inner, dict):
        return inner
    return workspace if ('regions' in workspace or 'view' in workspace or 'markers' in workspace) else None


def _load_state_file(path: str) -> Optional[Dict[str, Any]]:
    import json
    try:
        with open(path, 'r', encoding='utf-8-sig') as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else None
    except (OSError, ValueError) as exc:
        logger.error("Could not read workspace file %s: %s", path, exc)
        return None


def generate_static_html(
    config_path: str,
    resources: str = "INLINE",
    workspace: Optional[Dict[str, Any]] = None,
    position_offsets: Optional[Dict[str, Dict[str, float]]] = None,
    output_path: Optional[str] = None,
    state_path: Optional[str] = None,
    detail: str = "auto",
    audio_clips: bool = False,
) -> Optional[Path]:
    """
    Builds the dashboard layout from a config file and saves it as a standalone HTML file.

    Args:
        config_path: Path to the saved JSON config (as produced by the selector or provided manually)
        resources: 'INLINE' (default) or 'CDN' to control Bokeh resource embedding
        workspace: Workspace payload (or bare app state) to bake in: regions, markers, layout, offsets.
            Default: ``state_path``'s file, else the config's autosave beside it, else nothing.
        position_offsets: ``{position: {chart_offset_seconds, audio_offset_seconds}}``. Default: the
            config's ``positions`` block, overridden by chart offsets held in the workspace.
        output_path: HTML file or folder to write. Default: the config's folder.
        detail: 'auto' | 'full' | 'lines' | 'regions' | 'overview' -- how much 1 s log data to embed.
        audio_clips: also write <=60 s region clips as WAV beside the HTML (20 MB cap).

    Returns:
        pathlib.Path to the written HTML on success, or None on failure.
    """
    try:
        started = time.perf_counter()
        logger.info(f"--- Generating static HTML from config: {config_path} ---")

        # Load config and prepare sources once.
        loaded_filename, source_configs, job_number = load_config_and_prepare_sources(config_path=config_path)
        if source_configs is None:
            logger.error("Could not load source configurations. Aborting static generation.")
            return None

        # Determine output filename from config path or job_number
        if job_number:
            output_filename = f"{job_number}_survey_dashboard.html"
        else:
            # Try to extract from config filename
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

        if output_path:
            candidate = Path(output_path)
            if candidate.suffix.lower() in ('.html', '.htm'):
                output_full_path = candidate
            else:
                output_full_path = candidate / output_filename
        else:
            # The output directory is the same as the config file's directory.
            output_full_path = Path(config_path).parent / output_filename
        output_full_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Output will be saved to: {output_full_path}")

        # Annotations, layout and offsets to bake in.
        if workspace is None and state_path:
            workspace = _load_state_file(state_path)
        if workspace is None:
            workspace = read_workspace_autosave(config_path)
            if workspace is not None:
                logger.info("Static export: using the config's autosaved workspace.")
        app_state = _app_state_from(workspace)

        extras = load_config_extras(str(config_path)) if os.path.exists(str(config_path)) else {'positions': {}}
        offsets = {k: dict(v) for k, v in (extras.get('positions') or {}).items()}
        offsets.update({k: dict(v) for k, v in (position_offsets or {}).items()})
        chart_offsets_ms: Dict[str, float] = {k: float(v.get('chart_offset_seconds', 0.0)) * 1000.0
                                              for k, v in offsets.items()}
        state_offsets = ((app_state or {}).get('view') or {}).get('positionChartOffsets')
        if isinstance(state_offsets, dict):
            for position, value in state_offsets.items():
                try:
                    chart_offsets_ms[position] = float(value)
                    offsets.setdefault(position, {})['chart_offset_seconds'] = float(value) / 1000.0
                except (TypeError, ValueError):
                    continue

        # 1. Load Data
        app_data = DataManager(source_configurations=source_configs)
        AudioDataProcessor().anchor_audio_files(app_data)

        # 1b. Decide how much 1 s log detail the page carries (needs the logs loaded).
        for position_name in list(app_data.positions()):
            position_data = app_data[position_name]
            if getattr(position_data, 'log_file_paths', None) and not getattr(position_data, '_log_data_loaded', False):
                try:
                    position_data.load_log_data_lazy(app_data.parser_factory, app_data.use_cache)
                except Exception as exc:
                    logger.error("Failed to load log data for %s: %s", position_name, exc, exc_info=True)
        plan = static_payload.plan_static_detail(detail, app_data, static_payload.STATIC_AUTO_MAX_MB)
        mode, step_s, explanation = plan['mode'], plan['step_s'], plan['explanation']
        logger.info("Static export: %s", explanation)
        print(f"[static] threshold {static_payload.STATIC_AUTO_MAX_MB:.0f} MB -> {explanation}")
        if mode != 'full':
            windows = static_payload.collect_detail_windows(app_state)
            reduced = static_payload.apply_static_detail(app_data, mode, windows, chart_offsets_ms, step_s=step_s)
            logger.info("Static export detail '%s' (step %s): %d window(s); rows kept %s", mode, step_s, len(windows), reduced)

        # 2. Instantiate builder (no audio for static version)
        dash_builder = DashBuilder(audio_control_source=None, audio_status_source=None)
        dash_builder.static_log_step_s = step_s

        # 2b. Optional audio clips, referenced from the baked-in regions by relative URL.
        if audio_clips and app_state:
            try:
                from noise_survey_analysis.export.audio_clips import write_region_clips
                clips_dir = output_full_path.with_name(output_full_path.stem + '_clips')
                audio_offsets_ms = {k: float(v.get('audio_offset_seconds', 0.0) or 0.0) * 1000.0
                                    for k, v in offsets.items()}
                clips = write_region_clips(app_data, app_state, clips_dir, chart_offsets_ms, audio_offsets_ms)
                by_id = (app_state.get('regions') or {}).get('byId') or {}
                for region_id, per_pos in clips.items():
                    if region_id in by_id:
                        by_id[region_id]['audioClips'] = per_pos
            except Exception as exc:
                logger.error("Audio clip export failed: %s", exc, exc_info=True)

        # 3. Create and build document
        static_doc = Document()
        dash_builder.build_layout(
            static_doc,
            app_data,
            CHART_SETTINGS,
            source_configs=source_configs,
            saved_workspace_state=app_state,
            job_number=job_number,
            server_mode=False,
            position_offsets=offsets,
        )

        if step_s:
            for component in dash_builder.components.values():
                try:
                    figure = component['spectrogram'].figure
                    figure.title.text = f"{figure.title.text} (Log {step_s:g} s)"
                except Exception:
                    pass

        # 4. Save the document using file_html (works under bokeh serve and CLI)
        try:
            res = CDN if str(resources).upper() == "CDN" else INLINE
            html = file_html(static_doc, res, title="Noise Survey Dashboard")
            html = _with_export_id(html)
            with open(output_full_path, "w", encoding="utf-8") as f:
                f.write(html)
            size_mb = os.path.getsize(output_full_path) / 1048576
            elapsed = time.perf_counter() - started
            logger.info(f"--- Static HTML file saved successfully to {output_full_path} ({size_mb:.1f} MB, {elapsed:.0f} s) ---")
            print(f"[static] wrote {output_full_path} ({size_mb:.1f} MB, detail '{mode}', {elapsed:.0f} s)")
            if size_mb > static_payload.STATIC_AUTO_MAX_MB:
                logger.warning("Static HTML is %.0f MB (over %.0f MB); consider --static-detail regions.",
                               size_mb, static_payload.STATIC_AUTO_MAX_MB)
            return output_full_path
        except Exception as e:
            logger.error(f"Failed to save static HTML file: {e}", exc_info=True)
            return None

    except Exception as e:
        logger.error(f"Static export failed: {e}", exc_info=True)
        return None
