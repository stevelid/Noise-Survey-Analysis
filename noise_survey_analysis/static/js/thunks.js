// noise_survey_analysis/static/js/thunks.js

/**
 * @fileoverview Aggregates thunks from feature modules into a single facade.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const regionThunks = app.features?.regions?.thunks || {};
    const interactionThunks = app.features?.interaction?.thunks || {};
    const audioThunks = app.features?.audio?.thunks || {};

    app.thunks = {
        ...regionThunks,
        ...interactionThunks,
        ...audioThunks
    };
})(window.NoiseSurveyApp);
