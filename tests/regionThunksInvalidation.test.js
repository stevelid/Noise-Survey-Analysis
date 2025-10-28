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

        // Mock FileReader for import tests
        global.FileReader = class MockFileReader {
            readAsText(file) {
                // Simulate async file read
                setTimeout(() => {
                    if (this.onload) {
                        file.text().then(text => {
                            this.onload({ target: { result: text } });
                        });
                    }
                }, 0);
            }
        };
    });

    it('invalidates region metrics when creating a region', () => {
        const { store, thunks, regions } = app;
        if (!store || !thunks?.createRegionIntent || !regions) {
            throw new Error('Required dependencies not available.');
        }

        // createRegionIntent calls invalidateMetricsCache, not invalidateRegionMetrics
        const invalidateSpy = vi.spyOn(regions, 'invalidateMetricsCache');

        const intent = thunks.createRegionIntent({ positionId: 'P1', start: 0, end: 1000 });
        store.dispatch(intent);

        // Should have been called to invalidate the cache
        expect(invalidateSpy).toHaveBeenCalled();
        invalidateSpy.mockRestore();
    });

    it('invalidates cache when creating auto day/night regions', () => {
        const { store, thunks, regions, actions } = app;
        if (!store || !thunks?.createAutoRegionsIntent || !regions || !actions) {
            throw new Error('Required dependencies not available.');
        }

        // Mock time series data - need multiple days and enough points for buffering
        const mockData = {
            Datetime: [
                new Date('2025-08-06T07:00:00').getTime(),
                new Date('2025-08-06T08:00:00').getTime(),
                new Date('2025-08-06T12:00:00').getTime(),
                new Date('2025-08-06T15:00:00').getTime(),
                new Date('2025-08-06T18:00:00').getTime(),
                new Date('2025-08-06T23:00:00').getTime(),
                new Date('2025-08-07T00:00:00').getTime(),
                new Date('2025-08-07T07:00:00').getTime(),
                new Date('2025-08-07T12:00:00').getTime(),
                new Date('2025-08-07T15:00:00').getTime(),
                new Date('2025-08-07T23:00:00').getTime()
            ],
            LAeq: [50, 52, 55, 54, 53, 45, 42, 51, 56, 54, 44]
        };

        // Ensure registry exists and set mock data BEFORE initializing state
        if (!app.registry) {
            app.registry = {};
        }
        if (!app.registry.models) {
            app.registry.models = {};
        }
        if (!app.registry.models.timeSeriesSources) {
            app.registry.models.timeSeriesSources = {};
        }
        app.registry.models.timeSeriesSources.P1 = {
            overview: { data: mockData },
            log: { data: mockData }
        };

        // Initialize state with available positions
        store.dispatch(actions.initializeState({
            availablePositions: ['P1'],
            selectedParameter: 'LAeq',
            viewport: { min: mockData.Datetime[0], max: mockData.Datetime[mockData.Datetime.length - 1] },
            chartVisibility: {}
        }));

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

        let state = store.getState();
        const [targetId, sourceId] = state?.regions?.allIds || [];

        // Select the first region (target) before merging
        store.dispatch(actions.regionSelect(targetId));

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

    it.skip('invalidates cache when importing regions (TODO: requires DOM file input simulation)', () => {
        // handleImport() creates a file input element and doesn't accept file parameter directly
        // This test requires complex DOM interaction simulation (file input click + change event)
        // Alternative: Test the importRegions() function directly or use E2E tests
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
