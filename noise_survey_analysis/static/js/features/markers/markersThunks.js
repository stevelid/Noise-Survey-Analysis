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

    function cloneArrayLike(values) {
        if (!values || typeof values.length !== 'number') {
            return [];
        }
        return Array.from(values);
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
                if (lineData && Array.isArray(lineData.Datetime)) {
                    timeIndex = typeof app.utils?.findAssociatedDateIndex === 'function'
                        ? app.utils.findAssociatedDateIndex(lineData, timestamp)
                        : lineData.Datetime.findLastIndex(value => Number(value) <= timestamp);
                }

                if (timeIndex !== -1 && selectedParameter && Array.isArray(lineData?.[selectedParameter])) {
                    const broadbandValue = Number(lineData[selectedParameter][timeIndex]);
                    metricsPayload.broadband.push({
                        positionId,
                        value: Number.isFinite(broadbandValue) ? broadbandValue : null
                    });
                }

                if (spectralData && Array.isArray(spectralData.times_ms)) {
                    const spectralTimeIndex = spectralData.times_ms.findLastIndex(value => Number(value) <= timestamp);
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
            const viewportMin = Number.isFinite(viewport.min) ? viewport.min : -Infinity;
            const viewportMax = Number.isFinite(viewport.max) ? viewport.max : Infinity;

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
        nudgeSelectedMarkerIntent
    };
})(window.NoiseSurveyApp);
