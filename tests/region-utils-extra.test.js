import { describe, it, expect, beforeEach } from 'vitest';

import '../noise_survey_analysis/static/js/features/regions/regionUtils.js';

const app = window.NoiseSurveyApp;
const regionUtils = app.features.regions.utils;

describe('NoiseSurveyApp.features.regions.utils (extra coverage)', () => {
    beforeEach(() => {
        regionUtils.invalidateMetricsCache();
    });

    it('formats spectrum clipboard text from legacy band/value keys', () => {
        const text = regionUtils.formatSpectrumClipboardText({
            bands: ['63 Hz', '125 Hz'],
            band_values: [40.125, null]
        });

        expect(text).toBe('Band\tLAeq (dB)\n63 Hz\t40.1\n125 Hz\t0.0');
    });

    it('imports regions from legacy start/end fields and skips invalid areas', () => {
        const imported = regionUtils.importRegions(JSON.stringify([
            {
                id: 10,
                positionId: 'P1',
                start: 1000,
                end: 2000,
                note: 'Legacy shape',
                color: '#abcdef'
            },
            {
                id: 11,
                positionId: 'P2',
                areas: [{ start: 5, end: 5 }]
            }
        ]));

        expect(imported).toEqual([
            {
                id: 10,
                positionId: 'P1',
                areas: [{ start: 1000, end: 2000 }],
                note: 'Legacy shape',
                color: '#abcdef'
            }
        ]);
    });

    it('computes log metrics using LAFmax and log-resolution LA90', () => {
        const region = {
            id: 1,
            positionId: 'P1',
            start: 0,
            end: 2000,
            areas: [{ start: 0, end: 2000 }]
        };
        const state = { view: { selectedParameter: 'LAeq' } };
        const metrics = regionUtils.computeRegionMetrics(region, state, {}, {
            timeSeriesSources: {
                P1: {
                    log: {
                        data: {
                            Datetime: [0, 1000, 2000],
                            LAeq: [50, 60, 70],
                            LAF90: [40, 41, 42],
                            LAFmax: [80, 81, 82]
                        }
                    }
                }
            },
            preparedGlyphData: {}
        });

        expect(metrics.dataResolution).toBe('log');
        expect(metrics.lafmax).toBe(82);
        expect(metrics.la90Available).toBe(true);
        expect(metrics.la90).toBeCloseTo(40.2, 1);
    });

    it('falls back to overview spectral data when log spectral data is unavailable', () => {
        const region = {
            id: 2,
            positionId: 'P2',
            start: 0,
            end: 1000,
            areas: [{ start: 0, end: 1000 }]
        };
        const state = { view: { selectedParameter: 'LAeq' } };
        const metrics = regionUtils.computeRegionMetrics(region, state, {}, {
            timeSeriesSources: {
                P2: {
                    overview: {
                        data: {
                            Datetime: [0, 1000],
                            LAeq: [55, 65]
                        }
                    }
                }
            },
            preparedGlyphData: {
                P2: {
                    overview: {
                        prepared_params: {
                            LZeq: {
                                times_ms: [0, 1000],
                                levels_flat_transposed: new Float32Array([60, 61, 70, 71]),
                                n_freqs: 2,
                                n_times: 2,
                                frequency_labels: ['100 Hz', '200 Hz']
                            }
                        }
                    },
                    log: { prepared_params: {} }
                }
            }
        });

        expect(metrics.dataResolution).toBe('overview');
        expect(metrics.spectrum.source).toBe('overview');
        expect(metrics.spectrum.labels).toEqual(['100 Hz', '200 Hz']);
        expect(metrics.spectrum.values[0]).toBeCloseTo(60.5, 1);
    });

    it('exports regions with computed metrics and colour metadata', () => {
        const region = {
            id: 3,
            positionId: 'P3',
            start: 0,
            end: 1000,
            areas: [{ start: 0, end: 1000 }],
            note: 'Export me',
            color: '#123456'
        };
        const state = {
            view: { selectedParameter: 'LAeq' },
            regions: { allIds: [3], byId: { 3: region } }
        };
        const exported = JSON.parse(regionUtils.exportRegions(state, {}, {
            timeSeriesSources: {
                P3: {
                    overview: {
                        data: {
                            Datetime: [0, 1000],
                            LAeq: [50, 52]
                        }
                    }
                }
            },
            preparedGlyphData: {}
        }));

        expect(exported).toHaveLength(1);
        expect(exported[0].color).toBe('#123456');
        expect(exported[0].areas).toEqual([{ start: 0, end: 1000 }]);
        expect(exported[0].metrics.dataResolution).toBe('overview');
        expect(exported[0].metrics.laeq).toBeCloseTo(51.1, 1);
    });
});
