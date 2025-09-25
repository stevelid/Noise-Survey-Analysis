// noise_survey_analysis/static/js/features/markers/markersThunks.js

/**
 * @fileoverview Thunks orchestrating marker-specific business logic.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;
    const markerSelectors = app.features?.markers?.selectors || {};

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

    app.features = app.features || {};
    app.features.markers = app.features.markers || {};
    app.features.markers.thunks = {
        computeMarkerMetricsIntent
    };
})(window.NoiseSurveyApp);
