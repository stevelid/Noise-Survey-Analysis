// noise_survey_analysis/static/js/data-processors.js

/**
 * @fileoverview Contains data processing and transformation functions for the Noise Survey app.
 * These functions are responsible for the "heavy lifting" of data manipulation. They take
 * the core application state (e.g., current viewport, selected parameters) and the raw
 * source data, then compute the derived "active" data slices that are ready to be
 * rendered by the UI. This isolates complex calculations from state management and rendering.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const MAX_LINE_POINTS_TO_RENDER = 5000;
    const MAX_SPECTRAL_POINTS_TO_RENDER = 5000;

    const _models = app.models;

    function cloneDataColumns(source) {
        if (!source || typeof source !== 'object') {
            return {};
        }
        const clone = {};
        for (const key in source) {
            if (!Object.prototype.hasOwnProperty.call(source, key)) continue;
            const column = source[key];
            if (Array.isArray(column)) {
                clone[key] = column.slice();
            } else if (column && typeof column.slice === 'function') {
                clone[key] = column.slice();
            } else {
                clone[key] = column;
            }
        }
        return clone;
    }

    function createOffsetArray(source, offsetMs) {
        if (!Number.isFinite(offsetMs) || !source || typeof source.length !== 'number') {
            return Array.isArray(source) ? source.slice() : (source && typeof source.slice === 'function' ? source.slice() : []);
        }
        const length = source.length;
        const adjusted = new Array(length);
        for (let i = 0; i < length; i++) {
            const value = Number(source[i]);
            adjusted[i] = Number.isFinite(value) ? value + offsetMs : value;
        }
        return adjusted;
    }

    function applyDatetimeOffset(data, offsetMs) {
        if (!data || !data.Datetime) {
            return data;
        }
        const adjusted = createOffsetArray(data.Datetime, offsetMs);
        data.Datetime = adjusted;
        return data;
    }

    function getChartOffsetMs(viewState, position) {
        if (!viewState || !position) {
            return 0;
        }
        const raw = Number(viewState.positionChartOffsets?.[position]);
        return Number.isFinite(raw) ? raw : 0;
    }

    function applySpectrogramReplacementOffset(replacement, offsetMs) {
        if (!replacement || typeof replacement !== 'object') {
            return replacement;
        }
        const next = { ...replacement };
        if (Array.isArray(replacement.x)) {
            next.x = replacement.x.map(value => {
                const numeric = Number(value);
                return Number.isFinite(numeric) ? numeric + offsetMs : value;
            });
        }
        if (Array.isArray(replacement.times_ms) || (replacement.times_ms && typeof replacement.times_ms.length === 'number')) {
            next.times_ms = createOffsetArray(replacement.times_ms, offsetMs);
        }
        return next;
    }


    /**
     * _updateActiveData()
     * 
     * Updates the active data for all visible charts. This involves:
     * 
     * 1. Updating the active line chart data for each visible chart.
     * 2. Updating the active spectrogram data for each visible chart.
     * 3. Determining the context (position and timestamp) for the frequency bar
     *    from the currently active interaction (hover or tap), and calling
     *    _updateActiveFreqBarData() to update the bar chart's data.
     */
    function updateActiveData(viewState, dataCache, models) {
        viewState.availablePositions.forEach(position => {
            const tsChartName = `figure_${position}_timeseries`;
            const specChartName = `figure_${position}_spectrogram`;



            // Only process data for charts that are currently visible
            if (viewState.chartVisibility[tsChartName] || viewState.chartVisibility[specChartName]) {
                const offsetMs = getChartOffsetMs(viewState, position);
                updateActiveLineChartData(position, viewState, dataCache, models, offsetMs);
                updateActiveSpectralData(position, viewState, dataCache, models, offsetMs);
            }
        });

        // This function is now called from onStateChange, so we get the full state there.
        // We'll need to get the state inside this function for now.
        // updateActiveFreqBarData is now called from onStateChange, so this call is redundant.
        // const state = app.store.getState();
        // updateActiveFreqBarData(state, dataCache);
    }

    /**
     * Updates the active line chart data for a given position based on the view type.
     * 
     * This function determines whether to use 'overview' or 'log' data for the line chart 
     * based on the provided viewType and the current viewport. It updates the activeLineData 
     * in the state with the selected data and sets the display details for the position.
     * 
     * @param {string} position - The position identifier for which the line chart data is updated.
     * @param {string} viewType - The type of view ('overview' or 'log') to determine data selection.
     */
    function updateActiveLineChartData(position, viewState, dataCache, models, positionOffsetMs = 0) {
        try {
            const viewType = viewState.globalViewType;
            const sourceData = models.timeSeriesSources[position];
            const overviewData = sourceData?.overview?.data;
            const logData = sourceData?.log?.data;
            const hasLogData = logData && logData.Datetime && logData.Datetime.length > 0;

            let displayDetails = { type: 'overview', reason: ' (Overview)' }; // Default reason

            const viewportMin = Number(viewState.viewport?.min);
            const viewportMax = Number(viewState.viewport?.max);
            const effectiveMin = Number.isFinite(viewportMin) ? viewportMin - positionOffsetMs : viewportMin;
            const effectiveMax = Number.isFinite(viewportMax) ? viewportMax - positionOffsetMs : viewportMax;

            if (viewType === 'log') {
                if (hasLogData) {
                    const startIndex = logData.Datetime.findIndex(t => t >= effectiveMin);
                    const endIndex = logData.Datetime.findLastIndex(t => t <= effectiveMax);
                    const pointsInView = (startIndex !== -1 && endIndex !== -1) ? endIndex - startIndex : 0;

                    if (pointsInView > MAX_LINE_POINTS_TO_RENDER) {
                        // Log view is active, but user is too zoomed out
                        const overviewClone = cloneDataColumns(overviewData || {});
                        applyDatetimeOffset(overviewClone, positionOffsetMs);
                        dataCache.activeLineData[position] = overviewClone;
                        displayDetails = { type: 'overview', reason: ' - Zoom in for Log Data' };
                    } else {
                        // Happy path: Show a chunk of log data
                        const buffer = Math.floor(pointsInView * 0.5);
                        const sliceStart = Math.max(0, startIndex - buffer);
                        const sliceEnd = Math.min(logData.Datetime.length, endIndex + buffer + 1);
                        const chunk = {};
                        for (const key in logData) {
                            const column = logData[key];
                            if (column && typeof column.slice === 'function') {
                                chunk[key] = column.slice(sliceStart, sliceEnd);
                            } else if (Array.isArray(column)) {
                                chunk[key] = column.slice(sliceStart, sliceEnd);
                            } else {
                                chunk[key] = column;
                            }
                        }
                        applyDatetimeOffset(chunk, positionOffsetMs);
                        dataCache.activeLineData[position] = chunk;
                        displayDetails = { type: 'log', reason: ' (Log Data)' };
                    }
                } else {
                    // Log view is active, but no log data exists for this position
                    const overviewClone = cloneDataColumns(overviewData || {});
                    applyDatetimeOffset(overviewClone, positionOffsetMs);
                    dataCache.activeLineData[position] = overviewClone;
                    displayDetails = { type: 'overview', reason: ' (No Log Data Available)' };
                }
            } else {
                // Overview view is explicitly active
                const overviewClone = cloneDataColumns(overviewData || {});
                applyDatetimeOffset(overviewClone, positionOffsetMs);
                dataCache.activeLineData[position] = overviewClone;
                displayDetails = { type: 'overview', reason: ' (Overview)' };
            }

            if (!viewState.displayDetails[position]) {
                viewState.displayDetails[position] = {};
            }
            viewState.displayDetails[position].line = displayDetails;
        }
        catch (error) {
            console.error(" [data-processors.js - updateActiveLineChartData()]", error);
        }
    }

    /**
     * Updates the active spectrogram data for a given position based on the view type and parameter.
     * 
     * This function determines whether to use 'overview' or 'log' data for the spectrogram based on 
     * the provided viewType and the current viewport. It updates the activeSpectralData in the state 
     * with the selected data and sets the display details for the position.
     * 
     * @param {string} position - The position identifier for which the spectrogram data is updated.
     * @param {string} viewType - The type of view ('overview' or 'log') to determine data selection.
     * @param {string} parameter - The parameter to be displayed in the spectrogram.
     */
    function updateActiveSpectralData(position, viewState, dataCache, models, positionOffsetMs = 0) {
        try {
            const viewType = viewState.globalViewType;
            const parameter = viewState.selectedParameter;
            const positionGlyphData = models.preparedGlyphData[position];
            const overviewData = positionGlyphData?.overview?.prepared_params?.[parameter];
            const logData = positionGlyphData?.log?.prepared_params?.[parameter];
            const hasLogData = logData && logData.times_ms && logData.times_ms.length > 0;

            let finalDataToUse, finalGlyphData, displayReason;

            const offsetMs = positionOffsetMs;
            const viewportMin = Number(viewState.viewport?.min);
            const viewportMax = Number(viewState.viewport?.max);
            const effectiveMin = Number.isFinite(viewportMin) ? viewportMin - offsetMs : viewportMin;
            const effectiveMax = Number.isFinite(viewportMax) ? viewportMax - offsetMs : viewportMax;

            if (viewType === 'log') {
                if (hasLogData) {
                    const pointsInView = Math.floor((viewState.viewport.max - viewState.viewport.min) / logData.time_step);

                    if (pointsInView <= MAX_SPECTRAL_POINTS_TO_RENDER) {
                        // Happy Path: Show chunked LOG data
                        finalDataToUse = logData;
                        displayReason = ' (Log Data)'; // Explicitly label the log view

                        const { n_times, chunk_time_length, times_ms, time_step, levels_flat_transposed, n_freqs } = finalDataToUse;
                        let viewportCenter = Number.isFinite(effectiveMax) && Number.isFinite(effectiveMin)
                            ? (effectiveMax + effectiveMin) / 2
                            : times_ms[Math.max(0, Math.floor(n_times / 2))];
                        if (!Number.isFinite(viewportCenter)) {
                            viewportCenter = times_ms[Math.max(0, Math.floor(n_times / 2))];
                        }
                        const targetChunkStartTimeStamp = viewportCenter - (chunk_time_length * time_step / 2);

                        // A more robust way to find the index, defaulting to 0 if the view is before the data starts.
                        let chunkStartTimeIdx = times_ms.findIndex(t => t >= targetChunkStartTimeStamp);
                        if (chunkStartTimeIdx === -1) {
                            // If the view is past the end of the data, show the last possible chunk.
                            chunkStartTimeIdx = Math.max(0, n_times - chunk_time_length);
                        }

                        const chunk_image_full_freqs = _extractTimeChunkFromFlatData(levels_flat_transposed, n_freqs, n_times, chunkStartTimeIdx, chunk_time_length);

                        // Apply paint-on-canvas frequency slicing for spectrogram
                        finalGlyphData = tryApplySpectrogramSlice(finalDataToUse, chunk_image_full_freqs, chunkStartTimeIdx, position, dataCache, models);

                    } else {
                        // Log view active, but too zoomed out
                        finalDataToUse = overviewData;
                        displayReason = ' - Zoom in for Log Data';
                        const baseImage = finalDataToUse?.initial_glyph_data?.image?.[0];
                        finalGlyphData = tryApplySpectrogramSlice(finalDataToUse, baseImage, 0, position, dataCache, models);
                    }
                } else {
                    // Log view active, but no log data exists
                    finalDataToUse = overviewData;
                    displayReason = ' (No Log Data Available)';
                    const baseImage = finalDataToUse?.initial_glyph_data?.image?.[0];
                    finalGlyphData = tryApplySpectrogramSlice(finalDataToUse, baseImage, 0, position, dataCache, models);
                }
            } else {
                // Overview view is explicitly active
                finalDataToUse = overviewData;
                displayReason = ' (Overview)';
                const baseImage = finalDataToUse?.initial_glyph_data?.image?.[0];
                finalGlyphData = tryApplySpectrogramSlice(finalDataToUse, baseImage, 0, position, dataCache, models);
            }

            // --- Final state update ---
            if (finalGlyphData && finalDataToUse) {
                const adjustedReplacement = applySpectrogramReplacementOffset(finalGlyphData, offsetMs);
                const adjustedTimes = finalDataToUse.times_ms ? createOffsetArray(finalDataToUse.times_ms, offsetMs) : [];
                dataCache.activeSpectralData[position] = {
                    ...finalDataToUse,
                    times_ms: adjustedTimes,
                    source_replacement: adjustedReplacement
                };
            } else {
                // This case handles when overviewData was also null in one of the fallback paths.
                dataCache.activeSpectralData[position] = { source_replacement: null, reason: 'No Data Available', times_ms: [] };
                // If we ended up with no data, this reason overrides any previous one.
                displayReason = ' (No Data Available)';
            }
            if (!viewState.displayDetails[position]) {
                viewState.displayDetails[position] = {};
            }
            viewState.displayDetails[position].spec = { reason: displayReason };
        }
        catch (error) {
            console.error(" [data-processors.js - updateActiveSpectralData()]", error);
        }
    }

    function tryApplySpectrogramSlice(finalDataToUse, imageData, chunkStartTimeIdx, position, dataCache, models) {
        if (!finalDataToUse || !imageData) {
            return null;
        }
        try {
            return _applySpectrogramFreqSlicing(finalDataToUse, imageData, chunkStartTimeIdx, position, dataCache, models);
        }
        catch (error) {
            console.error(" [data-processors.js - tryApplySpectrogramSlice()]", error);
            return null;
        }
    }


    /**
     * Updates the active frequency bar data based on the current interaction context.
     * 
     * This function determines the context (position and timestamp) for the frequency bar
     * from the currently active interaction (hover or tap), and applies independent frequency
     * slicing for the bar chart's specific range.
     */
    function updateActiveFreqBarData(state, dataCache) {

        try {
            const { models } = app.registry; // Get models from registry
            const blankData = { levels: [], frequency_labels: [], sourceposition: '', timestamp: null, setBy: null, param: null };

            // --- Step 1: Determine the context and priority from the global state ---
            let position, timestamp, setBy;

            if (state.interaction.hover.isActive) {
                // Priority 1: Active hover
                position = state.interaction.hover.position;
                timestamp = state.interaction.hover.timestamp;
                setBy = 'hover';
            }
            else if (state.interaction.tap.isActive) {
                // Priority 2: Active tap (which may be driven by audio)
                position = state.interaction.tap.position;
                timestamp = state.interaction.tap.timestamp;
                setBy = state.audio.isPlaying && state.audio.activePositionId === position ? 'audio' : 'tap';
            }
            else {
                // No active interaction, so set to blank and exit
                dataCache.activeFreqBarData = blankData;
                return;
            }

            // If there's no valid context, exit
            if (!timestamp || !position) {
                dataCache.activeFreqBarData = blankData;
                return;
            }

            // --- Step 2: Fetch and process data based on the determined context ---
            const activeSpectralData = dataCache.activeSpectralData[position];
            if (!activeSpectralData?.times_ms?.length) {
                dataCache.activeFreqBarData = blankData;
                return;
            }

            const closestTimeIdx = activeSpectralData.times_ms.findLastIndex(time => time <= timestamp);
            if (closestTimeIdx === -1) {
                dataCache.activeFreqBarData = blankData;
                return;
            }

            // --- Step 3: Apply independent frequency slicing for bar chart ---
            const barFreqRange = models?.config?.freq_bar_freq_range_hz;
            if (barFreqRange && activeSpectralData.frequencies_hz) {
                const [barMinHz, barMaxHz] = barFreqRange;
                const bar_start_idx = activeSpectralData.frequencies_hz.findIndex(f => f >= barMinHz);
                const bar_end_idx = activeSpectralData.frequencies_hz.findLastIndex(f => f <= barMaxHz);
                
                if (bar_start_idx !== -1 && bar_end_idx !== -1) {
                    // Extract levels for the bar chart's frequency range
                    const barFreqCount = (bar_end_idx - bar_start_idx) + 1;
                    const barLevelsSlice = new Float32Array(barFreqCount);
                    
                    for (let i = 0; i < barFreqCount; i++) {
                        const globalFreqIdx = bar_start_idx + i;
                        barLevelsSlice[i] = activeSpectralData.levels_flat_transposed[globalFreqIdx * activeSpectralData.n_times + closestTimeIdx];
                    }
                    
                    dataCache.activeFreqBarData = {
                        levels: Array.from(barLevelsSlice).map(l => (l === null || isNaN(l)) ? 0 : l),
                        frequency_labels: activeSpectralData.frequency_labels.slice(bar_start_idx, bar_end_idx + 1),
                        sourceposition: position,
                        timestamp: timestamp,
                        setBy: setBy,
                        param: state.view.selectedParameter,
                        dataViewType: state.view.displayDetails[position]?.spec?.type || 'None'
                    };
                    return;
                }
            }
            
            // --- Fallback: Use full frequency range if slicing config is missing or invalid ---
            const freqDataSlice = new Float32Array(activeSpectralData.n_freqs);
            for (let i = 0; i < activeSpectralData.n_freqs; i++) {
                freqDataSlice[i] = activeSpectralData.levels_flat_transposed[i * activeSpectralData.n_times + closestTimeIdx];
            }

            dataCache.activeFreqBarData = {
                levels: Array.from(freqDataSlice).map(l => (l === null || isNaN(l)) ? 0 : l),
                frequency_labels: activeSpectralData.frequency_labels,
                sourceposition: position,
                timestamp: timestamp,
                setBy: setBy,
                param: state.view.selectedParameter,
                dataViewType: state.view.displayDetails[position]?.spec?.type || 'None'
            };
        }
        catch (error) {
            console.error(" [data-processors.js - updateActiveFreqBarData()]", error);
        }
    }

    /**
     * Calculates an appropriate keyboard navigation step size based on the total
     * time duration of the currently active dataset for the position with focus.
     * The position with focus is determined by checking audio state first, then tap state.
     */
    function calculateStepSize(state, dataCache) { // Accept the full state object
        try {
            // Determine the focused position from the interaction state
            const positionId = state.interaction.tap.position || state.audio.activePositionId;
    
            if (!positionId) {
                console.warn("[DEBUG] Can't calculate step size - no active position.");
                return;
            }
    
            const activeData = dataCache.activeLineData[positionId];
    
            if (!activeData || !activeData.Datetime || activeData.Datetime.length < 11) {
                console.warn(`[DEBUG] Can't calculate step size for '${positionId}' - no data or not enough data points.`);
                return;
            }
    
            // --- The rest of the function remains the same ---
            let newStep = (activeData.Datetime[10] - activeData.Datetime[5]) / 5;
    
            const oneSecond = 1000;
            const oneHour = 3600000;
            newStep = Math.max(oneSecond, Math.min(newStep, oneHour));
            
            // Return the calculated value
            return newStep;
    
        } catch (error) {
            console.error(" [data-processors.js - calculateStepSize()]", error);
        }
    }

    function _extractTimeChunkFromFlatData(flatData, n_freqs, n_times_total, start_time_idx, chunk_time_length) {
        try {
            const typedFlatData = (flatData instanceof Float32Array) ? flatData : new Float32Array(flatData);
            const chunk_data = new Float32Array(n_freqs * chunk_time_length);
            const end_time_idx = Math.min(start_time_idx + chunk_time_length, n_times_total);
            const actual_slice_width = end_time_idx - start_time_idx;
            for (let i = 0; i < n_freqs; i++) {
                const row_offset = i * n_times_total;
                const slice_start_in_flat_array = row_offset + start_time_idx;
                const source_row_start = slice_start_in_flat_array;
                const source_row_end = slice_start_in_flat_array + actual_slice_width;
                const row_slice = typedFlatData.subarray(source_row_start, source_row_end);
                chunk_data.set(row_slice, i * chunk_time_length);
            }
            return chunk_data;
        }
        catch (error) {
            console.error(" [data-processors.js - _extractTimeChunkFromFlatData()]", error);
        }
    }

    /**
     * Apply paint-on-canvas frequency slicing for spectrogram display.
     */
    function _applySpectrogramFreqSlicing(finalDataToUse, chunk_image_full_freqs, chunkStartTimeIdx, position, dataCache, models) {
        try {
            if (!finalDataToUse || !finalDataToUse.frequencies_hz || !models.config) {
                return {
                    ...finalDataToUse.initial_glyph_data,
                    image: [chunk_image_full_freqs],
                    x: [finalDataToUse.times_ms[chunkStartTimeIdx]],
                    dw: [finalDataToUse.chunk_time_length * finalDataToUse.time_step],
                    times_ms: finalDataToUse.times_ms.slice(chunkStartTimeIdx, chunkStartTimeIdx + finalDataToUse.chunk_time_length),
                };
            }

            // Get frequency range and find indices
            const [minHz, maxHz] = models.config.spectrogram_freq_range_hz;
            const all_freqs_hz = finalDataToUse.frequencies_hz;
            
            const start_freq_index = all_freqs_hz.findIndex(f => f >= minHz);
            const end_freq_index = all_freqs_hz.findLastIndex(f => f <= maxHz);
            
            
            if (start_freq_index === -1 || end_freq_index === -1) {
                // Handle edge case - no frequencies in range, show all
                console.warn(`No frequencies found in spectrogram range ${minHz}-${maxHz} Hz for position ${position}`);
                return {
                    ...finalDataToUse.initial_glyph_data,
                    image: [chunk_image_full_freqs],
                    x: [finalDataToUse.times_ms[chunkStartTimeIdx]],
                    dw: [finalDataToUse.chunk_time_length * finalDataToUse.time_step],
                    times_ms: finalDataToUse.times_ms.slice(chunkStartTimeIdx, chunkStartTimeIdx + finalDataToUse.chunk_time_length),
                };
            }
            
            const visible_n_freqs = (end_freq_index - start_freq_index) + 1;
            
            // CRITICAL: Maintain original buffer size to preserve Bokeh datasource structure
            if (!dataCache._spectrogramCanvasBuffers) dataCache._spectrogramCanvasBuffers = {};
            const bufferKey = `${position}_original_${chunk_image_full_freqs.length}`;
            
            if (!dataCache._spectrogramCanvasBuffers[bufferKey]) {
                dataCache._spectrogramCanvasBuffers[bufferKey] = new Float32Array(chunk_image_full_freqs.length);
            }
            
            const canvasBuffer = dataCache._spectrogramCanvasBuffers[bufferKey];
            const transparent_val = finalDataToUse.min_val - 100;
            
            // Clear entire buffer, then copy only visible frequencies to their original positions
            canvasBuffer.fill(transparent_val);
            
            for (let freq_idx = start_freq_index; freq_idx < start_freq_index + visible_n_freqs; freq_idx++) {
                const source_row_start = freq_idx * finalDataToUse.chunk_time_length;
                const source_row_end = source_row_start + finalDataToUse.chunk_time_length;
                
                if (source_row_end > chunk_image_full_freqs.length) {
                    console.error(`[DEBUG] Source overflow! freq_idx: ${freq_idx}, source_row_end: ${source_row_end}, source_length: ${chunk_image_full_freqs.length}`);
                    break;
                }
                
                // Copy visible frequency band to the same position in the buffer (preserves original layout)
                for (let i = 0; i < finalDataToUse.chunk_time_length; i++) {
                    canvasBuffer[source_row_start + i] = chunk_image_full_freqs[source_row_start + i];
                }
            }
            
            const result = {
                ...finalDataToUse.initial_glyph_data,
                image: [canvasBuffer],  // Same size buffer as original
                x: [finalDataToUse.times_ms[chunkStartTimeIdx]],
                dw: [finalDataToUse.chunk_time_length * finalDataToUse.time_step],
                // CRITICAL: Use original glyph positioning to match full image data layout
                y: finalDataToUse.initial_glyph_data.y,      // Original position (matches full image)
                dh: finalDataToUse.initial_glyph_data.dh,    // Original height (matches full image)
                times_ms: finalDataToUse.times_ms.slice(chunkStartTimeIdx, chunkStartTimeIdx + finalDataToUse.chunk_time_length),
                y_range_start: start_freq_index - 0.5,
                y_range_end: end_freq_index + 0.5,
                visible_frequency_labels: finalDataToUse.frequency_labels.slice(start_freq_index, end_freq_index + 1),
                visible_freq_indices: Array.from({length: visible_n_freqs}, (_, i) => start_freq_index + i)
            };
            
            return result;
        }
        catch (error) {
            console.error(" [data-processors.js - _applySpectrogramFreqSlicing()]", error);
            // Fallback to original behavior on error
            return {
                ...finalDataToUse.initial_glyph_data,
                image: [chunk_image_full_freqs],
                x: [finalDataToUse.times_ms[chunkStartTimeIdx]],
                dw: [finalDataToUse.chunk_time_length * finalDataToUse.time_step],
                times_ms: finalDataToUse.times_ms.slice(chunkStartTimeIdx, chunkStartTimeIdx + finalDataToUse.chunk_time_length),
            };
        }
    }

    app.data_processors = {
        updateActiveData: updateActiveData,
        updateActiveLineChartData: updateActiveLineChartData,
        updateActiveSpectralData: updateActiveSpectralData,
        updateActiveFreqBarData: updateActiveFreqBarData,
        calculateStepSize: calculateStepSize
    };

})(window.NoiseSurveyApp);