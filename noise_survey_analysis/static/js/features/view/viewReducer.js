// noise_survey_analysis/static/js/features/view/viewReducer.js

/**
 * @fileoverview Defines the reducer responsible for managing the view slice of state.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const initialComparisonState = {
        isActive: false,
        start: null,
        end: null,
        includedPositions: []
    };

    const initialViewState = {
        availablePositions: [],
        globalViewType: 'log',
        selectedParameter: 'LZeq',
        viewport: { min: null, max: null },
        chartVisibility: {},
        displayDetails: {},
        hoverEnabled: true,
        mode: 'normal',
        comparison: { ...initialComparisonState }
    };

    function ensureAvailablePositions(availablePositions) {
        return Array.isArray(availablePositions) ? [...availablePositions] : [];
    }

    function viewReducer(state = initialViewState, action) {
        switch (action.type) {
            case actionTypes.INITIALIZE_STATE: {
                const availablePositions = ensureAvailablePositions(action.payload?.availablePositions);
                return {
                    ...state,
                    availablePositions,
                    selectedParameter: action.payload?.selectedParameter ?? state.selectedParameter,
                    viewport: action.payload?.viewport ?? state.viewport,
                    chartVisibility: action.payload?.chartVisibility ?? state.chartVisibility,
                    mode: 'normal',
                    comparison: {
                        ...initialComparisonState,
                        includedPositions: availablePositions
                    }
                };
            }

            case actionTypes.VIEWPORT_CHANGE:
                return {
                    ...state,
                    viewport: action.payload
                };

            case actionTypes.PARAM_CHANGE:
                return {
                    ...state,
                    selectedParameter: action.payload?.parameter ?? state.selectedParameter
                };

            case actionTypes.VIEW_TOGGLE:
                return {
                    ...state,
                    globalViewType: action.payload?.newViewType ?? state.globalViewType
                };

            case actionTypes.VISIBILITY_CHANGE:
                return {
                    ...state,
                    chartVisibility: {
                        ...state.chartVisibility,
                        [action.payload?.chartName]: action.payload?.isVisible
                    }
                };

            case actionTypes.HOVER_TOGGLE:
                return {
                    ...state,
                    hoverEnabled: action.payload?.isActive ?? state.hoverEnabled
                };

            case actionTypes.COMPARISON_MODE_ENTERED: {
                const availablePositions = ensureAvailablePositions(state.availablePositions);
                return {
                    ...state,
                    mode: 'comparison',
                    comparison: {
                        ...state.comparison,
                        isActive: true,
                        start: null,
                        end: null,
                        includedPositions: availablePositions
                    }
                };
            }

            case actionTypes.COMPARISON_MODE_EXITED: {
                const availablePositions = ensureAvailablePositions(state.availablePositions);
                return {
                    ...state,
                    mode: 'normal',
                    comparison: {
                        ...initialComparisonState,
                        includedPositions: availablePositions
                    }
                };
            }

            case actionTypes.COMPARISON_POSITIONS_UPDATED: {
                const availablePositions = ensureAvailablePositions(state.availablePositions);
                const incoming = ensureAvailablePositions(action.payload?.includedPositions);
                const incomingSet = new Set(incoming);
                const filtered = availablePositions.filter(pos => incomingSet.has(pos));
                return {
                    ...state,
                    comparison: {
                        ...state.comparison,
                        includedPositions: filtered
                    }
                };
            }

            case actionTypes.COMPARISON_SLICE_UPDATED: {
                const rawStart = Number(action.payload?.start);
                const rawEnd = Number(action.payload?.end);
                const hasValidBounds = Number.isFinite(rawStart) && Number.isFinite(rawEnd) && rawStart !== rawEnd;

                const nextStart = hasValidBounds ? Math.min(rawStart, rawEnd) : null;
                const nextEnd = hasValidBounds ? Math.max(rawStart, rawEnd) : null;

                if (state.comparison.start === nextStart && state.comparison.end === nextEnd) {
                    return state;
                }

                return {
                    ...state,
                    comparison: {
                        ...state.comparison,
                        start: nextStart,
                        end: nextEnd
                    }
                };
            }

            default:
                return state;
        }
    }

    app.features = app.features || {};
    app.features.view = {
        initialState: initialViewState,
        initialComparisonState,
        viewReducer
    };
})(window.NoiseSurveyApp);
