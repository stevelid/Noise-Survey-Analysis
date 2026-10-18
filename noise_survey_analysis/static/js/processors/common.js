/** Shared processing policy and offset helpers. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    app.processing = app.processing || {};
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


    Object.assign(app.processing, { getDebugPosition, isDebugEnabled, calculateLogViewThreshold, calculateSpectrogramLogViewThreshold, calculateSharedLogDisplayThreshold, cloneDataColumns, createOffsetArray, applyDatetimeOffset, getChartOffsetMs, applySpectrogramReplacementOffset, debugSpectrogram, createDisplayMetadata, unwrapScalarValue });
})(window.NoiseSurveyApp);
