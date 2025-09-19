import { describe, it, expect, beforeEach } from 'vitest';

import '../noise_survey_analysis/static/js/store.js';
import '../noise_survey_analysis/static/js/actions.js';
import '../noise_survey_analysis/static/js/reducers.js';
import '../noise_survey_analysis/static/js/thunks.js';

const { createStore, actions, rootReducer, thunks } = window.NoiseSurveyApp;

describe('NoiseSurveyApp thunks', () => {
    let store;
    beforeEach(() => {
        store = createStore(rootReducer);
        window.NoiseSurveyApp.store = store;
    });

    it('handleTapIntent clears selection and taps when no region hit', () => {
        store.dispatch(actions.regionAdd('P1', 1000, 2000));
        const thunk = thunks.handleTapIntent({
            timestamp: 5000,
            positionId: 'P1',
            chartName: 'figure_P1_timeseries',
            modifiers: {}
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.markers.regions.selectedId).toBeNull();
        expect(state.interaction.tap.timestamp).toBe(5000);
        expect(state.interaction.tap.position).toBe('P1');
    });

    it('handleTapIntent selects region when hit', () => {
        store.dispatch(actions.regionAdd('P1', 1000, 2000));
        const thunk = thunks.handleTapIntent({
            timestamp: 1500,
            positionId: 'P1',
            chartName: 'figure_P1_timeseries',
            modifiers: {}
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.markers.regions.selectedId).toBe(1);
        expect(state.interaction.tap.timestamp).toBe(1500);
        expect(state.markers.regions.byId[1]).toBeTruthy();
    });

    it('handleTapIntent removes region on ctrl click', () => {
        store.dispatch(actions.regionAdd('P1', 1000, 2000));
        const thunk = thunks.handleTapIntent({
            timestamp: 1500,
            positionId: 'P1',
            chartName: 'figure_P1_timeseries',
            modifiers: { ctrl: true }
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.markers.regions.allIds).toHaveLength(0);
        expect(state.markers.regions.counter).toBe(2);
    });

    it('createRegionIntent adds region when bounds valid', () => {
        const thunk = thunks.createRegionIntent({
            positionId: 'P1',
            start: 1000,
            end: 2000
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.markers.regions.allIds).toHaveLength(1);
        expect(state.markers.regions.byId[1].start).toBe(1000);
        expect(state.markers.regions.byId[1].end).toBe(2000);
    });

    it('resizeSelectedRegionIntent nudges end when shift held', () => {
        store.dispatch(actions.viewportChange(0, 10000));
        store.dispatch(actions.stepSizeCalculated(1000));
        store.dispatch(actions.regionAdd('P1', 1000, 5000));
        const thunk = thunks.resizeSelectedRegionIntent({ key: 'ArrowRight', modifiers: { shift: true } });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.markers.regions.byId[1].end).toBe(6000);
    });

    it('resizeSelectedRegionIntent nudges start when alt held', () => {
        store.dispatch(actions.viewportChange(0, 10000));
        store.dispatch(actions.stepSizeCalculated(1000));
        store.dispatch(actions.regionAdd('P1', 1000, 5000));
        const thunk = thunks.resizeSelectedRegionIntent({ key: 'ArrowLeft', modifiers: { alt: true } });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.markers.regions.byId[1].start).toBe(0);
    });

    it('nudgeTapLineIntent dispatches key nav', () => {
        store.dispatch(actions.viewportChange(0, 10000));
        store.dispatch(actions.stepSizeCalculated(1000));
        store.dispatch(actions.tap(5000, 'P1', 'figure_P1_timeseries'));
        const thunk = thunks.nudgeTapLineIntent({ key: 'ArrowLeft' });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.interaction.tap.timestamp).toBe(4000);
    });

    it('enterComparisonModeIntent enables comparison mode', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1', 'P2'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        const state = store.getState();
        expect(state.view.mode).toBe('comparison');
        expect(state.view.comparison.includedPositions).toEqual(['P1', 'P2']);
    });

    it('exitComparisonModeIntent returns to normal mode', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.exitComparisonModeIntent());
        const state = store.getState();
        expect(state.view.mode).toBe('normal');
        expect(state.view.comparison.isActive).toBe(false);
    });

    it('updateIncludedPositionsIntent updates included positions', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1', 'P2'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.updateIncludedPositionsIntent({ includedPositions: ['P2'] }));
        const state = store.getState();
        expect(state.view.comparison.includedPositions).toEqual(['P2']);
    });

    it('updateComparisonSliceIntent records normalized bounds when active', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.updateComparisonSliceIntent({ start: 4000, end: 2000 }));
        const state = store.getState();
        expect(state.view.comparison.start).toBe(2000);
        expect(state.view.comparison.end).toBe(4000);
    });

    it('updateComparisonSliceIntent clears slice when bounds collapse', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.updateComparisonSliceIntent({ start: 4000, end: 2000 }));
        store.dispatch(thunks.updateComparisonSliceIntent({ start: 2500, end: 2500 }));
        const state = store.getState();
        expect(state.view.comparison.start).toBeNull();
        expect(state.view.comparison.end).toBeNull();
    });

    it('createRegionsFromComparisonIntent creates regions and exits comparison mode', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1', 'P2'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.updateComparisonSliceIntent({ start: 1000, end: 3000 }));
        store.dispatch(thunks.createRegionsFromComparisonIntent());
        const state = store.getState();
        expect(state.view.mode).toBe('normal');
        expect(state.markers.regions.allIds).toEqual([1, 2]);
        expect(state.markers.regions.byId[1].positionId).toBe('P1');
        expect(state.markers.regions.byId[2].positionId).toBe('P2');
    });
});
