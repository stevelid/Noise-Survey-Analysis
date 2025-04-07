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
from core.config import CONFIG
from noise_survey_analysis.js.loader import get_core_js, get_charts_js, get_frequency_js

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

def add_vertical_line_and_hover(charts, sources=None):
    """
    Add vertical line and hover functionality to charts.
    
    Parameters:
    charts (list): List of Bokeh figures to add vertical lines to
    sources (dict, optional): Dictionary of ColumnDataSource objects
    
    Returns:
    list: The updated charts
    """
    
    print("Adding click and hover lines")
    
    # Load charts JavaScript
    charts_js = get_charts_js()
    core_js = get_core_js()
    
    hover_lines = [Span(location=0, dimension='height', line_color='grey',
                       line_width=1, line_dash='dashed') for _ in charts]
    click_lines = [Span(location=0, dimension='height', line_color='red',
                       line_width=1, line_dash='solid', visible=True,
                       line_alpha=0.7, name="click_line") for _ in charts]
    
    # Create labels for each chart that will appear on click
    labels = []
    for i, chart in enumerate(charts):
        # Check if chart is a range selector by looking at its title
        if (hasattr(chart, 'title') and chart.title.text == "Drag to select a time range"):
            # Range selector has no visible label
            label = Label(
                x=0, y=0,
                x_units='data', y_units='data',
                text="",
                text_font_size="0pt",
                text_align="left",
                text_baseline="top",
                x_offset=0,
                y_offset=0,
                visible=True,
                background_fill_alpha=0,
                border_line_alpha=0
            )
        else:
            label = Label(
                x=0, y=0,  # Will be updated in the callback
                x_units='data', y_units='data',
                text="",
                text_font_size="10pt",
                text_align="left",
                text_baseline="top",
                x_offset=15,
                background_fill_color="white",
                background_fill_alpha=0.7,
                border_line_color="black",
                border_line_alpha=0.5,
                visible=False
            )
            chart.add_layout(label, 'center')
        
        labels.append(label)    

    # Add spans to charts AFTER creating them all
    for chart, hover_line, click_line in zip(charts, hover_lines, click_lines):
        chart.add_layout(hover_line)
        chart.add_layout(click_line)

    #---JS Callbacks---

    # Hover Callback (operates on hover_lines models directly)
    hover_callback = CustomJS(
        args={
            'hoverLines': hover_lines
        },
        code="""
            if (typeof window.handleHover === 'function') {
                window.handleHover(hoverLines, cb_data);
            } else if (typeof handleHover === 'function') {
                handleHover(hoverLines, cb_data);
                console.log('handleHover called');
            } else {
                console.error('handleHover not defined!');
            }
        """
    )

    # Click Callback (operates on click_lines and labels models directly)
    # Pass the Python lists directly. JS will receive them as arrays of BokehJS models.
    click_callback = CustomJS(
        args={
            'charts': charts,
            'clickLines': click_lines, # Pass the list of click_line models
            'labels': labels,         # Pass the list of label models
            'sources': sources
        },
        code="""
            console.log('Tap callback executing.'); // Basic log
            if (typeof window.handleTap === 'function') {
                // Pass the necessary args to the globally defined function
                window.handleTap(cb_obj, charts, clickLines, labels, sources);
            } else if (typeof handleTap === 'function') {
                handleTap(cb_obj, charts, clickLines, labels, sources);
                console.log('handleTap called');
            } else {
                console.error('handleTap not defined!');
            }
        """
    )

    #---Tool Setup---

    hover_tool = HoverTool(
        tooltips=None,
        mode='vline',
        callback=hover_callback,
        description="Vertical Line on Hover",
        name="Vertical Line on Hover"
    )

    # Add hover tool and register tap event
    for chart in charts:
        chart.add_tools(hover_tool)
        chart.js_on_event('tap', click_callback) # Use js_on_event for CustomJS

    return charts, click_lines, labels

def initialize_global_js(doc, charts, sources, clickLines, labels, playback_source, play_button, pause_button):
    """
    Combines all necessary JS files and initializes global references
    using a single CustomJS callback attached to DocumentReady.

    Parameters:
    doc (bokeh.document.Document): The Bokeh document.
    charts (list): List of Bokeh chart models.
    sources (dict): Dictionary of ColumnDataSource objects.
    clickLines (list): List of Span models for click lines.
    labels (list): List of Label models.
    playback_source (bokeh.models.ColumnDataSource): The playback data source.
    play_button (bokeh.models.Button): The play button model.
    pause_button (bokeh.models.Button): The pause button model.

    Returns:
    bokeh.document.Document: The document with the event handler attached.
    """
    logger.info("Registering unified JavaScript initialization on DocumentReady.")

    # 1. Load all required JS code
    core_js = get_core_js()
    charts_js = get_charts_js()
    frequency_js = get_frequency_js()
    #audio_js = get_audio_js() # Include if audio functions are needed globally

    # 2. Combine JS in the correct order (definitions first)
    # Ensure core_js comes first as it defines initializeReferences and other utils
    combined_js = (
        core_js + "\n\n// ---- CORE LOADED ----\n\n" +
        charts_js + "\n\n// ---- CHARTS LOADED ----\n\n" +
        frequency_js + "\n\n// ---- FREQUENCY LOADED ----\n\n"
    )

    # 3. Define the initialization call within the same script
    initialization_call_js = """
        console.log('DocumentReady event fired. All custom JS should be loaded.');
        // Ensure Bokeh models passed as args are accessible
        if (typeof charts !== 'undefined' && typeof sources !== 'undefined' &&
            typeof clickLines !== 'undefined' && typeof labels !== 'undefined')
        {
            // Now, attempt to call the initialization function
            if (typeof initializeReferences === 'function') {
                try {
                    initializeReferences(charts, sources, clickLines, labels, playback_source, play_button, pause_button);
                    console.log('SUCCESS: initializeReferences called.');
                    // Optionally enable keyboard nav here if it depends on init
                    if (typeof enableKeyboardNavigation === 'function') {
                       enableKeyboardNavigation(); // Call after init is confirmed
                       console.log('Keyboard navigation enabled.');
                    } else {
                       console.warn('enableKeyboardNavigation not found after init.');
                    }
                } catch (e) {
                    console.error('Error executing initializeReferences:', e);
                }
            } else {
                console.error('CRITICAL ERROR: initializeReferences function not found even after loading core.js!');
                // Log available window properties for debugging
                // console.log('Window keys:', Object.keys(window));
            }
        } else {
             console.error('CRITICAL ERROR: Bokeh models (charts, sources, etc.) not available in CustomJS args.');
        }
    """

    # 4. Create a SINGLE CustomJS callback
    init_callback = CustomJS(
        args={
            # Pass the actual Bokeh models needed by initializeReferences
            'charts': charts,
            'sources': sources,
            'clickLines': clickLines,
            'labels': labels,
            'playback_source': playback_source,
            'play_button': play_button,
            'pause_button': pause_button
        },
        # Execute the combined definitions AND the initialization call
        code=combined_js + initialization_call_js
    )

    # 5. Attach to DocumentReady
    doc.on_event(DocumentReady, init_callback)

    logger.info("Unified JS initialization callback attached to DocumentReady.")
    return doc


