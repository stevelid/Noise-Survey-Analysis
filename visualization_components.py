"""
Visualization components for noise survey analysis.

This module contains functions for creating various visualization components
used in the noise survey analysis application.
"""

import pandas as pd
import numpy as np
from bokeh.plotting import figure
from bokeh.models import (
    LinearColorMapper, ColorBar, ColumnDataSource, HoverTool, DatetimeTickFormatter, 
    DatetimeTicker, CustomJS, Span, RangeTool, Slider, Div, Line, Tabs, TabPanel, Range1d, Label, LabelSet
)
from bokeh.layouts import column, row
from bokeh.models.tools import TapTool
# Import JavaScript callbacks
from js_callbacks import get_hover_line_js, get_click_line_js, get_keyboard_navigation_js, get_common_utility_functions

# Configuration dictionary - moved from plot_analysis.py
CONFIG = {
    'chart_settings': {
        'lower_freq_band': 6,
        'upper_freq_band': -5,
        'low_freq_height': 360,      
        'low_freq_width': 1600,      
        'high_freq_height': 360,     
        'high_freq_width': 1600,      
        'spectrogram_height': 360,   
        'spectrogram_width': 1600,    
        'sync_charts': False,
        'tools': 'xzoom_in,xzoom_out,xpan,reset,xwheel_zoom',  # X-axis only tools
        'active_scroll': 'xwheel_zoom',
        'line_width': 1,
        'colormap': 'Turbo256',
        'active_drag': 'xpan',
        'range_selector_width': 1600,
        'range_selector_height': 150,
        'y_range': (0, 100),
        'auto_y_range': False,
        'frequency_log_scale': True
    },
    'visualization': {
        'default_title': 'Sound Level Analysis',
        'line_colors': {
            'LAeq': '#0000FF',  # Blue (adjusted to match example)
            'LAF90': '#008000', # Green (adjusted to match example as LA90)
            'LAF10': '#FFA500', # Orange
            'LAFmax': '#FF0000', # Red
            'LAFmax_dt': '#FF0000', # Red
            'LAeq_dt': '#0000FF',  # Blue (adjusted to match example)
        },
        'show_grid': True,
        'sync_ranges': True,
    },
    'processing': {
        'default_resample': '1T',
        'smooth_window': 3,
    }
}

# Visualization Functions
def create_TH_chart(df, title="Overview (Lower Frequency Data)", height=260, metrics=None, colors=None):
    """
    Create a line chart for lower frequency data metrics.
    
    Parameters:
    df (pd.DataFrame): DataFrame with sound level data
    title (str): Chart title
    height (int): Chart height in pixels
    metrics (list): List of metrics to plot (defaults to LAeq, LAF90, LAF10, LAFmax if available)
    colors (dict): Dictionary mapping metrics to colors
    
    Returns:
    tuple: (bokeh figure, ColumnDataSource)
    """
    # Check if DataFrame is empty
    if df is None or df.empty:
        print(f"Warning: Empty DataFrame provided for chart '{title}'")
        # Create a minimal figure with a warning message
        p = figure(title=f"{title} (No Data)", height=height, width=800)
        p.text(x=0, y=0, text=["No data available"], text_font_size="20pt", text_align="center")
        source = ColumnDataSource(data=dict(x=[], y=[]))
        return p, source
    
    # Use configuration or default values
    if metrics is None:
        # Try to find available metrics in the dataframe
        available = set(df.columns)
        potential_metrics = ['LAeq', 'LAF90', 'LAF10', 'LAFmax']
        metrics = [m for m in potential_metrics if m in available]
        
        if not metrics:
            print(f"Warning: No recognized metrics found for chart '{title}'")
            # Try to use any numeric columns
            metrics = [col for col in df.columns 
                      if col != 'Datetime' and pd.api.types.is_numeric_dtype(df[col])][:4]  # Limit to 4 metrics
    
    if colors is None:
        colors = CONFIG['visualization']['line_colors']
    
    # Create data source
    source_data = {'Datetime': df['Datetime']}
    for metric in metrics:
        if metric in df.columns:
            source_data[metric] = df[metric]
    
    source = ColumnDataSource(data=source_data)
    
    # Create figure
    p = figure(
        title=title,
        x_axis_type="datetime",
        height=height,
        width=CONFIG['chart_settings']['low_freq_width'],
        tools=CONFIG['chart_settings']['tools'],
        active_drag=CONFIG['chart_settings']['active_drag'],
        active_scroll=CONFIG['chart_settings']['active_scroll']
    )
    
    # Add lines for each metric
    used_metrics = []
    for i, metric in enumerate(metrics):
        if metric in source_data:
            color = colors.get(metric, f"#{hash(metric) % 0xFFFFFF:06x}")  # Generate color if not specified
            line = p.line(
                x='Datetime', 
                y=metric, 
                source=source, 
                line_width=CONFIG['chart_settings']['line_width'],
                color=color,
                legend_label=metric
            )
            if i == 0:
                first_line = line
            used_metrics.append(metric)
            
    # Add hover tool for this line
    hover = HoverTool(
        tooltips=[
            ("Time", "@Datetime{%Y-%m-%d %H:%M:%S}"),
            *[(metric, f"@{metric}{{0.0}} dB") for metric in used_metrics]
        ],
        formatters={"@Datetime": "datetime"},
        mode="vline",
        renderers=[first_line]
    )
    p.add_tools(hover)
    
    # Configure axis and legend
    p.xaxis.formatter = DatetimeTickFormatter(
        hours="%H:%M",
        days="%H:%M\n%A %d/%m/%y",
        months="%H:%M\n%A %d/%m/%y",
        years="%H:%M\n%A %d/%m/%y"
    )
    
    # Configure grid and axis
    p.grid.grid_line_alpha = 0.3 if CONFIG['visualization']['show_grid'] else 0
    p.ygrid.band_fill_alpha = 0.1
    p.ygrid.band_fill_color = "gray"
    #p.xaxis.major_label_orientation = 0.75
    p.xaxis.ticker = DatetimeTicker(desired_num_ticks=24)
    if not CONFIG['chart_settings']['auto_y_range']:
        p.y_range = Range1d(*CONFIG['chart_settings']['y_range'])
    
    # Configure legend
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    p.legend.background_fill_alpha = 0.7
    
    return p, source

def create_log_chart(df, title="Logger Overview", height=260, metrics=None, colors=None):
    """
    Create a line chart for log data.
    
    Parameters:
    df (pd.DataFrame): DataFrame with log data
    title (str): Chart title
    height (int): Chart height in pixels
    metrics (list): List of metrics to plot (defaults to available metrics if None)
    colors (dict): Dictionary mapping metrics to colors
    
    Returns:
    tuple: (bokeh figure, ColumnDataSource)
    """
    # Check if DataFrame is empty
    if df is None or df.empty:
        print(f"Warning: Empty DataFrame provided for chart '{title}'")
        # Create a minimal figure with a warning message
        p = figure(title=f"{title} (No Data)", height=height, width=CONFIG['chart_settings']['low_freq_width'])
        p.text(x=0, y=0, text=["No data available"], text_font_size="20pt", text_align="center")
        source = ColumnDataSource(data=dict(x=[], y=[]))
        return p, source
    
    # Use configuration or default values
    if metrics is None:
        # Try to find available metrics in the dataframe
        available = set(df.columns)
        # Exclude the Datetime column and any non-numeric columns
        metrics = [col for col in available 
                  if col != 'Datetime' and pd.api.types.is_numeric_dtype(df[col])]

    if colors is None:
        colors = CONFIG['visualization']['line_colors']
    
    # Create data source
    source_data = {'Datetime': df['Datetime']}
    for metric in metrics:
        if metric in df.columns:
            source_data[metric] = df[metric]

    
    source = ColumnDataSource(data=source_data)
    
    # Create figure
    p = figure(
        title=title,
        x_axis_type="datetime",
        height=height,
        width=CONFIG['chart_settings']['low_freq_width'],
        tools=CONFIG['chart_settings']['tools'],
        active_drag=CONFIG['chart_settings']['active_drag'],
        active_scroll=CONFIG['chart_settings']['active_scroll']
    )
    
    # Add lines for each metric
    used_metrics = []
    for i, metric in enumerate(metrics):
        if metric in source_data:
            color = colors.get(metric, f"#{hash(metric) % 0xFFFFFF:06x}")  # Generate color if not specified
            line = p.line(
                x='Datetime', 
                y=metric, 
                source=source, 
                line_width=CONFIG['chart_settings']['line_width'],
                color=color,
                legend_label=metric
            )
            if i == 0:
                first_line = line
            used_metrics.append(metric)
    
    # Add hover tool for this line
    hover = HoverTool(
        tooltips=[
            ("Time", "@Datetime{%Y-%m-%d %H:%M:%S}"),
            *[(metric, f"@{metric}{{0.0}} dB") for metric in used_metrics]
        ],
        formatters={"@Datetime": "datetime"},
        mode="vline",
        renderers=[first_line]
    )
    p.add_tools(hover)
    
    # Configure axis and legend
    p.xaxis.formatter = DatetimeTickFormatter(
        hours="%H:%M", days="%H:%M\n%A %d/%m/%y", months="%H:%M\n%A %d/%m/%y", years="%H:%M\n%A %d/%m/%y"
    )
    
    # Configure grid and axis
    p.grid.grid_line_alpha = 0.3 if CONFIG['visualization']['show_grid'] else 0
    p.ygrid.band_fill_alpha = 0.1
    p.ygrid.band_fill_color = "gray"
    #p.xaxis.major_label_orientation = 0.75
    p.xaxis.ticker = DatetimeTicker(desired_num_ticks=24)
    
    # Configure y range
    if not CONFIG['chart_settings']['auto_y_range']:
        p.y_range = Range1d(*CONFIG['chart_settings']['y_range'])
    
    # Configure legend
    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    p.legend.background_fill_alpha = 0.7
    
    return p, source

def make_spectrogram(param, df, title=-1, height=400, colormap='Viridis256', font_size='10pt'):
    """
    Create a spectrogram visualization for frequency data.
    
    Parameters:
    param (str): Parameter to visualize (e.g., 'LZeq', 'LZF90')
    df (pd.DataFrame): DataFrame with frequency data
    title (str or int): Chart title or -1 to use param as title
    height (int): Chart height in pixels
    colormap (str): Colormap to use for the spectrogram
    font_size (str): Font size for axis labels
    
    Returns:
    tuple: (bokeh figure, ColumnDataSource)
    """
    # Check for empty DataFrame
    if df is None or df.empty:
        print(f"Warning: Empty DataFrame provided for spectrogram '{param}'")
        spec = figure(title=f"Spectrogram ({param}) - No Data", height=height, width=CONFIG['chart_settings']['low_freq_width'])
        spec.text(x=0, y=0, text=["No data available"], text_font_size="20pt", text_align="center")
        source = ColumnDataSource(data=dict(x=[], y=[], width=[], height=[], value=[], time=[], freq=[]))
        return spec, source
    
    # Find relevant frequency columns
    frequencies = [
        float(col.split('_')[1])
        for col in df.columns
        if col.startswith(param+'_') and col.split('_')[1][:1].isdigit()
    ]
    
    # Check if we found any matching columns
    if not frequencies:
        print(f"Warning: No frequency columns found for parameter '{param}'")
        spec = figure(title=f"Spectrogram ({param}) - No Frequency Data", height=height, width=CONFIG['chart_settings']['low_freq_width'])
        spec.text(x=0, y=0, text=["No frequency data available"], text_font_size="20pt", text_align="center")
        source = ColumnDataSource(data=dict(x=[], y=[], width=[], height=[], value=[], time=[], freq=[]))
        return spec, source
    
    # Sort frequencies
    frequencies.sort()
    
    # Create data for the spectrogram
    times = df['Datetime'].to_numpy()
    values = []
    
    # Extract data for each frequency
    for freq in frequencies:
        col_name = f"{param}_{freq}"
        if col_name in df.columns:
            values.append(df[col_name].to_numpy())
    
    # Convert to numpy array
    values = np.array(values)
    
    # Create a mesh grid for the spectrogram
    X, Y = np.meshgrid(range(len(times)), frequencies)
    
    # Create source data for Bokeh
    source_data = {
        'x': [], 'y': [], 'width': [], 'height': [], 'value': [], 'time': [], 'freq': []
    }
    
    # Determine min and max values for color mapping
    vmin = np.nanmin(values)
    vmax = np.nanmax(values)
    
    # Create rectangles for the spectrogram
    for i in range(len(times)):
        for j in range(len(frequencies)):
            # Skip NaN values
            if np.isnan(values[j, i]):
                continue
                
            # Calculate rectangle dimensions
            if i < len(times) - 1:
                width = (times[i+1] - times[i]).total_seconds() * 1000  # Width in milliseconds
            else:
                # For the last time point, use the same width as the previous one
                width = (times[i] - times[i-1]).total_seconds() * 1000 if i > 0 else 3600000  # Default to 1 hour
            
            # Calculate height based on log or linear scale
            if CONFIG['chart_settings']['frequency_log_scale']:
                # For log scale, use the ratio between frequencies
                if j < len(frequencies) - 1:
                    height = np.log(frequencies[j+1]) - np.log(frequencies[j])
                else:
                    # For the last frequency, use the same ratio as the previous one
                    height = np.log(frequencies[j]) - np.log(frequencies[j-1]) if j > 0 else 0.1
            else:
                # For linear scale, use the difference between frequencies
                if j < len(frequencies) - 1:
                    height = frequencies[j+1] - frequencies[j]
                else:
                    # For the last frequency, use the same difference as the previous one
                    height = frequencies[j] - frequencies[j-1] if j > 0 else 10
            
            # Add data to source
            source_data['x'].append(times[i])
            source_data['y'].append(frequencies[j])
            source_data['width'].append(width)
            source_data['height'].append(height)
            source_data['value'].append(values[j, i])
            source_data['time'].append(times[i])
            source_data['freq'].append(frequencies[j])
    
    # Create ColumnDataSource
    source = ColumnDataSource(data=source_data)
    
    # Create color mapper
    color_mapper = LinearColorMapper(palette=colormap, low=vmin, high=vmax)
    
    # Create figure
    if title == -1:
        title = f"Spectrogram - {param}"
    
    # Determine y-axis type based on configuration
    y_axis_type = "log" if CONFIG['chart_settings']['frequency_log_scale'] else "linear"
    
    spec = figure(
        title=title,
        x_axis_type="datetime",
        y_axis_type=y_axis_type,
        height=height,
        width=CONFIG['chart_settings']['spectrogram_width'],
        tools=CONFIG['chart_settings']['tools'] + ",hover",
        active_drag=CONFIG['chart_settings']['active_drag'],
        active_scroll=CONFIG['chart_settings']['active_scroll']
    )
    
    # Add rectangles for the spectrogram
    rects = spec.rect(
        x="x", y="y", width="width", height="height", 
        fill_color={'field': 'value', 'transform': color_mapper},
        line_color=None, source=source
    )
    
    # Add color bar
    color_bar = ColorBar(
        color_mapper=color_mapper, 
        label_standoff=12, 
        location=(0, 0), 
        title=f"{param} (dB)",
        title_text_font_size=font_size,
        major_label_text_font_size=font_size
    )
    spec.add_layout(color_bar, 'right')
    
    # Configure hover tool
    hover = spec.select(dict(type=HoverTool))
    hover.tooltips = [
        ("Time", "@time{%Y-%m-%d %H:%M:%S}"),
        ("Frequency", "@freq{0.0} Hz"),
        ("Level", "@value{0.0} dB")
    ]
    hover.formatters = {"@time": "datetime"}
    hover.mode = "mouse"
    
    # Configure axis and grid
    spec.xaxis.formatter = DatetimeTickFormatter(
        hours="%H:%M", days="%H:%M\n%A %d/%m/%y", months="%H:%M\n%A %d/%m/%y", years="%H:%M\n%A %d/%m/%y"
    )
   #spec.xaxis.major_label_orientation = 0.75
    spec.xaxis.ticker = DatetimeTicker(desired_num_ticks=24)
    
    spec.yaxis.axis_label = "Frequency (Hz)"
    spec.yaxis.axis_label_text_font_size = font_size
    spec.yaxis.major_label_text_font_size = font_size
    
    spec.grid.grid_line_alpha = 0.3 if CONFIG['visualization']['show_grid'] else 0
    
    return spec, source

import numpy as np
from bokeh.plotting import figure
from bokeh.models import ColumnDataSource, LinearColorMapper, ColorBar, HoverTool, DatetimeTickFormatter, DatetimeTicker

def make_rec_spectrogram(param, df, title=-1, height=400, colormap='Viridis256', font_size='10pt'):
    """
    Create a spectrogram visualization for frequency data, optimized for large datasets.
    
    Parameters:
    param (str): Parameter to visualize (e.g., 'LZeq', 'LZF90')
    df (pd.DataFrame): DataFrame with frequency data
    title (str or int): Chart title or -1 to use param as title
    height (int): Chart height in pixels
    colormap (str): Colormap to use for the spectrogram
    font_size (str): Font size for axis labels
    
    Returns:
    tuple: (bokeh figure, ColumnDataSource)
    """
    # Check for empty DataFrame
    if df is None or df.empty:
        print(f"Warning: Empty DataFrame provided for spectrogram '{param}'")
        spec = figure(title=f"Spectrogram ({param}) - No Data", height=height, width=CONFIG['chart_settings']['low_freq_width'])
        spec.text(x=0, y=0, text=["No data available"], text_font_size="20pt", text_align="center")
        source = ColumnDataSource(data=dict(x=[], y=[], width=[], height=[], value=[]))
        return spec, source
    
    # Find relevant frequency columns
    frequencies = [
        float(col.split('_')[1])
        for col in df.columns
        if col.startswith(param+'_') and col.split('_')[1][:1].isdigit()
    ][CONFIG['chart_settings']['lower_freq_band']:CONFIG['chart_settings']['upper_freq_band']] 
    if not frequencies:
        print(f"Warning: No frequency data found for '{param}'")
        spec = figure(title=f"Spectrogram ({param}) - No Matching Data", height=height, width=CONFIG['chart_settings']['low_freq_width'])
        spec.text(x=0, y=0, text=["No matching frequency data found"], text_font_size="20pt", text_align="center")
        source = ColumnDataSource(data=dict(x=[], y=[], width=[], height=[], value=[]))
        return spec, source
    
    # Extract data efficiently
    freq_columns = [f'{param}_{freq}' for freq in frequencies]
    data_matrix = df[freq_columns].values  # Shape: (n_times, n_freqs)
    times = df['Datetime'].values
    freqs = np.array(frequencies)
    
    # Compute widths per time
    if len(times) > 1:
        time_diffs = np.diff(times)
        median_width = np.median(time_diffs)
        widths_per_time = np.append(time_diffs, median_width)
    else:
        widths_per_time = np.array([3600000])  # 1 hour in milliseconds
    
    # Compute heights per frequency
    if len(freqs) > 1:
        freq_diffs = np.diff(freqs)
        heights_per_freq = np.append(freq_diffs, freq_diffs[-1])
    else:
        heights_per_freq = np.array([freqs[0] * 0.2])
    
    # Create full grids for all rectangles
    n_times = len(times)
    n_freqs = len(freqs)
    x_full = np.repeat(times, n_freqs)              # Time for each rectangle
    y_full = np.tile(freqs, n_times)                # Frequency for each rectangle
    widths_full = np.repeat(widths_per_time, n_freqs)  # Width for each rectangle
    heights_full = np.tile(heights_per_freq, n_times)  # Height for each rectangle
    values_full = data_matrix.flatten(order='C')    # Values in row-major order
    
    # Filter out NaN values
    mask = ~np.isnan(values_full)
    x = x_full[mask]
    y = y_full[mask]
    widths = widths_full[mask]
    heights = heights_full[mask]
    values = values_full[mask]
    
    # Create ColumnDataSource
    source = ColumnDataSource(data=dict(
        x=x,
        y=y,
        width=widths,
        height=heights,
        value=values
    ))
    
    # Set up color mapper
    if len(values) > 0:
        color_mapper = LinearColorMapper(
            palette=CONFIG['chart_settings']['colormap'],
            low=np.min(values),
            high=np.max(values)
        )
    else:
        color_mapper = LinearColorMapper(
            palette=CONFIG['chart_settings']['colormap'],
            low=0,
            high=100
        )
    
    # Create the figure
    if title == -1:
        title = f"Spectrogram ({param})"
    
    spec = figure(
        title=title,
        x_axis_type="datetime",
        y_axis_type="log",
        height=height,
        width=CONFIG['chart_settings']['low_freq_width'],
        tools=CONFIG['chart_settings']['tools'],
        active_drag=CONFIG['chart_settings']['active_drag'],
        active_scroll=CONFIG['chart_settings']['active_scroll']
    )
    
    # Add color bar
    color_bar = ColorBar(
        color_mapper=color_mapper,
        location=(0, 0),
        title=f'{param} (dB)',
        title_standoff=12,
        border_line_color=None,
        background_fill_alpha=0.7
    )
    spec.add_layout(color_bar, 'right')
    
    # Configure axes
    spec.yaxis.ticker = frequencies
    spec.yaxis.major_label_overrides = {freq: str(freq) for freq in frequencies}
    #spec.xaxis.major_label_orientation = 0.75
    spec.yaxis.axis_label = "Frequency (Hz)"
    spec.xaxis.axis_label = "Time"
    
    # Add rectangular glyphs
    spec.rect(
        x='x', y='y',
        width='width', height='height',
        fill_color={'field': 'value', 'transform': color_mapper},
        line_color=None,
        source=source
    )
    
    # Set x-axis formatter
    spec.xaxis.formatter = DatetimeTickFormatter(
        hours="%H:%M", days="%H:%M\n%A %d/%m/%y", months="%H:%M\n%A %d/%m/%y", years="%H:%M\n%A %d/%m/%y"
    )
    spec.xaxis.ticker = DatetimeTicker(desired_num_ticks=24)
    
    # Add hover tool
    hover = HoverTool(
        tooltips=[
            ("Time", "@x{%Y-%m-%d %H:%M:%S}"),
            ("Frequency", "@y{0.0} Hz"),
            ("Value", "@value{0.0} dB")
        ],
        formatters={"@x": "datetime"},
        mode="mouse"
    )
    spec.add_tools(hover)
    
    return spec, source

def create_frequency_bar_chart(title="Frequency Analysis", height=260, width=1600):
    """
    Create a bar chart for frequency analysis at a specific time.
    
    Parameters:
    title (str): Chart title
    height (int): Chart height in pixels
    width (int): Chart width in pixels
    
    Returns:
    bokeh.plotting.figure: The bar chart figure
    ColumnDataSource: The data source for dynamic updates
    """
    # Sample data with 1/3 octave bands
    frequencies = [
        20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 
        200, 250, 315, 400, 500, 630, 800, 1000, 1250, 
        1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000
    ]
    levels = []    
    frequency_labels = [f"{f} Hz" for f in frequencies]  # Categorical labels like "31.5 Hz"

    # Create a data source
    source = ColumnDataSource(data={
        'frequency_labels': frequency_labels,  # X-axis categories
        'levels': levels                      # Y-axis values
    })

    # Create the figure with a categorical x-axis
    p = figure(
        title=title,
        height=height,
        width=width,
        x_range=frequency_labels,  # Tell Bokeh to use these as x-axis categories
        x_axis_label='Frequency (Hz)',
        y_axis_label='Level (dB)',
        tools="pan,wheel_zoom,box_zoom,reset,save"
    )

    # Add vertical bars
    p.vbar(
        x='frequency_labels',  # Use the categorical labels from the source
        top='levels',         # Bar height from the levels
        width=0.8,            # Bar width as a fraction of category space
        source=source,
        fill_color="#6baed6", # Bar color
        line_color="white"    # Bar outline
    )

    # Add labels above the bars
    labels = LabelSet(
        x='frequency_labels',  # X-coordinate matches bar positions
        y='levels',           # Y-coordinate matches bar heights
        text='levels',        # Display the 'levels' values
        level='glyph',        # Render on top of bars
        x_offset=0,           # Center horizontally
        y_offset=5,           # Slight offset above the bar
        source=source,        # Use the same data source
        text_align='center',  # Center the text
        text_font_size='10pt',# Font size for readability
        text_color='black',   # Text color
        text_baseline='bottom'# Align text bottom to the y position
    )
    p.add_layout(labels)      # Add the labels to the plot
    if not CONFIG['chart_settings']['auto_y_range']:
        p.y_range = Range1d(*CONFIG['chart_settings']['y_range'])

    # Add a hover tool for interactivity
    hover = HoverTool(tooltips=[
        ("Frequency", "@frequency_labels"),
        ("Level", "@levels{0.0} dB")
    ])
    p.add_tools(hover)

    # Style the chart
    p.xaxis.major_label_orientation = "vertical"  # Rotate x-axis labels for readability
    p.grid.grid_line_alpha = 0.3                  # Light grid lines

    return p, source

def create_range_selector(attached_chart, source, height=150):
    """
    Create a range selector chart.
    
    Parameters:
    attached_chart (bokeh.plotting.figure): The chart to add the range selector to
    source (bokeh.models.ColumnDataSource): The data source for the chart
    height (int): Height of the range selector in pixels
    
    Returns:
    bokeh.plotting.figure: The range selector chart.
    """
    df = source.to_df()
    metrics = [col for col in df.columns if col not in ['Datetime', 'index']]
    
    # Create the range selector figure
    select = figure(
        title="Drag to select a time range",
        height=CONFIG["chart_settings"]["range_selector_height"],
        width=CONFIG["chart_settings"]["range_selector_width"],
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
    hover_lines = [Span(location=0, dimension='height', line_color='grey',
                       line_width=1, line_dash='dashed', name=f"hover_line_{i}") for i, _ in enumerate(charts)]
    click_lines = [Span(location=0, dimension='height', line_color='red',
                       line_width=1, line_dash='solid', visible=False,
                       line_alpha=0.7, name=f"click_line_{i}") for i, _ in enumerate(charts)]
    
    # Create labels for each chart that will appear on click
    labels = []
    for i, chart in enumerate(charts):
        # Check if chart is a range selector by looking at its title
        if (hasattr(chart, 'title') and chart.title.text == "Drag to select a time range"):
            # Range selector has no invisible label
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

    # Add spans to charts
    for chart, hover_line, click_line in zip(charts, hover_lines, click_lines):
        chart.add_layout(hover_line)
        chart.add_layout(click_line)

    #---JS Callbacks (Cleaned Up - Calling Global Functions)---

    # Hover Callback
    hover_callback = CustomJS(
        # Args needed by the global handleHover function
        args={'hoverLines': hover_lines}, # Pass the list of hover_line models
        # Code simply calls the global function
        code="""
            // console.log("Hover event triggered"); // Optional debug
            if (typeof window.handleHover === 'function') {
                // handleHover expects the models list and cb_data
                window.handleHover(hoverLines, cb_data);
            } else {
                console.error('window.handleHover not defined!');
            }
        """
    )

    # Click Callback
    click_callback = CustomJS(
        # Args needed by the global handleTap function
        args={
            'charts': charts,
            'clickLines': click_lines, # Pass the list of click_line models
            'labels': labels,         # Pass the list of label models
            'sources': sources        # Pass sources dict
        },
        # Code simply calls the global function
        code="""
            // console.log('Tap callback executing.'); // Optional debug
            if (typeof window.handleTap === 'function') {
                // handleTap expects cb_obj, charts, clickLines, labels, sources
                window.handleTap(cb_obj, charts, clickLines, labels, sources);
            } else {
                console.error('window.handleTap not defined!');
            }
        """
    )

    # --- Tool Setup ---
    hover_tool = HoverTool(
        tooltips=None, # Tooltips managed by label now
        mode='vline',
        callback=hover_callback, # Attach the JS hover callback
        description="Vertical Line on Hover",
        name="Vertical Line on Hover"
    )

    # Add tools and attach tap event listener
    for chart in charts:
        chart.add_tools(hover_tool)
        # Attach the JS tap callback
        chart.js_on_event('tap', click_callback)

    # RETURN THE CREATED MODELS FOR GLOBAL INITIALIZATION
    return charts, click_lines, labels
