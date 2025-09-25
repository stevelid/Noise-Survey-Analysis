// noise_survey_analysis/static/js/features/view/viewThunks.js

/**
 * @fileoverview Thunks responsible for view-level intents.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const viewSelectors = app.features?.view?.selectors || {};

    function handleTabSwitchIntent(payload) {
        return function (dispatch, getState) {
            if (typeof dispatch !== 'function' || typeof getState !== 'function') {
                return;
            }

            const nextIndexRaw = payload?.newIndex;
            const nextIndex = Number.isFinite(nextIndexRaw) ? nextIndexRaw : Number(nextIndexRaw);
            const resolvedIndex = Number.isFinite(nextIndex) ? nextIndex : 0;

            const state = getState();
            const viewState = viewSelectors.selectViewState
                ? viewSelectors.selectViewState(state)
                : state?.view || {};
            const isComparisonModeActive = viewState.mode === 'comparison';

            if (resolvedIndex === 1) {
                const regionThunks = app.features?.regions?.thunks || {};
                const enterThunkCreator = regionThunks.enterComparisonModeIntent;
                if (typeof enterThunkCreator === 'function') {
                    dispatch(enterThunkCreator());
                }
                return;
            }

            if (isComparisonModeActive) {
                const regionThunks = app.features?.regions?.thunks || {};
                const exitThunkCreator = regionThunks.exitComparisonModeIntent;
                if (typeof exitThunkCreator === 'function') {
                    dispatch(exitThunkCreator());
                }
            }
        };
    }

    app.features = app.features || {};
    app.features.view = app.features.view || {};
    app.features.view.thunks = {
        ...(app.features.view.thunks || {}),
        handleTabSwitchIntent
    };
})(window.NoiseSurveyApp);
