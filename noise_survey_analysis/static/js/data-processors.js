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

    const MAX_LOG_SPECTROGRAM_TIME_POINTS = 30000;

    function getDebugPosition() {
        try {
            return localStorage.getItem('nsa_debug_position') || '';
        } catch (e) {
            return '';
        }
    }

    function isDebugEnabled() {
        try {
            return localStorage.getItem('nsa_debug') === '1';
        } catch (e) {
            return false;
        }
    }

    // Log view threshold default:
    // min(1 hour, 10 overview steps, 360 log steps)
    // capped by backend hard limit.

    const _models = app.models;

    // Utility for handling spectrogram matrix operations
    const MatrixUtils = {
        /**
         * Generates a 2D image array from flat level data.
         * Bokeh 3.x Image glyph expects a 2D array (Array of TypedArrays).
         * 
         * @param {Array|Float32Array} levelsFlat - Flattened spectrogram data (n_freqs * n_times)
         * @param {number} nFreqs - Number of frequency bins (rows)
         * @param {number} nTimes - Number of time steps (cols)
         * @returns {Object} { image: Array<Float32Array> }
         */
        generateSpectrogramImage: function(levelsFlat, nFreqs, nTimes) {
            if (!levelsFlat || nFreqs <= 0 || nTimes <= 0) {
                return { image: [] };
            }

            // Create 2D array structure: Array of Float32Arrays
            const image = new Array(nFreqs);
            
            // Check if input is already a typed array to optimize
            const isTyped = levelsFlat.subarray !== undefined;

            for (let i = 0; i < nFreqs; i++) {
                const start = i * nTimes;
                const end = start + nTimes;
                
                if (isTyped) {
                    // Fast slice for typed arrays
                    image[i] = levelsFlat.slice(start, end);
                } else {
                    // Manual copy for regular arrays
                    const row = new Float32Array(nTimes);
                    for (let j = 0; j < nTimes; j++) {
                        row[j] = levelsFlat[start + j];
                    }
                    image[i] = row;
                }
            }
            
            return { image: image };
        },

        /**
         * Updates a Bokeh image buffer in place.
         * 
         * @param {Array<Float32Array>} buffer - The target 2D array buffer
         * @param {Array|Float32Array} newData - Flattened new data
         * @param {number} nFreqs - Number of frequency bins
         * @param {number} nTimes - Number of time steps
         */
        updateBokehImageData: function(buffer, newData, nFreqs, nTimes) {
            // Check dimensions match
            if (!buffer || buffer.length !== nFreqs || (buffer[0] && buffer[0].length !== nTimes)) {
                console.warn("[MatrixUtils] Buffer dimensions mismatch, creating new image.");
                return this.generateSpectrogramImage(newData, nFreqs, nTimes).image;
            }

            // Update in place
            for (let i = 0; i < nFreqs; i++) {
                const row = buffer[i];
                const start = i * nTimes;
                for (let j = 0; j < nTimes; j++) {
                    row[j] = newData[start + j];
                }
            }
            return buffer;
        }
    };

    /**
     * Calculates the dynamic log view threshold in seconds.
     * Uses the shared view resolution module so all callers use one policy.
     * 
     * @param {Object} models - The models registry
     * @param {string} position - The position identifier
     * @param {Object|null} thresholdInput - Explicit threshold config ({ mode, seconds })
     * @returns {number} Threshold in seconds
     */
    function calculateLogViewThreshold(models, position, thresholdInput) {
        const resolution = app.features?.view?.resolution;
        if (resolution?.resolveLogThresholdSeconds) {
            const viewState = {
                availablePositions: [position],
                logViewThreshold: thresholdInput
            };
            return resolution.resolveLogThresholdSeconds(models, viewState, position);
        }
        return 3600;
    }

    function calculateSpectrogramLogViewThreshold(models, position, thresholdInput, logData) {
        const baseThresholdSeconds = calculateLogViewThreshold(models, position, thresholdInput);
        const glyphDw = Array.isArray(logData?.initial_glyph_data?.dw)
            ? Number(logData.initial_glyph_data.dw[0])
            : Number(logData?.initial_glyph_data?.dw);
        const chunkTimeLength = Number(logData?.chunk_time_length);
        const timeStep = Number(logData?.time_step);
        const chunkWindowSeconds = Number.isFinite(glyphDw) && glyphDw > 0
            ? glyphDw / 1000
            : (
                Number.isFinite(chunkTimeLength)
                && chunkTimeLength > 0
                && Number.isFinite(timeStep)
                && timeStep > 0
                    ? (chunkTimeLength * timeStep) / 1000
                    : null
            );

        return Number.isFinite(chunkWindowSeconds) && chunkWindowSeconds > 0
            ? Math.min(baseThresholdSeconds, chunkWindowSeconds)
            : baseThresholdSeconds;
    }

    function calculateSharedLogDisplayThreshold(models, viewState) {
        const resolution = app.features?.view?.resolution;
        let sharedThresholdSeconds = null;

        if (resolution?.resolveLogThresholdSeconds) {
            sharedThresholdSeconds = resolution.resolveLogThresholdSeconds(models, viewState, null);
        }

        if (!Number.isFinite(sharedThresholdSeconds) || sharedThresholdSeconds <= 0) {
            const positions = Array.isArray(viewState?.availablePositions) ? viewState.availablePositions : [];
            const fallbackThresholds = positions
                .map(positionId => calculateLogViewThreshold(models, positionId, viewState?.logViewThreshold))
                .filter(value => Number.isFinite(value) && value > 0);
            sharedThresholdSeconds = fallbackThresholds.length ? Math.min(...fallbackThresholds) : Infinity;
        }

        const positions = Array.isArray(viewState?.availablePositions) ? viewState.availablePositions : [];
        positions.forEach(positionId => {
            const serverThresholdSeconds = Number(models?.positionLogSpectralThresholdSeconds?.[positionId]);
            if (Number.isFinite(serverThresholdSeconds) && serverThresholdSeconds > 0) {
                sharedThresholdSeconds = Math.min(sharedThresholdSeconds, serverThresholdSeconds);
                return;
            }

            const preparedLogParams = models?.preparedGlyphData?.[positionId]?.log?.prepared_params;
            let representativeLogData = preparedLogParams && typeof preparedLogParams === 'object'
                ? Object.values(preparedLogParams).find(Boolean)
                : null;
            if (!representativeLogData) {
                const sourceData = models?.spectrogramSources?.[positionId]?.log?.data;
                const glyphDw = unwrapScalarValue(sourceData?.initial_glyph_data_dw)
                    ?? unwrapScalarValue(sourceData?.initial_glyph_data?.dw);
                const chunkTimeLength = unwrapScalarValue(sourceData?.chunk_time_length);
                const timeStep = unwrapScalarValue(sourceData?.time_step);
                if (Number.isFinite(Number(glyphDw)) || (Number.isFinite(Number(chunkTimeLength)) && Number.isFinite(Number(timeStep)))) {
                    representativeLogData = {
                        initial_glyph_data: { dw: [Number(glyphDw)] },
                        chunk_time_length: Number(chunkTimeLength),
                        time_step: Number(timeStep),
                    };
                }
            }
            if (!representativeLogData) {
                return;
            }

            const spectralThresholdSeconds = calculateSpectrogramLogViewThreshold(
                models,
                positionId,
                viewState?.logViewThreshold,
                representativeLogData
            );

            if (Number.isFinite(spectralThresholdSeconds) && spectralThresholdSeconds > 0) {
                sharedThresholdSeconds = Math.min(sharedThresholdSeconds, spectralThresholdSeconds);
            }
        });

        return Number.isFinite(sharedThresholdSeconds) && sharedThresholdSeconds > 0
            ? sharedThresholdSeconds
            : Infinity;
    }

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

    function debugSpectrogram(position, label, payload) {
        const debugPos = getDebugPosition();
        if (!debugPos || position !== debugPos) {
            return;
        }
        try {
            console.log(`[SpecDebug] ${label}`, payload);
        } catch (error) {
            console.warn('[SpecDebug] Failed to log payload', error);
        }
    }

    function createDisplayMetadata(options = {}) {
        const requestedViewType = options.requestedViewType === 'log' ? 'log' : 'overview';
        const selectedParameter = typeof options.selectedParameter === 'string' && options.selectedParameter
            ? options.selectedParameter
            : null;
        const displayedParameter = typeof options.displayedParameter === 'string' && options.displayedParameter
            ? options.displayedParameter
            : selectedParameter;

        return {
            type: typeof options.type === 'string' ? options.type : 'none',
            reason: typeof options.reason === 'string' ? options.reason : '',
            statusCode: typeof options.statusCode === 'string' ? options.statusCode : 'unknown',
            statusLabel: typeof options.statusLabel === 'string' ? options.statusLabel : '',
            requestedViewType,
            displayedViewType: typeof options.type === 'string' ? options.type : 'none',
            selectedParameter,
            displayedParameter,
            isLoading: Boolean(options.isLoading),
            requiresZoom: Boolean(options.requiresZoom),
            logDataExists: Boolean(options.logDataExists),
            coverageRatio: Number.isFinite(options.coverageRatio) ? options.coverageRatio : null,
            centeredChunkReady: options.centeredChunkReady === undefined ? null : Boolean(options.centeredChunkReady),
            parameterMismatch: Boolean(options.parameterMismatch),
        };
    }

    function unwrapScalarValue(value) {
        if (Array.isArray(value)) {
            return value.length ? unwrapScalarValue(value[0]) : null;
        }
        return value;
    }

    function buildOverviewSpectrogramFallback(overviewData, position, dataCache, models, metadataOptions = {}) {
        const displayMetadata = createDisplayMetadata({
            type: 'overview',
            ...metadataOptions
        });
        const baseImage = getPreparedSpectrogramChunk(
            overviewData,
            0,
            overviewData?.n_times
        );
        const finalGlyphData = tryApplySpectrogramSlice(
            overviewData,
            baseImage,
            0,
            overviewData?.n_times,
            position,
            dataCache,
            models
        );

        return {
            finalDataToUse: overviewData,
            finalGlyphData,
            displayMetadata
        };
    }

    function assessSpectrogramLogReadiness(logData, viewportStart, viewportEnd) {
        const times_ms = logData?.times_ms;
        const n_times = Number(logData?.n_times);
        const chunk_time_length = Number(logData?.chunk_time_length);
        const time_step = Number(logData?.time_step);
        if (!times_ms?.length || !Number.isFinite(n_times) || n_times <= 0) {
            return {
                coverageRatio: 0,
                hasAdequateCoverage: false,
                canCenterChunk: false,
                chunkStartTimeIdx: 0,
                actualChunkPoints: 0,
                safeTimeStep: Number.isFinite(time_step) && time_step > 0 ? time_step : 1000,
                targetChunkPoints: 0,
                viewportWidth: 0,
                logDataStart: null,
                logDataEnd: null,
            };
        }

        const safeViewportStart = Math.min(viewportStart, viewportEnd);
        const safeViewportEnd = Math.max(viewportStart, viewportEnd);
        const viewportWidth = Math.max(0, safeViewportEnd - safeViewportStart);
        const logDataStart = Number(times_ms[0]);
        const logDataEnd = Number(times_ms[times_ms.length - 1]);
        const rawReservoirDisplayStart = unwrapScalarValue(logData?.initial_glyph_data_x)
            ?? unwrapScalarValue(logData?.initial_glyph_data?.x);
        const rawReservoirDisplayWidth = unwrapScalarValue(logData?.initial_glyph_data_dw)
            ?? unwrapScalarValue(logData?.initial_glyph_data?.dw);
        const initialChunkStart = Number.isFinite(Number(rawReservoirDisplayStart))
            ? Number(rawReservoirDisplayStart)
            : logDataStart;
        const initialChunkWidth = Number.isFinite(Number(rawReservoirDisplayWidth)) && Number(rawReservoirDisplayWidth) > 0
            ? Number(rawReservoirDisplayWidth)
            : (Number.isFinite(time_step) && time_step > 0 && Number.isFinite(chunk_time_length) && chunk_time_length > 0
                ? chunk_time_length * time_step
                : Math.max(0, logDataEnd - logDataStart));
        // For reservoir payloads, the safe pan/zoom span is the full backing reservoir,
        // not the initial fixed-size display chunk described by initial_glyph_data.dw.
        const reservoirDisplayStart = logData?._isReservoirPayload
            ? logDataStart
            : initialChunkStart;
        const reservoirDisplayEnd = logData?._isReservoirPayload
            ? (logDataEnd + (Number.isFinite(time_step) && time_step > 0 ? time_step : 0))
            : (initialChunkStart + initialChunkWidth);
        const overlapStart = Math.max(safeViewportStart, logDataStart);
        const overlapEnd = Math.min(safeViewportEnd, logDataEnd);
        const overlapWidth = Math.max(0, overlapEnd - overlapStart);
        const coverageRatio = viewportWidth > 0 ? (overlapWidth / viewportWidth) : 1;
        const MIN_COVERAGE_RATIO = 0.98;
        const hasAdequateCoverage = coverageRatio >= MIN_COVERAGE_RATIO;

        const safeTimeStep = Number.isFinite(time_step) && time_step > 0 ? time_step : 1000;
        const rawViewportPoints = viewportWidth > 0
            ? Math.ceil(viewportWidth / safeTimeStep)
            : chunk_time_length;
        const viewportPoints = Math.max(
            1,
            Math.min(n_times, Number.isFinite(rawViewportPoints) ? rawViewportPoints : chunk_time_length)
        );
        const targetChunkPoints = Math.max(
            1,
            Math.min(n_times, Number.isFinite(chunk_time_length) && chunk_time_length > 0 ? Math.floor(chunk_time_length) : viewportPoints)
        );
        let viewportCenter = Number.isFinite(safeViewportStart) && Number.isFinite(safeViewportEnd)
            ? (safeViewportStart + safeViewportEnd) / 2
            : Number(times_ms[Math.max(0, Math.floor(n_times / 2))]);
        if (!Number.isFinite(viewportCenter)) {
            viewportCenter = Number(times_ms[Math.max(0, Math.floor(n_times / 2))]);
        }

        const targetChunkStartTimeStamp = viewportCenter - (targetChunkPoints * safeTimeStep / 2);
        const targetChunkEndTimeStamp = viewportCenter + (targetChunkPoints * safeTimeStep / 2);
        const centeredTolerance = safeTimeStep * 0.5;

        let chunkStartTimeIdx = times_ms.findIndex(t => t >= targetChunkStartTimeStamp);
        if (chunkStartTimeIdx === -1) {
            chunkStartTimeIdx = Math.max(0, n_times - targetChunkPoints);
        }
        chunkStartTimeIdx = Math.min(
            Math.max(0, chunkStartTimeIdx),
            Math.max(0, n_times - targetChunkPoints)
        );
        const actualChunkPoints = Math.max(1, Math.min(targetChunkPoints, n_times - chunkStartTimeIdx));
        const viewportWithinReservoir = safeViewportStart >= (reservoirDisplayStart - centeredTolerance)
            && safeViewportEnd <= (reservoirDisplayEnd + safeTimeStep + centeredTolerance);
        const canCenterChunk = viewportWithinReservoir && actualChunkPoints >= targetChunkPoints;

        return {
            coverageRatio,
            hasAdequateCoverage,
            canCenterChunk,
            viewportWithinReservoir,
            chunkStartTimeIdx,
            actualChunkPoints,
            safeTimeStep,
            targetChunkPoints,
            viewportWidth,
            viewportCenter,
            targetChunkStartTimeStamp,
            targetChunkEndTimeStamp,
            logDataStart,
            logDataEnd,
            reservoirDisplayStart,
            reservoirDisplayEnd,
            chunkStartTime: times_ms?.[chunkStartTimeIdx],
            chunkEndTime: times_ms?.[Math.min(n_times - 1, chunkStartTimeIdx + actualChunkPoints - 1)],
        };
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
                        const startIndex = logData.Datetime.findIndex(t => t >= effectiveMin);
                        const endIndex = logData.Datetime.findLastIndex(t => t <= effectiveMax);
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
                    displayDetails = createDisplayMetadata({
                        type: 'overview',
                        reason: logDataExists ? ' (Overview - Zoom in for Log Data)' : ' (Overview)',
                        statusCode: logDataExists ? 'loading_log' : 'overview_only',
                        statusLabel: logDataExists ? 'Waiting for log data' : 'Overview data only',
                        requestedViewType: viewType,
                        logDataExists,
                        isLoading: logDataExists,
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
    function updateActiveSpectralData(position, viewState, dataCache, models, positionOffsetMs = 0) {
        try {
            if (!dataCache.activeSpectralData) {
                dataCache.activeSpectralData = {};
            }

            const viewType = viewState.globalViewType;
            const parameter = viewState.selectedParameter;
            
            // Read from streaming sources (reservoir)
            const spectrogramSources = models.spectrogramSources?.[position];
            const overviewSourceData = spectrogramSources?.overview?.data;
            const logSourceData = spectrogramSources?.log?.data;
            
            if (viewType === 'log') {
                debugSpectrogram(position, 'processing', {
                    hasSource: !!spectrogramSources,
                    hasLogSource: !!spectrogramSources?.log,
                    hasLogData: !!logSourceData,
                    keys: logSourceData ? Object.keys(logSourceData) : []
                });
            }

            // For overview, use preparedGlyphData (static)
            const positionGlyphData = models.preparedGlyphData[position];
            const overviewData = positionGlyphData?.overview?.prepared_params?.[parameter];
            
            // For log, reconstruct data from streaming source (Bokeh ColumnDataSource format)
            // Server wraps EVERYTHING in single-element lists to satisfy Bokeh constraint.
            // Payloads may contain typed arrays (Float32Array, Float64Array) from NumPy
            // or plain arrays from JSON serialization. We normalize both forms here.
            const streamedLogData = logSourceData?.times_ms ? (() => {
                // Normalize helper: unwrap from single-element Bokeh list wrapper,
                // handling both plain arrays and typed arrays.
                const unwrapArray = (field) => {
                    if (!field) return null;
                    const inner = field[0];
                    // Typed arrays (Float32Array, Float64Array etc.) are not plain arrays
                    // but are valid numeric buffers — return them directly.
                    if (inner != null && typeof inner === 'object' && ArrayBuffer.isView(inner)) return inner;
                    if (Array.isArray(inner)) return inner;
                    // Already unwrapped (no wrapping list)
                    return field;
                };

                const times = unwrapArray(logSourceData.times_ms);
                const levels = unwrapArray(logSourceData.levels_flat_transposed);
                const freqLabels = logSourceData.frequency_labels ? unwrapArray(logSourceData.frequency_labels) : null;
                const freqHz = logSourceData.frequencies_hz ? unwrapArray(logSourceData.frequencies_hz) : null;
                const payloadParameter = logSourceData.parameter ? logSourceData.parameter[0] : null;

                // Unwrap scalar metadata from single-element lists (Bokeh transport format)
                const rawNTimes = Number(logSourceData.n_times ? logSourceData.n_times[0] : times?.length);
                const rawNFreqs = Number(logSourceData.n_freqs ? logSourceData.n_freqs[0] : (freqLabels?.length || freqHz?.length || 0));
                const safeNFreqs = Number.isFinite(rawNFreqs) && rawNFreqs > 0 ? Math.floor(rawNFreqs) : 0;
                const inferredNTimes = safeNFreqs > 0 && levels?.length
                    ? Math.floor(levels.length / safeNFreqs)
                    : (times?.length || 0);
                const n_times = Number.isFinite(rawNTimes) && rawNTimes > 0
                    ? Math.min(Math.floor(rawNTimes), inferredNTimes || Math.floor(rawNTimes))
                    : inferredNTimes;
                const n_freqs = safeNFreqs;
                const time_step = logSourceData.time_step ? logSourceData.time_step[0] : (n_times > 1 ? (times[n_times - 1] - times[0]) / (n_times - 1) : 0);
                const rawChunkTimeLength = Number(logSourceData.chunk_time_length ? logSourceData.chunk_time_length[0] : n_times);
                const chunk_time_length = Number.isFinite(rawChunkTimeLength) && rawChunkTimeLength > 0
                    ? Math.min(Math.floor(rawChunkTimeLength), n_times || Math.floor(rawChunkTimeLength))
                    : n_times;
                const min_val = logSourceData.min_val ? logSourceData.min_val[0] : 0;
                const max_val = logSourceData.max_val ? logSourceData.max_val[0] : 100;

                // Detect payload type: reservoir (wider than display chunk) or legacy chunk-only
                const isReservoirPayload = logSourceData.is_reservoir_payload
                    ? !!logSourceData.is_reservoir_payload[0]
                    : false;
                const levelsLength = levels?.length || 0;
                const expectedChunkCells = n_freqs * chunk_time_length;
                const isChunkOnlyPayload = !isReservoirPayload && levelsLength > 0 && levelsLength === expectedChunkCells;

                if (viewType === 'log') {
                    debugSpectrogram(position, 'unwrapped-log-source', {
                        timesLen: times?.length,
                        levelsLen: levelsLength,
                        freqLabelsLen: freqLabels?.length,
                        firstTime: times?.[0],
                        lastTime: times?.[times?.length - 1],
                        isReservoirPayload,
                        isChunkOnlyPayload,
                        expectedChunkCells,
                        n_freqs,
                        chunk_time_length
                    });
                }

                // Reconstruct initial_glyph_data from flattened transport fields
                let initial_glyph_data = null;
                if (logSourceData.initial_glyph_data_image) {
                    const imageData = unwrapArray(logSourceData.initial_glyph_data_image);
                    initial_glyph_data = {
                        x: logSourceData.initial_glyph_data_x ? logSourceData.initial_glyph_data_x[0] : [0],
                        y: logSourceData.initial_glyph_data_y ? logSourceData.initial_glyph_data_y[0] : [-0.5],
                        dw: logSourceData.initial_glyph_data_dw ? logSourceData.initial_glyph_data_dw[0] : [0],
                        dh: logSourceData.initial_glyph_data_dh ? logSourceData.initial_glyph_data_dh[0] : [0],
                        image: [imageData]
                    };
                }

                return {
                    parameter: typeof payloadParameter === 'string' && payloadParameter ? payloadParameter : null,
                    times_ms: times,
                    levels_flat_transposed: levels,
                    n_freqs,
                    n_times,
                    time_step,
                    chunk_time_length,
                    frequency_labels: freqLabels,
                    frequencies_hz: freqHz,
                    min_val,
                    max_val,
                    initial_glyph_data,
                    _isChunkOnlyPayload: isChunkOnlyPayload,
                    _isReservoirPayload: isReservoirPayload
                };
            })() : null;
            const fallbackPreparedLogData = positionGlyphData?.log?.prepared_params?.[parameter] || null;
            const hasStreamedLogData = Boolean(
                streamedLogData
                && streamedLogData.times_ms
                && streamedLogData.times_ms.length > 0
            );
            const streamedParameterMismatch = Boolean(
                hasStreamedLogData
                && streamedLogData.parameter
                && streamedLogData.parameter !== parameter
            );
            const logData = streamedParameterMismatch
                ? fallbackPreparedLogData
                : (streamedLogData || fallbackPreparedLogData);
            
            const hasLogData = logData && logData.times_ms && logData.times_ms.length > 0;
            // Whether log data exists on disk (even if not yet lazy-loaded)
            const logDataExists = models.positionHasLogData?.[position] ?? (hasStreamedLogData || hasLogData);

            let finalDataToUse, finalGlyphData;
            let displayMetadata = createDisplayMetadata({
                type: 'none',
                reason: ' (No Data Available)',
                statusCode: 'no_data',
                statusLabel: 'No data available',
                requestedViewType: viewType,
                selectedParameter: parameter,
                displayedParameter: null,
                logDataExists,
            });

            const offsetMs = positionOffsetMs;
            const viewportMin = Number(viewState.viewport?.min);
            const viewportMax = Number(viewState.viewport?.max);
            const effectiveMin = Number.isFinite(viewportMin) ? viewportMin - offsetMs : viewportMin;
            const effectiveMax = Number.isFinite(viewportMax) ? viewportMax - offsetMs : viewportMax;
            
            // Check viewport width against dynamic threshold (in milliseconds)
            const logViewThresholdSeconds = calculateSharedLogDisplayThreshold(models, viewState);
            const viewportWidthMs = Number.isFinite(effectiveMax) && Number.isFinite(effectiveMin)
                ? effectiveMax - effectiveMin : Infinity;
            const viewportWidthSeconds = viewportWidthMs / 1000;
            const viewportTooLarge = viewportWidthSeconds > logViewThresholdSeconds;

            if (viewType === 'log') {
                if (streamedParameterMismatch) {
                    debugSpectrogram(position, 'parameter-mismatch', {
                        selectedParameter: parameter,
                        streamedParameter: streamedLogData?.parameter
                    });
                    ({ finalDataToUse, finalGlyphData, displayMetadata } = buildOverviewSpectrogramFallback(
                        overviewData,
                        position,
                        dataCache,
                        models,
                        {
                            reason: ' (Overview - Waiting for selected Log parameter...)',
                            statusCode: 'parameter_sync',
                            statusLabel: `Waiting for ${parameter} log data`,
                            requestedViewType: viewType,
                            selectedParameter: parameter,
                            displayedParameter: parameter,
                            logDataExists,
                            isLoading: true,
                            parameterMismatch: true,
                        }
                    ));
                } else if (hasLogData) {
                    if (viewportTooLarge) {
                        ({ finalDataToUse, finalGlyphData, displayMetadata } = buildOverviewSpectrogramFallback(
                            overviewData,
                            position,
                            dataCache,
                            models,
                            {
                                reason: ' - Overview - zoom in for Log',
                                statusCode: 'zoom_required',
                                statusLabel: 'Zoom in for log spectrogram',
                                requestedViewType: viewType,
                                selectedParameter: parameter,
                                displayedParameter: parameter,
                                logDataExists,
                                requiresZoom: true,
                            }
                        ));
                    } else {
                        const readiness = assessSpectrogramLogReadiness(logData, effectiveMin, effectiveMax);
                        debugSpectrogram(position, 'coverage-check', {
                            viewportStart: effectiveMin,
                            viewportEnd: effectiveMax,
                            viewportWidth: readiness.viewportWidth,
                            logDataStart: readiness.logDataStart,
                            logDataEnd: readiness.logDataEnd,
                            reservoirDisplayStart: readiness.reservoirDisplayStart,
                            reservoirDisplayEnd: readiness.reservoirDisplayEnd,
                            coverageRatio: readiness.coverageRatio,
                            viewportWithinReservoir: readiness.viewportWithinReservoir,
                            canCenterChunk: readiness.canCenterChunk,
                            targetChunkPoints: readiness.targetChunkPoints,
                            targetChunkStartTimeStamp: readiness.targetChunkStartTimeStamp,
                            targetChunkEndTimeStamp: readiness.targetChunkEndTimeStamp,
                        });

                        if (readiness.hasAdequateCoverage && readiness.canCenterChunk) {
                            // Happy Path: Show chunked LOG data
                            finalDataToUse = logData;
                            displayMetadata = createDisplayMetadata({
                                type: 'log',
                                reason: ' (Log Data)',
                                statusCode: 'log_displayed',
                                statusLabel: 'Showing log spectrogram',
                                requestedViewType: viewType,
                                selectedParameter: parameter,
                                displayedParameter: logData.parameter || parameter,
                                logDataExists,
                                coverageRatio: readiness.coverageRatio,
                                centeredChunkReady: true,
                            });

                            const { n_times, chunk_time_length, times_ms, time_step, levels_flat_transposed, n_freqs, _isChunkOnlyPayload, _isReservoirPayload } = finalDataToUse;

                            // Legacy fast path for chunk-only payloads (server already extracted the exact chunk)
                            if (_isChunkOnlyPayload) {
                                debugSpectrogram(position, 'chunk-only-fast-path', {
                                    levelsLen: levels_flat_transposed.length,
                                    n_freqs,
                                    chunk_time_length,
                                    expectedCells: n_freqs * chunk_time_length
                                });

                                finalGlyphData = tryApplySpectrogramSlice(
                                    finalDataToUse,
                                    levels_flat_transposed,
                                    0,
                                    chunk_time_length,
                                    position,
                                    dataCache,
                                    models
                                );
                            } else {
                                // Reservoir path (new) and legacy full-backing-array path:
                                // Extract the fixed-size display chunk from the wider backing data client-side.
                                // This is the same extraction logic used in static mode.
                                debugSpectrogram(position, 'chunk-selection', {
                                    n_times,
                                    time_step: readiness.safeTimeStep,
                                    viewportMin: effectiveMin,
                                    viewportMax: effectiveMax,
                                    viewportWidth: readiness.viewportWidth,
                                    targetChunkPoints: readiness.targetChunkPoints,
                                    viewportCenter: readiness.viewportCenter,
                                    targetChunkStartTimeStamp: readiness.targetChunkStartTimeStamp,
                                    chunkStartTimeIdx: readiness.chunkStartTimeIdx,
                                    actualChunkPoints: readiness.actualChunkPoints,
                                    chunkStartTime: readiness.chunkStartTime,
                                    chunkEndTime: readiness.chunkEndTime,
                                    isReservoir: _isReservoirPayload
                                });

                                const chunk_image_full_freqs = _extractTimeChunkFromFlatData(
                                    levels_flat_transposed,
                                    n_freqs,
                                    n_times,
                                    readiness.chunkStartTimeIdx,
                                    readiness.actualChunkPoints
                                );

                                finalGlyphData = tryApplySpectrogramSlice(
                                    finalDataToUse,
                                    chunk_image_full_freqs,
                                    readiness.chunkStartTimeIdx,
                                    readiness.actualChunkPoints,
                                    position,
                                    dataCache,
                                    models
                                );
                            }

                        } else {
                            // Log view active, but current streamed source does not cover viewport.
                            const loadingReason = readiness.hasAdequateCoverage
                                ? ' (Overview - Waiting for centered Log chunk...)'
                                : ' (Overview - Streaming Log Data...)';
                            const loadingLabel = readiness.hasAdequateCoverage
                                ? 'Waiting for aligned log spectrogram'
                                : 'Loading log spectrogram';
                            debugSpectrogram(position, 'edge-guard-fallback', readiness);
                            ({ finalDataToUse, finalGlyphData, displayMetadata } = buildOverviewSpectrogramFallback(
                                overviewData,
                                position,
                                dataCache,
                                models,
                                {
                                    reason: loadingReason,
                                    statusCode: readiness.hasAdequateCoverage ? 'edge_guard' : 'loading_log',
                                    statusLabel: loadingLabel,
                                    requestedViewType: viewType,
                                    selectedParameter: parameter,
                                    displayedParameter: parameter,
                                    logDataExists,
                                    isLoading: true,
                                    coverageRatio: readiness.coverageRatio,
                                    centeredChunkReady: readiness.canCenterChunk,
                                }
                            ));
                        }
                    }
                } else {
                    // Log view active, but no log data exists
                    ({ finalDataToUse, finalGlyphData, displayMetadata } = buildOverviewSpectrogramFallback(
                        overviewData,
                        position,
                        dataCache,
                        models,
                        {
                            reason: logDataExists ? ' (Overview - Zoom in for Log Data)' : ' (Overview)',
                            statusCode: logDataExists ? 'loading_log' : 'overview_only',
                            statusLabel: logDataExists ? 'Waiting for log spectrogram' : 'Overview data only',
                            requestedViewType: viewType,
                            selectedParameter: parameter,
                            displayedParameter: parameter,
                            logDataExists,
                            isLoading: logDataExists,
                        }
                    ));
                }
            } else {
                // Overview view is explicitly active
                ({ finalDataToUse, finalGlyphData, displayMetadata } = buildOverviewSpectrogramFallback(
                    overviewData,
                    position,
                    dataCache,
                    models,
                    {
                        reason: logDataExists ? ' (Overview - Enable Log View for detail)' : ' (Overview)',
                        statusCode: 'overview_selected',
                        statusLabel: logDataExists ? 'Overview selected' : 'Overview data only',
                        requestedViewType: viewType,
                        selectedParameter: parameter,
                        displayedParameter: parameter,
                        logDataExists,
                    }
                ));
            }

            // --- Final state update ---
            if (finalDataToUse) {
                const adjustedReplacement = finalGlyphData
                    ? { ...applySpectrogramReplacementOffset(finalGlyphData, offsetMs), _offsetMs: offsetMs }
                    : null;
                const adjustedTimes = finalDataToUse.times_ms ? createOffsetArray(finalDataToUse.times_ms, offsetMs) : [];
                debugSpectrogram(position, 'final-active-spectral-data', {
                    dataViewType: displayMetadata?.type,
                    finalTimesFirst: finalDataToUse.times_ms?.[0],
                    finalTimesLast: finalDataToUse.times_ms?.[finalDataToUse.times_ms?.length - 1],
                    adjustedTimesFirst: adjustedTimes?.[0],
                    adjustedTimesLast: adjustedTimes?.[adjustedTimes.length - 1],
                    replacementX: adjustedReplacement?.x?.[0],
                    replacementDw: adjustedReplacement?.dw?.[0],
                    replacementTimesFirst: adjustedReplacement?.times_ms?.[0],
                    replacementTimesLast: adjustedReplacement?.times_ms?.[adjustedReplacement?.times_ms?.length - 1],
                    replacementTimesLen: adjustedReplacement?.times_ms?.length,
                    replacementImageLen: adjustedReplacement?.image?.[0]?.length
                });
                
                dataCache.activeSpectralData[position] = {
                    ...finalDataToUse,
                    dataViewType: displayMetadata.type,
                    displayDetails: displayMetadata,
                    displayedParameter: displayMetadata.displayedParameter,
                    selectedParameter: displayMetadata.selectedParameter,
                    times_ms: adjustedTimes,
                    source_replacement: adjustedReplacement
                };
            } else {
                // This case handles when overviewData was also null in one of the fallback paths.
                dataCache.activeSpectralData[position] = {
                    source_replacement: null,
                    reason: 'No Data Available',
                    times_ms: [],
                    dataViewType: 'none',
                    displayDetails: createDisplayMetadata({
                        type: 'none',
                        statusCode: 'no_data',
                        statusLabel: 'No data available',
                        requestedViewType: viewType,
                        selectedParameter: parameter,
                        displayedParameter: null,
                    }),
                    displayedParameter: null,
                    selectedParameter: parameter
                };
                // If we ended up with no data, this reason overrides any previous one.
                displayMetadata = createDisplayMetadata({
                    type: 'none',
                    reason: ' (No Data Available)',
                    statusCode: 'no_data',
                    statusLabel: 'No data available',
                    requestedViewType: viewType,
                    selectedParameter: parameter,
                    displayedParameter: null,
                    logDataExists,
                });
            }
            return displayMetadata;
        }
        catch (error) {
            console.error(" [data-processors.js - updateActiveSpectralData()]", error);
            return { type: 'unknown', reason: '' };
        }
    }

    function tryApplySpectrogramSlice(finalDataToUse, imageData, chunkStartTimeIdx, chunkTimeLength, position, dataCache, models) {
        if (!finalDataToUse || !imageData) {
            return null;
        }
        try {
            return _applySpectrogramFreqSlicing(finalDataToUse, imageData, chunkStartTimeIdx, chunkTimeLength, position, dataCache, models);
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

    function _extractTimeChunkFromFlatData(flatData, n_freqs, n_times_total, start_time_idx, chunk_time_length) {
        try {
            // Accept any typed array (Float32Array, Int16Array, etc.) or plain array.
            // Bokeh may hydrate NumPy buffers into custom typed-array wrappers whose
            // `subarray()` implementation returns the full buffer, so copy by index.
            const typedFlatData = ArrayBuffer.isView(flatData) ? flatData : new Float32Array(flatData);
            const safeFreqs = Number.isFinite(Number(n_freqs)) && Number(n_freqs) > 0
                ? Math.floor(Number(n_freqs))
                : 0;
            if (!safeFreqs || !typedFlatData.length) {
                return new Float32Array(0);
            }

            const inferredTotalTimes = Math.floor(typedFlatData.length / safeFreqs);
            const requestedTotalTimes = Number.isFinite(Number(n_times_total)) && Number(n_times_total) > 0
                ? Math.floor(Number(n_times_total))
                : inferredTotalTimes;
            const safeTotalTimes = Math.max(0, Math.min(requestedTotalTimes, inferredTotalTimes));
            if (!safeTotalTimes) {
                return new Float32Array(0);
            }

            const safeStart = Math.max(0, Math.min(
                Number.isFinite(Number(start_time_idx)) ? Math.floor(Number(start_time_idx)) : 0,
                Math.max(0, safeTotalTimes - 1)
            ));
            const requestedChunkLength = Number.isFinite(Number(chunk_time_length)) && Number(chunk_time_length) > 0
                ? Math.floor(Number(chunk_time_length))
                : safeTotalTimes;
            const safeChunkLength = Math.max(1, Math.min(requestedChunkLength, safeTotalTimes - safeStart));
            const chunk_data = new Float32Array(safeFreqs * safeChunkLength);

            for (let i = 0; i < safeFreqs; i++) {
                const source_row_start = (i * safeTotalTimes) + safeStart;
                const remainingCells = typedFlatData.length - source_row_start;
                if (remainingCells <= 0) {
                    break;
                }
                const rowWidth = Math.min(safeChunkLength, remainingCells, safeTotalTimes - safeStart);
                if (rowWidth <= 0) {
                    continue;
                }

                const target_row_start = i * safeChunkLength;
                for (let j = 0; j < rowWidth; j++) {
                    chunk_data[target_row_start + j] = typedFlatData[source_row_start + j];
                }
            }
            return chunk_data;
        }
        catch (error) {
            console.error(" [data-processors.js - _extractTimeChunkFromFlatData()]", error);
        }
    }

    function getPreparedSpectrogramChunk(finalDataToUse, startTimeIdx = 0, requestedChunkLength = null) {
        if (!finalDataToUse) {
            return null;
        }

        const nTimes = Number(finalDataToUse.n_times);
        const nFreqs = Number(finalDataToUse.n_freqs);
        const flat = finalDataToUse.levels_flat_transposed;
        if (flat && Number.isFinite(nTimes) && Number.isFinite(nFreqs) && nTimes > 0 && nFreqs > 0) {
            const safeStart = Math.max(0, Math.min(startTimeIdx, Math.max(0, nTimes - 1)));
            const defaultLength = Math.min(
                Number.isFinite(finalDataToUse.chunk_time_length) ? finalDataToUse.chunk_time_length : nTimes,
                nTimes - safeStart
            );
            const chunkLength = Math.max(
                1,
                Math.min(
                    nTimes - safeStart,
                    Number.isFinite(requestedChunkLength) ? Math.floor(requestedChunkLength) : defaultLength
                )
            );
            return _extractTimeChunkFromFlatData(flat, nFreqs, nTimes, safeStart, chunkLength);
        }

        return finalDataToUse?.initial_glyph_data?.image?.[0] || null;
    }

    function _calculateSpectrogramChunkWidth(timesMs, fallbackTimeStep) {
        if (!timesMs || timesMs.length === 0) {
            return 0;
        }
        if (timesMs.length === 1) {
            return Number.isFinite(fallbackTimeStep) ? fallbackTimeStep : 0;
        }

        const start = Number(timesMs[0]);
        const end = Number(timesMs[timesMs.length - 1]);
        const span = end - start;
        const safeStep = Number.isFinite(fallbackTimeStep) && fallbackTimeStep > 0
            ? fallbackTimeStep
            : Math.max(0, Number(timesMs[1]) - Number(timesMs[0]));

        return Math.max(0, span) + safeStep;
    }

    function _buildDisplayChunkTimes(finalDataToUse, chunkStartTimeIdx, effectiveChunkTimeLength) {
        const baseTimes = finalDataToUse?.times_ms;
        const safeStart = Math.max(0, Math.floor(chunkStartTimeIdx || 0));
        const safeLength = Math.max(1, Math.floor(effectiveChunkTimeLength || 1));
        const firstTime = Number(baseTimes?.[safeStart]);
        const safeTimeStep = Number.isFinite(finalDataToUse?.time_step) && finalDataToUse.time_step > 0
            ? Number(finalDataToUse.time_step)
            : 0;

        if (!Number.isFinite(firstTime)) {
            return [];
        }

        // Use a synthetic monotonic time grid for display chunks so padded tail bins
        // preserve the native bin width instead of collapsing repeated padded timestamps.
        if (safeTimeStep > 0) {
            return Array.from({ length: safeLength }, (_, idx) => firstTime + (idx * safeTimeStep));
        }

        return baseTimes?.slice(safeStart, safeStart + safeLength) || [];
    }

    /**
     * Apply paint-on-canvas frequency slicing for spectrogram display.
     */
    function _applySpectrogramFreqSlicing(finalDataToUse, chunk_image_full_freqs, chunkStartTimeIdx, chunkTimeLength, position, dataCache, models) {
        try {
            const effectiveChunkTimeLength = Math.max(
                1,
                Number.isFinite(chunkTimeLength) ? Math.floor(chunkTimeLength) : Math.floor(finalDataToUse?.chunk_time_length || 1)
            );
            const chunkTimes = _buildDisplayChunkTimes(finalDataToUse, chunkStartTimeIdx, effectiveChunkTimeLength);
            const safeTimeStep = Number.isFinite(finalDataToUse?.time_step) && finalDataToUse.time_step > 0
                ? Number(finalDataToUse.time_step)
                : 0;
            const chunkDw = safeTimeStep > 0
                ? effectiveChunkTimeLength * safeTimeStep
                : _calculateSpectrogramChunkWidth(chunkTimes, finalDataToUse?.time_step);
            if (!finalDataToUse || !finalDataToUse.frequencies_hz || !models.config) {
                return {
                    ...finalDataToUse.initial_glyph_data,
                    image: [chunk_image_full_freqs],
                    x: [finalDataToUse.times_ms[chunkStartTimeIdx]],
                    dw: [chunkDw],
                    times_ms: chunkTimes,
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
                    dw: [chunkDw],
                    times_ms: chunkTimes,
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
                const source_row_start = freq_idx * effectiveChunkTimeLength;
                const source_row_end = source_row_start + effectiveChunkTimeLength;
                
                if (source_row_end > chunk_image_full_freqs.length) {
                    console.error(`[DEBUG] Source overflow! freq_idx: ${freq_idx}, source_row_end: ${source_row_end}, source_length: ${chunk_image_full_freqs.length}`);
                    break;
                }
                
                // Copy visible frequency band to the same position in the buffer (preserves original layout)
                for (let i = 0; i < effectiveChunkTimeLength; i++) {
                    canvasBuffer[source_row_start + i] = chunk_image_full_freqs[source_row_start + i];
                }
            }
            
            const result = {
                ...finalDataToUse.initial_glyph_data,
                image: [canvasBuffer],  // Preserve the original flat glyph buffer shape
                x: [finalDataToUse.times_ms[chunkStartTimeIdx]],
                dw: [chunkDw],
                // CRITICAL: Use original glyph positioning to match full image data layout
                y: finalDataToUse.initial_glyph_data.y,      // Original position (matches full image)
                dh: finalDataToUse.initial_glyph_data.dh,    // Original height (matches full image)
                times_ms: chunkTimes,
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
                dw: [chunkDw],
                times_ms: chunkTimes,
            };
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
