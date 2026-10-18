"""Frequency components extracted without changing Bokeh wiring."""

import numpy as np
from typing import (
    Any,
    Dict,
    List,
    Optional,
)
from noise_survey_analysis.core.config import CHART_SETTINGS
from bokeh.palettes import Category10
from bokeh.models import (
    ColumnDataSource,
    Div,
    FactorRange,
    HoverTool,
    LabelSet,
    NumeralTickFormatter,
    Range1d,
)
from bokeh.layouts import column
from bokeh.plotting import figure

from .shared import logger


class FrequencyBarComponent:
    """
    A self-contained component for displaying frequency levels as a bar chart
    for a specific time slice, typically updated via JavaScript interactions
    from other components like a spectrogram. Includes a table below the chart
    to allow for easy data copying.
    """
    def __init__(self, chart_settings: Optional[Dict[str, Any]] = None):
        """
        Initializes the FrequencyBarComponent.

        Args:
            chart_settings (Optional[Dict[str, Any]]): A dictionary of settings
                to override the default appearance and behavior of the chart.
        """
        self.settings = CHART_SETTINGS
        
        # Initial empty data structure. JavaScript will populate this.
        # 'frequency_labels' should be strings (e.g., "63 Hz", "1 kHz")
        # 'levels' should be numeric dB values.
        initial_data = {
            'frequency_labels': ['31.5 Hz', '40 Hz', '50 Hz', '63 Hz', '80 Hz', '100 Hz', '125 Hz', '160 Hz', '200 Hz', 
            '250 Hz', '315 Hz', '400 Hz', '500 Hz', '630 Hz', '800 Hz', '1000 Hz', '1250 Hz', '1600 Hz', '2000 Hz'], # More complete example initial factors
            'levels': [0] * 19 # Match the number of labels
        } 
        
        self.source: ColumnDataSource = ColumnDataSource(data=initial_data, name="frequency_bar_source")
        # The FactorRange is crucial for categorical x-axis. It must be initialized with
        # the factors that will appear on the x-axis. JS will update source.data,
        # and if the factors change, x_range.factors also needs updating.
        self.x_range: FactorRange = FactorRange(factors=initial_data['frequency_labels'])
        
        # Add a Div component to hold the HTML table for copying data
        self.table_div = Div(
            name="frequency_table_div",
            width=self.settings['frequency_bar_width']
        )
        
        self.figure: figure = self._create_figure()
        
        # Initialize the table with empty data
        self._update_table(initial_data['levels'], initial_data['frequency_labels'])
        
        logger.info("FrequencyBarComponent initialized.")

    def _create_figure(self) -> figure:
        """Creates and configures the Bokeh figure for the bar chart."""
        
        p = figure(
            title="Frequency Slice",
            height=self.settings['high_freq_height'],
            width=self.settings['frequency_bar_width'], # Initial width, sizing_mode handles final
            x_range=self.x_range, # Use the FactorRange instance
            x_axis_label='Frequency Band', # Suffix (Hz) implied by labels
            y_axis_label='Level (dB)',
            tools="pan,wheel_zoom,box_zoom,reset", # Standard tools
            name="frequency_bar_chart" # For identification
        )
        p.toolbar.autohide = True
        p.toolbar.logo = None

        # Add vertical bars
        p.vbar(
            x='frequency_labels',
            top='levels',
            width=0.8,
            source=self.source,
            fill_color="#6baed6",
            line_color="white",
            legend_label="Level" # Simple legend
        )

        # Add labels above bars to show the level
        labels = LabelSet(
            x='frequency_labels',
            y='levels',
            text='levels',
            level='glyph',
            x_offset=0,
            y_offset=5,
            source=self.source,
            text_align='center',
            text_font_size='8pt',
            text_color='black',
            text_baseline='bottom'
        )
        p.add_layout(labels)

        # Configure y-range
        if not self.settings['auto_y_range']:
            try:
                p.y_range = Range1d(*self.settings['y_range'])
            except Exception as e:
                 logger.warning(f"Invalid y_range configuration for Frequency Bar: {self.settings['y_range']}. Using auto-range. Error: {e}")
        
        p.yaxis.formatter = NumeralTickFormatter(format="0.0") # Format y-axis ticks

        # Add hover tool
        hover = HoverTool(tooltips=[
            ("Frequency", "@frequency_labels"), # @column_name refers to ColumnDataSource columns
            ("Level", "@levels{0.1f} dB")     # Format level to one decimal place
        ])
        p.add_tools(hover)

        # Styling
        p.xaxis.major_label_orientation = 0.8
        p.xaxis.major_label_text_font_size = "8pt" # Smaller for potentially many labels
        p.grid.grid_line_alpha = 0.3
        p.xaxis.axis_label_text_font_size = "10pt"
        p.yaxis.axis_label_text_font_size = "10pt"
        
        # Hide the default legend if only one series, or customize
        p.legend.visible = False 
        # If you had multiple vbar calls for different parameters, you might enable legend:
        # p.legend.location = "top_right"
        # p.legend.click_policy = "hide"

        return p

    def layout(self):
        """
        Returns the Bokeh layout object for this component, including both the chart and table div.
        """
        return column(
            self.figure,
            self.table_div
        )

    def _update_table(self, levels: List[float], labels: List[str]):
        """
        Updates the HTML table with frequency data for copying.
        
        Args:
            levels (List[float]): List of level values to display in the table.
            labels (List[str]): List of frequency band labels to display in the table.
        """
        if not labels or not levels:
            self.table_div.text = "<p>No frequency data available</p>"
            return
        
        table_html = """
        <style>
            .freq-html-table { border-collapse: collapse; width: 100%; font-size: 0.9em; table-layout: fixed; }
            .freq-html-table th, .freq-html-table td { border: 1px solid #e2e8f0; padding: 6px; text-align: center; white-space: nowrap; }
            .freq-html-table th { background-color: #f2f2f2; font-weight: bold; }
        </style>
        <table class="freq-html-table"><tr>"""
        
        # Add header row with frequency labels
        for label in labels:
            table_html += f"<th title=\"{label}\">{label}</th>"
        table_html += "</tr><tr>"
        
        # Add data row with level values
        for level in levels:
            level_num = float(level) if level is not None else float('nan')
            level_text = 'N/A' if np.isnan(level_num) else f"{level_num:.1f}"
            table_html += f"<td>{level_text}</td>"
        table_html += "</tr></table>"
        
        self.table_div.text = table_html
        logger.debug("Frequency table HTML updated.")

    def update_data(self, frequency_labels: List[str], levels: List[float]):
        """
        Public method to update the data in the bar chart and the associated table.
        This would typically be called by JavaScript via a CustomJS callback
        or by Python code if interactions are Python-driven.

        Args:
            frequency_labels (List[str]): New list of frequency band labels.
            levels (List[float]): Corresponding list of level values.
        """
        if len(frequency_labels) != len(levels):
            logger.error("Frequency labels and levels must have the same length for update.")
            return

        self.source.data = {'frequency_labels': frequency_labels, 'levels': levels}
        self.x_range.factors = frequency_labels # CRITICAL: Update factors for categorical axis
        
        # Update the table with the new data
        self._update_table(levels, frequency_labels)
        
        logger.debug(f"FrequencyBarComponent data updated. Factors: {frequency_labels[:5]}..., Levels: {levels[:5]}...")


class ComparisonFrequencyBarComponent:
    """Multi-series frequency comparison chart."""

    def __init__(self, width: Optional[int] = None):
        configured_width = CHART_SETTINGS.get('frequency_bar_width', None)
        chart_width = width if width is not None else configured_width
        initial_data = {
            'x': [],
            'level': [],
            'position': [],
            'color': []
        }
        self.source = ColumnDataSource(data=initial_data, name="comparison_frequency_source")
        self.x_range = FactorRange(factors=[])
        self.palette = Category10[10]
        self.figure = self._create_figure(chart_width)
        self.table_div = Div(
            text=self._empty_table_html(),
            width=chart_width,
            name="comparison_frequency_table",
            styles={
                "border": "1px solid #cbd5e1",
                "padding": "12px",
                "background-color": "#f1f5f9",
                "margin-top": "8px"
            }
        )

        self.container = column(
            self.figure,
            self.table_div,
            name="comparison_frequency_layout"
        )
        self.container.visible = False

    def _empty_table_html(self) -> str:
        return """
            <table class="comparison-frequency-table" style="width:100%; border-collapse: collapse; font-size:12px;">
                <thead>
                    <tr>
                        <th style="border:1px solid #e2e8f0; padding:4px; background:#f1f5f9;">Position</th>
                        <th style="border:1px solid #e2e8f0; padding:4px; background:#f1f5f9;">Spectrum</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td colspan="2" style="border:1px solid #e2e8f0; padding:6px; text-align:center; font-style:italic; color:#64748b;">
                            Select a time slice to view averaged spectra.
                        </td>
                    </tr>
                </tbody>
            </table>
        """

    def _create_figure(self, chart_width: Optional[int]):
        figure_kwargs = dict(
            title="Comparison Spectrum",
            height=CHART_SETTINGS.get('high_freq_height', 300),
            width=chart_width,
            x_range=self.x_range,
            x_axis_label='Frequency Band',
            y_axis_label='Level (dB)',
            tools="pan,wheel_zoom,box_zoom,reset",
            name="comparison_frequency_chart"
        )

        if chart_width is not None:
            figure_kwargs["width"] = chart_width

        p = figure(**figure_kwargs)
        p.toolbar.autohide = True
        p.toolbar.logo = None

        p.vbar(
            x='x',
            top='level',
            width=0.8,
            source=self.source,
            fill_color='color',
            line_color='color',
            legend_field='position'
        )

        p.legend.location = "top_left"
        p.legend.click_policy = "hide"
        p.xaxis.major_label_orientation = 0.8
        p.xaxis.major_label_text_font_size = "8pt"
        p.yaxis.formatter = NumeralTickFormatter(format="0.0")

        hover = HoverTool(tooltips=[
            ("Position", "@position"),
            ("Frequency", "@x{safe}"),
            ("Level", "@level{0.1f} dB")
        ])
        p.add_tools(hover)

        return p

    def layout(self):
        return self.container
