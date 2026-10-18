/** Frequency-bar data selection. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    app.processing = app.processing || {};

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

            // Runs on every hover move and every audio status tick.
            const closestTimeIdx = app.utils.lastIndexAtOrBefore(activeSpectralData.times_ms, timestamp);
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
                    
                    const viewTypeLabel = activeSpectralData.dataViewType || 'None';
                    const normalizedType = viewTypeLabel === 'none' ? 'None' : viewTypeLabel;
                    dataCache.activeFreqBarData = {
                        levels: Array.from(barLevelsSlice).map(l => (l === null || isNaN(l)) ? 0 : l),
                        frequency_labels: activeSpectralData.frequency_labels.slice(bar_start_idx, bar_end_idx + 1),
                        sourceposition: position,
                        timestamp: timestamp,
                        setBy: setBy,
                        param: state.view.selectedParameter,
                        dataViewType: normalizedType
                    };
                    return;
                }
            }

            // --- Fallback: Use full frequency range if slicing config is missing or invalid ---
            const freqDataSlice = new Float32Array(activeSpectralData.n_freqs);
            for (let i = 0; i < activeSpectralData.n_freqs; i++) {
                freqDataSlice[i] = activeSpectralData.levels_flat_transposed[i * activeSpectralData.n_times + closestTimeIdx];
            }

            const viewTypeLabel = activeSpectralData.dataViewType || 'None';
            const normalizedType = viewTypeLabel === 'none' ? 'None' : viewTypeLabel;
            dataCache.activeFreqBarData = {
                levels: Array.from(freqDataSlice).map(l => (l === null || isNaN(l)) ? 0 : l),
                frequency_labels: activeSpectralData.frequency_labels,
                sourceposition: position,
                timestamp: timestamp,
                setBy: setBy,
                param: state.view.selectedParameter,
                dataViewType: normalizedType
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


    Object.assign(app.processing, { updateActiveFreqBarData });
})(window.NoiseSurveyApp);
