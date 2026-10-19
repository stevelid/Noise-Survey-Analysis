"""Page-level HTML layout prototype; individual charts remain Bokeh components.

Bokeh supplies ``roots``, ``embed`` and its base template to both server pages
and file_html. The standalone callers must pass Document.template explicitly.
"""

from bokeh.document import Document
from bokeh.models import LayoutDOM

from noise_survey_analysis.ui.component_parts.shared import SIDE_PANEL_WIDTH


HTML_SHELL_TEMPLATE = """
{% block postamble %}
{{ super() }}
<style>
  .nsa-page-shell {
    display: grid;
    grid-template-columns: minmax(300px, 1fr) {{ nsa_sidebar_width }}px;
    grid-template-areas:
      "controls controls"
      "navigator navigator"
      "charts annotations"
      "frequency frequency"
      "comparison comparison"
      "summary summary";
    gap: 12px;
    padding: 12px;
    min-width: 0;
    overflow: visible;
    align-items: start;
  }
  .nsa-page-shell > * { min-width: 0; overflow: visible; }
  .nsa-shell-controls { grid-area: controls; position: sticky; top: 0; z-index: 100; }
  .nsa-shell-navigator { grid-area: navigator; }
  .nsa-shell-charts { grid-area: charts; }
  /* Stretch the aside through the chart row so its Bokeh child can stick. */
  .nsa-shell-annotations { grid-area: annotations; align-self: stretch; }
  .nsa-shell-frequency { grid-area: frequency; }
  .nsa-shell-comparison { grid-area: comparison; }
  .nsa-shell-summary { grid-area: summary; }
</style>
{% endblock %}

{% block contents %}
<main class="nsa-page-shell" aria-label="Noise survey analysis">
  <header class="nsa-shell-controls">{{ embed(roots.controls_component_layout) }}</header>
  <section class="nsa-shell-navigator" aria-label="Survey navigator">
    {{ embed(roots.RangeSelector_component) }}
  </section>
  <section class="nsa-shell-charts" aria-label="Survey charts">
    {{ embed(roots.charts_stack_layout) }}
  </section>
  <aside class="nsa-shell-annotations" aria-label="Annotations">
    {{ embed(roots.side_panel_container) }}
  </aside>
  <section class="nsa-shell-frequency" aria-label="Frequency analysis">
    {{ embed(roots.frequency_bar_layout) }}
  </section>
  <section class="nsa-shell-comparison" aria-label="Comparison spectra">
    {{ embed(roots.comparison_frequency_layout) }}
  </section>
  <section class="nsa-shell-summary" aria-label="Level summary">
    {{ embed(roots.summary_table_div) }}
  </section>
</main>
{{ embed(roots.js_init_trigger) }}
<div hidden aria-hidden="true">
  {# Keep Bokeh's embedding anchors for later non-visual server bridge roots. #}
  {% for root in roots if root.name not in nsa_shell_ui_roots %}
    {{ embed(root) }}
  {% endfor %}
</div>
{% endblock %}
"""


def attach_html_shell(document: Document, roots: list[LayoutDOM]) -> None:
    """Register named UI roots without changing their model or callback names."""
    document.template = HTML_SHELL_TEMPLATE
    document.template_variables["nsa_shell_ui_roots"] = [root.name for root in roots]
    document.template_variables["nsa_sidebar_width"] = SIDE_PANEL_WIDTH + 32
    for root in roots:
        document.add_root(root)
