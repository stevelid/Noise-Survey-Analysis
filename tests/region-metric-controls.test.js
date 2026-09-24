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
