// noise_survey_analysis/static/js/core/history.js

/**
 * @fileoverview Higher-order reducer that adds undo/redo capability to the store.
 * History is maintained in closure-private arrays; getState() returns present only,
 * so the external state shape is unchanged.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const HISTORY_LIMIT = 50;

    // Closure-private history stacks — shared across all uses of withHistory()
    // within a single module load. Tests use reset() to clear between runs.
    let past = [];
    let future = [];

    // These are set lazily once actionTypes are available.
    const UNDOABLE_ACTION_TYPES = new Set([
        'regions/regionAdded',
        'regions/regionsAdded',
        'regions/regionUpdated',
        'regions/regionColorSet',
        'regions/regionRemoved',
        'regions/regionsReplaced',
        'markers/markerAdded',
        'markers/markerRemoved',
        'markers/markerUpdated',
        'markers/markerColorSet',
        'markers/markersReplaced',
        'view/positionChartOffsetSet',
    ]);

    function isUndoableAction(action) {
        return UNDOABLE_ACTION_TYPES.has(action && action.type);
    }

    function snapshot(state) {
        if (typeof structuredClone === 'function') {
            return structuredClone(state);
        }
        return JSON.parse(JSON.stringify(state));
    }

    function hasRelevantChange(prev, next) {
        // Referential check on the slices that matter for undo
        return (
            next.regions !== prev.regions ||
            next.markers !== prev.markers ||
            (next.view && prev.view && next.view.positionChartOffsets !== prev.view.positionChartOffsets)
        );
    }

    /**
     * Wraps a root reducer with undo/redo capability.
     * @param {Function} rootReducer
     * @returns {Function} A new reducer (state, action) => nextState
     */
    function withHistory(rootReducer) {
        return function historyReducer(state, action) {
            const { actionTypes } = app;

            // UNDO
            if (actionTypes && action.type === actionTypes.HISTORY_UNDO) {
                if (past.length === 0) return state;
                const previous = past[past.length - 1];
                past = past.slice(0, past.length - 1);
                future = [snapshot(state), ...future];
                return previous;
            }

            // REDO
            if (actionTypes && action.type === actionTypes.HISTORY_REDO) {
                if (future.length === 0) return state;
                const next = future[0];
                future = future.slice(1);
                past = [...past, snapshot(state)].slice(-HISTORY_LIMIT);
                return next;
            }

            // Run inner reducer
            const prev = state;
            const next = rootReducer(state, action);

            // Push to history only for undoable actions that actually changed relevant state
            if (isUndoableAction(action)) {
                if (next !== prev && hasRelevantChange(prev || {}, next)) {
                    past = [...past, snapshot(prev)].slice(-HISTORY_LIMIT);
                    future = []; // clear redo stack on new undoable action
                }
            }

            return next;
        };
    }

    function reset() {
        past = [];
        future = [];
    }

    function _debug() {
        return { pastLength: past.length, futureLength: future.length };
    }

    app.history = {
        withHistory,
        isUndoableAction,
        reset,
        _debug,
    };

})(window.NoiseSurveyApp);
