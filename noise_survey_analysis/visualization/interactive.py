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


def initialize_global_js(bokeh_models):
    """
    Initialize JavaScript environment by loading the unified app.js file 
    and calling NoiseSurveyApp.initialize with all models.
    
    Parameters:
    bokeh_models (dict): Dictionary containing all Bokeh models needed for JS initialization
    
    Returns:
    CustomJS: The JavaScript initialization callback that can be attached to a Bokeh model
    """
    logger.debug("Creating JavaScript initialization callback...")
    
    # --- Prepare args dictionary with all needed models ---
    args = {
        'all_sources': bokeh_models.get('all_sources', {}),
        'all_charts': bokeh_models.get('all_charts', []),
        'playback_source': bokeh_models.get('playback_source'),
        'play_button': bokeh_models.get('playback_controls', {}).get('play_button'),
        'pause_button': bokeh_models.get('playback_controls', {}).get('pause_button'),
        'position_play_buttons': bokeh_models.get('position_play_buttons', {}),
        'click_lines': bokeh_models.get('click_lines', {}),
        'labels': bokeh_models.get('labels', {}),
        'freq_bar_source': bokeh_models.get('freq_bar_source'),
        'freq_bar_x_range': bokeh_models.get('freq_bar_x_range'),
        'param_holder': bokeh_models.get('param_holder'),
        'param_select': bokeh_models.get('param_select'),
        'seek_command_source': bokeh_models.get('seek_command_source'),
        'play_request_source': bokeh_models.get('play_request_source'),
        'spectral_param_charts': bokeh_models.get('spectral_param_charts', {}),
        # Add bar chart model itself if needed by JS _updateBarChart
        'barChart': bokeh_models.get('freq_bar_chart')
    }

    # --- Filter out None values ---
    args = {k: v for k, v in args.items() if v is not None}

    # --- Prepare JS Code ---
    combined_js = get_combined_js() # Get app.js content
    full_js_code = """
        console.log('DEBUG: Starting JavaScript initialization...');
        
        // Log what we received
        console.log('DEBUG: Received models:', {
            all_sources: !!all_sources,
            all_charts: all_charts ? all_charts.length : 0,
            playback_source: !!playback_source,
            play_button: !!play_button,
            pause_button: !!pause_button,
            click_lines: !!click_lines,
            labels: !!labels,
            freq_bar_source: !!freq_bar_source,
            freq_bar_x_range: !!freq_bar_x_range,
            param_holder: !!param_holder,
            param_select: !!param_select,
            spectral_param_charts: !!spectral_param_charts
        });
        
    """ + combined_js + """
        console.log('DEBUG: Combined JS loaded, starting app initialization...');
        
        // Create models object with all the required references
        const models = {};
        models.sources = all_sources || {};
        models.charts = all_charts ? (Array.isArray(all_charts) ? all_charts : Object.values(all_charts)) : [];
        models.clickLines = click_lines ? (Array.isArray(click_lines) ? click_lines : Object.values(click_lines)) : [];
        models.labels = labels ? (Array.isArray(labels) ? labels : Object.values(labels)) : [];
        models.playback_source = playback_source;
        models.seek_command_source = seek_command_source;
        models.play_request_source = play_request_source;
        models.play_button = play_button;
        models.pause_button = pause_button;
        models.position_play_buttons = position_play_buttons || {};
        models.bar_source = freq_bar_source;
        models.bar_x_range = freq_bar_x_range;
        models.barChart = barChart;
        models.param_select = param_select;
        models.param_holder = param_holder;
        models.spectral_param_charts = spectral_param_charts || {};
        
        console.log('DEBUG: Models prepared:', {
            hasCharts: models.charts && models.charts.length > 0,
            hasBarChart: !!models.barChart,
            hasBarSource: !!models.bar_source,
            hasBarXRange: !!models.bar_x_range,
            positionCount: Object.keys(models.spectral_param_charts || {}).length
        });

        var initOptions = { enableKeyboardNavigation: true };

        // Initialize the app
        if (window.NoiseSurveyApp && typeof window.NoiseSurveyApp.init === 'function') {
            console.log('DEBUG: Found NoiseSurveyApp, calling init...');
            window.NoiseSurveyApp.init(models, initOptions);
            
            // Ensure global handlers are properly exposed
            window.interactions = window.NoiseSurveyApp.interactions || {};
            window.NoiseFrequency = window.NoiseSurveyApp.frequency || {};
            window.handleHover = function(hoverLines, cb_data) {
                if (window.NoiseSurveyApp?.interactions?.handleHover) { 
                    return window.NoiseSurveyApp.interactions.handleHover(hoverLines, cb_data); 
                }
                console.warn("NoiseSurveyApp.interactions.handleHover not available.");
                return false;
            };
            window.handleTap = function(cb_obj) {
                if (window.NoiseSurveyApp?.interactions?.handleTap) { 
                    return window.NoiseSurveyApp.interactions.handleTap(cb_obj); 
                }
                console.warn("NoiseSurveyApp.interactions.handleTap not available.");
                return false;
            };
            
            window.NoiseSurveyAppInitialized = true;
            console.log('DEBUG: NoiseSurveyApp initialization complete.');
        } else {
            console.error('DEBUG: NoiseSurveyApp not found or init method not available!');
            console.log('DEBUG: window.NoiseSurveyApp =', window.NoiseSurveyApp);
        }
    """

    # Create CustomJS callback
    try:
        # Pass necessary models directly into args for the JS init code
        callback_args = {**args} # Pass all collected args

        init_callback = CustomJS(args=callback_args, code=full_js_code)
        logger.info("JavaScript initialization callback created.")
        return init_callback
    except Exception as e:
        logger.error(f"Failed to create CustomJS callback: {e}", exc_info=True)
        return None


