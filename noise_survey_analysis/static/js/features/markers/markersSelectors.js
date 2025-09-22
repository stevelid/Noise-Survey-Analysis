// noise_survey_analysis/static/js/features/markers/markersSelectors.js

/**
 * @fileoverview Selectors for reading marker state from the global store.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    function selectMarkersState(state) {
        return state?.markers || { timestamps: [], enabled: true };
    }

    function selectMarkerTimestamps(state) {
        return selectMarkersState(state).timestamps;
    }

    function selectAreMarkersEnabled(state) {
        return Boolean(selectMarkersState(state).enabled);
    }

    app.features = app.features || {};
    app.features.markers = app.features.markers || {};
    app.features.markers.selectors = {
        selectMarkersState,
        selectMarkerTimestamps,
        selectAreMarkersEnabled
    };
})(window.NoiseSurveyApp);
