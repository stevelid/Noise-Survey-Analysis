"""
Shared visual theme for the dashboard.

Bokeh 3 widgets render inside shadow DOM, so a single document-level stylesheet
cannot restyle widget internals. This module provides apply_theme(), which walks
a model tree and attaches the shared theme stylesheet to every UI element's
shadow root, plus a document-level stylesheet for the page background, fonts,
and the --nsa-* design tokens (CSS custom properties inherit across shadow
boundaries, so tokens defined on :root are visible inside every widget).

Usage: call apply_theme(root_layout) on any layout *before* doc.add_root().
Fresh stylesheet model instances are created per call because a Bokeh model
cannot belong to more than one Document (each server session is a Document).
"""

import logging
from pathlib import Path

from bokeh.models import GlobalInlineStyleSheet, InlineStyleSheet, UIElement

logger = logging.getLogger(__name__)

_WIDGET_CSS_PATH = Path(__file__).resolve().parents[1] / "static" / "css" / "theme.css"

# Document-level styles: page chrome and design tokens. Tokens inherit into
# every shadow root, so theme.css can reference var(--nsa-*) values.
GLOBAL_CSS = """
:root {
  --nsa-bg: #f8fafc;
  --nsa-surface: #ffffff;
  --nsa-border: #e2e8f0;
  --nsa-border-strong: #cbd5e1;
  --nsa-text: #0f172a;
  --nsa-text-secondary: #334155;
  --nsa-text-muted: #64748b;
  --nsa-accent: #2563eb;
  --nsa-accent-strong: #1d4ed8;
  --nsa-accent-soft: #eff6ff;
  --nsa-radius: 6px;
  --nsa-font: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
}

body {
  background-color: var(--nsa-bg);
  color: var(--nsa-text);
  font-family: var(--nsa-font);
}
"""


def _load_widget_css() -> str:
    try:
        return _WIDGET_CSS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not load theme stylesheet %s: %s", _WIDGET_CSS_PATH, exc)
        return ""


def apply_theme(*models):
    """Attach the shared theme to every UI element referenced by the given models.

    Safe to call on any mix of layouts/widgets; non-UI models referenced by the
    tree (data sources, ranges, etc.) are skipped. Elements that already carry
    custom stylesheets keep them - the theme is appended, so existing rules win
    only where they are more specific.

    Returns the first model, so calls can be inlined: doc.add_root(apply_theme(layout)).
    """
    widget_css = _load_widget_css()
    widget_sheet = InlineStyleSheet(css=widget_css) if widget_css else None
    global_sheet = GlobalInlineStyleSheet(css=GLOBAL_CSS)

    # The global sheet is attached to every element; BokehJS installs a global
    # stylesheet's <style> node in the document head only once per model.
    themed_ids = set()
    for model in models:
        if model is None:
            continue
        for ref in model.references():
            if not isinstance(ref, UIElement) or ref.id in themed_ids:
                continue
            themed_ids.add(ref.id)
            sheets = list(ref.stylesheets)
            sheets.append(global_sheet)
            if widget_sheet is not None:
                sheets.append(widget_sheet)
            ref.stylesheets = sheets

    logger.debug("Theme applied to %d UI elements.", len(themed_ids))
    return models[0] if models else None
