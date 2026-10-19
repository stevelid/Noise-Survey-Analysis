"""Server-side full-resolution export; called from a worker, never the Bokeh loop."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def export_workspace_request(payload: dict[str, Any]) -> dict[str, Any]:
    from noise_survey_analysis.export.annotations import export_annotations

    if not isinstance(payload, dict) or not isinstance(payload.get("workspace"), dict):
        raise ValueError("Full-resolution export requires a workspace snapshot")
    from noise_survey_analysis.control.validation import validate_command_payload

    options = validate_command_payload("export_annotations", payload)
    workspace = payload["workspace"]
    output = options.get("output_path")
    if not output:
        sources = workspace.get("sourceConfigs") or []
        first_source = sources[0] if sources else {}
        paths = first_source.get("file_paths") or [first_source.get("file_path") or first_source.get("path")]
        first_path = Path(paths[0]).resolve() if paths and paths[0] else Path.cwd()
        folder = first_path if first_path.is_dir() else first_path.parent
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        output = folder / f"annotations-{stamp}.full-resolution.csv"
    path = export_annotations(workspace, output_path=output,
                              include_all_resolutions=options["include_all_resolutions"],
                              background_window_s=options["background_window_s"], min_context_s=options["min_context_s"])
    return {"success": True, "output_path": str(path),
            "message": f"Full-resolution annotations exported: {path}"}
