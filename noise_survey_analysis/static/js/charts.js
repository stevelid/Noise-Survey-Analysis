/**
 * charts.js
 * 
 * Chart interaction functionality for Noise Survey Analysis
 * 
 * This file contains functions for chart interactions including
 * hover effects, click events, vertical line synchronization,
 * and keyboard navigation.
 */

/**
 * Update a single chart's line model and label model properties at given x position.
 * Uses chart.name to find the correct data source.
 * @param {Object} chart - Bokeh chart object/model
 * @param {Object} clickLineModel - Vertical line span model object
 * @param {Object} labelModel - Label model object for displaying values
 * @param {number} x - X position for the line
 * @param {number} chartIndex - Index of the chart in the array
 * @returns {boolean} - True if update was successful
 */
function updateChartLine(chart, clickLineModel, labelModel, x, chartIndex) {
    if (!clickLineModel || !labelModel) {
        console.warn("Missing clickLineModel or labelModel for chart index:", chartIndex);
        return false;
    } 

    // Update line model properties
    clickLineModel.location = x;
    clickLineModel.visible = true;

    // --- Robust Source Finding using chart.name ---
    const sourceKey = chart.name; // Get the key assigned in Python
    let source = null;

    // Exclude charts that shouldn't have this type of label/source lookup
    // e.g., range selector, frequency bar, potentially spectrograms
    if (!sourceKey || sourceKey === 'range_selector' || sourceKey === 'frequency_bar' || sourceKey.includes('_spectral')) {
        // console.log(`Skipping label update for chart '${sourceKey || chart.title?.text}'`);
        labelModel.visible = false; // Ensure label is hidden for these types
        // Still return true because the line was updated
        return true;
    }

    // Find the source in the global sources object
    if (window.sources && window.sources.hasOwnProperty(sourceKey)) {
        source = window.sources[sourceKey];
    }

    // --- Update Label using the found source ---
    if (!source || !source.data || !source.data.Datetime) {
        console.warn(`Could not find valid data source for chart index: ${chartIndex}, Name: '${sourceKey}', Title: '${chart.title?.text}'`);
        labelModel.visible = false; // Hide label if source is invalid
        return true; // Line updated, label hidden
    }

    // If we have a valid source and Datetime data, update the label
    let closest_idx = findClosestDateIndex(source.data.Datetime, x);
    if (closest_idx !== -1) {
        let label_text = createLabelText(source, closest_idx); // Uses the correctly found source

        // Position the label model (uses chart for range info)
        positionLabel(labelModel, chart, x); // Pass the model

        // Update label model text and visibility
        labelModel.text = label_text;
        labelModel.visible = true;

        // Update step size for the active chart (using the found source)
        if (window.activeChartIndex === chartIndex) {
            window.stepSize = calculateStepSize(source);
            // console.log('Calculated stepSize for chart ' + chartIndex + ':', window.stepSize);
        }
        return true;
    } else {
        console.warn(`Could not find closest date index for chart '${sourceKey}'`);
        labelModel.visible = false;
        return true; // Line updated, label hidden
    }

  
    /* OLD IMPLEMENTATION
    
    // Find renderer with data source
    let renderers = chart.renderers.filter(r => r.data_source);
    let mainRenderer = renderers.find(r => r.type.includes('Line') || r.type.includes('Scatter')) || renderers[0];
    
    // If we have valid data source, update label
    if (mainRenderer && mainRenderer.data_source && mainRenderer.data_source.data.Datetime) {
        let closest_idx = findClosestDateIndex(mainRenderer.data_source.data.Datetime, x);
        let label_text = createLabelText(mainRenderer.data_source, closest_idx);
        
        positionLabel(label, chart, x);
        label.text = label_text;
        label.visible = true;
        
        // Update step size for active chart
        if (window.activeChartIndex === chartIndex) {
            let source = mainRenderer.data_source;
            window.stepSize = calculateStepSize(source);
            console.log('Calculated stepSize for chart ' + chartIndex + ':', window.stepSize);
        }
        
        return true;
    } else {
        console.log('No valid renderer or Datetime data for chart', chartIndex);
        return false;
    } */
}

/**
 * Update all chart line models to the given x position
 * @param {number} x - X position for the lines
 * @param {Array} charts - Array of chart models
 * @param {Array} clickLineModels - Array of click line span models
 * @param {Array} labelModels - Array of label models
 */
function updateAllLines(x, charts, clickLineModels, labelModels) {
    console.log("updateAllLines called with x:", new Date(x).toISOString());
    window.verticalLinePosition = x; // Store current position globally
    
    // Update lines for all charts
    for (let i = 0; i < charts.length; i++) {
        updateChartLine(
            charts[i], 
            clickLineModels[i], 
            labelModels[i], 
            x, 
            i
        );
    }
    
    // Update frequency bar chart if the function exists and sources are available
    if (typeof updateFrequencyBarChart === 'function' && window.sources) {
        updateFrequencyBarChart(x, window.sources);
    } else {
        if (typeof updateFrequencyBarChart !== 'function') console.log("updateFrequencyBarChart not defined");
        if (!window.sources) console.log("window.sources not available for frequency chart update");
    }
}

/**
 * Handle hover events on charts
 * @param {Array} hoverLinesModels - Array of hover line span objects
 * @param {Object} cb_data - Callback data from Bokeh
 */
function handleHover(hoverLinesModels, cb_data, chart_index) {
    console.log("[handleHover] called with chart_index:", chart_index);
    if (!hoverLinesModels) return;
    let geometry = cb_data['geometry'];
    if (geometry) {
        let x = geometry['x'];
        // Update all hover lines
        for (let i = 0; i < hoverLinesModels.length; i++) {
            if (hoverLinesModels[i]) {
                hoverLinesModels[i].location = x;
            }
        }
    }
}

/**
 * Handle tap/click events on charts
 * @param {Object} cb_obj - Click event object from Bokeh
 * @param {Array} charts - Array of chart objects
 * @param {Array} clickLineModels - Array of click line span objects
 * @param {Array} labelModels - Array of label objects
 * @param {Object} sources - Data sources (passed from Python args)
 */
function handleTap(cb_obj, charts, clickLineModels, labelModels, sources) {
    console.log('Tap event triggered');
    
    // Store models globally for keyboard nav / playback updates
    // This happens on every tap, ensuring they are current if the chart set changes dynamically (unlikely here)
    //window.clickLineModels = clickLineModels;
    //window.labelModels = labelModels;
    // Ensure window.sources is also set (redundant if initializeReferences worked, but safe)
    //window.sources = sources;
    
    let x = cb_obj.x;
    console.log('Tap x position:', x, new Date(x).toISOString());
    
    // Determine which chart was clicked
    window.activeChartIndex = -1; // Reset
    for (let i = 0; i < charts.length; i++) {
        // Compare BokehJS model IDs for robust matching
        if (cb_obj.origin && cb_obj.origin.id === charts[i].id) {
            window.activeChartIndex = i;
            console.log("Clicked chart index:", i, "Title:", charts[i].title?.text);
            break;
        }
    }
    if (window.activeChartIndex === -1) {
        console.warn("Could not identify clicked chart.");
        // Optionally, try a less robust comparison if ID match fails
        for (let i = 0; i < charts.length; i++) {
           if (cb_obj.origin === charts[i]) { // Fallback to direct object comparison
                window.activeChartIndex = i;
                console.log("Clicked chart index (fallback match):", i, "Title:", charts[i].title?.text);
                break;
           }
        }
   }
    

    
    if (x === undefined || x === null) {
        // Hide all lines and labels
        console.log("Invalid x position from tap event.");
        for (let i = 0; i < clickLineModels.length; i++) {
            if (clickLineModels[i]) clickLineModels[i].visible = false;
            if (labelModels[i]) labelModels[i].visible = false;
        }
    } else {
        
        if (!window.playback_source) {
            console.error("playback_source not available in handleTap!");
            return; // Or handle error appropriately
        }
        
        // Update all lines/labels by modifying the models
        updateAllLines(x, window.chartRefs, window.clickLineModels, window.labelModels);

        // *** Update the playback_source ***
        console.log('Tap: Updating playback_source time to:', new Date(x).toISOString());
        window.playback_source.data = {'current_time': [x]};
        window.playback_source.change.emit();
    }
}

/**
 * Enable keyboard navigation for charts
 */
function enableKeyboardNavigation() {
    
    if (!window.keyboardNavigationEnabled) {
        window.keyboardNavigationEnabled = true;
        document.addEventListener('keydown', handleKeyPress);
        console.log('Keyboard navigation enabled');
    }
}

/**
 * Handle keyboard navigation events
 * @param {Event} e - Keyboard event
 */
function handleKeyPress(e) {

    //check if models are available
    if (!window.chartRefs || !window.clickLineModels || !window.labelModels || !window.playback_source) {
        console.warn("Cannot navigate with keyboard: chart/line/label/playback models not ready.");
        console.log('chartRefs:', window.chartRefs);
        console.log('clickLineModels:', window.clickLineModels);
        console.log('labelModels:', window.labelModels);
        console.log('playback_source:', window.playback_source);
        return;
    }
        
    // --- Arrow Key Navigation ---
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault(); // Prevent browser default scrolling

        let currentX = window.verticalLinePosition || window.playback_source.data.Time[0] ||
                       (window.chartRefs[0].x_range.start + window.chartRefs[0].x_range.end) / 2;
        
        // Use stepSize calculated based on the *active* chart's data, or default
        let step = window.stepSize || 300000;  // Default to 5 minutes if not set
        let newX = e.key === 'ArrowLeft' ? currentX - step : currentX + step;
        
        // Clamp newX to the overall time range of the data 
        let allTimes = [];
        Object.values(window.sources).forEach(s => { if(s.data.Datetime) allTimes.push(...s.data.Datetime); });
        let minTime = Math.min(...allTimes);
        let maxTime = Math.max(...allTimes);

        newX = Math.max(minTime, Math.min(maxTime, newX));
        let time_ms = newX;

        // *** Update the playback_source ***
        if (window.playback_source) {
            
            console.log('Key Nav: Updating playback_source time to:', new Date(time_ms).toISOString());
            window.playback_source.data = {'current_time': [time_ms]};
            window.playback_source.change.emit(); // Notify Bokeh of the change
        } else {
            console.warn("Cannot update playback_source: playback_source not available.");
        }

        // Update lines using the globally stored models
        updateAllLines(time_ms, window.chartRefs, window.clickLineModels, window.labelModels);

    }
    // --- Spacebar Play/Pause ---
    else if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        console.log("Spacebar pressed.");
        // Check if button models are available
        if (!window.play_button_model || !window.pause_button_model) { // Check original buttons
            console.warn("Cannot toggle playback: Play/Pause button models not available.");
            return;
        }

        // *** Revert to trying .active = true ***
        // This might not work reliably to trigger Python on_click
        if (window.pause_button_model.disabled === false) {
             console.log("Attempting to click Pause button via Spacebar (.active)");
             window.pause_button_model.active = true;
        } else if (window.play_button_model.disabled === false) {
            console.log("Attempting to click Play button via Spacebar (.active)");
            window.play_button_model.active = true;
        } else {
             console.log("Both Play and Pause buttons seem disabled.");
        }
   }
}

/**
 * Synchronize ranges between multiple charts
 * @param {Array} charts - Array of chart objects to synchronize
 */
function syncChartRanges(charts) {
    // Skip if there's only one chart
    if (!charts || charts.length <= 1) return;
    
    console.log('Setting up range synchronization for', charts.length, 'charts');
    
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
        freqBarSource.change.emit();
    } catch (e) {
        console.error('Error updating frequency bar chart:', e);
    }
}



// Export functions for use in Bokeh callbacks
window.updateAllLines = updateAllLines;
window.handleHover = handleHover;
window.handleTap = handleTap;
window.enableKeyboardNavigation = enableKeyboardNavigation;
 