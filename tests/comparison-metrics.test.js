import { describe, it, expect } from 'vitest';

import '../noise_survey_analysis/static/js/features/regions/regionUtils.js';
import '../noise_survey_analysis/static/js/comparison-metrics.js';

const { comparisonMetrics, calcMetrics } = window.NoiseSurveyApp;

const processComparisonSliceMetrics = comparisonMetrics.processComparisonSliceMetrics;

describe('processComparisonSliceMetrics', () => {
    it('calculates metrics and spectrum for log data', () => {
        const timeSeriesSources = {
            P1: {
                log: {
                    data: {
                        Datetime: [0, 1000, 2000, 3000],
                        LAeq: [40, 50, 60, 50],
                        LAFmax: [55, 65, 70, 68]
                    }
                },
                overview: { data: { Datetime: [], LAeq: [] } }
            }
        };

        const preparedGlyphData = {
            P1: {
                log: {
                    prepared_params: {
                        LZeq: {
                            frequency_labels: ['63 Hz', '125 Hz'],
                            times_ms: [0, 1000, 2000, 3000],
                            n_freqs: 2,
                            n_times: 4,
                            levels_flat_transposed: [10, 20, 30, 40, 15, 25, 35, 45]
                        }
                    }
                },
                overview: { prepared_params: {} }
            }
        };

        const result = processComparisonSliceMetrics({
            start: 1000,
            end: 3000,
            positionIds: ['P1'],
            timeSeriesSources,
            preparedGlyphData,
            selectedParameter: 'LZeq'
        });

        expect(result.metricsRows).toHaveLength(1);
        const metrics = result.metricsRows[0];
        const expectedLaeq = calcMetrics.calcLAeq([50, 60, 50]);
        const expectedLafmax = calcMetrics.calcLAMax([65, 70, 68]);
        const expectedLa90 = calcMetrics.calcLA90([50, 60, 50]);
        expect(metrics.dataset).toBe('log');
        expect(metrics.laeq).toBeCloseTo(expectedLaeq ?? 0, 6);
        expect(metrics.lafmax).toBeCloseTo(expectedLafmax ?? 0, 6);
        expect(metrics.la90).toBeCloseTo(expectedLa90 ?? 0, 6);
        expect(metrics.la90Available).toBe(true);
        expect(metrics.durationMs).toBe(2000);

        expect(result.spectrum.labels).toEqual(['63 Hz', '125 Hz']);
        expect(result.spectrum.series).toHaveLength(1);
        const seriesValues = result.spectrum.series[0].values;
        const expectedFreq1 = calcMetrics.calcLAeq([20, 30, 40]);
        const expectedFreq2 = calcMetrics.calcLAeq([25, 35, 45]);
        expect(seriesValues[0]).toBeCloseTo(expectedFreq1 ?? 0, 6);
        expect(seriesValues[1]).toBeCloseTo(expectedFreq2 ?? 0, 6);
    });

    it('falls back to overview data when log data is empty', () => {
        const timeSeriesSources = {
            P2: {
                log: {
                    data: {
                        Datetime: [0, 1000, 2000],
                        LAeq: [NaN, NaN, NaN]
                    }
                },
                overview: {
                    data: {
                        Datetime: [0, 6000],
                        LAeq: [45, 47]
                    }
                }
            }
        };

        const preparedGlyphData = {
            P2: {
                overview: {
                    prepared_params: {
                        LZeq: {
                            frequency_labels: ['63 Hz'],
                            times_ms: [0, 6000],
                            n_freqs: 1,
                            n_times: 2,
                            levels_flat_transposed: [40, 50]
                        }
                    }
                }
            }
        };

        const result = processComparisonSliceMetrics({
            start: 0,
            end: 6000,
            positionIds: ['P2'],
            timeSeriesSources,
            preparedGlyphData,
            selectedParameter: 'LZeq'
        });

        expect(result.metricsRows).toHaveLength(1);
        const metrics = result.metricsRows[0];
        const expectedLaeq = calcMetrics.calcLAeq([45, 47]);
        expect(metrics.dataset).toBe('overview');
        expect(metrics.laeq).toBeCloseTo(expectedLaeq ?? 0, 6);
        expect(metrics.la90Available).toBe(false);
        expect(result.spectrum.series[0].values[0]).toBeCloseTo(calcMetrics.calcLAeq([40, 50]) ?? 0, 6);
    });

    it('returns empty results when slice or positions are invalid', () => {
        const result = processComparisonSliceMetrics({
            start: 0,
            end: 0,
            positionIds: [],
            timeSeriesSources: {},
            preparedGlyphData: {}
        });
        expect(result.metricsRows).toEqual([]);
        expect(result.spectrum.labels).toEqual([]);
        expect(result.spectrum.series).toEqual([]);
        expect(result.hasData).toBe(false);
    });
});
