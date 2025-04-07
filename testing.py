#%%
#initialization

import logging
import pandas as pd
import numpy as np
from bokeh.plotting import figure
from bokeh.models import (
    ColumnDataSource, LinearColorMapper, ColorBar, HoverTool, CustomJS, Div,
    DatetimeTickFormatter, DatetimeTicker, Range1d, NumeralTickFormatter, Select, FactorRange, LabelSet
    # Remove rect-specific things if not used elsewhere
)
from bokeh.io import show
from bokeh.layouts import column, row
try:
    from noise_survey_analysis.core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS
    from noise_survey_analysis.core.data_loaders import load_and_process_data, examine_data, get_default_data_sources

except ImportError:
    print("Failed to import configuration from core.config")
    raise
logger = logging.getLogger(__name__)


#%%

def make_image_spectrogram(param, df, bar_source, bar_x_range, title=-1, height=None, colormap=None, font_size='9pt'):
    """
    Create a high-performance spectrogram using the `image` glyph.
    Hover information is displayed in a separate Div updated via CustomJS.

    Parameters:
    param (str): Base parameter name (e.g., 'LZeq').
    df (pd.DataFrame): DataFrame with frequency data. Must contain 'Datetime'.
    title (str or int): Chart title. Defaults to parameter name.
    height (int, optional): Chart height. Defaults to config.
    colormap (str, optional): Colormap name. Defaults to config.
    font_size (str): Font size for axis labels.

    Returns:
    tuple: (bokeh.plotting.figure, bokeh.models.ColumnDataSource, bokeh.models.Div)
           Returns (None, None, None) if creation fails. The Div is for hover info.
    """
    height = height if height is not None else CHART_SETTINGS['spectrogram_height']
    width = CHART_SETTINGS['spectrogram_width']
    lower_band_idx = CHART_SETTINGS['lower_freq_band']
    upper_band_idx = CHART_SETTINGS['upper_freq_band'] # Can be negative
    colormap = colormap if colormap is not None else CHART_SETTINGS['colormap']
    tools = CHART_SETTINGS['tools'] # Keep base tools
    active_drag = CHART_SETTINGS['active_drag']
    active_scroll = CHART_SETTINGS['active_scroll']

    # --- Input Validation ---
    if df is None or df.empty:
        logger.warning(f"Empty DataFrame provided for image spectrogram '{param}'")
        return None, None, None
    if 'Datetime' not in df.columns:
         logger.error(f"Missing 'Datetime' column for image spectrogram '{param}'")
         return None, None, None
    if not pd.api.types.is_datetime64_any_dtype(df['Datetime']):
        df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')
        df.dropna(subset=['Datetime'], inplace=True)
        if df.empty: return None, None, None # Bail if no valid dates

    # --- Find and Sort Frequency Columns ---
    freq_cols_found = []
    all_frequencies = []
    for col in df.columns:
         if col.startswith(param + '_') and col.split('_')[-1].replace('.', '', 1).isdigit():
              try:
                   freq = float(col.split('_')[-1])
                   freq_cols_found.append(col)
                   all_frequencies.append(freq)
              except (ValueError, IndexError): continue

    if not freq_cols_found:
        logger.error(f"No frequency columns found for parameter '{param}' in image spectrogram.")
        return None, None, None

    sorted_indices = np.argsort(all_frequencies)
    frequencies = np.array(all_frequencies)[sorted_indices]
    freq_columns = np.array(freq_cols_found)[sorted_indices]

    # --- Apply Band Slicing ---
    if upper_band_idx is None or upper_band_idx == -1: upper_band_idx = len(frequencies)
    selected_frequencies = frequencies[lower_band_idx:upper_band_idx]
    selected_freq_columns = freq_columns[lower_band_idx:upper_band_idx]

    if len(selected_frequencies) == 0:
        logger.error(f"No frequencies after band slicing for image spectrogram '{param}'.")
        return None, None, None
    n_freqs = len(selected_frequencies)
    logger.info(f"Using {n_freqs} frequencies for '{param}' image spectrogram.")

    frequency_labels_str = [(str(int(f)) if f >= 10 else f"{f:.1f}") + " Hz" for f in selected_frequencies]

    # --- Prepare Data for `image` Glyph ---
    levels_matrix = df[selected_freq_columns].values # Shape: (n_times, n_freqs)
    times_dt = df['Datetime'].values
    n_times = len(times_dt)

    if n_times == 0:
        logger.warning(f"No time points for image spectrogram '{param}'")
        return None, None, None

    # Convert times to milliseconds epoch (numeric) for x coordinate
    times_ms = (times_dt - np.datetime64('1970-01-01T00:00:00Z')) / np.timedelta64(1, 'ms')

    # Y coordinate: Use simple linear indices [0, 1, ..., n_freqs-1]
    freq_indices = np.arange(n_freqs)

    # Handle NaNs in the data matrix: replace with a value outside the range (e.g., low)
    # or use image_rgba later. Replacing is simpler for image.
    valid_levels = levels_matrix[~np.isnan(levels_matrix)]
    if len(valid_levels) > 0:
        min_val = np.min(valid_levels)
        max_val = np.max(valid_levels)
        nan_replace_val = min_val - 20 # Choose a value clearly outside range
    else: # All NaNs?
        min_val, max_val = 0, 100
        nan_replace_val = -100
    levels_matrix = np.nan_to_num(levels_matrix, nan=nan_replace_val)

    # **Important for `image`:** The data array needs to match the axis order.
    # Bokeh `image` expects the array oriented as `(rows, cols)`, where rows correspond
    # to the y-axis and cols to the x-axis.
    # Our `levels_matrix` is currently (n_times, n_freqs).
    # We need to transpose it to (n_freqs, n_times) for plotting.
    levels_matrix_transposed = levels_matrix.T # Shape: (n_freqs, n_times)

    # --- Create Source ---
    # Source ONLY holds the 2D image data. Other arrays passed via JS args.
    source = ColumnDataSource(data={'image': [levels_matrix_transposed]}) # Pass as a list containing the 2D array

    # --- Color Mapper ---
    # Adjust range slightly if all NaNs were replaced
    if len(valid_levels) == 0:
        mapper_low, mapper_high = min_val, max_val
    elif min_val == max_val: # Handle single value case
         mapper_low, mapper_high = min_val - 1, max_val + 1
    else:
         mapper_low, mapper_high = min_val, max_val
    color_mapper = LinearColorMapper(palette=colormap, low=mapper_low, high=mapper_high, nan_color='#00000000') # Transparent NaN

    # --- Create Figure ---
    if title == -1: title = f"Spectrogram ({param})"

    # Define explicit ranges for image positioning
    x_range = (times_ms[0], times_ms[-1]) if n_times > 0 else (0, 1)
    # Y range based on linear indices centered around integers
    y_range = (-0.5, n_freqs - 0.5)

    spec = figure(
        title=title,
        x_axis_type="datetime", # X axis remains datetime
        y_axis_type="linear",   # Y axis uses linear indices
        height=height,
        width=width,
        tools=tools, # Base tools
        active_drag=active_drag,
        active_scroll=active_scroll,
        x_range=x_range, # Use numeric ms range here, Bokeh converts for axis
        y_range=y_range, # Use linear index range
    )

    # --- Add `image` Glyph ---
    # `x, y` are bottom-left corner, `dw, dh` are total width/height
    image_glyph = spec.image(
        image='image', # Key in source
        x=times_ms[0], # Start time in ms
        y=-0.5,        # Start at the bottom edge of the first index bin
        dw=times_ms[-1] - times_ms[0] if n_times > 1 else 60000, # Total time duration in ms
        dh=n_freqs,    # Total height in index units (N bands span N units)
        source=source,
        color_mapper=color_mapper,
        level="image"
    )

    # --- Configure Axes ---
    spec.xaxis.formatter = DatetimeTickFormatter(days="%d/%m/%y %H:%M", hours="%H:%M:%S")
    spec.xaxis.ticker = DatetimeTicker(desired_num_ticks=10)
    spec.yaxis.axis_label = "Frequency (Hz)"
    spec.xaxis.axis_label = "Time"

    # **Crucial:** Override Y-axis labels to show frequencies
    spec.yaxis.ticker = freq_indices # Ticks at 0, 1, 2...
    spec.yaxis.major_label_overrides = {
        i: str(int(freq)) if freq >= 10 else str(freq) # Format freq labels nicely
        for i, freq in enumerate(selected_frequencies)
    }
    spec.yaxis.major_label_text_font_size = font_size
    spec.yaxis.axis_label_text_font_size = font_size
    spec.ygrid.visible = False
    spec.xgrid.visible = False
    # --- Color Bar ---
    color_bar = ColorBar(
        color_mapper=color_mapper, title=f'{param} (dB)', # ... other properties ...
        major_label_text_font_size=font_size, title_text_font_size=font_size
    )
    spec.add_layout(color_bar, 'right')

    # --- Hover Setup ---
    # 1. Create a Div for hover info display with proper centering
    hover_info_div = Div(
        text="Hover over spectrogram for details",
        width=width,
        height=30,
        name="spectrogram_hover_div",
        styles={'text-align': 'center', 'margin': '0 auto', 'display': 'block'}
    )

    # 2. Define CustomJS callback code
    # Note: levels_matrix needs to be the ORIGINAL (non-transposed) one if indexing is time, freq
    hover_js_code = """
        const {x: gx, y: gy} = cb_data.geometry; // Hover coords (ms epoch, linear index)
        const div = hover_div; // The Div model passed in args
        const bar_source_js = bar_source;       // Bar chart source
        const bar_x_range_js = bar_x_range;     // Bar chart x-range (FactorRange)

        // Data arrays from Python
        const times = times_array;
        const freqs = freqs_array; // Actual frequency numbers
        const freq_labels_str = freq_labels_array; // Frequency strings for labels
        const levels_flat = levels_flat_array; // FLATTENED levels matrix (original data w/ NaN)

        const n_times = times.length;
        const n_freqs = freqs.length;
        const x_start = fig_x_range.start;
        const x_end = fig_x_range.end;

        // Bar chart data object
        const bar_data = bar_source_js.data;

        // Check if hover is within the main plot area (image bounds)
        const is_inside = !(gx < x_start || gx > x_end || gy < -0.5 || gy > n_freqs - 0.5 || n_times === 0 || n_freqs === 0);

        if (is_inside) {
            // --- Calculate Indices ---
            let time_idx = -1;
            let min_time_diff = Infinity;
            // Find closest time_idx (use binary search if n_times is large and sorted)
             for (let i = 0; i < n_times; i++) {
                const diff = Math.abs(times[i] - gx);
                if (diff < min_time_diff) {
                    min_time_diff = diff;
                    time_idx = i;
                } else if (diff > min_time_diff && i > 0) {
                    break; // Since times are sorted, diff will only increase
                }
            }
            if (time_idx === -1) time_idx = 0; // Fallback

            const freq_idx = Math.max(0, Math.min(n_freqs - 1, Math.floor(gy + 0.5)));

            // --- Lookup Data for Div ---
            const time_val_ms = times[time_idx];
            const freq_val = freqs[freq_idx];
            const flat_index_hover = time_idx * n_freqs + freq_idx;
            const level_val_hover = levels_flat[flat_index_hover];

            // --- Format for Div ---
            const time_str = new Date(time_val_ms).toLocaleString();
            const freq_str = freq_labels_str[freq_idx]; // Use pre-formatted label
            let level_str_hover = "";
            if (level_val_hover === null || level_val_hover === undefined || Number.isNaN(level_val_hover)) {
                 level_str_hover = "N/A";
            } else {
                 level_str_hover = level_val_hover.toFixed(1) + " dB";
            }
            div.text = `<b>Time:</b> ${time_str} | <b>Freq:</b> ${freq_str} | <b>Level:</b> ${level_str_hover}`;

            // --- Update Bar Chart ---
            const start_index_slice = time_idx * n_freqs;
            const end_index_slice = start_index_slice + n_freqs;
            let levels_slice = levels_flat.slice(start_index_slice, end_index_slice);

            // Check before updating
            if (levels_slice.length !== freq_labels_str.length) {
                console.error("Mismatch between levels_slice and freq_labels_str lengths!");
            }

            levels_slice = levels_slice.map(level => (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);

            // Update bar chart source data
            bar_data['levels'] = levels_slice;
            bar_data['frequency_labels'] = freq_labels_str;

            // Update bar chart x-axis factors (**CRUCIAL**)
            bar_x_range_js.factors = freq_labels_str;

            // Emit change to update the bar chart plot
            bar_source_js.change.emit();


        } else {

            // ... (check clearing logic too) ...

            bar_source_js.change.emit();
        }
        """

    # 3. Create CustomJS callback
    hover_callback = CustomJS(args=dict(
        hover_div=hover_info_div,
        bar_source = bar_source,
        bar_x_range = bar_x_range,
        times_array=times_ms, # Pass numeric times
        freqs_array=selected_frequencies, # Pass original frequencies
        freq_labels_array=frequency_labels_str, # Pass original frequencies
        levels_matrix=levels_matrix, # Pass original (non-transposed) levels matrix
        levels_flat_array=levels_matrix.flatten(),
        fig_x_range=spec.x_range # Pass figure range for bounds checking
        # fig_y_range=spec.y_range # Y range is simpler: -0.5 to n_freqs - 0.5
    ), code=hover_js_code)

    # 4. Create HoverTool and attach callback
    hover_tool = HoverTool(
        tooltips=None, # Disable default tooltips
        callback=hover_callback,
        renderers=[image_glyph], # Important: Target the image glyph
        mode='mouse' # Point hover, not vline
    )
    spec.add_tools(hover_tool)

    # --- Return figure, source, and the Div for layout ---
    return spec, source, hover_info_div

def create_frequency_bar_chart(title="Frequency Slice", height=None, width=None):
    """
    Creates an empty bar chart structure for displaying frequency levels at a specific time.
    The data source will be updated by JavaScript interactions.

    Parameters:
    title (str): Chart title.
    height (int, optional): Chart height. Defaults to config.
    width (int, optional): Chart width. Defaults to config.

    Returns:
    tuple: (bokeh.plotting.figure, bokeh.models.ColumnDataSource)
    """
    height = height if height is not None else CHART_SETTINGS['high_freq_height'] # Use a height setting
    width = width if width is not None else CHART_SETTINGS['high_freq_width']
    auto_y = CHART_SETTINGS['auto_y_range']
    y_range_cfg = CHART_SETTINGS['y_range']

    # Initial empty data structure
    # 'frequency_labels' will be the actual string labels (e.g., "31.5 Hz")
    # 'levels' will be the dB values
    initial_data = {'frequency_labels': ['25 Hz', '31 Hz', '40 Hz', '50 Hz', '63 Hz', '80 Hz', '100 Hz', '125 Hz', '160 Hz', '200 Hz', '250 Hz', '315 Hz', '400 Hz', '500 Hz', '630 Hz', '800 Hz', '1000 Hz', '1250 Hz', '1600 Hz', '2000 Hz'], 
    'levels': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]}
    source = ColumnDataSource(data=initial_data, name="frequency_bar_source") # Give source a name
    x_range = FactorRange(factors=initial_data['frequency_labels'])
    # Create figure with a categorical x-range (initially empty)
    p = figure(
        title=title,
        height=height,
        width=width,
        x_range=initial_data['frequency_labels'], # Use the labels for x-range categories
        x_axis_label='Frequency Band (Hz)',
        y_axis_label='Level (dB)',
        tools="pan,wheel_zoom,box_zoom,reset,save" # Standard tools
    )

    # Add vertical bars linked to the source
    p.vbar(
        x='frequency_labels',
        top='levels',
        width=0.8, # Adjust bar width as needed
        source=source,
        fill_color="#6baed6",
        line_color="white"
    )

    # Add labels above bars
    labels = LabelSet(
        x='frequency_labels',
        y='levels',
        text='levels',
        level='glyph',
        x_offset=0,
        y_offset=5,
        source=source,
        text_align='center',
        text_font_size='8pt',
        text_color='black',
        text_baseline='bottom'
    )
    p.add_layout(labels)

    # Configure y-range
    if not auto_y:
        try:
            p.y_range = Range1d(*y_range_cfg)
        except:
             logger.warning(f"Invalid y_range configuration for Freq Bar: {y_range_cfg}. Using auto-range.")

    # Add hover tool
    hover = HoverTool(tooltips=[
        ("Frequency", "@frequency_labels"),
        ("Level", "@levels{0.1f} dB")
    ])
    p.add_tools(hover)

    # Style the chart
    p.xaxis.major_label_orientation = 0.8 # Radians for slight rotation if needed, or "vertical"
    p.grid.grid_line_alpha = 0.3
    p.xaxis.axis_label_text_font_size = "10pt"
    p.yaxis.axis_label_text_font_size = "10pt"

    return p, source, x_range


# %%

#%%
# Load data using the new data sources configuration
position_data = load_and_process_data()
examine_data(position_data)
spec_df = position_data['SE']['spectral']


#%%
#plot
params_to_plot = ['LZeq', 'LZF90']
font_size = '9pt'
height = CHART_SETTINGS['spectrogram_height']
width = CHART_SETTINGS['spectrogram_width']
lower_band_idx = CHART_SETTINGS['lower_freq_band']
upper_band_idx = CHART_SETTINGS['upper_freq_band']
colormap = CHART_SETTINGS['colormap']
tools = CHART_SETTINGS['tools']
active_drag = CHART_SETTINGS['active_drag']
active_scroll = CHART_SETTINGS['active_scroll']

# --- Pre-calculate data for all parameters ---
all_param_data = {}
common_data = {}

for param in params_to_plot:
    logger.info(f"Processing {param} data...")
    param_data = {}

    freq_cols_found = []
    all_frequencies = []

    for col in spec_df.columns:
        if col.startswith(param + '_') and col.split('_')[-1].replace('.', '', 1).isdigit():
            try:
                frequ = float(col.split('_')[-1])
                freq_cols_found.append(col)
                all_frequencies.append(frequ)
            except (ValueError, IndexError): continue

    if not freq_cols_found:
        logger.warning(f"No frequency columns found for '{param}'. Skipping...")
        continue

    sorted_indices = np.argsort(all_frequencies)
    frequencies = np.array(all_frequencies)[sorted_indices]
    freq_columns = np.array(freq_cols_found)[sorted_indices]

    # Apply band slicing
    current_upper_band_idx = upper_band_idx
    if upper_band_idx is None or upper_band_idx == -1 or upper_band_idx > len(frequencies):
        current_upper_band_idx = len(frequencies)
    selected_frequencies = frequencies[lower_band_idx:current_upper_band_idx]
    selected_freq_columns = freq_columns[lower_band_idx:current_upper_band_idx]

    if len(selected_frequencies) == 0:
        logger.warning(f"No frequencies after band slicing for '{param}'. Skipping...")
        continue

    n_freqs = len(selected_frequencies)
    
    #prepare Data for 'image' Glyph
    levels_matrix = spec_df[selected_freq_columns].values # Shape: (n_times, n_freqs)
    times_dt = spec_df['Datetime'].values
    n_times = len(times_dt)

    if n_times == 0:
        logger.warning(f"No time points for '{param}'. Skipping...")
        continue

    # Store flattened levels with NaNs for hover
    param_data['levels_flat_nan'] = levels_matrix.flatten()

    # Handle NaNs for image display (replace with value outside range)
    valid_levels = levels_matrix[~np.isnan(levels_matrix)]
    if len(valid_levels) > 0:
        min_val, max_val = np.nanmin(valid_levels), np.nanmax(valid_levels)
        nan_replace_val = min_val - 20
    else:
        min_val, max_val = 0, 100
        nan_replace_val = -100
    levels_matrix_filled = np.nan_to_num(levels_matrix, nan=nan_replace_val)

    # Transpose levels matrix for Bokeh image
    param_data['image_data'] = levels_matrix_filled.T # Shape: (n_freqs, n_times)

    # Store color mapper range for this parameter
    if len(valid_levels) > 0:
        param_data['mapper_low'], param_data['mapper_high'] = min_val, max_val
    elif min_val == max_val:
        param_data['mapper_low'], param_data['mapper_high'] = min_val - 1, max_val + 1
    else:
        param_data['mapper_low'], param_data['mapper_high'] = min_val, max_val
    
    all_param_data[param] = param_data

    # Store common data only once (assuming times/freqs are identical)
    if not common_data:
        common_data['times_ms'] = (times_dt - np.datetime64('1970-01-01T00:00:00Z')) / np.timedelta64(1, 'ms')
        common_data['freq_indices'] = np.arange(n_freqs)
        common_data['selected_frequencies'] = selected_frequencies
        common_data['frequency_labels_str'] = [(str(int(f)) if f >= 10 else f"{f:.1f}") + " Hz" for f in selected_frequencies]
        common_data['n_freqs'] = n_freqs
        common_data['n_times'] = n_times
        common_data['y_range'] = (-0.5, n_freqs - 0.5)
        common_data['x_range'] = (common_data['times_ms'][0], common_data['times_ms'][-1]) if n_times > 0 else (0, 1)
        common_data['dw'] = common_data['times_ms'][-1] - common_data['times_ms'][0] if n_times > 1 else 60000
        common_data['dh'] = n_freqs

if not all_param_data:
    raise ValueError("No valid parameter data could be processed")
if not common_data:
    raise ValueError("Could not extract common time/freq data from processed parameters")

# -- Initial Parameter ---
initial_param = params_to_plot[0]

# -- Create Shared Bar Chart Components ---
bar_chart, bar_source, bar_x_range = create_frequency_bar_chart(
    width=width,
)

# --- Create Single Spectrogram Figure ---
spec = figure(
    # title set dynamically later
    x_axis_type="datetime",
    y_axis_type="linear",
    height=height,
    width=width,
    tools=tools,
    active_drag=active_drag,
    active_scroll=active_scroll,
    x_range=common_data['x_range'],
    y_range=common_data['y_range'],
)

# Spectrogram Source (initially for first param)
spec_source = ColumnDataSource(data={'image': [all_param_data[initial_param]['image_data']]}) # Note: data needs list wrapper
color_mapper = LinearColorMapper(
    palette=colormap,
    low=all_param_data[initial_param]['mapper_low'],
    high=all_param_data[initial_param]['mapper_high'],
    nan_color='#00000000' # Transparent NaN
)

# Add Image Glyph
image_glyph = spec.image(
    image='image',
    x=common_data['times_ms'][0],
    y=-0.5,
    dw=common_data['dw'],
    dh=common_data['dh'],
    source=spec_source,
    color_mapper=color_mapper,
    level='image'
)
# Configure Axes (using common data)
spec.xaxis.formatter = DatetimeTickFormatter(days="%d/%m/%y %H:%M", hours="%H:%M:%S")
spec.xaxis.ticker = DatetimeTicker(desired_num_ticks=10)
spec.yaxis.axis_label = "Frequency (Hz)"
spec.xaxis.axis_label = "Time"
spec.yaxis.ticker = common_data['freq_indices']
spec.yaxis.major_label_overrides = {
    i: label.replace(" Hz", "") # Shorter labels for axis
    for i, label in enumerate(common_data['frequency_labels_str'])
}
spec.yaxis.major_label_text_font_size = font_size
spec.yaxis.axis_label_text_font_size = font_size
spec.ygrid.visible = False
spec.xgrid.visible = False

# Color Bar (linked to the single mapper)
color_bar = ColorBar(
    color_mapper=color_mapper,
    # title set dynamically later
    major_label_text_font_size=font_size,
    title_text_font_size=font_size
)
spec.add_layout(color_bar, 'right')

# --- Single Hover Info Div ---
hover_info_div = Div(
    text="Hover over spectrogram for details",
    width=width, height=30, name="spectrogram_hover_div",
    styles={'text-align': 'center', 'margin': '0 auto', 'display': 'block'}
)

# --- shared data holder for dropdown callback ---
selected_param_data = {'param': [initial_param]}
selected_param_holder = ColumnDataSource(data=selected_param_data)

# --- Unified Hover JS Callback ---
hover_js_code = """
    const holder = selected_param_holder_js;
    const all_data = all_param_data_js;
    const current_param = holder.data['param'][0];
    const levels_flat = all_data[current_param]['levels_flat_nan'];

    const {x: gx, y: gy} = cb_data.geometry;
    const div = hover_div;
    const bar_source_js = bar_source;
    const bar_x_range_js = bar_x_range;


    // Data arrays from Python args - some fixed, some updated by dropdown
    const times = times_array;
    const freqs = freqs_array;
    const freq_labels_str = freq_labels_array;

    const n_times = times.length;
    const n_freqs = freqs.length;
    const x_start = fig_x_range.start;
    const x_end = fig_x_range.end;

    const bar_data = bar_source_js.data;

    const is_inside = !(gx < x_start || gx > x_end || gy < -0.5 || gy > n_freqs - 0.5 || n_times === 0 || n_freqs === 0);

    if (is_inside) {
        // --- Calculate Indices ---
        let time_idx = -1;
        let min_time_diff = Infinity;
        for (let i = 0; i < n_times; i++) {
            const diff = Math.abs(times[i] - gx);
            if (diff < min_time_diff) {
                min_time_diff = diff;
                time_idx = i;
            } else if (diff > min_time_diff && i > 0) {
                break;
            }
        }
        if (time_idx === -1) time_idx = 0;

        const freq_idx = Math.max(0, Math.min(n_freqs - 1, Math.floor(gy + 0.5)));

        // --- Lookup Data for Div ---
        const time_val_ms = times[time_idx];
        const freq_val = freqs[freq_idx];
        const flat_index_hover = time_idx * n_freqs + freq_idx;
        const level_val_hover = levels_flat[flat_index_hover];

        // --- Format for Div ---
        const time_str = new Date(time_val_ms).toLocaleString();
        const freq_str = freq_labels_str[freq_idx];
        let level_str_hover = "";
        if (level_val_hover === null || level_val_hover === undefined || Number.isNaN(level_val_hover)) {
            level_str_hover = "N/A";
        } else {
            level_str_hover = level_val_hover.toFixed(1) + " dB";
        }

        div.text = `<b>Param:</b> ${current_param} | <b>Time:</b> ${time_str} | <b>Freq:</b> ${freq_str} | <b>Level:</b> ${level_str_hover}`;

        // --- Update Bar Chart ---
        const start_index_slice = time_idx * n_freqs;
        const end_index_slice = start_index_slice + n_freqs;
        let raw_levels_slice = levels_flat.slice(start_index_slice, end_index_slice);

        let levels_slice = raw_levels_slice.map(level => (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);

        bar_data['levels'] = levels_slice;
        bar_data['frequency_labels'] = freq_labels_str;
        bar_x_range_js.factors = freq_labels_str;

        bar_source_js.change.emit();

    } else {
        console.log('Hover outside plot bounds');
        div.text = "Hover over spectrogram for details";
        bar_source_js.change.emit();
    }
"""

# Create the single CustomJS callback
# Args include placeholders that the dropdown callback will update
hover_callback = CustomJS(args=dict(
    hover_div=hover_info_div,
    bar_source=bar_source,
    bar_x_range=bar_x_range,
    selected_param_holder_js=selected_param_holder,
    times_array=common_data['times_ms'],
    freqs_array=common_data['selected_frequencies'],
    freq_labels_array=common_data['frequency_labels_str'],
    all_param_data_js=all_param_data,
    fig_x_range=spec.x_range,
), code=hover_js_code)

# Create HoverTool and attach the single callback
hover_tool = HoverTool(
    tooltips=None, # Use the Div
    callback=hover_callback,
    renderers=[image_glyph], # Target the single image glyph
    mode='mouse'
)
spec.add_tools(hover_tool)

# -- Dropdwen Selection Widget ---
param_select = Select(
    title="Parameter:",
    value=initial_param,
    options=params_to_plot,
    width=200
)

# --- Dropdown JS Callback ---
# This callback updates the spectrogram source, visuals, AND the hover callback args
dropdown_callback_code = """
    const selected_param = cb_obj.value;    
    const all_data = all_param_data_js;    
    const common = common_data_js;
    const holder = selected_param_holder_js;
        
    try {
        // Update Spectrogram Image Source
        spec_source.data['image'] = [all_data[selected_param]['image_data']];
        spec_source.change.emit();

        // Update Color Mapper Range
        color_mapper.low = all_data[selected_param]['mapper_low'];
        color_mapper.high = all_data[selected_param]['mapper_high'];

        // Update Color Bar Title
        color_bar.title = `${selected_param} (dB)`;

        // Update Spectrogram Title
        spec_figure.title.text = `Spectrogram (${selected_param})`;

        // Update Shared Holder Data
        holder.data['param'] = [selected_param]; // Update data in holder
        holder.change.emit();                   // Notify change on holder

        // Clear hover info and bar chart
        hover_div.text = "Hover over spectrogram for details";
        const bar_data = bar_source.data; // Get reference to bar_source data
        const bar_x_range_js = bar_x_range; // Get reference to bar_x_range
        bar_data['levels'] = [];           // Clear levels
        bar_data['frequency_labels'] = []; // Clear labels
        bar_x_range_js.factors = [];       // Clear factors on the range
        bar_source.change.emit();          // Emit change AFTER all updates

    } catch (error) {
        console.error('Error in dropdown callback:', error);
        console.error('Error details:', {
            message: error.message,
            stack: error.stack
        });
    }
"""

# Pass necessary Python data structures to JS for the dropdown callback
dropdown_args = dict(
    spec_source=spec_source,
    color_mapper=color_mapper,
    color_bar=color_bar,
    spec_figure=spec,
    hover_div=hover_info_div,      # To clear the text
    bar_source=bar_source,       # Pass if clearing bar chart on dropdown change
    bar_x_range=bar_x_range,
    selected_param_holder_js=selected_param_holder,
    all_param_data_js=all_param_data, # Pass the dictionary containing data for all params
    common_data_js=common_data      # Pass common data if needed
)

param_select.js_on_change('value', CustomJS(args=dropdown_args, code=dropdown_callback_code))

# --- Set Initial Titles ---
spec.title.text = f"Spectrogram ({initial_param})"
color_bar.title = f'{initial_param} (dB)'

# --- Final Layout ---
controls = row(param_select)
final_layout = column(
    controls,
    spec,             # Single spectrogram figure
    hover_info_div,   # Single hover div
    bar_chart         # Single bar chart
)

# --- Show ---
show(final_layout)

#%%




