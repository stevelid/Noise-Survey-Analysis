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
    const constants = app.constants || {};
    const sidePanelTabs = constants.sidePanelTabs || {};
    console.log("[Markers] sidePanelTabs", sidePanelTabs); //debug
    const SIDE_PANEL_TAB_MARKERS = Number.isFinite(sidePanelTabs.markers)
        ? sidePanelTabs.markers
        : 1;

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

    function selectMarkerIntent(markerId) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function') {
                return;
            }

            const normalizedId = Number(markerId);
            if (!Number.isFinite(normalizedId)) {
                dispatch(actions.markerSelect(null));
                return;
            }

            const state = typeof getState === 'function' ? getState() : null;
            const currentSelectedId = Number.isFinite(state?.markers?.selectedId)
                ? state.markers.selectedId
                : null;

            if (currentSelectedId === normalizedId) {
                return;
            }

            dispatch(actions.markerSelect(normalizedId));
            if (typeof actions.regionClearSelection === 'function') {
                dispatch(actions.regionClearSelection());
            }
            if (typeof actions.setActiveSidePanelTab === 'function') {
                console.log('[markersThunks] dispatching setActiveSidePanelTab'); // DEBUG
                dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_MARKERS));
            }
        };
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

/**
     * The canonical thunk for creating a marker. It determines the best
     * timestamp and position based on the payload, active tap line, or viewport center.
     * After creation, it computes metrics and switches to the marker panel.
     *
     * @param {Object} [payload={}] - Optional overrides.
     * @param {number} [payload.timestamp] - Explicit timestamp in milliseconds.
     * @param {string} [payload.positionId] - Explicit position ID.
     * @param {string} [payload.note] - Optional note to store with the marker.
     * @param {string} [payload.color] - Optional colour override.
     */
function createMarkerIntent(payload = {}) {
    return function (dispatch, getState) {
        if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') {
            return;
        }

        const state = getState();
        const markersState = state.markers || {};
        const beforeCount = Array.isArray(markersState.allIds) ? markersState.allIds.length : 0;

        // 1. Determine timestamp (Payload > Tap > Viewport Center)
        let timestamp = Number(payload.timestamp);
        const tapState = state.interaction?.tap;
        if (!Number.isFinite(timestamp) && tapState?.isActive) {
            const tapTimestamp = Number(tapState.timestamp);
            if (Number.isFinite(tapTimestamp)) {
                timestamp = tapTimestamp;
            }
        }
        if (!Number.isFinite(timestamp)) {
            const viewport = viewSelectors.selectViewport ? viewSelectors.selectViewport(state) : (state.view?.viewport || {});
            if (Number.isFinite(viewport.min) && Number.isFinite(viewport.max)) {
                timestamp = Math.round((viewport.min + viewport.max) / 2);
            }
        }
        if (!Number.isFinite(timestamp)) {
            return; // Cannot create a marker without a timestamp
        }

        // 2. Gather extras, determining positionId (Payload > Tap > Single Available Position)
        const extras = {};
        if (typeof payload.positionId === 'string' && payload.positionId.trim()) {
            extras.positionId = payload.positionId.trim();
        } else if (tapState?.position) {
            extras.positionId = tapState.position;
        } else {
            const availablePositions = Array.isArray(state.view?.availablePositions)
                ? state.view.availablePositions.filter(Boolean)
                : [];
            if (availablePositions.length === 1) {
                extras.positionId = availablePositions[0];
            }
        }
        if (typeof payload.note === 'string') extras.note = payload.note;
        if (typeof payload.color === 'string') extras.color = payload.color;
        if (payload.metrics) extras.metrics = payload.metrics;


        // 3. Dispatch the creation action
        dispatch(actions.markerAdd(timestamp, extras));

        // 4. Handle side effects after state update
        const updatedState = getState();
        const updatedMarkers = updatedState.markers || {};
        const afterIds = Array.isArray(updatedMarkers.allIds) ? updatedMarkers.allIds : [];

        // If a marker was successfully added...
        if (afterIds.length > beforeCount) {
            const newMarkerId = updatedMarkers.selectedId;
            if (Number.isFinite(newMarkerId)) {
                // a. Compute its metrics
                dispatch(computeMarkerMetricsIntent(newMarkerId));
            }
            // b. Switch to the markers panel
            dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_MARKERS));
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
        selectMarkerIntent,
        computeMarkerMetricsIntent,
        createMarkerIntent,
        nudgeSelectedMarkerIntent
    };
})(window.NoiseSurveyApp);
