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
    const viewThunks = app.features?.view?.thunks || {};
    const markerThunks = app.features?.markers?.thunks || {};

    function handleUndoRedoIntent({ direction }) {
        return (dispatch) => {
            if (direction === 'undo') dispatch(app.actions.undo());
            else if (direction === 'redo') dispatch(app.actions.redo());
        };
    }

    app.thunks = {
        ...markerThunks,
        ...regionThunks,
        ...interactionThunks,
        ...audioThunks,
        ...viewThunks,
        handleUndoRedoIntent,
    };
})(window.NoiseSurveyApp);
