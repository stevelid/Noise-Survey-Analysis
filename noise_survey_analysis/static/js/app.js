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
        freqTableSource: null,   // CDS for frequency table {'value':[], 'frequency_labels':[]}
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
        lastHoverX: null,           // Last hovered X position
    };

    // Debugging access
    window.__debugNoiseSurveyModels = _models;
    window.__debugNoiseSurveyState = _state;

    // --- Private Utility Functions ---
    // [findClosestDateIndex, findClosestIndex, createLabelText, positionLabel, calculateStepSize - unchanged]
    function findClosestDateIndex(dates, x) {
        // Add checks for robustness
        if (dates === null || dates === undefined || typeof dates.length !== 'number' || dates.length === 0) {
            // console.warn("findClosestDateIndex received invalid or empty 'dates' array-like object");
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

            return true;
        } else {
            labelModel.visible = false; return true;
        }
    }

    function _updateTapLinePositions(x) {
        if (typeof x !== 'number' || isNaN(x)) {
            //if x is invalid, hide all lines and labels
            return _hideAllLinesAndLabels();
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
        _models.seekCommandSource.data = {
            'target_time': [x],
            'position': [_state.activeAudioPosition]
        };
        _models.seekCommandSource.change.emit();
    }

    // --- Frequency Bar Update ---
    // [_updateBarChart - unchanged]
    function _updateFrequencyTable(levels, labels) {
        const tableDiv = _models.freqTableDiv;
        if (!tableDiv) { console.error("Frequency table div not found"); return; }

        let tableHtml = `
            <style>
                .freq-html-table { border-collapse: collapse; width: 100%; font-size: 0.9em; table-layout: fixed; }
                .freq-html-table th, .freq-html-table td { border: 1px solid #ddd; padding: 6px; text-align: center; white-space: nowrap; }
                .freq-html-table th { background-color: #f2f2f2; font-weight: bold; }
            </style>
            <table class="freq-html-table"><tr>`;

        labels.forEach(label => { tableHtml += `<th title="${label}">${label}</th>`; });
        tableHtml += `</tr><tr>`;

        levels.forEach(level => {
            const levelNum = Number(level);
            const levelText = isNaN(levelNum) ? 'N/A' : levelNum.toFixed(1);
            tableHtml += `<td>${levelText}</td>`;
        });
        tableHtml += `</tr></table>`;

        tableDiv.text = tableHtml;
    }

    function _updateBarChart(x, activeChartIndex, activeAudioPos, title_source = '') {
        const barSource = _models.barSource;
        const barXRange = _models.barXRange;
        const barChart = _models.barChart;
        const spectralDataStore = _models.spectralParamCharts;
        const selectedParam = _state.selectedParameter;


        if (!barSource || !barXRange || !barChart || !spectralDataStore || Object.keys(spectralDataStore).length === 0) {
            return;
        }

        let position = "Unknown";
        let interactionSourceInfo = title_source || "Audio Playback";
        let spectralKey = null;

        if (activeAudioPos && spectralDataStore[activeAudioPos]) {
            position = activeAudioPos;
            spectralKey = spectralDataStore[position]?.spectral ? 'spectral' : 'spectral_log';
        } else if (activeChartIndex !== -1 && _models.charts?.[activeChartIndex]?.name) {
            const chartName = _models.charts[activeChartIndex].name;
            position = chartName.split('_')[0];
            const chartType = chartName.substring(position.length + 1);

            if (chartType === 'spectral' || chartType === 'spectral_log') {
                spectralKey = chartType;
            } else {
                spectralKey = spectralDataStore[position]?.spectral ? 'spectral' : 'spectral_log';
            }
        } else {
            position = Object.keys(spectralDataStore)[0];
            if (position) {
                spectralKey = spectralDataStore[position]?.spectral ? 'spectral' : 'spectral_log';
            }
        }

        if (position === "Unknown" || !spectralKey) {
            console.warn("Could not determine position or spectral key for bar chart.");
            return;
        }

        // --- CORRECTED DATA ACCESS ---
        const preparedData = spectralDataStore[position]?.[spectralKey]?.prepared_data?.[selectedParam];

        if (!preparedData) {
            barChart.title.text = `Frequency Slice: ${position} | ${selectedParam} (Data N/A)`;
            barSource.data = { 'levels': [], 'frequency_labels': [] };
            barXRange.factors = [];
            barSource.change.emit();
            return;
        }

        const times = preparedData.times_ms;
        const levels_matrix_flat = preparedData.levels_matrix;
        const freq_labels = preparedData.frequency_labels;
        const n_freqs = freq_labels?.length || 0;

        if (!times || !levels_matrix_flat || !freq_labels || n_freqs === 0) {
            console.warn(`[updateBarChart] Missing values: times=${times}, levels_matrix_flat=${levels_matrix_flat}, freq_labels=${freq_labels}, n_freqs=${n_freqs}`);
            return;
        }

        let closestTimeIdx = findClosestDateIndex(times, x);
        if (closestTimeIdx === -1) {
            console.warn(`[updateBarChart] No closest time index found for x=${x}`);
            return;
        }

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
            return;
        }

        const cleanedLevels = freqDataSlice.map(level => (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);

        barSource.data = { 'levels': cleanedLevels, 'frequency_labels': freq_labels };
        barXRange.factors = freq_labels;
        barChart.title.text = `Frequency Slice: ${position} (${spectralKey.replace('_', ' ')}) | ${selectedParam} | ${new Date(x).toLocaleString()}`;
        barSource.change.emit();

        _updateFrequencyTable(cleanedLevels, freq_labels);
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
                // Restore frequency bar to the last clicked position if mouse leaves charts
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
                if (button && button.id) {
                    const isActivePosition = isPlaying && posName === _state.activeAudioPosition;

                    if (isActivePosition) {
                        // This position is playing: Show Pause state
                        button.label = `Pause ${posName}`;
                        button.button_type = "warning"; // e.g., 'warning' or 'danger' for pause
                        button.disabled = false; // Enable clicking to pause
                    } else {
                        // This position is NOT playing: Show Play state
                        button.label = `Play ${posName}`;
                        button.button_type = "success";
                        // Disable if *any* audio is playing (can't start another)
                        button.disabled = isPlaying;
                    }
                } else if (button !== null && button !== undefined) { // Log only if it exists but isn't valid
                    // Avoid logging if the button genuinely wasn't created/passed for this position
                    console.warn(`Item '${posName}' in positionPlayButtons is not a valid Bokeh button model or is missing properties.`);
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
            _models.playbackStatusSource = models.playback_status_source || null;
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
            _models.freqTableDiv = models.freqTableDiv || null;

            console.log('Global models set:', _models);

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

            //set up playback_status_source monitor
            if (_models.playbackStatusSource) {
                _models.playbackStatusSource.on_change('data', () => {
                    const isPlaying = _models.playbackStatusSource.data.is_playing[0];
                    const activePosition = _models.playbackStatusSource.data.active_position[0];

                    console.log(`JS received state update: isPlaying=<span class="math-inline">\{isPlaying\}, activePosition\=</span>{activePosition}`);

                    // Update the JS state from the single source of truth (Python)
                    _state.isPlaying = isPlaying;
                    _state.activeAudioPosition = activePosition;

                    // Update all UI buttons based on this new, correct state
                    _updatePlayButtonsState(isPlaying);
                });
            }


            // Validate individual position buttons
            Object.keys(_models.positionPlayButtons).forEach(posName => {
                const button = _models.positionPlayButtons[posName];
                if (button && button.id) {
                    const isActivePosition = _state.isPlaying && posName === _state.activeAudioPosition;
                    if (isActivePosition) {
                        // This position is playing: Show Pause state
                        button.label = `Pause ${posName}`;
                        button.button_type = "warning"; // e.g., 'warning' or 'danger' for pause
                        button.disabled = false; // Enable clicking to pause
                    } else {
                        // This position is NOT playing: Show Play state
                        button.label = `Play ${posName}`;
                        button.button_type = "success";
                        // Disable if *any* audio is playing (can't start another)
                        button.disabled = _state.isPlaying;
                    }
                }
            });

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
                _hideAllLinesAndLabels(); // Hide lines initially
                _state.verticalLinePosition = initialTimeMs; // Sync internal state
                console.log('Playback source position initialized to time:', new Date(initialTimeMs).toISOString());
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
    function handleParameterChange(param) {
        if (!param) {
            console.warn('handleParameterChange called with null or undefined parameter.');
            return false;
        }

        // Store the selected parameter in the app's state
        _state.selectedParameter = param;

        // Update the hidden div model that Python can see
        if (_models.selectedParamHolder) {
            _models.selectedParamHolder.text = param;
        }

        try {
            const spectralDataStore = _models.spectralParamCharts || {};

            // Loop through each position (e.g., 'SW', 'N')
            for (const position in spectralDataStore) {
                const positionData = spectralDataStore[position];
                if (!positionData) continue;

                // Loop through the possible spectral types for that position
                for (const dataKey of ['spectral', 'spectral_log']) {
                    // Check if this position has this type of data (e.g., 'spectral')
                    if (!positionData[dataKey]) {
                        continue;
                    }

                    const chartName = `${position}_${dataKey}`;
                    const chart = _models.charts.find(c => c.name === chartName);
                    if (!chart) {
                        console.warn(`Chart model not found for name: ${chartName}`);
                        continue;
                    }

                    const imageRenderer = chart.renderers.find(r => r.glyph?.type === 'Image');
                    if (!imageRenderer) {
                        console.warn(`Image renderer not found for chart: ${chartName}`);
                        continue;
                    }
                    const source = imageRenderer.data_source;

                    // Correctly look for the prepared data nested under the dataKey
                    const preparedData = positionData[dataKey]?.prepared_data?.[param];

                    if (preparedData) {
                        // --- Data is available for the new parameter, update the chart ---
                        imageRenderer.glyph.x = preparedData.x;
                        imageRenderer.glyph.y = preparedData.y;
                        imageRenderer.glyph.dw = preparedData.dw;
                        imageRenderer.glyph.dh = preparedData.dh;
                        source.data = { 'image': [preparedData.levels_matrix_transposed] };

                        // Correctly update the chart title while preserving its suffix
                        const titleBase = chart.title.text.split('(')[0].trim();
                        chart.title.text = `${titleBase} (${param})`;

                        const colorMapper = imageRenderer.glyph.color_mapper;
                        if (colorMapper) {
                            colorMapper.low = preparedData.min_val;
                            colorMapper.high = preparedData.max_val;
                        }
                        source.change.emit();

                    } else {
                        // --- Data is NOT available, clear the image and update the title ---
                        source.data.image = [];
                        const titleBase = chart.title.text.split('(')[0].trim();
                        chart.title.text = `${titleBase} (${param} N/A)`;
                        source.change.emit();
                    }
                }
            }

            // If a click line is active, update the frequency bar with the new parameter
            if (_state.verticalLinePosition !== null) {
                _updateBarChart(_state.verticalLinePosition, _state.activeChartIndex, _state.activeAudioPosition, "Parameter Change");
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
        // ... (rest of the code remains the same)
        try {
            if (typeof x !== 'number' || isNaN(x)) { return false; }
            // Call internal function - activeAudioPos is null for user interactions unless already playing
            const activePos = _state.isPlaying ? _state.activeAudioPosition : null;
            _updateBarChart(x, activeChartIndex, activePos, title_source);
            return true;
        } catch (error) { console.error("Error updating frequency bar:", error); return false; }
    }

    // --- Tap Line Visibility ---
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
            if (!_models.playRequestSource) {
                console.error("Cannot pause: playRequestSource model is missing!");
                return false;
            }

            console.log("JS: Sending pause request to Python.");

            // Send a specific signal for pausing via the playRequestSource.
            // Python will listen for this exact 'pause_request' string.
            _models.playRequestSource.data = { 'position': ['pause_request'], 'time': [_state.verticalLinePosition] };
            _models.playRequestSource.change.emit(); // Signal Python

            return true;
        } catch (error) {
            console.error("Error sending pause request from JS:", error);
            return false;
        }
    }

    function handlePositionPlayClick(positionName) {
        if (!_models.playRequestSource) {
            console.error("Cannot handle position play click: playRequestSource model is missing!");
            return false;
        }

        let currentTime = _state.verticalLinePosition;
        if (currentTime === null || currentTime === undefined) {
            if (_models.charts?.[0]?.x_range?.start) {
                currentTime = _models.charts[0].x_range.start;
                _state.verticalLinePosition = currentTime; // Update the state as well
                console.log(`verticalLinePosition was null, defaulting to chart start: ${currentTime}`);
            } else {
                console.error("Cannot determine a valid time to play from.");
                return false;
            }
        }

        console.log(`JS: Sending toggle play request for position: ${positionName}, time: ${currentTime}`);

        // Update the playRequestSource model
        _models.playRequestSource.data = { 'position': [positionName], 'time': [currentTime] };
        _models.playRequestSource.change.emit(); // Signal Python to handle the request

        return true;
    }

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
    function onTapHandler(cb_obj, chartModels, clickLineModels, labelModels, sourcesDict) {
        try {
            // Use the models passed directly as arguments instead of relying on the global _models state
            const charts = chartModels || _models.charts;
            const clickLines = clickLineModels || _models.clickLines;
            const labels = labelModels || _models.labels;
            const sources = sourcesDict || _models.sources;

            _state.activeChartIndex = _getActiveChartIndex(cb_obj);
            if (_state.activeChartIndex === -1) {
                console.warn("Could not determine active chart on tap.");
            }

            const raw_x = cb_obj.x;
            if (raw_x === undefined || raw_x === null || isNaN(raw_x)) {
                console.warn("Tap handler received invalid x coordinate:", raw_x);
                return false;
            }

            const activeChart = charts[_state.activeChartIndex];
            const source = sources[activeChart.name];
            let snapped_x = raw_x;

            if (source && source.data.Datetime && source.data.Datetime.length > 0) {
                const closest_idx = findClosestDateIndex(source.data.Datetime, raw_x);
                if (closest_idx !== -1) {
                    snapped_x = source.data.Datetime[closest_idx];
                }
            }

            // Update the visual representation of all tap lines
            _state.verticalLinePosition = snapped_x;
            for (let i = 0; i < charts.length; i++) {
                if (charts[i] && clickLines?.[i] && labels?.[i]) {
                    _updateChartLine(charts[i], clickLines[i], labels[i], snapped_x, i);
                }
            }

            // Update step size based on the actively tapped chart's data
            _state.stepSize = calculateStepSize(source);

            // Update the frequency bar chart based on the new position
            _updateBarChart(snapped_x, _state.activeChartIndex, _state.activeAudioPosition, "Click");

            // Send a seek command to Python to update the audio handler's position
            _sendSeekCommand(snapped_x);

            return true;
        } catch (error) { console.error("Error handling tap:", error); return false; }
    }

    function onHoverHandler(hoverLines, hoverLabels, cb_data, chart_index) { // Now accepts chart_index and labels

        try {
            // Check if geometry data exists from the event
            const geometry = cb_data.geometry;
            if (!geometry || !Number.isFinite(geometry.x)) {
                // Hide all hover labels when mouse is not over a valid chart area
                _updateTapLinePositions(_state.verticalLinePosition);

                // If geometry is invalid, reset lastHoverX so next valid hover isn't skipped
                _state.lastHoverX = null;
                // Restore frequency bar to the last clicked position if mouse leaves charts
                if (_state.verticalLinePosition !== null) {
                    const activePosForRestore = _state.isPlaying ? _state.activeAudioPosition : null;
                    const activeIndexForRestore = _state.isPlaying ? null : _state.activeChartIndex;
                    _updateBarChart(_state.verticalLinePosition, activeIndexForRestore, activePosForRestore, "Click Line");
                }
                return false;
            }

            //debounce hover events
            if (_state.lastHoverX === geometry.x) {
                return true;
            }

            const hoveredX = geometry.x;
            _state.lastHoverX = hoveredX;

            // Update all hover lines (the grey vertical guides)
            if (hoverLines && Array.isArray(hoverLines)) {
                hoverLines.forEach(line => { if (line) line.location = hoveredX; });
            }

            // Directly use the chart_index passed from the specific callback
            const hoveredChartIndex = chart_index;
            const hoveredChart = _models.charts[hoveredChartIndex];

            if (hoveredChart && hoveredChartIndex !== -1) {
                const chartName = hoveredChart.name || '';
                // Only update the bar chart for time-series charts (overview/log)
                const isLineChart = chartName.includes('_overview') || chartName.includes('_log');

                if (isLineChart) {
                    const activePosForHover = _state.isPlaying ? _state.activeAudioPosition : null;

                    // --- Logic to update the hover label ---
                    const labelModel = hoverLabels[hoveredChartIndex];
                    const source = _models.sources[chartName];

                    if (labelModel && source && source.data.Datetime) {
                        const closestIdx = findClosestDateIndex(source.data.Datetime, hoveredX);
                        if (closestIdx !== -1) {
                            const snappedX = source.data.Datetime[closestIdx];
                            const labelText = createLabelText(source, closestIdx);

                            positionLabel(snappedX, hoveredChart, labelModel);
                            labelModel.text = labelText;
                            labelModel.visible = true;
                        } else {
                            labelModel.visible = false;
                        }
                    }
                    // --- End of label logic ---

                    // Pass the correct chart index to the bar chart updater
                    _updateBarChart(hoveredX, hoveredChartIndex, activePosForHover, `Hover: ${chartName}`);
                }
            }
            return true;
        } catch (error) {
            console.error("Error handling hover:", error);
            return false;
        }
    }

    function onZoomHandler(cb_obj, master_range) {
        //console.log("Zoom event triggered:", cb_obj, master_range);
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
        interactions: { onTap: onTapHandler, onHover: onHoverHandler, handleHover: onHoverHandler, handleTap: onTapHandler, sendSeekCommand: _sendSeekCommand, onZoom: onZoomHandler },
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
window.handleTap = function (cb_obj, chartModels, clickLineModels, labelModels, sourcesDict) {
    if (window.NoiseSurveyApp?.interactions?.onTap) {
        // Pass all arguments through
        return window.NoiseSurveyApp.interactions.onTap(cb_obj, chartModels, clickLineModels, labelModels, sourcesDict);
    } else {
        console.warn("NoiseSurveyApp.interactions.onTap not available.");
        return false;
    }
};

// Function called by Bokeh HoverTool on main charts
window.handleHover = function (hoverLines, cb_data, chart_index) {
    console.log("[window.handleHover] called with chart_index:", chart_index);
    if (window.NoiseSurveyApp?.interactions?.handleHover) { return window.NoiseSurveyApp.interactions.handleHover(hoverLines, cb_data, chart_index); }
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
window.notifyPlaybackStopped = function () {
    if (window.NoiseSurveyApp?.notifyPlaybackStopped) { return window.NoiseSurveyApp.notifyPlaybackStopped(); }
    else { console.warn("NoiseSurveyApp.notifyPlaybackStopped not available."); return false; }
};


// Deprecated Global Fallbacks
window.updateTapLinePositions = function (ms) { console.warn("Deprecated global function 'updateTapLinePositions' called."); };
window.sendSeekCommand = function (ms) { console.warn("Deprecated global function 'sendSeekCommand' called."); };


console.log("app.js loaded and NoiseSurveyApp object created (v3.3 - Refactored Position Play).");