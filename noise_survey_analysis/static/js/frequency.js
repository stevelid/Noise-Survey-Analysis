/**
 * Frequency visualization functions for Noise Survey Analysis
 * 
 * This file contains functions for updating frequency visualizations
 * including spectrograms and frequency bar charts.
 */

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
            console.log('Using spectral source:', key);
            break;
        }
    }
    
    // Check if we found a spectral source
    if (!spectralSource) {
        console.log('No suitable spectral source found');
        return;
    }
    
    // Check for required columns
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
    console.log('Found closest time point:', new Date(clickTime).toLocaleString());
    
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
        freqBarSource.change.emit();
        console.log('Frequency bar chart updated with', newLabels.length, 'values');
    } catch (e) {
        console.error('Error updating frequency bar chart:', e);
    }
}

/**
 * Update spectrogram based on selected parameter
 * @param {string} param - Parameter to display (e.g., 'LZeq')
 * @param {Object} df - Data frame with frequency data
 * @param {Object} chart - Spectrogram chart to update
 * @param {Object} source - Data source for the spectrogram
 * @param {Array} frequencies - Array of frequency values
 */
function updateSpectrogram(param, df, chart, source, frequencies) {
    console.log('Updating spectrogram with parameter:', param);
    
    // Update chart title
    chart.title.text = chart.title.text.replace(/Spectrogram \(.*\)/, `Spectrogram (${param})`);
    
    // Extract times
    const times = df['Datetime'];
    
    // Compute widths per time
    let widths_per_time = [];
    if (times.length > 1) {
        for (let i = 0; i < times.length - 1; i++) {
            widths_per_time.push((times[i + 1] - times[i]));  // Time difference in ms
        }
        widths_per_time.push(widths_per_time[widths_per_time.length - 1]);  // Repeat last width
    } else {
        widths_per_time = [3600000];  // Default 1 hour
    }
    
    // Compute heights per frequency (linear scale for simplicity)
    let heights_per_freq = [];
    if (frequencies.length > 1) {
        for (let i = 0; i < frequencies.length - 1; i++) {
            heights_per_freq.push(frequencies[i + 1] - frequencies[i]);
        }
        heights_per_freq.push(heights_per_freq[heights_per_freq.length - 1]);
    } else {
        heights_per_freq = [frequencies[0] * 0.2];
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
        for (let j = 0; j < frequencies.length; j++) {
            const col_name = `${param}_${frequencies[j]}`;
            const value = df[col_name] ? df[col_name][i] : NaN;
            if (!isNaN(value)) {
                new_data.x.push(times[i]);
                new_data.y.push(frequencies[j]);
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
    
    console.log('Spectrogram updated with', new_data.value.length, 'values');
}

// Export functions for use in Bokeh callbacks
window.updateSpectrogram = updateSpectrogram; 