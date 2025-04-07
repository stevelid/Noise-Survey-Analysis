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
    from noise_survey_analysis.core.config import CONFIG, DEFAULT_DATA_SOURCES, CHART_SETTINGS, VISUALIZATION_SETTINGS
    from noise_survey_analysis.core.data_loaders import load_and_process_data, examine_data, get_default_data_sources
    from noise_survey_analysis.core.data_processors import synchronize_time_range
    from noise_survey_analysis.core.audio_handler import AudioPlaybackHandler

    # Interactive visualization components
    from noise_survey_analysis.visualization.interactive import (
        create_range_selector, link_x_ranges, add_vertical_line_and_hover, initialize_global_js
    )
    
    # Import refactored visualization components
    from noise_survey_analysis.visualization.visualization_components import (
        create_TH_chart, create_log_chart, make_image_spectrogram,
        create_frequency_bar_chart, link_x_ranges
    )
except ImportError:
    # Use relative imports for Bokeh server mode
    logger.info("Using relative imports for Bokeh server mode")
    from .core.config import CONFIG, DEFAULT_DATA_SOURCES, CHART_SETTINGS, VISUALIZATION_SETTINGS
    from .core.data_loaders import load_and_process_data, examine_data, get_default_data_sources
    from .core.data_processors import synchronize_time_range
    from .core.audio_handler import AudioPlaybackHandler

    # Interactive visualization components
    from .visualization.interactive import (
        create_range_selector, link_x_ranges, add_vertical_line_and_hover, initialize_global_js
    )
    
    # Import refactored visualization components
    from .visualization.visualization_components import (
        create_TH_chart, create_log_chart, make_image_spectrogram,
        create_frequency_bar_chart, link_x_ranges as components_link_x_ranges
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
    chart_details = []  # Store tuples of (chart, source_key) for ordering/checkboxes

    # Variables for spectral data handling (needed for dropdown/bar chart)
    spectral_info = {}
    
    # Initialize variables that may not be created in all code paths
    freq_bar_source = None
    freq_bar_x_range = None
    freq_bar_chart = None
    hover_info_div = None
    param_select = None
    selected_param_holder = None
    spectral_figures = {}
    all_param_data = {}
    
    # --- NEW: Create a single frequency bar chart and hover info div for all spectrograms ---
    freq_bar_chart, freq_bar_source, freq_bar_x_range = create_frequency_bar_chart(
        title="Frequency Slice",
        height=CHART_SETTINGS["frequency_bar_height"]
    )
    freq_bar_chart.name = "frequency_bar"
    all_sources["frequency_bar"] = freq_bar_source
    
    # --- NEW: Data structures for shared spectrogram parameter selection ---
    # Store spectral figures and data for all positions
    spectral_figures = {}
    spectral_sources = {}
    all_spectral_params = set()
    all_positions_spectral_data = {}
    
    # --- Process each position ---
    for position, data_dict in position_data.items():
        logger.info(f"Creating visualizations for position: {position}")
        if not isinstance(data_dict, dict):
            logger.warning(f"Skipping position {position}: Invalid data format: {type(data_dict)}")
            continue 

        # --- 1. Overview Chart ---

        overview_df = data_dict.get('overview')
        if isinstance(overview_df, pd.DataFrame) and not overview_df.empty:
            source_key = f"{position}_overview"
            chart_title = f"{position} - Overview"
            chart, source = create_TH_chart(
                overview_df,
                title=chart_title,
                height=CHART_SETTINGS["low_freq_height"]
            )
            if chart and source:
                chart.name = source_key #Important for JS interactions
                all_sources[source_key] = source
                chart_details.append({'chart': chart, 'key': source_key, 'type': 'overview'})
                time_series_charts.append(chart)
            else:
                logger.error(f"Failed to create overview chart for {position}")
        else:
            logger.warning(f"No 'overview' data found or DataFrame empty for {position}")


        # --- 2. Log Chart ---
        log_df = data_dict.get('log')
        if isinstance(log_df, pd.DataFrame) and not log_df.empty:
            source_key = f"{position}_log"
            chart_title = f"{position} - Log Data"
            chart, source = create_log_chart(
                log_df, 
                title=chart_title, 
                height=CHART_SETTINGS["high_freq_height"]
            )
            if chart and source:
                chart.name = source_key
                all_sources[source_key] = source
                chart_details.append({'chart': chart, 'key': source_key, 'type': 'log'})
                time_series_charts.append(chart)
            else:
                logger.error(f"Failed to create log chart for {position}")
        else:
            logger.info(f"No 'log' data found or DataFrame empty for {position}")
            

        # --- 3. Spectral Chart ---
        spectral_df = data_dict.get('spectral')
        if isinstance(spectral_df, pd.DataFrame) and not spectral_df.empty:
            source_key = f"{position}_spectral"
            chart_title = f"{position} - Spectral Data"
            
            # --- NEW: Find available parameters for this position ---
            available_params = []
            for col in spectral_df.columns:
                if '_' in col and col.split('_')[0].startswith('L'):
                    param = col.split('_')[0]
                    available_params.append(param)
            
            available_params = sorted(set(available_params))
            all_spectral_params.update(available_params)
            
            # Set default parameter
            default_param = "LZeq"
            if default_param not in available_params and available_params:
                default_param = available_params[0]
                logger.warning(f"Default param 'LZeq' not found for {position}, using '{default_param}' instead.")
            
            if available_params:
                # --- NEW: Store position spectral data and metadata ---
                position_spectral_data = {
                    'df': spectral_df,
                    'params': available_params
                }
                all_positions_spectral_data[position] = position_spectral_data
                
                # Create image spectrogram with the shared bar chart/source
                chart, source, hover_info_div = make_image_spectrogram(
                    default_param,
                    spectral_df,
                    bar_source=freq_bar_source,
                    bar_x_range=freq_bar_x_range,
                    position=position,
                    title=chart_title,
                    height=CHART_SETTINGS["spectrogram_height"]
                )
                
                if chart and source:
                    chart.name = source_key
                    all_sources[source_key] = source
                    spectral_figures[position] = chart
                    spectral_sources[position] = source
                    chart_details.append({'chart': chart, 'key': source_key, 'type': 'spectral'})
                    time_series_charts.append(chart) 
                    
                    # Save spectral info for the first position with spectral data
                    # This will be used for the parameter dropdown and bar chart
                    if not spectral_info:
                        spectral_info = {
                            'position': position,
                            'params': available_params,
                            'default_param': default_param
                        }
                else:
                    logger.error(f"Failed to create spectral chart for {position}")
            else:
                logger.error(f"No suitable spectral parameters found for {position}.")
        else:
            logger.info(f"No 'spectral' data found or DataFrame empty for {position}")
            
    # --- Create parameter dropdown if we have spectral data ---
    if all_spectral_params:
        # Convert to sorted list for dropdown
        param_options = sorted(all_spectral_params)
        default_param = spectral_info.get('default_param', param_options[0] if param_options else 'LZeq')
        
        # Create data holder for selected parameter
        selected_param_data = {'param': [default_param]}
        selected_param_holder = ColumnDataSource(data=selected_param_data)
        all_sources['param_holder'] = selected_param_holder
        
        # Create Select widget
        param_select = Select(
            title="Parameter:",
            value=default_param,
            options=param_options,
            width=200
        )
        
        # --- Create pre-calculated data for all parameters and positions ---
        all_param_data = {}
        
        for position, position_data in all_positions_spectral_data.items():
            df = position_data['df']
            position_param_data = {}
            
            for param in position_data['params']:
                # Calculate data for this parameter (similar to make_image_spectrogram but just data)
                param_data = {}
                
                # Find and sort frequency columns
                freq_cols_found = []
                all_frequencies = []
                for col in df.columns:
                    if col.startswith(param + '_') and col.split('_')[-1].replace('.', '', 1).isdigit():
                        try:
                            freq = float(col.split('_')[-1])
                            freq_cols_found.append(col)
                            all_frequencies.append(freq)
                        except (ValueError, IndexError): 
                            continue
                
                if not freq_cols_found:
                    logger.warning(f"No frequency columns found for parameter '{param}' in position '{position}'")
                    continue
                
                sorted_indices = np.argsort(all_frequencies)
                frequencies = np.array(all_frequencies)[sorted_indices]
                freq_columns = np.array(freq_cols_found)[sorted_indices]
                
                # Apply band slicing
                lower_band_idx = CHART_SETTINGS['lower_freq_band']
                upper_band_idx = CHART_SETTINGS['upper_freq_band']
                if upper_band_idx is None or upper_band_idx == -1 or upper_band_idx > len(frequencies):
                    upper_band_idx = len(frequencies)
                
                selected_frequencies = frequencies[lower_band_idx:upper_band_idx]
                selected_freq_columns = freq_columns[lower_band_idx:upper_band_idx]
                
                if len(selected_frequencies) == 0:
                    logger.warning(f"No frequencies after band slicing for '{param}' in position '{position}'")
                    continue
                
                n_freqs = len(selected_frequencies)
                
                # Prepare data for image glyph
                levels_matrix = df[selected_freq_columns].values
                times_dt = df['Datetime'].values
                n_times = len(times_dt)
                
                if n_times == 0:
                    logger.warning(f"No time points for '{param}' in position '{position}'")
                    continue
                
                # Store flattened levels with NaNs for hover
                param_data['levels_flat_nan'] = levels_matrix.flatten()
                
                # Handle NaNs for image display
                valid_levels = levels_matrix[~np.isnan(levels_matrix)]
                if len(valid_levels) > 0:
                    min_val, max_val = np.nanmin(valid_levels), np.nanmax(valid_levels)
                    nan_replace_val = min_val - 20
                else:
                    min_val, max_val = 0, 100
                    nan_replace_val = -100
                
                levels_matrix_filled = np.nan_to_num(levels_matrix, nan=nan_replace_val)
                
                # Transpose levels matrix for Bokeh image
                param_data['image_data'] = levels_matrix_filled.T
                
                # Store color mapper range
                if len(valid_levels) > 0:
                    param_data['mapper_low'], param_data['mapper_high'] = min_val, max_val
                elif min_val == max_val:
                    param_data['mapper_low'], param_data['mapper_high'] = min_val - 1, max_val + 1
                else:
                    param_data['mapper_low'], param_data['mapper_high'] = min_val, max_val
                
                # Store parameter data
                position_param_data[param] = param_data
            
            # Store common data for this position
            times_ms = pd.to_datetime(times_dt).astype('int64') // 10**6
            #times_ms = (times_dt - np.datetime64('1970-01-01T00:00:00Z')) / np.timedelta64(1, 'ms')
            position_param_data['common'] = {
                'times_ms': times_ms,
                'freq_indices': np.arange(n_freqs),
                'selected_frequencies': selected_frequencies,
                'frequency_labels_str': [(str(int(f)) if f >= 10 else f"{f:.1f}") + " Hz" for f in selected_frequencies],
                'n_freqs': n_freqs,
                'n_times': n_times,
                'y_range': (-0.5, n_freqs - 0.5),
                'x_range': (times_ms[0], times_ms[-1]) if n_times > 0 else (0, 1),
                'dw': times_ms[-1] - times_ms[0] if n_times > 1 else 60000,
                'dh': n_freqs
            }
            
            # Add to all param data
            all_param_data[position] = position_param_data
        
        # --- Create dropdown callback ---
        dropdown_callback_code = """
            const selected_param = cb_obj.value;
            const all_data = all_positions_spectral_data_js;
            const holder = selected_param_holder_js;
            
            console.log('Dropdown changed to: ' + selected_param);
            
            try {
                // Update selected parameter in holder
                holder.data['param'] = [selected_param];
                holder.change.emit();
                
                // Update all spectrograms
                for (const position in spectral_figures_js) {
                    const position_data = all_data[position];
                    if (!position_data || !position_data[selected_param]) {
                        console.log(`No data for ${selected_param} in position ${position}, skipping`);
                        continue;
                    }
                    
                    const figure = spectral_figures_js[position];
                    const source = spectral_sources_js[position];
                    const param_data = position_data[selected_param];
                    const common = position_data['common'];
                    
                    // Update source data
                    source.data['image'] = [param_data['image_data']];
                    source.change.emit();
                    
                    // Find color mapper in figure
                    const color_mapper = figure.select_one({'type': 'LinearColorMapper'});
                    if (color_mapper) {
                        color_mapper.low = param_data['mapper_low'];
                        color_mapper.high = param_data['mapper_high'];
                    }
                    
                    // Update color bar title
                    const color_bar = figure.right.filter(model => model.toString().includes('ColorBar'))[0];
                    if (color_bar) {
                        color_bar.title = `${selected_param} (dB)`;
                    }
                    
                    // Update figure title
                    figure.title.text = figure.title.text.replace(/Spectral Data/, `Spectral Data (${selected_param})`);
                }
                
                // Clear hover info and bar chart
                bar_source.data['levels'] = [];
                bar_source.data['frequency_labels'] = [];
                bar_x_range.factors = [];
                bar_source.change.emit();
                
            } catch (error) {
                console.error('Error in dropdown callback:', error);
                console.error('Error details:', error.message, error.stack);
            }
        """
        
        # Attach callback to dropdown
        dropdown_args = {
            'spectral_figures_js': spectral_figures,
            'spectral_sources_js': spectral_sources,
            'all_positions_spectral_data_js': all_param_data,
            'selected_param_holder_js': selected_param_holder,
            'bar_source': freq_bar_source,
            'bar_x_range': freq_bar_x_range
        }
        
        param_select.js_on_change('value', CustomJS(args=dropdown_args, code=dropdown_callback_code))
        
        # --- Add dropdown to layout ---
        controls = row(param_select)
        layout.children.append(controls)
        
    # --- Checkbox Group (after processing all positions) ---

    if not chart_details:
        logger.warning("No charts were created. Cannot proceed with layout.")
        layout.children.append(Div(text="<h3 style='color:red;'>Error: No data could be visualized.</h3>"))
        return layout, [], [], {}, [], [], None, None, None, None, None, {} # Return empty structures

    # use details for checkbox labels and initial state
    chart_labels = [details['chart'].title.text for details in chart_details]
    checkbox = CheckboxGroup(labels=chart_labels, active=list(range(len(chart_details))))

    # JS callbacks needs access to the *charts* in the current order
    checkbox_callback = CustomJS(args={'charts': [d['chart'] for d in chart_details]}, code ="""
                                 const active_indices = cb_obj.active;
                                 charts.forEach((chart, i) => {
                                    chart.visible = active_indices.includes(i);
                                 });
                                 """)
    
    checkbox.js_on_change('active', checkbox_callback)
    
    chart_controls = row(checkbox, sizing_mode="stretch_width")
    layout.children.append(chart_controls)
    
    # --- Range Tool Selector ---
    # Ensure the layout has at least one chart for range selector
    if not time_series_charts:
        logger.warning("No time series charts available for range selector.")
    else:
        first_chart = time_series_charts[0] # Use first chart as reference
        first_source_key = first_chart.name
        first_source = all_sources.get(first_source_key)
        
        if first_source:
            range_selector = create_range_selector(
                first_chart, 
                first_source,
                height=CHART_SETTINGS["range_selector_height"],
                width=CHART_SETTINGS["range_selector_width"]
            )
            range_selector.name = "range_selector"
            layout.children.append(range_selector)
            
            # Add to charts for vertical lines (optional)
            time_series_charts.append(range_selector)
        else:
            logger.error(f"Could not find source for chart {first_source_key}")
    
    # --- Range Synchronization ---
    if CHART_SETTINGS["sync_charts"] and len(time_series_charts) > 1:
        link_x_ranges(time_series_charts)
        logger.info(f"Linked x-ranges of {len(time_series_charts)} charts")
    
    # --- Add Vertical Lines and Hover ---
    charts_for_interaction = time_series_charts # May exclude some in the future
    
    charts_with_lines, all_click_lines, all_labels = add_vertical_line_and_hover(
        charts_for_interaction, 
        all_sources,
        freq_bar_source,
        freq_bar_x_range,
        selected_param_holder,
        all_param_data
    )
    logger.info(f"Added vertical lines/hover to {len(charts_with_lines)} charts")

    # --- Add charts to layout ---
    # First, check if chart_order is provided and valid
    if chart_order is not None and chart_order:
        # Handle chart reordering logic (existing logic)
        # ... (existing reordering code)
        # Replace this comment with the actual reordering code
        ordered_details = []
        # Convert order to 0-indexed if needed 
        
        # Handling different chart_order formats
        if all(isinstance(x, str) for x in chart_order):
            # Order by titles
            title_to_detail = {d['chart'].title.text: d for d in chart_details}
            for title in chart_order:
                if title in title_to_detail:
                    ordered_details.append(title_to_detail[title])
            # Add remaining charts not specified in order
            for d in chart_details:
                if d['chart'].title.text not in chart_order:
                    ordered_details.append(d)
        
        elif all(isinstance(x, int) for x in chart_order):
            # Order by indices
            valid_indices = [i for i in chart_order if 0 <= i < len(chart_details)]
            for i in valid_indices:
                ordered_details.append(chart_details[i])
            # Add remaining charts not specified in order
            used_indices = set(valid_indices)
            for i, d in enumerate(chart_details):
                if i not in used_indices:
                    ordered_details.append(d)
        
        final_ordered_charts = [d['chart'] for d in ordered_details]
    else:
        # Default order
        final_ordered_charts = [d['chart'] for d in chart_details]


    # Append ordered charts to layout
    for chart in final_ordered_charts:
        layout.children.append(chart)

    # --- Add shared components for spectrograms ---
    if hover_info_div and spectral_figures:
        layout.children.append(hover_info_div)
    
    if freq_bar_chart and spectral_figures:
        layout.children.append(freq_bar_chart)

    # Return all necessary components
    # charts_for_js_init needs to include all charts involved in interactions (lines, labels, tap)
    charts_for_js_init = charts_for_interaction + [freq_bar_chart] if freq_bar_chart else charts_for_interaction
    
    # Add spectrogram-specific data to sources
    if all_param_data:
        all_sources['all_positions_spectral_data'] = all_param_data
    
    # Return additional components needed for JS initialization
    return layout, final_ordered_charts, charts_for_js_init, all_sources, all_click_lines, all_labels, freq_bar_source, freq_bar_x_range, hover_info_div, param_select, selected_param_holder, spectral_figures

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
    media_path = r"G:\Shared drives\Venta\Jobs\5772 Field Farm, Somerford Keynes\5772 Surveys\5772-1"
    audio_handler = AudioPlaybackHandler(media_path)
    playback_source = ColumnDataSource(data={'current_time': [0]}, name='playback_source')


    # --- Visualizations ---
    layout, all_charts, charts_for_js_init, all_sources, all_click_lines, all_labels, freq_bar_source, freq_bar_x_range, hover_info_div, param_select, selected_param_holder, spectral_figures = create_visualizations(position_data)

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
        pause_button,
        freq_bar_source,
        freq_bar_x_range,
        hover_info_div,
        param_select,
        selected_param_holder,
        spectral_figures,
        all_sources.get('all_positions_spectral_data')
    )

    # Find the first source with a 'Datetime' key for start time calculation
    start_time = None
    for source_key in all_sources:
        source = all_sources[source_key]
        if source.data and 'Datetime' in source.data and len(source.data['Datetime']) > 0:
            start_time = pd.Timestamp(min(source.data['Datetime']))
            break
    
    if start_time is None:
        # Fallback to current time if no valid source found
        start_time = pd.Timestamp.now()
        logger.warning("No valid source with Datetime found for start_time, using current time")

    # --- Python Tap Callback --- 
    #def tap_callback(event):
    #    selected_time_ms = event.x
    #    timestamp = datetime.datetime.fromtimestamp(selected_time_ms / 1000)
    #    logger.debug(f'Tap Event: Seeking audio to {timestamp}')
    #    # Use the lambda with the next_tick_callback inside update_playback_position
    #    if audio_handler.is_playing: # Seek if already playing
    #    audio_handler.play(timestamp, lambda pos: update_playback_position(pos, start_time, playback_source))
        # Note: JS handleTap will have already updated playback_source.data

    # Attach Python tap callback (if still needed for seek-on-tap)
    #for chart in charts_for_js_init: # Use the list corresponding to interactions
    #    if chart.name != 'range_selector':
    #        chart.on_event(Tap, tap_callback)

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

    const currentData = playback_source.data;
    if (!currentData || !currentData['current_time'] || currentData['current_time'].length === 0) {
        console.log('JS playback_callback: Invalid data in playback_source.');
        return;
    }
    const currentTime = currentData['current_time'][0];
    // Check if functions AND models are ready (BE VERY THOROUGH)
    const functionsReady = typeof window.updateTapLinePositions === 'function' && typeof window.findClosestDateIndex === 'function';
    const modelsReady = window.chartRefs && window.clickLineModels && window.labelModels &&
                       window.chartRefs.length > 0 && window.clickLineModels.length > 0 && window.labelModels.length > 0;

    if (functionsReady && modelsReady) {
        try { // Add try-catch within JS callback for safety
             window.updateTapLinePositions(currentTime, window.chartRefs, window.clickLineModels, window.labelModels);
        } catch (e) {
             console.error("JS playback_callback: Error calling updateTapLinePositions:", e);
        }
    } else {
        console.warn('JS functions or global models not ready for playback update.');
        // Log detailed status
        console.log('typeof window.updateTapLinePositions:', typeof window.updateTapLinePositions);
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

    # Playback speed control
    speed_options = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0]
    current_speed_index = 2  # Start at 1.0x (normal speed)
    
    speed_button = Button(
        label=f"🚀 Speed: {speed_options[current_speed_index]}x", 
        button_type="primary", 
        name="speed_button"
    )
    
    def speed_button_click(event):
        nonlocal current_speed_index
        # Cycle to next speed option
        current_speed_index = (current_speed_index + 1) % len(speed_options)
        new_rate = speed_options[current_speed_index]
        
        # Update button label
        speed_button.label = f"🚀 Speed: {new_rate}x"
        
        # Set the new playback rate
        if audio_handler.is_playing:
            audio_handler.set_playback_rate(new_rate)
    
    speed_button.on_click(speed_button_click)

    controls = row(play_button, pause_button, stop_button, speed_button)
    layout.children.append(controls)
    
    doc.add_root(playback_source)
    doc.add_root(layout)

#%% Main Function
def main():
    """
    Main function to run the noise survey analysis.
    
    Returns:
    tuple: (layout, position_data) - The created Bokeh layout and the loaded data dictionary
    """
    # Load data using the new data sources configuration
    position_data = load_and_process_data()
    
    # Print data overview
    examine_data(position_data)
    
    # Synchronize time ranges if configured
    if CHART_SETTINGS["sync_charts"]:
        position_data = synchronize_time_range(position_data)
    
    # Create visualizations
    layout, all_charts, charts_for_js_init, all_sources, all_click_lines, all_labels, freq_bar_source, freq_bar_x_range, hover_info_div, param_select, selected_param_holder, spectral_figures = create_visualizations(position_data)
    
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
    position_data = load_and_process_data()
    
    if CHART_SETTINGS["sync_charts"]:
        position_data = synchronize_time_range(position_data)
    
    create_app(curdoc(), position_data)

# For Bokeh server, this portion runs when the module is loaded by the server
if not __name__.startswith('bokeh_app'):
    # This code doesn't run when just importing the module
    pass
else:
    # This runs when the module is loaded by Bokeh server
    run_bokeh_app() 