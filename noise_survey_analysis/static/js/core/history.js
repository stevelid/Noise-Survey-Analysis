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
        'classifications/classificationsAdded',
        'classifications/classificationsReplaced',
        'classifications/classificationUpdated',
        'classifications/classificationRemoved',
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
            next.classifications !== prev.classifications ||
            (next.view && prev.view && next.view.positionChartOffsets !== prev.view.positionChartOffsets)
        );
    }

    /**
     * Captures only the slices undo/redo owns.
     *
     * Snapshotting the whole state would mean an undo also rewinds everything the
     * user did *after* the annotation edit — viewport, audio playback, selected
     * parameter — and would restore a stale `system.lastAction`, which the audio
     * side-effect handler in app.js reads and would replay (e.g. re-sending a
     * `play` command for an old tap).
     */
    function captureSlices(state) {
        if (!state || typeof state !== 'object') {
            return null;
        }
        return {
            regions: snapshot(state.regions),
            markers: snapshot(state.markers),
            classifications: snapshot(state.classifications),
            positionChartOffsets: snapshot(state.view?.positionChartOffsets)
        };
    }

    function isEquivalent(left, right) {
        if (left === right) return true;
        if (left === undefined || right === undefined) return false;
        try {
            return JSON.stringify(left) === JSON.stringify(right);
        } catch (error) {
            return false;
        }
    }

    /**
     * Merges a captured slice set back onto the *current* state, leaving every
     * other slice — and the identity of anything that did not actually change —
     * untouched so renderers keep their cheap referential change checks.
     */
    function applySlices(state, slices, action) {
        if (!slices) {
            return state;
        }
        let nextState = state;
        const replace = (key) => {
            if (slices[key] !== undefined && !isEquivalent(nextState[key], slices[key])) {
                nextState = { ...nextState, [key]: snapshot(slices[key]) };
            }
        };
        replace('regions');
        replace('markers');
        replace('classifications');

        const currentOffsets = nextState.view?.positionChartOffsets;
        if (slices.positionChartOffsets !== undefined
            && !isEquivalent(currentOffsets, slices.positionChartOffsets)) {
            nextState = {
                ...nextState,
                view: {
                    ...nextState.view,
                    positionChartOffsets: snapshot(slices.positionChartOffsets)
                }
            };
        }

        if (nextState === state) {
            return state;
        }

        return {
            ...nextState,
            system: {
                ...nextState.system,
                lastAction: action
            }
        };
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
                future = [captureSlices(state), ...future];
                return applySlices(state, previous, action);
            }

            // REDO
            if (actionTypes && action.type === actionTypes.HISTORY_REDO) {
                if (future.length === 0) return state;
                const next = future[0];
                future = future.slice(1);
                past = [...past, captureSlices(state)].slice(-HISTORY_LIMIT);
                return applySlices(state, next, action);
            }

            // Run inner reducer
            const prev = state;
            const next = rootReducer(state, action);

            // Push to history only for undoable actions that actually changed relevant state
            if (isUndoableAction(action)) {
                if (next !== prev && hasRelevantChange(prev || {}, next)) {
                    past = [...past, captureSlices(prev)].slice(-HISTORY_LIMIT);
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
