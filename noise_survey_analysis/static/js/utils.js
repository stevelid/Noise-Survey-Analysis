// noise_survey_analysis/static/utils.js

/**
 * @fileoverview Contains utility functions used throughout the Noise Survey application.
 * These functions are designed to be generic and reusable across different components.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    function findAssociatedDateIndex(activeData, timestamp) {
        if (!activeData || !activeData.Datetime || activeData.Datetime.length === 0) {
            return -1;
        }
        for (let i = activeData.Datetime.length - 1; i >= 0; i--) {
            if (activeData.Datetime[i] <= timestamp) return i;
        }
        return -1;
    }

    app.utils = {
        findAssociatedDateIndex: findAssociatedDateIndex
    };
})(window.NoiseSurveyApp);