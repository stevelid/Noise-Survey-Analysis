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


}

/**
 * Update all line models to the given x position on all charts
 * @param {number} x - X position for the lines
 * @param {Array} charts - Array of chart models
 * @param {Array} clickLineModels - Array of click line span models
 * @param {Array} labelModels - Array of label models
 */
function updateTapLinePositions(x, charts, clickLineModels, labelModels) {
    window.verticalLinePosition = x; // Store current position globally

    for (let i = 0; i < charts.length; i++) {
        if (charts[i].name === 'frequency_bar') continue;
        updateChartLine(
            charts[i], 
            clickLineModels[i], 
            labelModels[i], 
            x, 
            i
        );
    }
}

/**
 * Handle hover events on charts
 * @param {Array} hoverLinesModels - Array of hover line span objects
 * @param {Object} cb_data - Callback data from Bokeh
 * @param {Array} charts - Array of chart objects
 * @param {Object} sources - Dictionary of data sources
 * @param {Object} bar_source - The frequency bar chart data source
 * @param {Object} bar_x_range - The x range for the frequency bar chart
 * @param {Object} selected_param_holder - The holder for selected parameter
 * @param {Object} all_positions_spectral_data - Dictionary of pre-calculated spectral data
 */
function handleHover(hoverLinesModels, cb_data, charts, sources, bar_source, bar_x_range, 
                     selected_param_holder, all_positions_spectral_data) {
    if (!hoverLinesModels) return;
    
    // Get hover position
    let geometry = cb_data['geometry'];
    if (!geometry || typeof geometry.x !== 'number') return;
    
    let hoveredX = geometry.x;
    
    // Update hover lines
    for (let i = 0; i < hoverLinesModels.length; i++) {
        if (hoverLinesModels[i]) {
            hoverLinesModels[i].location = hoveredX;
        }
    }
    
    // Determine which chart is being hovered over
    let hoveredChart = null;
    let hoveredChartIndex = -1;
    
    // Check if the event includes the model/origin
    if (cb_data.geometries && cb_data.geometries.length > 0 && cb_data.geometries[0].model) {
        // Find the chart by model ID
        const hoveredModelId = cb_data.geometries[0].model.id;
        for (let i = 0; i < charts.length; i++) {
            if (charts[i].id === hoveredModelId) {
                hoveredChart = charts[i];
                hoveredChartIndex = i;
                break;
            }
        }
    }
    
    // If chart not found by model, try using coordinates
    if (!hoveredChart && typeof hoveredX === 'number' && typeof geometry.y === 'number') {
        for (let i = 0; i < charts.length; i++) {
            const chart = charts[i];
            
            // Skip range_selector or frequency_bar charts
            if (chart.name === 'range_selector' || chart.name === 'frequency_bar') continue;
            
            // Check if hover position is within chart bounds
            const inXRange = hoveredX >= chart.x_range.start && hoveredX <= chart.x_range.end;
            const inYRange = true; // We only care about x-position for line charts
            
            if (inXRange && inYRange) {
                hoveredChart = chart;
                hoveredChartIndex = i;
                break;
            }
        }
    }
    
    // If we have a hovered chart, extract the position
    if (hoveredChart && hoveredChart.name) {
        // Extract position key from chart name (e.g., "SW_overview" -> "SW")
        const position = hoveredChart.name.split('_')[0];
        
        // Check if chart is a line chart (overview or log, not spectral)
        const isLineChart = hoveredChart.name.includes('_overview') || hoveredChart.name.includes('_log');
        
        if (isLineChart && position) {
            // We're hovering over a line chart, update the bar chart if we have spectral data
            
            // Use globally available arguments or the ones passed directly
            const actualBarSource = bar_source || window.barSource;
            const actualBarXRange = bar_x_range || window.barXRange;
            const actualAllPositionsData = all_positions_spectral_data || window.allPositionsSpectralData;
            const actualParamHolder = selected_param_holder || window.selectedParamHolder;
            
            if (actualBarSource && actualBarXRange && actualAllPositionsData && 
                actualAllPositionsData[position] && actualParamHolder) {
                
                // Get the currently selected parameter
                let selectedParam = 'LZeq'; // Default fallback
                if (actualParamHolder.data && actualParamHolder.data.param && actualParamHolder.data.param.length > 0) {
                    selectedParam = actualParamHolder.data.param[0];
                }
                
                // Store the active chart index so tap can reuse it
                window.activeChartIndex = hoveredChartIndex;
                
                // Call the helper to update the bar chart with spectral data for this position
                if (typeof updateBarChartFromClickLine === 'function') {
                    console.log(`Hover: Updating bar chart for position ${position} at time ${new Date(hoveredX).toLocaleString()}`);
                    updateBarChartFromClickLine(hoveredX, hoveredChartIndex);
                }
            }
        }
    } else {
        // If we're not hovering over a valid chart, restore the bar chart to the click line position
        // (only if we have a valid click position and chart stored)
        if (typeof updateBarChartFromClickLine === 'function' && 
            window.verticalLinePosition && window.activeChartIndex >= 0) {
            updateBarChartFromClickLine(window.verticalLinePosition, window.activeChartIndex);
        }
    }
}

// ------------- Tap/Click Events -------------

/**
 * Handle tap/click events on charts
 * @param {Object} cb_obj - Click event object from Bokeh
 * @param {Array} clickLineModels - Array of click line span objects
 * @param {Array} labelModels - Array of label objects
 * @param {Object} sources - Data sources (passed from Python args)
 * @param {Object} bar_source - The frequency bar chart data source
 * @param {Object} bar_x_range - The x range for the frequency bar chart
 * @param {Object} selected_param_holder - The holder for selected parameter
 * @param {Object} all_positions_spectral_data - Dictionary of pre-calculated spectral data
 */
function handleTap(cb_obj, clickLineModels, labelModels, sources,
                  bar_source, bar_x_range, selected_param_holder, 
                  all_positions_spectral_data) {
    
    // Check if global initialization was completed
    if (!globalInitialized) {
        console.warn("Charts.js called before initialization completed.");
        // No need to manually call initializeReferences here - it should be completed by the DocumentReady event
        // Let's check if we have global access to the necessary components
        if (!globalChartRefs || !globalClickLineModels || !globalLabelModels || !globalPlaybackSource) {
            console.error("Missing required global references. Charts:", !!globalChartRefs, 
                          "Click lines:", !!globalClickLineModels, 
                          "Labels:", !!globalLabelModels, 
                          "Playback source:", !!globalPlaybackSource);
            return;
        }
    }
    
    charts = globalChartRefs;
    window.activeChartIndex = getActiveChartIndex(cb_obj, charts);
    let x = cb_obj.x;   
    
    if (x === undefined || x === null) {
        //outside of all charts
        hideAllLinesAndLabels(clickLineModels, labelModels);
    } else {
        
        updateTapLinePositions(x, window.chartRefs, window.clickLineModels, window.labelModels);
        updatePlaybackSource(x);
        updateBarChartFromClickLine(x, window.activeChartIndex);       

    }
}

function getActiveChartIndex(cb_obj, charts) {
    // Determine which chart was clicked
    let activeChartIndex = -1; // Reset
    for (let i = 0; i < charts.length; i++) {
        // Compare BokehJS model IDs for robust matching
        if (cb_obj.origin && cb_obj.origin.id === charts[i].id) {
            activeChartIndex = i;
            console.log("Clicked chart index:", i, "Title:", charts[i].title?.text);
            break;
        }
    }
    if (activeChartIndex === -1) {
        console.warn("Could not identify clicked chart.");
        // Optionally, try a less robust comparison if ID match fails
        for (let i = 0; i < charts.length; i++) {
           if (cb_obj.origin === charts[i]) { // Fallback to direct object comparison
                activeChartIndex = i;
                console.log("Clicked chart index (fallback match):", i, "Title:", charts[i].title?.text);
                break;
           }
        }
    }
    if (activeChartIndex === -1) {
        console.error("Could not identify clicked chart.");
        throw new Error("Could not identify clicked chart.");
    }
    return activeChartIndex;
}

function hideAllLinesAndLabels(clickLineModels, labelModels) {
    // Hide all lines and labels
    console.log("Invalid x position from tap event.");
    for (let i = 0; i < clickLineModels.length; i++) {
        if (clickLineModels[i]) clickLineModels[i].visible = false;
        if (labelModels[i]) labelModels[i].visible = false;
    }

    return activeChartIndex;
}

function updatePlaybackSource(x) {
    // Ensure we have access to the playback source
    const playbackSource = window.playback_source;
    if (!playbackSource) {
        console.error("playback_source not available in handleTap!");
        return; // Or handle error appropriately
    }    
    // Update the playback source
    playbackSource.data = {'current_time': [x]};
    playbackSource.change.emit();
}


// ------------- Keyboard Navigation -------------

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
        Object.values(window.sources).forEach(s => { 
            if(s?.data?.Datetime?.length > 0) {
                allTimes.push(...s.data.Datetime);
            }
        });
        if (allTimes.length === 0) {
            console.error("Could not determine time range for keyboard navigation. No sources with valid 'Datetime' array found in window.sources.");
            // Option 1: Use chart ranges as fallback (might be less accurate if zoomed)
            if (window.chartRefs && window.chartRefs[0]?.x_range?.start && window.chartRefs[0]?.x_range?.end) {
                 const firstChartRange = window.chartRefs[0].x_range;
                 newX = Math.max(firstChartRange.start, Math.min(firstChartRange.end, newX));
                 console.warn("Using first chart's x_range for clamping keyboard navigation.");
            } else {
                 // Option 2: Don't clamp, or return
                 console.error("Cannot clamp keyboard navigation. Proceeding without clamping.");
                 // return; // Or let it proceed unclamped
            }
        } else {
            // Proceed with min/max calculation only if allTimes is populated
            let minTime = Math.min(...allTimes);
            let maxTime = Math.max(...allTimes);
            newX = Math.max(minTime, Math.min(maxTime, newX));
        }


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
        if(typeof updateTapLinePositions === 'function' && window.chartRefs && window.clickLineModels && window.labelModels){
             updateTapLinePositions(time_ms, window.chartRefs, window.clickLineModels, window.labelModels);
             // Also update the bar chart based on the new position
             if (typeof updateBarChartFromClickLine === 'function' && window.activeChartIndex !== undefined && window.activeChartIndex >= 0) {
                updateBarChartFromClickLine(time_ms, window.activeChartIndex);
             }
        } else {
             console.warn("Cannot update tap line position visually - function or models missing.");
        }
    

        // *** Update the playback_source ***
        if (window.playback_source) {
            
            console.log('Key Nav: Updating playback_source time to:', new Date(time_ms).toISOString());
            window.playback_source.data = {'current_time': [time_ms]};
            window.playback_source.change.emit(); // Notify Bokeh of the change
        } else {
            console.warn("Cannot update playback_source: playback_source not available.");
        }

        // Update lines using the globally stored models
        updateTapLinePositions(time_ms, window.chartRefs, window.clickLineModels, window.labelModels);

    }
    // --- Spacebar Play/Pause ---
    else if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        console.log("Spacebar pressed.");
        // Check if button models are available
        if (!window.play_button_model || !window.pause_button_model) { // Check original buttons
            console.warn("Cannot toggle playback: Play/Pause button models not available.");
            console.log("Play button model:", window.play_button_model);
            console.log("Pause button model:", window.pause_button_model);
            return;
        }

        console.log("Play button disabled:", window.play_button_model.disabled);
        console.log("Pause button disabled:", window.pause_button_model.disabled);

        // --- Use DOM click() method ---
        try {
            if (window.pause_button_model.disabled === false) {
                console.log("Attempting to click Pause button via Spacebar (Class Selector)");
                // Select using the warning button class
                const pauseButtonElement = document.querySelector('button.bk-btn-warning');
                if (pauseButtonElement) {
                    console.log("Found Pause button element:", pauseButtonElement);
                    pauseButtonElement.click();
                } else {
                    console.warn("Could not find Pause button DOM element using selector: button.bk-btn-warning");
                }
            } else if (window.play_button_model.disabled === false) {
                console.log("Attempting to click Play button via Spacebar (Class Selector)");
                // Select using the success button class
                const playButtonElement = document.querySelector('button.bk-btn-success');
                if (playButtonElement) {
                    console.log("Found Play button element:", playButtonElement);
                    playButtonElement.click();
                } else {
                    console.warn("Could not find Play button DOM element using selector: button.bk-btn-success");
                }
            } else {
                console.log("Both Play and Pause buttons seem disabled.");
            }
        } catch (error) {
             console.error("Error during spacebar button click simulation:", error);
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






// Export functions for use in Bokeh callbacks
window.updateTapLinePositions = updateTapLinePositions;
window.handleHover = handleHover;
window.handleTap = handleTap;
window.enableKeyboardNavigation = enableKeyboardNavigation;
 