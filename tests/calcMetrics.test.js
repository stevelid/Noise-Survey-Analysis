import { describe, it, expect, beforeEach } from 'vitest';

import '../noise_survey_analysis/static/js/features/regions/regionUtils.js';

const { calcMetrics } = window.NoiseSurveyApp;

describe('calcMetrics module', () => {
    beforeEach(() => {
        expect(calcMetrics).toBeDefined();
    });

    it('calculates LAeq using energy mean', () => {
        const result = calcMetrics.calcLAeq([50, 60]);
        expect(result).toBeCloseTo(57.4, 1);
    });

    it('calculates LAeq for varied levels', () => {
        const result = calcMetrics.calcLAeq([80, 40, 60, 70, 30, 50]);
        expect(result).toBeCloseTo(72.7, 1);
    });

    it('returns null for empty LAeq input', () => {
        expect(calcMetrics.calcLAeq([])).toBeNull();
    });

    it('calculates LAFmax correctly', () => {
        expect(calcMetrics.calcLAMax([40, 55, 51])).toBe(55);
    });

    it('calculates LA90 percentile', () => {
        const result = calcMetrics.calcLA90([80, 40, 60, 70, 50]);
        expect(result).toBeCloseTo(44, 1);
    });

    it('slices time series within range', () => {
        const timestamps = [0, 1000, 2000, 3000];
        const values = [10, 20, 30, 40];
        const slice = calcMetrics.sliceTimeSeries(timestamps, values, 500, 2500);
        expect(slice).toEqual([20, 30]);
    });

    it('computes average spectrum per band', () => {
        const spectrum = calcMetrics.calcAverageSpectrum([
            [50, 60],
            [40, 50]
        ]);
        expect(spectrum[0]).toBeCloseTo(57.4, 1);
        expect(spectrum[1]).toBeCloseTo(47.4, 1);
    });
});
