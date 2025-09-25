// noise_survey_analysis/static/js/core/actions.js

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
        STATE_REHYDRATED: 'STATE_REHYDRATED',

        // Interaction
        TAP: 'TAP',
        HOVER: 'HOVER',
        KEY_NAV: 'KEY_NAV',
        AUDIO_PLAY_PAUSE_TOGGLE: 'audio/PLAY_PAUSE_TOGGLE',
        DRAG_TOOL_CHANGED: 'interaction/dragToolChanged',

        // View
        VIEWPORT_CHANGE: 'VIEWPORT_CHANGE',
        PARAM_CHANGE: 'view/PARAM_CHANGE',
        VIEW_TOGGLE: 'view/VIEW_TOGGLE',
        VISIBILITY_CHANGE: 'VISIBILITY_CHANGE',
        HOVER_TOGGLE: 'HOVER_TOGGLE',
        POSITION_CHART_OFFSET_SET: 'view/positionChartOffsetSet',
        POSITION_AUDIO_OFFSET_SET: 'view/positionAudioOffsetSet',
        STEP_SIZE_CALCULATED: 'view/STEP_SIZE_CALCULATED',

        COMPARISON_MODE_ENTERED: 'view/comparisonModeEntered',
        COMPARISON_MODE_EXITED: 'view/comparisonModeExited',
        COMPARISON_POSITIONS_UPDATED: 'view/comparisonPositionsUpdated',
        COMPARISON_SLICE_UPDATED: 'view/comparisonSliceUpdated',

        // Markers
        MARKER_ADDED: 'markers/markerAdded',
        MARKER_REMOVED: 'markers/markerRemoved',
        MARKER_UPDATED: 'markers/markerUpdated',
        MARKER_SELECTED: 'markers/markerSelected',
        MARKER_NOTE_SET: 'markers/markerNoteSet',
        MARKER_COLOR_SET: 'markers/markerColorSet',
        MARKER_METRICS_SET: 'markers/markerMetricsSet',
        MARKERS_REPLACED: 'markers/markersReplaced',

        // Regions
        REGION_ADDED: 'markers/regionAdded',
        REGIONS_ADDED: 'markers/regionsAdded',
        REGION_UPDATED: 'markers/regionUpdated',
        REGION_REMOVED: 'markers/regionRemoved',
        REGION_SELECTED: 'markers/regionSelected',
        REGION_SELECTION_CLEARED: 'markers/regionSelectionCleared',
        REGION_NOTE_SET: 'markers/regionNoteSet',
        REGION_COLOR_SET: 'markers/regionColorSet',
        REGION_METRICS_SET: 'markers/regionMetricsSet',
        REGION_ADD_AREA_MODE_SET: 'markers/regionAddAreaModeSet',
        REGION_MERGE_MODE_SET: 'markers/regionMergeModeSet',
        REGIONS_REPLACED: 'markers/regionsReplaced',
        REGION_VISIBILITY_SET: 'regions/visibilitySet',

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
        rehydrateState: (state) => ({ type: actionTypes.STATE_REHYDRATED, payload: { state } }),

        tap: (timestamp, position, sourceChartName) => ({ 
            type: actionTypes.TAP, 
            payload: { timestamp, position, sourceChartName } }),

        hover: (payload) => ({ type: actionTypes.HOVER, payload }),

        keyNav: (direction) => ({ type: actionTypes.KEY_NAV, payload: { direction } }),

        dragToolChanged: (tool) => ({ type: actionTypes.DRAG_TOOL_CHANGED, payload: { tool } }),

        paramChange: (parameter) => ({ type: actionTypes.PARAM_CHANGE, payload: { parameter } }),

        viewToggle: (newViewType) => ({ type: actionTypes.VIEW_TOGGLE, payload: { newViewType } }),
        
        viewportChange: (min, max) => ({ type: actionTypes.VIEWPORT_CHANGE, payload: { min, max } }),

        positionChartOffsetSet: (positionId, offsetMs) => ({
            type: actionTypes.POSITION_CHART_OFFSET_SET,
            payload: { positionId, offsetMs }
        }),

        positionAudioOffsetSet: (positionId, offsetMs) => ({
            type: actionTypes.POSITION_AUDIO_OFFSET_SET,
            payload: { positionId, offsetMs }
        }),

        visibilityChange: (chartName, isVisible) => ({ 
            type: actionTypes.VISIBILITY_CHANGE, 
            payload: { chartName, isVisible } }),

        hoverToggle: (isActive) => ({ type: actionTypes.HOVER_TOGGLE, payload: { isActive } }),

        stepSizeCalculated: (stepSizeMs) => ({ type: actionTypes.STEP_SIZE_CALCULATED, payload: { stepSizeMs } }),

        comparisonModeEntered: () => ({ type: actionTypes.COMPARISON_MODE_ENTERED }),

        comparisonModeExited: () => ({ type: actionTypes.COMPARISON_MODE_EXITED }),

        comparisonPositionsUpdated: (includedPositions) => ({
            type: actionTypes.COMPARISON_POSITIONS_UPDATED,
            payload: { includedPositions }
        }),

        comparisonSliceUpdated: (start, end) => ({
            type: actionTypes.COMPARISON_SLICE_UPDATED,
            payload: { start, end }
        }),

        markerAdd: (timestamp, extras = {}) => ({
            type: actionTypes.MARKER_ADDED,
            payload: {
                timestamp,
                note: typeof extras.note === 'string' ? extras.note : undefined,
                color: extras.color,
                metrics: extras.metrics
            }
        }),

        markerRemove: (id) => ({ type: actionTypes.MARKER_REMOVED, payload: { id } }),

        markerUpdate: (id, changes) => ({ type: actionTypes.MARKER_UPDATED, payload: { id, changes } }),

        markerSelect: (id) => ({ type: actionTypes.MARKER_SELECTED, payload: { id } }),

        markerSetNote: (id, note) => ({ type: actionTypes.MARKER_NOTE_SET, payload: { id, note } }),

        markerSetColor: (id, color) => ({ type: actionTypes.MARKER_COLOR_SET, payload: { id, color } }),

        markerSetMetrics: (id, metrics) => ({ type: actionTypes.MARKER_METRICS_SET, payload: { id, metrics } }),

        markersReplace: (markers, options = {}) => ({
            type: actionTypes.MARKERS_REPLACED,
            payload: {
                markers,
                enabled: typeof options.enabled === 'boolean' ? options.enabled : undefined,
                selectedId: Number.isFinite(options.selectedId) ? options.selectedId : undefined
            }
        }),

        regionAdd: (positionId, start, end) => ({
            type: actionTypes.REGION_ADDED,
            payload: { positionId, start, end }
        }),

        regionsAdded: (regions) => ({
            type: actionTypes.REGIONS_ADDED,
            payload: { regions }
        }),

        regionUpdate: (id, changes) => ({
            type: actionTypes.REGION_UPDATED,
            payload: { id, changes }
        }),

        regionRemove: (id) => ({ type: actionTypes.REGION_REMOVED, payload: { id } }),

        regionSelect: (id) => ({ type: actionTypes.REGION_SELECTED, payload: { id } }),

        regionClearSelection: () => ({ type: actionTypes.REGION_SELECTION_CLEARED }),

        regionSetNote: (id, note) => ({ type: actionTypes.REGION_NOTE_SET, payload: { id, note } }),

        regionSetColor: (id, color) => ({ type: actionTypes.REGION_COLOR_SET, payload: { id, color } }),

        regionSetMetrics: (id, metrics) => ({ type: actionTypes.REGION_METRICS_SET, payload: { id, metrics } }),

        regionReplaceAll: (regions) => ({ type: actionTypes.REGIONS_REPLACED, payload: { regions } }),

        regionVisibilitySet: (config) => ({
            type: actionTypes.REGION_VISIBILITY_SET,
            payload: {
                showPanel: typeof config?.showPanel === 'boolean' ? config.showPanel : undefined,
                showOverlays: typeof config?.showOverlays === 'boolean' ? config.showOverlays : undefined,
            }
        }),

        regionSetAddAreaMode: (regionId) => ({
            type: actionTypes.REGION_ADD_AREA_MODE_SET,
            payload: { regionId: Number.isFinite(regionId) ? regionId : null }
        }),

        regionSetMergeMode: (isActive) => ({
            type: actionTypes.REGION_MERGE_MODE_SET,
            payload: { isActive: Boolean(isActive) }
        }),

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