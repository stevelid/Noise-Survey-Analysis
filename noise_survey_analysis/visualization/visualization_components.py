"""
Visualization components for noise survey analysis.

This module contains functions for creating various individual Bokeh visualization
components (figures, sources) based on provided DataFrames and configuration.
"""

import logging
import pandas as pd
import numpy as np
from bokeh.plotting import figure
from bokeh.models import (
    LinearColorMapper, ColorBar, ColumnDataSource, HoverTool, DatetimeTickFormatter,
    DatetimeTicker, RangeTool, Range1d, Label, LabelSet, Span, CustomJS, Div, FactorRange
)

# --- Import configuration from the central config file ---
try:
    # Try normal imports first (for when the module is properly installed)
    from noise_survey_analysis.core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS
except ImportError:
    # Use relative imports for Bokeh server mode
    from ..core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS


# --- Setup Logger ---
logger = logging.getLogger(__name__)

# --- Visualization Functions ---
def create_TH_chart(df, title="Overview Data", height=None, metrics=None, colors=None):
    """
    Create a time history line chart for general metrics (LAeq, LAF90, etc.).

    Parameters:
    df (pd.DataFrame): DataFrame with sound level data. Must contain 'Datetime'.
    title (str): Chart title.
    height (int, optional): Chart height in pixels. Defaults to config.
    metrics (list, optional): List of metrics to plot. Auto-detects if None.
    colors (dict, optional): Dictionary mapping metrics to colors. Defaults to config.

    Returns:
    tuple: (bokeh.plotting.figure, bokeh.models.ColumnDataSource) or (None, None) if error.
    """
    height = height if height is not None else CHART_SETTINGS['low_freq_height']
    width = CHART_SETTINGS['low_freq_width'] # Get width from config
    line_width = CHART_SETTINGS['line_width']
    tools = CHART_SETTINGS['tools']
    active_drag = CHART_SETTINGS['active_drag']
    active_scroll = CHART_SETTINGS['active_scroll']
    show_grid = VISUALIZATION_SETTINGS['show_grid']
    auto_y = CHART_SETTINGS['auto_y_range']
    y_range_cfg = CHART_SETTINGS['y_range']

    # --- Input Validation ---
    if df is None or df.empty:
        logger.warning(f"Empty DataFrame provided for TH chart '{title}'")
        # Return a placeholder or None - returning None might be cleaner for the caller
        return None, None
    if 'Datetime' not in df.columns:
         logger.error(f"Missing 'Datetime' column in DataFrame for TH chart '{title}'")
         return None, None
    # Ensure datetime is actual datetime objects
    if not pd.api.types.is_datetime64_any_dtype(df['Datetime']):
        logger.warning(f"'Datetime' column is not datetime type for '{title}'. Attempting conversion.")
        df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')
        df.dropna(subset=['Datetime'], inplace=True)
        if df.empty:
            logger.error(f"No valid Datetime entries after conversion for '{title}'")
            return None, None

    # --- Metrics and Colors ---
    if metrics is None:
        available = set(df.columns)
        potential_metrics = ['LAeq', 'LAF90', 'LAF10', 'LAFmax'] # Common overview metrics
        metrics = [m for m in potential_metrics if m in available]
        if not metrics:
            # Fallback: Use first few numeric columns if no standard ones found
            numeric_cols = [col for col in df.columns if col != 'Datetime' and pd.api.types.is_numeric_dtype(df[col])]
            metrics = numeric_cols[:4] # Limit to 4
            if not metrics:
                 logger.error(f"No suitable numeric metrics found for TH chart '{title}'")
                 return None, None
            logger.warning(f"Using auto-detected metrics for '{title}': {metrics}")

    if colors is None:
        colors = VISUALIZATION_SETTINGS['line_colors']

    # --- Create Source ---
    source_data = {'Datetime': df['Datetime']}
    used_metrics = []
    for metric in metrics:
        if metric in df.columns:
            if pd.api.types.is_numeric_dtype(df[metric]):
                source_data[metric] = df[metric]
                used_metrics.append(metric)
            else:
                logger.warning(f"Metric '{metric}' for chart '{title}' is not numeric. Skipping.")
        else:
            logger.warning(f"Metric '{metric}' not found in DataFrame for chart '{title}'.")

    if not used_metrics:
         logger.error(f"No valid metrics to plot for TH chart '{title}'")
         return None, None

    source = ColumnDataSource(data=source_data)

    # --- Create Figure ---
    p = figure(
        title=title,
        x_axis_type="datetime",
        height=height,
        width=width,
        tools=tools,
        active_drag=active_drag,
        active_scroll=active_scroll
    )

    # --- Add Lines ---
    renderers = []
    for metric in used_metrics:
        color = colors.get(metric, "#%06x" % np.random.randint(0, 0xFFFFFF)) # Random color if missing
        line = p.line(
            x='Datetime',
            y=metric,
            source=source,
            line_width=line_width,
            color=color,
            legend_label=metric,
            name=metric # Give the line a name for potential reference
        )
        renderers.append(line)

    # --- Add Hover Tool --- #TODO: this is done elsewhere, remove here
    # Attach hover to the first line renderer for efficiency with vline mode
    #if renderers:
    #    hover = HoverTool(
    #        tooltips=[("Time", "@Datetime{%F %T}")] + # Use standard format codes
    #                 [(metric, f"@{metric}{{0.1f}} dB") for metric in used_metrics], # Use Bokeh format specifier
    #        formatters={"@Datetime": "datetime"},
    #        mode="vline",
    #        renderers=[renderers[0]] # Target only one renderer for vline efficiency
    #    )
    #    p.add_tools(hover)

    # --- Configure Axes and Grid ---
    p.xaxis.formatter = DatetimeTickFormatter(days="%d/%m/%y %H:%M", hours="%H:%M:%S") # Simplified formats
    p.xaxis.ticker = DatetimeTicker(desired_num_ticks=10) # Fewer ticks might be cleaner
    p.yaxis.axis_label = "Sound Level (dB)"

    p.grid.grid_line_alpha = 0.3 if show_grid else 0
    p.ygrid.band_fill_alpha = 0.1
    p.ygrid.band_fill_color = "gray"

    if not auto_y:
        try:
            p.y_range = Range1d(*y_range_cfg)
        except:
             logger.warning(f"Invalid y_range configuration: {y_range_cfg}. Using auto-range.")


    # --- Configure Legend ---
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    p.legend.background_fill_alpha = 0.7

    return p, source

def create_log_chart(df, title="Log Data", height=None, metrics=None, colors=None):
    """
    Create a line chart specifically for detailed LOG data.

    Parameters:
    df (pd.DataFrame): DataFrame with log data. Must contain 'Datetime'.
    title (str): Chart title.
    height (int, optional): Chart height in pixels. Defaults to config.
    metrics (list, optional): List of metrics to plot. Auto-detects if None.
    colors (dict, optional): Dictionary mapping metrics to colors. Defaults to config.

    Returns:
    tuple: (bokeh.plotting.figure, bokeh.models.ColumnDataSource) or (None, None) if error.
    """
    height = height if height is not None else CHART_SETTINGS['high_freq_height']
    width = CHART_SETTINGS['high_freq_width']
    line_width = CHART_SETTINGS['line_width']
    tools = CHART_SETTINGS['tools']
    active_drag = CHART_SETTINGS['active_drag']
    active_scroll = CHART_SETTINGS['active_scroll']
    show_grid = VISUALIZATION_SETTINGS['show_grid']
    auto_y = CHART_SETTINGS['auto_y_range']
    y_range_cfg = CHART_SETTINGS['y_range']

    # --- Input Validation ---
    if df is None or df.empty:
        logger.warning(f"Empty DataFrame provided for Log chart '{title}'")
        return None, None
    if 'Datetime' not in df.columns:
         logger.error(f"Missing 'Datetime' column in DataFrame for Log chart '{title}'")
         return None, None
    if not pd.api.types.is_datetime64_any_dtype(df['Datetime']):
        logger.warning(f"'Datetime' column is not datetime type for '{title}'. Attempting conversion.")
        df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')
        df.dropna(subset=['Datetime'], inplace=True)
        if df.empty:
             logger.error(f"No valid Datetime entries after conversion for '{title}'")
             return None, None

    # --- Metrics and Colors ---
    if metrics is None:
        # Auto-detect: Use all numeric columns except 'Datetime'
        metrics = [col for col in df.columns
                   if col != 'Datetime' and pd.api.types.is_numeric_dtype(df[col])]
        if not metrics:
             logger.error(f"No suitable numeric metrics found for Log chart '{title}'")
             return None, None
        logger.warning(f"Using auto-detected metrics for '{title}': {metrics}")

    if colors is None:
        colors = VISUALIZATION_SETTINGS['line_colors']

    # --- Create Source ---
    source_data = {'Datetime': df['Datetime']}
    used_metrics = []
    for metric in metrics:
        if metric in df.columns:
            if pd.api.types.is_numeric_dtype(df[metric]):
                source_data[metric] = df[metric]
                used_metrics.append(metric)
            else:
                logger.warning(f"Metric '{metric}' for chart '{title}' is not numeric. Skipping.")
        else:
            logger.warning(f"Metric '{metric}' not found in DataFrame for chart '{title}'.")

    if not used_metrics:
         logger.error(f"No valid metrics to plot for Log chart '{title}'")
         return None, None

    source = ColumnDataSource(data=source_data)

    # --- Create Figure ---
    p = figure(
        title=title,
        x_axis_type="datetime",
        height=height,
        width=width,
        tools=tools,
        active_drag=active_drag,
        active_scroll=active_scroll
    )

    # --- Add Lines ---
    renderers = []
    for metric in used_metrics:
        # Use more specific log colors if available, otherwise fallback
        color_key = metric if metric in colors else metric.split('_')[0] # e.g., LAFmax_dt -> LAFmax
        color = colors.get(color_key, "#%06x" % np.random.randint(0, 0xFFFFFF))
        line = p.line(
            x='Datetime',
            y=metric,
            source=source,
            line_width=line_width,
            color=color,
            legend_label=metric,
            name=metric
        )
        renderers.append(line)

    # --- Add Hover Tool --- #TODO: this is done elsewhere, remove here
    #if renderers:
    #    hover = HoverTool(
    #        tooltips=[("Time", "@Datetime{%F %T}")] +
    #                 [(metric, f"@{metric}{{0.1f}} dB") for metric in used_metrics],
    #        formatters={"@Datetime": "datetime"},
    #        mode="vline",
    #        renderers=[renderers[0]]
    #    )
    #    p.add_tools(hover)

    # --- Configure Axes and Grid ---
    p.xaxis.formatter = DatetimeTickFormatter(days="%d/%m/%y %H:%M", hours="%H:%M:%S")
    p.xaxis.ticker = DatetimeTicker(desired_num_ticks=10)
    p.yaxis.axis_label = "Sound Level (dB)"

    p.grid.grid_line_alpha = 0.3 if show_grid else 0
    p.ygrid.band_fill_alpha = 0.1
    p.ygrid.band_fill_color = "gray"

    if not auto_y:
        try:
            p.y_range = Range1d(*y_range_cfg)
        except:
             logger.warning(f"Invalid y_range configuration: {y_range_cfg}. Using auto-range.")

    # --- Configure Legend ---
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    p.legend.background_fill_alpha = 0.7

    return p, source

def make_rec_spectrogram(param, df, title=-1, height=None, colormap=None, font_size='10pt'):
    """
    Create an optimized spectrogram visualization using bokeh.rect.

    Parameters:
    param (str): Base parameter name (e.g., 'LZeq').
    df (pd.DataFrame): DataFrame with frequency data. Must contain 'Datetime'.
    title (str or int): Chart title. Defaults to parameter name.
    height (int, optional): Chart height. Defaults to config.
    colormap (str, optional): Colormap name. Defaults to config.
    font_size (str): Font size for labels.

    Returns:
    tuple: (bokeh.plotting.figure, bokeh.models.ColumnDataSource) or (None, None) if error.
    """
    height = height if height is not None else CHART_SETTINGS['spectrogram_height']
    width = CHART_SETTINGS['spectrogram_width']
    lower_band = CHART_SETTINGS['lower_freq_band']
    upper_band = CHART_SETTINGS['upper_freq_band'] # Can be negative index
    colormap = colormap if colormap is not None else CHART_SETTINGS['colormap']
    tools = CHART_SETTINGS['tools'] # Exclude hover initially, add specific one later
    active_drag = CHART_SETTINGS['active_drag']
    active_scroll = CHART_SETTINGS['active_scroll']
    log_freq_axis = CHART_SETTINGS['frequency_log_scale']

    # --- Input Validation ---
    if df is None or df.empty:
        logger.warning(f"Empty DataFrame provided for spectrogram '{param}'")
        return None, None
    if 'Datetime' not in df.columns:
         logger.error(f"Missing 'Datetime' column in DataFrame for spectrogram '{param}'")
         return None, None
    if not pd.api.types.is_datetime64_any_dtype(df['Datetime']):
        logger.warning(f"'Datetime' column is not datetime type for '{title}'. Attempting conversion.")
        df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')
        df.dropna(subset=['Datetime'], inplace=True)
        if df.empty:
             logger.error(f"No valid Datetime entries after conversion for '{title}'")
             return None, None


    # --- Find Frequency Columns ---
    freq_cols_found = []
    all_frequencies = []
    for col in df.columns:
         if col.startswith(param + '_'):
              try:
                   freq = float(col.split('_')[-1]) # Assume frequency is last part
                   freq_cols_found.append(col)
                   all_frequencies.append(freq)
              except (ValueError, IndexError):
                   continue # Skip columns that don't match pattern

    if not freq_cols_found:
        logger.error(f"No frequency columns found for parameter '{param}' in spectrogram.")
        return None, None

    # Sort by frequency and apply band slicing
    sorted_indices = np.argsort(all_frequencies)
    frequencies = np.array(all_frequencies)[sorted_indices]
    freq_columns = np.array(freq_cols_found)[sorted_indices]

    # Apply slicing (handle negative upper bound)
    if upper_band is None or upper_band == -1 : # Treat None or -1 as end
        selected_frequencies = frequencies[lower_band:]
        selected_freq_columns = freq_columns[lower_band:]
    else:
        selected_frequencies = frequencies[lower_band:upper_band]
        selected_freq_columns = freq_columns[lower_band:upper_band]


    if len(selected_frequencies) == 0:
        logger.error(f"No frequencies remaining after applying bands [{lower_band}:{upper_band}] for '{param}'.")
        return None, None
    logger.info(f"Using frequencies for '{param}' spectrogram: {selected_frequencies.tolist()}")


    # --- Prepare Data for Rectangles ---
    data_matrix = df[selected_freq_columns].values
    times_dt = df['Datetime'].values # Keep as datetime64 for calculations
    freqs = selected_frequencies

    # Need times as numeric (milliseconds epoch) for Bokeh plotting x-axis
    times_ms = pd.to_datetime(times_dt).astype('int64') // 10**6
    #times_ms = (times_dt - np.datetime64('1970-01-01T00:00:00Z')) / np.timedelta64(1, 'ms')

    # Compute widths (in milliseconds)
    if len(times_ms) > 1:
        time_diffs_ms = np.diff(times_ms)
        # Handle potential gaps: use median of positive diffs, or default if none
        pos_diffs = time_diffs_ms[time_diffs_ms > 0]
        median_width_ms = np.median(pos_diffs) if len(pos_diffs) > 0 else 60000 # Default 1 min
        # Pad width array for the last element
        widths_per_time_ms = np.append(time_diffs_ms, median_width_ms)
        # Replace non-positive widths with median
        widths_per_time_ms[widths_per_time_ms <= 0] = median_width_ms
    elif len(times_ms) == 1:
        widths_per_time_ms = np.array([60000]) # Default 1 min width if only one point
    else: # No time points
        widths_per_time_ms = np.array([])


    # Compute heights (depends on log/linear axis)
    if len(freqs) > 1:
        if log_freq_axis:
            # Geometric mean for y-position, log difference for height
            log_freqs = np.log10(freqs)
            log_diffs = np.diff(log_freqs)
            heights_per_freq_log = np.append(log_diffs, log_diffs[-1]) # Pad last
            # Calculate center points in log space for y-coordinates
            centers_log = log_freqs - heights_per_freq_log / 2
            y_coords = 10**centers_log # Convert back for y-position
        else:
            # Arithmetic mean for y-position, linear difference for height
            freq_diffs = np.diff(freqs)
            heights_per_freq_lin = np.append(freq_diffs, freq_diffs[-1])
            y_coords = freqs - heights_per_freq_lin / 2
    elif len(freqs) == 1:
         # Single frequency band
         heights_per_freq_log = np.array([0.1]) # Arbitrary small height in log
         heights_per_freq_lin = np.array([freqs[0] * 0.2]) # Arbitrary linear height
         y_coords = freqs # Center is just the frequency itself
    else: # No frequencies
         heights_per_freq_log = np.array([])
         heights_per_freq_lin = np.array([])
         y_coords = np.array([])

    # Use appropriate heights based on axis type
    heights_per_freq = heights_per_freq_log if log_freq_axis else heights_per_freq_lin


    # --- Create Full Grids and Filter NaNs ---
    n_times = len(times_ms)
    n_freqs = len(freqs)

    if n_times == 0 or n_freqs == 0:
        logger.warning(f"No time or frequency points to plot for spectrogram '{param}'")
        return None, None

    # Use times_ms for x coordinate
    x_full = np.repeat(times_ms, n_freqs)
    # Use calculated y_coords (centers) for y coordinate
    y_full = np.tile(y_coords, n_times)
    widths_full = np.repeat(widths_per_time_ms, n_freqs)
    heights_full = np.tile(heights_per_freq, n_times)
    values_full = data_matrix.flatten(order='C') # Flatten column-wise if necessary based on df structure
    # Add original frequency values for tooltip/hover
    freq_labels_full = np.tile(freqs, n_times)

    mask = ~np.isnan(values_full)
    x = x_full[mask]
    y = y_full[mask]
    widths = widths_full[mask]
    heights = heights_full[mask]
    values = values_full[mask]
    freq_labels = freq_labels_full[mask] # Keep corresponding freq labels


    # --- Create Source ---
    source = ColumnDataSource(data=dict(
        x=x, # time in ms epoch
        y=y, # frequency band center
        width=widths, # time width in ms
        height=heights, # frequency height (log or linear diff)
        value=values, # dB level
        freq_label=freq_labels # original frequency for tooltip
    ))

    # --- Color Mapper ---
    if len(values) > 0:
        vmin = np.nanmin(values) # Use nanmin just in case mask didn't catch all
        vmax = np.nanmax(values)
        if vmin == vmax: # Handle case where all values are the same
            vmin -= 1
            vmax += 1
        color_mapper = LinearColorMapper(palette=colormap, low=vmin, high=vmax)
    else: # No data points
        logger.warning(f"No non-NaN values found for spectrogram '{param}'")
        color_mapper = LinearColorMapper(palette=colormap, low=0, high=100) # Default range

    # --- Create Figure ---
    if title == -1:
        title = f"Spectrogram ({param})"

    y_axis_type = "log" if log_freq_axis else "linear"

    spec = figure(
        title=title,
        x_axis_type="datetime", # Let Bokeh handle ms epoch for datetime axis
        y_axis_type=y_axis_type,
        height=height,
        width=width,
        tools=tools, # Add hover later
        active_drag=active_drag,
        active_scroll=active_scroll,
        # Define y_range based on actual freq values for clarity
        y_range=(freqs[0]*0.8, freqs[-1]*1.2) if len(freqs)>0 else (10, 20000) # Add buffer
    )

    # --- Add Rectangles ---
    spec.rect(
        x='x', y='y', width='width', height='height',
        fill_color={'field': 'value', 'transform': color_mapper},
        line_color=None, # No lines for performance
        source=source
    )

    # --- Add Color Bar ---
    color_bar = ColorBar(
        color_mapper=color_mapper,
        location=(0, 0),
        title=f'{param} (dB)',
        title_standoff=12,
        border_line_color=None,
        background_fill_alpha=0.7,
        major_label_text_font_size=font_size,
        title_text_font_size=font_size
    )
    spec.add_layout(color_bar, 'right')

    # --- Configure Axes ---
    spec.xaxis.formatter = DatetimeTickFormatter(days="%d/%m/%y %H:%M", hours="%H:%M:%S")
    spec.xaxis.ticker = DatetimeTicker(desired_num_ticks=10)
    spec.yaxis.axis_label = "Frequency (Hz)"
    spec.xaxis.axis_label = "Time"
    # Improve y-axis ticks for log scale if used
    if log_freq_axis and len(freqs) > 0:
         spec.yaxis.ticker = list(freqs) # Show ticks at the actual frequencies
         spec.yaxis.major_label_overrides = {f: str(int(f)) if f.is_integer() else str(f) for f in freqs}


    # --- Add Hover Tool ---
    hover = HoverTool(
        tooltips=[
            ("Time", "@x{%F %T}"), # Format timestamp from ms epoch
            ("Frequency", "@freq_label{0.0} Hz"), # Show original frequency
            ("Level", "@value{0.1f} dB")
        ],
        formatters={"@x": "datetime"}, # Tell hover x is datetime
        mode="mouse" # Hover over individual rectangles
    )
    spec.add_tools(hover)

    return spec, source

def make_image_spectrogram(param, df, bar_source, bar_x_range, position, title=-1, height=None, colormap=None, font_size='9pt', prepared_data=None):
    """
    Create a high-performance spectrogram using the `image` glyph.
    Hover information is displayed in a separate Div updated via CustomJS.

    Parameters:
    param (str): Base parameter name (e.g., 'LZeq').
    df (pd.DataFrame): DataFrame with frequency data. Must contain 'Datetime'. 
                       Not used if prepared_data is provided.
    bar_source (bokeh.models.ColumnDataSource): Source for the frequency bar chart
    bar_x_range (bokeh.models.FactorRange): X range for the frequency bar chart
    position (str): Position name for JavaScript callbacks
    title (str or int): Chart title. Defaults to parameter name.
    height (int, optional): Chart height. Defaults to config.
    colormap (str, optional): Colormap name. Defaults to config.
    font_size (str): Font size for axis labels.
    prepared_data (dict, optional): Pre-processed data dict from prepare_spectral_image_data.
                                   If provided, will skip data processing steps.

    Returns:
    tuple: (bokeh.plotting.figure, bokeh.models.ColumnDataSource, bokeh.models.Div)
           Returns (None, None, None) if creation fails. The Div is for hover info.
    """
    height = height if height is not None else CHART_SETTINGS['spectrogram_height']
    width = CHART_SETTINGS['spectrogram_width']
    colormap = colormap if colormap is not None else CHART_SETTINGS['colormap']
    tools = CHART_SETTINGS['tools'] # Keep base tools
    active_drag = CHART_SETTINGS['active_drag']
    active_scroll = CHART_SETTINGS['active_scroll']
    
    # --- Use Prepared Data if Provided, Otherwise Process Data ---
    if prepared_data is None:
        # Import the data preparation function 
        try:
            from ..core.data_processors import prepare_spectral_image_data
            prepared_data = prepare_spectral_image_data(df, param, CHART_SETTINGS)
            if prepared_data is None:
                logger.error(f"Failed to prepare spectral data for '{param}'")
                return None, None, None
        except ImportError:
            logger.error("Failed to import prepare_spectral_image_data, falling back to in-function processing")
            # In-function data processing would go here, but since we've moved it, 
            # this fallback is unlikely to work well. Consider proper error handling.
            return None, None, None
    
    # --- Extract Values from Prepared Data ---
    selected_frequencies = prepared_data['frequencies']
    frequency_labels_str = prepared_data['frequency_labels']
    times_ms = prepared_data['times_ms']
    levels_matrix = prepared_data['levels_matrix']  # Original for data access
    levels_matrix_transposed = prepared_data['levels_matrix_transposed']  # For image glyph
    freq_indices = prepared_data['freq_indices']
    min_val = prepared_data['min_val']
    max_val = prepared_data['max_val']
    n_freqs = prepared_data['n_freqs']
    n_times = prepared_data['n_times']

    # --- Create Source ---
    source = ColumnDataSource(data={'image': [levels_matrix_transposed]})

    # --- Color Mapper ---
    if min_val == max_val:  # Handle single value case
        mapper_low, mapper_high = min_val - 1, max_val + 1
    else:
        mapper_low, mapper_high = min_val, max_val
    color_mapper = LinearColorMapper(palette=colormap, low=mapper_low, high=mapper_high, nan_color='#00000000')

    # --- Create Figure ---
    if title == -1: 
        title = f"{position} - {param} Spectral Data"

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
        color_mapper=color_mapper, 
        title=f'{param} (dB)',
        location=(0, 0),
        title_standoff=12,
        border_line_color=None,
        background_fill_alpha=0.7,
        major_label_text_font_size=font_size, 
        title_text_font_size=font_size
    )
    spec.add_layout(color_bar, 'right')

    # --- Hover Setup ---
    # 1. Create a Div for hover info display with proper centering
    hover_info_div = Div(
        text="Hover over spectrogram for details",
        width=width,
        height=30,
        name=f"{position}_spectrogram_hover_div",
        styles={'text-align': 'center', 'margin': '0 auto', 'display': 'block'}
    )

    # 2. Create CustomJS callback
    hover_callback = CustomJS(args=dict(
        hover_div=hover_info_div,
        bar_source=bar_source,
        bar_x_range=bar_x_range,
        times_array=times_ms, # Pass numeric times
        freqs_array=selected_frequencies, # Pass original frequencies
        freq_labels_array=frequency_labels_str, # Pass original frequencies
        levels_matrix=levels_matrix, # Pass original (non-transposed) levels matrix
        levels_flat_array=levels_matrix.flatten(),
        fig_x_range=spec.x_range, # Pass figure range for bounds checking
        position_name=position # Pass position name for title update
    ), code="""
        if (typeof window.NoiseSurveyApp?.frequency?.handleSpectrogramHover === 'function') {
            window.NoiseSurveyApp.frequency.handleSpectrogramHover(
                cb_data, 
                hover_div, 
                bar_source, 
                bar_x_range, 
                position_name,
                times_array, 
                freqs_array, 
                freq_labels_array, 
                levels_matrix, 
                levels_flat_array, 
                fig_x_range
            );
        } else {
            console.error('NoiseSurveyApp.frequency.handleSpectrogramHover not defined!');
        }
    """)

    # 3. Create HoverTool and attach callback
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
    tuple: (bokeh.plotting.figure, bokeh.models.ColumnDataSource, bokeh.models.FactorRange)
    """
    height = height if height is not None else CHART_SETTINGS['high_freq_height'] # Use a height setting
    width = width if width is not None else CHART_SETTINGS['high_freq_width']
    auto_y = CHART_SETTINGS['auto_y_range']
    y_range_cfg = CHART_SETTINGS['y_range']

    # Initial empty data structure
    # 'frequency_labels' will be the actual string labels (e.g., "31.5 Hz")
    # 'levels' will be the dB values
    initial_data = {'frequency_labels': ['25 Hz', '31 Hz', '40 Hz', '50 Hz', '63 Hz', '80 Hz', '100 Hz', '125 Hz', '160 Hz', '200 Hz', '250 Hz', '315 Hz', '400 Hz', '500 Hz', '630 Hz', '800 Hz', '1000 Hz', '1250 Hz', '1600 Hz', '2000 Hz'], 
    'levels': [0] * 20}
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

    p.name = "frequency_bar_chart"

    return p, source, x_range

def create_range_selector(attached_chart, source, height=None, width=None):
    """
    Create a range selector chart linked to another chart's x-range.

    Parameters:
    attached_chart (bokeh.plotting.figure): The main chart whose x_range will be controlled.
    source (bokeh.models.ColumnDataSource): The data source for the overview in the selector.
                                             Should contain 'Datetime' and metrics.
    height (int, optional): Height of the selector. Defaults to config.
    width (int, optional): Width of the selector. Defaults to config.

    Returns:
    bokeh.plotting.figure: The range selector chart, or None if input is invalid.
    """
    height = height if height is not None else CHART_SETTINGS['range_selector_height']
    width = width if width is not None else CHART_SETTINGS['range_selector_width']
    colors = VISUALIZATION_SETTINGS['line_colors']

    # --- Input Validation ---
    if attached_chart is None or source is None:
         logger.error("Missing attached_chart or source for create_range_selector.")
         return None
    if 'Datetime' not in source.data:
         logger.error("Source for range selector missing 'Datetime' column.")
         return None

    # --- Identify Metrics in Source ---
    metrics = [col for col in source.data if col != 'Datetime' and isinstance(source.data[col], (pd.Series, np.ndarray))] #this was list before the refactor of the data structure to hirarchy structure. 
    if not metrics:
         logger.warning("No plottable metrics found in source for range selector.")
         # Still create selector, just without lines
         metrics_to_plot = []
    else:
         metrics_to_plot = metrics[:3] # Limit displayed lines for clarity


    # --- Create Selector Figure ---
    select = figure(
        title="Drag handles to select time range", # More descriptive title
        height=height,
        width=width,
        x_axis_type="datetime",
        y_axis_type=None, # No y-axis needed
        tools="", # No tools needed on the selector itself
        toolbar_location=None,
        background_fill_color="#efefef", # Lighter background
    )

    # --- Add Subtle Lines ---
    for i, metric in enumerate(metrics_to_plot):
        color = colors.get(metric, "#cccccc") # Use grey if color not defined
        select.line('Datetime', metric, source=source, line_width=1, color=color, alpha=0.6)

    # --- Add RangeTool ---
    range_tool = RangeTool(x_range=attached_chart.x_range)
    range_tool.overlay.fill_color = "navy"
    range_tool.overlay.fill_alpha = 0.2
    select.add_tools(range_tool)

    # --- Configure Appearance ---
    select.xaxis.formatter = DatetimeTickFormatter(days="%d/%m", hours="%H:%M") # Simpler format
    select.xaxis.ticker = DatetimeTicker(desired_num_ticks=8)
    select.grid.grid_line_color = None # No grid lines
    select.yaxis.visible = False # Hide y-axis completely

    return select

def link_x_ranges(charts):
    """
    Link the x_range of multiple charts. The first chart's range is used as the master.

    Parameters:
    charts (list): List of Bokeh figures to link.
    """
    valid_charts = [c for c in charts if hasattr(c, 'x_range') and c.name != 'shared_range_selector']
    if len(valid_charts) <= 1:
        logger.debug("Less than 2 valid charts provided for x-range linking.")
        return # Nothing to link

    master_range = valid_charts[0].x_range
    logger.info(f"Linking x-ranges of {len(valid_charts)-1} charts to master.")

    for chart in valid_charts[1:]:
        chart.x_range = master_range

def add_vertical_line_and_hover(charts, sources=None):
    if False: #TODO: legacy and can be removed
        
        """
        Adds vertical line Spans, Labels, and Hover/Tap interactivity to charts.

        Relies on JavaScript functions (handleHover, handleTap) defined globally.

        Parameters:
        charts (list): List of Bokeh figures to add interactivity to.
        sources (dict, optional): Dictionary mapping keys (e.g., chart names)
                                to their ColumnDataSources. Passed to JS.

        Returns:
        tuple: (list_of_charts, list_of_click_line_models, list_of_label_models)
            The models created are returned for potential use elsewhere (e.g., JS init).
        """
        # Ensure charts is a list
        if not isinstance(charts, list):
            charts = [charts]

        # Filter out None charts
        valid_charts = [c for c in charts if c is not None]
        if not valid_charts:
            logger.warning("No valid charts provided to add_vertical_line_and_hover.")
            return [], [], []

        logger.info(f"Adding vertical lines/hover/tap to {len(valid_charts)} charts.")

        hover_lines = []
        click_lines = []
        labels = []

        # Create models for each valid chart
        for i, chart in enumerate(valid_charts):
            logger.info(f"Adding vertical lines/hover/tap to chart {chart.name}.")
            hover_line = Span(location=0, dimension='height', line_color='grey',
                            line_width=1, line_dash='dashed', name=f"hover_line_{i}", level='overlay')
            click_line = Span(location=0, dimension='height', line_color='red',
                            line_width=1.5, line_dash='solid', visible=False, # Start invisible
                            line_alpha=0.8, name=f"click_line_{i}", level='overlay')

            # Check if it's the range selector (simple title check, might need refinement)
            is_range_selector = hasattr(chart, 'title') and "select time range" in chart.title.text.lower()
            logger.info(f"Is range selector: {is_range_selector}.")

            if is_range_selector:
                # Range selector doesn't need a visible hover label
                label = Label(x=0, y=0, text="", visible=False, name=f"label_{i}") # Still create model, just hidden
            else:
                label = Label(
                    x=0, y=0, x_units='data', y_units='screen', # Use screen units for y offset
                    text="", text_font_size="9pt", # Smaller font
                    text_align="left", text_baseline="bottom", # Baseline bottom, position with offset
                    x_offset=10, y_offset=5, # Offset from cursor/line
                    background_fill_color="white", background_fill_alpha=0.7,
                    border_line_color="black", border_line_alpha=0.5,
                    visible=False, # Start invisible
                    name=f"label_{i}",
                )
                chart.add_layout(label) # Add label to non-selector charts

            # Add spans to the chart
            chart.add_layout(hover_line)
            chart.add_layout(click_line)

            # Store models
            hover_lines.append(hover_line)
            click_lines.append(click_line)
            labels.append(label)


        # --- Define JS Callbacks ---
        # (These call globally defined functions like window.handleHover/window.handleTap)

        hover_callback_code = """
            if (typeof window.handleHover === 'function') {
                window.handleHover(hoverLinesModels, cb_data, chart_index); // Pass models directly
            } else { console.error('window.handleHover not defined!'); }
        """
        hover_callback = CustomJS(args={'hoverLinesModels': hover_lines}, code=hover_callback_code)

        click_callback_code = """
            if (typeof window.handleTap === 'function') {
                // Pass models directly, plus sources dict and cb_obj
                window.handleTap(cb_obj, chartModels, clickLineModels, labelModels, sourcesDict);
            } else { console.error('window.handleTap not defined!'); }
        """
        click_callback = CustomJS(args={
            'chartModels': valid_charts,
            'clickLineModels': click_lines,
            'labelModels': labels,
            'sourcesDict': sources if sources is not None else {} # Ensure sources is a dict
        }, code=click_callback_code)


        # --- Add Tools ---
        # Add specific hover tool for vline mode
        vline_hover = HoverTool(
            tooltips=None, # We use the Label model for tooltips on click/playback
            mode='vline',
            callback=hover_callback, # JS callback updates hover lines
            name="vline_hover" # Give it a name
        )

        for chart in valid_charts:
            # Add the vline hover tool
            # Check if a tool with this name already exists to avoid duplicates
            existing_tools = [t for t in chart.tools if t.name == "vline_hover"]
            if not existing_tools:
                chart.add_tools(vline_hover)
            else:
                # Optionally update the callback if needed, though usually not necessary
                # existing_tools[0].callback = hover_callback
                pass
            # Attach JS tap callback
            chart.js_on_event('tap', click_callback)

        # Return the created models in case they are needed for JS initialization args
        return valid_charts, click_lines, labels
