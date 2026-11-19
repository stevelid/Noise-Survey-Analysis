// noise_survey_analysis/static/js/features/layout/layoutReducer.js

/**
 * @fileoverview Reducer for the `layout` state slice (page layout and navigation preferences).
 *
 * Skeleton only: nothing renders from this slice yet. Layout work (WP1) reads it through
 * `app.features.layout.selectors` and changes it with the `layout*Set` actions.
 *
 *   positionOrder      array of position ids in display order, or null for the default (data) order
 *   spectrogramMode    { [positionId]: 'full' | 'strip' | 'hidden' }; a missing id means 'full'
 *   yAxisMode          'auto' | 'shared' | 'locked'
 *   fitToWindow        fit chart rows to the browser window height
 *   wheelZoomLock      keep the mouse wheel bound to zoom even when the page could scroll
 *   frequencyDockOpen  frequency slice docked in the sidebar
 *   soloSaved          chart visibility to restore when Solo (O) is toggled off, or null; kept here (not in
 *                      a runtime variable) because the solo-hidden visibility is autosaved with the workspace
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const SPECTROGRAM_MODES = ['full', 'strip', 'hidden'];
    const Y_AXIS_MODES = ['auto', 'shared', 'locked'];
    const LAYOUT_SOLO_SAVED_SET = 'layout/soloSavedSet';

    const initialLayoutState = {
        positionOrder: null,
        spectrogramMode: {},
        yAxisMode: 'auto',
        fitToWindow: true,
        wheelZoomLock: false,
        frequencyDockOpen: false,
        sidePanelCollapsed: false,
        sidePanelWidth: null,
        soloSaved: null
    };

    function layoutReducer(state = initialLayoutState, action) {
        switch (action.type) {
            case actionTypes.LAYOUT_POSITION_ORDER_SET: {
                const order = action.payload?.order;
                if (order === null || order === undefined) {
                    return state.positionOrder === null ? state : { ...state, positionOrder: null };
                }
                if (!Array.isArray(order)) {
                    return state;
                }
                return { ...state, positionOrder: order.filter(id => typeof id === 'string') };
            }

            case actionTypes.LAYOUT_SPECTROGRAM_MODE_SET: {
                const { positionId, mode } = action.payload || {};
                if (typeof positionId !== 'string' || !SPECTROGRAM_MODES.includes(mode)) {
                    return state;
                }
                if (state.spectrogramMode[positionId] === mode) {
                    return state;
                }
                return { ...state, spectrogramMode: { ...state.spectrogramMode, [positionId]: mode } };
            }

            case actionTypes.LAYOUT_Y_AXIS_MODE_SET: {
                const mode = action.payload?.mode;
                if (!Y_AXIS_MODES.includes(mode) || mode === state.yAxisMode) {
                    return state;
                }
                return { ...state, yAxisMode: mode };
            }

            case actionTypes.LAYOUT_FIT_TO_WINDOW_SET: {
                const enabled = Boolean(action.payload?.enabled);
                return enabled === state.fitToWindow ? state : { ...state, fitToWindow: enabled };
            }

            case actionTypes.LAYOUT_WHEEL_ZOOM_LOCK_SET: {
                const locked = Boolean(action.payload?.locked);
                return locked === state.wheelZoomLock ? state : { ...state, wheelZoomLock: locked };
            }

            case actionTypes.LAYOUT_SIDE_PANEL_SET: {
                const { collapsed, width } = action.payload || {};
                const nextCollapsed = typeof collapsed === 'boolean' ? collapsed : state.sidePanelCollapsed;
                const nextWidth = Number.isFinite(width) && width > 0 ? width : state.sidePanelWidth;
                return nextCollapsed === state.sidePanelCollapsed && nextWidth === state.sidePanelWidth
                    ? state : { ...state, sidePanelCollapsed: nextCollapsed, sidePanelWidth: nextWidth };
            }

            case actionTypes.LAYOUT_FREQUENCY_DOCK_OPEN_SET: {
                const open = Boolean(action.payload?.open);
                return open === state.frequencyDockOpen ? state : { ...state, frequencyDockOpen: open };
            }

            case LAYOUT_SOLO_SAVED_SET: {
                const saved = action.payload?.saved;
                if (saved === null || saved === undefined) {
                    return state.soloSaved === null ? state : { ...state, soloSaved: null };
                }
                return typeof saved === 'object' && !Array.isArray(saved) ? { ...state, soloSaved: { ...saved } } : state;
            }

            default:
                return state;
        }
    }

    app.features = app.features || {};
    app.features.layout = app.features.layout || {};
    app.features.layout.initialState = initialLayoutState;
    app.features.layout.layoutReducer = layoutReducer;
    app.features.layout.constants = { SPECTROGRAM_MODES, Y_AXIS_MODES, LAYOUT_SOLO_SAVED_SET };
})(window.NoiseSurveyApp);
