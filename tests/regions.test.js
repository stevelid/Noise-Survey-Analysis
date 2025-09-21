import { describe, it, expect } from 'vitest';

import '../noise_survey_analysis/static/js/calcMetrics.js';
import '../noise_survey_analysis/static/js/regions.js';

const { regions } = window.NoiseSurveyApp;

function buildSpectralData() {
    return {
        times_ms: [0, 1000, 2000],
        n_times: 3,
        n_freqs: 2,
        levels_flat_transposed: new Float32Array([
            40, 42, 44,
            50, 52, 54
        ]),
        frequency_labels: ['63 Hz', '125 Hz']
    };
}

describe('regions module', () => {
    it('computes metrics for regions using log data when available', () => {
        const spectral = buildSpectralData();
        const state = {
            view: { selectedParameter: 'LZeq' },
            markers: {
                regions: {
                    byId: {
                        1: { id: 1, positionId: 'P1', start: 0, end: 2000, note: '', metrics: null }
                    },
                    allIds: [1],
                    selectedId: 1,
                    counter: 2
                }
            }
        };
        const models = {
            timeSeriesSources: {
                P1: {
                    log: { data: { Datetime: [0, 1000, 2000], LAeq: [50, 60, 70], LAFmax: [55, 65, 75] } },
                    overview: { data: { Datetime: [0, 2000], LAeq: [52, 68] } }
                }
            },
            preparedGlyphData: {
                P1: {
                    log: { prepared_params: { LZeq: spectral } },
                    overview: { prepared_params: { LZeq: spectral } }
                }
            }
        };

        const updates = regions.prepareMetricsUpdates(state, {}, models);
        expect(updates).toHaveLength(1);
        const metrics = updates[0].metrics;
        expect(metrics.dataResolution).toBe('log');
        expect(metrics.laeq).toBeCloseTo(65.7, 1);
        expect(metrics.lafmax).toBe(75);
        expect(metrics.la90).toBeCloseTo(52, 0);
        expect(metrics.spectrum.values[0]).toBeCloseTo(42, 0);
        expect(metrics.spectrum.values[1]).toBeCloseTo(52, 0);
        expect(metrics.parameter).toBe('LZeq');
    });

    it('recomputes metrics when selected parameter changes', () => {
        const spectral = buildSpectralData();
        const state = {
            view: { selectedParameter: 'LAeq' },
            markers: {
                regions: {
                    byId: {
                        1: {
                            id: 1,
                            positionId: 'P1',
                            start: 0,
                            end: 2000,
                            note: '',
                            metrics: {
                                laeq: 60,
                                lafmax: 65,
                                la90: null,
                                la90Available: false,
                                dataResolution: 'log',
                                spectrum: { labels: ['63 Hz', '125 Hz'], values: [55, 60] },
                                parameter: 'LZeq',
                                durationMs: 2000
                            }
                        }
                    },
                    allIds: [1],
                    selectedId: 1,
                    counter: 2
                }
            }
        };
        const models = {
            timeSeriesSources: {
                P1: {
                    log: { data: { Datetime: [0, 1000, 2000], LAeq: [50, 60, 70], LAFmax: [55, 65, 75] } }
                }
            },
            preparedGlyphData: {
                P1: {
                    log: { prepared_params: { LAeq: spectral } },
                    overview: { prepared_params: {} }
                }
            }
        };

        const updates = regions.prepareMetricsUpdates(state, {}, models);
        expect(updates).toHaveLength(1);
        const metrics = updates[0].metrics;
        expect(metrics.parameter).toBe('LAeq');
        expect(metrics.spectrum.values[0]).toBeCloseTo(42, 0);
        expect(metrics.spectrum.values[1]).toBeCloseTo(52, 0);
    });

    it('exports and imports region payloads', () => {
        const state = {
            markers: {
                regions: {
                    byId: {
                        1: { id: 1, positionId: 'P1', start: 0, end: 1000, note: 'Note', metrics: { laeq: 50 } }
                    },
                    allIds: [1],
                    selectedId: 1,
                    counter: 2
                }
            }
        };
        const json = regions.exportRegions(state);
        expect(json).toContain('"positionId": "P1"');
        const imported = regions.importRegions(json);
        expect(imported).toHaveLength(1);
        expect(imported[0].note).toBe('Note');
    });

    it('formats region summaries for clipboard', () => {
        const region = { id: 3, positionId: 'P1', start: 0, end: 65000 };
        const metrics = { laeq: 55.1, la90: null, la90Available: false, lafmax: 70.3, durationMs: 65000 };
        const summary = regions.formatRegionSummary(region, metrics, 'P1');
        expect(summary).toContain('Region 3');
        expect(summary).toContain('LAeq 55.1 dB');
        expect(summary).toContain('LAF90 N/A');
    });
});
