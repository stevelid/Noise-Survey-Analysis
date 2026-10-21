"""One HTML model for annotations; controls are rendered from the browser store."""
from pathlib import Path

from bokeh.models import Div, InlineStyleSheet

from .shared import SIDE_PANEL_WIDTH


class HtmlSidePanelComponent:
    """Keep CSS in this Div's shadow root for server and standalone documents."""

    def __init__(self) -> None:
        css_path = Path(__file__).resolve().parents[2] / "static/css/annotation-panel.css"
        self.div = Div(
            text='<div class="nsa-annotation-panel">Loading annotations…</div>',
            name="html_side_panel",
            sizing_mode="stretch_width",
            margin=0,
            css_classes=["nsa-html-panel-host"],
            styles={"overflow": "visible", "min-width": "0"},
            stylesheets=[InlineStyleSheet(css=css_path.read_text(encoding="utf-8"))],
        )

    def layout(self) -> Div:
        return self.div
