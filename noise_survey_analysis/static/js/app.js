/**
 * app.js - v3.3 (JS Handles Freq Bar Data, Position Toggle Refactored, EOF Handling)
 *
 * Unified JavaScript module for Noise Survey Analysis Visualization.
 * JS handles frequency bar DATA updates during playback, using data passed at init.
 * Adds toggle functionality to position-specific play/pause buttons.
 * Position play requests now use a dedicated playRequestSource CDS.
 * Includes function `notifyPlaybackStopped` called by Python on end-of-playback.
 *
 * WARNING: Requires Python to send potentially large 'prepared_data' during
 * initialization, which may impact performance and memory usage.
 * Python needs to listen to 'playRequestSource' changes to handle position play actions.
 */

window.NoiseSurveyApp = (function () {
    'use strict';

    // --- Private State & Models ---
    let _models = {
        charts: [],
        sources: {}, // Overview/log data sources
        clickLines: [],
        labels: [],
        playbackSource: null, // CDS {'current_time': [ms]} - Current playback time
        playButton: null,     // Main play button
        pauseButton: null,    // Main pause button
        positionPlayButtons: {}, // Dict: {pos_name: button_model}
        barSource: null,         // CDS for frequency bar chart {'levels':[], 'frequency_labels':[]}
        barXRange: null,         // FactorRange for frequency bar x-axis
        barChart: null,          // Frequency bar chart figure model
        paramSelect: null,
        selectedParamHolder: null,
        allSources: {},          // Potentially includes spectral image sources if needed
        spectralParamCharts: {}, // { pos: { available_params:[], prepared_data:{ param: { times_ms:[], levels_matrix:[], ... } } } }
        seekCommandSource: null, // CDS {'target_time': [ms]} - JS -> Python seek requests
        playRequestSource: null, // CDS {'position': [str|None], 'time': [ms|None]} - JS -> Python position play requests
    };

    let _state = {
        verticalLinePosition: null, // ms timestamp
        activeChartIndex: -1,       // Index of last chart tapped
        activeAudioPosition: null,  // Position name ('SW', 'N', etc.) playing
        isPlaying: false,           // Tracks if any audio is currently playing
        stepSize: 300000,           // ms for keyboard nav
        keyboardNavigationEnabled: false,
        selectedParameter: 'LZeq',  // Currently selected spectral parameter
    };

    // Debugging access
    window.__debugNoiseSurveyModels = _models;
    window.__debugNoiseSurveyState = _state;

    // --- Private Utility Functions ---
    // [findClosestDateIndex, findClosestIndex, createLabelText, positionLabel, calculateStepSize - unchanged]
    function findClosestDateIndex(dates, x) {
        // Add checks for robustness
        if (dates === null || dates === undefined || typeof dates.length !== 'number' || dates.length === 0) {
            // console.warn("findClosestDateIndex received invalid 'dates' array-like object");
            return -1;
        }
        if (typeof x !== 'number' || isNaN(x)) {
            // console.warn("findClosestDateIndex received invalid 'x' value:", x);
            return -1;
        }

        let low = 0;
        let high = dates.length - 1;
        let closest_idx = 0;
        let min_diff = Infinity;

        // Handle edge cases: x before start or after end
        if (x <= dates[0]) return 0;
        if (x >= dates[high]) return high;

        // Linear scan approach (robust for potentially unsorted/gappy data):
        min_diff = Math.abs(dates[0] - x); // Initialize difference
        for (let j = 1; j < dates.length; j++) {
            let diff = Math.abs(dates[j] - x);
            if (diff < min_diff) {
                min_diff = diff;
                closest_idx = j;
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
        if (!source || !source.data || !source.data.Datetime || closest_idx < 0 || closest_idx >= source.data.Datetime.length) {
            return "Error: Invalid data for label";
        }
        let date = new Date(source.data.Datetime[closest_idx]);
        let formatted_date = date.toLocaleString(); // Use locale-specific format
        let label_text = 'Time: ' + formatted_date + '\n';
        for (let key in source.data) {
            // Only include non-internal keys that have data at this index
            if (key !== 'Datetime' && key !== 'index' && source.data.hasOwnProperty(key) && source.data[key]?.length > closest_idx) {
                let value = source.data[key][closest_idx];
                if (value !== undefined && value !== null && !isNaN(value)) {
                    let formatted_value = parseFloat(value).toFixed(1);
                    // Basic check for common dB parameters - could be made more robust
                    let unit = (key.startsWith('L') || key.includes('eq') || key.includes('max') || key.includes('min')) ? ' dB' : '';
                    label_text += key + ': ' + formatted_value + unit + '\n';
                }
            }
        }
        return label_text;
    }

    function positionLabel(x, chart, labelModel) {
        if (!chart || !labelModel || !chart.x_range || !chart.y_range) return;
        const xStart = chart.x_range.start ?? 0; // Use nullish coalescing for defaults
        const xEnd = chart.x_range.end ?? 0;
        const yStart = chart.y_range.start ?? 0;
        const yEnd = chart.y_range.end ?? 0;

        if (xStart === xEnd || yStart === yEnd) return; // Avoid division by zero or nonsensical ranges

        const middleX = xStart + (xEnd - xStart) / 2;
        const topY = yEnd - (yEnd - yStart) / 5; // Position near top of chart

        // Position label to avoid overlapping the vertical line (x)
        if (x <= middleX) {
            labelModel.x = x + (xEnd - xStart) * 0.02; // Offset slightly right
            labelModel.text_align = 'left';
        } else {
            labelModel.x = x - (xEnd - xStart) * 0.02; // Offset slightly left
            labelModel.text_align = 'right';
        }
        labelModel.y = topY;
        labelModel.text_baseline = 'middle';
    }

    function calculateStepSize(source) {
        const DEFAULT_STEP_SIZE = 300000; // 5 minutes
     
        if (!source?.data?.Datetime || source.data.Datetime.length < 2) {
            console.warn("calculateStepSize: Invalid source data for step size calculation.");
            console.log("source.data:", source.data);
            return DEFAULT_STEP_SIZE;
        }
        const times = source.data.Datetime;

        const interval = times[5] - times[4];

        // Step size: interval, clamped between 1s and 1hr
        return Math.max(1000, Math.min(3600000, Math.round(interval)));
    }

    // --- Private Interaction Functions ---
    // [_updateChartLine, _updateTapLinePositions, _getActiveChartIndex, _hideAllLinesAndLabels, _sendSeekCommand - unchanged]
     function _updateChartLine(chart, clickLineModel, labelModel, x, chartIndex) {
        if (!chart || !clickLineModel || !labelModel) { return false; }
        clickLineModel.location = x;
        clickLineModel.visible = true;
        const sourceKey = chart.name;
        let source = null;
        // Labels only apply to overview/log charts
        if (!sourceKey || sourceKey === 'range_selector' || sourceKey === 'shared_range_selector' || sourceKey === 'frequency_bar' || sourceKey.includes('_spectral')) {
            labelModel.visible = false; return true;
        }
        if (_models.sources && _models.sources.hasOwnProperty(sourceKey)) { source = _models.sources[sourceKey]; }
        if (!source?.data?.Datetime) { labelModel.visible = false; return true; } // Simplified check

        let closest_idx = findClosestDateIndex(source.data.Datetime, x);
        if (closest_idx !== -1) {
            let label_text = createLabelText(source, closest_idx);
            positionLabel(x, chart, labelModel);
            labelModel.text = label_text;
            labelModel.visible = true;
            // Update step size based on the actively tapped chart's data
            if (_state.activeChartIndex === chartIndex) { _state.stepSize = calculateStepSize(source); }
            return true;
        } else {
            labelModel.visible = false; return true;
        }
    }

    function _updateTapLinePositions(x) {
        if (typeof x !== 'number' || isNaN(x)) {
             console.warn("Attempted to update tap line with invalid position:", x);
             return false;
        }
        _state.verticalLinePosition = x;
        if (!_models?.charts || !Array.isArray(_models.charts) || _models.charts.length === 0) { return false; }
        for (let i = 0; i < _models.charts.length; i++) {
            if (_models.charts[i]?.name === 'frequency_bar') continue; // Skip freq bar chart itself
            // Check models exist for this index before calling update
            if (_models.charts[i] && _models.clickLines?.[i] && _models.labels?.[i]) {
                _updateChartLine(_models.charts[i], _models.clickLines[i], _models.labels[i], x, i);
            }
        }
        return true;
    }

    function _getActiveChartIndex(cb_obj) {
        let activeChartIndex = -1;
        if (!cb_obj?.origin?.id || !_models.charts) { return -1; } // Check id exists
        activeChartIndex = _models.charts.findIndex(chart => chart?.id === cb_obj.origin.id);
        return activeChartIndex; // Will be -1 if not found
    }

    function _hideAllLinesAndLabels() {
        if (!_models.clickLines || !_models.labels) return false;
        try {
            _models.clickLines.forEach(line => { if (line) line.visible = false; });
            _models.labels.forEach(label => { if (label) label.visible = false; });
            return true;
        } catch (error) { console.error("Error hiding lines/labels:", error); return false; }
    }

    function _sendSeekCommand(x) {
        if (!_models.seekCommandSource) { console.error("seekCommandSource not available!"); return; }
        if (typeof x !== 'number' || isNaN(x)) { console.warn(`Invalid seek time: ${x}`); return; }
        console.debug(`Sending seek command to ${x}ms`);
        _models.seekCommandSource.data = { 'target_time': [x] };
        _models.seekCommandSource.change.emit();
    }

    // --- Frequency Bar Update ---
    // [_updateBarChart - unchanged]
    function _updateBarChart(x, activeChartIndex, activeAudioPos, title_source = '') {
        const barSource = _models.barSource;
        const barXRange = _models.barXRange;
        const barChart = _models.barChart;
        const spectralDataStore = _models.spectralParamCharts; // Should contain prepared_data now
        const selectedParam = _state.selectedParameter;

        if (!barSource || !barXRange || !barChart || !spectralDataStore || Object.keys(spectralDataStore).length === 0) {
            // console.warn("Missing required models/data for _updateBarChart."); // Can be noisy
            return;
        }

        let position = "Unknown";
        let interactionSourceInfo = ""; // Info for title source

        // Determine position: Prioritize active audio position if provided (during playback)
        if (activeAudioPos && spectralDataStore[activeAudioPos]) { // Check if position exists in data
            position = activeAudioPos;
            interactionSourceInfo = title_source || "Audio Playback";
        } else if (activeChartIndex !== null && activeChartIndex >= 0 && _models.charts?.[activeChartIndex]?.name) {
            // Otherwise, use the index from user interaction (tap/hover)
            const chartName = _models.charts[activeChartIndex].name;
            // Extract position name (assuming format like 'SW_overview', 'N_log', 'E_spectral')
            const possiblePos = chartName.split('_')[0];
            if (spectralDataStore[possiblePos]) { // Check if derived position exists
                position = possiblePos;
                interactionSourceInfo = title_source || "User Interaction";
            }
        }

        // If still Unknown, try a fallback (e.g., first available position)
        if (position === "Unknown") {
            const firstPosKey = Object.keys(spectralDataStore)[0];
            if (firstPosKey && spectralDataStore[firstPosKey]) {
                position = firstPosKey;
                interactionSourceInfo = "Fallback";
                console.debug(`_updateBarChart: No specific position context, falling back to first position: ${position}`);
            } else {
                console.warn("Cannot determine position for frequency bar update.");
                // Clear chart?
                barSource.data = { 'levels': [], 'frequency_labels': [] }; barXRange.factors = []; barSource.change.emit();
                if (barChart.title) barChart.title.text = `Frequency Slice: (No Position Data)`;
                return;
            }
        }


        // --- Access Prepared Data ---
        const positionDataContainer = spectralDataStore[position];
        if (!positionDataContainer) {
            console.warn(`No spectral data container found for resolved position: ${position}`);
            barSource.data = { 'levels': [], 'frequency_labels': [] }; barXRange.factors = []; barSource.change.emit();
            if (barChart.title) barChart.title.text = `Frequency Slice: ${position} (Data Missing)`;
            return;
        }

        // Check parameter availability
        if (!positionDataContainer.available_params?.includes(selectedParam)) {
            // console.warn(`Parameter ${selectedParam} not available for position ${position}.`);
            barSource.data = { 'levels': [], 'frequency_labels': [] }; barXRange.factors = []; barSource.change.emit();
            if (barChart.title) barChart.title.text = `Frequency Slice: ${position} | ${selectedParam} (N/A)`;
            return;
        }

        // Get the actual prepared data for the selected parameter
        const preparedData = positionDataContainer.prepared_data?.[selectedParam];
        if (!preparedData) {
            console.warn(`No prepared_data found for position ${position}, parameter ${selectedParam}.`);
            barSource.data = { 'levels': [], 'frequency_labels': [] }; barXRange.factors = []; barSource.change.emit();
            if (barChart.title) barChart.title.text = `Frequency Slice: ${position} | ${selectedParam} (Data Missing)`;
            return;
        }

        // --- Extract Data for Time 'x' ---
        const times = preparedData.times_ms;
        // Prefer flattened matrix if available, otherwise assume [times][freqs]
        const levels_matrix_flat = preparedData.levels_matrix;
        const freq_labels = preparedData.frequency_labels;
        const n_freqs = freq_labels?.length || 0;

        if (!times || (!levels_matrix_flat) || !freq_labels || n_freqs === 0) {
            console.warn(`Missing critical data (times, levels, labels) in preparedData for ${position}/${selectedParam}.`);
            return;
        }

        // Find closest time index
        let closestTimeIdx = findClosestDateIndex(times, x);
        if (closestTimeIdx === -1) {
            console.warn(`Could not find valid time index for ${x}ms.`);
            return;
        }

        // Get frequency data slice for this time
        let freqDataSlice = null;
        if (levels_matrix_flat) {
            const start_idx = closestTimeIdx * n_freqs;
            const end_idx = start_idx + n_freqs;
            if (start_idx >= 0 && end_idx <= levels_matrix_flat.length) {
                freqDataSlice = levels_matrix_flat.slice(start_idx, end_idx);
            } else {
                console.warn(`Flat matrix slice indices out of bounds: ${start_idx}-${end_idx}`);
            }
        // } else if (levels_matrix && closestTimeIdx < levels_matrix.length) { // Fallback for non-flat? (Shouldn't be needed with current structure)
        //     freqDataSlice = levels_matrix[closestTimeIdx];
        }


        if (!freqDataSlice || freqDataSlice.length !== n_freqs) {
            console.warn(`Frequency data slice at index ${closestTimeIdx} is invalid or has wrong length (${freqDataSlice?.length} vs ${n_freqs}).`);
            // Optionally clear chart instead of showing potentially wrong data
            // barSource.data = { 'levels': [], 'frequency_labels': [] }; barXRange.factors = []; barSource.change.emit();
            return;
        }

        // Clean data (replace null/NaN with 0)
        const cleanedLevels = freqDataSlice.map(level => (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);

        // --- Update Bar Chart Source and Title ---
        // Avoid unnecessary updates if data is identical? (More complex check needed)
        barSource.data = {
            'levels': cleanedLevels,
            'frequency_labels': freq_labels
        };
        barXRange.factors = freq_labels; // Update factors

        let timeString = new Date(x).toLocaleString();
        barChart.title.text = `Frequency Slice: ${position} | ${selectedParam} | ${timeString} (${interactionSourceInfo})`;

        // Emit change
        barSource.change.emit();
    }

    // Spectrogram Hover Tool
    // [_handleSpectrogramHover - unchanged]
     function _handleSpectrogramHover(cb_data, hover_div, bar_source_arg, bar_x_range_arg, position_name, times_array, freqs_array, freq_labels_array, levels_matrix_unused, levels_flat_array, fig_x_range) {
        try {
            const div = hover_div;
            const bar_source_js = bar_source_arg || _models.barSource;
            const bar_x_range_js = bar_x_range_arg || _models.barXRange;
            if (!div || !bar_source_js || !bar_x_range_js || !fig_x_range) { console.warn("Missing models/args for handleSpectrogramHover"); return false; }
            const times = times_array, freqs = freqs_array, freq_labels_str = freq_labels_array, levels_flat = levels_flat_array;
            if (!times || !freqs || !freq_labels_str || !levels_flat) { console.warn("Missing data arrays for handleSpectrogramHover"); return false; }
            const n_times = times.length, n_freqs = freqs.length;
            const x_start = fig_x_range.start, x_end = fig_x_range.end;
            const barChart = _models.barChart;
            if (!barChart) { console.error("Spectrogram Hover: No global bar chart model found"); return false; }
            const { x: gx, y: gy } = cb_data.geometry;
            const is_inside = !(gx < x_start || gx > x_end || gy < -0.5 || gy > n_freqs - 0.5 || n_times === 0 || n_freqs === 0);

            if (is_inside) {
                const time_idx = findClosestDateIndex(times, gx);
                if (time_idx === -1) { console.warn("Spectrogram Hover: Could not find time index."); return false; }
                const freq_idx = Math.max(0, Math.min(n_freqs - 1, Math.floor(gy + 0.5)));
                const time_val_ms = times[time_idx];
                const flat_index_hover = time_idx * n_freqs + freq_idx;
                if (flat_index_hover < 0 || flat_index_hover >= levels_flat.length || freq_idx < 0 || freq_idx >= freq_labels_str.length) { console.warn(`Spectrogram Hover: Index out of bounds.`); div.text = "Data Error"; div.change.emit(); return false; }
                const level_val_hover = levels_flat[flat_index_hover];
                const time_str = new Date(time_val_ms).toLocaleString();
                const freq_str = freq_labels_str[freq_idx];
                let level_str_hover = (level_val_hover === null || level_val_hover === undefined || Number.isNaN(level_val_hover)) ? "N/A" : level_val_hover.toFixed(1) + " dB";
                div.text = `<b>Time:</b> ${time_str} | <b>Freq:</b> ${freq_str} | <b>Level:</b> ${level_str_hover}`;
                div.change.emit();

                // --- Update Bar Chart DATA and TITLE from Hover Data ---
                const start_index_slice = time_idx * n_freqs;
                const end_index_slice = start_index_slice + n_freqs;
                if (start_index_slice < 0 || end_index_slice > levels_flat.length) { console.warn(`Spectrogram Hover: Slice indices out of bounds.`); return false; }
                let levels_slice = levels_flat.slice(start_index_slice, end_index_slice);
                if (levels_slice.length !== n_freqs || freq_labels_str.length !== n_freqs) { console.error(`Spectrogram Hover: Length mismatch.`); levels_slice = Array(n_freqs).fill(0); }
                else { levels_slice = levels_slice.map(level => (level === null || level === undefined || Number.isNaN(level)) ? 0 : level); }
                const cleanData = { 'levels': levels_slice, 'frequency_labels': freq_labels_str };
                bar_source_js.data = cleanData; // Update data
                bar_x_range_js.factors = freq_labels_str; // Update factors
                const timeForTitle = new Date(time_val_ms).toLocaleTimeString();
                barChart.title.text = `Frequency Slice: ${position_name} | ${_state.selectedParameter} | ${timeForTitle} (Hover)`; // Update title
                bar_source_js.change.emit();
                return true;
            } else {
                div.text = "Hover over spectrogram to view details";
                div.change.emit();
                // Restore frequency bar to click line position (JS handles data/title now)
                if (_state.verticalLinePosition !== null) {
                    // Call the main update function using the click position state
                    // Pass null for activeAudioPos if not playing, otherwise use current state
                    const activePosForRestore = _state.isPlaying ? _state.activeAudioPosition : null;
                    _updateBarChart(_state.verticalLinePosition, _state.activeChartIndex, activePosForRestore, "Click Line");
                } else if (barChart.title) {
                    barChart.title.text = `Frequency Slice`; // Reset title only
                    // Optionally clear data if no click position
                    bar_source_js.data = { 'levels': [], 'frequency_labels': [] }; bar_x_range_js.factors = []; bar_source_js.change.emit();
                }
                return true;
            }
        } catch (error) { console.error("Error in handleSpectrogramHover:", error); return false; }
    }

    // --- Audio Button State Management ---
    // [_updatePlayButtonsState - unchanged]
     function _updatePlayButtonsState(isPlaying) {
        // Main play/pause buttons
        if (_models.playButton) { _models.playButton.disabled = isPlaying; }
        if (_models.pauseButton) { _models.pauseButton.disabled = !isPlaying; }

        // Position-specific play/pause buttons
        if (_models.positionPlayButtons && typeof _models.positionPlayButtons === 'object') {
            Object.keys(_models.positionPlayButtons).forEach(posName => {
                const button = _models.positionPlayButtons[posName];
                // Check if it looks like a Bokeh button model
                // Use a more robust check for Bokeh model properties
                if (button && typeof button.set === 'function' && button.hasOwnProperty('label') && button.hasOwnProperty('button_type') && button.hasOwnProperty('disabled')) {
                    const isActivePosition = isPlaying && posName === _state.activeAudioPosition;

                    if (isActivePosition) {
                        // This position is playing: Show Pause state
                        button.label = `Pause ${posName}`;
                        button.button_type = "warning"; // e.g., 'warning' or 'danger' for pause
                        button.disabled = false; // Enable clicking to pause
                    } else {
                        // This position is NOT playing: Show Play state
                        button.label = `Play ${posName}`;
                        button.button_type = "default"; // e.g., 'default', 'primary', or 'success' for play
                        // Disable if *any* audio is playing (can't start another)
                        button.disabled = isPlaying;
                    }
                } else if (button !== null && button !== undefined) { // Log only if it exists but isn't valid
                     // Avoid logging if the button genuinely wasn't created/passed for this position
                     console.warn(`Item '${posName}' in positionPlayButtons is not a valid Bokeh button model or is missing properties.`);
                     // console.log("Button object:", button); // Uncomment for detailed debugging
                }
            });
        }
    }

    // --- Public API - Initialize App ---
    function initializeApp(models, options) {
        console.info('NoiseSurveyApp - Initializing with hierarchical structure support...');
        try {
            console.log('Setting global models...');
            
            // Check if using hierarchical structure (passed from Python)
            const usingHierarchicalStructure = models.hierarchical === true;
            console.log(`Using ${usingHierarchicalStructure ? 'hierarchical' : 'legacy'} structure`);
            
            // Assign models from the structure provided
            _models.charts = models.charts || [];
            _models.sources = models.sources || {}; // Overview/log chart sources
            _models.clickLines = models.clickLines || [];
            _models.labels = models.labels || [];
            _models.playbackSource = models.playback_source || null;
            _models.playButton = models.play_button || null;
            _models.pauseButton = models.pause_button || null;
            _models.positionPlayButtons = models.position_play_buttons || {}; // Store dict
            _models.barSource = models.bar_source || null;
            _models.barXRange = models.bar_x_range || null;
            _models.barChart = models.barChart || _models.charts.find(c => c?.name === 'frequency_bar') || null;
            _models.paramSelect = models.param_select || null;
            _models.selectedParamHolder = models.param_holder || null;
            _models.allSources = models.all_sources || {}; // If needed
            _models.spectralParamCharts = models.spectral_param_charts || {};
            _models.seekCommandSource = models.seek_command_source || null;
            _models.playRequestSource = models.play_request_source || null; // NEW: Get play request source

            console.log('Global models set.');

            // --- Model Validation ---
            if (!_models.playbackSource) { console.error("Initialization Error: playback_source model missing!"); }
            if (!_models.playButton) { console.warn("Initialization Warning: Main play_button model missing."); }
            if (!_models.pauseButton) { console.warn("Initialization Warning: Main pause_button model missing."); }
            if (!_models.seekCommandSource) { console.error("Initialization Error: seek_command_source model missing!"); }
            if (!_models.playRequestSource) { console.error("Initialization Error: play_request_source model missing!"); } // Essential for new logic
            if (!_models.barChart) { console.warn("Initialization Warning: Frequency bar chart model not found."); }
            if (!_models.barSource) { console.warn("Initialization Warning: Frequency bar chart data source not found."); }
            if (!_models.barXRange) { console.warn("Initialization Warning: Frequency bar chart x-range not found."); }
            if (Object.keys(_models.positionPlayButtons || {}).length === 0) { console.warn("Initialization Warning: No position play button models found."); }
            if (Object.keys(_models.spectralParamCharts || {}).length === 0) {
                console.warn("Initialization Warning: Spectral parameter chart data store is empty! Frequency bar updates during playback may fail.");
            }

            // Validate individual position buttons
            Object.keys(_models.positionPlayButtons).forEach(posName => {
                 const button = _models.positionPlayButtons[posName];
                 if (!button || typeof button.set !== 'function' || !button.hasOwnProperty('label')) {
                      console.error(`Initialization Error: Position button for '${posName}' is not a valid Bokeh model or is missing properties.`);
                 }
            });
            // --- End Model Validation ---


            // Set state from models
            if (_models.selectedParamHolder?.text) { _state.selectedParameter = _models.selectedParamHolder.text; }
            _state.isPlaying = false; // Initialize playback state

            // Initialize playback time
            if (_models.playbackSource) {
                let initialTimeMs = 0;
                // Default to chart start if available
                if (_models.charts.length > 0 && _models.charts[0]?.x_range?.start !== undefined && _models.charts[0]?.x_range?.start !== null) {
                     initialTimeMs = _models.charts[0].x_range.start;
                }
                // Ensure data structure exists and initialize/reset time
                if (!_models.playbackSource.data || typeof _models.playbackSource.data !== 'object') {
                     _models.playbackSource.data = { 'current_time': [initialTimeMs] };
                } else {
                     _models.playbackSource.data['current_time'] = [initialTimeMs];
                }
                hideTapLines(); // Hide lines initially
                _state.verticalLinePosition = initialTimeMs; // Sync internal state
                console.log('Playback source position initialized:', _state.verticalLinePosition);
            } else { console.error("Initialization Error: Cannot initialize playback time - playbackSource missing."); }

            _updatePlayButtonsState(false); // Set initial button states (not playing)
            const kbNavEnabled = options?.enableKeyboardNavigation ?? false; // Default to false if option missing
            if (kbNavEnabled) { setupKeyboardNavigation(); }
            else { _state.keyboardNavigationEnabled = false; console.log("Keyboard navigation disabled."); }

            console.info('NoiseSurveyApp - Initialization complete.');
            // console.log('Models:', _models); // Can be verbose
            return true;
        } catch (error) { console.error('Error during initialization:', error); return false; }
    }

    // --- Audio Player Integration ---
    // [synchronizePlaybackPosition - unchanged]
     function synchronizePlaybackPosition(ms) {
        try {
            // console.debug(`Sync viz to: ${ms}ms, Active Audio Pos: ${_state.activeAudioPosition}`);
            if (!_state.isPlaying) {
                // If Python sends sync update but JS thinks it's paused, log warning and potentially pause Python side?
                console.warn("synchronizePlaybackPosition called while _state.isPlaying is false. State mismatch?");
                // Optionally, attempt to pause Python side:
                // pauseAudioPlayback(); // Careful: this might trigger unwanted state changes if called rapidly
                return false; // Don't update visuals if supposed to be paused
            }
             // Ensure ms is valid before updating
             if (typeof ms === 'number' && !isNaN(ms)) {
                _updateTapLinePositions(ms);
                // Update frequency bar DATA and TITLE using the stored active position
                // Pass null for activeChartIndex to prioritize activeAudioPosition
                _updateBarChart(ms, null, _state.activeAudioPosition, "Audio Playback");
             } else {
                  console.warn("synchronizePlaybackPosition called with invalid time:", ms);
             }

            return true;
        } catch (error) { console.error('Error synchronizing playback visualization:', error); return false; }
    }

    // [notifyPlaybackStopped - unchanged]
     function notifyPlaybackStopped() {
        console.log("JS: Received notification that playback stopped (e.g., EOF or error). Resetting state.");
        if (_state.isPlaying) { // Only reset if JS thought it was playing
            _state.isPlaying = false;
            _state.activeAudioPosition = null;
            _updatePlayButtonsState(false);
        } else {
            console.log("JS: notifyPlaybackStopped called, but already in paused state.");
            // Ensure buttons are visually correct even if state was already false
             _updatePlayButtonsState(false);
        }
    }

    // --- Parameter Selection ---
    // [handleParameterChange - unchanged]
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

                // Find the corresponding image glyph renderer's data source
                 const imageRenderer = chart.renderers.find(r => r.glyph?.type === 'ImageURL' || r.glyph?.type === 'ImageRGBA' || r.glyph?.type === 'Image'); // Find the image renderer
                 const source = imageRenderer?.data_source;

                if (!source) {
                     console.warn(`Source not found for spectral chart at position ${position}`);
                     continue;
                }

                // Skip positions that don't have this parameter
                if (!availableParams.includes(param)) {
                    console.log(`Parameter ${param} not available for position ${position}. Clearing image.`);
                    // Clear the image data or set to a placeholder
                    source.data.image = []; // Or provide a transparent/empty image array matching dimensions
                    source.data.x = [];
                    source.data.y = [];
                    source.data.dw = [];
                    source.data.dh = [];
                    chart.title.text = `${position} - ${param} (N/A)`;
                    source.change.emit();
                    continue;
                }

                // Get the prepared data for this parameter
                const preparedData = positionData.prepared_data?.[param];
                if (!preparedData) {
                    console.warn(`No prepared data for position ${position} with parameter ${param}. Clearing image.`);
                    source.data.image = []; source.data.x = []; source.data.y = []; source.data.dw = []; source.data.dh = [];
                    chart.title.text = `${position} - ${param} (Data Missing)`;
                    source.change.emit();
                    continue;
                }

                // Update the data in the source
                source.data.image = preparedData.levels_matrix_transposed ? [preparedData.levels_matrix_transposed] : [];
                source.data.x = preparedData.x ? [preparedData.x] : [];
                source.data.y = preparedData.y ? [preparedData.y] : [];
                source.data.dw = preparedData.dw ? [preparedData.dw] : [];
                source.data.dh = preparedData.dh ? [preparedData.dh] : [];

                // Update the chart title
                chart.title.text = `${position} - ${param} Spectral Data`;

                // Update color mapper range if necessary
                const colorMapper = imageRenderer?.glyph?.color_mapper;
                if (colorMapper && preparedData.color_range_low !== undefined && preparedData.color_range_high !== undefined) {
                    colorMapper.low = preparedData.color_range_low;
                    colorMapper.high = preparedData.color_range_high;
                } else if (colorMapper) {
                     console.warn(`Color range data missing for ${position}/${param}, color bar may be inaccurate.`);
                }

                // Signal that the data has changed
                source.change.emit();
                console.log(`Updated ${position} spectrogram to parameter ${param}`);
            }

            // If a click line is active, update the frequency bar with the new parameter
            const activePosForUpdate = _state.isPlaying ? _state.activeAudioPosition : null;
            const activeIndexForUpdate = _state.isPlaying ? null : _state.activeChartIndex;
            if (_state.verticalLinePosition !== null) {
                _updateBarChart(_state.verticalLinePosition, activeIndexForUpdate, activePosForUpdate, "Parameter Change");
            }

            return true;
        } catch (error) {
            console.error('Error handling parameter change:', error);
            return false;
        }
    }

    // Public wrapper for _updateBarChart
    // [updateFrequencyBar - unchanged]
     function updateFrequencyBar(x, activeChartIndex, title_source = '') {
        try {
            if (typeof x !== 'number' || isNaN(x)) { return false; }
            // Call internal function - activeAudioPos is null for user interactions unless already playing
            const activePos = _state.isPlaying ? _state.activeAudioPosition : null;
            _updateBarChart(x, activeChartIndex, activePos, title_source);
            return true;
        } catch (error) { console.error("Error updating frequency bar:", error); return false; }
    }

    // --- Tap Line Visibility ---
    // [showTapLines, hideTapLines, updateTapLinePosition - unchanged]
     function showTapLines() {
        if (!_models.clickLines) return false;
        try {
            if (_state.verticalLinePosition !== null) { _updateTapLinePositions(_state.verticalLinePosition); }
            // Only make lines visible, labels are handled by _updateChartLine
            _models.clickLines.forEach(line => { if (line) line.visible = true; });
            // Ensure labels corresponding to the current position are visible
            if (_state.verticalLinePosition !== null) {
                 _models.charts.forEach((chart, i) => {
                      if (chart && _models.clickLines?.[i] && _models.labels?.[i]) {
                           _updateChartLine(chart, _models.clickLines[i], _models.labels[i], _state.verticalLinePosition, i);
                      }
                 });
            }
            return true;
        } catch (error) { console.error("Error showing tap lines:", error); return false; }
    }
    function hideTapLines() { return _hideAllLinesAndLabels(); }
    
    function updateTapLinePosition(x) {
        if (typeof x !== 'number' || isNaN(x)) { return false; }
        try { return _updateTapLinePositions(x); }
        catch (error) { console.error("Error updating tap line position:", error); return false; }
    }

    // --- JS Audio Control Wrappers (trigger Python via model changes) ---

    // [startAudioPlayback - unchanged]
     function startAudioPlayback() {
        try {
            if (!_models.playButton) { console.warn("Main Play button model missing."); return false; }
            if (!_models.playButton.disabled) { // Check if already playing (button is disabled if so)
                console.log("JS: Triggering main Play button click via model");

                // Optimistically update state - Python callback should confirm/correct if needed
                _state.isPlaying = true;
                // If activeAudioPosition isn't set, Python needs a default or error handling
                if (!_state.activeAudioPosition && Object.keys(_models.positionPlayButtons).length > 0) {
                     // Attempt to set a default if none is active
                     _state.activeAudioPosition = Object.keys(_models.positionPlayButtons)[0];
                     console.log("No active position set, defaulting to:", _state.activeAudioPosition);
                } else if (!_state.activeAudioPosition) {
                     console.error("Cannot start playback: No active audio position set and no position buttons found.");
                     _state.isPlaying = false; // Revert state
                     _updatePlayButtonsState(false); // Update buttons to reflect reverted state
                     return false;
                }

                _updatePlayButtonsState(true); // Update button visuals

                // Trigger the Bokeh model change, which Python listens for
                _models.playButton.clicks = (_models.playButton.clicks || 0) + 1;
                _models.playButton.change.emit();
                return true;
            } else {
                console.warn("JS: Main Play button is disabled (already playing?).");
                return false;
            }
        } catch (error) {
            console.error("Error triggering start audio from JS:", error);
            _state.isPlaying = false; // Revert state on error
            _updatePlayButtonsState(false);
            return false;
        }
    }

    // [pauseAudioPlayback - unchanged]
     function pauseAudioPlayback() {
        try {
            if (!_models.pauseButton) { console.warn("Main Pause button model missing."); return false; }
            if (!_models.pauseButton.disabled) { // Check if already paused (button is disabled if so)
                console.log("JS: Triggering main Pause button click via model");

                // Optimistically update state - Python callback should confirm/correct if needed
                const wasPlaying = _state.isPlaying; // Store previous state
                _state.isPlaying = false;
                _state.activeAudioPosition = null; // Clear active position on pause
                _updatePlayButtonsState(false); // Update button visuals

                // Trigger the Bokeh model change, which Python listens for
                _models.pauseButton.clicks = (_models.pauseButton.clicks || 0) + 1;
                _models.pauseButton.change.emit();
                return true;
            } else {
                console.warn("JS: Main Pause button is disabled (already paused?).");
                return false;
            }
        } catch (error) {
            console.error("Error triggering pause audio from JS:", error);
            // Revert state on error? Depends if pause actually failed.
            // Assume pause might have worked partially, keep paused state for safety.
             _state.isPlaying = false;
             _state.activeAudioPosition = null;
             _updatePlayButtonsState(false);
            return false;
        }
    }

    // REFACTORED: Handles clicks on the POSITION-SPECIFIC play/pause buttons
    function handlePositionPlayClick(positionName) {
        console.log(`handlePositionPlayClick called for: ${positionName}`);
        if (!_models.positionPlayButtons[positionName]) {
            console.error(`Button model for position ${positionName} not found.`);
            return false;
        }
        if (!_models.playRequestSource) {
             console.error("Cannot handle position play click: playRequestSource model is missing!");
             return false;
        }

        const currentlyPlaying = _state.isPlaying;
        const currentPosition = _state.activeAudioPosition;

        // Case 1: Clicking the button for the currently playing position (request Pause)
        if (currentlyPlaying && positionName === currentPosition) {
            console.log(`Requesting PAUSE for active position: ${positionName}`);
            // Trigger the main pause mechanism (which updates state and triggers Python _pause_click)
            pauseAudioPlayback();
        }
        // Case 2: Clicking to play this position (either nothing playing, or different position playing)
        else {
            console.log(`Requesting PLAY for position: ${positionName}`);
            // If another position is playing, Python's _handle_play_request MUST handle stopping it first.

            // Update JS state optimistically
            _state.activeAudioPosition = positionName;
            _state.isPlaying = true; // Assume play will start
            _updatePlayButtonsState(true); // Update button visuals immediately

            // Update the frequency bar immediately to reflect the requested state
             if (_state.verticalLinePosition !== null) {
                 _updateBarChart(_state.verticalLinePosition, null, _state.activeAudioPosition, "Position Play Click");
             } else {
                  console.warn("Cannot update frequency bar on position play click: verticalLinePosition is null.");
             }

            // *** NEW: Trigger Python via the dedicated playRequestSource ***
            const currentTime = _state.verticalLinePosition;
            console.log(`Updating playRequestSource: position=${positionName}, time=${currentTime}`);
            _models.playRequestSource.data = {'position': [positionName], 'time': [currentTime]};
            _models.playRequestSource.change.emit(); // Signal Python to handle the request

            // NOTE: The Python callback attached to playRequestSource is now responsible
            // for the actual audio logic (stop old, set position, play new).
        }
        return true;
    }

    // [togglePlayPause - unchanged]
     function togglePlayPause() {
        try {
            // This toggles based on the MAIN pause button's state
            if (!_models.playButton || !_models.pauseButton) { console.warn("Main Play/Pause button models missing."); return false; }

            if (!_models.pauseButton.disabled) { // If pause is ENABLED, it means we are currently playing
                return pauseAudioPlayback();
            } else if (!_models.playButton.disabled) { // If play is ENABLED, it means we are currently paused
                 // When toggling play from paused state, ensure an active position is selected or default
                 if (!_state.activeAudioPosition && Object.keys(_models.positionPlayButtons).length > 0) {
                      _state.activeAudioPosition = Object.keys(_models.positionPlayButtons)[0];
                      console.log("Toggle Play: No active position, defaulting to:", _state.activeAudioPosition);
                 } else if (!_state.activeAudioPosition) {
                      console.error("Toggle Play: Cannot start playback - no position selected and no defaults available.");
                      return false;
                 }
                return startAudioPlayback();
            } else {
                // This state should ideally not happen if logic is correct
                console.warn("Toggle Play/Pause: Both Play and Pause buttons seem disabled.");
                return false;
            }
        } catch (error) { console.error("Error toggling play/pause from JS:", error); return false; }
    }

    // --- Keyboard Navigation ---
    // [enableKeyboardNavigation, disableKeyboardNavigation, handleKeyPress, setupKeyboardNavigation - unchanged]
     function enableKeyboardNavigation() {
        if (!_state.keyboardNavigationEnabled) {
            try {
                document.addEventListener('keydown', handleKeyPress);
                _state.keyboardNavigationEnabled = true;
                console.log('Keyboard navigation enabled');
                return true;
            } catch (error) { console.error("Error enabling keyboard navigation:", error); return false; }
        }
        return true; // Already enabled
    }
    function disableKeyboardNavigation() {
        if (_state.keyboardNavigationEnabled) {
            try {
                document.removeEventListener('keydown', handleKeyPress);
                _state.keyboardNavigationEnabled = false;
                console.log('Keyboard navigation disabled');
                return true;
            } catch (error) { console.error("Error disabling keyboard navigation:", error); return false; }
        }
        return true; // Already disabled
    }
    function handleKeyPress(e) {
        // Allow keyboard input in text fields, etc.
        const targetTagName = e.target.tagName.toLowerCase();
         if (targetTagName === 'input' || targetTagName === 'textarea' || targetTagName === 'select') {
             // Don't interfere with form inputs
             return;
         }

        // Basic check for models needed for navigation/playback
        if (!_models.playbackSource || !_models.seekCommandSource) { console.warn("Keyboard nav disabled: models not ready."); return; }

        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            e.preventDefault();
            let currentX = _state.verticalLinePosition ?? _models.playbackSource.data?.current_time?.[0];
            if (currentX === null || currentX === undefined) { // Try chart center fallback
                currentX = (_models.charts?.[0]?.x_range?.start + _models.charts?.[0]?.x_range?.end) / 2;
            }
            if (currentX === null || currentX === undefined || isNaN(currentX)) { console.warn("Keyboard nav: Cannot determine current X."); return; }

            let step = _state.stepSize || 300000;
            let newX = e.key === 'ArrowLeft' ? currentX - step : currentX + step;

             // Clamp navigation within the main chart's range if possible
             if (_models.charts?.[0]?.x_range) {
                  const minX = _models.charts[0].x_range.start;
                  const maxX = _models.charts[0].x_range.end;
                  if (newX < minX) newX = minX;
                  if (newX > maxX) newX = maxX;
             }


            updateTapLinePosition(newX); // Update visuals
            _sendSeekCommand(newX);      // Send command to Python (e.g., for audio seeking if implemented)

            // Update frequency bar based on this keyboard nav interaction
            const activePosForNav = _state.isPlaying ? _state.activeAudioPosition : null;
            const activeIndexForNav = _state.isPlaying ? null : _state.activeChartIndex;
            _updateBarChart(newX, activeIndexForNav, activePosForNav, "Keyboard Nav");

        } else if (e.key === ' ' || e.code === 'Space') {
            e.preventDefault();
            togglePlayPause(); // Use the JS toggle function
        }
    }
    function setupKeyboardNavigation() { return enableKeyboardNavigation(); } // Helper

    // --- Chart Interaction Handlers ---
    // [onTapHandler, onHoverHandler - unchanged]
     function onTapHandler(cb_obj) {
        try {
            _state.activeChartIndex = _getActiveChartIndex(cb_obj); // Store index of tapped chart
            const x = cb_obj.x;
            if (x === undefined || x === null || isNaN(x)) {
                 console.warn("Tap handler received invalid x coordinate:", x);
                 return false;
            }
            _updateTapLinePositions(x); // Update lines
            _sendSeekCommand(x);        // Send seek command to Python

            // Update frequency bar based on tap location and chart index
             const activePosForTap = _state.isPlaying ? _state.activeAudioPosition : null;
             const activeIndexForTap = _state.isPlaying ? null : _state.activeChartIndex;
            _updateBarChart(x, activeIndexForTap, activePosForTap, "Click Line");
            return true;
        } catch (error) { console.error("Error handling tap:", error); return false; }
    }

    function onHoverHandler(hoverLines, cb_data) {
        try {
            if (!cb_data?.geometry || typeof cb_data.geometry.x !== 'number') {
                 // If geometry is invalid (e.g., mouse moved off chart), restore freq bar to click line pos
                 if (_state.verticalLinePosition !== null) {
                      const activePosForRestore = _state.isPlaying ? _state.activeAudioPosition : null;
                      const activeIndexForRestore = _state.isPlaying ? null : _state.activeChartIndex;
                      _updateBarChart(_state.verticalLinePosition, activeIndexForRestore, activePosForRestore, "Click Line");
                 }
                 return false;
            }
            const hoveredX = cb_data.geometry.x;

            // Update hover lines (spans)
            if (hoverLines && Array.isArray(hoverLines)) { hoverLines.forEach(line => { if(line) line.location = hoveredX; }); }

            let hoveredChartIndex = -1;
             if (cb_data.event_name === 'mousemove' && cb_data.tool_type === 'HoverTool') {
                 // Logic to find hovered chart index might need refinement
             } else if (cb_data.geometries?.[0]?.model) {
                 hoveredChartIndex = _models.charts.findIndex(c => c?.id === cb_data.geometries[0].model.id);
             }
            const hoveredChart = _models.charts[hoveredChartIndex];

            if (hoveredChart && hoveredChartIndex !== -1) {
                const chartName = hoveredChart.name || '';
                const isLineChart = chartName.includes('_overview') || chartName.includes('_log');

                if (isLineChart) {
                    const activePosForHover = _state.isPlaying ? _state.activeAudioPosition : null;
                    _updateBarChart(hoveredX, hoveredChartIndex, activePosForHover, `Hover: ${chartName}`);
                }
            } else if (_state.verticalLinePosition !== null) {
                 const activePosForRestore = _state.isPlaying ? _state.activeAudioPosition : null;
                 const activeIndexForRestore = _state.isPlaying ? null : _state.activeChartIndex;
                _updateBarChart(_state.verticalLinePosition, activeIndexForRestore, activePosForRestore, "Click Line");
            }
            return true;
        } catch (error) { console.error("Error handling hover:", error); return false; }
    }

    // --- Module Exports ---
    return {
        // Core
        init: initializeApp,
        // State Access
        getState: function () { return JSON.parse(JSON.stringify(_state)); },
        getModelsInfo: function () { /* ... simplified ... */ return { /* basic info */ }; },
        // Tap Lines
        showTapLines: showTapLines,
        hideTapLines: hideTapLines,
        updateTapLinePosition: updateTapLinePosition,
        // Parameters
        handleParameterChange: handleParameterChange,
        // Frequency Bar (User Interaction Trigger)
        updateFrequencyBar: updateFrequencyBar,
        // Audio Control (JS -> Python via model changes)
        startAudioPlayback: startAudioPlayback, // Main Play
        pauseAudioPlayback: pauseAudioPlayback, // Main Pause
        togglePlayPause: togglePlayPause,       // Main Toggle
        handlePositionPlayClick: handlePositionPlayClick, // Position button clicks (triggers playRequestSource)
        // Audio Sync & State (Python -> JS)
        synchronizePlaybackPosition: synchronizePlaybackPosition, // Called by Python timer
        notifyPlaybackStopped: notifyPlaybackStopped, // Called by Python on EOF/error
        // Keyboard Nav
        enableKeyboardNavigation: enableKeyboardNavigation,
        disableKeyboardNavigation: disableKeyboardNavigation,
        // Namespaces / Detailed Access
        frequency: { handleSpectrogramHover: _handleSpectrogramHover },
        interactions: { onTap: onTapHandler, onHover: onHoverHandler, handleHover: onHoverHandler, handleTap: onTapHandler, sendSeekCommand: _sendSeekCommand },
        // Utilities
        findClosestIndex: findClosestIndex,
        findClosestDateIndex: findClosestDateIndex,
        // Debug
        selfCheck: function () { /* ... simplified ... */ return true; }
    };
})();

// --- Global Exposure for Bokeh CustomJS Callbacks ---
window.interactions = window.NoiseSurveyApp.interactions;
window.NoiseFrequency = window.NoiseSurveyApp.frequency;

// Function called by Python timer during playback
window.synchronizePlaybackPosition = function (ms) {
    if (typeof ms === 'number' && !isNaN(ms)) {
        if (window.NoiseSurveyApp?.synchronizePlaybackPosition) { return window.NoiseSurveyApp.synchronizePlaybackPosition(ms); }
        else { console.warn("NoiseSurveyApp.synchronizePlaybackPosition not available."); return false; }
    } else { console.warn(`Global synchronizePlaybackPosition called with invalid value: ${ms}`); return false; }
};

// Function called by Bokeh TapTool
window.handleTap = function (cb_obj) {
    if (window.NoiseSurveyApp?.interactions?.handleTap) { return window.NoiseSurveyApp.interactions.handleTap(cb_obj); }
    else { console.warn("NoiseSurveyApp.interactions.handleTap not available."); return false; }
};

// Function called by Bokeh HoverTool on main charts
window.handleHover = function (hoverLines, cb_data) {
    if (window.NoiseSurveyApp?.interactions?.handleHover) { return window.NoiseSurveyApp.interactions.handleHover(hoverLines, cb_data); }
    else { console.warn("NoiseSurveyApp.interactions.handleHover not available."); return false; }
};

// Function called by Bokeh HoverTool on spectrograms
window.handleSpectrogramHover = function (cb_data, hover_div, bar_source, bar_x_range, position_name, times_array, freqs_array, freq_labels_array, levels_matrix, levels_flat_array, fig_x_range) {
    if (window.NoiseSurveyApp?.frequency?.handleSpectrogramHover) { return window.NoiseSurveyApp.frequency.handleSpectrogramHover(cb_data, hover_div, bar_source, bar_x_range, position_name, times_array, freqs_array, freq_labels_array, levels_matrix, levels_flat_array, fig_x_range); }
    else { console.warn("NoiseSurveyApp.frequency.handleSpectrogramHover not available."); return false; }
};

// Function called by Parameter Select widget
window.handleParameterChange = function (param) {
    if (window.NoiseSurveyApp?.handleParameterChange) { return window.NoiseSurveyApp.handleParameterChange(param); }
    else { console.warn("NoiseSurveyApp.handleParameterChange not available."); return false; }
};

// Function Called by Position Play Button CustomJS
window.handlePositionPlayClick = function (positionName) {
    if (typeof positionName === 'string') {
        if (window.NoiseSurveyApp?.handlePositionPlayClick) { return window.NoiseSurveyApp.handlePositionPlayClick(positionName); }
        else { console.warn("NoiseSurveyApp.handlePositionPlayClick not available."); return false; }
    } else { console.warn(`Global handlePositionPlayClick called with invalid value: ${positionName}`); return false; }
};

// Global Function Called by Python on Playback Stop (EOF/Error)
window.notifyPlaybackStopped = function() {
     if (window.NoiseSurveyApp?.notifyPlaybackStopped) { return window.NoiseSurveyApp.notifyPlaybackStopped(); }
     else { console.warn("NoiseSurveyApp.notifyPlaybackStopped not available."); return false; }
};


// Deprecated Global Fallbacks
window.updateTapLinePositions = function (ms) { console.warn("Deprecated global function 'updateTapLinePositions' called."); };
window.sendSeekCommand = function (ms) { console.warn("Deprecated global function 'sendSeekCommand' called."); };


console.log("app.js loaded and NoiseSurveyApp object created (v3.3 - Refactored Position Play).");
