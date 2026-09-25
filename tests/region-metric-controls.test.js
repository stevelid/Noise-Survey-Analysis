import { describe, it, beforeEach, expect } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/init.js';

const app = window.NoiseSurveyApp;

function initializeSelectedRegion() {
    app.store.dispatch(app.actions.initializeState({
        availablePositions: ['P1'],
        viewport: { min: 0, max: 1000 }
    }));
    app.store.dispatch(app.actions.regionsAdded([{
        id: 1,
        positionId: 'P1',
        areas: [{ start: 4000, end: 5000 }]
    }]));
    app.store.dispatch(app.actions.regionSelect(1));
}

describe('region metric view controls', () => {
    beforeEach(() => {
        app.init.reInitializeStore();
        app.regions.invalidateMetricsCache();
        app.dataCache = {};
        app.registry = app.registry || {};
        app.registry.models = { timeSeriesSources: {}, preparedGlyphData: {} };
        initializeSelectedRegion();
    });

    it('centres the viewport on the selected region and preserves a wider current span', () => {
        app.store.dispatch(app.thunks.centerViewportOnSelectedRegionIntent());
        expect(app.store.getState().view.viewport).toEqual({ min: 3900, max: 5100 });

        app.store.dispatch(app.actions.viewportChange(0, 10000));
        app.store.dispatch(app.thunks.centerViewportOnSelectedRegionIntent());
        expect(app.store.getState().view.viewport).toEqual({ min: -500, max: 9500 });
    });

    it('zooms in when the region is small relative to the current view', () => {
        app.store.dispatch(app.actions.viewportChange(0, 100000));
        app.store.dispatch(app.thunks.centerViewportOnSelectedRegionIntent());
        // 1 s region in a 100 s view: zoom to three region spans, centred.
        expect(app.store.getState().view.viewport).toEqual({ min: 3000, max: 6000 });
    });

    it('selects a double-clicked region before centring the viewport', () => {
        app.store.dispatch(app.actions.regionsAdded([{
            id: 2,
            positionId: 'P1',
            areas: [{ start: 8000, end: 9000 }]
        }]));

        app.store.dispatch(app.thunks.centerViewportOnRegionIntent(2));

        expect(app.store.getState().regions.selectedId).toBe(2);
        expect(app.store.getState().view.viewport).toEqual({ min: 7900, max: 9100 });
    });

    it('returns through earlier views after consecutive region jumps', () => {
        app.store.dispatch(app.thunks.centerViewportOnSelectedRegionIntent());
        app.store.dispatch(app.actions.viewportChange(10000, 11000));
        app.store.dispatch(app.thunks.centerViewportOnSelectedRegionIntent());

        app.store.dispatch(app.thunks.returnToPreviousRegionViewIntent());
        expect(app.store.getState().view.viewport).toEqual({ min: 10000, max: 11000 });
        app.store.dispatch(app.thunks.returnToPreviousRegionViewIntent());
        expect(app.store.getState().view.viewport).toEqual({ min: 0, max: 1000 });
        expect(app.store.getState().view.regionJumpHistory).toEqual([]);
    });

    it('reveals the selected region and requests note focus', () => {
        app.store.dispatch(app.actions.regionVisibilitySet({ showPanel: false }));
        app.store.dispatch(app.actions.setActiveSidePanelTab(1));

        app.store.dispatch(app.thunks.focusSelectedRegionNoteIntent());

        const state = app.store.getState();
        expect(state.regions.panelVisible).toBe(true);
        expect(state.view.activeSidePanelTab).toBe(0);
        expect(state.view.regionNoteFocusRequestId).toBe(1);
    });

    it('steps through regions in list order with [ and ]', () => {
        app.store.dispatch(app.actions.regionsAdded([{
            id: 2,
            positionId: 'P1',
            areas: [{ start: 8000, end: 9000 }]
        }]));
        app.store.dispatch(app.actions.regionSelect(1));

        app.store.dispatch(app.thunks.handleKeyboardShortcutIntent({ key: ']' }));
        expect(app.store.getState().regions.selectedId).toBe(2);
        expect(app.store.getState().view.viewport).toEqual({ min: 7900, max: 9100 });

        app.store.dispatch(app.thunks.handleKeyboardShortcutIntent({ key: ']' }));
        let state = app.store.getState();
        expect(state.regions.selectedId).toBe(2);
        expect(state.view.notice.message).toBe('This is the last region.');

        app.store.dispatch(app.thunks.handleKeyboardShortcutIntent({ key: '[' }));
        state = app.store.getState();
        expect(state.regions.selectedId).toBe(1);
        expect(state.view.viewport).toEqual({ min: 3900, max: 5100 });
    });

    it('starts at the first or last region when nothing is selected', () => {
        app.store.dispatch(app.actions.regionsAdded([{
            id: 2,
            positionId: 'P1',
            areas: [{ start: 8000, end: 9000 }]
        }]));
        app.store.dispatch(app.actions.regionClearSelection());
        app.store.dispatch(app.thunks.stepRegionSelectionIntent(-1));
        expect(app.store.getState().regions.selectedId).toBe(2);

        app.store.dispatch(app.actions.regionClearSelection());
        app.store.dispatch(app.thunks.stepRegionSelectionIntent(1));
        expect(app.store.getState().regions.selectedId).toBe(1);
    });

    it('returns to the view before a run of region hops with one Back', () => {
        app.store.dispatch(app.actions.regionsAdded([{
            id: 2,
            positionId: 'P1',
            areas: [{ start: 8000, end: 9000 }]
        }]));
        app.store.dispatch(app.actions.regionSelect(1));
        app.store.dispatch(app.thunks.stepRegionSelectionIntent(1));
        app.store.dispatch(app.thunks.stepRegionSelectionIntent(-1));
        expect(app.store.getState().view.viewport).toEqual({ min: 3900, max: 5100 });
        expect(app.store.getState().view.regionJumpHistory).toEqual([{ min: 0, max: 1000 }]);

        app.store.dispatch(app.thunks.handleKeyboardShortcutIntent({ key: 'b' }));
        const state = app.store.getState();
        expect(state.view.viewport).toEqual({ min: 0, max: 1000 });
        expect(state.view.regionJumpHistory).toEqual([]);
    });

    it('explains when there is no previous view to return to', () => {
        app.store.dispatch(app.thunks.returnToPreviousRegionViewIntent());
        const state = app.store.getState();
        expect(state.view.viewport).toEqual({ min: 0, max: 1000 });
        expect(state.view.notice.message).toBe('No previous view to return to.');
    });

    it('selects the region under the tap line when N is pressed with nothing selected', () => {
        app.store.dispatch(app.actions.regionClearSelection());
        app.store.dispatch(app.actions.tap(4500, 'P1', 'figure_P1_timeseries'));

        app.store.dispatch(app.thunks.focusSelectedRegionNoteIntent());

        const state = app.store.getState();
        expect(state.regions.selectedId).toBe(1);
        expect(state.view.regionNoteFocusRequestId).toBe(1);
    });

    it('tells the user to select a region when N has nothing to edit', () => {
        app.store.dispatch(app.actions.regionClearSelection());

        app.store.dispatch(app.thunks.focusSelectedRegionNoteIntent());

        const state = app.store.getState();
        expect(state.view.regionNoteFocusRequestId).toBe(0);
        expect(state.view.notice.message).toMatch(/^Select a region first/);
    });

    it('tracks unsaved and saved note states', () => {
        app.store.dispatch(app.thunks.updateRegionNoteDraftIntent(1, 'Dog barking'));
        expect(app.store.getState().view.regionNoteStatus).toBe('unsaved');

        app.store.dispatch(app.thunks.saveRegionNoteIntent(1, 'Dog barking'));
        let state = app.store.getState();
        expect(state.regions.byId[1].note).toBe('Dog barking');
        expect(state.view.regionNoteStatus).toBe('saved');

        // Loading the same text back into the widget is not a new save.
        const regionsBefore = state.regions;
        app.store.dispatch(app.thunks.saveRegionNoteIntent(1, 'Dog barking'));
        expect(app.store.getState().regions).toBe(regionsBefore);

        app.store.dispatch(app.actions.regionClearSelection());
        expect(app.store.getState().view.regionNoteStatus).toBe('idle');
    });

    it('does not replay saved notices or note focus when a workspace is loaded', () => {
        app.store.dispatch(app.actions.noticeShown('Current session notice'));
        const current = app.store.getState().view;
        const saved = JSON.parse(JSON.stringify(app.store.getState()));
        saved.view.notice = { id: 7, message: 'Old notice', level: 'info' };
        saved.view.regionNoteFocusRequestId = 5;
        saved.view.regionNoteStatus = 'unsaved';

        app.store.dispatch(app.actions.rehydrateState(saved));

        const view = app.store.getState().view;
        expect(view.notice).toEqual(current.notice);
        expect(view.regionNoteFocusRequestId).toBe(current.regionNoteFocusRequestId);
        expect(view.regionNoteStatus).toBe('idle');
    });

    it('recalculates from the currently displayed overview or log data', () => {
        app.registry.models.timeSeriesSources.P1 = {
            log: { data: { Datetime: [4000, 4500, 5000], LAeq: [40, 40, 40] } },
            overview: { data: { Datetime: [4000, 4500, 5000], LAeq: [60, 60, 60] } }
        };
        app.dataCache.activeLineData = { P1: { dataViewType: 'overview' } };

        app.store.dispatch(app.thunks.recalculateSelectedRegionIntent());
        let state = app.store.getState();
        let region = state.regions.byId[state.regions.selectedId];
        let metrics = app.regions.getRegionMetrics(region, state, app.dataCache, app.registry.models);
        expect(metrics.dataResolution).toBe('overview');
        expect(metrics.laeq).toBeCloseTo(60, 6);

        app.dataCache.activeLineData.P1.dataViewType = 'log';
        app.store.dispatch(app.thunks.recalculateSelectedRegionIntent());
        state = app.store.getState();
        region = state.regions.byId[state.regions.selectedId];
        metrics = app.regions.getRegionMetrics(region, state, app.dataCache, app.registry.models);
        expect(metrics.dataResolution).toBe('log');
        expect(metrics.laeq).toBeCloseTo(40, 6);
        expect(state.regions.metricsRevision).toBe(2);
    });

    it('uses log spectral data with log broadband metrics when it is available', () => {
        app.registry.models.timeSeriesSources.P1 = {
            log: { data: { Datetime: [4000, 4500, 5000], LAeq: [40, 40, 40] } },
            overview: { data: { Datetime: [4000, 4500, 5000], LAeq: [60, 60, 60] } }
        };
        app.registry.models.preparedGlyphData.P1 = {
            log: {
                prepared_params: {
                    LZeq: {
                        frequency_labels: ['63 Hz'],
                        times_ms: [4000, 4500, 5000],
                        n_freqs: 1,
                        n_times: 3,
                        levels_flat_transposed: [30, 30, 30]
                    }
                }
            },
            overview: {
                prepared_params: {
                    LZeq: {
                        frequency_labels: ['63 Hz'],
                        times_ms: [4000, 4500, 5000],
                        n_freqs: 1,
                        n_times: 3,
                        levels_flat_transposed: [70, 70, 70]
                    }
                }
            }
        };

        const region = app.store.getState().regions.byId[1];
        const metrics = app.regions.computeRegionMetrics(
            region,
            app.store.getState(),
            app.dataCache,
            app.registry.models,
            { resolution: 'log' }
        );

        expect(metrics.dataResolution).toBe('log');
        expect(metrics.spectrum.source).toBe('log');
        expect(metrics.spectrum.values[0]).toBeCloseTo(30, 6);
    });
});
