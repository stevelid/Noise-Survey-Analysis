"""Template embedding uses the same actual Document contract in both modes."""
from html.parser import HTMLParser

from bokeh.document import Document
from bokeh.embed import file_html
from bokeh.models import ColumnDataSource, Div
from bokeh.resources import INLINE

from noise_survey_analysis.ui.html_shell import attach_html_shell


class ElementInventory(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.elements: list[tuple[str, dict[str, str | None]]] = []

    def handle_starttag(self, tag: str, attributes) -> None:
        self.elements.append((tag, dict(attributes)))


def test_named_ui_roots_render_in_shared_grid_and_keep_auxiliary_anchors():
    document = Document()
    names = [
        "controls_component_layout", "RangeSelector_component", "charts_stack_layout",
        "side_panel_container", "frequency_bar_layout", "comparison_frequency_layout",
        "summary_table_div", "js_init_trigger",
    ]
    roots = [Div(name=name, text=name) for name in names]
    attach_html_shell(document, roots)
    bridge = ColumnDataSource(data={"status": [""]}, name="server_bridge")
    document.add_root(bridge)

    html = file_html(
        document, INLINE, template=document.template,
        template_variables=document.template_variables,
    )
    inventory = ElementInventory()
    inventory.feed(html)
    assert any(tag == "main" and attributes.get("class") == "nsa-page-shell"
               for tag, attributes in inventory.elements)
    root_ids = [attributes["data-root-id"] for _, attributes in inventory.elements
                if "data-root-id" in attributes]
    assert set(root_ids) == {root.id for root in [*roots, bridge]}
    assert len(root_ids) == len(set(root_ids))
    assert document.get_model_by_name("side_panel_container") is roots[3]
