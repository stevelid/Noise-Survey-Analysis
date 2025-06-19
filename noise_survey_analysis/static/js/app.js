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

/* DEBUG START */
console.log("[DEBUG] app.js: Script loading started.");
/* DEBUG END */
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
        barSource: null,          // CDS for frequency bar chart {'levels':[], 'frequency_labels':[]}
        barXRange: null,          // FactorRange for frequency bar x-axis
        barChart: null,           // Frequency bar chart figure model
        freqTableSource: null,    // CDS for frequency table {'value':[], 'frequency_labels':[]}
        paramSelect: null,
        selectedParamHolder: null,
        allSources: {},           // Potentially includes spectral image sources if needed
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
        activeSpectralData: null, // Single point of truth for current spectral data
    };

    // Debugging access
    window.__debugNoiseSurveyModels = _models;
    window.__debugNoiseSurveyState = _state;

    // --- Centralized Spectral Data State ---
    function _updateActiveSpectralData(position, spec_key, param) {
        /* DEBUG START */
        console.log(`[DEBUG] _updateActiveSpectralData: Updating for pos='${position}', key='${spec_key}', param='${param}'`);
        /* DEBUG END */
        const dataStore = _models.spectralParamCharts;
        if (dataStore?.[position]?.[spec_key]?.prepared_data?.[param]) {
            const dataObj = dataStore[position][spec_key].prepared_data[param];
            // Store a copy along with helpful context
            _state.activeSpectralData = { ...dataObj, position, spec_key, param };
            /* DEBUG START */
            console.log('[DEBUG] _updateActiveSpectralData: Success. Active data set.');
            /* DEBUG END */
        } else {
            _state.activeSpectralData = null;
            console.warn('[DEBUG] _updateActiveSpectralData: Data not found. Active data cleared.');
        }
    }

    // --- Private Utility Functions ---
    // [findClosestDateIndex, findClosestIndex, createLabelText, positionLabel, calculateStepSize - unchanged]
    function findClosestDateIndex(dates, x) {
        /* DEBUG START */
        console.log(`[DEBUG] findClosestDateIndex: Searching for closest index to x=${x} in dates array of length ${dates?.length}.`);
        /* DEBUG END */
        // Add checks for robustness
        if (dates === null || dates === undefined || typeof dates.length !== 'number' || dates.length === 0) {
            /* DEBUG START */
            console.warn("[DEBUG] findClosestDateIndex: Received invalid or empty 'dates' array. Returning -1.");
            /* DEBUG END */
            return -1;
        }
        if (typeof x !== 'number' || isNaN(x)) {
            /* DEBUG START */
            console.warn("[DEBUG] findClosestDateIndex: Received invalid 'x' value. Returning -1.");
            /* DEBUG END */
            return -1;
        }

        let low = 0;
        let high = dates.length - 1;
        let closest_idx = 0;
        let min_diff = Infinity;

        // Handle edge cases: x before start or after end
        /* DEBUG START */
        if (x <= dates[0]) { console.log("[DEBUG] findClosestDateIndex: x is before the first date. Returning 0."); return 0; }
        if (x >= dates[high]) { console.log("[DEBUG] findClosestDateIndex: x is after the last date. Returning high."); return high; }
        /* DEBUG END */

        // Linear scan approach (robust for potentially unsorted/gappy data):
        min_diff = Math.abs(dates[0] - x); // Initialize difference
        for (let j = 1; j < dates.length; j++) {
            let diff = Math.abs(dates[j] - x);
            if (diff < min_diff) {
                /* DEBUG START */
                console.log(`[DEBUG] findClosestDateIndex: Found closer index at j=${j}, diff=${diff}. Previous min_diff=${min_diff}.`);
                /* DEBUG END */
                min_diff = diff;
                closest_idx = j;
            }
        }
        /* DEBUG START */
        console.log(`[DEBUG] findClosestDateIndex: Closest index found: ${closest_idx}.`);
        /* DEBUG END */
        return closest_idx;
    }

    function findClosestIndex(array, target) {
        /* DEBUG START */
        console.log(`[DEBUG] findClosestIndex: Searching for closest index to target=${target} in array of length ${array?.length}.`);
        /* DEBUG END */
        if (array === null || array === undefined || typeof array.length !== 'number' || array.length === 0) {
            /* DEBUG START */
            console.warn("[DEBUG] findClosestIndex: Received invalid or empty 'array'. Returning -1.");
            /* DEBUG END */
            return -1;
        }
        let minDiff = Infinity;
        let closestIndex = -1;
        for (let i = 0; i < array.length; i++) {
            let diff = Math.abs(array[i] - target);
            if (diff < minDiff) {
                /* DEBUG START */
                console.log(`[DEBUG] findClosestIndex: Found closer index at i=${i}, diff=${diff}. Previous minDiff=${minDiff}.`);
                /* DEBUG END */
                minDiff = diff;
                closestIndex = i;
            }
        }
        /* DEBUG START */
        console.log(`[DEBUG] findClosestIndex: Closest index found: ${closestIndex}.`);
        /* DEBUG END */
        return closestIndex;
    }

    function createLabelText(source, closest_idx) {
        /* DEBUG START */
        console.log(`[DEBUG] createLabelText: Generating label for source with data at index ${closest_idx}.`);
        /* DEBUG END */
        if (!source || !source.data || !source.data.Datetime || closest_idx < 0 || closest_idx >= source.data.Datetime.length) {
            /* DEBUG START */
            console.warn("[DEBUG] createLabelText: Invalid data for label. Returning error string.");
            /* DEBUG END */
            return "Error: Invalid data for label";
        }
        let date = new Date(source.data.Datetime[closest_idx]);
        let formatted_date = date.toLocaleString(); // Use locale-specific format
        let label_text = 'Time: ' + formatted_date + '\n';
        for (let key in source.data) {
            // Only include non-internal keys that have data at this index
            if (key !== 'Datetime' && key !== 'index' && source.data.hasOwnProperty(key) && source.data[key]?.length > closest_idx) {
                /* DEBUG START */
                console.log(`[DEBUG] createLabelText: Processing key '${key}' for label.`);
                /* DEBUG END */
                let value = source.data[key][closest_idx];
                if (value !== undefined && value !== null && !isNaN(value)) {
                    let formatted_value = parseFloat(value).toFixed(1);
                    // Basic check for common dB parameters - could be made more robust
                    let unit = (key.startsWith('L') || key.includes('eq') || key.includes('max') || key.includes('min')) ? ' dB' : '';
                    label_text += key + ': ' + formatted_value + unit + '\n';
                }
            }
        }
        /* DEBUG START */
        console.log(`[DEBUG] createLabelText: Generated label text: \n${label_text}`);
        /* DEBUG END */
        return label_text;
    }

    function positionLabel(x, chart, labelModel) {
        /* DEBUG START */
        console.log(`[DEBUG] positionLabel: Positioning label for x=${x} on chart ${chart?.name}.`);
        /* DEBUG END */
        if (!chart || !labelModel || !chart.x_range || !chart.y_range) return;
        const xStart = chart.x_range.start ?? 0; // Use nullish coalescing for defaults
        const xEnd = chart.x_range.end ?? 0;
        const yStart = chart.y_range.start ?? 0;
        const yEnd = chart.y_range.end ?? 0;

        if (xStart === xEnd || yStart === yEnd) return; // Avoid division by zero or nonsensical ranges
        /* DEBUG START */
        console.log(`[DEBUG] positionLabel: Chart ranges - X: [${xStart}, ${xEnd}], Y: [${yStart}, ${yEnd}].`);
        /* DEBUG END */

        const middleX = xStart + (xEnd - xStart) / 2;
        const topY = yEnd - (yEnd - yStart) / 5; // Position near top of chart

        // Position label to avoid overlapping the vertical line (x)
        if (x <= middleX) {
            labelModel.x = x + (xEnd - xStart) * 0.02; // Offset slightly right
            labelModel.text_align = 'left';
            /* DEBUG START */
            console.log(`[DEBUG] positionLabel: x (${x}) <= middleX (${middleX}). Positioning label to the right.`);
            /* DEBUG END */
        } else {
            labelModel.x = x - (xEnd - xStart) * 0.02; // Offset slightly left
            labelModel.text_align = 'right';
            /* DEBUG START */
            console.log(`[DEBUG] positionLabel: x (${x}) > middleX (${middleX}). Positioning label to the left.`);
            /* DEBUG END */
        }
        labelModel.y = topY;
        labelModel.text_baseline = 'middle';
        /* DEBUG START */
        console.log(`[DEBUG] positionLabel: Label position set to x=${labelModel.x}, y=${labelModel.y}, align=${labelModel.text_align}.`);
        /* DEBUG END */
    }

    function calculateStepSize(source) {
        const DEFAULT_STEP_SIZE = 300000; // 5 minutes
        /* DEBUG START */
        console.log("[DEBUG] calculateStepSize: Calculating step size for keyboard navigation.");
        /* DEBUG END */

        if (!source?.data?.Datetime || source.data.Datetime.length < 2) {
            console.warn("calculateStepSize: Invalid source data for step size calculation.");
            console.log("source.data:", source.data);
            /* DEBUG START */
            console.log(`[DEBUG] calculateStepSize: Returning default step size ${DEFAULT_STEP_SIZE}ms.`);
            /* DEBUG END */
            return DEFAULT_STEP_SIZE;
        }
        const times = source.data.Datetime;

        const interval = times[5] - times[4];
        /* DEBUG START */
        console.log(`[DEBUG] calculateStepSize: Calculated interval from data: ${interval}ms.`);
        /* DEBUG END */

        // Step size: interval, clamped between 1s and 1hr
        let stepSize = Math.max(1000, Math.min(3600000, Math.round(interval)));
        /* DEBUG START */
        console.log(`[DEBUG] calculateStepSize: Clamped step size: ${stepSize}ms.`);
        /* DEBUG END */
        return stepSize;
    }

    // --- Private Interaction Functions ---
    // [_updateChartLine, _updateTapLinePositions, _getActiveChartIndex, _hideAllLinesAndLabels, _sendSeekCommand - unchanged]
    function _updateChartLine(chart, clickLineModel, labelModel, x, chartIndex) {
        /* DEBUG START */
        console.log(`[DEBUG] _updateChartLine: Updating chart line for chart ${chart?.name} (index: ${chartIndex}) at x=${x}.`);
        /* DEBUG END */
        if (!chart || !clickLineModel || !labelModel) { console.warn("[DEBUG] _updateChartLine: Missing chart, clickLineModel, or labelModel. Skipping update."); return false; }
        clickLineModel.location = x;
        clickLineModel.visible = true;
        const sourceKey = chart.name;
        let source = null;
        // Labels only apply to overview/log charts
        if (!sourceKey || sourceKey === 'range_selector' || sourceKey === 'shared_range_selector' || sourceKey === 'frequency_bar' || sourceKey.includes('_spectral')) {
            /* DEBUG START */
            console.log(`[DEBUG] _updateChartLine: Chart '${sourceKey}' is not an overview/log chart. Hiding label.`);
            /* DEBUG END */
            labelModel.visible = false;
            return true;
        }
        if (_models.sources && _models.sources.hasOwnProperty(sourceKey)) { source = _models.sources[sourceKey]; }
        if (!source?.data?.Datetime) { console.warn(`[DEBUG] _updateChartLine: No Datetime data for source '${sourceKey}'. Hiding label.`); labelModel.visible = false; return true; } // Simplified check

        let closest_idx = findClosestDateIndex(source.data.Datetime, x);
        if (closest_idx !== -1) {
            let label_text = createLabelText(source, closest_idx);
            positionLabel(x, chart, labelModel);
            labelModel.text = label_text;
            labelModel.visible = true;
            /* DEBUG START */
            console.log(`[DEBUG] _updateChartLine: Label for chart '${sourceKey}' at index ${closest_idx} updated and visible.`);
            /* DEBUG END */
            return true;
        } else {
            /* DEBUG START */
            console.log(`[DEBUG] _updateChartLine: No closest index found for source '${sourceKey}'. Hiding label.`);
            /* DEBUG END */
            labelModel.visible = false;
            return true;
        }
    }

    function _updateTapLinePositions(x) {
        /* DEBUG START */
        console.log(`[DEBUG] _updateTapLinePositions: Updating tap line positions to x=${x}.`);
        /* DEBUG END */
        if (typeof x !== 'number' || isNaN(x)) {
            //if x is invalid, hide all lines and labels
            /* DEBUG START */
            console.warn("[DEBUG] _updateTapLinePositions: Invalid 'x' value received. Hiding all lines and labels.");
            /* DEBUG END */
            return _hideAllLinesAndLabels();
        }

        _state.verticalLinePosition = x;
        if (!_models?.charts || !Array.isArray(_models.charts) || _models.charts.length === 0) { console.warn("[DEBUG] _updateTapLinePositions: No charts available to update. Returning false."); return false; }
        for (let i = 0; i < _models.charts.length; i++) {
            if (_models.charts[i]?.name === 'frequency_bar') { /* DEBUG START */ console.log(`[DEBUG] _updateTapLinePositions: Skipping frequency_bar chart (index ${i}).`); /* DEBUG END */ continue; } // Skip freq bar chart itself
            // Check models exist for this index before calling update
            if (_models.charts[i] && _models.clickLines?.[i] && _models.labels?.[i]) {
                /* DEBUG START */
                console.log(`[DEBUG] _updateTapLinePositions: Calling _updateChartLine for chart index ${i}.`);
                /* DEBUG END */
                _updateChartLine(_models.charts[i], _models.clickLines[i], _models.labels[i], x, i);
            } else {
                /* DEBUG START */
                console.warn(`[DEBUG] _updateTapLinePositions: Missing models for chart index ${i}. Skipping.`);
                /* DEBUG END */
            }
        }
        /* DEBUG START */
        console.log(`[DEBUG] _updateTapLinePositions: Successfully updated all visible tap lines to x=${x}.`);
        /* DEBUG END */
        return true;
    }

    function _getActiveChartIndex(cb_obj) {
        /* DEBUG START */
        console.log(`[DEBUG] _getActiveChartIndex: Determining active chart from cb_obj.origin.id=${cb_obj?.origin?.id}.`);
        /* DEBUG END */
        let activeChartIndex = -1;
        if (!cb_obj?.origin?.id || !_models.charts) { console.warn("[DEBUG] _getActiveChartIndex: cb_obj.origin.id or _models.charts missing. Returning -1."); return -1; } // Check id exists
        activeChartIndex = _models.charts.findIndex(chart => chart?.id === cb_obj.origin.id);
        /* DEBUG START */
        console.log(`[DEBUG] _getActiveChartIndex: Active chart index found: ${activeChartIndex}.`);
        /* DEBUG END */
        return activeChartIndex; // Will be -1 if not found
    }

    function _hideAllLinesAndLabels() {
        /* DEBUG START */
        console.log("[DEBUG] _hideAllLinesAndLabels: Hiding all click lines and labels.");
        /* DEBUG END */
        if (!_models.clickLines || !_models.labels) { console.warn("[DEBUG] _hideAllLinesAndLabels: clickLines or labels models are missing. Cannot hide."); return false; }
        try {
            _models.clickLines.forEach(line => { if (line) line.visible = false; });
            _models.labels.forEach(label => { if (label) label.visible = false; });
            /* DEBUG START */
            console.log("[DEBUG] _hideAllLinesAndLabels: Successfully hid all lines and labels.");
            /* DEBUG END */
            return true;
        } catch (error) { console.error("[DEBUG] _hideAllLinesAndLabels: Error hiding lines/labels:", error); return false; }
    }

    function _sendSeekCommand(x) {
        /* DEBUG START */
        console.log(`[DEBUG] _sendSeekCommand: Preparing to send seek command to ${x}ms for position '${_state.activeAudioPosition}'.`);
        /* DEBUG END */
        if (!_models.seekCommandSource) { console.error("[DEBUG] _sendSeekCommand: seekCommandSource not available! Cannot send seek command."); return; }
        if (typeof x !== 'number' || isNaN(x)) { console.warn(`[DEBUG] _sendSeekCommand: Invalid seek time: ${x}. Skipping command.`); return; }
        console.debug(`[DEBUG] _sendSeekCommand: Sending seek command to ${x}ms.`);
        _models.seekCommandSource.data = {
            'target_time': [x],
            'position': [_state.activeAudioPosition]
        };
        _models.seekCommandSource.change.emit();
        /* DEBUG START */
        console.log("[DEBUG] _sendSeekCommand: Seek command emitted via seekCommandSource.");
        /* DEBUG END */
    }

    // --- Frequency Bar Update ---
    // [_updateBarChart - unchanged]
    function _updateFrequencyTable(levels, labels) {
        /* DEBUG START */
        console.log(`[DEBUG] _updateFrequencyTable: Updating frequency table with ${levels?.length} levels and ${labels?.length} labels.`);
        /* DEBUG END */
        const tableDiv = _models.freqTableDiv;
        if (!tableDiv) { console.error("[DEBUG] _updateFrequencyTable: Frequency table div model not found. Skipping update."); return; }

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
        /* DEBUG START */
        console.log("[DEBUG] _updateFrequencyTable: Frequency table HTML updated.");
        /* DEBUG END */
    }

    function _updateBarChart(x, activeChartIndex, activeAudioPos, title_source = '') {
        /* DEBUG START */
        console.log(`[DEBUG] _updateBarChart: Called for x=${x}, activeChartIndex=${activeChartIndex}, activeAudioPos='${activeAudioPos}', title_source='${title_source}'.`);
        /* DEBUG END */
        const barSource = _models.barSource;
        const barXRange = _models.barXRange;
        const barChart = _models.barChart;
        const spectralDataStore = _models.spectralParamCharts;
        const selectedParam = _state.selectedParameter;

        if (!barSource || !barXRange || !barChart || !spectralDataStore || Object.keys(spectralDataStore).length === 0) {
            /* DEBUG START */
            console.warn("[DEBUG] _updateBarChart: Essential models for bar chart missing or spectral data store empty. Aborting update.");
            /* DEBUG END */
            return;
        }

        let position = "Unknown";
        //let interactionSourceInfo = title_source || "Audio Playback"; // interactionSourceInfo is unused. Kept for context.
        let spectralKey = null;

        if (activeAudioPos && spectralDataStore[activeAudioPos]) {
            position = activeAudioPos;
            spectralKey = spectralDataStore[position]?.spectral ? 'spectral' : 'spectral_log';
            /* DEBUG START */
            console.log(`[DEBUG] _updateBarChart: Determined position from activeAudioPos: '${position}', spectralKey: '${spectralKey}'.`);
            /* DEBUG END */
        } else if (activeChartIndex !== -1 && _models.charts?.[activeChartIndex]?.name) {
            const chartName = _models.charts[activeChartIndex].name;
            position = chartName.replace('_combined_spectrogram', '')
                           .replace('_combined_time_series', '')
                           .replace('_spectral_log', '')
                           .replace('_spectral', '')
                           .replace('_overview', '')
                           .replace('_log', '');
        } else {
            // Fallback if no other context is available
            position = Object.keys(spectralDataStore)[0];
        }

        // --- Determine Active Spectral Type (Overview vs. Log) ---
        const specChart = _models.charts.find(c => c.name === `${position}_combined_spectrogram`);
        if (specChart && specChart.title.text.includes('Log')) {
            spectralKey = 'spectral_log';
        } else {
            spectralKey = 'spectral';
        }

        console.log(`[DEBUG] _updateBarChart: Determined position='${position}', spectralKey='${spectralKey}', selectedParam='${selectedParam}'`);

        if (position === "Unknown" || !spectralKey) {
            /* DEBUG START */
            console.warn("[DEBUG] _updateBarChart: Could not determine position or spectral key for bar chart. Aborting.");
            /* DEBUG END */
            return;
        }

        // --- CORRECTED DATA ACCESS ---
        const preparedData = spectralDataStore[position]?.[spectralKey]?.prepared_data?.[selectedParam];

        if (!preparedData) {
            /* DEBUG START */
            console.warn(`[DEBUG] _updateBarChart: No prepared data found for position '${position}', spectralKey '${spectralKey}', parameter '${selectedParam}'. Resetting bar chart.`);
            /* DEBUG END */
            barChart.title.text = `Frequency Slice: ${position} | ${selectedParam} (Data N/A)`;
            barSource.data = { 'levels': [], 'frequency_labels': [] };
            barXRange.factors = [];
            barSource.change.emit();
            return;
        }
        /* DEBUG START */
        console.log(`[DEBUG] _updateBarChart: Found prepared data for position '${position}', spectralKey '${spectralKey}', parameter '${selectedParam}'.`);
        /* DEBUG END */

        const times = preparedData.times_ms;
        const levels_matrix_flat = preparedData.levels_matrix;
        const freq_labels = preparedData.frequency_labels;
        const n_freqs = freq_labels?.length || 0;

        if (!times || !levels_matrix_flat || !freq_labels || n_freqs === 0) {
            /* DEBUG START */
            console.warn(`[DEBUG] _updateBarChart: Missing required data components (times, levels_matrix_flat, freq_labels, or n_freqs). Aborting.`);
            /* DEBUG END */
            console.warn(`[DEBUG] _updateBarChart: Missing values: times=${times}, levels_matrix_flat=${levels_matrix_flat}, freq_labels=${freq_labels}, n_freqs=${n_freqs}`);
            return;
        }

        let closestTimeIdx = findClosestDateIndex(times, x);
        if (closestTimeIdx === -1) {
            /* DEBUG START */
            console.warn(`[DEBUG] _updateBarChart: No closest time index found for x=${x}. Aborting.`);
            /* DEBUG END */
            console.warn(`[DEBUG] _updateBarChart: No closest time index found for x=${x}`);
            return;
        }
        /* DEBUG START */
        console.log(`[DEBUG] _updateBarChart: Closest time index for x=${x} is ${closestTimeIdx}.`);
        /* DEBUG END */

        let freqDataSlice = null;
        if (levels_matrix_flat) {
            const start_idx = closestTimeIdx * n_freqs;
            const end_idx = start_idx + n_freqs;
            if (start_idx >= 0 && end_idx <= levels_matrix_flat.length) {
                freqDataSlice = levels_matrix_flat.slice(start_idx, end_idx);
                /* DEBUG START */
                console.log(`[DEBUG] _updateBarChart: Sliced frequency data from levels_matrix_flat. start=${start_idx}, end=${end_idx}.`);
                /* DEBUG END */
            } else {
                /* DEBUG START */
                console.warn(`[DEBUG] _updateBarChart: Flat matrix slice indices out of bounds: ${start_idx}-${end_idx}. Levels_matrix_flat length: ${levels_matrix_flat.length}.`);
                /* DEBUG END */
                console.warn(`[DEBUG] _updateBarChart: Flat matrix slice indices out of bounds: ${start_idx}-${end_idx}`);
            }
            // } else if (levels_matrix && closestTimeIdx < levels_matrix.length) { // Fallback for non-flat? (Shouldn't be needed with current structure)
            //     freqDataSlice = levels_matrix[closestTimeIdx];
        }


        if (!freqDataSlice || freqDataSlice.length !== n_freqs) {
            /* DEBUG START */
            console.warn(`[DEBUG] _updateBarChart: Frequency data slice at index ${closestTimeIdx} is invalid or has wrong length (${freqDataSlice?.length} vs ${n_freqs}). Aborting.`);
            /* DEBUG END */
            console.warn(`[DEBUG] _updateBarChart: Frequency data slice at index ${closestTimeIdx} is invalid or has wrong length (${freqDataSlice?.length} vs ${n_freqs}).`);
            return;
        }

        const cleanedLevels = freqDataSlice.map(level => (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);
        /* DEBUG START */
        console.log("[DEBUG] _updateBarChart: Cleaned levels for bar chart. Updating barSource data and x-range factors.");
        /* DEBUG END */

        barSource.data = { 'levels': cleanedLevels, 'frequency_labels': freq_labels };
        barXRange.factors = freq_labels;
        barChart.title.text = `Frequency Slice: ${position} (${spectralKey.replace('_', ' ')}) | ${selectedParam} | ${new Date(x).toLocaleString()}`;
        barSource.change.emit();

        _updateFrequencyTable(cleanedLevels, freq_labels);
        /* DEBUG START */
        console.log("[DEBUG] _updateBarChart: Bar chart and frequency table updated successfully.");
        /* DEBUG END */
    }

    function _handleSpectrogramHover(cb_data, hover_div, bar_source_arg, bar_x_range_arg, position_name, fig_x_range) {
        try {
            // --- DYNAMIC DATA LOOKUP ---
            const chart = _models.charts.find(c => c.name === `${position_name}_combined_spectrogram`);
            if (!chart) { return false; }
    
            const active_spec_key = chart.title.text.includes('Log') ? 'spectral_log' : 'spectral';
            const spectral_data_obj = _models.spectralParamCharts[position_name]?.[active_spec_key];
            const preparedData = spectral_data_obj?.prepared_data?.[_state.selectedParameter];
    
            if (!preparedData) {
                hover_div.text = "Hover over spectrogram to view details";
                hover_div.change.emit();
                return false;
            }
    
            const { times_ms: times, frequencies: freqs, frequency_labels: freq_labels_str, levels_matrix } = preparedData;
            const div = hover_div;
            const bar_source_js = bar_source_arg || _models.barSource;
            const bar_x_range_js = bar_x_range_arg || _models.barXRange;
            const barChart = _models.barChart;
    
            if (!div || !bar_source_js || !bar_x_range_js || !fig_x_range || !barChart) { return false; }
    
            const { x: gx, y: gy } = cb_data.geometry;
            const n_times = times.length;
            const n_freqs = freqs.length;
            const is_inside = !(gx < fig_x_range.start || gx > fig_x_range.end || gy < -0.5 || gy > n_freqs - 0.5 || n_times === 0 || n_freqs === 0);
    
            if (is_inside) {
                const time_idx = findClosestDateIndex(times, gx);
                if (time_idx === -1) return false;
                
                const freq_idx = Math.max(0, Math.min(n_freqs - 1, Math.floor(gy + 0.5)));
                const time_val_ms = times[time_idx];
                
                if (time_idx >= levels_matrix.length || freq_idx >= levels_matrix[time_idx].length) {
                    div.text = "Data Error";
                    div.change.emit();
                    return false;
                }
                const level_val_hover = levels_matrix[time_idx][freq_idx];
                const time_str = new Date(time_val_ms).toLocaleString();
                const freq_str = freq_labels_str[freq_idx];
                let level_str_hover = (level_val_hover == null || isNaN(level_val_hover)) ? "N/A" : level_val_hover.toFixed(1) + " dB";
                div.text = `<b>Time:</b> ${time_str} | <b>Freq:</b> ${freq_str} | <b>Level:</b> ${level_str_hover}`;
                div.change.emit();
    
                // Update Bar Chart from Hover Data
                let levels_slice = levels_matrix[time_idx];
                const cleanedLevels = levels_slice.map(level => (level == null || isNaN(level)) ? 0 : level);
                bar_source_js.data = { 'levels': cleanedLevels, 'frequency_labels': freq_labels_str };
                bar_x_range_js.factors = freq_labels_str;
                barChart.title.text = `Frequency Slice: ${position_name} (${active_spec_key.replace('_', ' ')}) | ${_state.selectedParameter} | ${new Date(time_val_ms).toLocaleTimeString()} (Hover)`;
                bar_source_js.change.emit();
                return true;
            } else {
                // Logic for when mouse leaves spectrogram area
                div.text = "Hover over spectrogram to view details";
                div.change.emit();
                if (_state.verticalLinePosition !== null) {
                    const activePosForRestore = _state.isPlaying ? _state.activeAudioPosition : null;
                    _updateBarChart(_state.verticalLinePosition, _state.activeChartIndex, activePosForRestore, "Click Line");
                }
                return true;
            }
        } catch (error) { 
            console.error("Error in _handleSpectrogramHover:", error);
            return false; 
        }
    }

    // --- Audio Button State Management ---
    // [_updatePlayButtonsState - unchanged]
    function _updatePlayButtonsState(isPlaying) {
        /* DEBUG START */
        console.log(`[DEBUG] _updatePlayButtonsState: Updating play button states. isPlaying: ${isPlaying}, activeAudioPosition: ${_state.activeAudioPosition}.`);
        /* DEBUG END */
        // Main play/pause buttons
        if (_models.playButton) { _models.playButton.disabled = isPlaying; /* DEBUG START */ console.log(`[DEBUG] _updatePlayButtonsState: Main Play button disabled state set to ${isPlaying}.`); /* DEBUG END */ }
        if (_models.pauseButton) { _models.pauseButton.disabled = !isPlaying; /* DEBUG START */ console.log(`[DEBUG] _updatePlayButtonsState: Main Pause button disabled state set to ${!isPlaying}.`); /* DEBUG END */ }

        // Position-specific play/pause buttons
        if (_models.positionPlayButtons && typeof _models.positionPlayButtons === 'object') {
            /* DEBUG START */
            console.log(`[DEBUG] _updatePlayButtonsState: Iterating through ${_models.positionPlayButtons ? Object.keys(_models.positionPlayButtons).length : 0} position play buttons.`);
            /* DEBUG END */
            Object.keys(_models.positionPlayButtons).forEach(posName => {
                const button = _models.positionPlayButtons[posName];
                // Check if it looks like a Bokeh button model
                // Use a more robust check for Bokeh model properties
                if (button && button.id) {
                    const isActivePosition = isPlaying && posName === _state.activeAudioPosition;
                    /* DEBUG START */
                    console.log(`[DEBUG] _updatePlayButtonsState: Processing button for position '${posName}'. Is active position: ${isActivePosition}.`);
                    /* DEBUG END */

                    if (isActivePosition) {
                        // This position is playing: Show Pause state
                        button.label = `Pause ${posName}`;
                        button.button_type = "warning"; // e.g., 'warning' or 'danger' for pause
                        button.disabled = false; // Enable clicking to pause
                        /* DEBUG START */
                        console.log(`[DEBUG] _updatePlayButtonsState: Position '${posName}' is active. Setting to 'Pause' state (label: ${button.label}, type: ${button.button_type}, disabled: ${button.disabled}).`);
                        /* DEBUG END */
                    } else {
                        // This position is NOT playing: Show Play state
                        button.label = `Play ${posName}`;
                        button.button_type = "success";
                        // Disable if *any* audio is playing (can't start another)
                        button.disabled = isPlaying;
                        /* DEBUG START */
                        console.log(`[DEBUG] _updatePlayButtonsState: Position '${posName}' is not active. Setting to 'Play' state (label: ${button.label}, type: ${button.button_type}, disabled: ${button.disabled}).`);
                        /* DEBUG END */
                    }
                } else if (button !== null && button !== undefined) { // Log only if it exists but isn't valid
                    // Avoid logging if the button genuinely wasn't created/passed for this position
                    /* DEBUG START */
                    console.warn(`[DEBUG] _updatePlayButtonsState: Item '${posName}' in positionPlayButtons is not a valid Bokeh button model or is missing properties.`);
                    /* DEBUG END */
                }
            });
        }
        /* DEBUG START */
        console.log("[DEBUG] _updatePlayButtonsState: Finished updating all play button states.");
        /* DEBUG END */
    }

    // --- Public API - Initialize App ---
    function initializeApp(models, options) {
        console.info('[DEBUG] NoiseSurveyApp - Initializing with hierarchical structure support...');
        try {
            console.log('[DEBUG] Setting global models...');

            // Check if using hierarchical structure (passed from Python)
            const usingHierarchicalStructure = models.hierarchical === true;
            console.log(`[DEBUG] Using ${usingHierarchicalStructure ? 'hierarchical' : 'legacy'} structure.`);

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

            console.log('[DEBUG] Global models set:', _models);

            // --- Model Validation ---
            if (!_models.playbackSource) { console.error("[DEBUG] Initialization Error: playback_source model missing!"); }
            if (!_models.playbackStatusSource) { console.error("[DEBUG] Initialization Error: playback_status_source model missing!"); }
            if (!_models.playButton) { console.warn("[DEBUG] Initialization Warning: Main play_button model missing."); }
            if (!_models.pauseButton) { console.warn("[DEBUG] Initialization Warning: Main pause_button model missing."); }
            if (!_models.seekCommandSource) { console.error("[DEBUG] Initialization Error: seek_command_source model missing!"); }
            if (!_models.playRequestSource) { console.error("[DEBUG] Initialization Error: play_request_source model missing!"); } // Essential for new logic
            if (!_models.barChart) { console.warn("[DEBUG] Initialization Warning: Frequency bar chart model not found."); }
            if (!_models.barSource) { console.warn("[DEBUG] Initialization Warning: Frequency bar chart data source not found."); }
            if (!_models.barXRange) { console.warn("[DEBUG] Initialization Warning: Frequency bar chart x-range not found."); }
            if (Object.keys(_models.positionPlayButtons || {}).length === 0) { console.warn("[DEBUG] Initialization Warning: No position play button models found."); }
            if (Object.keys(_models.spectralParamCharts || {}).length === 0) {
                console.warn("[DEBUG] Initialization Warning: Spectral parameter chart data store is empty! Frequency bar updates during playback may fail.");
            }

            //set up playback_status_source monitor
            if (_models.playbackStatusSource) {
                /* DEBUG START */
                console.log("[DEBUG] Setting up playback_status_source data change listener.");
                /* DEBUG END */
                _models.playbackStatusSource.on_change('data', () => {
                    const isPlaying = _models.playbackStatusSource.data.is_playing[0];
                    const activePosition = _models.playbackStatusSource.data.active_position[0];

                    console.log(`[DEBUG] JS received state update from Python: isPlaying=${isPlaying}, activePosition='${activePosition}'.`);

                    // Update the JS state from the single source of truth (Python)
                    _state.isPlaying = isPlaying;
                    _state.activeAudioPosition = activePosition;
                    /* DEBUG START */
                    console.log(`[DEBUG] Internal state updated: _state.isPlaying=${_state.isPlaying}, _state.activeAudioPosition='${_state.activeAudioPosition}'.`);
                    /* DEBUG END */

                    // Update all UI buttons based on this new, correct state
                    _updatePlayButtonsState(isPlaying);
                });
            } else {
                /* DEBUG START */
                console.warn("[DEBUG] playback_status_source not available. Cannot set up state change listener.");
                /* DEBUG END */
            }


            // Validate individual position buttons
            Object.keys(_models.positionPlayButtons).forEach(posName => {
                const button = _models.positionPlayButtons[posName];
                if (button && button.id) {
                    const isActivePosition = _state.isPlaying && posName === _state.activeAudioPosition;
                    /* DEBUG START */
                    console.log(`[DEBUG] Initializing button '${posName}'. Is active position: ${isActivePosition}.`);
                    /* DEBUG END */
                    if (isActivePosition) {
                        // This position is playing: Show Pause state
                        button.label = `Pause ${posName}`;
                        button.button_type = "warning"; // e.g., 'warning' or 'danger' for pause
                        button.disabled = false; // Enable clicking to pause
                        /* DEBUG START */
                        console.log(`[DEBUG] Button '${posName}' initialized to 'Pause' state.`);
                        /* DEBUG END */
                    } else {
                        // This position is NOT playing: Show Play state
                        button.label = `Play ${posName}`;
                        button.button_type = "success";
                        // Disable if *any* audio is playing (can't start another)
                        button.disabled = _state.isPlaying;
                        /* DEBUG START */
                        console.log(`[DEBUG] Button '${posName}' initialized to 'Play' state, disabled: ${_state.isPlaying}.`);
                        /* DEBUG END */
                    }
                } else if (button !== null && button !== undefined) {
                    /* DEBUG START */
                    console.warn(`[DEBUG] Item '${posName}' in positionPlayButtons is not a valid Bokeh button model or is missing properties during initialization.`);
                    /* DEBUG END */
                }
            });

            // Set state from models
            if (_models.selectedParamHolder?.text) {
                _state.selectedParameter = _models.selectedParamHolder.text;
                /* DEBUG START */
                console.log(`[DEBUG] Initial selected parameter set from holder: ${_state.selectedParameter}.`);
                /* DEBUG END */
            }
            _state.isPlaying = false; // Initialize playback state
            /* DEBUG START */
            console.log("[DEBUG] Initial playback state set to not playing.");
            /* DEBUG END */

            // Initialize playback time
            if (_models.playbackSource) {
                let initialTimeMs = 0;
                // Default to chart start if available
                if (_models.charts.length > 0 && _models.charts[0]?.x_range?.start !== undefined && _models.charts[0]?.x_range?.start !== null) {
                    initialTimeMs = _models.charts[0].x_range.start;
                    /* DEBUG START */
                    console.log(`[DEBUG] Initial playback time derived from first chart's x_range.start: ${initialTimeMs}ms.`);
                    /* DEBUG END */
                } else {
                    /* DEBUG START */
                    console.warn("[DEBUG] Could not derive initial playback time from charts. Defaulting to 0ms.");
                    /* DEBUG END */
                }
                // Ensure data structure exists and initialize/reset time
                if (!_models.playbackSource.data || typeof _models.playbackSource.data !== 'object') {
                    _models.playbackSource.data = { 'current_time': [initialTimeMs] };
                    /* DEBUG START */
                    console.log(`[DEBUG] Initialized playbackSource.data as new object with current_time: [${initialTimeMs}].`);
                    /* DEBUG END */
                } else {
                    _models.playbackSource.data['current_time'] = [initialTimeMs];
                    /* DEBUG START */
                    console.log(`[DEBUG] Set playbackSource.data.current_time to: [${initialTimeMs}].`);
                    /* DEBUG END */
                }
                _hideAllLinesAndLabels(); // Hide lines initially
                _state.verticalLinePosition = initialTimeMs; // Sync internal state
                console.log(`[DEBUG] Playback source position initialized to time: ${new Date(initialTimeMs).toISOString()}.`);
            } else { console.error("[DEBUG] Initialization Error: Cannot initialize playback time - playbackSource missing."); }

            _updatePlayButtonsState(false); // Set initial button states (not playing)
            const kbNavEnabled = options?.enableKeyboardNavigation ?? false; // Default to false if option missing
            if (kbNavEnabled) { setupKeyboardNavigation(); }
            else { _state.keyboardNavigationEnabled = false; console.log("[DEBUG] Keyboard navigation disabled based on options."); }

            console.info('[DEBUG] NoiseSurveyApp - Initialization complete.');
            // console.log('Models:', _models); // Can be verbose
            return true;
        } catch (error) { console.error('[DEBUG] Error during initialization:', error); return false; }
    }

    // --- Audio Player Integration ---
    // [synchronizePlaybackPosition - unchanged]
    function synchronizePlaybackPosition(ms) {
        /* DEBUG START */
        console.log(`[DEBUG] synchronizePlaybackPosition: Called with ms=${ms}.`);
        /* DEBUG END */
        try {
            // Ensure ms is valid before updating
            if (typeof ms === 'number' && !isNaN(ms)) {
                _updateTapLinePositions(ms);
                // Update frequency bar DATA and TITLE using the stored active position
                // Pass null for activeChartIndex to prioritize activeAudioPosition
                _updateBarChart(ms, null, _state.activeAudioPosition, "Audio Playback");
                /* DEBUG START */
                console.log(`[DEBUG] synchronizePlaybackPosition: Tap lines and bar chart updated for time ${ms}ms.`);
                /* DEBUG END */
            } else {
                console.warn("[DEBUG] synchronizePlaybackPosition called with invalid time:", ms);
            }

            return true;
        } catch (error) { console.error('[DEBUG] Error synchronizing playback visualization:', error); return false; }
    }

    // [notifyPlaybackStopped - unchanged]
    function notifyPlaybackStopped() {
        console.log("[DEBUG] JS: Received notification that playback stopped (e.g., EOF or error). Resetting state.");
        if (_state.isPlaying) { // Only reset if JS thought it was playing
            _state.isPlaying = false;
            _state.activeAudioPosition = null;
            _updatePlayButtonsState(false);
            /* DEBUG START */
            console.log("[DEBUG] notifyPlaybackStopped: Playback state reset to not playing, active position cleared. Buttons updated.");
            /* DEBUG END */
        } else {
            console.log("[DEBUG] notifyPlaybackStopped: Called, but already in paused state. Ensuring buttons are correct.");
            // Ensure buttons are visually correct even if state was already false
            _updatePlayButtonsState(false);
        }
    }

    // --- Parameter Selection ---
    function handleParameterChange(param) {
        /* DEBUG START */
        console.log(`[DEBUG] handleParameterChange: Parameter changed to '${param}'.`);
        /* DEBUG END */
        if (!param) {
            console.warn('[DEBUG] handleParameterChange: Called with null or undefined parameter. Aborting.');
            return false;
        }

        // Store the selected parameter in the app's state
        _state.selectedParameter = param;
        /* DEBUG START */
        console.log(`[DEBUG] _state.selectedParameter updated to '${_state.selectedParameter}'.`);
        /* DEBUG END */

        // Update the hidden div model that Python can see
        if (_models.selectedParamHolder) {
            _models.selectedParamHolder.text = param;
            /* DEBUG START */
            console.log(`[DEBUG] _models.selectedParamHolder text set to '${param}'.`);
            /* DEBUG END */
        } else {
            /* DEBUG START */
            console.warn("[DEBUG] handleParameterChange: _models.selectedParamHolder not found. Cannot update Python visible parameter.");
            /* DEBUG END */
        }

        try {
            const spectralDataStore = _models.spectralParamCharts || {};
            /* DEBUG START */
            console.log(`[DEBUG] handleParameterChange: Processing ${Object.keys(spectralDataStore).length} spectral charts.`);
            /* DEBUG END */

            // Loop through each position (e.g., 'SW', 'N')
            for (const positionKey in spectralDataStore) {
                const chart = _models.charts.find(c => c.name === `${positionKey}_combined_spectrogram`);
                if (!chart) { /* DEBUG START */ console.log(`[DEBUG] handleParameterChange: No combined spectrogram chart found for position '${positionKey}'. Skipping.`); /* DEBUG END */ continue; }

                const active_spec_key = chart.title.text.includes('Spectral Log') ? 'spectral_log' : 'spectral';
            _updateActiveSpectralData(positionKey, active_spec_key, param);
                const data_to_use = spectralDataStore[positionKey][active_spec_key];
                const imageRenderer = chart.renderers.find(r => r.glyph?.type === "Image");
    
                if (!imageRenderer) continue;
                /* DEBUG START */
                console.log(`[DEBUG] handleParameterChange: For position '${positionKey}', active_spec_key is '${active_spec_key}'.`);
                /* DEBUG END */

                if (!imageRenderer) { /* DEBUG START */ console.warn(`[DEBUG] handleParameterChange: No Image renderer found for chart '${chart.name}'. Skipping.`); /* DEBUG END */ continue; }

                if (data_to_use && data_to_use.prepared_data) {
                    const preparedData = data_to_use.prepared_data[param];
                    if (preparedData) {
                        const source = imageRenderer.data_source;
                        const glyph = imageRenderer.glyph;
                        const colourMapper = glyph.color_mapper;

                        /* DEBUG START */
                        console.log(`[DEBUG] handleParameterChange: Updating spectrogram for '${positionKey}' with new data for param '${param}'.`);
                        /* DEBUG END */
                        //update glyph properties
                        glyph.x = preparedData.x;
                        glyph.y = preparedData.y;
                        glyph.dw = preparedData.dw;
                        glyph.dh = preparedData.dh;
                        source.data = { 'image': [preparedData.levels_matrix_transposed] };

                        if (colourMapper) {
                            colourMapper.low = preparedData.min_val;
                            colourMapper.high = preparedData.max_val;
                            /* DEBUG START */
                            console.log(`[DEBUG] handleParameterChange: Color mapper for '${positionKey}' updated: low=${colourMapper.low}, high=${colourMapper.high}.`);
                            /* DEBUG END */
                        }

                        //update the chart title
                        const new_title_suffix = (active_spec_key === 'spectral_log') ? "Spectral Log" : "Spectral Overview";
                        combined_chart.title.text = `${positionKey} - (${new_title_suffix})`;

                        // Make the chart visible and emit changes
                        combined_spectrogram.visible = true;
                        source.change.emit();
                        /* DEBUG START */
                        console.log(`[DEBUG] Spectrogram for ${positionKey} updated and made visible. Title: '${combined_chart.title.text}'.`);
                        /* DEBUG END */
                    } else {
                        combined_spectrogram.visible = false;
                        source.change.emit(); // Emit change even if hiding to ensure Bokeh updates
                        /* DEBUG START */
                        console.warn(`[DEBUG] No prepared data for param '${_state.selectedParameter}' in '${active_spec_key}' for position ${positionKey}. Hiding chart.`);
                        /* DEBUG END */
                    }
                } else {
                    combined_spectrogram.visible = false;
                    /* DEBUG START */
                    console.log(`[DEBUG] No spectral data_to_use or prepared_data for this toggle state for position ${positionKey}. Hiding chart.`);
                    /* DEBUG END */
                }
            }
            if (_state.verticalLinePosition !== null) {
                /* DEBUG START */
                console.log("[DEBUG] handleParameterChange: Re-updating bar chart due to parameter change.");
                /* DEBUG END */
                _updateBarChart(_state.verticalLinePosition, _state.activeChartIndex, _state.activeAudioPosition, "Parameter Change");
            }
            /* DEBUG START */
            console.log("[DEBUG] handleParameterChange: Parameter change handled successfully.");
            /* DEBUG END */
            return true;
        } catch (error) {
            console.error('[DEBUG] Error handling parameter change:', error);
            return false;
        }
    }

    function handleCombinedChartToggle(is_active, combined_source, overview_raw_data, log_raw_data, combined_chart_state_source, combined_chart, position, combined_spectrogram, spectral_prepared_data, toggle_widget) {
        console.log(`[DEBUG] handleCombinedChartToggle for ${position} called. Active: ${is_active}.`);

        //determine which data to display
        let new_data_obj = null;
        let new_display_type = "";
        let toggle_button_label = "";
        let toggle_widget_active = is_active;

        if (is_active) { // Toggle is ON, meaning user wants to see LOG data
            /* DEBUG START */
            console.log(`[DEBUG] handleCombinedChartToggle: Toggle is active (ON), attempting to switch to Log Data for ${position}.`);
            /* DEBUG END */
            if (log_raw_data) {
                new_data_obj = log_raw_data;
                new_display_type = "Log Data";
                toggle_button_label = "Switch to Overview";
            } else {
                console.warn(`[DEBUG] No log data available for ${position}. Cannot switch to log. Reverting toggle.`);
                // If no overview data, revert toggle to OFF (Overview)
                toggle_widget_active = false;
                toggle_widget.active = toggle_widget_active; // Ensure widget reflects true state
                return;
            }
        } else { // Toggle is OFF, meaning user wants to see OVERVIEW data
            /* DEBUG START */
            console.log(`[DEBUG] handleCombinedChartToggle: Toggle is inactive (OFF), attempting to switch to Overview Data for ${position}.`);
            /* DEBUG END */
            if (overview_raw_data) {
                new_data_obj = overview_raw_data;
                new_display_type = "Overview Data";
                toggle_button_label = "Switch to Log";
            } else {
                console.warn(`[DEBUG] No overview data available for ${position}. Cannot switch to overview. Reverting toggle.`);
                // If no overview data, revert toggle to ON (Log)
                toggle_widget_active = true;
                toggle_widget.active = toggle_widget_active; // Ensure widget reflects true state
                return;
            }
        }

        if (new_data_obj) {
            //Swap the data in the combined source
            combined_source.data = new_data_obj;
            combined_source.change.emit();
            console.log(`[DEBUG] Combined chart data for ${position} updated to ${new_display_type}. Data change emitted.`);

            const current_title = combined_chart.title.text;
            combined_chart.title.text = current_title.replace(/ (Overview|Log|Combined) Data/, ` ${new_display_type}`);
            /* DEBUG START */
            console.log(`[DEBUG] Combined chart title updated to: '${combined_chart.title.text}'.`);
            /* DEBUG END */

            toggle_widget.label = toggle_button_label;
            toggle_widget.active = toggle_widget_active;
            /* DEBUG START */
            console.log(`[DEBUG] Toggle widget label set to '${toggle_button_label}' and active state to ${toggle_widget_active}.`);
            /* DEBUG END */

            // Update the state source that tracks what's currently displayed
            combined_chart_state_source.data['display_type'][0] = new_display_type;
            combined_chart_state_source.data['enable_auto_switch'][0] = is_active;
            combined_chart_state_source.change.emit();
            /* DEBUG START */
            console.log(`[DEBUG] combined_chart_state_source updated: display_type='${new_display_type}', enable_auto_switch=${is_active}. Change emitted.`);
            /* DEBUG END */

            //recalculate step size for keyboard navigation
            _state.stepSize = calculateStepSize(combined_source);
            console.log(`[DEBUG] Updated keyboard step size for ${position}: ${_state.stepSize}ms.`);

            // Force an update of the main vertical line's label
            if (_state.verticalLinePosition !== null) {
                /* DEBUG START */
                console.log("[DEBUG] handleCombinedChartToggle: Forcing update of tap line positions and labels.");
                /* DEBUG END */
                _updateTapLinePositions(_state.verticalLinePosition);
            }

            if (combined_spectrogram && spectral_prepared_data) {
                const new_spec_key = is_active ? "spectral_log" : "spectral";
                _updateActiveSpectralData(position, new_spec_key, _state.selectedParameter);
                const fallback_spec_key = is_active ? "spectral" : "spectral_log";
                /* DEBUG START */
                console.log(`[DEBUG] handleCombinedChartToggle: Spectrogram update for ${position}. New spec key: '${new_spec_key}'. Fallback spec key: '${fallback_spec_key}'.`);
                /* DEBUG END */

                let spec_data_to_use = spectral_prepared_data[new_spec_key] || spectral_prepared_data[fallback_spec_key];

                if (spec_data_to_use) {
                    const prepared_data = spec_data_to_use.prepared_data[_state.selectedParameter];
                    const imageRenderer = combined_spectrogram.renderers.find(r => r.glyph && r.glyph.type === "Image");

                    if (prepared_data && imageRenderer) {
                        const source = imageRenderer.data_source;
                        const glyph = imageRenderer.glyph;
                        const colourMapper = glyph.color_mapper;

                        /* DEBUG START */
                        console.log(`[DEBUG] handleCombinedChartToggle: Updating spectrogram image for position '${position}' with data for parameter '${_state.selectedParameter}'.`);
                        /* DEBUG END */
                        //update glyph properties
                        glyph.x = prepared_data.x;
                        glyph.y = prepared_data.y;
                        glyph.dw = prepared_data.dw;
                        glyph.dh = prepared_data.dh;
                        source.data = { 'image': [prepared_data.levels_matrix_transposed] };

                        if (colourMapper) {
                            colourMapper.low = prepared_data.min_val;
                            colourMapper.high = prepared_data.max_val;
                            /* DEBUG START */
                            console.log(`[DEBUG] handleCombinedChartToggle: Spectrogram color mapper for '${position}' updated: low=${colourMapper.low}, high=${colourMapper.high}.`);
                            /* DEBUG END */
                        }

                        //update the chart title
                        const new_title_suffix = (new_spec_key === 'spectral_log') ? "Spectral Log" : "Spectral Overview";
                        combined_chart.title.text = `${position} - (${new_title_suffix})`;

                        // Make the chart visible and emit changes
                        combined_spectrogram.visible = true;
                        source.change.emit();
                        console.log(`[DEBUG] Spectrogram for ${position} updated to ${new_spec_key} and made visible. Title: '${combined_chart.title.text}'.`);

                    } else {
                        combined_spectrogram.visible = false;
                        /* DEBUG START */
                        console.warn(`[DEBUG] No prepared data for param '${_state.selectedParameter}' in '${new_spec_key}' (or fallback '${fallback_spec_key}') for position ${position}. Hiding chart.`);
                        /* DEBUG END */
                    }

                } else {
                    combined_spectrogram.visible = false;
                    /* DEBUG START */
                    console.log(`[DEBUG] No spectral data_to_use available for this toggle state for position ${position}. Hiding spectrogram.`);
                    /* DEBUG END */
                }
            }


        } else {
            console.warn(`[DEBUG] No data to switch to for ${position}. This should not happen if previous checks were correct.`);
        }
    }




    // Public wrapper for _updateBarChart
    // [updateFrequencyBar - unchanged]
    function updateFrequencyBar(x, activeChartIndex, title_source = '') {
        /* DEBUG START */
        console.log(`[DEBUG] updateFrequencyBar: Public wrapper called for x=${x}, activeChartIndex=${activeChartIndex}, title_source='${title_source}'.`);
        /* DEBUG END */
        try {
            if (typeof x !== 'number' || isNaN(x)) { console.warn("[DEBUG] updateFrequencyBar: Invalid 'x' value. Returning false."); return false; }
            // Call internal function - activeAudioPos is null for user interactions unless already playing
            const activePos = _state.isPlaying ? _state.activeAudioPosition : null;
            _updateBarChart(x, activeChartIndex, activePos, title_source);
            /* DEBUG START */
            console.log("[DEBUG] updateFrequencyBar: Successfully called internal _updateBarChart.");
            /* DEBUG END */
            return true;
        } catch (error) { console.error("[DEBUG] Error updating frequency bar:", error); return false; }
    }

    // --- Tap Line Visibility ---
    function showTapLines() {
        /* DEBUG START */
        console.log("[DEBUG] showTapLines: Attempting to make tap lines visible.");
        /* DEBUG END */
        if (!_models.clickLines) { console.warn("[DEBUG] showTapLines: _models.clickLines is missing. Cannot show lines."); return false; }
        try {
            if (_state.verticalLinePosition !== null) {
                _updateTapLinePositions(_state.verticalLinePosition);
                /* DEBUG START */
                console.log(`[DEBUG] showTapLines: Updated tap line positions to ${_state.verticalLinePosition}ms.`);
                /* DEBUG END */
            } else {
                /* DEBUG START */
                console.log("[DEBUG] showTapLines: verticalLinePosition is null. No specific position to update lines to, just making them visible if they exist.");
                /* DEBUG END */
            }
            // Only make lines visible, labels are handled by _updateChartLine
            _models.clickLines.forEach(line => { if (line) line.visible = true; });
            /* DEBUG START */
            console.log("[DEBUG] showTapLines: All click lines set to visible.");
            /* DEBUG END */
            // Ensure labels corresponding to the current position are visible
            if (_state.verticalLinePosition !== null) {
                _models.charts.forEach((chart, i) => {
                    if (chart && _models.clickLines?.[i] && _models.labels?.[i]) {
                        _updateChartLine(chart, _models.clickLines[i], _models.labels[i], _state.verticalLinePosition, i);
                        /* DEBUG START */
                        console.log(`[DEBUG] showTapLines: Re-rendered label for chart index ${i} at ${_state.verticalLinePosition}ms.`);
                        /* DEBUG END */
                    }
                });
            }
            /* DEBUG START */
            console.log("[DEBUG] showTapLines: Tap lines visibility process complete.");
            /* DEBUG END */
            return true;
        } catch (error) { console.error("[DEBUG] Error showing tap lines:", error); return false; }
    }
    function hideTapLines() {
        /* DEBUG START */
        console.log("[DEBUG] hideTapLines: Calling internal _hideAllLinesAndLabels.");
        /* DEBUG END */
        return _hideAllLinesAndLabels();
    }

    function updateTapLinePosition(x) {
        /* DEBUG START */
        console.log(`[DEBUG] updateTapLinePosition: Public wrapper called with x=${x}.`);
        /* DEBUG END */
        if (typeof x !== 'number' || isNaN(x)) { console.warn("[DEBUG] updateTapLinePosition: Invalid 'x' value. Returning false."); return false; }
        try {
            const result = _updateTapLinePositions(x);
            /* DEBUG START */
            console.log(`[DEBUG] updateTapLinePosition: Internal _updateTapLinePositions returned ${result}.`);
            /* DEBUG END */
            return result;
        } catch (error) { console.error("[DEBUG] Error updating tap line position:", error); return false; }
    }

    // --- JS Audio Control Wrappers (trigger Python via model changes) ---

    // [startAudioPlayback - unchanged]
    function startAudioPlayback() {
        /* DEBUG START */
        console.log("[DEBUG] startAudioPlayback: Attempting to start audio playback.");
        /* DEBUG END */
        try {
            if (!_models.playButton) { console.warn("[DEBUG] Main Play button model missing. Cannot start playback."); return false; }
            if (!_models.playButton.disabled) { // Check if already playing (button is disabled if so)
                console.log("[DEBUG] JS: Triggering main Play button click via model.");

                // Optimistically update state - Python callback should confirm/correct if needed
                _state.isPlaying = true;
                /* DEBUG START */
                console.log("[DEBUG] Optimistically set _state.isPlaying to true.");
                /* DEBUG END */
                // If activeAudioPosition isn't set, Python needs a default or error handling
                if (!_state.activeAudioPosition && Object.keys(_models.positionPlayButtons).length > 0) {
                    // Attempt to set a default if none is active
                    _state.activeAudioPosition = Object.keys(_models.positionPlayButtons)[0];
                    console.log("[DEBUG] No active position set, defaulting to:", _state.activeAudioPosition);
                } else if (!_state.activeAudioPosition) {
                    console.error("[DEBUG] Cannot start playback: No active audio position set and no position buttons found to default to.");
                    _state.isPlaying = false; // Revert state
                    _updatePlayButtonsState(false); // Update buttons to reflect reverted state
                    return false;
                }
                /* DEBUG START */
                console.log(`[DEBUG] Current active audio position for playback: '${_state.activeAudioPosition}'.`);
                /* DEBUG END */

                _updatePlayButtonsState(true); // Update button visuals
                /* DEBUG START */
                console.log("[DEBUG] Play buttons state updated to 'playing'.");
                /* DEBUG END */

                // Trigger the Bokeh model change, which Python listens for
                _models.playButton.clicks = (_models.playButton.clicks || 0) + 1;
                _models.playButton.change.emit();
                /* DEBUG START */
                console.log(`[DEBUG] _models.playButton.clicks incremented to ${_models.playButton.clicks}. Change emitted to Python.`);
                /* DEBUG END */
                return true;
            } else {
                console.warn("[DEBUG] JS: Main Play button is disabled (already playing?). Skipping start playback.");
                return false;
            }
        } catch (error) {
            console.error("[DEBUG] Error triggering start audio from JS:", error);
            _state.isPlaying = false; // Revert state on error
            _updatePlayButtonsState(false);
            return false;
        }
    }

    // [pauseAudioPlayback - unchanged]
    function pauseAudioPlayback() {
        /* DEBUG START */
        console.log("[DEBUG] pauseAudioPlayback: Attempting to pause audio playback.");
        /* DEBUG END */
        try {
            if (!_models.playRequestSource) {
                console.error("[DEBUG] Cannot pause: playRequestSource model is missing! Aborting.");
                return false;
            }

            console.log("[DEBUG] JS: Sending pause request to Python via playRequestSource.");

            // Send a specific signal for pausing via the playRequestSource.
            // Python will listen for this exact 'pause_request' string.
            _models.playRequestSource.data = { 'position': ['pause_request'], 'time': [_state.verticalLinePosition] };
            _models.playRequestSource.change.emit(); // Signal Python
            /* DEBUG START */
            console.log(`[DEBUG] Pause request emitted via playRequestSource. Current verticalLinePosition: ${_state.verticalLinePosition}ms.`);
            /* DEBUG END */

            return true;
        } catch (error) {
            console.error("[DEBUG] Error sending pause request from JS:", error);
            return false;
        }
    }

    function handlePositionPlayClick(positionName) {
        /* DEBUG START */
        console.log(`[DEBUG] handlePositionPlayClick: Called for position '${positionName}'.`);
        /* DEBUG END */
        if (!_models.playRequestSource) {
            console.error("[DEBUG] Cannot handle position play click: playRequestSource model is missing! Aborting.");
            return false;
        }

        let currentTime = _state.verticalLinePosition;
        if (currentTime === null || currentTime === undefined) {
            if (_models.charts?.[0]?.x_range?.start) {
                currentTime = _models.charts[0].x_range.start;
                _state.verticalLinePosition = currentTime; // Update the state as well
                console.log(`[DEBUG] verticalLinePosition was null, defaulting to chart start: ${currentTime}ms.`);
            } else {
                console.error("[DEBUG] Cannot determine a valid time to play from. No verticalLinePosition and no chart start. Aborting.");
                return false;
            }
        }
        /* DEBUG START */
        console.log(`[DEBUG] JS: Sending toggle play request for position: '${positionName}', time: ${currentTime}ms.`);
        /* DEBUG END */

        // Update the playRequestSource model
        _models.playRequestSource.data = { 'position': [positionName], 'time': [currentTime] };
        _models.playRequestSource.change.emit(); // Signal Python to handle the request
        /* DEBUG START */
        console.log("[DEBUG] playRequestSource change emitted for position play click.");
        /* DEBUG END */

        return true;
    }

    function togglePlayPause() {
        /* DEBUG START */
        console.log("[DEBUG] togglePlayPause: Attempting to toggle play/pause state.");
        /* DEBUG END */
        try {
            // This toggles based on the MAIN pause button's state
            if (!_models.playButton || !_models.pauseButton) { console.warn("[DEBUG] Main Play/Pause button models missing. Cannot toggle playback."); return false; }

            if (!_models.pauseButton.disabled) { // If pause is ENABLED, it means we are currently playing
                /* DEBUG START */
                console.log("[DEBUG] togglePlayPause: Main pause button is enabled, so currently playing. Calling pauseAudioPlayback().");
                /* DEBUG END */
                return pauseAudioPlayback();
            } else if (!_models.playButton.disabled) { // If play is ENABLED, it means we are currently paused
                /* DEBUG START */
                console.log("[DEBUG] togglePlayPause: Main play button is enabled, so currently paused. Preparing to call startAudioPlayback().");
                /* DEBUG END */
                // When toggling play from paused state, ensure an active position is selected or default
                if (!_state.activeAudioPosition && Object.keys(_models.positionPlayButtons).length > 0) {
                    _state.activeAudioPosition = Object.keys(_models.positionPlayButtons)[0];
                    console.log("[DEBUG] Toggle Play: No active position, defaulting to:", _state.activeAudioPosition);
                } else if (!_state.activeAudioPosition) {
                    console.error("[DEBUG] Toggle Play: Cannot start playback - no position selected and no defaults available.");
                    return false;
                }
                return startAudioPlayback();
            } else {
                // This state should ideally not happen if logic is correct
                console.warn("[DEBUG] Toggle Play/Pause: Both Play and Pause buttons seem disabled. This indicates an unexpected state.");
                return false;
            }
        } catch (error) { console.error("[DEBUG] Error toggling play/pause from JS:", error); return false; }
    }

    // --- Keyboard Navigation ---
    // [enableKeyboardNavigation, disableKeyboardNavigation, handleKeyPress, setupKeyboardNavigation - unchanged]
    function enableKeyboardNavigation() {
        /* DEBUG START */
        console.log("[DEBUG] enableKeyboardNavigation: Attempting to enable keyboard navigation.");
        /* DEBUG END */
        if (!_state.keyboardNavigationEnabled) {
            try {
                document.addEventListener('keydown', handleKeyPress);
                _state.keyboardNavigationEnabled = true;
                console.log('[DEBUG] Keyboard navigation enabled.');
                return true;
            } catch (error) { console.error("[DEBUG] Error enabling keyboard navigation:", error); return false; }
        }
        console.log("[DEBUG] Keyboard navigation already enabled.");
        return true; // Already enabled
    }
    function disableKeyboardNavigation() {
        /* DEBUG START */
        console.log("[DEBUG] disableKeyboardNavigation: Attempting to disable keyboard navigation.");
        /* DEBUG END */
        if (_state.keyboardNavigationEnabled) {
            try {
                document.removeEventListener('keydown', handleKeyPress);
                _state.keyboardNavigationEnabled = false;
                console.log('[DEBUG] Keyboard navigation disabled.');
                return true;
            } catch (error) { console.error("[DEBUG] Error disabling keyboard navigation:", error); return false; }
        }
        console.log("[DEBUG] Keyboard navigation already disabled.");
        return true; // Already disabled
    }
    function handleKeyPress(e) {
        /* DEBUG START */
        console.log(`[DEBUG] handleKeyPress: Key '${e.key}' (${e.code}) pressed.`);
        /* DEBUG END */
        // Allow keyboard input in text fields, etc.
        const targetTagName = e.target.tagName.toLowerCase();
        if (targetTagName === 'input' || targetTagName === 'textarea' || targetTagName === 'select') {
            // Don't interfere with form inputs
            /* DEBUG START */
            console.log("[DEBUG] handleKeyPress: Key press occurred within an input field. Skipping default handling.");
            /* DEBUG END */
            return;
        }

        // Basic check for models needed for navigation/playback
        if (!_models.playbackSource || !_models.seekCommandSource) { console.warn("[DEBUG] Keyboard navigation disabled: essential models (playbackSource or seekCommandSource) not ready."); return; }

        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            e.preventDefault();
            let currentX = _state.verticalLinePosition ?? _models.playbackSource.data?.current_time?.[0];
            if (currentX === null || currentX === undefined) { // Try chart center fallback
                /* DEBUG START */
                console.log("[DEBUG] handleKeyPress: currentX is null/undefined. Attempting to fall back to chart center.");
                /* DEBUG END */
                currentX = (_models.charts?.[0]?.x_range?.start + _models.charts?.[0]?.x_range?.end) / 2;
            }
            if (currentX === null || currentX === undefined || isNaN(currentX)) { console.warn("[DEBUG] Keyboard navigation: Cannot determine current X position for movement. Aborting."); return; }
            /* DEBUG START */
            console.log(`[DEBUG] handleKeyPress: Current X for navigation: ${currentX}ms.`);
            /* DEBUG END */

            let step = _state.stepSize || 300000;
            let newX = e.key === 'ArrowLeft' ? currentX - step : currentX + step;
            /* DEBUG START */
            console.log(`[DEBUG] handleKeyPress: Calculated new X: ${newX}ms (step: ${step}ms, direction: ${e.key === 'ArrowLeft' ? 'Left' : 'Right'}).`);
            /* DEBUG END */

            // Clamp navigation within the main chart's range if possible
            if (_models.charts?.[0]?.x_range) {
                const minX = _models.charts[0].x_range.start;
                const maxX = _models.charts[0].x_range.end;
                /* DEBUG START */
                console.log(`[DEBUG] handleKeyPress: Chart 0 x_range: [${minX}, ${maxX}].`);
                /* DEBUG END */
                if (newX < minX) { newX = minX; /* DEBUG START */ console.log(`[DEBUG] handleKeyPress: Clamped newX to minX: ${newX}ms.`); /* DEBUG END */ }
                if (newX > maxX) { newX = maxX; /* DEBUG START */ console.log(`[DEBUG] handleKeyPress: Clamped newX to maxX: ${newX}ms.`); /* DEBUG END */ }
            }


            updateTapLinePosition(newX); // Update visuals
            _sendSeekCommand(newX);      // Send command to Python (e.g., for audio seeking if implemented)
            /* DEBUG START */
            console.log(`[DEBUG] handleKeyPress: Tap line updated and seek command sent to ${newX}ms.`);
            /* DEBUG END */

            // Update frequency bar based on this keyboard nav interaction
            const activePosForNav = _state.isPlaying ? _state.activeAudioPosition : null;
            const activeIndexForNav = _state.isPlaying ? null : _state.activeChartIndex; // If playing, activeAudioPosition is primary. Otherwise, use last tapped chart.
            _updateBarChart(newX, activeIndexForNav, activePosForNav, "Keyboard Nav");
            /* DEBUG START */
            console.log("[DEBUG] handleKeyPress: Frequency bar updated based on keyboard navigation.");
            /* DEBUG END */

        } else if (e.key === ' ' || e.code === 'Space') {
            e.preventDefault();
            /* DEBUG START */
            console.log("[DEBUG] handleKeyPress: Spacebar pressed. Calling togglePlayPause().");
            /* DEBUG END */
            togglePlayPause(); // Use the JS toggle function
        }
    }
    function setupKeyboardNavigation() {
        /* DEBUG START */
        console.log("[DEBUG] setupKeyboardNavigation: Helper function called. Calling enableKeyboardNavigation().");
        /* DEBUG END */
        return enableKeyboardNavigation();
    } // Helper

    // --- Chart Interaction Handlers ---
    // [onTapHandler, onHoverHandler - unchanged]
    function onTapHandler(cb_obj, chartModels, clickLineModels, labelModels, sourcesDict) {
        /* DEBUG START */
        console.log(`[DEBUG] onTapHandler: Tap event received. cb_obj.x=${cb_obj?.x}, cb_obj.origin.id=${cb_obj?.origin?.id}.`);
        /* DEBUG END */
        try {
            // Use the models passed directly as arguments instead of relying on the global _models state
            const charts = chartModels || _models.charts;
            const clickLines = clickLineModels || _models.clickLines;
            const labels = labelModels || _models.labels;
            const sources = sourcesDict || _models.sources;
            /* DEBUG START */
            console.log("[DEBUG] onTapHandler: Resolved chart models, clickLines, labels, and sources.");
            /* DEBUG END */

            _state.activeChartIndex = _getActiveChartIndex(cb_obj);
            if (_state.activeChartIndex === -1) {
                console.warn("[DEBUG] onTapHandler: Could not determine active chart on tap. Aborting.");
                return false;
            }
            /* DEBUG START */
            console.log(`[DEBUG] onTapHandler: Active chart index determined: ${_state.activeChartIndex}.`);
            /* DEBUG END */

            const raw_x = cb_obj.x;
            if (raw_x === undefined || raw_x === null || isNaN(raw_x)) {
                console.warn("[DEBUG] Tap handler received invalid x coordinate:", raw_x);
                return false;
            }

            const activeChart = charts[_state.activeChartIndex];
            const source = sources[activeChart.name];
            let snapped_x = raw_x;

            if (source && source.data.Datetime && source.data.Datetime.length > 0) {
                const closest_idx = findClosestDateIndex(source.data.Datetime, raw_x);
                if (closest_idx !== -1) {
                    snapped_x = source.data.Datetime[closest_idx];
                    /* DEBUG START */
                    console.log(`[DEBUG] onTapHandler: Raw X (${raw_x}ms) snapped to closest data point: ${snapped_x}ms (index: ${closest_idx}).`);
                    /* DEBUG END */
                } else {
                    /* DEBUG START */
                    console.warn("[DEBUG] onTapHandler: Could not find closest date index for snapping. Using raw_x.");
                    /* DEBUG END */
                }
            } else {
                /* DEBUG START */
                console.warn("[DEBUG] onTapHandler: Source data (Datetime) missing for active chart. Skipping X snapping.");
                /* DEBUG END */
            }

            // Update the visual representation of all tap lines
            _state.verticalLinePosition = snapped_x;
            /* DEBUG START */
            console.log(`[DEBUG] onTapHandler: Setting _state.verticalLinePosition to ${snapped_x}ms.`);
            /* DEBUG END */
            for (let i = 0; i < charts.length; i++) {
                if (charts[i] && clickLines?.[i] && labels?.[i]) {
                    _updateChartLine(charts[i], clickLines[i], labels[i], snapped_x, i);
                    /* DEBUG START */
                    console.log(`[DEBUG] onTapHandler: Updated click line and label for chart index ${i}.`);
                    /* DEBUG END */
                }
            }

            // Update step size based on the actively tapped chart's data
            _state.stepSize = calculateStepSize(source);
            /* DEBUG START */
            console.log(`[DEBUG] onTapHandler: Updated keyboard navigation step size to ${_state.stepSize}ms.`);
            /* DEBUG END */

            // Update the frequency bar chart based on the new position
            _updateBarChart(snapped_x, _state.activeChartIndex, _state.activeAudioPosition, "Click");
            /* DEBUG START */
            console.log("[DEBUG] onTapHandler: Frequency bar chart updated based on tap event.");
            /* DEBUG END */

            // Send a seek command to Python to update the audio handler's position
            _sendSeekCommand(snapped_x);
            /* DEBUG START */
            console.log("[DEBUG] onTapHandler: Seek command sent to Python.");
            /* DEBUG END */

            return true;
        } catch (error) { console.error("[DEBUG] Error handling tap:", error); return false; }
    }

    function onHoverHandler(hoverLines, hoverLabels, cb_data, chart_index) { // Now accepts chart_index and labels
        /* DEBUG START */
        console.log(`[DEBUG] onHoverHandler: Hover event received for chart_index: ${chart_index}. Geometry: x=${cb_data.geometry?.x}, y=${cb_data.geometry?.y}.`);
        /* DEBUG END */
        try {
            // Check if geometry data exists from the event
            const geometry = cb_data.geometry;
            if (!geometry || !Number.isFinite(geometry.x)) {
                /* DEBUG START */
                console.log("[DEBUG] onHoverHandler: Invalid geometry or x-coordinate. Hiding hover lines and restoring bar chart to click position.");
                /* DEBUG END */
                //when not over a valid chart, the label is attached to the tapline
                _updateTapLinePositions(_state.verticalLinePosition);
                hoverLines.forEach(line => { if (line) line.visible = false; });

                // If geometry is invalid, reset lastHoverX so next valid hover isn't skipped
                _state.lastHoverX = null;
                // Restore frequency bar to the last clicked position if mouse leaves charts
                if (_state.verticalLinePosition !== null) {
                    const activePosForRestore = _state.isPlaying ? _state.activeAudioPosition : null;
                    const activeIndexForRestore = _state.isPlaying ? null : _state.activeChartIndex;
                    _updateBarChart(_state.verticalLinePosition, activeIndexForRestore, activePosForRestore, "Click Line");
                    /* DEBUG START */
                    console.log(`[DEBUG] onHoverHandler: Restored bar chart to click position ${_state.verticalLinePosition}ms.`);
                    /* DEBUG END */
                } else if (_models.barChart?.title) {
                    _models.barChart.title.text = `Frequency Slice`; // Reset title only
                    _models.barSource.data = { 'levels': [], 'frequency_labels': [] }; _models.barXRange.factors = []; _models.barSource.change.emit();
                    /* DEBUG START */
                    console.log("[DEBUG] onHoverHandler: No click position, cleared bar chart.");
                    /* DEBUG END */
                }
                return false;
            }

            //debounce hover events
            if (_state.lastHoverX === geometry.x) {
                /* DEBUG START */
                console.log(`[DEBUG] onHoverHandler: Debouncing hover event at x=${geometry.x}.`);
                /* DEBUG END */
                return true;
            }

            const hoveredX = geometry.x;
            _state.lastHoverX = hoveredX;
            /* DEBUG START */
            console.log(`[DEBUG] onHoverHandler: Processing hover at X: ${hoveredX}ms.`);
            /* DEBUG END */

            // Update all hover lines (the grey vertical guides)
            if (hoverLines && Array.isArray(hoverLines)) {
                hoverLines.forEach(line => { if (line) line.location = hoveredX, line.visible = true; });
                /* DEBUG START */
                console.log("[DEBUG] onHoverHandler: All hover lines updated and visible.");
                /* DEBUG END */
            }

            // Directly use the chart_index passed from the specific callback
            const hoveredChartIndex = chart_index;
            const hoveredChart = _models.charts[hoveredChartIndex];
            /* DEBUG START */
            console.log(`[DEBUG] onHoverHandler: Hovered chart index: ${hoveredChartIndex}, Chart name: ${hoveredChart?.name}.`);
            /* DEBUG END */

            if (hoveredChart && hoveredChartIndex !== -1) {
                const chartName = hoveredChart.name || '';
                // Only update the bar chart for time-series charts (overview/log)
                //const isLineChart = chartName.toLowerCase().includes('_overview') || chartName.toLowerCase().includes('_log');
                const isLineChart = true; // This line seems to force it to always be true regardless of name.

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
                            /* DEBUG START */
                            console.log(`[DEBUG] onHoverHandler: Hover label for chart '${chartName}' updated to visible with text for snapped X: ${snappedX}ms.`);
                            /* DEBUG END */
                        } else {
                            labelModel.visible = false;
                            /* DEBUG START */
                            console.log(`[DEBUG] onHoverHandler: No closest data point for hover label for chart '${chartName}'. Hiding label.`);
                            /* DEBUG END */
                        }
                    } else {
                        /* DEBUG START */
                        console.warn(`[DEBUG] onHoverHandler: Missing labelModel, source, or source.data.Datetime for chart '${chartName}'. Cannot update hover label.`);
                        /* DEBUG END */
                    }
                    // --- End of label logic ---

                    // Pass the correct chart index to the bar chart updater
                    _updateBarChart(hoveredX, hoveredChartIndex, activePosForHover, `Hover: ${chartName}`);
                    /* DEBUG START */
                    console.log("[DEBUG] onHoverHandler: Bar chart updated based on hover event.");
                    /* DEBUG END */
                } else {
                    /* DEBUG START */
                    console.log(`[DEBUG] onHoverHandler: Chart '${chartName}' is not a line chart. Skipping bar chart update.`);
                    /* DEBUG END */
                }
            }
            return true;
        } catch (error) {
            console.error("[DEBUG] Error handling hover:", error);
            return false;
        }
    }

    function onZoomHandler(cb_obj, master_range) {
        /* DEBUG START */
        console.log("[DEBUG] onZoomHandler: Zoom event triggered.");
        // console.log("[DEBUG] Zoom event cb_obj:", cb_obj); // Can be very verbose
        // console.log("[DEBUG] Zoom event master_range:", master_range); // Can be very verbose
        /* DEBUG END */
    }

    // --- Module Exports ---
    return {
        // Core
        init: initializeApp,
        // State Access
        getState: function () {
            /* DEBUG START */
            console.log("[DEBUG] getState: Returning a deep copy of the internal state.");
            /* DEBUG END */
            return JSON.parse(JSON.stringify(_state));
        },
        getModelsInfo: function () {
            /* DEBUG START */
            console.log("[DEBUG] getModelsInfo: Returning basic info about internal models.");
            /* DEBUG END */
            /* ... simplified ... */ return { /* basic info */ };
        },
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
        //chart control
        handleCombinedChartToggle: handleCombinedChartToggle,
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
        selfCheck: function () {
            /* DEBUG START */
            console.log("[DEBUG] selfCheck: Performing a simple self-check.");
            // Add more detailed checks here if needed for debugging specific issues
            /* DEBUG END */
            return true;
        }
    };
})();

// --- Global Exposure for Bokeh CustomJS Callbacks ---
window.interactions = window.NoiseSurveyApp.interactions;
window.NoiseFrequency = window.NoiseSurveyApp.frequency;
/* DEBUG START */
console.log("[DEBUG] Global exposure for 'interactions' and 'NoiseFrequency' namespaces set.");
/* DEBUG END */


// Function called by Python timer during playback
window.synchronizePlaybackPosition = function (ms) {
    /* DEBUG START */
    console.log(`[DEBUG] Global synchronizePlaybackPosition wrapper called with ms=${ms}.`);
    /* DEBUG END */
    if (typeof ms === 'number' && !isNaN(ms)) {
        if (window.NoiseSurveyApp?.synchronizePlaybackPosition) {
            const result = window.NoiseSurveyApp.synchronizePlaybackPosition(ms);
            /* DEBUG START */
            console.log(`[DEBUG] NoiseSurveyApp.synchronizePlaybackPosition returned ${result}.`);
            /* DEBUG END */
            return result;
        } else {
            console.warn("[DEBUG] NoiseSurveyApp.synchronizePlaybackPosition not available. Cannot synchronize playback.");
            return false;
        }
    } else {
        console.warn(`[DEBUG] Global synchronizePlaybackPosition called with invalid value: ${ms}.`);
        return false;
    }
};

// Function called by Bokeh TapTool
window.handleTap = function (cb_obj, chartModels, clickLineModels, labelModels, sourcesDict) {
    /* DEBUG START */
    console.log(`[DEBUG] Global handleTap wrapper called for cb_obj.origin.id=${cb_obj?.origin?.id}.`);
    /* DEBUG END */
    if (window.NoiseSurveyApp?.interactions?.onTap) {
        // Pass all arguments through
        const result = window.NoiseSurveyApp.interactions.onTap(cb_obj, chartModels, clickLineModels, labelModels, sourcesDict);
        /* DEBUG START */
        console.log(`[DEBUG] NoiseSurveyApp.interactions.onTap returned ${result}.`);
        /* DEBUG END */
        return result;
    } else {
        console.warn("[DEBUG] NoiseSurveyApp.interactions.onTap not available. Cannot handle tap event.");
        return false;
    }
};

// Function called by Bokeh HoverTool on main charts
window.handleHover = function (hoverLines, cb_data, chart_index) {
    console.log("[DEBUG] Global handleHover wrapper called with chart_index:", chart_index);
    if (window.NoiseSurveyApp?.interactions?.handleHover) {
        const result = window.NoiseSurveyApp.interactions.handleHover(hoverLines, cb_data, chart_index);
        /* DEBUG START */
        console.log(`[DEBUG] NoiseSurveyApp.interactions.handleHover returned ${result}.`);
        /* DEBUG END */
        return result;
    } else {
        console.warn("[DEBUG] NoiseSurveyApp.interactions.handleHover not available. Cannot handle hover event.");
        return false;
    }
};

// Function called by Bokeh HoverTool on spectrograms
window.handleSpectrogramHover = function (cb_data, hover_div, bar_source, bar_x_range, position_name, times_array, freqs_array, freq_labels_array, levels_matrix, levels_flat_array, fig_x_range) {
    /* DEBUG START */
    console.log(`[DEBUG] Global handleSpectrogramHover wrapper called for position '${position_name}'.`);
    /* DEBUG END */
    if (window.NoiseSurveyApp?.frequency?.handleSpectrogramHover) {
        const result = window.NoiseSurveyApp.frequency.handleSpectrogramHover(cb_data, hover_div, bar_source, bar_x_range, position_name, times_array, freqs_array, freq_labels_array, levels_matrix, levels_flat_array, fig_x_range);
        /* DEBUG START */
        console.log(`[DEBUG] NoiseSurveyApp.frequency.handleSpectrogramHover returned ${result}.`);
        /* DEBUG END */
        return result;
    } else {
        console.warn("[DEBUG] NoiseSurveyApp.frequency.handleSpectrogramHover not available. Cannot handle spectrogram hover event.");
        return false;
    }
};

// Function called by Parameter Select widget
window.handleParameterChange = function (param) {
    /* DEBUG START */
    console.log(`[DEBUG] Global handleParameterChange wrapper called with param='${param}'.`);
    /* DEBUG END */
    if (window.NoiseSurveyApp?.handleParameterChange) {
        const result = window.NoiseSurveyApp.handleParameterChange(param);
        /* DEBUG START */
        console.log(`[DEBUG] NoiseSurveyApp.handleParameterChange returned ${result}.`);
        /* DEBUG END */
        return result;
    } else {
        console.warn("[DEBUG] NoiseSurveyApp.handleParameterChange not available. Cannot handle parameter change.");
        return false;
    }
};

// Function Called by Position Play Button CustomJS
window.handlePositionPlayClick = function (positionName) {
    /* DEBUG START */
    console.log(`[DEBUG] Global handlePositionPlayClick wrapper called for positionName='${positionName}'.`);
    /* DEBUG END */
    if (typeof positionName === 'string') {
        if (window.NoiseSurveyApp?.handlePositionPlayClick) {
            const result = window.NoiseSurveyApp.handlePositionPlayClick(positionName);
            /* DEBUG START */
            console.log(`[DEBUG] NoiseSurveyApp.handlePositionPlayClick returned ${result}.`);
            /* DEBUG END */
            return result;
        } else {
            console.warn("[DEBUG] NoiseSurveyApp.handlePositionPlayClick not available. Cannot handle position play click.");
            return false;
        }
    } else {
        console.warn(`[DEBUG] Global handlePositionPlayClick called with invalid value: ${positionName}.`);
        return false;
    }
};

// Global Function Called by Python on Playback Stop (EOF/Error)
window.notifyPlaybackStopped = function () {
    /* DEBUG START */
    console.log("[DEBUG] Global notifyPlaybackStopped wrapper called.");
    /* DEBUG END */
    if (window.NoiseSurveyApp?.notifyPlaybackStopped) {
        const result = window.NoiseSurveyApp.notifyPlaybackStopped();
        /* DEBUG START */
        console.log(`[DEBUG] NoiseSurveyApp.notifyPlaybackStopped returned ${result}.`);
        /* DEBUG END */
        return result;
    } else {
        console.warn("[DEBUG] NoiseSurveyApp.notifyPlaybackStopped not available. Cannot notify playback stopped.");
        return false;
    }
};


// Deprecated Global Fallbacks
window.updateTapLinePositions = function (ms) { console.warn("[DEBUG] Deprecated global function 'updateTapLinePositions' called. Please use NoiseSurveyApp.updateTapLinePosition(ms) instead."); };
window.sendSeekCommand = function (ms) { console.warn("[DEBUG] Deprecated global function 'sendSeekCommand' called. Please use NoiseSurveyApp.interactions.sendSeekCommand(ms) instead."); };


console.log("[DEBUG] app.js loaded and NoiseSurveyApp object created (v3.3 - Refactored Position Play).");