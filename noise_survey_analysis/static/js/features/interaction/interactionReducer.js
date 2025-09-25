// noise_survey_analysis/static/js/features/interaction/interactionReducer.js

/**
 * @fileoverview Reducer for managing interaction state (tap, hover, keyboard, drag tools).
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const initialInteractionState = {
        tap: { isActive: false, timestamp: null, position: null, sourceChartName: null },
        hover: { isActive: false, timestamp: null, position: null, sourceChartName: null, spec_y: null },
        keyboard: { enabled: false, stepSizeMs: 300000 },
        activeDragTool: 'pan',
        pendingRegionStart: null
    };

    function clamp(value, min, max) {
        return Math.max(min, Math.min(max, value));
    }

    function interactionReducer(state = initialInteractionState, action, fullState) {
        switch (action.type) {
            case actionTypes.TAP:
                return {
                    ...state,
                    tap: { ...action.payload, isActive: true },
                    hover: { ...state.hover }
                };

            case actionTypes.HOVER:
                return {
                    ...state,
                    hover: { ...action.payload }
                };

            case actionTypes.DRAG_TOOL_CHANGED:
                return {
                    ...state,
                    activeDragTool: action.payload?.tool ?? state.activeDragTool
                };

            case actionTypes.KEY_NAV: {
                if (!state.tap.isActive) {
                    return state;
                }
                const currentTime = state.tap.timestamp;
                const step = state.keyboard.stepSizeMs;
                const viewport = fullState?.view?.viewport || {};
                const min = Number.isFinite(viewport.min) ? viewport.min : -Infinity;
                const max = Number.isFinite(viewport.max) ? viewport.max : Infinity;

                const direction = action.payload?.direction === 'left' ? -1 : 1;
                let newTimestamp = currentTime + direction * step;
                newTimestamp = clamp(newTimestamp, min, max);

                if (newTimestamp === currentTime) {
                    return state;
                }

                return {
                    ...state,
                    tap: {
                        ...state.tap,
                        timestamp: newTimestamp
                    }
                };
            }

            case actionTypes.KEYBOARD_SETUP_COMPLETE:
                return {
                    ...state,
                    keyboard: { ...state.keyboard, enabled: true }
                };

            case actionTypes.STEP_SIZE_CALCULATED:
                return {
                    ...state,
                    keyboard: { ...state.keyboard, stepSizeMs: action.payload?.stepSizeMs ?? state.keyboard.stepSizeMs }
                };

            case actionTypes.AUDIO_STATUS_UPDATE: {
                const status = action.payload?.status;
                if (!status?.is_playing?.[0]) {
                    return state;
                }
                return {
                    ...state,
                    tap: {
                        isActive: true,
                        timestamp: status.current_time?.[0] ?? state.tap.timestamp,
                        position: status.active_position_id?.[0] ?? state.tap.position,
                        sourceChartName: state.tap.sourceChartName
                    }
                };
            }

            case actionTypes.REGION_CREATION_STARTED: {
                const timestamp = Number(action.payload?.timestamp);
                const positionId = action.payload?.positionId || null;
                if (!Number.isFinite(timestamp) || !positionId) {
                    return state;
                }
                return {
                    ...state,
                    pendingRegionStart: { timestamp, positionId }
                };
            }

            case actionTypes.REGION_CREATION_CANCELLED:
                if (state.pendingRegionStart === null) {
                    return state;
                }
                return {
                    ...state,
                    pendingRegionStart: null
                };

            default:
                return state;
        }
    }

    app.features = app.features || {};
    app.features.interaction = {
        initialState: initialInteractionState,
        interactionReducer
    };
})(window.NoiseSurveyApp);
