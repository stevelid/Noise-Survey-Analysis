// noise_survey_analysis/static/js/features/view/viewSelectors.js

/**
 * @fileoverview Selectors for view state.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    function selectViewState(state) {
        return state?.view || {};
    }

    function selectViewport(state) {
        return selectViewState(state).viewport || { min: null, max: null };
    }

    function selectComparisonState(state) {
        return selectViewState(state).comparison || {};
    }

    app.features = app.features || {};
    app.features.view = app.features.view || {};
    app.features.view.selectors = {
        selectViewState,
        selectViewport,
        selectComparisonState
    };
})(window.NoiseSurveyApp);
