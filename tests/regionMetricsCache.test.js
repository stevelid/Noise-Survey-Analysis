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

    it('cache key includes chart offset so offset changes invalidate cached metrics', () => {
        const { regions } = app;
        if (!regions?.getRegionMetrics) {
            throw new Error('Region utilities are not available.');
        }

        const region = { id: 10, positionId: 'P1', start: 0, end: 1000, areas: [{ start: 0, end: 1000 }] };
        const dataCache = {};
        const models = { timeSeriesSources: {} };

        const stateOffset0 = { view: { selectedParameter: 'LAeq', positionChartOffsets: { P1: 0 } } };
        const stateOffset5k = { view: { selectedParameter: 'LAeq', positionChartOffsets: { P1: 5000 } } };

        const metrics0 = regions.getRegionMetrics(region, stateOffset0, dataCache, models);
        const metrics5k = regions.getRegionMetrics(region, stateOffset5k, dataCache, models);

        expect(metrics0).not.toBe(metrics5k);
    });

    it('computeRegionMetrics returns sourceAreas offset-corrected for chart offset', () => {
        const { regions } = app;
        if (!regions?.computeRegionMetrics) {
            throw new Error('Region utilities are not available.');
        }

        const region = { id: 11, positionId: 'P1', start: 10000, end: 20000, areas: [{ start: 10000, end: 20000 }] };
        const state = { view: { selectedParameter: 'LAeq', positionChartOffsets: { P1: 5000 } } };
        const dataCache = {};
        const models = { timeSeriesSources: {} };

        const metrics = regions.computeRegionMetrics(region, state, dataCache, models);
        expect(metrics.chartOffsetMs).toBe(5000);
        expect(metrics.sourceAreas).toHaveLength(1);
        expect(metrics.sourceAreas[0].start).toBe(5000);
        expect(metrics.sourceAreas[0].end).toBe(15000);
    });

    it('computeRegionMetrics uses selected parameter for spectrum when available', () => {
        const { regions } = app;
        if (!regions?.computeRegionMetrics) {
            throw new Error('Region utilities are not available.');
        }

        const region = { id: 12, positionId: 'P1', start: 0, end: 1000, areas: [{ start: 0, end: 1000 }] };
        const state = { view: { selectedParameter: 'LCeq' } };
        const dataCache = {};
        const models = {
            timeSeriesSources: {
                P1: {
                    log: {
                        data: {
                            Datetime: [0, 500, 1000],
                            LAeq: [50, 55, 52]
                        }
                    }
                }
            },
            preparedGlyphData: {
                P1: {
                    log: {
                        prepared_params: {
                            LCeq: {
                                frequency_labels: ['63 Hz', '125 Hz'],
                                times_ms: [0, 500, 1000],
                                n_freqs: 2,
                                n_times: 3,
                                levels_flat_transposed: [10, 20, 30, 15, 25, 35]
                            }
                        }
                    }
                }
            }
        };

        const metrics = regions.computeRegionMetrics(region, state, dataCache, models);
        expect(metrics.spectrumParameter).toBe('LCeq');
        expect(metrics.spectrum.labels).toEqual(['63 Hz', '125 Hz']);
    });

    it('computeRegionMetrics falls back to LZeq when selected parameter spectral data is absent', () => {
        const { regions } = app;
        if (!regions?.computeRegionMetrics) {
            throw new Error('Region utilities are not available.');
        }

        const region = { id: 13, positionId: 'P1', start: 0, end: 1000, areas: [{ start: 0, end: 1000 }] };
        const state = { view: { selectedParameter: 'LCeq' } };
        const dataCache = {};
        const models = {
            timeSeriesSources: {
                P1: {
                    log: {
                        data: {
                            Datetime: [0, 500, 1000],
                            LAeq: [50, 55, 52]
                        }
                    }
                }
            },
            preparedGlyphData: {
                P1: {
                    log: {
                        prepared_params: {
                            LZeq: {
                                frequency_labels: ['63 Hz'],
                                times_ms: [0, 500, 1000],
                                n_freqs: 1,
                                n_times: 3,
                                levels_flat_transposed: [10, 20, 30]
                            }
                        }
                    }
                }
            }
        };

        const metrics = regions.computeRegionMetrics(region, state, dataCache, models);
        expect(metrics.spectrumParameter).toBe('LZeq');
        expect(metrics.spectrum.labels).toEqual(['63 Hz']);
    });
});
