"""Summary components extracted without changing Bokeh wiring."""

from noise_survey_analysis.core.config import CHART_SETTINGS
from bokeh.models import Div
from typing import List

from .shared import logger


class SummaryTableComponent:
    """
    A component that displays a summary table of parameter values for all 
    positions at a specific tapped timestamp. The content is entirely 
    controlled by JavaScript.
    """
    def __init__(self, position_names: List[str], parameters: List[str], compact: bool = True):
        self.settings = CHART_SETTINGS
        self.position_names = position_names
        self.parameters = parameters
        self.compact = compact
        
    
        initial_html = self._create_initial_html()

        self.summary_div = Div(
            text = initial_html,
            name = "summary_table_div",
            width=self.settings.get('low_freq_width', 1200) # Match the width of the charts
        )

        logger.info(f"SummaryTableComponent initialized with {len(parameters)} parameters, compact={compact}.")

    def _create_initial_html(self) -> str:
        """Generates the initial HTML for the table with a placeholder message."""
        # Responsive styling based on compact mode
        font_size = "0.8em" if self.compact else "0.9em"
        padding = "4px" if self.compact else "8px"
        margin_bottom = "10px" if self.compact else "20px"
        
        style = f"""
        <style>
            .summary-html-table {{ border-collapse: collapse; width: 100%; font-size: {font_size}; table-layout: fixed; margin-top: 10px; margin-bottom: {margin_bottom};}}
            .summary-html-table th, .summary-html-table td {{ border: 1px solid #e2e8f0; padding: {padding}; text-align: center; }}
            .summary-html-table th {{ background-color: #f2f2f2; font-weight: bold; }}
            .summary-html-table .position-header {{ text-align: left; font-weight: bold; }}
            .summary-html-table .placeholder {{ color: #94a3b8; font-style: italic; }}
            .summary-html-table .timestamp-info {{ background-color: #f1f5f9; font-size: 0.85em; color: #64748b; }}
        </style>
        """
        
        header_row = "".join(f"<th>{param}</th>" for param in self.parameters)
        
        placeholder_row = f"<tr><td class='placeholder' colspan='{len(self.parameters) + 1}'>Tap on a time series chart to populate this table.</td></tr>"

        table_html = f"""
        {style}
        <table class="summary-html-table">
            <thead>
                <tr>
                    <th class="position-header">Position</th>
                    {header_row}
                </tr>
            </thead>
            <tbody>
                {placeholder_row}
            </tbody>
        </table>
        """
        return table_html

    def layout(self):
        """Returns the Bokeh layout object for this component."""
        return self.summary_div
