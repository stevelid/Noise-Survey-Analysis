// noise_survey_analysis/static/js/features/layout/layoutThunks.js

/**
 * @fileoverview Thunks for the `layout` slice. Skeleton: simple intents that validate input and
 * dispatch the setter actions. Spread into `app.thunks` by thunks.js.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;

    function setPositionOrderIntent({ order }) {
        return (dispatch) => dispatch(actions.layoutPositionOrderSet(order));
    }

    /** Moves one position up (-1) or down (+1) in the effective order. */
    function movePositionIntent({ positionId, delta }) {
        return (dispatch, getState) => {
            const state = getState();
            const available = state?.view?.availablePositions || [];
            const selectors = app.features.layout.selectors;
            const order = selectors.selectOrderedPositions(state, available);
            const from = order.indexOf(positionId);
            const to = from + (delta < 0 ? -1 : 1);
            if (from < 0 || to < 0 || to >= order.length) {
                return;
            }
            const next = order.slice();
            next.splice(to, 0, next.splice(from, 1)[0]);
            dispatch(actions.layoutPositionOrderSet(next));
        };
    }

    function setSpectrogramModeIntent({ positionId, mode }) {
        return (dispatch) => dispatch(actions.layoutSpectrogramModeSet(positionId, mode));
    }

    function setYAxisModeIntent({ mode }) {
        return (dispatch) => dispatch(actions.layoutYAxisModeSet(mode));
    }

    function setFitToWindowIntent({ enabled }) {
        return (dispatch) => dispatch(actions.layoutFitToWindowSet(enabled));
    }

    function setWheelZoomLockIntent({ locked }) {
        return (dispatch) => dispatch(actions.layoutWheelZoomLockSet(locked));
    }

    function setFrequencyDockOpenIntent({ open }) {
        return (dispatch) => dispatch(actions.layoutFrequencyDockOpenSet(open));
    }

    app.features = app.features || {};
    app.features.layout = app.features.layout || {};
    app.features.layout.thunks = {
        setPositionOrderIntent,
        movePositionIntent,
        setSpectrogramModeIntent,
        setYAxisModeIntent,
        setFitToWindowIntent,
        setWheelZoomLockIntent,
        setFrequencyDockOpenIntent
    };
})(window.NoiseSurveyApp);
