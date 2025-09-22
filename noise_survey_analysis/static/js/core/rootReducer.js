// noise_survey_analysis/static/js/core/rootReducer.js

/**
 * @fileoverview Root reducer that orchestrates feature reducers.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const viewFeature = app.features?.view || {};
    const interactionFeature = app.features?.interaction || {};
    const markersFeature = app.features?.markers || {};
    const regionsFeature = app.features?.regions || {};
    const audioFeature = app.features?.audio || {};

    const initialSystemState = {
        initialized: false,
        lastAction: null
    };

    function deepClone(value) {
        return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
    }

    function createInitialState() {
        return {
            view: deepClone(viewFeature.initialState),
            interaction: deepClone(interactionFeature.initialState),
            markers: deepClone(markersFeature.initialState),
            regions: deepClone(regionsFeature.initialState),
            audio: deepClone(audioFeature.initialState),
            system: deepClone(initialSystemState)
        };
    }

    function systemReducer(state = initialSystemState, action) {
        switch (action.type) {
            case actionTypes.INITIALIZE_STATE:
                return {
                    ...state,
                    initialized: true
                };

            default:
                return state;
        }
    }

    function rootReducer(state, action) {
        const previousState = state ?? createInitialState();

        const nextView = typeof viewFeature.viewReducer === 'function'
            ? viewFeature.viewReducer(previousState.view, action)
            : previousState.view;

        const nextInteraction = typeof interactionFeature.interactionReducer === 'function'
            ? interactionFeature.interactionReducer(previousState.interaction, action, previousState)
            : previousState.interaction;

        const nextMarkers = typeof markersFeature.markersReducer === 'function'
            ? markersFeature.markersReducer(previousState.markers, action, previousState)
            : previousState.markers;

        const nextRegions = typeof regionsFeature.regionsReducer === 'function'
            ? regionsFeature.regionsReducer(previousState.regions, action)
            : previousState.regions;

        const nextAudio = typeof audioFeature.audioReducer === 'function'
            ? audioFeature.audioReducer(previousState.audio, action)
            : previousState.audio;

        const nextSystem = systemReducer(previousState.system, action);

        const combinedState = {
            view: nextView,
            interaction: nextInteraction,
            markers: nextMarkers,
            regions: nextRegions,
            audio: nextAudio,
            system: nextSystem
        };

        return {
            ...combinedState,
            system: {
                ...combinedState.system,
                lastAction: action
            }
        };
    }

    const initialState = createInitialState();

    app.rootReducer = rootReducer;
    app.initialState = initialState;
    app.createInitialState = createInitialState;
})(window.NoiseSurveyApp);
