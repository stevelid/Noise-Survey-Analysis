"""Comparison components extracted without changing Bokeh wiring."""

from bokeh.models import (
    Button,
    CheckboxGroup,
    CustomJS,
    Div,
)
from bokeh.layouts import Column, Row
from typing import List, Optional

from .shared import SIDE_PANEL_WIDTH


class ComparisonPanelComponent:
    """Container for comparison mode controls and placeholders."""

    def __init__(self, position_ids: Optional[List[str]] = None):
        self.position_ids: List[str] = list(position_ids or [])
        panel_width = SIDE_PANEL_WIDTH
        selector_width = max(panel_width - 20, 100)

        instructions_html = (
            "<div class='comparison-panel-instructions'>"
            "<h3>Comparison Mode</h3>"
            "<p>Select the positions you want to include. Drag on a chart to choose a time slice.</p>"
            "</div>"
        )
        self.instructions_div = Div(
            text=instructions_html,
            width=panel_width,
            name="comparison_panel_instructions",
            styles={"margin-bottom": "8px"}
        )

        self.slice_info_div = Div(
            text="<div class='comparison-slice-info'><em>No time slice selected.</em></div>",
            width=panel_width,
            name="comparison_slice_info_div",
            styles={
                "border": "1px solid #cbd5e1",
                "padding": "8px",
                "background-color": "#f1f5f9",
                "font-size": "12px",
                "margin-bottom": "8px"
            }
        )

        labels = [str(position_id) for position_id in self.position_ids]
        self.position_selector = CheckboxGroup(
            labels=labels,
            active=list(range(len(labels))),
            width=selector_width,
            name="comparison_position_selector"
        )
        self.position_selector.js_on_change(
            "active",
            CustomJS(
                args={"positionIds": self.position_ids},
                code="""
                    if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleComparisonPositionsChange) {
                        const selected = cb_obj.active
                            .map(index => positionIds[index])
                            .filter(id => id !== undefined && id !== null);
                        window.NoiseSurveyApp.eventHandlers.handleComparisonPositionsChange(selected);
                    } else {
                        console.error('NoiseSurveyApp.eventHandlers.handleComparisonPositionsChange not defined!');
                    }
                """
            )
        )

        metrics_table_html = """
            <style>
                .comparison-metrics-table { width: 100%; border-collapse: collapse; font-size: 12px; }
                .comparison-metrics-table th, .comparison-metrics-table td {
                    border: 1px solid #e2e8f0;
                    padding: 4px 6px;
                    text-align: center;
                }
                .comparison-metrics-table th {
                    background-color: #f1f5f9;
                    font-weight: 600;
                }
                .comparison-metrics-table__placeholder {
                    font-style: italic;
                    color: #64748b;
                }
            </style>
            <table class="comparison-metrics-table">
                <thead>
                    <tr>
                        <th>Position</th>
                        <th>Duration</th>
                        <th>LAeq</th>
                        <th>LAFmax</th>
                        <th>LA90</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td class="comparison-metrics-table__placeholder" colspan="5">Select a time slice to populate metrics.</td>
                    </tr>
                </tbody>
            </table>
        """
        self.metrics_table_div = Div(
            text=metrics_table_html,
            width=panel_width,
            height=220,
            name="comparison_metrics_div",
            styles={
                "border": "1px solid #cbd5e1",
                "padding": "12px",
                "background-color": "#f1f5f9",
                "overflow-y": "auto"
            }
        )

        self.make_regions_button = Button(
            label="Make Region(s)",
            button_type="primary",
            width=150,
            name="comparison_make_regions_button",
            disabled=True
        )
        self.make_regions_button.js_on_event(
            "button_click",
            CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleComparisonMakeRegions) {
                    window.NoiseSurveyApp.eventHandlers.handleComparisonMakeRegions();
                } else {
                    console.info('Comparison region creation will be implemented in a future update.');
                }
            """)
        )

        self.finish_button = Button(
            label="Finish Comparison",
            button_type="success",
            width=150,
            name="comparison_finish_button",
            disabled=True
        )
        self.finish_button.js_on_event(
            "button_click",
            CustomJS(code="""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.eventHandlers && window.NoiseSurveyApp.eventHandlers.handleFinishComparison) {
                    window.NoiseSurveyApp.eventHandlers.handleFinishComparison();
                } else {
                    console.error('NoiseSurveyApp.eventHandlers.handleFinishComparison not defined!');
                }
            """)
        )

        buttons_row = Row(
            self.make_regions_button,
            self.finish_button,
            name="comparison_panel_buttons",
            sizing_mode="scale_width"
        )

        self.container = Column(
            self.instructions_div,
            self.position_selector,
            self.slice_info_div,
            self.metrics_table_div,
            buttons_row,
            name="comparison_panel_layout",
            sizing_mode="stretch_width",
            width=panel_width,
        )
        self.container.visible = False

    def layout(self):
        return self.container
