"""
interactive.py

Interactive visualization components for the Noise Survey Analysis.

This module provides functions for creating interactive visualization elements,
such as synchronized chart navigation, hover tools, and interactive features.
"""

import logging
from bokeh.models import (
    ColumnDataSource, CustomJS, Span, Label, HoverTool, 
    DatetimeTickFormatter, DatetimeTicker, RangeTool, Model
)
from bokeh.events import Tap, DocumentReady
import os

# Fix imports to use relative paths
try:
    # Try normal imports first (for when the module is properly installed)
    from noise_survey_analysis.core.config import CONFIG
    from noise_survey_analysis.js.loader import get_combined_js
except ImportError:
    # Use relative imports for Bokeh server mode
    from ..core.config import CONFIG
    from ..js.loader import get_combined_js

# Configure Logging
logger = logging.getLogger(__name__)

def create_range_selector(attached_chart, source, height=150, width=1600):
    """
    Create a range selector chart.
    
    Parameters:
    attached_chart (bokeh.plotting.figure): The chart to add the range selector to
    source (bokeh.models.ColumnDataSource): The data source for the chart
    height (int): Height of the range selector in pixels
    width (int): Width of the range selector in pixels
    
    Returns:
    bokeh.plotting.figure: The range selector chart.
    """
    from bokeh.plotting import figure
    
    df = source.to_df()
    metrics = [col for col in df.columns if col not in ['Datetime', 'index']]
    
    # Create the range selector figure
    select = figure(
        title="Drag to select a time range",
        height=height,
        width=width,
        x_axis_type="datetime",
        y_axis_type=None,
        tools="",
        toolbar_location=None,
        background_fill_color="#f5f5f5",
        sizing_mode="stretch_width"
    )
    
    # Add lines for metrics in a more subtle style
    for i, metric in enumerate(metrics[:3]):  # Limit to 3 metrics for cleaner visualization
        select.line('Datetime', metric, source=source, line_width=1, 
                 color=CONFIG["visualization"]["line_colors"].get(metric, f"#{''.join(['%02x' % ((i * 50 + j * 50) % 256) for j in range(3)])}"))
    
    # Add the range tool
    range_tool = RangeTool(x_range=attached_chart.x_range)
    range_tool.overlay.fill_color = "navy"
    range_tool.overlay.fill_alpha = 0.2
    
    # Format date axis
    select.xaxis.formatter = DatetimeTickFormatter(
        hours="%H:%M", days="%H:%M\n%A %d/%m/%y", months="%H:%M\n%A %d/%m/%y", years="%H:%M\n%A %d/%m/%y"
    )
    select.xaxis.ticker = DatetimeTicker(desired_num_ticks=24)
    
    select.add_tools(range_tool)
    select.grid.grid_line_color = None
    
    return select

def link_x_ranges(charts):
    """
    Link the x ranges of multiple charts.
    
    Parameters:
    charts (list): List of Bokeh figures to link
    """
    # Skip if there's only one chart
    if len(charts) <= 1:
        return
    
    # Get the x_range from the first chart
    master_range = charts[0].x_range
    
    # Link all other charts to this range
    for chart in charts[1:]:
        chart.x_range = master_range

# NEW function for Hover Interaction
def add_hover_interaction(charts, sources=None, bar_source=None, bar_x_range=None,
                          hover_info_div=None, selected_param_holder=None,
                          all_positions_spectral_data=None):
    """
    Adds vertical hover line and related callbacks to charts.

    Parameters:
    charts (list): List of Bokeh figures to add interactions to.
    sources (dict, optional): Dictionary of ColumnDataSource objects for charts.
    bar_source (ColumnDataSource): Frequency bar chart data source.
    bar_x_range (FactorRange): X-range for the frequency bar chart.
    hover_info_div (Div): Div for displaying hover information (e.g., spectral data).
    selected_param_holder (ColumnDataSource): Holder for the selected spectral parameter.
    all_positions_spectral_data (dict): Dict of spectral sources {position: source}.
    """
    logger.debug("Adding hover interaction...")

    valid_charts = [c for c in charts if c is not None]
    if not valid_charts:
        logger.warning("No valid charts provided for hover interaction.")
        return

    # Create hover lines (one for each chart)
    hover_lines = [Span(location=0, dimension='height', line_color='grey',
                        line_width=1, line_dash='dashed', name=f"hover_line_{i}")
                   for i, _ in enumerate(valid_charts)]

    # Add hover lines as layout to each chart
    for chart, h_line in zip(valid_charts, hover_lines):
        chart.add_layout(h_line)

    # --- JS Hover Callback ---
    hover_callback = CustomJS(
        args={
            'hoverLinesModels': hover_lines,
        },
        code="""
            if (typeof window.NoiseSurveyApp?.interactions?.handleHover === 'function') {
                window.NoiseSurveyApp.interactions.handleHover(hoverLinesModels, cb_data);
            } else {
                console.error('NoiseSurveyApp.interactions.handleHover not defined!');
            }
        """
    )

    # --- Hover Tool Setup ---
    hover_tool = HoverTool(
        tooltips=None,  # We use the CustomJS callback for behavior
        mode='vline',   # Trigger across the vertical line
        callback=hover_callback,
        description="Vertical Line on Hover",
        name="hover_vertical_line" # Give the tool a name
    )

    # Add the hover tool to each chart
    for chart in valid_charts:
        # Skip frequency bar chart and spectrograms
        if chart.name == 'frequency_bar' or '_spectral' in chart.name:
            continue
            
        # Check if a similar tool already exists to avoid duplicates if run multiple times
        existing_tool = next((t for t in chart.tools 
                             if isinstance(t, HoverTool) and t.name == "hover_vertical_line"), None)
        if not existing_tool:
            chart.add_tools(hover_tool)
        else:
            logger.warning(f"Hover tool already exists on chart: {chart.name}. Skipping add.")

    logger.debug(f"Hover interaction added to {len(valid_charts)} charts.")


# NEW function for Tap Interaction
def add_tap_interaction(charts, sources=None, bar_source=None, bar_x_range=None,
                        hover_info_div=None, # Pass hover_info_div in case tap needs to update it too
                        selected_param_holder=None, all_positions_spectral_data=None):
    """
    Adds click/tap interaction (vertical line, label) to charts.

    Parameters:
    charts (list): List of Bokeh figures to add interactions to.
    sources (dict, optional): Dictionary of ColumnDataSource objects for charts.
    bar_source (ColumnDataSource): Frequency bar chart data source.
    bar_x_range (FactorRange): X-range for the frequency bar chart.
    hover_info_div (Div): Div for displaying hover information.
    selected_param_holder (ColumnDataSource): Holder for the selected spectral parameter.
    all_positions_spectral_data (dict): Dict of spectral sources {position: source}.

    Returns:
    tuple(list, list): A tuple containing:
                       - click_lines (list): List of Span models for click lines.
                       - labels (list): List of Label models associated with click lines.
    """
    logger.debug("Adding tap/click interaction...")

    valid_charts = [c for c in charts if c is not None]
    if not valid_charts:
        logger.warning("No valid charts provided for tap interaction.")
        return [], []

    # Create click lines (one for each chart)
    click_lines = [Span(location=0, dimension='height', line_color='red',
                         line_width=1, name=f"click_line_{i}")
                   for i, _ in enumerate(valid_charts)]

    # Create labels (one for each chart)
    labels = [Label(x=0, y=0, text="", text_font_size='10pt', background_fill_color="white", 
                    background_fill_alpha=0.6, text_baseline="middle", visible=False, name=f"click_label_{i}")
                for i, _ in enumerate(valid_charts)]

    # Add click lines and labels as layouts to each chart
    for chart, c_line, label in zip(valid_charts, click_lines, labels):
        chart.add_layout(c_line)
        chart.add_layout(label)

    # --- JS Tap Callback ---
    tap_callback = CustomJS(
        args={
            # No need to pass all models if handleTap uses app state
            # Focus on just passing what's needed for this specific callback
        },
        code="""
            if (typeof window.NoiseSurveyApp?.interactions?.handleTap === 'function') {
                window.NoiseSurveyApp.interactions.handleTap(cb_obj);
            } else {
                console.error('NoiseSurveyApp.interactions.handleTap not defined!');
            }
        """
    )

    # --- Add tap event handler to each chart ---
    for chart in valid_charts:
        chart.js_on_event('tap', tap_callback)

    logger.debug(f"Tap interaction added to {len(valid_charts)} charts.")
    return click_lines, labels


def initialize_global_js(doc, charts, sources, clickLines, labels, playback_source=None, play_button=None, 
                        pause_button=None, bar_source=None, bar_x_range=None, bar_chart=None, hover_info_div=None, 
                        param_select=None, selected_param_holder=None, spectral_param_charts=None, 
                        all_positions_spectral_data=None):
    """
    Initialize JavaScript environment by loading the unified app.js file 
    and calling NoiseSurveyApp.initialize with all models.
    
    Parameters:
    doc (bokeh.document.Document): The Bokeh document to attach the JS to
    charts (list): List of chart figures
    sources (dict): Dictionary of data sources
    clickLines (list): List of click line models
    labels (list): List of label models
    playback_source (ColumnDataSource, optional): Source for audio playback time
    play_button (Button, optional): Play button model
    pause_button (Button, optional): Pause button model
    bar_source (ColumnDataSource, optional): Frequency bar chart data source
    bar_x_range (Range, optional): X range for the frequency bar chart
    bar_chart (Figure, optional): Frequency bar chart figure
    hover_info_div (Div, optional): Div for displaying hover information
    param_select (Select, optional): Dropdown for spectral parameter selection
    selected_param_holder (Div, optional): Div holding the selected parameter
    spectral_param_charts (dict, optional): Structure containing spectral parameter data by position
    all_positions_spectral_data (dict, optional): Pre-calculated spectral data by position and parameter
    """
    logger.debug("Initializing global JavaScript...")
    combined_js = get_combined_js()

    # --- Single CustomJS Callback to Initialize App ---
    callback_code = """
    // Wait for document ready for JS initialization to ensure all elements are in the DOM
    document.addEventListener('DOMContentLoaded', function() {
        console.log('DOM content loaded - initializing App...');
        
        if (typeof window.NoiseSurveyApp !== 'undefined') {
            try {
                // Create models object with all our models
                const models = {
                    charts: cb_obj.charts,
                    sources: cb_obj.sources, 
                    click_lines: cb_obj.clickLines,
                    labels: cb_obj.labels,
                    playback_source: cb_obj.playback_source,
                    play_button: cb_obj.play_button,
                    pause_button: cb_obj.pause_button,
                    bar_source: cb_obj.bar_source,
                    bar_x_range: cb_obj.bar_x_range,
                    bar_chart: cb_obj.bar_chart,
                    hover_info_div: cb_obj.hover_info_div,
                    param_select: cb_obj.param_select,
                    param_holder: cb_obj.selected_param_holder,
                    spectral_param_charts: cb_obj.spectral_param_charts,
                    all_positions_spectral_data: cb_obj.all_positions_spectral_data
                };
                
                // Initialize app with models
                const success = window.NoiseSurveyApp.init(models, {
                    enableKeyboardNavigation: true
                });
                
                if (success) {
                    console.log('NoiseSurveyApp initialized successfully');
                } else {
                    console.error('NoiseSurveyApp initialization returned failure');
                }
            } catch (error) {
                console.error('Error initializing NoiseSurveyApp:', error);
            }
        } else {
            console.error('NoiseSurveyApp not found. Make sure app.js is loaded.');
        }
    });
    """

    args = {
        'charts': charts,
        'sources': sources,
        'clickLines': clickLines,
        'labels': labels,
        'playback_source': playback_source,
        'play_button': play_button,
        'pause_button': pause_button,
        'bar_source': bar_source,
        'bar_x_range': bar_x_range,
        'bar_chart': bar_chart,
        'hover_info_div': hover_info_div,
        'param_select': param_select,
        'selected_param_holder': selected_param_holder,
        'spectral_param_charts': spectral_param_charts,
        'all_positions_spectral_data': all_positions_spectral_data
    }

    ready_callback = CustomJS(args=args, code=combined_js + "\n" + callback_code)
    doc.on_event(DocumentReady, ready_callback)
    logger.info("JavaScript initialization attached to DocumentReady event.")


