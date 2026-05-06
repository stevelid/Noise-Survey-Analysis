// tests/history.test.js

import { describe, it, expect, beforeEach } from 'vitest';
import './loadCoreModules.js';

const app = window.NoiseSurveyApp;

// Helper: build a fresh wrapped store for each test
function freshStore() {
    app.history.reset();
    // createStore internally wraps with withHistory when app.history is available
    return app.createStore(app.rootReducer);
}

describe('history', () => {

    describe('exports', () => {
        it('isUndoableAction identifies undoable action types', () => {
            expect(app.history.isUndoableAction({ type: app.actionTypes.REGION_ADDED })).toBe(true);
            expect(app.history.isUndoableAction({ type: app.actionTypes.REGION_COLOR_SET })).toBe(true);
            expect(app.history.isUndoableAction({ type: app.actionTypes.MARKER_ADDED })).toBe(true);
            expect(app.history.isUndoableAction({ type: app.actionTypes.MARKER_COLOR_SET })).toBe(true);
            expect(app.history.isUndoableAction({ type: app.actionTypes.POSITION_CHART_OFFSET_SET })).toBe(true);
            expect(app.history.isUndoableAction({ type: app.actionTypes.TAP })).toBe(false);
            expect(app.history.isUndoableAction({ type: app.actionTypes.HOVER })).toBe(false);
        });

        it('actions.undo and actions.redo exist', () => {
            expect(typeof app.actions.undo).toBe('function');
            expect(typeof app.actions.redo).toBe('function');
            expect(app.actions.undo()).toEqual({ type: app.actionTypes.HISTORY_UNDO });
            expect(app.actions.redo()).toEqual({ type: app.actionTypes.HISTORY_REDO });
        });
    });

    describe('test 1: regionAdd → undo removes; redo restores', () => {
        it('undo removes added region, redo restores it', () => {
            const store = freshStore();
            store.dispatch(app.actions.regionAdd('P1', 1000, 2000));
            expect(store.getState().regions.allIds).toHaveLength(1);

            store.dispatch(app.actions.undo());
            expect(store.getState().regions.allIds).toHaveLength(0);

            store.dispatch(app.actions.redo());
            expect(store.getState().regions.allIds).toHaveLength(1);
        });
    });

    describe('test 2: regionUpdate → undo restores prev bounds; redo reapplies', () => {
        it('undo restores original bounds after regionUpdate', () => {
            const store = freshStore();
            store.dispatch(app.actions.regionAdd('P1', 1000, 2000));
            const idAfterAdd = store.getState().regions.allIds[0];
            store.dispatch(app.actions.regionUpdate(idAfterAdd, { end: 5000 }));
            expect(store.getState().regions.byId[idAfterAdd].end).toBe(5000);

            store.dispatch(app.actions.undo());
            expect(store.getState().regions.byId[idAfterAdd].end).toBe(2000);

            store.dispatch(app.actions.redo());
            expect(store.getState().regions.byId[idAfterAdd].end).toBe(5000);
        });
    });

    describe('regionSetColor', () => {
        it('undo restores previous color, redo reapplies new color', () => {
            const store = freshStore();
            store.dispatch(app.actions.regionAdd('P1', 1000, 2000));
            const id = store.getState().regions.allIds[0];
            const originalColor = store.getState().regions.byId[id].color;

            store.dispatch(app.actions.regionSetColor(id, '#ff00ff'));
            expect(store.getState().regions.byId[id].color).toBe('#ff00ff');

            store.dispatch(app.actions.undo());
            expect(store.getState().regions.byId[id].color).toBe(originalColor);

            store.dispatch(app.actions.redo());
            expect(store.getState().regions.byId[id].color).toBe('#ff00ff');
        });
    });

    describe('test 3: regionRemove → undo restores; redo removes again', () => {
        it('undo restores removed region, redo removes it again', () => {
            const store = freshStore();
            store.dispatch(app.actions.regionAdd('P1', 1000, 2000));
            const id = store.getState().regions.allIds[0];
            store.dispatch(app.actions.regionRemove(id));
            expect(store.getState().regions.allIds).toHaveLength(0);

            store.dispatch(app.actions.undo());
            expect(store.getState().regions.allIds).toHaveLength(1);

            store.dispatch(app.actions.redo());
            expect(store.getState().regions.allIds).toHaveLength(0);
        });
    });

    describe('test 4: markerAdd → undo removes; markerRemove → undo restores', () => {
        it('markerAdd undo removes the marker', () => {
            const store = freshStore();
            store.dispatch(app.actions.markerAdd(5000));
            expect(store.getState().markers.allIds).toHaveLength(1);

            store.dispatch(app.actions.undo());
            expect(store.getState().markers.allIds).toHaveLength(0);
        });

        it('markerRemove undo restores the marker', () => {
            const store = freshStore();
            store.dispatch(app.actions.markerAdd(5000));
            const id = store.getState().markers.allIds[0];
            store.dispatch(app.actions.markerRemove(id));
            expect(store.getState().markers.allIds).toHaveLength(0);

            store.dispatch(app.actions.undo());
            expect(store.getState().markers.allIds).toHaveLength(1);
        });
    });

    describe('markerSetColor', () => {
        it('undo restores previous color, redo reapplies new color', () => {
            const store = freshStore();
            store.dispatch(app.actions.markerAdd(5000));
            const id = store.getState().markers.allIds[0];
            const originalColor = store.getState().markers.byId[id].color;

            store.dispatch(app.actions.markerSetColor(id, '#00ff00'));
            expect(store.getState().markers.byId[id].color).toBe('#00ff00');

            store.dispatch(app.actions.undo());
            expect(store.getState().markers.byId[id].color).toBe(originalColor);

            store.dispatch(app.actions.redo());
            expect(store.getState().markers.byId[id].color).toBe('#00ff00');
        });
    });

    describe('test 5: positionChartOffsetSet chain → undo/redo cycles', () => {
        it('undo restores 1500 after 3000; redo restores 3000', () => {
            const store = freshStore();
            store.dispatch(app.actions.positionChartOffsetSet('P1', 1500));
            store.dispatch(app.actions.positionChartOffsetSet('P1', 3000));
            expect(store.getState().view.positionChartOffsets.P1).toBe(3000);

            store.dispatch(app.actions.undo());
            expect(store.getState().view.positionChartOffsets.P1).toBe(1500);

            store.dispatch(app.actions.redo());
            expect(store.getState().view.positionChartOffsets.P1).toBe(3000);
        });
    });

    describe('test 6: non-undoable actions do not add history entries', () => {
        it('tap, hover, viewportChange, paramChange do not increment pastLength', () => {
            const store = freshStore();
            store.dispatch(app.actions.tap(100, 'P1', 'line_P1'));
            store.dispatch(app.actions.hover({ isActive: true, timestamp: 200, position: 'P1', sourceChartName: 'line_P1' }));
            store.dispatch(app.actions.viewportChange(0, 10000));
            store.dispatch(app.actions.paramChange('LAeq'));
            expect(app.history._debug().pastLength).toBe(0);
        });
    });

    describe('test 7: undo + new undoable action clears future', () => {
        it('dispatching undoable action after undo clears future', () => {
            const store = freshStore();
            store.dispatch(app.actions.regionAdd('P1', 1000, 2000));
            store.dispatch(app.actions.regionAdd('P1', 3000, 4000));
            store.dispatch(app.actions.undo()); // future now has 1 entry
            expect(app.history._debug().futureLength).toBe(1);

            store.dispatch(app.actions.markerAdd(5000)); // new undoable → clear future
            expect(app.history._debug().futureLength).toBe(0);
        });
    });

    describe('test 8: identical positionChartOffsetSet is a no-op', () => {
        it('second identical dispatch does not push another history entry', () => {
            const store = freshStore();
            store.dispatch(app.actions.positionChartOffsetSet('P1', 1500));
            expect(app.history._debug().pastLength).toBe(1);

            store.dispatch(app.actions.positionChartOffsetSet('P1', 1500));
            expect(app.history._debug().pastLength).toBe(1);
        });
    });

    describe('test 9: undo/redo themselves do not push to past', () => {
        it('pastLength reflects only the original push, not undo/redo calls', () => {
            const store = freshStore();
            store.dispatch(app.actions.regionAdd('P1', 1000, 2000));
            expect(app.history._debug().pastLength).toBe(1);

            store.dispatch(app.actions.undo());
            store.dispatch(app.actions.redo());
            // Still 1: undo moved present→future (past=0), redo moved future→past (past=1)
            expect(app.history._debug().pastLength).toBe(1);
        });
    });

    describe('replaced actions', () => {
        it('regionsReplaced is undoable', () => {
            const store = freshStore();
            store.dispatch(app.actions.regionAdd('P1', 1000, 2000));
            expect(store.getState().regions.allIds).toHaveLength(1);

            store.dispatch(app.actions.regionReplaceAll([]));
            expect(store.getState().regions.allIds).toEqual([]);

            store.dispatch(app.actions.undo());
            expect(store.getState().regions.allIds).toHaveLength(1);

            store.dispatch(app.actions.redo());
            expect(store.getState().regions.allIds).toEqual([]);
        });

        it('markersReplaced is undoable', () => {
            const store = freshStore();
            store.dispatch(app.actions.markerAdd(5000));
            expect(store.getState().markers.allIds).toHaveLength(1);

            store.dispatch(app.actions.markersReplace([]));
            expect(store.getState().markers.allIds).toEqual([]);

            store.dispatch(app.actions.undo());
            expect(store.getState().markers.allIds).toHaveLength(1);

            store.dispatch(app.actions.redo());
            expect(store.getState().markers.allIds).toEqual([]);
        });
    });

    describe('test 10: history is capped at 50 entries', () => {
        it('after 60 regionAdds, pastLength is capped at 50', () => {
            const store = freshStore();
            for (let i = 0; i < 60; i++) {
                store.dispatch(app.actions.regionAdd('P1', i * 1000, (i + 1) * 1000));
            }
            expect(app.history._debug().pastLength).toBe(50);
        });

        it('can undo 50 times but not 51 (earliest snapshot dropped)', () => {
            const store = freshStore();
            for (let i = 0; i < 60; i++) {
                store.dispatch(app.actions.regionAdd('P1', i * 1000, (i + 1) * 1000));
            }
            // Undo 50 times — should bring pastLength to 0
            for (let i = 0; i < 50; i++) {
                store.dispatch(app.actions.undo());
            }
            expect(app.history._debug().pastLength).toBe(0);
            const stateAt50 = store.getState();

            // 51st undo is a no-op
            store.dispatch(app.actions.undo());
            expect(store.getState()).toBe(stateAt50);
        });
    });
});
