// noise_survey_analysis/static/js/comparison-metrics.js

/**
 * @fileoverview Provides helper utilities for calculating comparison-mode metrics.
 * The exported function is pure and does not mutate incoming state or models.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const calcMetrics = app.calcMetrics || {};

    function normalizeBounds(start, end) {
        const rawStart = Number(start);
        const rawEnd = Number(end);
        if (!Number.isFinite(rawStart) || !Number.isFinite(rawEnd) || rawStart === rawEnd) {
            return null;
        }
        return {
            start: Math.min(rawStart, rawEnd),
            end: Math.max(rawStart, rawEnd)
        };
    }

    function chooseDatasetForSlice(bounds, sources) {
        if (!sources || !bounds) return null;
        const { start, end } = bounds;
        const logData = sources.log?.data;
        if (logData?.Datetime && logData.LAeq) {
            const laeqValues = calcMetrics.sliceTimeSeries(logData.Datetime, logData.LAeq, start, end);
            if (laeqValues.length) {
                return {
                    dataset: 'log',
                    data: logData,
                    laeqValues
                };
            }
        }

        const overviewData = sources.overview?.data;
        if (overviewData?.Datetime && overviewData.LAeq) {
            const laeqValues = calcMetrics.sliceTimeSeries(overviewData.Datetime, overviewData.LAeq, start, end);
            if (laeqValues.length) {
                return {
                    dataset: 'overview',
                    data: overviewData,
                    laeqValues
                };
            }
        }

        return null;
    }

    function clampRangeIndices(times, min, max) {
        if (!times || (typeof times.length !== 'number')) return null;
        const length = times.length;
        if (!length) return null;
        let startIdx = 0;
        while (startIdx < length && Number(times[startIdx]) < min) {
            startIdx++;
        }
        if (startIdx >= length) return null;
        let endIdx = length - 1;
        while (endIdx >= 0 && Number(times[endIdx]) > max) {
            endIdx--;
        }
        if (endIdx < startIdx) return null;
        return { startIdx, endIdx };
    }

    function computeSpectrumAverage(preparedData, bounds) {
        if (!preparedData || !bounds) {
            return { labels: [], values: [] };
        }
        const labels = Array.isArray(preparedData.frequency_labels)
            ? preparedData.frequency_labels.slice()
            : [];
        const times = preparedData.times_ms;
        const nFreqs = Number(preparedData.n_freqs);
        const nTimes = Number(preparedData.n_times);
        const levels = preparedData.levels_flat_transposed;

        if (!labels.length || !Array.isArray(times) || !levels || !Number.isFinite(nFreqs) || !Number.isFinite(nTimes)) {
            return { labels, values: [] };
        }

        const boundsIdx = clampRangeIndices(times, bounds.start, bounds.end);
        if (!boundsIdx) {
            return { labels, values: [] };
        }

        const values = new Array(nFreqs);
        for (let freqIdx = 0; freqIdx < nFreqs; freqIdx++) {
            const bandValues = [];
            for (let timeIdx = boundsIdx.startIdx; timeIdx <= boundsIdx.endIdx; timeIdx++) {
                const value = Number(levels[freqIdx * nTimes + timeIdx]);
                if (Number.isFinite(value)) {
                    bandValues.push(value);
                }
            }
            values[freqIdx] = bandValues.length ? calcMetrics.calcLAeq(bandValues) : null;
        }

        return { labels, values };
    }

    function alignSpectra(series, baseLabels) {
        if (!Array.isArray(series)) return [];
        if (!Array.isArray(baseLabels) || !baseLabels.length) {
            return series.map(item => ({
                positionId: item.positionId,
                dataset: item.dataset,
                values: Array.isArray(item.values) ? item.values.slice() : []
            }));
        }
        return series.map(item => {
            const aligned = baseLabels.map(label => {
                const idx = Array.isArray(item.labels) ? item.labels.indexOf(label) : -1;
                if (idx === -1) {
                    return null;
                }
                const value = item.values?.[idx];
                return Number.isFinite(value) ? value : (value === null ? null : Number(value));
            });
            return {
                positionId: item.positionId,
                dataset: item.dataset,
                values: aligned
            };
        });
    }

    function processComparisonSliceMetrics(options) {
        const bounds = normalizeBounds(options?.start, options?.end);
        const positionIds = Array.isArray(options?.positionIds) ? options.positionIds : [];
        const timeSeriesSources = options?.timeSeriesSources || {};
        const preparedGlyphData = options?.preparedGlyphData || {};
        const selectedParameter = typeof options?.selectedParameter === 'string'
            ? options.selectedParameter
            : null;

        if (!bounds || !positionIds.length) {
            return {
                start: bounds ? bounds.start : null,
                end: bounds ? bounds.end : null,
                metricsRows: [],
                spectrum: { labels: [], series: [] },
                hasData: false
            };
        }

        const durationMs = Math.max(0, bounds.end - bounds.start);
        const rawSpectra = [];
        const metricsRows = [];
        let hasData = false;

        positionIds.forEach(positionId => {
            const sources = timeSeriesSources[positionId];
            const selection = chooseDatasetForSlice(bounds, sources);

            if (!selection) {
                metricsRows.push({
                    positionId,
                    dataset: 'none',
                    laeq: null,
                    lafmax: null,
                    la90: null,
                    la90Available: false,
                    durationMs
                });
                return;
            }

            const laeq = calcMetrics.calcLAeq(selection.laeqValues);
            let lafmaxValues = selection.laeqValues;
            const lafmaxField = selection.data?.LAFmax;
            if (lafmaxField) {
                const extracted = calcMetrics.sliceTimeSeries(selection.data.Datetime, lafmaxField, bounds.start, bounds.end);
                if (extracted.length) {
                    lafmaxValues = extracted;
                }
            }
            const lafmax = calcMetrics.calcLAMax(lafmaxValues);
            const la90 = selection.dataset === 'log'
                ? calcMetrics.calcLA90(selection.laeqValues)
                : null;

            const glyphData = preparedGlyphData[positionId] || {};
            const parameter = selectedParameter
                || Object.keys(glyphData?.log?.prepared_params || {})[0]
                || Object.keys(glyphData?.overview?.prepared_params || {})[0]
                || 'LZeq';

            let spectralSource = selection.dataset === 'log'
                ? glyphData?.log?.prepared_params?.[parameter]
                : null;
            if (!spectralSource) {
                spectralSource = glyphData?.overview?.prepared_params?.[parameter];
            }

            const spectrum = computeSpectrumAverage(spectralSource, bounds);
            rawSpectra.push({
                positionId,
                dataset: selection.dataset,
                labels: spectrum.labels,
                values: spectrum.values
            });

            metricsRows.push({
                positionId,
                dataset: selection.dataset,
                laeq,
                lafmax,
                la90,
                la90Available: selection.dataset === 'log' && la90 !== null,
                durationMs
            });

            if (laeq !== null || lafmax !== null || (Array.isArray(spectrum.values) && spectrum.values.some(value => Number.isFinite(value)))) {
                hasData = true;
            }
        });

        let baseLabels = [];
        rawSpectra.forEach(entry => {
            if (Array.isArray(entry.labels) && entry.labels.length > baseLabels.length) {
                baseLabels = entry.labels.slice();
            }
        });

        const alignedSeries = alignSpectra(rawSpectra, baseLabels);

        return {
            start: bounds.start,
            end: bounds.end,
            metricsRows,
            spectrum: {
                labels: baseLabels,
                series: alignedSeries
            },
            hasData: hasData
        };
    }

    app.comparisonMetrics = {
        processComparisonSliceMetrics
    };
})(window.NoiseSurveyApp);
