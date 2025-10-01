import { describe, it, beforeEach, expect, vi } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/init.js';

const app = window.NoiseSurveyApp;

if (!app) {
    throw new Error('NoiseSurveyApp namespace is not available.');
}

describe('Region thunks cache invalidation', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
        if (app.init?.reInitializeStore) {
            app.init.reInitializeStore();
        }
        if (app.regions?.invalidateMetricsCache) {
            app.regions.invalidateMetricsCache();
        }
    });

    it('invalidates region metrics when creating a region', () => {
        const { store, thunks, regions } = app;
        if (!store || !thunks?.createRegionIntent || !regions) {
            throw new Error('Required dependencies not available.');
        }

        const invalidateSpy = vi.spyOn(regions, 'invalidateRegionMetrics');

        const intent = thunks.createRegionIntent({ positionId: 'P1', start: 0, end: 1000 });
        store.dispatch(intent);

        // Should have been called for the newly created region
        expect(invalidateSpy).toHaveBeenCalled();
        invalidateSpy.mockRestore();
    });

    it('invalidates cache when creating auto day/night regions', () => {
        const { store, thunks, regions, registry } = app;
        if (!store || !thunks?.createAutoRegionsIntent || !regions) {
            throw new Error('Required dependencies not available.');
        }

        // Mock time series data
        const mockData = {
            Datetime: [
                new Date('2025-08-06T07:00:00').getTime(),
                new Date('2025-08-06T12:00:00').getTime(),
                new Date('2025-08-06T23:00:00').getTime()
            ],
            LAeq: [50, 55, 45]
        };

        if (registry?.models?.timeSeriesSources) {
            registry.models.timeSeriesSources.P1 = {
                overview: { data: mockData },
                log: { data: mockData }
            };
        }

        const invalidateSpy = vi.spyOn(regions, 'invalidateMetricsCache');

        const intent = thunks.createAutoRegionsIntent({
            positions: ['P1'],
            modes: ['daytime', 'nighttime']
        });
        store.dispatch(intent);

        expect(invalidateSpy).toHaveBeenCalled();
        invalidateSpy.mockRestore();
    });

    it('invalidates region metrics when resizing a region', () => {
        const { store, actions, thunks, regions } = app;
        if (!store || !actions || !thunks?.resizeSelectedRegionIntent || !regions) {
            throw new Error('Required dependencies not available.');
        }

        // Create a region first
        store.dispatch(actions.regionAdd('P1', 0, 1000));
        const state = store.getState();
        const regionId = state?.regions?.allIds?.[0];

        const invalidateSpy = vi.spyOn(regions, 'invalidateRegionMetrics');

        // Resize the region
        const intent = thunks.resizeSelectedRegionIntent({
            key: 'ArrowRight',
            modifiers: { ctrl: true }
        });
        store.dispatch(intent);

        expect(invalidateSpy).toHaveBeenCalledWith(regionId);
        invalidateSpy.mockRestore();
    });

    it('invalidates cache when splitting a region', () => {
        const { store, actions, thunks, regions } = app;
        if (!store || !actions || !thunks?.splitSelectedRegionIntent || !regions) {
            throw new Error('Required dependencies not available.');
        }

        // Create a multi-area region
        store.dispatch(actions.regionAdd('P1', 0, 1000));
        const state = store.getState();
        const regionId = state?.regions?.allIds?.[0];
        
        // Add another area
        store.dispatch(actions.regionUpdate(regionId, {
            areas: [{ start: 0, end: 1000 }, { start: 2000, end: 3000 }]
        }));

        const invalidateSpy = vi.spyOn(regions, 'invalidateMetricsCache');

        // Split the region
        const intent = thunks.splitSelectedRegionIntent();
        store.dispatch(intent);

        expect(invalidateSpy).toHaveBeenCalled();
        invalidateSpy.mockRestore();
    });

    it('invalidates cache when merging regions', () => {
        const { store, actions, thunks, regions } = app;
        if (!store || !actions || !thunks?.mergeRegionIntoSelectedIntent || !regions) {
            throw new Error('Required dependencies not available.');
        }

        // Create two regions
        store.dispatch(actions.regionAdd('P1', 0, 1000));
        store.dispatch(actions.regionAdd('P1', 2000, 3000));
        
        const state = store.getState();
        const [targetId, sourceId] = state?.regions?.allIds || [];

        const invalidateSpy = vi.spyOn(regions, 'invalidateRegionMetrics');

        // Merge source into target
        const intent = thunks.mergeRegionIntoSelectedIntent(sourceId);
        store.dispatch(intent);

        // Should invalidate both regions
        expect(invalidateSpy).toHaveBeenCalledWith(targetId);
        expect(invalidateSpy).toHaveBeenCalledWith(sourceId);
        invalidateSpy.mockRestore();
    });

    it('invalidates cache when parameter changes', () => {
        const { store, thunks, regions } = app;
        if (!store || !thunks?.selectParameterIntent || !regions) {
            throw new Error('Required dependencies not available.');
        }

        const invalidateSpy = vi.spyOn(regions, 'invalidateMetricsCache');

        const intent = thunks.selectParameterIntent('LAFmax');
        store.dispatch(intent);

        expect(invalidateSpy).toHaveBeenCalled();
        invalidateSpy.mockRestore();
    });

    it('invalidates cache when importing regions', () => {
        const { regions } = app;
        if (!regions?.handleImport) {
            throw new Error('Import handler not available.');
        }

        const invalidateSpy = vi.spyOn(regions, 'invalidateMetricsCache');

        const mockFile = new File(
            [JSON.stringify([{ positionId: 'P1', start: 0, end: 1000, areas: [{ start: 0, end: 1000 }] }])],
            'regions.json',
            { type: 'application/json' }
        );

        regions.handleImport(mockFile);

        // Wait for file read to complete
        return new Promise(resolve => {
            setTimeout(() => {
                expect(invalidateSpy).toHaveBeenCalled();
                invalidateSpy.mockRestore();
                resolve();
            }, 100);
        });
    });
});
