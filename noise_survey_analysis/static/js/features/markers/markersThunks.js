// noise_survey_analysis/static/js/features/markers/markersThunks.js

/**
 * @fileoverview Thunks orchestrating marker-specific business logic.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;
    const markerSelectors = app.features?.markers?.selectors || {};
    const viewSelectors = app.features?.view?.selectors || {};

    function hasArrayLikeLength(values) {
        return Boolean(values && typeof values.length === 'number');
    }

    function cloneArrayLike(values) {
        if (!hasArrayLikeLength(values)) {
            return [];
        }
        return Array.from(values);
    }

    function findLastIndexBeforeOrEqual(values, target) {
        if (!hasArrayLikeLength(values) || !Number.isFinite(target)) {
            return -1;
        }
        for (let i = values.length - 1; i >= 0; i--) {
            const value = Number(values[i]);
            if (Number.isFinite(value) && value <= target) {
                return i;
            }
        }
        return -1;
    }

    function sliceSpectralSnapshot(spectralData, timeIndex) {
        if (!spectralData || !Number.isInteger(timeIndex) || timeIndex < 0) {
            return null;
        }
        const labels = cloneArrayLike(spectralData.frequency_labels);
        if (!labels.length || !Number.isFinite(spectralData.n_freqs) || !Number.isFinite(spectralData.n_times)) {
            return null;
        }
        const values = new Array(labels.length);
        for (let i = 0; i < labels.length; i++) {
            const valueIndex = (i * spectralData.n_times) + timeIndex;
            const level = spectralData.levels_flat_transposed?.[valueIndex];
            values[i] = Number.isFinite(level) ? Number(level) : null;
        }
        return { labels, values };
    }

    function computeMarkerMetricsIntent(payload) {
        return function (dispatch, getState) {
            if (typeof actions?.markerSetMetrics !== 'function') {
                return;
            }

            const markerId = Number.isFinite(payload)
                ? Number(payload)
                : Number(payload?.markerId ?? payload?.id);
            if (!Number.isFinite(markerId)) {
                return;
            }

            const state = getState();
            if (!state) {
                return;
            }

            const marker = typeof markerSelectors.selectMarkerById === 'function'
                ? markerSelectors.selectMarkerById(state, markerId)
                : null;
            if (!marker) {
                return;
            }

            const timestamp = Number(marker.timestamp);
            if (!Number.isFinite(timestamp)) {
                return;
            }

            const dataCache = app.dataCache;
            if (!dataCache) {
                console.error('[Markers] computeMarkerMetricsIntent requires the shared data cache.');
                return;
            }

            const availablePositions = Array.isArray(state?.view?.availablePositions)
                ? state.view.availablePositions
                : [];
            const selectedParameter = state?.view?.selectedParameter || null;
            const metricsPayload = {
                timestamp,
                parameter: selectedParameter,
                broadband: [],
                spectral: []
            };

            availablePositions.forEach(positionId => {
                const lineData = dataCache.activeLineData?.[positionId];
                const spectralData = dataCache.activeSpectralData?.[positionId];

                let timeIndex = -1;
                if (lineData && hasArrayLikeLength(lineData.Datetime)) {
                    if (typeof app.utils?.findAssociatedDateIndex === 'function') {
                        timeIndex = app.utils.findAssociatedDateIndex(lineData, timestamp);
                    }
                    if (!Number.isInteger(timeIndex) || timeIndex < 0) {
                        timeIndex = findLastIndexBeforeOrEqual(lineData.Datetime, timestamp);
                    }
                }

                const parameterValues = lineData?.[selectedParameter];
                if (
                    timeIndex !== -1
                    && selectedParameter
                    && hasArrayLikeLength(parameterValues)
                    && timeIndex < parameterValues.length
                ) {
                    const broadbandValue = Number(parameterValues[timeIndex]);
                    metricsPayload.broadband.push({
                        positionId,
                        value: Number.isFinite(broadbandValue) ? broadbandValue : null
                    });
                }

                if (spectralData && hasArrayLikeLength(spectralData.times_ms)) {
                    const spectralTimeIndex = findLastIndexBeforeOrEqual(spectralData.times_ms, timestamp);
                    if (spectralTimeIndex !== -1) {
                        const snapshot = sliceSpectralSnapshot(spectralData, spectralTimeIndex);
                        if (snapshot) {
                            metricsPayload.spectral.push({
                                positionId,
                                labels: snapshot.labels,
                                values: snapshot.values
                            });
                        }
                    }
                }
            });

            dispatch(actions.markerSetMetrics(markerId, metricsPayload));
        };
    }

    function addMarkerAtTapIntent() {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') {
                return;
            }

            const state = getState();
            const tapState = state?.interaction?.tap;
            if (!tapState?.isActive || !Number.isFinite(tapState.timestamp) || !tapState.position) {
                return;
            }

            dispatch(actions.markerAdd(tapState.timestamp, { positionId: tapState.position }));
        };
    }

    /**
     * Creates a marker from a keyboard shortcut. The thunk determines the best
     * timestamp based on the payload, the active tap line, or the centre of the
     * current viewport.
     *
     * @param {Object} [payload] - Optional overrides supplied by the caller.
     * @param {number} [payload.timestamp] - Explicit timestamp in milliseconds.
     * @param {string} [payload.note] - Optional note to store with the marker.
     * @param {string} [payload.color] - Optional colour override.
     * @returns {Function} Thunk function that can be dispatched.
     */
    function createMarkerFromKeyboardIntent(payload = {}) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function') {
                return;
            }

            const state = typeof getState === 'function' ? getState() : null;
            const markersState = state?.markers || {};
            const beforeCount = Array.isArray(markersState.allIds) ? markersState.allIds.length : 0;

            let timestamp = Number(payload.timestamp);
            const tapState = state?.interaction?.tap;
            if (!Number.isFinite(timestamp) && tapState?.isActive) {
                const tapTimestamp = Number(tapState.timestamp);
                if (Number.isFinite(tapTimestamp)) {
                    timestamp = tapTimestamp;
                }
            }
            if (!Number.isFinite(timestamp)) {
                const viewport = typeof viewSelectors.selectViewport === 'function'
                    ? viewSelectors.selectViewport(state)
                    : state?.view?.viewport || {};
                if (Number.isFinite(viewport?.min) && Number.isFinite(viewport?.max)) {
                    timestamp = Math.round((viewport.min + viewport.max) / 2);
                }
            }
            if (!Number.isFinite(timestamp)) {
                return;
            }

            const extras = {};
            if (typeof payload.positionId === 'string' && payload.positionId.trim()) {
                extras.positionId = payload.positionId.trim();
            } else if (tapState?.position) {
                extras.positionId = tapState.position;
            } else {
                const availablePositions = Array.isArray(state?.view?.availablePositions)
                    ? state.view.availablePositions
                        .map(pos => typeof pos === 'string' ? pos.trim() : '')
                        .filter(Boolean)
                    : [];
                if (availablePositions.length === 1) {
                    extras.positionId = availablePositions[0];
                }
            }
            if (typeof payload.note === 'string') {
                extras.note = payload.note;
            }
            if (typeof payload.color === 'string') {
                extras.color = payload.color;
            }
            if (payload.metrics) {
                extras.metrics = payload.metrics;
            }

            dispatch(actions.markerAdd(timestamp, extras));

            if (typeof getState !== 'function') {
                return;
            }

            const updatedState = getState();
            const updatedMarkers = updatedState?.markers || {};
            const afterIds = Array.isArray(updatedMarkers.allIds) ? updatedMarkers.allIds : [];

            if (afterIds.length <= beforeCount) {
                return;
            }

            const newMarkerId = updatedMarkers.selectedId;
            if (Number.isFinite(newMarkerId)) {
                dispatch(computeMarkerMetricsIntent(newMarkerId));
            }
        };
    }

    function nudgeSelectedMarkerIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') {
                return;
            }

            const { key } = payload || {};
            if (key !== 'ArrowLeft' && key !== 'ArrowRight') {
                return;
            }

            const state = getState();
            const selectedMarker = typeof markerSelectors.selectSelectedMarker === 'function'
                ? markerSelectors.selectSelectedMarker(state)
                : null;
            if (!selectedMarker) {
                return;
            }

            const direction = key === 'ArrowLeft' ? -1 : 1;
            const stepSize = Number.isFinite(state?.interaction?.keyboard?.stepSizeMs)
                ? state.interaction.keyboard.stepSizeMs
                : 1000;
            const viewport = typeof viewSelectors.selectViewport === 'function'
                ? viewSelectors.selectViewport(state)
                : state?.view?.viewport || {};
            const viewportMin = Number.isFinite(viewport?.min) ? viewport.min : -Infinity;
            const viewportMax = Number.isFinite(viewport?.max) ? viewport.max : Infinity;

            const currentTimestamp = Number(selectedMarker.timestamp);
            if (!Number.isFinite(currentTimestamp)) {
                return;
            }

            const rawTimestamp = currentTimestamp + (direction * stepSize);
            const clampedTimestamp = Math.min(Math.max(rawTimestamp, viewportMin), viewportMax);
            if (clampedTimestamp === currentTimestamp) {
                return;
            }

            dispatch(actions.markerUpdate(selectedMarker.id, { timestamp: clampedTimestamp }));
        };
    }

    app.features = app.features || {};
    app.features.markers = app.features.markers || {};
    app.features.markers.thunks = {
        computeMarkerMetricsIntent,
        addMarkerAtTapIntent,
        createMarkerFromKeyboardIntent,
        nudgeSelectedMarkerIntent
    };
})(window.NoiseSurveyApp);
