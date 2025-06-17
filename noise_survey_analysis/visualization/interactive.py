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
def add_hover_interaction(charts, labels, sources=None, bar_source=None, bar_x_range=None,
                          hover_info_div=None, selected_param_holder=None,
                          all_positions_spectral_data=None):
    """
    Adds vertical hover line to charts, creating a unique callback for each chart
    to correctly identify the hovered chart index.

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
    for i, chart in enumerate(valid_charts):
        # Skip for charts where hover is not desired
        if chart.name == 'frequency_bar' or '_spectral' in chart.name:
            continue

        hover_callback = CustomJS(
            args={
                'hoverLinesModels': hover_lines,
                'hoverLabelModels': labels, # Pass the label models to JS
                'chart_index': i  # Pass the specific index of this chart
            },
            code="""
                // Call the application's handler directly
                if (window.NoiseSurveyApp?.interactions?.onHover) {
                    window.NoiseSurveyApp.interactions.onHover(hoverLinesModels, hoverLabelModels, cb_data, chart_index);
                } else {
                    console.error('NoiseSurveyApp.interactions.onHover not defined!');
                }
            """
        )

        hover_tool = HoverTool(
            tooltips=None,
            mode='vline',
            callback=hover_callback,
            name=f"hover_tool_{i}"
        )
        chart.add_tools(hover_tool)

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
        args={}, # No arguments needed, the app state has the models
        code="""
            // Call the application's handler directly
            if (window.NoiseSurveyApp?.interactions?.onTap) {
                window.NoiseSurveyApp.interactions.onTap(cb_obj);
            } else {
                console.error('NoiseSurveyApp.interactions.onTap not defined!');
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
                         using the hierarchical structure
    
    Returns:
    CustomJS: The JavaScript initialization callback that can be attached to a Bokeh model
    """
    logger.debug("Creating JavaScript initialization callback...")
    
    # --- Prepare args dictionary with all needed models ---
    args = {
        # Maps directly from hierarchical structure 
        'all_sources': bokeh_models['sources']['data'],
        'all_charts': bokeh_models['charts']['all'],
        'playback_source': bokeh_models['sources']['playback']['position'],
        'play_button': bokeh_models['ui']['controls']['playback'].get('play_button'),
        'pause_button': bokeh_models['ui']['controls']['playback'].get('pause_button'),
        'position_play_buttons': bokeh_models['ui']['controls']['playback'].get('position_buttons', {}),
        'click_lines': bokeh_models['ui']['visualization']['click_lines'],
        'labels': bokeh_models['ui']['visualization']['labels'],
        'freq_bar_source': bokeh_models['sources']['frequency']['bar'],
        'freq_bar_x_range': bokeh_models['frequency_analysis']['bar_chart']['x_range'],
        'freq_table_div': bokeh_models['frequency_analysis'].get('table_div'),
        'param_holder': bokeh_models['ui']['controls']['parameter']['holder'],
        'param_select': bokeh_models['ui']['controls']['parameter']['select'],
        'seek_command_source': bokeh_models['sources']['playback']['seek_command'],
        'js_trigger_source': bokeh_models['sources']['playback']['js_trigger'],
        'play_request_source': bokeh_models['sources']['playback']['play_request'],
        'spectral_param_charts': bokeh_models['spectral_data'],
        # Add bar chart model itself if needed by JS _updateBarChart
        'barChart': bokeh_models['frequency_analysis']['bar_chart']['figure']
    }

    # --- Filter out None values ---
    args = {k: v for k, v in args.items() if v is not None}

    # --- Prepare JS Code ---
    combined_js = get_combined_js()
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
            freq_table_div: !!freq_table_div,
            param_holder: !!param_holder,
            param_select: !!param_select,
            js_trigger_source: !!js_trigger_source,
            spectral_param_charts: !!spectral_param_charts,
        });
        
    """ + combined_js + """
        console.log('DEBUG: Combined JS loaded, starting app initialization...');
        
        // Create models object with all the required references
        const models = {};
        
        // Create a compact structure for JS that matches what it expects
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
        models.js_trigger_source = js_trigger_source;
        models.bar_source = freq_bar_source;
        models.bar_x_range = freq_bar_x_range;
        models.freqTableDiv = freq_table_div;
        models.barChart = barChart;
        models.param_select = param_select;
        models.param_holder = param_holder;
        models.spectral_param_charts = spectral_param_charts || {};
        models.hierarchical = true;
        
        console.log('DEBUG: Models prepared:', {
            hierarchical: models.hierarchical,
            hasCharts: models.charts && models.charts.length > 0,
            hasBarChart: !!models.barChart,
            hasBarSource: !!models.bar_source,
            hasBarXRange: !!models.bar_x_range,
            positionCount: Object.keys(models.spectral_param_charts || {}).length
        });

        console.log('DEBUG: Models:', models);

        var initOptions = { enableKeyboardNavigation: true };

        // Initialize the app
        if (window.NoiseSurveyApp && typeof window.NoiseSurveyApp.init === 'function') {
            console.log('DEBUG: Found NoiseSurveyApp, calling init...');
            window.NoiseSurveyApp.init(models, initOptions);
            
            // --- Set up the Python-to-JS event listener ---
            if (models.js_trigger_source) {
                models.js_trigger_source.js_on_change('data', (cb_obj) => {
                    const event_name = cb_obj.data.event[0] || '';
                    console.log(`JS Trigger Event Received: ${event_name}`);

                    if (event_name.startsWith('playback_stopped')) {
                        if (window.NoiseSurveyApp && window.NoiseSurveyApp.notifyPlaybackStopped) {
                            window.NoiseSurveyApp.notifyPlaybackStopped();
                        }
                    }
                    // Future events from Python can be handled here
                });
            }
            
            // Ensure global handlers are properly exposed
            window.interactions = window.NoiseSurveyApp.interactions || {};
            window.NoiseFrequency = window.NoiseSurveyApp.frequency || {};
            window.NoiseSurveyAppInitialized = true;
            console.log('DEBUG: NoiseSurveyApp initialization complete.');
        } else {
             console.error('CRITICAL ERROR: Bokeh models (charts, sources, etc.) not available in CustomJS args.');
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


