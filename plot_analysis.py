"""
Noise Survey Analysis Tool
--------------------------
This script provides tools for loading, analyzing, and visualizing noise survey data from
different sound meter models (Noise Sentry, NTi, and Svan).

It can be run in two modes:
1. As a complete script (python plot_analysis.py)
2. With individual cells run in a Jupyter-like environment (VS Code, Jupyter, etc.)

Use the cell markers (#%%) to execute individual code sections for interactive analysis.

For audio playback, ensure VLC is installed and the path is set correctly.
Run as "bokeh serve --show plot_analysis.py"
"""

#%% Imports
import os
import time
import datetime
import logging
import pandas as pd
import numpy as np
import re
import vlc

from bokeh.io import output_notebook, show
from bokeh.plotting import figure, curdoc, output_file, save
from bokeh.models import (
    ColumnDataSource, Div, Tabs, TabPanel, CheckboxGroup, CustomJS, 
    Select, Button
)
from bokeh.events import Tap, DocumentReady
from bokeh.layouts import column, row

# Import data parser functions
from data_parsers import read_in_noise_sentry_file, read_in_Svan_file, read_NTi, safe_convert_to_float

# Import JavaScript callbacks
from js_callbacks import get_hover_line_js, get_click_line_js, get_keyboard_navigation_js, get_update_spectrogram_js, get_common_utility_functions

# Import visualization components
from visualization_components import (
    CONFIG, create_TH_chart, create_log_chart, make_spectrogram, make_rec_spectrogram,
    create_frequency_bar_chart, create_range_selector, link_x_ranges, add_vertical_line_and_hover
)

# Import audio playback handler
from AudioPlaybackHandler import AudioPlaybackHandler

#%% Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#%% Utility Functions
def get_common_time_range(dataframes, column='Datetime'):
    """
    Find the common time range across multiple dataframes, handling nested dictionaries.
    
    Parameters:
    dataframes (dict): dict of DataFrames or nested dicts containing DataFrames to analyze
    column (str): Name of the datetime column
    
    Returns:
    tuple: (start_time, end_time) as pandas Timestamps
    """
    start_times = []
    end_times = []
    
    def process_item(item):
        if isinstance(item, dict):
            # If it's a dictionary, recursively process its values
            for value in item.values():
                process_item(value)
        elif hasattr(item, 'columns'):  # Check if it's a DataFrame-like object
            if column in item.columns and not item.empty:
                start_times.append(item[column].min())
                end_times.append(item[column].max())
    
    # Process the input dictionary
    process_item(dataframes)
    
    if not start_times or not end_times:
        return None, None
    
    common_start = max(start_times)
    common_end = min(end_times)
    
    return common_start, common_end

def filter_by_time_range(df, start_time, end_time, column='Datetime'):
    """
    Filter a DataFrame to a specific time range.
    
    Parameters:
    df (pd.DataFrame): DataFrame to filter
    start_time (pd.Timestamp): Start time
    end_time (pd.Timestamp): End time
    column (str): Name of the datetime column
    
    Returns:
    pd.DataFrame: Filtered DataFrame
    """
    if column not in df.columns:
        logger.warning(f"Column {column} not found in DataFrame")
        return df
    
    return df[(df[column] >= start_time) & (df[column] <= end_time)]

#%% Data Configuration
def define_file_paths_and_types():
    """
    Define file paths and parser types for noise survey data.
    
    Modify this function to specify your file paths and data types.
    
    Returns:
    tuple: (file_paths, file_types) - Dictionaries with file paths and parser types
    """
    file_paths = {
        'SW': r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\NS4A\5793 Alton Road, Ross-on-wye_2025_02_21__17h20m41s_2025_02_15__10h45m00s.csv",
        'N': r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\NS7\5793 Alton Road, Ross-on-wye_2025_02_21__17h34m02s_2025_02_15__10h50m00s.csv",
        'SE': r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\5793-1\2025-02-15_SLM_000"
    }
    
    file_types = {
        'SW': 'sentry',  # Noise Sentry (low frequency data only)
        'N': 'sentry',   # Noise Sentry (low frequency data only)
        'SE': 'nti'      # NTi (may have low, high frequency, and spectral data)
    }
    
    return file_paths, file_types

#%% Data Loading
def load_data(file_paths, file_types):
    """
    Load all data using the specified parsers.
    
    Parameters:
    file_paths (dict): Dictionary of file paths
    file_types (dict): Dictionary of parser types
    
    Returns:
    dict: Dictionary of loaded data by position
    """
    position_data = {}
    for position, path in file_paths.items():
        try:
            # Use explicitly specified parser
            parser_type = file_types.get(position, '').lower()
            
            if parser_type == 'sentry':
                logger.info(f"Loading {position} with Noise Sentry parser")
                position_data[position] = read_in_noise_sentry_file(path)
            elif parser_type == 'nti':
                logger.info(f"Loading {position} with NTi parser")
                position_data[position] = read_NTi(path) # may return a dictionary of dataframes
            elif parser_type == 'svan':
                logger.info(f"Loading {position} with Svan parser")
                position_data[position] = read_in_Svan_file(path) # may return a dictionary of dataframes
            else:
                logger.info(f"No parser specified for {position}. Guessing based on file extension.")
                # Guess parser based on file extension
                if path.endswith('.csv'):
                    position_data[position] = read_in_noise_sentry_file(path)
                elif path.endswith('.xlsx'):
                    position_data[position] = read_in_Svan_file(path)
                else:
                    # Assume NTi if no recognizable extension
                    position_data[position] = read_NTi(path)
                    
        except Exception as e:
            logger.error(f"Error loading data for {position}: {e}")
    
    return position_data

#%% Data Inspection
def examine_data(position_data):
    """
    Examine the loaded data structure and print summaries.
    
    Parameters:
    position_data (dict): Dictionary of loaded data by position
    """
    for position, data in position_data.items():
        print(f"\n=== Position: {position} ===")
        
        if isinstance(data, pd.DataFrame):
            print(f"DataFrame with shape: {data.shape}")
            print(f"Columns: {data.columns.tolist()}")
            print(f"Date range: {data['Datetime'].min()} to {data['Datetime'].max()}")
        elif isinstance(data, dict):
            print(f"Dictionary with keys: {list(data.keys())}")
            for key, df in data.items():
                if isinstance(df, pd.DataFrame):
                    print(f"  - {key}: DataFrame with shape {df.shape}")
                    if 'Datetime' in df.columns:
                        print(f"    Date range: {df['Datetime'].min()} to {df['Datetime'].max()}")

#%% Time Range Synchronization
def synchronize_time_range(position_data):
    """
    Find common time range and synchronize data across all positions.
    
    Parameters:
    position_data (dict): Dictionary of loaded data by position
    
    Returns:
    dict: Dictionary of filtered data by position
    """
    try:
        common_start, common_end = get_common_time_range(position_data)
        logger.info(f"Common time range: {common_start} to {common_end}")
        
        # Filter data to common time range, allowing nested dictionaries
        for position in position_data:
            if isinstance(position_data[position], dict):
                for key, df in position_data[position].items():
                    if isinstance(df, pd.DataFrame) and 'Datetime' in df.columns:
                        position_data[position][key] = filter_by_time_range(df, common_start, common_end)
            else:
                position_data[position] = filter_by_time_range(position_data[position], common_start, common_end)
    except Exception as e:
        logger.error(f"Error determining common time range: {e}")
        logger.warning("Disabling chart synchronization")
        CONFIG["chart_settings"]["sync_charts"] = False
    
    return position_data

#%% Visualization Creation
def create_visualizations(position_data, chart_order=None):
    """
    Create and display visualizations with individual checkboxes and optional chart ordering.
    
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
    all_sources = {}
    
    # Variables for spectral data handling
    spectral_data = None
    spectral_position = None
    spectral_chart = None
    spectral_source = None
    
    # Process each position's data to create charts
    for position, data in position_data.items():
        if isinstance(data, pd.DataFrame):
            df = data
        else:
            df = data.get('combined', None)
            if df is None or df.empty:
                for key in ['RPT', 'main', 'data']:
                    if key in data and isinstance(data[key], pd.DataFrame) and not data[key].empty:
                        df = data[key]
                        break
        
        if df is not None and not df.empty:
            chart, source = create_TH_chart(
                df,
                title=f"{position} - Overview",
                height=CONFIG["chart_settings"]["low_freq_height"]
            )
            all_charts.append(chart)
            time_series_charts.append(chart)
            all_sources[f"{position}_low_freq"] = source
        
        if isinstance(data, dict):
            # Add high frequency data chart if available
            for key in ['RPT_LOG', 'log']:
                if key in data and isinstance(data[key], pd.DataFrame) and not data[key].empty:
                    high_freq_df = data[key]
                    chart, source = create_log_chart(
                        high_freq_df,
                        title=f"{position} - Logging Data",
                        height=CONFIG["chart_settings"]["high_freq_height"]
                    )
                    all_charts.append(chart)
                    time_series_charts.append(chart)
                    all_sources[f"{position}_high_freq"] = source
                    break
            
            # Add spectral data chart if available
            for key in ['RTA', 'spectral']:
                if key in data and isinstance(data[key], pd.DataFrame) and not data[key].empty:
                    spectral_df = data[key]
                    spectral_data = spectral_df
                    spectral_position = position
                                
                    # Create initial spectrogram
                    default_param = "LZeq"  # Default parameter
                    chart, source = make_rec_spectrogram(
                        default_param,
                        spectral_df,
                        title=f"{position} - Frequency Analysis",
                        height=CONFIG["chart_settings"]["spectrogram_height"]
                    )
                    spectral_chart = chart
                    spectral_source = source
                    all_charts.append(chart)
                    time_series_charts.append(chart)
                    all_sources[f"{position}_spectral"] = source
                    break
    
    # Add frequency bar chart if spectral data exists
    if spectral_data is not None:
        freq_bar_chart, freq_bar_source = create_frequency_bar_chart(
            title=f"{spectral_position} - Frequency Distribution",
            height=360
        )
        all_sources['frequency_bar'] = freq_bar_source
        all_charts.append(freq_bar_chart)
    
    # Create CheckboxGroup with labels from chart titles
    chart_labels = [chart.title.text for chart in all_charts]
    checkbox = CheckboxGroup(labels=chart_labels, active=list(range(len(all_charts))))
    
    # Define callback to toggle chart visibility
    callback = CustomJS(args={'charts': all_charts}, code="""
        const active = cb_obj.active;
        for (let i = 0; i < charts.length; i++) {
            charts[i].visible = active.includes(i);
        }
    """)
    checkbox.js_on_change('active', callback)
    
    # Add dropdown for spectrogram parameters if spectral data exists
    if spectral_data is not None and spectral_chart is not None:
        # Extract available frequency parameters from spectral data
        columns = spectral_data.columns
        param_prefixes = sorted(set(
            col.split('_')[0] for col in columns
            if '_' in col and col.split('_')[0].startswith('L') and col.split('_')[1][:1].isdigit()
        ))
        if not param_prefixes:
            param_prefixes = ["LZeq"]  # Fallback if no parameters found
        
        # Create Select widget
        spectrogram_select = Select(
            title="Select Frequency Parameter",
            value="LZeq",  # Default value
            options=param_prefixes
        )
        
        # Define callback to update spectrogram data
        callback = CustomJS(args=dict(
            source=spectral_source,
            chart=spectral_chart,
            df=spectral_data.to_dict(orient='list'),  # Pass DataFrame as dictionary
            frequencies=[
                float(col.split('_')[1]) for col in columns
                if col.startswith('LZeq_') and col.split('_')[1][:1].isdigit()
            ][8:-10]  # Match make_rec_spectrogram frequency range
        ), code=get_update_spectrogram_js())
        spectrogram_select.js_on_change('value', callback)


    # Add checkbox group to layout after the title
    layout.children.append(checkbox)

    # Add spectrogram-specific controls if applicable
    if spectral_data is not None and spectral_chart is not None:
        layout.children.append(spectrogram_select)
    
    # Add range selector and hover functionality if time series charts exist
    if time_series_charts:
        range_selector = create_range_selector(time_series_charts[0], all_sources[list(all_sources.keys())[0]])
        layout.children.append(range_selector)
        charts, hover_lines, click_lines, labels = add_vertical_line_and_hover([range_selector] + time_series_charts, all_sources)
        link_x_ranges(time_series_charts)
    
    # Reorder charts if chart_order is provided
    if chart_order is not None:
        # Validate and map chart_order to indices
        if all(isinstance(x, str) for x in chart_order):
            # Order by titles
            title_to_index = {chart.title.text: i for i, chart in enumerate(all_charts)}
            ordered_indices = [title_to_index[title] for title in chart_order if title in title_to_index]
            remaining_indices = [i for i in range(len(all_charts)) if i not in ordered_indices]
            final_order = ordered_indices + remaining_indices
        elif all(isinstance(x, int) for x in chart_order):
            # Order by indices
            final_order = [i for i in chart_order if 0 <= i < len(all_charts)]
            remaining_indices = [i for i in range(len(all_charts)) if i not in final_order]
            final_order += remaining_indices
        else:
            logger.warning("chart_order must be a list of titles or indices. Using default order.")
            final_order = range(len(all_charts))
        
        # Reorder all_charts
        all_charts = [all_charts[i] for i in final_order]
        # Update checkbox labels to match new order
        chart_labels = [all_charts[i].title.text for i in range(len(all_charts))]
        checkbox.labels = chart_labels
        checkbox.active = list(range(len(all_charts)))  # Reset active to match new order

    # Append all charts to the layout in the specified order
    for chart in all_charts:
        layout.children.append(chart)
    
    return layout, all_charts, all_sources, click_lines, labels

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
    # Audio setup
    media_path = r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\5793-1"
    audio_handler = AudioPlaybackHandler(media_path)

    # Create a ColumnDataSource to communicate playback time to JavaScript
    playback_source = ColumnDataSource(data={'current_time': [0]})

    # Create visualizations (assumes this includes add_vertical_line_and_hover)
    layout, all_charts, all_sources, click_lines, labels = create_visualizations(position_data)

    # Calculate start_time after all_sources is populated
    start_time = pd.Timestamp(min(all_sources[list(all_sources.keys())[0]].data['Datetime']))

    # Initialize updateAllLines function in global scope before attaching callbacks
    init_js = CustomJS(args={'charts': all_charts, 'sources': all_sources, 'click_lines': click_lines, 'labels': labels}, code=get_common_utility_functions())
    
    # Add the initialization JavaScript to the document
    doc.on_event(DocumentReady, init_js)

    # Define tap callback to jump to clicked time
    def tap_callback(event):
        selected_time_ms = event.x
        timestamp = datetime.datetime.fromtimestamp(selected_time_ms / 1000)
        relative_time_s = (selected_time_ms - start_time.timestamp() * 1000) / 1000  # Convert to seconds
        if audio_handler.is_playing:
            audio_handler.play(timestamp)
        absolute_time_ms = start_time.timestamp() * 1000 + relative_time_s * 1000
        playback_source.data = {'current_time': [absolute_time_ms]}
        logger.debug(f'Setting time to timestamp: {timestamp}, absolute time: {absolute_time_ms}')

    # Attach tap callback to all charts
    for chart in all_charts:
        chart.on_event(Tap, tap_callback)
    
    # JavaScript code to call updateAllLines with the current time
    update_js = """
    console.log('update triggered')
    if (typeof window.updateAllLines === 'function') {
        console.log('updating lines to ' + playback_source.data['current_time'][0]);
        window.updateAllLines(playback_source.data['current_time'][0]);
    } else {
        console.log('updateAllLines is not defined');
    }
    """
    playback_callback = CustomJS(args={'playback_source': playback_source, 'charts': all_charts, 'sources': all_sources}, code=update_js)

    # Register the JS callback to fire when playback_source changes
    playback_source.js_on_change('data', playback_callback)

    # Periodic update function to track audio playback
    def update():
        if audio_handler.is_playing:
            current_pos = audio_handler.get_current_position()
            if current_pos:
                absolute_time_ms = current_pos.timestamp() * 1000
                playback_source.data = {'current_time': [absolute_time_ms]} #this will trigger the JS callback

    # Update every 1 second
    doc.add_periodic_callback(update, 1000)

    doc.add_root(playback_source)
    
    # Playback controls
    play_button = Button(label="▶️ Play", button_type="success")
    pause_button = Button(label="⏸️ Pause", button_type="warning")
    stop_button = Button(label="⏹️ Stop", button_type="danger")

    def play_audio():
        absolute_time_ms = playback_source.data['current_time'][0]
        if audio_handler.is_playing:
            return  # Already playing, do nothing
        timestamp = datetime.datetime.fromtimestamp(absolute_time_ms / 1000)  # Convert ms to seconds
        logger.info(f'Playing audio at: {timestamp}')
        audio_handler.play(timestamp)
        
    play_button.on_click(play_audio)
    pause_button.on_click(lambda: audio_handler.pause())
    stop_button.on_click(lambda: audio_handler.stop())

    controls = row(play_button, pause_button, stop_button)
    layout.children.append(controls)

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
    if file_paths is None:
        file_paths, file_types = define_file_paths_and_types()
    
    # Load data from files
    position_data = load_data(file_paths, file_types)
    
    # Print data overview
    examine_data(position_data)
    
    # Synchronize time ranges if configured
    if CONFIG["chart_settings"]["sync_charts"]:
        position_data = synchronize_time_range(position_data)
    
    # Create visualizations
    layout, all_charts, all_sources, click_lines, labels = create_visualizations(position_data)
    
    # Initialize updateAllLines function in global scope before attaching callbacks
    init_js = CustomJS(args={'charts': all_charts, 'sources': all_sources, 'click_lines': click_lines, 'labels': labels}, code=get_common_utility_functions())
    
    # Add the initialization JavaScript to the document
    curdoc().on_event(DocumentReady, init_js)
    
    # Display the layout
    show(layout)

    output_file("noise_survey.html")  # Set output file name
    save(layout)
    
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