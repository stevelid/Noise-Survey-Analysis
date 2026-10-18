/** Processing orchestration; public interface preserved. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    app.processing = app.processing || {};
    const {
        isDebugEnabled, getChartOffsetMs, updateActiveLineChartData,
        updateActiveSpectralData, updateActiveFreqBarData, calculateLogViewThreshold
    } = app.processing;

    function updateActiveData(viewState, dataCache, models) {
        const displayDetailsByPosition = {};

        viewState.availablePositions.forEach(position => {
            const tsChartName = `figure_${position}_timeseries`;
            const specChartName = `figure_${position}_spectrogram`;

            // Only process data for charts that are currently visible
            if (viewState.chartVisibility[tsChartName] || viewState.chartVisibility[specChartName]) {
                const offsetMs = getChartOffsetMs(viewState, position);
                const spectralDetails = updateActiveSpectralData(position, viewState, dataCache, models, offsetMs);
                const lineDetails = updateActiveLineChartData(position, viewState, dataCache, models, offsetMs, spectralDetails);

                if (lineDetails || spectralDetails) {
                    displayDetailsByPosition[position] = {
                        ...(lineDetails ? { line: lineDetails } : {}),
                        ...(spectralDetails ? { spec: spectralDetails } : {})
                    };
                }
            }
        });

        return displayDetailsByPosition;
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

    function calculateStepSize(state, dataCache) { // Accept the full state object
        try {
            // Determine the focused position from the interaction state
            const positionId = state.interaction.tap.position || state.audio.activePositionId;
    
            if (!positionId) {
                if (isDebugEnabled()) {
                    console.debug("[DEBUG] Can't calculate step size - no active position.");
                }
                return;
            }

            const activeData = dataCache.activeLineData[positionId];

            if (!activeData || !activeData.Datetime || activeData.Datetime.length < 11) {
                if (isDebugEnabled()) {
                    console.debug(`[DEBUG] Can't calculate step size for '${positionId}' - no data or not enough data points.`);
                }
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
    app.data_processors = {
        updateActiveData: updateActiveData,
        updateActiveLineChartData: updateActiveLineChartData,
        updateActiveSpectralData: updateActiveSpectralData,
        updateActiveFreqBarData: updateActiveFreqBarData,
        calculateStepSize: calculateStepSize,
        calculateLogViewThreshold: calculateLogViewThreshold
    };

})(window.NoiseSurveyApp);
