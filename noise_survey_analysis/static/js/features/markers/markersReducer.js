// noise_survey_analysis/static/js/features/markers/markersReducer.js

/**
 * @fileoverview Reducer responsible for marker timestamp state management.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const initialMarkersState = {
        timestamps: [],
        enabled: true
    };

    function addMarker(state, timestamp) {
        if (state.timestamps.includes(timestamp)) {
            return state;
        }
        const newTimestamps = [...state.timestamps, timestamp].sort((a, b) => a - b);
        return {
            ...state,
            timestamps: newTimestamps
        };
    }

    function removeClosestMarker(state, clickTimestamp, fullState) {
        const viewport = fullState?.view?.viewport;
        if (!viewport) {
            return state;
        }
        const viewportWidthMs = Number(viewport.max) - Number(viewport.min);
        const threshold = Math.max(viewportWidthMs * 0.02, 10000);

        let closestIndex = -1;
        let closestDistance = Infinity;
        state.timestamps.forEach((markerTime, index) => {
            const distance = Math.abs(markerTime - clickTimestamp);
            if (distance < threshold && distance < closestDistance) {
                closestDistance = distance;
                closestIndex = index;
            }
        });

        if (closestIndex === -1) {
            return state;
        }

        return {
            ...state,
            timestamps: state.timestamps.filter((_, index) => index !== closestIndex)
        };
    }

    function markersReducer(state = initialMarkersState, action, fullState) {
        switch (action.type) {
            case actionTypes.ADD_MARKER:
                return addMarker(state, action.payload?.timestamp);

            case actionTypes.REMOVE_MARKER: {
                const clickTimestamp = action.payload?.clickTimestamp;
                if (!Number.isFinite(clickTimestamp)) {
                    return state;
                }
                return removeClosestMarker(state, clickTimestamp, fullState);
            }

            case actionTypes.CLEAR_ALL_MARKERS:
                return {
                    ...state,
                    timestamps: []
                };

            default:
                return state;
        }
    }

    app.features = app.features || {};
    app.features.markers = app.features.markers || {};
    app.features.markers.initialState = initialMarkersState;
    app.features.markers.markersReducer = markersReducer;
})(window.NoiseSurveyApp);
