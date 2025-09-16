// noise_survey_analysis/static/actions.js

/**
 * @fileoverview Defines action type constants and action creator functions.
 * Using constants for action types helps prevent typos and makes it easy to
 * find all usages of a particular action. Action creators are helper functions
 * that build the action object, ensuring a consistent structure.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function(app) {
    'use strict';

    // --Action Type Constants --
    const actionTypes = {

        // Initialization
        INITIALIZE_STATE: 'INITIALIZE_STATE',

        // Interaction
        TAP: 'TAP',
        HOVER: 'HOVER',
        KEY_NAV: 'KEY_NAV',
        AUDIO_PLAY_PAUSE_TOGGLE: 'audio/PLAY_PAUSE_TOGGLE',

        // View
        VIEWPORT_CHANGE: 'VIEWPORT_CHANGE',
        PARAM_CHANGE: 'view/PARAM_CHANGE',
        VIEW_TOGGLE: 'view/VIEW_TOGGLE',
        VISIBILITY_CHANGE: 'VISIBILITY_CHANGE',
        HOVER_TOGGLE: 'HOVER_TOGGLE',
        STEP_SIZE_CALCULATED: 'view/STEP_SIZE_CALCULATED',

        // Markers
        ADD_MARKER: 'ADD_MARKER',
        REMOVE_MARKER: 'REMOVE_MARKER',
        CLEAR_ALL_MARKERS: 'CLEAR_ALL_MARKERS',

        // Audio
        AUDIO_STATUS_UPDATE: 'AUDIO_STATUS_UPDATE',
        AUDIO_RATE_CHANGE_REQUEST: 'audio/RATE_CHANGE_REQUEST', 
        AUDIO_BOOST_TOGGLE_REQUEST: 'audio/BOOST_TOGGLE_REQUEST', 

        // System
        KEYBOARD_SETUP_COMPLETE: 'KEYBOARD_SETUP_COMPLETE',
        
        
    };

    // --Action Creators --
    // These functions simply create and return the action object.
    const actions = {
        initializeState: (payload) => ({ type: actionTypes.INITIALIZE_STATE, payload }),

        tap: (timestamp, position, sourceChartName) => ({ 
            type: actionTypes.TAP, 
            payload: { timestamp, position, sourceChartName } }),

        hover: (payload) => ({ type: actionTypes.HOVER, payload }),

        keyNav: (direction) => ({ type: actionTypes.KEY_NAV, payload: { direction } }),

        paramChange: (parameter) => ({ type: actionTypes.PARAM_CHANGE, payload: { parameter } }),

        viewToggle: (newViewType) => ({ type: actionTypes.VIEW_TOGGLE, payload: { newViewType } }),
        
        viewportChange: (min, max) => ({ type: actionTypes.VIEWPORT_CHANGE, payload: { min, max } }),

        visibilityChange: (chartName, isVisible) => ({ 
            type: actionTypes.VISIBILITY_CHANGE, 
            payload: { chartName, isVisible } }),

        hoverToggle: (isActive) => ({ type: actionTypes.HOVER_TOGGLE, payload: { isActive } }),

        stepSizeCalculated: (stepSizeMs) => ({ type: actionTypes.STEP_SIZE_CALCULATED, payload: { stepSizeMs } }),

        addMarker: (timestamp) => ({ type: actionTypes.ADD_MARKER, payload: { timestamp } }),

        removeMarker: (clickTimestamp) => ({ type: actionTypes.REMOVE_MARKER, payload: { clickTimestamp } }),

        clearAllMarkers: () => ({ type: actionTypes.CLEAR_ALL_MARKERS }),

        audioStatusUpdate: (status) => ({ type: actionTypes.AUDIO_STATUS_UPDATE, payload: { status } }),

        audioPlayPauseToggle: (positionId, isActive) => ({
            type: actionTypes.AUDIO_PLAY_PAUSE_TOGGLE,
            payload: { positionId, isActive }
        }),

        keyboardSetupComplete: () => ({ type: actionTypes.KEYBOARD_SETUP_COMPLETE }),

        audioRateChangeRequest: (positionId) => ({ type: actionTypes.AUDIO_RATE_CHANGE_REQUEST, payload: { positionId } }),
        
        audioBoostToggleRequest: (positionId, isBoostActive) => ({ 
            type: actionTypes.AUDIO_BOOST_TOGGLE_REQUEST, 
            payload: { positionId, isBoostActive } }),
    
    };

    app.actionTypes = actionTypes;
    app.actions = actions;

})(window.NoiseSurveyApp);