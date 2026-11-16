// noise_survey_analysis/static/js/features/layout/layoutSelectors.js

/**
 * @fileoverview Selectors for the `layout` state slice.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    function selectLayoutState(state) {
        return state?.layout || app.features?.layout?.initialState || {};
    }

    /** Saved order, or null for the default (data) order. */
    function selectPositionOrder(state) {
        return selectLayoutState(state).positionOrder ?? null;
    }

    /**
     * Applies the saved order to a list of position ids. Unknown ids in the saved order are
     * dropped and positions missing from it are appended in their original order.
     */
    function selectOrderedPositions(state, positionIds) {
        const ids = Array.isArray(positionIds) ? positionIds : [];
        const saved = selectPositionOrder(state);
        if (!Array.isArray(saved) || !saved.length) {
            return ids.slice();
        }
        const known = saved.filter(id => ids.includes(id));
        return [...known, ...ids.filter(id => !known.includes(id))];
    }

    function selectSpectrogramMode(state, positionId) {
        return selectLayoutState(state).spectrogramMode?.[positionId] || 'full';
    }

    function selectYAxisMode(state) {
        return selectLayoutState(state).yAxisMode || 'auto';
    }

    function selectFitToWindow(state) {
        return selectLayoutState(state).fitToWindow !== false;
    }

    function selectWheelZoomLock(state) {
        return Boolean(selectLayoutState(state).wheelZoomLock);
    }

    function selectFrequencyDockOpen(state) {
        return Boolean(selectLayoutState(state).frequencyDockOpen);
    }

    app.features = app.features || {};
    app.features.layout = app.features.layout || {};
    app.features.layout.selectors = {
        selectLayoutState,
        selectPositionOrder,
        selectOrderedPositions,
        selectSpectrogramMode,
        selectYAxisMode,
        selectFitToWindow,
        selectWheelZoomLock,
        selectFrequencyDockOpen
    };
})(window.NoiseSurveyApp);
