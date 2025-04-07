"""
JavaScript callback functions for interactive visualizations.

This module contains JavaScript code that will be passed to Bokeh CustomJS objects.
The code is organized into clearly scoped functions with proper initialization.
"""

def get_common_utility_functions():
    """
    Returns common JavaScript utility functions used across different callbacks.
    
    This function provides core utility functions that must be initialized before
    other JavaScript functions can be used. It defines global variables and
    helper functions in the browser context.
    
    Returns:
    str: JavaScript code with utility functions
    """
    #return 
    """
    // Initialize global references
    window.chartRefs = charts;
    window.clickLineRefs = [];
    window.labelRefs = [];
    
    // Find and store all click lines and labels
    for (let i = 0; i < charts.length; i++) {
        let clickLine = null;
        let label = null;
        
        // Find click line and label in chart
        charts[i].renderers.forEach(function(renderer) {
            if (renderer.type === "Span" && renderer.name && renderer.name.includes("click_line")) {
                clickLine = renderer;
            }
            if (renderer.type === "Label") {
                label = renderer;
            }
        });
        
        window.clickLineRefs.push(clickLine);
        window.labelRefs.push(label);
    }
    
    console.log('Initialized updateAllLines function and references');
    
    // Helper function to find the closest index in an array to a target value
    function findClosestIndex(array, target) {
        if (!array || array.length === 0) return -1;
        
        var minDiff = Infinity;
        var closestIndex = -1;
        
        for (var i = 0; i < array.length; i++) {
            var diff = Math.abs(array[i] - target);
            if (diff < minDiff) {
                minDiff = diff;
                closestIndex = i;
            }
        }
        
        return closestIndex;
    }
    
    // Find closest index in a date array to a given x position
    function findClosestDateIndex(dates, x) {
        var closest_idx = 0;
        var min_diff = Math.abs(dates[0] - x);
        for (var j = 1; j < dates.length; j++) {
            var diff = Math.abs(dates[j] - x);
            if (diff < min_diff) {
                min_diff = diff;
                closest_idx = j;
            }
        }
        return closest_idx;
    }
    
    // Create label text from data source at given index
    function createLabelText(source, closest_idx) {
        var date = new Date(source.data.Datetime[closest_idx]);
        var formatted_date = date.toLocaleString();
        var label_text = 'Time: ' + formatted_date + '\\n';
        
        for (var key in source.data) {
            if (key !== 'Datetime' && key !== 'index') {
                var value = source.data[key][closest_idx];
                if (value !== undefined && !isNaN(value)) {
                    var formatted_value = parseFloat(value).toFixed(1);
                    label_text += key + ': ' + formatted_value + ' dB\\n';
                }
            }
        }
        return label_text;
    }
    
    // Position label based on x position and chart boundaries
    function positionLabel(label, chart, x) {
        var offset = (chart.x_range.end - chart.x_range.start) * 0.01;
        if (x + offset*15 > chart.x_range.end) {
            label.x = x - offset;
            label.text_align = 'right';
        } else {
            label.x = x + offset;
            label.text_align = 'left';
        }     
        label.y = chart.y_range.end;
    }
    
    // Update a single chart's line and label at given x position
    function updateChartLine(chart, click_line, label, x, chartIndex) {
        if (x < chart.x_range.start || x > chart.x_range.end) {
            click_line.visible = false;
            console.log('Chart', chartIndex, 'out of range');
            label.visible = false;
            return false;
        } else {
            click_line.location = x;
            click_line.visible = true;
            
            var renderers = chart.renderers.filter(r => r.data_source);
            var mainRenderer = renderers.find(r => r.type.includes('Line') || r.type.includes('Scatter')) || renderers[0];
            
            if (mainRenderer && mainRenderer.data_source && mainRenderer.data_source.data.Datetime) {
                var closest_idx = findClosestDateIndex(mainRenderer.data_source.data.Datetime, x);
                var label_text = createLabelText(mainRenderer.data_source, closest_idx);
                positionLabel(label, chart, x);
                label.text = label_text;
                label.visible = true;
            } else {
                console.log('No valid renderer or Datetime data for chart', chartIndex);
            }
        }
    
        // Update step size for active chart
        if (window.activeChartIndex === chartIndex && mainRenderer.data_source.data.Datetime.length > 10) {
            window.stepSize = Math.abs(mainRenderer.data_source.data.Datetime[10] - mainRenderer.data_source.data.Datetime[9]);
            console.log('Calculated stepSize for chart ' + chartIndex + ': ' + window.stepSize);
        } else {
            console.log('Step size not calculated');
        }
    }
    
    // Unified updateAllLines function
    window.updateAllLines = function(x) {
        console.log('window.updateAllLines called with x =', x);
        window.chartRefs = window.chartRefs || charts;  // Fallback to charts arg if not set
        window.clickLineRefs = window.clickLineRefs || [];
        window.labelRefs = window.labelRefs || [];
        
        for (var i = 0; i < window.chartRefs.length; i++) {
            if (window.clickLineRefs[i]) {  // Only proceed if click_line exists
                updateChartLine(window.chartRefs[i], window.clickLineRefs[i], window.labelRefs[i], x, i);
            } else {
                console.log("Skipping chart", i, "due to missing click_line");
            }
        }
        if (sources) {
            updateFrequencyBarChart(x);
        }
        window.verticalLinePosition = x;
    }
    
    // Function to update frequency bar chart based on a time value
    function updateFrequencyBarChart(x) {
        // Find the spectral source for the current position
        if (!(window.kb_sources && window.kb_sources.hasOwnProperty('frequency_bar'))) {
            return;
        }
        var spectralSource = null;
        var spectralKey = null;
        
        // Look for spectral sources in all available sources
        for (var key in sources) {
            if (key.includes('spectral') && sources[key].data && sources[key].data.hasOwnProperty('x')) {
                // Found a potential spectral source
                spectralSource = sources[key];
                spectralKey = key;
                break;
            }
        }
        
        // Check if we found a spectral source
        if (spectralSource) {
            
            // Check for required columns
            var hasX = spectralSource.data.hasOwnProperty('x') && spectralSource.data.x.length > 0;
            var hasY = spectralSource.data.hasOwnProperty('y') && spectralSource.data.y.length > 0;
            var hasValue = spectralSource.data.hasOwnProperty('value') && spectralSource.data.value.length > 0;
            
            // Check if the spectral source has the expected structure
            if (hasX && hasY && hasValue) {
                
                // Find the closest spectral data point to the click
                var closestIndex = findClosestIndex(spectralSource.data.x, x);
                
                if (closestIndex >= 0) {
                    var clickTime = spectralSource.data.x[closestIndex];
                    
                    // Extract frequency data for this time point
                    var freqs = [];
                    var values = [];
                    var labels = [];
                    
                    // Get the frequency and value data for the selected time
                    if (spectralSource.data.y && spectralSource.data.value) {
                        // Time tolerance in milliseconds (1 second)
                        var tolerance = 1000;
                        
                        for (var i = 0; i < spectralSource.data.x.length; i++) {
                            // Check if this data point is from the time we clicked on
                            if (Math.abs(spectralSource.data.x[i] - clickTime) < tolerance) {
                                var freq = spectralSource.data.y[i];  // Using 'y' for frequency
                                var value = spectralSource.data.value[i];
                                
                                freqs.push(freq);
                                values.push(value);
                                labels.push(freq.toString() + ' Hz');
                            }
                        }
                    }
                    
                    // Sort by frequency
                    var sortedIndices = Array.from(Array(freqs.length).keys())
                        .sort((a, b) => freqs[a] - freqs[b]);
                    
                    var sortedFreqs = sortedIndices.map(i => freqs[i]);
                    var sortedValues = sortedIndices.map(i => values[i]);
                    var sortedLabels = sortedIndices.map(i => labels[i]);
                    
                    if (sortedFreqs.length > 0) {
                        // Make sure to create new arrays to avoid references
                        var newFrequencies = [];
                        var newLevels = [];
                        var newLabels = [];
                        
                        // Copy values to ensure they're the right type
                        for (var i = 0; i < sortedFreqs.length; i++) {
                            newFrequencies.push(Number(sortedFreqs[i]));
                            newLevels.push(Number(sortedValues[i]));
                            newLabels.push(String(sortedLabels[i]));
                        }
                        
                        // Get a direct reference to the frequency_bar source
                        var freqBarSource = sources['frequency_bar'];
                        
                        // Update with a properly formatted object matching the expected structure
                        // UPDATED: Now using frequency_labels as the categorical x-axis
                        freqBarSource.data = {
                            'frequency_labels': newLabels,
                            'levels': newLevels
                        };
                        
                        // Update the x-range to match the new categories
                        for (var i = 0; i < charts.length; i++) {
                            if (charts[i].title && charts[i].title.text && 
                                charts[i].title.text.includes('Frequency')) {
                                // Update the categorical x-range
                                charts[i].x_range.factors = newLabels;
                                break;
                            }
                        }
                        
                        // Explicitly trigger data change
                        try {
                            freqBarSource.change.emit();
                        } catch (e) {
                            console.error('Error updating frequency bar chart:', e);
                        }
                    } else {
                        console.log('No frequency values found for the selected time');
                    }
                } else {
                    console.log('Could not find a valid index for the click time');
                }
            } else {
                console.log('Spectral source does not have the expected data structure');
                console.log('Available columns:');
                for (var key in spectralSource.data) {
                    console.log(' - ' + key);
                }
            }
        } else {
            console.log('No suitable spectral source found');
        }
    }
    """


def get_hover_line_js(num_lines):
    """
    Generate JavaScript code for synchronized hover line movement across multiple charts.
    
    Parameters:
    num_lines (int): Number of charts/lines to synchronize
    
    Returns:
    str: JavaScript code as string
    """
    hover_code = """
        var geometry = cb_data['geometry'];
        if (geometry) {
            var x = geometry['x'];
    """
    for i in range(num_lines):
        hover_code += f"""
            hover_line_{i}.location = x;
        """
    hover_code += "}"
    
    return hover_code


def get_click_line_js(num_lines):
    """
    Generate JavaScript code for click events on charts.
    
    Parameters:
    num_lines (int): Number of charts/lines to synchronize
    
    Returns:
    str: JavaScript code as string
    """
    # Include common utility functions
    click_code = """
        console.log('Tap event triggered');
        
        var x = cb_obj.x;
        console.log('X position: ' + x);
        
        // Determine which chart was clicked
        window.activeChartIndex = -1;  // Default to -1 (no chart)
        
        // Use the origin property to identify the chart
        for (let i = 0; i < charts.length; i++) {
            if (cb_obj.origin === charts[i]) {
                console.log("Clicked chart ID:", i);
                window.activeChartIndex = i;
                break;
            } 
        }
        
        window.verticalLinePosition = x;
        
        if (x === undefined || x === null) {
    """
    for i in range(num_lines):
        click_code += f"""
            click_line_{i}.visible = false;
            label_{i}.visible = false;
    """

    click_code += """
        } else {
            window.updateAllLines(x);  // Single call to update all lines
            enableKeyboardNavigation();
        }
    """
    
    return click_code


def get_keyboard_navigation_js(num_lines):
    """
    Generate JavaScript code for keyboard navigation.
    
    Parameters:
    num_lines (int): Number of charts/lines to synchronize
    
    Returns:
    str: JavaScript code as string
    """
    return """
    if (!window.kb_initialized) {
        window.kb_initialized = true;
        window.kb_charts = [];
        window.kb_click_lines = [];
        window.kb_labels = [];
        window.kb_sources = null;
        
        setTimeout(function() {
            console.log('Initializing keyboard navigation...');
            for (var i = 0; i < """ + str(num_lines) + """; i++) {
                var chartRef = eval('chart_' + i);
                var clickLine = eval('click_line_' + i);
                var label = eval('label_' + i);
                if (chartRef) window.kb_charts.push(chartRef);
                if (clickLine) window.kb_click_lines.push(clickLine);
                if (label) window.kb_labels.push(label);
            }
            if (typeof sources !== 'undefined') window.kb_sources = sources;
            window.chartRefs = window.kb_charts;  // Sync with global refs
            window.clickLineRefs = window.kb_click_lines;
            window.labelRefs = window.kb_labels;
            console.log('Found', window.kb_charts.length, 'charts');
            enableKeyboardNavigation();
        }, 1000);
    }
    
    function enableKeyboardNavigation() {
        if (!window.keyboardNavigationEnabled) {
            window.keyboardNavigationEnabled = true;
            document.addEventListener('keydown', function(e) {
                if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
                    var currentX = window.verticalLinePosition || (window.kb_charts[0].x_range.start + window.kb_charts[0].x_range.end) / 2;
                    var step = window.stepSize || 3600000;  // Default to 1 hour if not set
                    var newX = e.key === 'ArrowLeft' ? currentX - step : currentX + step;
                    var activeChart = window.kb_charts[window.activeChartIndex >= 0 ? window.activeChartIndex : 0];
                    newX = Math.max(activeChart.x_range.start, Math.min(activeChart.x_range.end, newX));
                    window.updateAllLines(newX);
                    e.preventDefault();
                }
            });
            console.log('Keyboard navigation enabled');
        }
    }
    """


def get_shared_chart_tools_js():
    """
    Returns JavaScript code for shared tools between charts.
    
    Returns:
    str: JavaScript code as string
    """
    return """
    // Get all charts in the document
    const charts = Object.values(Bokeh.documents[0].get_model_by_name())
                        .filter(model => model.type == "Plot");
    
    // Function to synchronize range
    function syncRange(sourceChart, targetCharts) {
        const xstart = sourceChart.x_range.start;
        const xend = sourceChart.x_range.end;
        
        for (const chart of targetCharts) {
            if (chart !== sourceChart) {
                chart.x_range.start = xstart;
                chart.x_range.end = xend;
            }
        }
    }
    
    // Apply synchronization to all charts
    for (const chart of charts) {
        chart.x_range.on_change('start', function() {
            syncRange(chart, charts);
        });
        chart.x_range.on_change('end', function() {
            syncRange(chart, charts);
        });
    }
    """


def get_update_spectrogram_js():
    """
    Generate JavaScript code for updating the spectrogram based on selected parameter.
    
    Returns:
    str: JavaScript code as string
    """
    return """
        // Get selected parameter
        const param = cb_obj.value;
            
        // Update chart title
        chart.title.text = chart.title.text.replace(/Spectrogram \\(.*\\)/, `Spectrogram (${param})`);
            
        // Extract frequencies and times
        const freqs = frequencies;
        const times = df['Datetime'];
            
        // Compute widths per time
        let widths_per_time = [];
        if (times.length > 1) {
            for (let i = 0; i < times.length - 1; i++) {
                widths_per_time.push((times[i + 1] - times[i]) / 1000);  // Convert to milliseconds
            }
            widths_per_time.push(widths_per_time[widths_per_time.length - 1]);  // Repeat last width
        } else {
            widths_per_time = [3600000];  // Default 1 hour
        }
            
        // Compute heights per frequency (linear scale for simplicity)
        let heights_per_freq = [];
        if (freqs.length > 1) {
            for (let i = 0; i < freqs.length - 1; i++) {
                heights_per_freq.push(freqs[i + 1] - freqs[i]);
            }
            heights_per_freq.push(heights_per_freq[heights_per_freq.length - 1]);
        } else {
            heights_per_freq = [freqs[0] * 0.2];
        }
            
        // Prepare new data
        let new_data = {
            x: [],
            y: [],
            width: [],
            height: [],
            value: []
        };
            
        // Populate data for the selected parameter
        for (let i = 0; i < times.length; i++) {
            for (let j = 0; j < freqs.length; j++) {
                const col_name = `${param}_${freqs[j]}`;
                const value = df[col_name] ? df[col_name][i] : NaN;
                if (!isNaN(value)) {
                    new_data.x.push(times[i]);
                    new_data.y.push(freqs[j]);
                    new_data.width.push(widths_per_time[i]);
                    new_data.height.push(heights_per_freq[j]);
                    new_data.value.push(value);
                }
            }
        }
            
        // Update color mapper range
        const values = new_data.value;
        if (values.length > 0) {
            const min_val = Math.min(...values);
            const max_val = Math.max(...values);
            chart.right[0].color_mapper.low = min_val;
            chart.right[0].color_mapper.high = max_val;
        }
            
        // Update data source
        source.data = new_data;
        source.change.emit();
    """ 