/** Time-series slicing and display metadata. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    app.processing = app.processing || {};
    const { calculateSharedLogDisplayThreshold, cloneDataColumns, applyDatetimeOffset, createDisplayMetadata } = app.processing;

    function updateActiveLineChartData(position, viewState, dataCache, models, positionOffsetMs = 0, spectralDetails = null) {
        try {
            if (!dataCache.activeLineData) {
                dataCache.activeLineData = {};
            }

            const viewType = viewState.globalViewType;
            const sourceData = models.timeSeriesSources[position];
            const overviewData = sourceData?.overview?.data;
            const logData = sourceData?.log?.data;
            const hasLogData = logData && logData.Datetime && logData.Datetime.length > 0;
            // Whether log data exists on disk (even if not yet lazy-loaded)
            const logDataExists = models.positionHasLogData?.[position] ?? hasLogData;

            let displayDetails = createDisplayMetadata({
                type: 'overview',
                reason: ' (Overview - Enable Log View for detail)',
                statusCode: 'overview_selected',
                statusLabel: logDataExists ? 'Overview selected' : 'Overview data only',
                requestedViewType: viewType,
                logDataExists,
            });

            const viewportMin = Number(viewState.viewport?.min);
            const viewportMax = Number(viewState.viewport?.max);
            const effectiveMin = Number.isFinite(viewportMin) ? viewportMin - positionOffsetMs : viewportMin;
            const effectiveMax = Number.isFinite(viewportMax) ? viewportMax - positionOffsetMs : viewportMax;

            let nextActiveLine = null;
            const shouldSyncLineToSpectrogramOverview = viewType === 'log'
                && spectralDetails
                && spectralDetails.requestedViewType === 'log'
                && spectralDetails.type === 'overview'
                && (
                    spectralDetails.isLoading
                    || spectralDetails.statusCode === 'edge_guard'
                    || spectralDetails.statusCode === 'parameter_sync'
                );

            if (viewType === 'log') {
                if (shouldSyncLineToSpectrogramOverview) {
                    const overviewClone = cloneDataColumns(overviewData || {});
                    applyDatetimeOffset(overviewClone, positionOffsetMs);
                    nextActiveLine = overviewClone;
                    displayDetails = createDisplayMetadata({
                        type: 'overview',
                        reason: spectralDetails.reason || ' (Overview - Waiting for spectrogram log data...)',
                        statusCode: spectralDetails.statusCode || 'loading_log',
                        statusLabel: spectralDetails.statusLabel || 'Waiting for log spectrogram',
                        requestedViewType: viewType,
                        logDataExists,
                        isLoading: Boolean(spectralDetails.isLoading),
                        requiresZoom: Boolean(spectralDetails.requiresZoom),
                        coverageRatio: spectralDetails.coverageRatio,
                        centeredChunkReady: spectralDetails.centeredChunkReady,
                        parameterMismatch: Boolean(spectralDetails.parameterMismatch),
                    });
                } else if (hasLogData) {
                    // Check viewport width against dynamic threshold (in milliseconds)
                    const logViewThresholdSeconds = calculateSharedLogDisplayThreshold(models, viewState);
                    const viewportWidthMs = Number.isFinite(effectiveMax) && Number.isFinite(effectiveMin)
                        ? effectiveMax - effectiveMin : Infinity;
                    const viewportWidthSeconds = viewportWidthMs / 1000;
                    const viewportTooLarge = viewportWidthSeconds > logViewThresholdSeconds;

                    if (viewportTooLarge) {
                        // Viewport too large for log data - use overview
                        const overviewClone = cloneDataColumns(overviewData || {});
                        applyDatetimeOffset(overviewClone, positionOffsetMs);
                        nextActiveLine = overviewClone;
                        displayDetails = createDisplayMetadata({
                            type: 'overview',
                            reason: ' - Overview - zoom in for Log',
                            statusCode: 'zoom_required',
                            statusLabel: 'Zoom in for log data',
                            requestedViewType: viewType,
                            logDataExists,
                            requiresZoom: true,
                        });
                    } else {
                        // Binary search: this runs per position on every heavy update,
                        // over a streamed log window that can hold tens of thousands of
                        // points.
                        const startIndex = app.utils.firstIndexAtOrAfter(logData.Datetime, effectiveMin);
                        const endIndex = app.utils.lastIndexAtOrBefore(logData.Datetime, effectiveMax);
                        const hasViewportOverlap = startIndex !== -1 && endIndex !== -1 && endIndex >= startIndex;
                        if (!hasViewportOverlap) {
                            // Log source has data, but current viewport is outside the streamed chunk.
                            const overviewClone = cloneDataColumns(overviewData || {});
                            applyDatetimeOffset(overviewClone, positionOffsetMs);
                            nextActiveLine = overviewClone;
                            displayDetails = createDisplayMetadata({
                                type: 'overview',
                                reason: ' (Overview - Streaming Log Data...)',
                                statusCode: 'loading_log',
                                statusLabel: 'Loading log data',
                                requestedViewType: viewType,
                                logDataExists,
                                isLoading: true,
                            });
                        } else {
                            // Log view: keep full-resolution data and only slice by viewport.
                            const sliceStart = startIndex;
                            const sliceEnd = endIndex + 1;
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
                            nextActiveLine = chunk;
                            displayDetails = createDisplayMetadata({
                                type: 'log',
                                reason: ' (Log Data)',
                                statusCode: 'log_displayed',
                                statusLabel: 'Showing log data',
                                requestedViewType: viewType,
                                logDataExists,
                            });
                        }
                    }
                } else {
                    // Log view is active, but no log data exists for this position
                    const overviewClone = cloneDataColumns(overviewData || {});
                    applyDatetimeOffset(overviewClone, positionOffsetMs);
                    nextActiveLine = overviewClone;
                    const logViewThresholdSeconds = calculateSharedLogDisplayThreshold(models, viewState);
                    const viewportWidthMs = Number.isFinite(effectiveMax) && Number.isFinite(effectiveMin)
                        ? effectiveMax - effectiveMin : Infinity;
                    const viewportWidthSeconds = viewportWidthMs / 1000;
                    const viewportTooLarge = viewportWidthSeconds > logViewThresholdSeconds;
                    const pendingBecauseViewportTooLarge = logDataExists && viewportTooLarge;
                    displayDetails = createDisplayMetadata({
                        type: 'overview',
                        reason: logDataExists ? ' (Overview - Zoom in for Log Data)' : ' (Overview)',
                        statusCode: pendingBecauseViewportTooLarge ? 'zoom_required' : (logDataExists ? 'loading_log' : 'overview_only'),
                        statusLabel: pendingBecauseViewportTooLarge ? 'Zoom in for log data' : (logDataExists ? 'Waiting for log data' : 'Overview data only'),
                        requestedViewType: viewType,
                        logDataExists,
                        isLoading: logDataExists && !pendingBecauseViewportTooLarge,
                        requiresZoom: pendingBecauseViewportTooLarge,
                    });
                }
            } else {
                // Overview view is explicitly active
                const overviewClone = cloneDataColumns(overviewData || {});
                applyDatetimeOffset(overviewClone, positionOffsetMs);
                nextActiveLine = overviewClone;
                displayDetails = createDisplayMetadata({
                    type: 'overview',
                    reason: logDataExists ? ' (Overview - Enable Log View for detail)' : ' (Overview)',
                    statusCode: 'overview_selected',
                    statusLabel: logDataExists ? 'Overview selected' : 'Overview data only',
                    requestedViewType: viewType,
                    logDataExists,
                });
            }

            if (nextActiveLine) {
                dataCache.activeLineData[position] = {
                    ...nextActiveLine,
                    dataViewType: displayDetails.type,
                    displayDetails,
                    _offsetMs: positionOffsetMs
                };
            } else {
                dataCache.activeLineData[position] = {
                    dataViewType: 'none',
                    displayDetails
                };
            }

            return displayDetails;
        }
        catch (error) {
            console.error(" [data-processors.js - updateActiveLineChartData()]", error);
            return { type: 'unknown', reason: '' };
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


    Object.assign(app.processing, { updateActiveLineChartData });
})(window.NoiseSurveyApp);
