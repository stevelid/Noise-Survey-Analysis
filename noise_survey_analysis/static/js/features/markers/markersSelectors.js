// noise_survey_analysis/static/js/features/markers/markersSelectors.js

/**
 * @fileoverview Selectors for reading marker state from the global store.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const initialState = app.features?.markers?.initialState || {
        byId: {},
        allIds: [],
        selectedId: null,
        counter: 1,
        enabled: true
    };

    function selectMarkersState(state) {
        return state?.markers || initialState;
    }

    function selectMarkersById(state) {
        return selectMarkersState(state).byId || {};
    }

    function selectAllMarkers(state) {
        const markersState = selectMarkersState(state);
        return markersState.allIds.map(id => markersState.byId[id]).filter(Boolean);
    }

    function selectMarkersByPosition(state, positionId) {
        if (!positionId) {
            return [];
        }
        const markersState = selectMarkersState(state);
        return markersState.allIds
            .map(id => markersState.byId[id])
            .filter(marker => marker && marker.positionId === positionId);
    }

    function selectMarkerById(state, id) {
        const markerId = Number(id);
        if (!Number.isFinite(markerId)) {
            return null;
        }
        return selectMarkersById(state)[markerId] || null;
    }

    function selectSelectedMarker(state) {
        const markersState = selectMarkersState(state);
        if (!Number.isFinite(markersState.selectedId)) {
            return null;
        }
        return markersState.byId[markersState.selectedId] || null;
    }

    function selectAreMarkersEnabled(state) {
        return Boolean(selectMarkersState(state).enabled !== false);
    }

    function selectMarkerTimestamps(state) {
        return selectAllMarkers(state).map(marker => marker.timestamp).filter(timestamp => Number.isFinite(timestamp));
    }

    function selectGlobalMarkers(state) {
        return selectAllMarkers(state).filter(marker => marker?.positionId === undefined || marker.positionId === null);
    }

    function selectClosestMarkerToTimestamp(state, timestamp, positionId = null) {
        const numericTimestamp = Number(timestamp);
        if (!Number.isFinite(numericTimestamp)) {
            return { marker: null, distance: Infinity };
        }
        let closestMarker = null;
        let smallestDistance = Infinity;
        const poolByPosition = positionId ? selectMarkersByPosition(state, positionId) : [];
        let pool;
        if (positionId) {
            pool = poolByPosition.length ? poolByPosition : selectGlobalMarkers(state);
        } else {
            pool = selectAllMarkers(state);
        }
        pool.forEach(marker => {
            const markerTimestamp = Number(marker?.timestamp);
            if (!Number.isFinite(markerTimestamp)) {
                return;
            }
            const distance = Math.abs(markerTimestamp - numericTimestamp);
            if (distance < smallestDistance) {
                smallestDistance = distance;
                closestMarker = marker;
            }
        });
        return { marker: closestMarker, distance: smallestDistance };
    }

    app.features = app.features || {};
    app.features.markers = app.features.markers || {};
    app.features.markers.selectors = {
        selectMarkersState,
        selectMarkersById,
        selectAllMarkers,
        selectMarkerById,
        selectSelectedMarker,
        selectAreMarkersEnabled,
        selectMarkerTimestamps,
        selectGlobalMarkers,
        selectClosestMarkerToTimestamp,
        selectMarkersByPosition
    };
})(window.NoiseSurveyApp);
