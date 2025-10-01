import { describe, it, beforeEach, expect, vi } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/init.js';
import '../noise_survey_analysis/static/js/services/session/sessionManager.js';

const app = window.NoiseSurveyApp;

if (!app) {
    throw new Error('NoiseSurveyApp namespace is not available.');
}

describe('Region metrics cache', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
        if (app.init?.reInitializeStore) {
            app.init.reInitializeStore();
        }
        // Clear the cache before each test
        if (app.regions?.invalidateMetricsCache) {
            app.regions.invalidateMetricsCache();
        }
    });

    it('caches metrics and returns same object on repeated calls', () => {
        const { regions } = app;
        if (!regions?.getRegionMetrics || !regions?.computeRegionMetrics) {
            throw new Error('Region utilities are not available.');
        }

        const region = { id: 1, positionId: 'P1', start: 0, end: 1000, areas: [{ start: 0, end: 1000 }] };
        const state = { view: { selectedParameter: 'LAeq' } };
        const dataCache = {};
        const models = { timeSeriesSources: {} };

        const metrics1 = regions.getRegionMetrics(region, state, dataCache, models);
        const metrics2 = regions.getRegionMetrics(region, state, dataCache, models);

        expect(metrics1).toBe(metrics2); // Same object reference = cached
    });

    it('returns different metrics after cache invalidation', () => {
        const { regions } = app;
        if (!regions?.getRegionMetrics || !regions?.invalidateRegionMetrics) {
            throw new Error('Region utilities are not available.');
        }

        const region = { id: 1, positionId: 'P1', start: 0, end: 1000, areas: [{ start: 0, end: 1000 }] };
        const state = { view: { selectedParameter: 'LAeq' } };
        const dataCache = {};
        const models = { timeSeriesSources: {} };

        const metrics1 = regions.getRegionMetrics(region, state, dataCache, models);
        
        regions.invalidateRegionMetrics(1);
        
        const metrics2 = regions.getRegionMetrics(region, state, dataCache, models);

        expect(metrics1).not.toBe(metrics2); // Different object = cache was cleared
    });

    it('returns different metrics for different parameters', () => {
        const { regions } = app;
        if (!regions?.getRegionMetrics) {
            throw new Error('Region utilities are not available.');
        }

        const region = { id: 1, positionId: 'P1', start: 0, end: 1000, areas: [{ start: 0, end: 1000 }] };
        const dataCache = {};
        const models = { timeSeriesSources: {} };

        const metricsLAeq = regions.getRegionMetrics(region, { view: { selectedParameter: 'LAeq' } }, dataCache, models);
        const metricsLAFmax = regions.getRegionMetrics(region, { view: { selectedParameter: 'LAFmax' } }, dataCache, models);

        expect(metricsLAeq).not.toBe(metricsLAFmax); // Different cache keys
    });

    it('clears entire cache when invalidateMetricsCache is called', () => {
        const { regions } = app;
        if (!regions?.getRegionMetrics || !regions?.invalidateMetricsCache) {
            throw new Error('Region utilities are not available.');
        }

        const region1 = { id: 1, positionId: 'P1', start: 0, end: 1000, areas: [{ start: 0, end: 1000 }] };
        const region2 = { id: 2, positionId: 'P2', start: 0, end: 2000, areas: [{ start: 0, end: 2000 }] };
        const state = { view: { selectedParameter: 'LAeq' } };
        const dataCache = {};
        const models = { timeSeriesSources: {} };

        const metrics1a = regions.getRegionMetrics(region1, state, dataCache, models);
        const metrics2a = regions.getRegionMetrics(region2, state, dataCache, models);

        regions.invalidateMetricsCache();

        const metrics1b = regions.getRegionMetrics(region1, state, dataCache, models);
        const metrics2b = regions.getRegionMetrics(region2, state, dataCache, models);

        expect(metrics1a).not.toBe(metrics1b);
        expect(metrics2a).not.toBe(metrics2b);
    });

    it('clears cache when applying a saved workspace', () => {
        const { session, regions, createInitialState } = app;
        if (!session || !regions || typeof session.applyWorkspaceState !== 'function') {
            throw new Error('Session helpers are not available for the test.');
        }

        const invalidateSpy = vi.spyOn(regions, 'invalidateMetricsCache');
        const payload = {
            appState: createInitialState(),
            sourceConfigs: []
        };

        const applied = session.applyWorkspaceState(payload);
        expect(applied).toBe(true);
        expect(invalidateSpy).toHaveBeenCalled();
        invalidateSpy.mockRestore();
    });
});
