// noise_survey_analysis/static/js/calcMetrics.js

/**
 * @fileoverview Provides pure helper functions for calculating acoustic metrics.
 * The functions in this module accept simple numeric arrays and return derived
 * statistics without referencing global application state.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const EPSILON = 1e-12;

    function toFiniteArray(values) {
        if (!values) return [];
        if (Array.isArray(values) || ArrayBuffer.isView(values)) {
            const result = [];
            for (let i = 0; i < values.length; i++) {
                const value = Number(values[i]);
                if (Number.isFinite(value)) {
                    result.push(value);
                }
            }
            return result;
        }
        return [];
    }

    /**
     * Calculates the equivalent continuous sound level (LAeq) from a collection of
     * decibel values using the energy mean method.
     *
     * @param {Array<number>|TypedArray} values - A list of decibel readings.
     * @returns {?number} The LAeq value in decibels, or null if no valid data.
     */
    function calcLAeq(values) {
        const finiteValues = toFiniteArray(values);
        if (!finiteValues.length) return null;

        let energySum = 0;
        for (let i = 0; i < finiteValues.length; i++) {
            energySum += Math.pow(10, finiteValues[i] / 10);
        }

        if (energySum <= EPSILON) return null;
        const meanEnergy = energySum / finiteValues.length;
        return 10 * Math.log10(meanEnergy);
    }

    /**
     * Calculates the LAFmax (maximum A-weighted fast level) for a region.
     *
     * @param {Array<number>|TypedArray} values - A list of decibel readings.
     * @returns {?number} The maximum value or null if no valid data.
     */
    function calcLAMax(values) {
        const finiteValues = toFiniteArray(values);
        if (!finiteValues.length) return null;
        let maxValue = -Infinity;
        for (let i = 0; i < finiteValues.length; i++) {
            if (finiteValues[i] > maxValue) {
                maxValue = finiteValues[i];
            }
        }
        return Number.isFinite(maxValue) ? maxValue : null;
    }

    /**
     * Calculates the LA90 metric, defined as the value exceeded for 90% of the time.
     *
     * @param {Array<number>|TypedArray} values - A list of decibel readings.
     * @returns {?number} The LA90 level or null if insufficient data.
     */
    function calcLA90(values) {
        const finiteValues = toFiniteArray(values);
        if (!finiteValues.length) return null;

        const sorted = finiteValues.slice().sort((a, b) => a - b);
        if (!sorted.length) return null;

        const position = 0.1 * (sorted.length - 1);
        const lowerIndex = Math.floor(position);
        const upperIndex = Math.ceil(position);

        if (lowerIndex === upperIndex) {
            return sorted[lowerIndex];
        }

        const lower = sorted[lowerIndex];
        const upper = sorted[upperIndex];
        const weight = position - lowerIndex;
        return lower + weight * (upper - lower);
    }

    /**
     * Filters a set of time-aligned samples to only include points within the
     * provided timestamp range. The function assumes both arrays are equal in
     * length and aligned such that `timestamps[i]` corresponds to `values[i]`.
     *
     * @param {Array<number>|TypedArray} timestamps - Epoch timestamps in ms.
     * @param {Array<number>|TypedArray} values - Values aligned with the timestamps.
     * @param {number} startMs - Inclusive start timestamp.
     * @param {number} endMs - Inclusive end timestamp.
     * @returns {number[]} The subset of values contained in the interval.
     */
    function sliceTimeSeries(timestamps, values, startMs, endMs) {
        if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return [];
        if (!timestamps || !values) return [];
        const min = Math.min(startMs, endMs);
        const max = Math.max(startMs, endMs);
        const length = Math.min(timestamps.length, values.length);
        const result = [];
        for (let i = 0; i < length; i++) {
            const time = Number(timestamps[i]);
            if (!Number.isFinite(time)) continue;
            if (time >= min && time <= max) {
                const value = Number(values[i]);
                if (Number.isFinite(value)) {
                    result.push(value);
                }
            }
        }
        return result;
    }

    /**
     * Calculates the energy average for each frequency band within a matrix of
     * spectral levels.
     *
     * @param {Array<Array<number>>} spectralMatrix - A matrix shaped as
     *     [frequency][time] containing decibel values.
     * @returns {number[]} The averaged level for each frequency band.
     */
    function calcAverageSpectrum(spectralMatrix) {
        if (!Array.isArray(spectralMatrix) || !spectralMatrix.length) return [];
        const result = new Array(spectralMatrix.length).fill(null);
        for (let bandIndex = 0; bandIndex < spectralMatrix.length; bandIndex++) {
            const bandValues = toFiniteArray(spectralMatrix[bandIndex]);
            result[bandIndex] = bandValues.length ? calcLAeq(bandValues) : null;
        }
        return result;
    }

    app.calcMetrics = {
        calcLAeq,
        calcLAMax,
        calcLA90,
        calcAverageSpectrum,
        sliceTimeSeries
    };
})(window.NoiseSurveyApp);
