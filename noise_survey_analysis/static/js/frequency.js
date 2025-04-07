/**
 * Frequency visualization functions for Noise Survey Analysis
 * 
 * This file contains functions for updating frequency visualizations
 * including spectrograms and frequency bar charts.
 */

// Import core utility functions if we're in a Node.js environment
//let findClosestDateIndex, findClosestIndex;

// Check if we're in a Node.js testing environment
if (typeof require !== 'undefined') {
  // We're in a Node.js environment
  const coreModule = require('./core.js');
  findClosestDateIndex = coreModule.findClosestDateIndex;
  findClosestIndex = coreModule.findClosestIndex;
} else {
  // We're in a browser environment
  findClosestDateIndex = window.findClosestDateIndex;
  findClosestIndex = window.findClosestIndex;
}

/**
 * Update local references to global variables
 * Called periodically to ensure synchronization
 */
function updateGlobalReferences() {
    if (typeof window !== 'undefined') {
        globalVerticalLinePosition = window.globalVerticalLinePosition;
        globalActiveChartIndex = window.globalActiveChartIndex;
    }
}

/**
 * Update frequency bar chart based on a time value
 * @param {number} x - X position (timestamp) to find frequency data for
 * @param {Object} sources - Object containing all data sources
 */
function updateFrequencyBarChart(x, sources) {
    console.log('Updating frequency bar chart for time:', new Date(x).toLocaleString());
    
    // Check if we have the necessary sources
    if (!sources || !sources.hasOwnProperty('frequency_bar')) {
        console.log('No frequency_bar source available');
        return;
    }
    
    // Find the spectral source for the current position
    let spectralSource = null;
    let spectralKey = null;
    
    // Look for spectral sources in all available sources
    for (let key in sources) {
        if (key.includes('spectral') && sources[key].data && sources[key].data.hasOwnProperty('x')) {
            // Found a potential spectral source
            spectralSource = sources[key];
            spectralKey = key;
            break;
        }
    }
    
    // Check if we found a spectral source
    if (!spectralSource) {
        console.log('No suitable spectral source found');
        return;
    }
    
    // Check for required columns    
    if (!spectralSource.data || !spectralSource.data.hasOwnProperty('x') || !spectralSource.data.hasOwnProperty('y') || !spectralSource.data.hasOwnProperty('value')) {
        console.log('Spectral source does not have the expected data structure');
        console.log('Available columns:', Object.keys(spectralSource.data).join(', '));
        return;
    }
    const hasX = spectralSource.data.hasOwnProperty('x') && spectralSource.data.x.length > 0;
    const hasY = spectralSource.data.hasOwnProperty('y') && spectralSource.data.y.length > 0;
    const hasValue = spectralSource.data.hasOwnProperty('value') && spectralSource.data.value.length > 0;
    
    if (!hasX || !hasY || !hasValue) {
        console.log('Spectral source does not have the expected data structure');
        console.log('Available columns:', Object.keys(spectralSource.data).join(', '));
        return;
    }
    
    // Find the closest spectral data point to the click
    const closestIndex = findClosestIndex(spectralSource.data.x, x);
    if (closestIndex < 0) {
        console.log('Could not find a valid index for the click time');
        return;
    }
    
    const clickTime = spectralSource.data.x[closestIndex];
    
    // Extract frequency data for this time point
    const freqs = [];
    const values = [];
    const labels = [];
    
    // Time tolerance in milliseconds (1 second)
    const tolerance = 1000;
    
    // Get the frequency and value data for the selected time
    for (let i = 0; i < spectralSource.data.x.length; i++) {
        // Check if this data point is from the time we clicked on
        if (Math.abs(spectralSource.data.x[i] - clickTime) < tolerance) {
            const freq = spectralSource.data.y[i];  // Using 'y' for frequency
            const value = spectralSource.data.value[i];
            
            freqs.push(freq);
            values.push(value);
            labels.push(freq.toString() + ' Hz');
        }
    }
    
    if (!freqs || !values || !labels) {
        console.log('No frequency values found for the selected time');
        return;
    }
    if (freqs.length === 0) {
        console.log('No frequency values found for the selected time');
        return;
    }
    
    // Sort by frequency
    const sortedIndices = Array.from(Array(freqs.length).keys())
        .sort((a, b) => freqs[a] - freqs[b]);
    
    const sortedFreqs = sortedIndices.map(i => freqs[i]);
    const sortedValues = sortedIndices.map(i => values[i]);
    const sortedLabels = sortedIndices.map(i => labels[i]);
    
    // Make sure to create new arrays to avoid references
    const newFrequencies = [];
    const newLevels = [];
    const newLabels = [];
    
    // Copy values to ensure they're the right type
    for (let i = 0; i < sortedFreqs.length; i++) {
        newFrequencies.push(Number(sortedFreqs[i]));
        newLevels.push(Number(sortedValues[i]));
        newLabels.push(String(sortedLabels[i]));
    }
    
    // Get a direct reference to the frequency_bar source
    const freqBarSource = sources['frequency_bar'];
    
    // Update with a properly formatted object matching the expected structure
    freqBarSource.data = {
        'frequency_labels': newLabels,
        'levels': newLevels
    };
    
    // Update the x-range to match the new categories
    if (!window.chartRefs || window.chartRefs.length === 0) {
        console.log('No chart references found');
        return;
    }
    for (let i = 0; i < window.chartRefs.length; i++) {
        const chart = window.chartRefs[i];
        if (chart.title && chart.title.text && chart.title.text.includes('Frequency')) {
            // Update the categorical x-range
            chart.x_range.factors = newLabels;
            break;
        }
    }
    
    // Explicitly trigger data change
    try {
        console.log('Frequency bar chart updated with', newLabels.length, 'values');
        freqBarSource.change.emit();
    } catch (e) {
        console.error('Error updating frequency bar chart:', e);
    }
}

/**
 * Update bar chart from click line when tapping on any chart
 * @param {number} x - X position (timestamp) to find frequency data for
 * @param {number} activeChartIndex - Index of the active (clicked) chart
 * 
 * if x is null or undefined, reset the bar chart.
 * if x is valid, update the bar chart.
 * data for the position corresponding to the clicked chart is used if available, 
 * otherwise the first position in allPositionsSpectralData is used.
 * The bar chart title is updated with the position, parameter, and time.
 */
function updateBarChartFromClickLine(x, activeChartIndex) {
    
    // Get references to required objects - try passed params first, then global fallbacks
    const chartRefs = window.chartRefs;
    const allPositionsSpectralData = window.allPositionsSpectralData || {};
    const barSource = window.barSource || { data: {}, change: { emit: () => {} } };
    const barXRange = window.barXRange || { factors: [] };
    const paramHolder = window.selectedParamHolder || { data: { param: ['LZeq'] } };

    // For testing environment, create empty defaults if objects are missing
    let commonData = { n_freqs: 0, frequency_labels_str: [] };

    // Safety checks
    if (!chartRefs || !allPositionsSpectralData || !barSource || !barXRange) {
        console.warn("Missing required references for updateBarChartFromClickLine");
        console.log("chartRefs:", !!chartRefs);
        console.log("allPositionsSpectralData:", !!allPositionsSpectralData);
        console.log("barSource:", !!barSource);
        console.log("barXRange:", !!barXRange);
        
        // In test environment, still populate with empty data to avoid errors
        barSource.data['levels'] = [];
        barSource.data['frequency_labels'] = [];
        if (barSource.change && typeof barSource.change.emit === 'function') {
            barSource.change.emit();
        }
        return;
    }

    // find the bar chart
    const barChart = chartRefs.find(chart => chart && chart.name === 'frequency_bar');
    if (!barChart) {
        console.warn("No bar chart found");
        return;
    }
    
    // Get the active chart and its name (which should contain the position key)
    const activeChart = chartRefs[activeChartIndex];

    // if no valid tapline, reset the bar chart
    if (x === null || x === undefined || x <= 0) {
        if (barChart.title) {
            barChart.title.text = `Frequency Slice`;
        }
        if (commonData && commonData.n_freqs > 0) {
            barSource.data['levels'] = Array(commonData.n_freqs).fill(0);
        } else {
            barSource.data['levels'] = [];
        }
        if (barSource.change && typeof barSource.change.emit === 'function') {
            barSource.change.emit();
        }
        return;
    }  
    
    if (!activeChart || !activeChart.name) {
        console.warn("Invalid active chart or missing name property");
        return;
    }
    
    // Extract the position from the chart name (e.g., "SW_overview" => "SW")
    const chartName = activeChart.name;
    let position = chartName.split('_')[0];
    
    // Get the spectral_param_charts for this position
    let posParamCharts = window.spectralParamCharts || {};
    
    // Check if we have spectral data for this position
    if (!posParamCharts[position]) {
        // Fall back to first available position
        position = Object.keys(posParamCharts)[0];
        
        // Check if any spectral data exists
        if (!position) {
            console.warn("No spectral parameter data available for any position");
            return;
        }
    }
    
    // Get currently selected parameter from holder
    if (!paramHolder || !paramHolder.text) {
        console.warn("Missing parameter holder data");
        return;
    }
    
    const selectedParam = paramHolder.text;
    
    // Check if this parameter is available for this position
    const positionParamData = posParamCharts[position];
    const availableParams = positionParamData.available_params || [];
    
    if (!availableParams.includes(selectedParam)) {
        console.warn(`Parameter ${selectedParam} not available for position ${position}`);
        return;
    }
    
    // Get spectral data for this position and parameter from all_positions_spectral_data
    const positionData = allPositionsSpectralData[position];
    if (!positionData || !positionData[selectedParam]) {
        console.log(`No data for ${selectedParam} in position ${position}`);
        return;
    }
    
    const paramData = positionData[selectedParam];
    commonData = positionData.common || { n_freqs: 0, frequency_labels_str: [] };
    
    // Safety check for missing common data
    if (!commonData || !commonData.times_ms) {
        console.warn("Missing common spectral data");
        return;
    }
    
    // Find the closest time index for the clicked time
    const times = commonData.times_ms;
    let closestTimeIdx = -1;
    let minTimeDiff = Infinity;
    
    for (let i = 0; i < times.length; i++) {
        const diff = Math.abs(times[i] - x);
        if (diff < minTimeDiff) {
            minTimeDiff = diff;
            closestTimeIdx = i;
        } else if (diff > minTimeDiff && i > 0) {
            break; // Since times are sorted, diff will only increase
        }
    }
    
    if (closestTimeIdx === -1) {
        console.warn("Could not find closest time index");
        return;
    }
    
    // Extract frequency values at this time
    const nFreqs = commonData.n_freqs || 0;
    const startIdx = closestTimeIdx * nFreqs;
    const endIdx = startIdx + nFreqs;
    
    // Check if flattened data is available, or create an empty array
    const levelsFlat = paramData.levels_flat_nan || [];
    
    // Make sure the array is large enough
    if (startIdx >= levelsFlat.length) {
        console.warn("Data index out of bounds");
        barSource.data = {
            'frequency_labels': commonData.frequency_labels_str || [],
            'levels': Array(nFreqs).fill(0)
        };
    } else {
        // Slice the flattened array to get values for this time point
        let levelsSlice = levelsFlat.slice(startIdx, endIdx);
        
        // Replace NaN with 0 for display
        levelsSlice = levelsSlice.map(level => 
            (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);
        
        // Update bar chart
        barSource.data = {
            'frequency_labels': commonData.frequency_labels_str || [],
            'levels': levelsSlice
        };
    }
    
    // Update x-range factors
    if (barXRange && barXRange.factors) {
        barXRange.factors = commonData.frequency_labels_str || [];
    }

    // Update Label
    let labelString = `Frequency Slice`;
    if (x !== null && x !== undefined && x > 0) {
        labelString = `Frequency Slice: ${position} | ${selectedParam} | ${new Date(x).toLocaleString()}`;
    }
    
    if (barChart.title) {
        barChart.title.text = labelString;
    }
    
    // Trigger update
    if (barSource.change && typeof barSource.change.emit === 'function') {
        barSource.change.emit();
    }
}

/**
 * Handle hover events on a spectrogram
 * Updates hover information div and frequency bar chart based on cursor position
 *
 * @param {Object} cb_data - Callback data from Bokeh containing hover information
 * @param {Object} hover_div - The div element to show hover information
 * @param {Object} bar_source - Data source for the frequency bar chart
 * @param {Object} bar_x_range - X range object for the frequency bar chart
 * @param {string} position_name - The position name ('SW', 'N', etc.) of the hovered spectrogram. // <--- ADDED ARG
 * @param {Array} times_array - Array of time values in milliseconds
 * @param {Array} freqs_array - Array of frequency values
 * @param {Array} freq_labels_array - Array of frequency labels as strings
 * @param {Array} levels_matrix - 2D matrix of level values
 * @param {Array} levels_flat_array - Flattened array of level values
 * @param {Object} fig_x_range - X range of the spectrogram figure
 */
function handleSpectrogramHover(cb_data, hover_div, bar_source, bar_x_range, position_name, // <--- ADDED ARG
                               times_array, freqs_array, freq_labels_array, levels_matrix,
                               levels_flat_array, fig_x_range) {
    // Update references to global variables (if still needed, maybe not for this specific task)
    // updateGlobalReferences(); // Consider if this is still necessary here

    const {x: gx, y: gy} = cb_data.geometry;
    const div = hover_div;
    const bar_source_js = bar_source;
    const bar_x_range_js = bar_x_range;

    // Data arrays from Python
    const times = times_array;
    const freqs = freqs_array;
    const freq_labels_str = freq_labels_array;
    const levels_flat = levels_flat_array;

    const n_times = times.length;
    const n_freqs = freqs.length;
    const x_start = fig_x_range.start;
    const x_end = fig_x_range.end;

    // REMOVE THE COMPLEX FIND LOGIC
    // console.log("cb_data", cb_data); // Keep for debugging if needed
    const barChart = window.chartRefs.find(chart => chart.name === 'frequency_bar');
    // const spectrogram = window.chartRefs.find(chart => chart.renderers[0].id === cb_data.renderers[0].id); // <-- REMOVE THIS LINE

    const bar_data = bar_source_js.data;

    const is_inside = !(gx < x_start || gx > x_end || gy < -0.5 || gy > n_freqs - 0.5 || n_times === 0 || n_freqs === 0);

    if (is_inside && barChart) { // Added check for barChart
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
        let level_str_hover = (level_val_hover === null || level_val_hover === undefined || Number.isNaN(level_val_hover))
                              ? "N/A"
                              : level_val_hover.toFixed(1) + " dB";
        div.text = `<b>Time:</b> ${time_str} | <b>Freq:</b> ${freq_str} | <b>Level:</b> ${level_str_hover}`;
        div.change.emit();

        // --- Update Bar Chart ---
        const start_index_slice = time_idx * n_freqs;
        const end_index_slice = start_index_slice + n_freqs;
        let levels_slice = levels_flat.slice(start_index_slice, end_index_slice);

        if (levels_slice.length !== freq_labels_str.length) {
            console.error("Mismatch between levels_slice and freq_labels_str lengths!");
             // Optionally reset or return to prevent errors
             levels_slice = Array(freq_labels_str.length).fill(0);
        } else {
             levels_slice = levels_slice.map(level => (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);
        }


        bar_data['levels'] = levels_slice;
        bar_data['frequency_labels'] = freq_labels_str;
        bar_x_range_js.factors = freq_labels_str;

        const timeForTitle = new Date(time_val_ms).toLocaleTimeString(); // More concise time for title
        barChart.title.text = `Frequency Slice: ${position_name} | ${window.selectedParam} | ${timeForTitle}`; // <-- USE position_name

        bar_source_js.change.emit();

    } else {
        // Reset
        div.text = "Hover over spectrogram to view details";
        // Optionally reset bar chart more reliably or use last clicked position
        if (window.verticalLinePosition !== null && window.verticalLinePosition > 0 && window.activeChartIndex !== null && window.activeChartIndex >= 0) {
             if (typeof updateBarChartFromClickLine === 'function') {
                updateBarChartFromClickLine(window.verticalLinePosition, window.activeChartIndex);
             } else {
                // Fallback reset if function not found
                if (bar_data && n_freqs > 0) bar_data['levels'] = Array(n_freqs).fill(0);
             }

        } else {
             if (bar_data && n_freqs > 0) bar_data['levels'] = Array(n_freqs).fill(null);
             barChart.title.text = `Frequency Slice`;
        }
        if (bar_source_js) bar_source_js.change.emit(); // Ensure emit happens on reset too
    }
}

// Export functions for use in Bokeh callbacks
window.updateFrequencyBarChart = updateFrequencyBarChart;
window.updateBarChartFromClickLine = updateBarChartFromClickLine;
window.handleSpectrogramHover = handleSpectrogramHover;
window.updateGlobalReferences = updateGlobalReferences;

// Export for Node.js testing environment
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        updateFrequencyBarChart,
        updateBarChartFromClickLine,
        handleSpectrogramHover,
        updateGlobalReferences
    };
}