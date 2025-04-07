/**
 * app.js
 * 
 * Unified JavaScript module for Noise Survey Analysis Visualization
 * 
 * Refactored from core.js, charts.js, frequency.js, and audio.js
 * to provide better structure, state management, and maintainability.
 */

window.NoiseSurveyApp = (function () {
    'use strict'; // Enable strict mode

    // --- Private State & Models (Internal) ---
    let _models = {
        charts: [],
        sources: {},
        clickLines: [],
        labels: [],
        playbackSource: null,
        playButton: null,
        pauseButton: null,
        barSource: null,
        barXRange: null,
        hoverInfoDiv: null,
        paramSelect: null,
        selectedParamHolder: null,
        allSources: {}, // All sources by key
        spectralParamCharts: {}, // Structure: { position: { available_params, current_param, prepared_data } }
        seekCommandSource: null, // Source for seeking commands from JS
    };

    let _state = {
        verticalLinePosition: null,
        activeChartIndex: -1,
        stepSize: 300000, // Default 5 mins
        keyboardNavigationEnabled: false,
        selectedParameter: 'LZeq' // Default, will be updated
    };

    // --- Make models and state accessible for debugging ---
    // These are deliberately not documented public API
    window.__debugNoiseSurveyModels = _models;
    window.__debugNoiseSurveyState = _state;

    // --- Private Utility Functions (from core.js) ---
    function findClosestDateIndex(dates, x) {
        // Add checks for robustness
        if (dates === null || dates === undefined || typeof dates.length !== 'number' || dates.length === 0) {
            console.warn("findClosestDateIndex received invalid 'dates' array-like object");
            return -1;
        }
        
        if (typeof x !== 'number' || isNaN(x)) {
            console.warn("findClosestDateIndex received invalid 'x' value:", x);
            return -1;
        }

        let low = 0;
        let high = dates.length - 1;
        let closest_idx = 0;
        let min_diff = Infinity;

        // Handle edge cases: x before start or after end
        if (x <= dates[0]) return 0;
        if (x >= dates[high]) return high;

        // Linear scan approach:
        min_diff = Math.abs(dates[0] - x); // Initialize difference
        for (let j = 1; j < dates.length; j++) {
            let diff = Math.abs(dates[j] - x);
            if (diff < min_diff) {
                min_diff = diff;
                closest_idx = j;
            }
            // Optimization: If the difference starts increasing again, we've passed the minimum
            else if (diff > min_diff) {
                break;
            }
        }

        return closest_idx;
    }

    function findClosestIndex(array, target) {
        if (array === null || array === undefined || typeof array.length !== 'number' || array.length === 0) {
            return -1;
        }
        
        let minDiff = Infinity;
        let closestIndex = -1;
        
        for (let i = 0; i < array.length; i++) {
            let diff = Math.abs(array[i] - target);
            if (diff < minDiff) {
                minDiff = diff;
                closestIndex = i;
            }
        }
        
        return closestIndex;
    }

    function createLabelText(source, closest_idx) {
        let date = new Date(source.data.Datetime[closest_idx]);
        let formatted_date = date.toLocaleString();
        let label_text = 'Time: ' + formatted_date + '\n';
        
        for (let key in source.data) {
            if (key !== 'Datetime' && key !== 'index') {
                let value = source.data[key][closest_idx];
                if (value !== undefined && !isNaN(value)) {
                    let formatted_value = parseFloat(value).toFixed(1);
                    label_text += key + ': ' + formatted_value + ' dB\n';
                }
            }
        }
        
        return label_text;
    }

    function positionLabel(x, chart, labelModel) {
        if (!chart || !labelModel) return;
        const xStart = chart.x_range.start || 0;
        const xEnd = chart.x_range.end || 0;
        const yStart = chart.y_range.start || 0;
        const yEnd = chart.y_range.end || 0;
        const middleX = xStart + (xEnd - xStart) / 2;
        const topY = yEnd - (yEnd - yStart) / 8; // Position at top of chart

        if (x <= middleX) {
            labelModel.x = x + (xEnd - xStart) * 0.02;
            labelModel.text_align = 'left';
        } else {
            labelModel.x = x - (xEnd - xStart) * 0.02;
            labelModel.text_align = 'right';
        }
        labelModel.y = topY;
        labelModel.text_baseline = 'middle';
    }

    function calculateStepSize(source) {
        const DEFAULT_STEP_SIZE = 300000;
        if (!source || !source.data || !source.data.Datetime || !Array.isArray(source.data.Datetime) || source.data.Datetime.length < 2) {
            return DEFAULT_STEP_SIZE;
        }
        const times = source.data.Datetime;
        let sumIntervals = 0; 
        let intervals = 0;
        for (let i = 1; i < times.length; i++) {
            const interval = times[i] - times[i-1];
            if (interval > 0) { 
                sumIntervals += interval; 
                intervals++; 
            }
        }
        if (intervals > 0) {
            const avgInterval = sumIntervals / intervals;
            // Ensure step is reasonable (e.g., at least 1 sec, max 1 hour?)
            return Math.max(1000, Math.min(3600000, Math.round(avgInterval * 5)));
        }
        return DEFAULT_STEP_SIZE;
    }

    // --- Private Interaction Functions (from charts.js) ---
    function _updateChartLine(chart, clickLineModel, labelModel, x, chartIndex) {
        if (!clickLineModel || !labelModel) { 
            console.warn("Missing clickLineModel or labelModel for chart index:", chartIndex);
            return false; 
        }

        clickLineModel.location = x;
        clickLineModel.visible = true;

        const sourceKey = chart.name;
        let source = null;
        
        if (!sourceKey || sourceKey === 'range_selector' || sourceKey === 'shared_range_selector' || sourceKey === 'frequency_bar' || sourceKey.includes('_spectral')) {
            labelModel.visible = false; 
            return true;
        }
        
        if (_models.sources && _models.sources.hasOwnProperty(sourceKey)) {
            source = _models.sources[sourceKey];
        }
        
        if (!source || !source.data || !source.data.Datetime) {
            console.warn(`Could not find valid data source for chart index: ${chartIndex}, Name: '${sourceKey}', Title: '${chart.title?.text}'`);
            labelModel.visible = false; 
            return true;
        }
        
        let closest_idx = findClosestDateIndex(source.data.Datetime, x);
        if (closest_idx !== -1) {
            let label_text = createLabelText(source, closest_idx);
            positionLabel(x, chart, labelModel);
            labelModel.text = label_text;
            labelModel.visible = true;
            
            if (_state.activeChartIndex === chartIndex) {
                _state.stepSize = calculateStepSize(source);
            }
            return true;
        } else { 
            labelModel.visible = false; 
            return true; 
        }
    }

    function _updateTapLinePositions(x) {
        _state.verticalLinePosition = x; // Update state

        if (!_models || !_models.charts || !Array.isArray(_models.charts) || _models.charts.length === 0) {
            console.warn("No charts found or charts not properly initialized");
            console.log("_models:", _models);
            console.log("_models.charts:", _models?.charts);
            return false;
        }
        
        for (let i = 0; i < _models.charts.length; i++) {
            // Skip frequency bar chart visuals here
            if (_models.charts[i] && _models.charts[i].name === 'frequency_bar') continue;
            
            // Ensure models exist for this index before calling update
            if (_models.charts[i] && 
                _models.clickLines && Array.isArray(_models.clickLines) && i < _models.clickLines.length && _models.clickLines[i] && 
                _models.labels && Array.isArray(_models.labels) && i < _models.labels.length && _models.labels[i]) {
                
                _updateChartLine(
                    _models.charts[i],
                    _models.clickLines[i],
                    _models.labels[i],
                    x,
                    i
                );
            } else {
                console.warn(`Skipping line update for chart index ${i}: Missing model references.`);
                console.log("models.charts[i]:", _models.charts[i]);
                console.log("models.clickLines:", _models.clickLines);
                console.log("models.clickLines[i]:", _models.clickLines?.[i]);
                console.log("models.labels:", _models.labels);
                console.log("models.labels[i]:", _models.labels?.[i]);
            }
        }
        return true;
    }

    function _getActiveChartIndex(cb_obj) {
        let activeChartIndex = -1;
        for (let i = 0; i < _models.charts.length; i++) {
            if (cb_obj.origin && cb_obj.origin.id === _models.charts[i].id) {
                activeChartIndex = i; 
                break;
            }
        }
        if (activeChartIndex === -1) {
            console.error("Could not identify clicked chart.");
            return -1;
        }
        return activeChartIndex;
    }

    function _hideAllLinesAndLabels() {
        if (!_models.clickLines || !_models.labels) { 
            return; 
        }
        
        try {
            for (let i = 0; i < _models.clickLines.length; i++) { 
                if (_models.clickLines[i]) _models.clickLines[i].visible = false; 
            }
            for (let i = 0; i < _models.labels.length; i++) { 
                if (_models.labels[i]) _models.labels[i].visible = false; 
            }
        } catch (error) {
            console.error("Error hiding lines and labels:", error);
        }
    }

    function _sendSeekCommand(x) {
        if (!_models.seekCommandSource) { 
            console.error("seekCommandSource not available!"); 
            
            // Fallback to legacy method if seek command source is not available
            if (_models.playbackSource) {
                console.warn("Falling back to legacy playbackSource update for seeking");
                _updatePlaybackSource(x);
            }
            return; 
        }
        
        // Send seek command
        console.debug(`Sending seek command to ${x}ms`);
        _models.seekCommandSource.data = {'target_time': [x]};
        _models.seekCommandSource.change.emit(); 
    }

    function _updatePlaybackSource(x) {
        if (!_models.playbackSource) { 
            console.error("playbackSource model not available!"); 
            return; 
        }
        
        // Legacy method - kept for backward compatibility
        // New code should use _sendSeekCommand instead
        _models.playbackSource.data = {'current_time': [x]};
        _models.playbackSource.change.emit();
    }

    // --- Private Frequency Functions (from frequency.js) ---
    function _updateBarChart(x, activeChartIndex, title_source =  '') {
        const chartRefs = _models.charts;
        const spectralParamCharts = _models.spectralParamCharts || {};
        const barSource = _models.barSource || { data: {}, change: { emit: () => {} } };
        const barXRange = _models.barXRange || { factors: [] };
        const barChart = _models.barChart || { title: { text: 'Frequency Slice' } };
        
        // Get currently selected parameter
        const selectedParam = _state.selectedParameter;

        if (!barChart || Object.keys(spectralParamCharts).length === 0 || !barSource.data || !barXRange) {
            console.warn("Missing required models/data for updateBarChartFromClickLine", {
                barChart: !!barChart, 
                spectralData: Object.keys(spectralParamCharts).length,
                barSource: !!barSource.data, 
                barXRange: !!barXRange
            });
            return;
        }

        if (!barChart) { 
            console.warn("No bar chart found"); 
            return; 
        }

        // Handle invalid input
        if (x === null || x === undefined || x <= 0 || activeChartIndex < 0 || activeChartIndex >= chartRefs.length) {
            // Reset the bar chart to empty state
            // Try to get frequency labels from the first available position
            const firstPosKey = Object.keys(spectralParamCharts)[0];
            if (firstPosKey && spectralParamCharts[firstPosKey]?.prepared_data?.[selectedParam]) {
                const firstPosData = spectralParamCharts[firstPosKey].prepared_data[selectedParam];
                if (firstPosData.frequency_labels) {
                    barSource.data['levels'] = Array(firstPosData.frequency_labels.length).fill(0);
                    barSource.data['frequency_labels'] = firstPosData.frequency_labels;
                    if (barXRange) barXRange.factors = firstPosData.frequency_labels;
                } else {
                    barSource.data['levels'] = [];
                    barSource.data['frequency_labels'] = [];
                    if (barXRange) barXRange.factors = [];
                }
            } else {
                barSource.data['levels'] = [];
                barSource.data['frequency_labels'] = [];
                if (barXRange) barXRange.factors = [];
            }
            
            if (barChart.title) barChart.title.text = `Frequency Slice`;
            if (barSource.change && typeof barSource.change.emit === 'function') barSource.change.emit();
            return;
        }

        // Get active chart and extract position from chart name
        const activeChart = chartRefs[activeChartIndex];
        if (!activeChart || !activeChart.name) {
            console.warn("Invalid active chart");
            return;
        }
        
        const chartName = activeChart.name;
        let position = chartName.split('_')[0];
        
        // Check if this position has spectral data
        if (!spectralParamCharts[position]) {
            position = Object.keys(spectralParamCharts)[0];
            if (!position) {
                console.warn("No position data found in spectralParamCharts");
                return;
            }
        }

        // Get position data and check if the parameter is available
        const positionData = spectralParamCharts[position];
        const availableParams = positionData.available_params || [];
        
        if (!availableParams.includes(selectedParam)) {
            console.warn(`Parameter ${selectedParam} not available for position ${position}`);
            return;
        }
        
        // Get prepared data for this parameter
        const preparedData = positionData.prepared_data?.[selectedParam];
        if (!preparedData) {
            console.warn(`No prepared data for position ${position} with parameter ${selectedParam}`);
            return;
        }
        
        // Get time information for finding the closest time index
        const times = preparedData.times_ms;
        if (!times || !Array.isArray(times)) {
            console.warn(`Missing time data for position ${position}`);
            return;
        }
        
        // Find closest time index
        let closestTimeIdx = findClosestDateIndex(times, x);
        if (closestTimeIdx === -1) {
            console.warn("Could not find closest time index");
            return;
        }
        
        // Get frequency data for this time
        const n_freqs = preparedData.n_freqs;
        const levelMatrixFlat = preparedData.levels_matrix || [];
        const baseFreqIdx = closestTimeIdx * n_freqs;
        const freqData = levelMatrixFlat.slice(baseFreqIdx, baseFreqIdx + n_freqs);

        if (!freqData) {
            console.log("closestTimeIdx:", closestTimeIdx);
            console.log("baseFreqIdx:", baseFreqIdx);
            console.log("n_freqs:", n_freqs);
            console.log("levelMatrixFlat:", levelMatrixFlat);
            console.log("frequencyData:", freqData);
            console.warn(`No frequency data at time index ${closestTimeIdx}`);
            return;
        }
        
        // Update bar chart with the data at the selected time
        barSource.data['levels'] = freqData;
        barSource.data['frequency_labels'] = preparedData.frequency_labels || [];
        
        if (barXRange) barXRange.factors = preparedData.frequency_labels || [];
        if (barChart.title) barChart.title.text = `Frequency Slice: ${position} | ${selectedParam} | ${new Date(x).toLocaleString()} (${title_source})`;
        if (barSource.change && typeof barSource.change.emit === 'function') barSource.change.emit();
    }


    // hovertool for spectrogram    
    function _handleSpectrogramHover(cb_data, hover_div, bar_source, bar_x_range, position_name,
        times_array, freqs_array, freq_labels_array, levels_matrix, levels_flat_array, fig_x_range) {
        try {

            // Check if the provided bar_source and bar_x_range are valid, otherwise use models
            const div = hover_div;
            const bar_source_js = bar_source || _models.barSource;
            const bar_x_range_js = bar_x_range || _models.barXRange;
            
            if (!div || !bar_source_js || !bar_x_range_js) {
                console.warn("Missing required models for handleSpectrogramHover");
                return false;
            }

            // Data arrays from parameters
            const times = times_array;
            const freqs = freqs_array;
            const freq_labels_str = freq_labels_array;
            const levels_flat = levels_flat_array;

            const n_times = times.length;
            const n_freqs = freqs.length;
            const x_start = fig_x_range.start;
            const x_end = fig_x_range.end;

            // Find frequency bar chart
            const barChart = _models.barChart;
            const bar_data = bar_source_js.data;

            if (!barChart) {
                console.error("DEBUG: No bar chart found");
                console.log("DEBUG: _models.barChart:", _models.barChart);
                console.log("DEBUG: _models.", _models);
                return false;
            }

            const {x: gx, y: gy} = cb_data.geometry;
            const is_inside = !(gx < x_start || gx > x_end || gy < -0.5 || gy > n_freqs - 0.5 || n_times === 0 || n_freqs === 0);
            

            if (is_inside && barChart) {
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
                    console.error("MISMATCH: levels_slice and freq_labels_str lengths don't match:", {
                        levels_slice_length: levels_slice.length,
                        freq_labels_length: freq_labels_str.length
                    });
                    // Optionally reset or return to prevent errors
                    levels_slice = Array(freq_labels_str.length).fill(0);
                } else {
                    levels_slice = levels_slice.map(level => 
                        (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);
                }

                // Check if there are any other properties in bar_data that might cause inconsistency
                if (Object.keys(bar_data).some(key => 
                    key !== 'levels' && 
                    key !== 'frequency_labels' && 
                    Array.isArray(bar_data[key]))) {
                    console.warn("DEBUG: bar_data contains additional array properties:", 
                        Object.keys(bar_data).filter(key => 
                            key !== 'levels' && 
                            key !== 'frequency_labels' && 
                            Array.isArray(bar_data[key])
                        )
                    );
                }

                // Clear existing data to ensure we're setting consistent data
                const cleanData = {
                    'levels': levels_slice,
                    'frequency_labels': freq_labels_str
                };
                bar_source_js.data = cleanData;
                
                bar_x_range_js.factors = freq_labels_str;

                const timeForTitle = new Date(time_val_ms).toLocaleTimeString(); // More concise time for title
                barChart.title.text = `Frequency Slice: ${position_name} | ${_state.selectedParameter} | ${timeForTitle}`;

                bar_source_js.change.emit();
                return true;

            } else {
                // Reset hover info
                div.text = "Hover over spectrogram to view details";
                div.change.emit();
                
                // Restore frequency bar to click line position if available
                if (_state.verticalLinePosition !== null && _state.activeChartIndex >= 0) {
                    _updateBarChart(_state.verticalLinePosition, _state.activeChartIndex, "Spectrogram");
                } else {
                    // Fallback reset if no click line position
                    if (bar_data && n_freqs > 0) {
                        // Create clean data with consistent lengths
                        const resetData = {
                            'levels': Array(freq_labels_str.length || n_freqs).fill(null),
                            'frequency_labels': freq_labels_str || []
                        };
                        bar_source_js.data = resetData;
                        
                        if (barChart) barChart.title.text = `Frequency Slice`;
                        bar_source_js.change.emit();
                    }
                }
                return true;
            }
        } catch (error) {
            console.error("Error in handleSpectrogramHover:", error);
            return false;
        }
    }

    function _waitForModelReady(modelRef, modelName, callback, timeout = 5000, interval = 250) {
        if (!modelRef) {
            console.error(`waitForModelReady: ${modelName} model is initially null or undefined.`);
            callback(new Error(`${modelName} model is null/undefined at start.`)); // Signal error via callback
            return;
        }
        console.log(`waitForModelReady: Entered for ${modelName}. Checking model:`, modelRef);

        let elapsed = 0;
        const check = setInterval(() => {
            elapsed += interval;
            // console.debug(`waitForModelReady (${modelName}): Checking... Elapsed: ${elapsed}ms`);

            // Check 1: Basic model exists and on_change is a function
            const hasOnChange = modelRef && typeof modelRef.on_change === 'function';

            // Check 2: Internal properties seem available (Focus on 'data' for CDS)
            // Check if the 'change' signal object exists on the 'data' property specifically
            const hasInternalProps = modelRef &&
                                     modelRef.properties &&
                                     modelRef.properties.data &&
                                     typeof modelRef.properties.data.change === 'object' &&
                                     typeof modelRef.properties.data.change.connect === 'function' && // <-- More specific check
                                     typeof modelRef.properties.data.change.disconnect === 'function';

            // Check 3: (Optional but potentially useful) Check if the model has an ID assigned by Bokeh
            const hasId = modelRef && typeof modelRef.id === 'string' && modelRef.id !== '';

            // console.debug(`waitForModelReady (${modelName}): hasOnChange=${hasOnChange}, hasInternalProps=${hasInternalProps}, hasId=${hasId}`);

            if (hasOnChange && hasInternalProps && hasId) {
                clearInterval(check);
                console.log(`waitForModelReady: Checks passed for ${modelName} after ${elapsed}ms.`);
                // Add a slightly longer delay AFTER checks pass, before calling the setup function
                setTimeout(() => {
                    console.log(`waitForModelReady: Executing callback for ${modelName} after longer delay.`);
                    callback(null); // Signal success (no error)
                }, 500); // Increase from 100ms to 500ms

            } else if (elapsed >= timeout) {
                clearInterval(check);
                const errorMsg = `waitForModelReady: Timeout waiting for ${modelName} readiness. Final checks: hasOnChange=${hasOnChange}, hasInternalProps=${hasInternalProps}, hasId=${hasId}`;
                console.error(errorMsg);
                console.error(`waitForModelReady: ${modelName} state on timeout:`, modelRef);
                if (modelRef && modelRef.properties) {
                   console.error(`waitForModelReady: ${modelName} properties on timeout:`, modelRef.properties);
                }
                callback(new Error(errorMsg)); // Signal error via callback
            }
        }, interval);
    }

    // --- Private Audio Functions (from audio.js) ---
    function _setupPlaybackListener() {
        // DEPRECATED: This function is no longer used.
        // We now use a CustomJS callback attached via Python's js_on_change mechanism in app_callbacks.py
        // which is more reliable and avoids initialization timing issues.
        // Keeping this for reference and backward compatibility.
        console.warn("_setupPlaybackListener called but this function is deprecated. The app now uses a Python-attached CustomJS callback.");
        
        // Re-check essential conditions although waitForModelReady should ensure them
        if (!_models.playbackSource || typeof _models.playbackSource.on_change !== 'function') {
            console.error("FATAL: _setupPlaybackListener called but playbackSource or on_change is invalid!");
            return;
        }
         console.log("_setupPlaybackListener: playbackSource and on_change method confirmed.");

        // Ensure _updateTapLinePositions is available
        if (typeof _updateTapLinePositions !== 'function') {
            console.error("_setupPlaybackListener: _updateTapLinePositions function not available.");
            return;
        }
         console.log("_setupPlaybackListener: Update playback position function found.");

        try {
            console.log("_setupPlaybackListener: Attempting to attach on_change listener to 'data' property...");
            console.log("_setupPlaybackListener: Current playbackSource model:", _models.playbackSource);

            // THE CORE CALL: Attach listener to changes in the 'data' property
            _models.playbackSource.js_on_change('data', () => {
                // Defensive checks inside the callback
                if (_models.playbackSource?.data?.current_time?.length > 0) {
                    const currentTime = _models.playbackSource.data.current_time[0];
                    if (typeof currentTime === 'number' && !isNaN(currentTime)) {
                        console.debug("Playback listener triggered. Time:", currentTime); // Reduced verbosity
                        // --- Directly update tapline visuals ---
                        // This prevents a feedback loop where updating the visual
                        // causes another update to the playbackSource.
                        _updateTapLinePositions(currentTime);
                    } else {
                        console.warn("Playback listener triggered, but current_time is not a valid number:", currentTime);
                    }
                } else {
                     console.warn("Playback listener triggered, but playbackSource.data.current_time is not accessible or empty.");
                     // console.log("Current playbackSource state in callback:", _models.playbackSource);
                }
            });

            console.log("_setupPlaybackListener: SUCCESSFULLY attached on_change listener to 'data'."); // Crucial success message

        } catch (error) {
            // Log detailed error information
            console.error("ERROR in _setupPlaybackListener during on_change attachment:", error.message);
            console.error("Stack trace:", error.stack); // Log stack trace
            console.error("PlaybackSource model state at time of error:", JSON.stringify(_models.playbackSource, null, 2)); // Log model state as JSON if possible
        }
    }

    // --- Public API - Initialize App ---
    function initializeApp(models, options) {
        console.info('NoiseSurveyApp - Initializing...');

        try {
            // Set global models (charts, sources, lines, etc)
            console.log('Setting global models...');
            _models.charts = models.charts || [];
            _models.sources = models.sources || {};
            _models.clickLines = models.clickLines || [];
            _models.labels = models.labels || [];
            _models.playbackSource = models.playback_source || null;  
            _models.playButton = models.play_button || null;
            _models.pauseButton = models.pause_button || null;
            _models.barSource = models.bar_source || null;
            _models.barXRange = models.bar_x_range || null;
            _models.barChart = models.barChart || null;
            _models.paramSelect = models.param_select || null;
            _models.selectedParamHolder = models.param_holder || null;
            _models.allSources = models.all_sources || {};
            _models.spectralParamCharts = models.spectral_param_charts || {};
            _models.seekCommandSource = models.seek_command_source || null;
            console.log('Global models set:', _models);

            // Set default parameter from data if available
            if (_models.selectedParamHolder && _models.selectedParamHolder.text) {
                _state.selectedParameter = _models.selectedParamHolder.text;
                console.log('Selected parameter set to:', _state.selectedParameter);
            }

            // Initialize playback source position
            if (_models.playbackSource) {
                console.log('Initializing playback source position...');
                let initialTimeMs = 0;
                if (_models.charts.length > 0 && _models.charts[0].x_range && typeof _models.charts[0].x_range.start === 'number') {
                    initialTimeMs = _models.charts[0].x_range.start;
                }
                if (!_models.playbackSource.data.hasOwnProperty('current_time') ||
                    !Array.isArray(_models.playbackSource.data.current_time) ||
                    _models.playbackSource.data.current_time.length === 0 ||
                    _models.playbackSource.data.current_time[0] !== initialTimeMs) {
                    console.log(`Initializing playbackSource current_time to ${initialTimeMs} ms`);
                    _models.playbackSource.data = {'current_time': [initialTimeMs]};
                    //hide the tap lines which are made 
                    hideTapLines();
                } else {
                    console.log(`playbackSource current_time already exists: ${_models.playbackSource.data.current_time[0]}`);
                }
                _state.verticalLinePosition = _models.playbackSource.data.current_time[0];
                console.log('Playback source position initialized:', _state.verticalLinePosition);
            } else {
                console.warn("initializeApp: playbackSource model not found in provided models.");
            }

            // Initialize keyboard navigation if enabled
            if (options && options.enableKeyboardNavigation) {
                console.log('Enabling keyboard navigation...');
                setupKeyboardNavigation();
            } else {
                console.log("Keyboard navigation disabled");
            }

            // Set up global references for legacy code that hasn't been migrated yet
            console.log('Setting up global references...');
            window.chartRefs = _models.charts;
            window.barSource = _models.barSource;
            window.barXRange = _models.barXRange;
            window.selectedParamHolder = _models.selectedParamHolder;
            window.globalVerticalLinePosition = _state.verticalLinePosition;
            window.globalActiveChartIndex = _state.activeChartIndex;
            console.log('Global references set.');

            console.info('NoiseSurveyApp - Initialization complete');
            return true;
        } catch (error) {
            console.error('Error during initialization:', error);
            return false;
        }
    }

    // --- Audio Player Integration ---
    function synchronizePlaybackPosition(ms) {
        // called from Python periodic update to update the playback position to match the audio playback position
        try {

            // Update tap lines visually
            _updateTapLinePositions(ms);
            updateFrequencyBar(ms, _state.activeChartIndex, "Audio Playback");


            return true;
        } catch (error) {
            console.error('Error synchronizing playback position:', error);
            return false;
        }
    }

    // Helper to get the current active position
    function getActivePosition() {
        const activeChartIndex = _state.activeChartIndex;
        if (activeChartIndex >= 0 && activeChartIndex < _models.charts.length) {
            const activeChart = _models.charts[activeChartIndex];
            if (activeChart && activeChart.name) {
                // Extract position from chart name (e.g. "Position_1_overview" -> "Position_1")
                const parts = activeChart.name.split('_');
                if (parts.length >= 2) {
                     // Handle names like SW_overview, Position_1_spectral, etc.
                     return parts[0]; // Assume position is the first part
                }
            }
        }

        // Fallback: return the first available position from spectral_param_charts
        const positions = Object.keys(_models.spectralParamCharts);
        if (positions.length > 0) {
            return positions[0];
        }

        return "Unknown";
    }

    // --- Parameter Selection ---
    function handleParameterChange(param) {
        if (!param) return false;
        
        // Store the selected parameter
        _state.selectedParameter = param;
        
        // Update the selected parameter holder if it exists
        if (_models.selectedParamHolder) {
            _models.selectedParamHolder.text = param;
        }
        
        // Update each spectral chart with the new parameter
        try {
            const spectralParams = _models.spectralParamCharts || {};
            
            for (const position in spectralParams) {
                const positionData = spectralParams[position];
                const availableParams = positionData.available_params || [];

                const chart = _models.charts.find(chart => chart.name === `${position}_spectral`);
                if (!chart) {
                    console.warn(`No chart found for position ${position}`);
                    continue;
                }
                
                // Skip positions that don't have this parameter
                if (!availableParams.includes(param)) {
                    console.log(`Parameter ${param} not available for position ${position}`);
                    console.log("DEBUG: handleParameterChange: availableParams:", availableParams);
                    //TODO: set data to zero for this parameter
                    continue;
                }
                
                // Get the prepared data for this parameter
                const preparedData = positionData.prepared_data?.[param];
                if (!preparedData) {
                    console.warn(`No prepared data for position ${position} with parameter ${param}`);
                    console.log("DEBUG: handleParameterChange: preparedData:", preparedData);
                    continue;
                }
                
                // Update the current parameter for this position
                positionData.current_param = param;

                // Get the source and update it with the new data
                const sourceKey = `${position}_spectral`;
                const source = _models.sources[sourceKey];

                
                if (!source) {
                    console.error(`Source not found for position ${position}`);
                    continue;
                }
                
                // Update the data in the source
                if (preparedData.levels_matrix_transposed) source.data.image = [preparedData.levels_matrix_transposed]; else source.data.image = [];
                if (preparedData.x) source.data.x = [preparedData.x]; else source.data.x = [];
                if (preparedData.y) source.data.y = [preparedData.y]; else source.data.y = [];
                if (preparedData.dw) source.data.dw = [preparedData.dw]; else source.data.dw = [];
                if (preparedData.dh) source.data.dh = [preparedData.dh]; else source.data.dh = [];
                
                // Update the chart title
                chart.title.text = `${position} - ${param} Spectral Data`;
                
                // Signal that the data has changed
                source.change.emit();
                
                console.log(`Updated ${position} spectrogram to parameter ${param}`);
            }
            
            // If a click line is active, update the frequency bar with the new parameter
            if (_state.verticalLinePosition !== null && _state.activeChartIndex !== -1) {
                _updateFrequencyBar(_state.verticalLinePosition, _state.activeChartIndex);
            }
            
            return true;
        } catch (error) {
            console.error('Error handling parameter change:', error);
            return false;
        }
    }
    
    // Helper function to update the frequency bar
    function _updateFrequencyBar(x, activeChartIndex) {
        // Use frequency.js functionality if available
        if (window.updateBarChartFromClickLine) {
            window.updateBarChartFromClickLine(x, activeChartIndex);
        }
    }

    function showTapLines() {
        if (!_models.clickLines) return false;
        
        try {
            // If we have a stored position, update all lines to that position
            if (_state.verticalLinePosition !== null) {
                _updateTapLinePositions(_state.verticalLinePosition);
            }
            
            // Ensure all lines are visible
            for (let i = 0; i < _models.clickLines.length; i++) {
                if (_models.clickLines[i]) {
                    _models.clickLines[i].visible = true;
                }
            }
            
            return true;
        } catch (error) {
            console.error("Error showing tap lines:", error);
            return false;
        }
    }

    function hideTapLines() {
        if (!_models.clickLines) return false;
        
        try {
            for (let i = 0; i < _models.clickLines.length; i++) {
                if (_models.clickLines[i]) _models.clickLines[i].visible = false;
            }
            for (let i = 0; i < _models.labels.length; i++) {
                if (_models.labels[i]) _models.labels[i].visible = false;
            }
            return true;
        } catch (error) {
            console.error("Error hiding tap lines:", error);
            return false;
        }
    }
    
    function updateTapLinePosition(x) {
        if (typeof x !== 'number' || isNaN(x)) {
            console.warn("Invalid position value for updateTapLinePosition:", x);
            return false;
        }
        
        // Check if _models is initialized properly
        if (!_models || !_models.charts || !Array.isArray(_models.charts)) {
            console.warn("Models not properly initialized in updateTapLinePosition");
            console.log("_models:", _models);
            return false;
        }
        
        try {
            return _updateTapLinePositions(x);
        } catch (error) {
            console.error("Error updating tap line position:", error);
            return false;
        }
    }

    function updateFrequencyBar(x, activeChartIndex, title_source = '') {
        try {
            if (typeof x !== 'number' || isNaN(x)) {
                console.warn("Invalid position value for updateFrequencyBar:", x);
                return false;
            }
            
            _updateBarChart(x, activeChartIndex !== undefined ? activeChartIndex : _state.activeChartIndex, title_source);
            return true;
        } catch (error) {
            console.error("Error updating frequency bar:", error);
            return false;
        }
    }

    function startAudioPlayback() {
        try {
            // Check if play button exists
            if (!_models.playButton) {
                console.warn("Play button not available");
                return false;
            }
            
            // Trigger play button click
            if (_models.playButton.disabled === false) {
                // Find play button in DOM
                const playButtonElement = document.querySelector('button.bk-btn-success');
                if (playButtonElement) {
                    playButtonElement.click();
                    return true;
                } else {
                    console.warn("Could not find Play button DOM element");
                    return false;
                }
            } else {
                console.warn("Play button is disabled");
                return false;
            }
        } catch (error) {
            console.error("Error starting audio playback:", error);
            return false;
        }
    }

    function pauseAudioPlayback() {
        try {
            // Check if pause button exists
            if (!_models.pauseButton) {
                console.warn("Pause button not available");
                return false;
            }
            
            // Trigger pause button click
            if (_models.pauseButton.disabled === false) {
                // Find pause button in DOM
                const pauseButtonElement = document.querySelector('button.bk-btn-warning');
                if (pauseButtonElement) {
                    pauseButtonElement.click();
                    return true;
                } else {
                    console.warn("Could not find Pause button DOM element");
                    return false;
                }
            } else {
                console.warn("Pause button is disabled");
                return false;
            }
        } catch (error) {
            console.error("Error pausing audio playback:", error);
            return false;
        }
    }

    function togglePlayPause() {
        try {
            if (!_models.playButton || !_models.pauseButton) {
                console.warn("Play/Pause buttons not available");
                return false;
            }
            
            // Check which button is enabled and click it
            if (_models.pauseButton.disabled === false) {
                return pauseAudioPlayback();
            } else if (_models.playButton.disabled === false) {
                return startAudioPlayback();
            } else {
                console.warn("Both Play and Pause buttons are disabled");
                return false;
            }
        } catch (error) {
            console.error("Error toggling play/pause:", error);
            return false;
        }
    }

    function enableKeyboardNavigation() {
        console.log("enableKeyboardNavigation. state:", _state.keyboardNavigationEnabled);
        if (!_state.keyboardNavigationEnabled) {
            try {
                document.addEventListener('keydown', handleKeyPress);
                _state.keyboardNavigationEnabled = true;
                console.log('Keyboard navigation enabled');
                return true;
            } catch (error) {
                console.error("Error enabling keyboard navigation:", error);
                return false;
            }
        }
        console.log("enableKeyboardNavigation. state:", _state.keyboardNavigationEnabled);
        return true; // Already enabled
    }

    function disableKeyboardNavigation() {
        console.log("disableKeyboardNavigation");
        if (_state.keyboardNavigationEnabled) {
            try {
                document.removeEventListener('keydown', handleKeyPress);
                _state.keyboardNavigationEnabled = false;
                console.log('Keyboard navigation disabled');
                return true;
            } catch (error) {
                console.error("Error disabling keyboard navigation:", error);
                return false;
            }
        }
        return true; // Already disabled
    }

    function handleKeyPress(e) {
        // Skip if models aren't available
        if (!_models.charts || !_models.clickLines || !_models.labels || !_models.playbackSource) {
            console.warn("Cannot navigate with keyboard: required models not ready");
            return;
        }
        
        // Arrow key navigation
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            e.preventDefault(); // Prevent browser default scrolling
            
            let currentX = _state.verticalLinePosition;
            if (!currentX && _models.playbackSource && _models.playbackSource.data && 
                _models.playbackSource.data.current_time && _models.playbackSource.data.current_time.length > 0) {
                currentX = _models.playbackSource.data.current_time[0];
            }
            
            // If still no currentX, use middle of the first chart's range
            if (!currentX && _models.charts.length > 0 && _models.charts[0].x_range) {
                currentX = (_models.charts[0].x_range.start + _models.charts[0].x_range.end) / 2;
            }
            
            // Use step size based on active chart, or default
            let step = _state.stepSize;
            let newX = e.key === 'ArrowLeft' ? currentX - step : currentX + step;
            
            // Optional: Clamp newX to data range if needed
            
            // Update position
            updateTapLinePosition(newX);
            
            // Update playback source with seek command
            _sendSeekCommand(newX);
            
            // Update frequency bar if needed
            if (_state.activeChartIndex !== -1) {
                updateFrequencyBar(newX, _state.activeChartIndex, "Click Line");
            }
        }
        // Spacebar for play/pause
        else if (e.key === ' ' || e.code === 'Space') {
            e.preventDefault();
            togglePlayPause();
        }
    }

    /**
     * Handle tap/click events on charts
     * @param {Object} cb_obj - Click event object from Bokeh containing x coordinate and origin data
     * @returns {boolean} True if handled successfully
     */
    function onTapHandler(cb_obj) {
        try {
            // Get active chart index
            _state.activeChartIndex = _getActiveChartIndex(cb_obj);
            
            // Get x position
            const x = cb_obj.x;
            
            // If tap is outside charts, hide lines
            if (x === undefined || x === null) {
                hideTapLines();
                return;
            }           
            
            // Update lines position
            _updateTapLinePositions(x);
            
            // Update playback source with seek command
            _sendSeekCommand(x);
            
            // Update frequency bar chart
            updateFrequencyBar(x, _state.activeChartIndex, "Click Line");
            
            return true;
        } catch (error) {
            console.error("Error handling tap:", error);
            return false;
        }
    }

    /**
     * Handle hover events on charts
     * @param {Array} hoverLines - Array of hover line span objects
     * @param {Object} cb_data - Callback data from Bokeh
     * @returns {boolean} True if handled successfully
     */
    function onHoverHandler(hoverLines, cb_data) {
        try {
            // Get hover position
            if (!cb_data || !cb_data.geometry || typeof cb_data.geometry.x !== 'number') {
                return false;
            }
            
            const hoveredX = cb_data.geometry.x;
            
            // Update hover lines
            if (hoverLines) {
                for (let i = 0; i < hoverLines.length; i++) {
                    if (hoverLines[i]) {
                        hoverLines[i].location = hoveredX;
                    }
                }
            }
            
            // Determine hovered chart
            let hoveredChart = null;
            let hoveredChartIndex = -1;
            
            // Check if the event includes the model/origin
            if (cb_data.geometries && cb_data.geometries.length > 0 && cb_data.geometries[0].model) {
                // Find chart by model ID
                const hoveredModelId = cb_data.geometries[0].model.id;
                for (let i = 0; i < _models.charts.length; i++) {
                    if (_models.charts[i].id === hoveredModelId) {
                        hoveredChart = _models.charts[i];
                        hoveredChartIndex = i;
                        break;
                    }
                }
            }
            
            // If chart not found by model, try coordinates
            if (!hoveredChart && cb_data.geometry) {
                const hoveredX = cb_data.geometry.x;
                const hoveredY = cb_data.geometry.y;
                
                for (let i = 0; i < _models.charts.length; i++) {
                    const chart = _models.charts[i];
                    
                    // Skip range_selector or frequency_bar charts
                    if (chart.name === 'range_selector' || chart.name === 'shared_range_selector' || chart.name === 'frequency_bar') continue;
                    
                    // Check if hover position is within chart bounds
                    if (chart.x_range && hoveredX >= chart.x_range.start && hoveredX <= chart.x_range.end) {
                        hoveredChart = chart;
                        hoveredChartIndex = i;
                        break;
                    }
                }
            }
            
            // If we have a valid hovered chart, update frequency bar
            if (hoveredChart && hoveredChart.name) {
                // Extract position from chart name (e.g., "SW_overview" -> "SW")
                const position = hoveredChart.name.split('_')[0];
                
                // Check if chart is a line chart (overview or log, not spectral)
                const isLineChart = hoveredChart.name.includes('_overview') || hoveredChart.name.includes('_log');
                
                if (isLineChart && position) {
                    // Update frequency bar
                    updateFrequencyBar(hoveredX, hoveredChartIndex, `Hover on ${hoveredChart.name}`);
                }
            } else if (_state.verticalLinePosition && _state.activeChartIndex >= 0) {
                // If not hovering over a chart, restore frequency bar to click line position
                updateFrequencyBar(_state.verticalLinePosition, _state.activeChartIndex, "Click Line");
            }
            
            return true;
        } catch (error) {
            console.error("Error handling hover:", error);
            return false;
        }
    }

    // Ensure setupKeyboardNavigation is defined
    function setupKeyboardNavigation() {
        return enableKeyboardNavigation();
    }

    // --- Module Exports ---
    return {
        // Core initialization
        init: initializeApp,
        
        // Getters for application state
        getState: function() {
            return JSON.parse(JSON.stringify(_state));
        },
        getModels: function() {
            // Filter out non-serializable properties and return a copy
            const modelsCopy = {};
            
            // Include basic models properties that can be serialized
            if (_models.charts && _models.charts.length) {
                modelsCopy.charts = _models.charts.map(chart => {
                    return {
                        id: chart.id,
                        name: chart.name,
                        title: chart.title ? chart.title.text : 'Untitled',
                        visible: chart.visible,
                        height: chart.height,
                        width: chart.width,
                        x_range: chart.x_range ? {
                            start: chart.x_range.start,
                            end: chart.x_range.end
                        } : null,
                        y_range: chart.y_range ? {
                            start: chart.y_range.start,
                            end: chart.y_range.end
                        } : null
                    };
                });
            }
            
            // Include sources info - extract basic data structure
            if (_models.sources) {
                modelsCopy.sources = {};
                Object.keys(_models.sources).forEach(key => {
                    const source = _models.sources[key];
                    if (source && source.data) {
                        // Get metadata about the source data
                        const sourceInfo = {
                            keys: Object.keys(source.data),
                            dataLength: source.data.Datetime ? source.data.Datetime.length : 0,
                            dataSample: {}
                        };
                        
                        // Add a small sample of the data (first item)
                        if (sourceInfo.dataLength > 0) {
                            Object.keys(source.data).forEach(dataKey => {
                                if (Array.isArray(source.data[dataKey]) && source.data[dataKey].length > 0) {
                                    sourceInfo.dataSample[dataKey] = source.data[dataKey][0];
                                }
                            });
                        }
                        
                        modelsCopy.sources[key] = sourceInfo;
                    }
                });
            }
            
            // Add other serializable properties
            if (_models.clickLines) {
                modelsCopy.clickLines = _models.clickLines.map(line => {
                    return line ? {
                        visible: line.visible,
                        location: line.location
                    } : null;
                });
            }
            
            if (_models.labels) {
                modelsCopy.labels = _models.labels.map(label => {
                    return label ? {
                        visible: label.visible,
                        text: label.text,
                        x: label.x,
                        y: label.y
                    } : null;
                });
            }
            
            // Add spectral parameter info if available
            if (_models.spectralParamCharts) {
                modelsCopy.spectralParams = {};
                Object.keys(_models.spectralParamCharts).forEach(pos => {
                    const posData = _models.spectralParamCharts[pos];
                    modelsCopy.spectralParams[pos] = {
                        availableParams: posData.available_params || [],
                        currentParam: posData.current_param || null
                    };
                });
            }
            
            return modelsCopy;
        },
        
        // Chart interactions
        showTapLines: showTapLines,
        hideTapLines: hideTapLines,
        updateTapLinePosition: updateTapLinePosition,
        
        // Spectral data
        handleParameterChange: handleParameterChange,
        updateFrequencyBar: updateFrequencyBar,
        
        // Audio playback
        synchronizePlaybackPosition: synchronizePlaybackPosition,
        startAudioPlayback: startAudioPlayback,
        pauseAudioPlayback: pauseAudioPlayback,
        togglePlayPause: togglePlayPause,
        
        // Navigation
        enableKeyboardNavigation: enableKeyboardNavigation,
        disableKeyboardNavigation: disableKeyboardNavigation,
        
        /**
         * Frequency namespace
         * Contains functions migrated from frequency.js for better organization and maintenance.
         * These functions handle spectrogram hover interactions and frequency visualization updates.
         */
        frequency: {
            /**
             * Handle hover events on a spectrogram
             * Updates hover information div and frequency bar chart based on cursor position
             *
             * @param {Object} cb_data - Callback data from Bokeh containing hover information
             * @param {Object} hover_div - The div element to show hover information 
             * @param {string} position_name - The position name ('SW', 'N', etc.) of the hovered spectrogram
             * @param {Array} times_array - Array of time values in milliseconds
             * @param {Array} freqs_array - Array of frequency values
             * @param {Array} freq_labels_array - Array of frequency labels as strings
             * @param {Array} levels_matrix - Matrix of level values
             * @param {Array} levels_flat_array - Flattened array of level values
             * @param {Object} fig_x_range - X range of the spectrogram figure
             */
            handleSpectrogramHover: function(cb_data, hover_div, bar_source, bar_x_range, position_name,
                times_array, freqs_array, freq_labels_array, levels_matrix, levels_flat_array, fig_x_range) {
                    return _handleSpectrogramHover(cb_data, hover_div, bar_source, bar_x_range, position_name,
                        times_array, freqs_array, freq_labels_array, levels_matrix, levels_flat_array, fig_x_range);
            },
            /**
             * Update frequency bar chart based on a time value
             * @param {number} x - X position (timestamp) to find frequency data for
             * @param {number} activeChartIndex - Index of the active chart
             * @param {string} [position] - Optional position override
             * @param {boolean} [updateHoverInfo] - Whether to update hover info div
             */
            updateFrequencyBarChart: function(x, activeChartIndex, position, updateHoverInfo) {
                return _updateBarChart(x, activeChartIndex);
            }
        },
        
        /**
         * Interactions namespace
         * Contains functions migrated from charts.js for better organization and maintenance.
         * These functions handle chart interaction events like hover, tap/click,
         * chart range synchronization, and related chart manipulation.
         */
        interactions: {
            // Chart interactions
            onTap: onTapHandler,
            onHover: onHoverHandler,
            
            // Aliases for interactive.py calls
            handleHover: onHoverHandler,
            handleTap: onTapHandler,
            
            // Chart synchronization
            syncChartRanges: function(charts) {
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
            },
            
            // Direct access to private methods with consistent naming
            updateChartLine: _updateChartLine,
            updateTapLinePositions: _updateTapLinePositions,
            hideAllLinesAndLabels: _hideAllLinesAndLabels,
            updatePlaybackSource: _updatePlaybackSource,
            sendSeekCommand: _sendSeekCommand,
            getActiveChartIndex: _getActiveChartIndex,
            synchronizePlaybackPosition: synchronizePlaybackPosition
        },
        
        // Utilities
        findClosestIndex: findClosestIndex,
        findClosestDateIndex: findClosestDateIndex
    };
})(); 

// Expose the interactions namespace globally for backward compatibility
// This allows legacy code to use window.interactions instead of window.NoiseSurveyApp.interactions
window.interactions = window.NoiseSurveyApp.interactions; 
// Expose the frequency namespace globally for backward compatibility
// This allows legacy code to use window.NoiseFrequency instead of window.NoiseSurveyApp.frequency
window.NoiseFrequency = window.NoiseSurveyApp.frequency; 

// Expose key functions for Bokeh CustomJS callbacks
window.updateTapLinePositions = function(ms) {
    if (typeof ms === 'number' && !isNaN(ms)) {

        // Check if NoiseSurveyApp is initialized and ready
        if (window.NoiseSurveyApp && 
            typeof window.NoiseSurveyApp.updateTapLinePosition === 'function' && 
            window.NoiseSurveyApp.getState && 
            window.NoiseSurveyApp.getModels) {
            
            // Add extra defensive checks
            const models = window.NoiseSurveyApp.getModels();
            if (!models || !models.charts || models.charts.length === 0) {
                console.warn("NoiseSurveyApp initialized but charts not ready. Skipping updateTapLinePosition call.");
                console.log("models:", models);
                return false;
            }
            
            return window.NoiseSurveyApp.updateTapLinePosition(ms);
        } else {
            console.warn("NoiseSurveyApp not fully initialized yet. Skipping updateTapLinePosition call.");
            console.log("window.NoiseSurveyApp:", window.NoiseSurveyApp);
            return false;
        }
    } else {
        console.warn(`Global updateTapLinePositions called with invalid value: ${ms}`);
        return false;
    }
}; 

// Global wrapper for _sendSeekCommand
window.sendSeekCommand = function(ms) {
    if (typeof ms === 'number' && !isNaN(ms)) {
        console.log(`Global sendSeekCommand called with ms=${ms}`);
        // Check if NoiseSurveyApp is initialized and ready
        if (window.NoiseSurveyApp && 
            typeof window.NoiseSurveyApp.interactions.sendSeekCommand === 'function') {
            
            return window.NoiseSurveyApp.interactions.sendSeekCommand(ms);
        } else if (window.NoiseSurveyApp) {
            console.warn("NoiseSurveyApp initialized but sendSeekCommand not available. Falling back to updatePlaybackSource.");
            if (typeof window.NoiseSurveyApp.interactions.updatePlaybackSource === 'function') {
                return window.NoiseSurveyApp.interactions.updatePlaybackSource(ms);
            }
        } else {
            console.warn("NoiseSurveyApp not fully initialized yet. Cannot seek.");
            return false;
        }
    } else {
        console.warn(`Global sendSeekCommand called with invalid value: ${ms}`);
        return false;
    }
}; 

// Global wrapper for synchronizePlaybackPosition
window.synchronizePlaybackPosition = function(ms) {
    if (typeof ms === 'number' && !isNaN(ms)) {
        console.log(`Global synchronizePlaybackPosition called with ms=${ms}`);
        // Check if NoiseSurveyApp is initialized and ready
        if (window.NoiseSurveyApp && 
            typeof window.NoiseSurveyApp.synchronizePlaybackPosition === 'function') {
            
            return window.NoiseSurveyApp.synchronizePlaybackPosition(ms);
        } else {
            console.warn("NoiseSurveyApp not fully initialized yet or synchronizePlaybackPosition not available.");
            return false;
        }
    } else {
        console.warn(`Global synchronizePlaybackPosition called with invalid value: ${ms}`);
        return false;
    }
}; 