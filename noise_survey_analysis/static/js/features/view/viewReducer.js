// noise_survey_analysis/static/js/features/view/viewReducer.js

/**
 * @fileoverview Defines the reducer responsible for managing the view slice of state.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;
    const constants = app.constants || {};
    const sidePanelTabs = constants.sidePanelTabs || {};
    const DEFAULT_ACTIVE_TAB = Number.isFinite(sidePanelTabs.regions)
        ? sidePanelTabs.regions
        : 0;

    const initialComparisonState = {
        isActive: false,
        start: null,
        end: null,
        includedPositions: []
    };

    const initialViewState = {
        availablePositions: [],
        positionChartOffsets: {},
        positionAudioOffsets: {},
        positionEffectiveOffsets: {},
        positionDisplayTitles: {},
        chartVisibility: {},
        viewport: { min: null, max: null },
        globalViewType: 'log',
        selectedParameter: 'LZeq',
        hoverEnabled: true,
        activeSidePanelTab: DEFAULT_ACTIVE_TAB,
        logViewThresholdSeconds: null,  // null = auto-calculated from data
        mode: 'normal',
        comparison: { ...initialComparisonState }
    };

    function normalizeTabIndex(rawValue, fallback) {
        const numeric = Number(rawValue);
        if (!Number.isFinite(numeric)) {
            return Number.isFinite(fallback) ? fallback : DEFAULT_ACTIVE_TAB;
        }
        const floored = Math.floor(numeric);
        return floored >= 0 ? floored : 0;
    }

    function ensureAvailablePositions(availablePositions) {
        return Array.isArray(availablePositions) ? [...availablePositions] : [];
    }

    function sanitizeDisplayTitle(rawTitle, fallback) {
        if (typeof rawTitle !== 'string') {
            return fallback;
        }
        const trimmed = rawTitle.trim();
        return trimmed.length ? trimmed : fallback;
    }

    function normalizeDisplayTitles(rawTitles, positions) {
        const normalized = {};
        const source = rawTitles && typeof rawTitles === 'object' ? rawTitles : {};
        positions.forEach(pos => {
            normalized[pos] = sanitizeDisplayTitle(source[pos], pos);
        });
        return normalized;
    }

    const MAX_OFFSET_MS = 3600000;

    function clampOffsetMs(rawValue) {
        if (!Number.isFinite(rawValue)) {
            return 0;
        }
        const rounded = Math.round(rawValue);
        return Math.max(-MAX_OFFSET_MS, Math.min(MAX_OFFSET_MS, rounded));
    }

    function normalizeOffsets(rawOffsets, positions) {
        const normalized = {};
        positions.forEach(pos => {
            const raw = Number(rawOffsets?.[pos]);
            normalized[pos] = clampOffsetMs(raw);
        });
        return normalized;
    }

    function computeEffectiveOffsets(chartOffsets, audioOffsets, positions) {
        const effective = {};
        positions.forEach(pos => {
            const chart = Number(chartOffsets?.[pos]) || 0;
            const audio = Number(audioOffsets?.[pos]) || 0;
            effective[pos] = chart + audio;
        });
        return effective;
    }

    function viewReducer(state = initialViewState, action) {
        switch (action.type) {
            case actionTypes.INITIALIZE_STATE: {
                const availablePositions = ensureAvailablePositions(action.payload?.availablePositions);
                const fallbackOffsets = availablePositions.reduce((acc, pos) => {
                    acc[pos] = 0;
                    return acc;
                }, {});

                const initialChartOffsets = normalizeOffsets(
                    action.payload?.positionChartOffsets ?? action.payload?.positionOffsets ?? fallbackOffsets,
                    availablePositions
                );

                const initialAudioOffsets = normalizeOffsets(
                    action.payload?.positionAudioOffsets ?? fallbackOffsets,
                    availablePositions
                );

                const initialEffectiveOffsets = computeEffectiveOffsets(
                    initialChartOffsets,
                    initialAudioOffsets,
                    availablePositions
                );
                const initialDisplayTitles = normalizeDisplayTitles(
                    action.payload?.positionDisplayTitles,
                    availablePositions
                );

                return {
                    ...state,
                    availablePositions,
                    selectedParameter: action.payload?.selectedParameter ?? state.selectedParameter,
                    viewport: action.payload?.viewport ?? state.viewport,
                    chartVisibility: action.payload?.chartVisibility ?? state.chartVisibility,
                    positionChartOffsets: initialChartOffsets,
                    positionAudioOffsets: initialAudioOffsets,
                    positionEffectiveOffsets: initialEffectiveOffsets,
                    positionDisplayTitles: initialDisplayTitles,
                    activeSidePanelTab: normalizeTabIndex(action.payload?.activeSidePanelTab, state.activeSidePanelTab),
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

            case actionTypes.POSITION_CHART_OFFSET_SET: {
                const positionId = typeof action.payload?.positionId === 'string'
                    ? action.payload.positionId
                    : null;
                const rawOffset = Number(action.payload?.offsetMs);
                if (!positionId || !Number.isFinite(rawOffset)) {
                    return state;
                }

                const clampedOffset = clampOffsetMs(rawOffset);
                const currentOffset = state.positionChartOffsets?.[positionId] ?? 0;
                if (currentOffset === clampedOffset) {
                    return state;
                }

                const nextChartOffsets = {
                    ...state.positionChartOffsets,
                    [positionId]: clampedOffset
                };

                return {
                    ...state,
                    positionChartOffsets: nextChartOffsets,
                    positionEffectiveOffsets: {
                        ...state.positionEffectiveOffsets,
                        [positionId]: clampedOffset + (state.positionAudioOffsets?.[positionId] ?? 0)
                    }
                };
            }

            case actionTypes.POSITION_AUDIO_OFFSET_SET: {
                const positionId = typeof action.payload?.positionId === 'string'
                    ? action.payload.positionId
                    : null;
                const rawOffset = Number(action.payload?.offsetMs);
                if (!positionId || !Number.isFinite(rawOffset)) {
                    return state;
                }

                const clampedOffset = clampOffsetMs(rawOffset);
                const currentOffset = state.positionAudioOffsets?.[positionId] ?? 0;
                if (currentOffset === clampedOffset) {
                    return state;
                }

                const nextAudioOffsets = {
                    ...state.positionAudioOffsets,
                    [positionId]: clampedOffset
                };

                return {
                    ...state,
                    positionAudioOffsets: nextAudioOffsets,
                    positionEffectiveOffsets: {
                        ...state.positionEffectiveOffsets,
                        [positionId]: (state.positionChartOffsets?.[positionId] ?? 0) + clampedOffset
                    }
                };
            }

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

            case actionTypes.POSITION_DISPLAY_TITLES_SET: {
                const incoming = action.payload?.titles;
                if (!incoming || typeof incoming !== 'object') {
                    return state;
                }

                const availablePositions = ensureAvailablePositions(state.availablePositions);
                if (!availablePositions.length) {
                    return state;
                }

                const nextTitles = { ...state.positionDisplayTitles };
                let didUpdate = false;

                availablePositions.forEach(pos => {
                    if (!Object.prototype.hasOwnProperty.call(incoming, pos)) {
                        return;
                    }
                    const sanitized = sanitizeDisplayTitle(incoming[pos], pos);
                    if (nextTitles[pos] !== sanitized) {
                        nextTitles[pos] = sanitized;
                        didUpdate = true;
                    }
                });

                if (!didUpdate) {
                    return state;
                }

                return {
                    ...state,
                    positionDisplayTitles: nextTitles
                };
            }

            case actionTypes.VIEW_ACTIVE_SIDE_PANEL_TAB_SET: {
                const desiredIndex = normalizeTabIndex(action.payload?.index, state.activeSidePanelTab);
                if (desiredIndex === state.activeSidePanelTab) {
                    return state;
                }
                return {
                    ...state,
                    activeSidePanelTab: desiredIndex
                };
            }

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

            case actionTypes.LOG_VIEW_THRESHOLD_SET: {
                const raw = Number(action.payload?.seconds);
                const value = (Number.isFinite(raw) && raw > 0) ? raw : null;
                if (value === state.logViewThresholdSeconds) return state;
                return { ...state, logViewThresholdSeconds: value };
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
