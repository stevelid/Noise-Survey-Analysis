"""
app.py

Noise Survey Analysis Tool
--------------------------
This script provides tools for loading, analyzing, and visualizing noise survey data from
different sound meter models (Noise Sentry, NTi, and Svan).

It can be run in two modes:
1. As a complete script (bokeh serve --show app.py)
2. With individual cells run in a Jupyter-like environment (VS Code, Jupyter, etc.)

Use the cell markers (#%%) to execute individual code sections for interactive analysis.
"""

#%% Imports
import os
import time
import datetime
import logging
import pandas as pd
import numpy as np
import vlc
import sys

# Add the project root to the Python path to enable proper imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bokeh.io import output_notebook, show
from bokeh.plotting import figure, curdoc
from bokeh.models import (
    ColumnDataSource, Div, Tabs, TabPanel, CheckboxGroup, CustomJS, 
    Select, Button
)
from bokeh.events import Tap, DocumentReady
from bokeh.layouts import column, row

# Configure Logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

#%% Import from the new module structure
# Core components
try:
    # Try normal imports first (for when the module is properly installed)
    from noise_survey_analysis.core.config import CONFIG, DEFAULT_FILE_PATHS, DEFAULT_FILE_TYPES
    from noise_survey_analysis.core.data_loaders import load_data, examine_data, define_file_paths_and_types
    from noise_survey_analysis.core.data_processors import synchronize_time_range
    from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler

    # Interactive visualization components
    from noise_survey_analysis.visualization.interactive import (
        create_range_selector, link_x_ranges, add_vertical_line_and_hover, initialize_global_js
    )
except ImportError:
    # Use relative imports for Bokeh server mode
    logger.info("Using relative imports for Bokeh server mode")
    from core.config import CONFIG, DEFAULT_FILE_PATHS, DEFAULT_FILE_TYPES
    from core.data_loaders import load_data, examine_data, define_file_paths_and_types
    from core.data_processors import synchronize_time_range
    from core.audio_handler import AudioPlaybackHandler

    # Interactive visualization components
    from visualization.interactive import (
        create_range_selector, link_x_ranges, add_vertical_line_and_hover, initialize_global_js
    )

# Import original visualization components (will move to new structure in Phase 2)
from visualization_components import (
    create_TH_chart, create_log_chart, make_spectrogram, make_rec_spectrogram,
    create_frequency_bar_chart
)

#%% Visualization Creation
def create_visualizations(position_data, chart_order=None):
    """
    Create and display visualizations with individual checkboxes and optional chart ordering.
    Assigns source keys to chart 'name' properties for robust JS lookup.
    
    Parameters:
    position_data (dict): Dictionary of loaded data by position
    chart_order (list, optional): List of chart titles or indices specifying the desired order
    
    Returns:
    tuple: (layout, all_charts, all_sources) - The created Bokeh layout and supporting data
    """
    # Initialize the layout
    layout = column()
    
    # Add dashboard title
    title_text = "Sound Level Analysis Dashboard"
    title_div = Div(
        text=f"<h1 style='text-align: center;'>{title_text}</h1>",
        sizing_mode="stretch_width"
    )
    layout.children.append(title_div)
    
    # Lists to store charts and data sources
    all_charts = []
    time_series_charts = []
    all_sources = {} # This will store { source_key: ColumnDataSource }
    
    # Variables for spectral data handling
    spectral_data = None
    spectral_position = None
    spectral_chart = None
    spectral_source = None
    
    # Process each position's data to create charts
    for position, data in position_data.items():
        df = None # Initialize DataFrame
        #--- Find the main time series dataframe ---
        if isinstance(data, pd.DataFrame):
            df = data
            main_data_key_part = 'main' # Generic key part if only one DataFrame
        elif isinstance(data, dict):
            # Prioritize 'combined' key, then fallback to 'RPT', 'main', or 'data'
            if 'combined' in data and isinstance(data['combined'], pd.DataFrame) and not data['combined'].empty:
                df = data['combined']
                main_data_key_part = 'combined'
            else:
                for key in ['RPT', 'main', 'data']:
                    if key in data and isinstance(data[key], pd.DataFrame) and not data[key].empty:
                        df = data[key]
                        main_data_key_part = key.lower()
                        break
        else:
            logger.warning(f"Unexpected data type for position {position}: {type(data)}")
            continue # Skip this position if data format is wrong
        
        #--- Create TH Chart ---
        if df is not None and not df.empty:
            #define a unique source key
            source_key = f"{position}_{main_data_key_part}_low_freq" # e.g., "P1_rpt_low_freq"
            chart_title = f"{position} - Overview ({main_data_key_part.upper()})"
            
            chart, source = create_TH_chart(
                df,
                title=chart_title,
                height=CONFIG["chart_settings"]["low_freq_height"]
            )
            # *** Assign the source key to the chart's name ***
            chart.name = source_key            
            all_charts.append(chart)
            time_series_charts.append(chart)
            all_sources[source_key] = source
        
# --- Process nested data (High Freq, Spectral) ---
        if isinstance(data, dict):
            # --- Create High Frequency Chart (if log data exists) ---
            high_freq_df = None
            log_data_key_part = None
            for key in ['RPT_LOG', 'log']:
                if key in data and isinstance(data[key], pd.DataFrame) and not data[key].empty:
                    high_freq_df = data[key]
                    log_data_key_part = key.lower() # e.g., 'rpt_log' or 'log'
                    break

            if high_freq_df is not None:
                # Define a unique source key
                source_key = f"{position}_{log_data_key_part}_high_freq" # e.g., "P1_rpt_log_high_freq"
                chart_title = f"{position} - Logging Data ({log_data_key_part.upper()})"

                chart, source = create_log_chart(
                    high_freq_df,
                    title=chart_title,
                    height=CONFIG["chart_settings"]["high_freq_height"]
                )
                 # *** Assign the source key to the chart's name ***
                chart.name = source_key
                all_charts.append(chart)
                time_series_charts.append(chart)
                all_sources[source_key] = source # Store source with its key

            # --- Create Spectral Chart (if spectral data exists) ---
            spectral_df = None
            spectral_data_key_part = None
            for key in ['RTA', 'spectral']:
                if key in data and isinstance(data[key], pd.DataFrame) and not data[key].empty:
                    spectral_df = data[key]
                    spectral_data_key_part = key.lower() # e.g., 'rta' or 'spectral'
                    spectral_data = spectral_df # Keep track for bar chart
                    spectral_position = position
                    break

            if spectral_df is not None:
                 # Define a unique source key
                source_key = f"{position}_{spectral_data_key_part}_spectral" # e.g., "P1_rta_spectral"
                chart_title = f"{position} - Frequency Analysis ({spectral_data_key_part.upper()})"

                default_param = "LZeq" # Default parameter
                chart, source = make_rec_spectrogram(
                    default_param,
                    spectral_df,
                    title=chart_title, # Use the defined title
                    height=CONFIG["chart_settings"]["spectrogram_height"]
                )
                # *** Assign the source key to the chart's name ***
                chart.name = source_key
                spectral_chart = chart # Keep reference
                spectral_source = source # Keep reference
                all_charts.append(chart)
                # Decide if spectrograms should link x-axis and have vertical lines
                time_series_charts.append(chart) # Optional: include in time sync/lines
                all_sources[source_key] = source # Store source with its key


    # --- Create Frequency Bar Chart (if spectral data exists) ---
    if spectral_data is not None:
        # Define a unique source key
        source_key = "frequency_bar"
        chart_title = f"{spectral_position} - Frequency Distribution at Tap Time"

        freq_bar_chart, freq_bar_source = create_frequency_bar_chart(
            title=chart_title,
            height=360
        )
        # *** Assign the source key to the chart's name ***
        freq_bar_chart.name = source_key
        all_sources[source_key] = freq_bar_source # Store source
        all_charts.append(freq_bar_chart)
        # Note: Frequency bar chart doesn't usually sync time or need vertical line like others


    # --- Checkbox Group ---
    # Create CheckboxGroup with labels from chart titles (titles are more user-friendly)
    chart_labels = [chart.title.text for chart in all_charts]
    checkbox = CheckboxGroup(labels=chart_labels, active=list(range(len(all_charts))))

    callback = CustomJS(args={'charts': all_charts}, code="""
        const active = cb_obj.active;
        charts.forEach((chart, i) => {
            chart.visible = active.includes(i);
        });
    """)
    checkbox.js_on_change('active', callback)
    layout.children.append(checkbox) # Add checkbox group

    # --- Spectrogram Dropdown (if applicable) ---
    if spectral_data is not None and spectral_chart is not None:
        # (Keep existing dropdown code - it updates the *data* in the spectral source)
        # Extract available frequency parameters...
        columns = spectral_data.columns
        param_prefixes = sorted(set(
            col.split('_')[0] for col in columns
            if '_' in col and col.split('_')[0].startswith('L') and col.split('_')[1][:1].isdigit()
        ))
        if not param_prefixes:
            param_prefixes = ["LZeq"]

        spectrogram_select = Select(
            title="Select Spectrogram Parameter",
            value="LZeq",
            options=param_prefixes
        )

        from noise_survey_analysis.js.loader import get_frequency_js
        frequency_js = get_frequency_js()

        # Pass the key of the spectral source to the JS callback
        spectral_source_key = spectral_chart.name # Get the name we assigned earlier
        callback = CustomJS(args=dict(
            # Pass the specific spectral source using its key
            source=all_sources[spectral_source_key],
            chart=spectral_chart,
            df_dict=spectral_data.to_dict(orient='list'), # Pass full data dict
            # Calculate frequencies dynamically based on available columns
            # Make sure this matches the range used in make_rec_spectrogram
            frequencies=[
                float(col.split('_')[1]) for col in spectral_data.columns
                if col.startswith('LZeq_') and '_' in col and col.split('_')[1][:1].isdigit()
            ][CONFIG['chart_settings'].get('lower_freq_band', 0):CONFIG['chart_settings'].get('upper_freq_band', None)] # Match make_rec_spectrogram slicing
        ), code=frequency_js + "\n\n" + "updateSpectrogram(cb_obj.value, df_dict, chart, source, frequencies);") # Pass df_dict
        spectrogram_select.js_on_change('value', callback)
        layout.children.append(spectrogram_select)


    all_click_lines = []
    all_labels = []

    # --- Range Selector and Interactions (if time series charts exist) ---
    if time_series_charts:
        # Use the first time series chart and its source for the range selector
        first_ts_chart = time_series_charts[0]
        first_ts_source_key = first_ts_chart.name # Get its assigned name
        first_ts_source = all_sources[first_ts_source_key]

        range_selector = create_range_selector(first_ts_chart, first_ts_source)
        # *** Assign a name to range selector for potential JS identification ***
        range_selector.name = "range_selector"
        layout.children.append(range_selector)

        # Identify charts that should have vertical lines and hover/tap interactions
        # Typically time series charts + the range selector itself
        charts_for_interaction = [range_selector] + time_series_charts
        # Maybe include spectrogram if desired: + ([spectral_chart] if spectral_chart else [])

        # Add vertical lines, hover, tap using the identified charts and all sources
        # interactive.py's add_vertical_line_and_hover will pass models to JS
        _, all_click_lines, all_labels = add_vertical_line_and_hover(charts_for_interaction, all_sources)

        

        # Link x-ranges only for the time series charts (and optionally spectrogram)
        link_x_ranges(time_series_charts) # Keep this for actual time series plots
        # If linking spectrogram: link_x_ranges(time_series_charts + ([spectral_chart] if spectral_chart else []))

        charts_for_js_init = charts_for_interaction
    else:
        charts_for_js_init = all_charts


    # --- Chart Ordering (if chart_order is provided) ---
    if chart_order is not None:
        # Validate and process the chart_order parameter
        final_order = []
        
        # Case 1: chart_order contains integers (indices)
        if all(isinstance(item, int) for item in chart_order):
            # Filter out invalid indices
            final_order = [i for i in chart_order if 0 <= i < len(all_charts)]
            
        # Case 2: chart_order contains strings (chart titles or partial matches)
        elif all(isinstance(item, str) for item in chart_order):
            for title_pattern in chart_order:
                # Find charts with matching titles (case-insensitive)
                for i, chart in enumerate(all_charts):
                    chart_title = chart.title.text.lower()
                    if title_pattern.lower() in chart_title:
                        final_order.append(i)
                        break  # Stop after first match for this pattern
        
        # If no valid ordering was created, fall back to default order
        if not final_order:
            final_order = list(range(len(all_charts)))
            logger.warning("Invalid chart_order provided. Using default chart order.")
        
        # Add any charts that weren't explicitly ordered at the end
        all_indices = set(range(len(all_charts)))
        missing_indices = all_indices - set(final_order)
        final_order.extend(sorted(missing_indices))
        
        # Reorder all_charts
        all_charts = [all_charts[i] for i in final_order]
        # Update checkbox labels and active state
        chart_labels = [chart.title.text for chart in all_charts]
        checkbox.labels = chart_labels
        checkbox.active = list(range(len(all_charts)))  # Ensure active matches new order

    # Append all charts (potentially reordered) to the layout
    for chart in all_charts:
        layout.children.append(chart) # Append reordered charts

    # Add frequency bar chart last if it wasn't included in the reordering logic explicitly
    # (Ensure it's only added once if it exists)
    if 'frequency_bar' in all_sources and freq_bar_chart not in layout.children:
         layout.children.append(freq_bar_chart)


    return layout, all_charts, charts_for_js_init, all_sources, all_click_lines, all_labels

#%% Bokeh App Creation for Interactive Mode
def create_app(doc, position_data):
    """
    Create a Bokeh app with audio support.
    
    Parameters:
    doc: Bokeh document to add components to
    position_data (dict): Dictionary of loaded data by position
    
    Returns:
    None - Adds components directly to the Bokeh document
    """
    # --- Audio setup ---
    media_path = r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\5793-1"
    audio_handler = AudioPlaybackHandler(media_path)
    playback_source = ColumnDataSource(data={'current_time': [0]}, name='playback_source')


    # --- Visualizations ---
    layout, all_charts, charts_for_js_init, all_sources, all_click_lines, all_labels = create_visualizations(position_data)

    # --- Playback Controls ---
    # *** Give buttons unique names for JS lookup ***
    play_button = Button(label="▶️ Play", button_type="success", name="play_button")
    pause_button = Button(label="⏸️ Pause", button_type="warning", name="pause_button")
    stop_button = Button(label="⏹️ Stop", button_type="danger", name="stop_button")
   
   
    # --- Initializations ---
    doc = initialize_global_js(
        doc, 
        charts_for_js_init, 
        all_sources, 
        all_click_lines, 
        all_labels,
        playback_source,
        play_button,
        pause_button
    )

    start_time = pd.Timestamp(min(all_sources[list(all_sources.keys())[0]].data['Datetime']))

    # --- Python Tap Callback --- 
    def tap_callback(event):
        # This could potentially *just* start playback if desired,
        # letting JS handle the position update via playback_source.
        # Or, keep it for explicit seek on tap? Let's keep seek for now.
        selected_time_ms = event.x
        timestamp = datetime.datetime.fromtimestamp(selected_time_ms / 1000)
        logger.debug(f'Tap Event: Seeking audio to {timestamp}')
        # Use the lambda with the next_tick_callback inside update_playback_position
        if audio_handler.is_playing: # Seek if already playing
            audio_handler.play(timestamp, lambda pos: update_playback_position(pos, start_time, playback_source))
        # Note: JS handleTap will have already updated playback_source.data

    # Attach Python tap callback (if still needed for seek-on-tap)
    for chart in charts_for_js_init: # Use the list corresponding to interactions
        if chart.name != 'range_selector':
            chart.on_event(Tap, tap_callback)

    # --- update_playback_position using add_next_tick_callback ---
    def update_playback_position(current_pos, start_time, playback_source):
        if current_pos:
            absolute_time_ms = current_pos.timestamp() * 1000
            def update_data():
                try:
                    playback_source.data = {'current_time': [absolute_time_ms]}
                except Exception as e:
                    logger.error(f"Error updating playback_source data: {e}")
            doc.add_next_tick_callback(update_data)

    
    #  --- JS callback for playback source change  ---
    from noise_survey_analysis.js.loader import get_audio_js
    audio_js = get_audio_js()
    
    # Playback source JS callback (Update JS visuals based on audio time)
    update_js = """
    console.log('JS playback_callback: Fired.'); // Basic check it runs
    const currentData = playback_source.data;
    if (!currentData || !currentData['current_time'] || currentData['current_time'].length === 0) {
        console.log('JS playback_callback: Invalid data in playback_source.');
        return;
    }
    const currentTime = currentData['current_time'][0];
    console.log('JS playback_callback: Received time:', new Date(currentTime).toISOString()); // Log the time received

    // Check if functions AND models are ready (BE VERY THOROUGH)
    const functionsReady = typeof window.updateAllLines === 'function' && typeof window.findClosestDateIndex === 'function';
    const modelsReady = window.chartRefs && window.clickLineModels && window.labelModels &&
                       window.chartRefs.length > 0 && window.clickLineModels.length > 0 && window.labelModels.length > 0;

    if (functionsReady && modelsReady) {
        console.log('JS playback_callback: Functions and models ready. Calling updateAllLines.'); // Confirmation
        try { // Add try-catch within JS callback for safety
             window.updateAllLines(currentTime, window.chartRefs, window.clickLineModels, window.labelModels);
        } catch (e) {
             console.error("JS playback_callback: Error calling updateAllLines:", e);
        }
    } else {
        console.warn('JS functions or global models not ready for playback update.');
        // Log detailed status
        console.log('typeof window.updateAllLines:', typeof window.updateAllLines);
        console.log('typeof window.findClosestDateIndex:', typeof window.findClosestDateIndex);
        console.log('window.chartRefs:', window.chartRefs ? window.chartRefs.length : 'undefined');
        console.log('window.clickLineModels:', window.clickLineModels ? window.clickLineModels.length : 'undefined');
        console.log('window.labelModels:', window.labelModels ? window.labelModels.length : 'undefined');
    }
    """
    playback_callback = CustomJS(args={'playback_source': playback_source}, code=update_js)
    playback_source.js_on_change('data', playback_callback)

    # --- Periodic update function to track audio playback ---
    def update():
        if audio_handler.is_playing:
            current_pos = audio_handler.get_current_position()
            if current_pos:
                update_playback_position(current_pos, start_time, playback_source)

    doc.add_periodic_callback(update, 1000)


    # --- NEW: Python callback to handle seeks triggered by JS ---
    # Threshold for difference (in ms) to distinguish seek vs normal playback update
    # Needs tuning - should be larger than your periodic update interval (e.g., 1000ms)
    # plus some buffer for timing variations.
    SEEK_THRESHOLD_MS = 1500

    # Store the last time processed by this handler to avoid rapid seeks
    last_seek_handler_time_ms = [0] # Use a list to allow modification within inner function

    def python_seek_handler(attr, old, new):
        # Runs when playback_source.data changes
        if not new or 'current_time' not in new or not new['current_time']:
            return # No valid new time

        new_time_ms = new['current_time'][0]

        # Avoid processing if the time hasn't actually changed significantly
        # from the *last time this handler specifically processed*.
        # This helps prevent duplicate seeks if the event fires rapidly.
        if abs(new_time_ms - last_seek_handler_time_ms[0]) < 100: # Small tolerance
            return
        
        # Update the last processed time
        last_seek_handler_time_ms[0] = new_time_ms


        logger.debug(f"SeekHandler triggered. New time: {new_time_ms}, Playing: {audio_handler.is_playing}")

        # Only seek if audio is currently playing
        if audio_handler.is_playing:
            old_time_ms = old.get('current_time', [0])[0] if old and 'current_time' in old else 0
            delta_ms = abs(new_time_ms - old_time_ms)

            logger.debug(f"SeekHandler delta: {delta_ms}ms (Threshold: {SEEK_THRESHOLD_MS}ms)")

            # Check if the change is large enough to be considered a user-initiated seek
            if delta_ms > SEEK_THRESHOLD_MS:
                timestamp = datetime.datetime.fromtimestamp(new_time_ms / 1000)
                logger.info(f"SeekHandler: Detected significant time change ({delta_ms}ms). Seeking audio to {timestamp}")

                # Define the action to be run in the next tick
                def seek_action():
                    try:
                         # Re-check if still playing right before seeking
                         if audio_handler.is_playing:
                            audio_handler.play(timestamp, lambda pos: update_playback_position(pos, start_time, playback_source))
                         else:
                             logger.info("SeekHandler: Audio stopped between event trigger and seek action.")
                    except Exception as e:
                        logger.error(f"Error during seek_action: {e}")

                # Schedule the seek action safely
                doc.add_next_tick_callback(seek_action)
            # else: (Small delta)
            #    logger.debug("SeekHandler: Small delta, assuming playback update. No seek.")
    
    playback_source.on_change('data', python_seek_handler)
    
    # --- Button Click Handlers ---
    def play_button_click(event):
        absolute_time_ms = playback_source.data['current_time'][0]
        if audio_handler.is_playing:
            return  # Already playing, do nothing
        timestamp = datetime.datetime.fromtimestamp(absolute_time_ms / 1000)  # Convert ms to seconds
        logger.info(f'Playing audio at: {timestamp}')
        audio_handler.play(timestamp, lambda pos: update_playback_position(pos, start_time, playback_source))

    def pause_button_click(event):
        audio_handler.pause()
        play_button.disabled = False
        pause_button.disabled = True

    def stop_button_click(event):
        audio_handler.stop()
        play_button.disabled = False
        pause_button.disabled = True

    play_button.on_click(play_button_click)
    pause_button.on_click(pause_button_click)
    stop_button.on_click(stop_button_click)

    controls = row(play_button, pause_button, stop_button)
    layout.children.append(controls)
    
    doc.add_root(playback_source)
    doc.add_root(layout)

#%% Main Function
def main(file_paths=None, file_types=None):
    """
    Main function to run the noise survey analysis.
    
    Parameters:
    file_paths (dict, optional): Dictionary of file paths to analyze.
                               Keys are position names, values are file paths.
    file_types (dict, optional): Dictionary specifying parser to use for each position.
                               Keys are position names, values are parser types ('sentry', 'nti', 'svan').
                               If None, will attempt to guess based on file extension.
    
    Returns:
    tuple: (layout, position_data) - The created Bokeh layout and the loaded data dictionary
    """
    # Initialize default file paths and types if not provided
    if file_paths is None or file_types is None:
        file_paths, file_types = define_file_paths_and_types(file_paths, file_types)
    
    # Load data from files
    position_data = load_data(file_paths, file_types)
    
    # Print data overview
    examine_data(position_data)
    
    # Synchronize time ranges if configured
    if CONFIG["chart_settings"]["sync_charts"]:
        position_data = synchronize_time_range(position_data)
    
    # Create visualizations
    layout, all_charts, all_sources, all_click_lines, all_labels = create_visualizations(position_data)
    
    # Display the layout using bokeh.io.show()
    # This generates a static HTML file (or displays in browser/notebook).
    # All CustomJS callbacks defined in create_visualizations and
    # initialize_js_for_standalone will be embedded in the HTML.
    logger.info("Displaying layout in standalone mode (using bokeh.io.show)...")
    show(layout) # This triggers the rendering to HTML
    
    return layout, position_data

#%% Run Script When Executed Directly
if __name__ == "__main__":
    # When running as a script (not just importing functions),
    # execute the main function with default settings
    logger.info("Running noise survey analysis...")
    main()

#%% Run Interactive Bokeh App in Notebook or Script
def run_bokeh_app():
    """
    Run the interactive Bokeh app with audio support.
    This can be called from a notebook cell or run from the main script.
    """
    file_paths, file_types = define_file_paths_and_types()
    position_data = load_data(file_paths, file_types)
    
    if CONFIG["chart_settings"]["sync_charts"]:
        position_data = synchronize_time_range(position_data)
    
    create_app(curdoc(), position_data)

# For Bokeh server, this portion runs when the module is loaded by the server
if not __name__.startswith('bokeh_app'):
    # This code doesn't run when just importing the module
    pass
else:
    # This runs when the module is loaded by Bokeh server
    run_bokeh_app() 