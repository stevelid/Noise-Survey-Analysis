// noise_survey_analysis/static/js/features/regions/regionUtils.js

/**
 * @fileoverview Region utilities including metric calculations and import/export helpers.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

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

    const EPSILON = 1e-12;

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

    function calcAverageSpectrum(spectralMatrix) {
        if (!Array.isArray(spectralMatrix) || !spectralMatrix.length) return [];
        const result = new Array(spectralMatrix.length).fill(null);
        for (let bandIndex = 0; bandIndex < spectralMatrix.length; bandIndex++) {
            const bandValues = toFiniteArray(spectralMatrix[bandIndex]);
            result[bandIndex] = bandValues.length ? calcLAeq(bandValues) : null;
        }
        return result;
    }

    function clampRangeIndices(times, min, max) {
        if (!Array.isArray(times) && !ArrayBuffer.isView(times)) return null;
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

    function computeSpectrumAverage(preparedData, start, end) {
        if (!preparedData || !preparedData.levels_flat_transposed) {
            return { labels: [], values: [] };
        }
        const min = Math.min(start, end);
        const max = Math.max(start, end);
        const times = preparedData.times_ms;
        if (!times || !times.length) {
            return { labels: preparedData.frequency_labels || [], values: [] };
        }
        const bounds = clampRangeIndices(times, min, max);
        if (!bounds) {
            return { labels: preparedData.frequency_labels || [], values: [] };
        }

        const nFreqs = preparedData.n_freqs;
        const nTimes = preparedData.n_times;
        const levels = preparedData.levels_flat_transposed;
        if (!Number.isFinite(nFreqs) || !Number.isFinite(nTimes) || !levels) {
            return { labels: preparedData.frequency_labels || [], values: [] };
        }

        const values = new Array(nFreqs);
        for (let freqIdx = 0; freqIdx < nFreqs; freqIdx++) {
            const bandValues = [];
            for (let timeIdx = bounds.startIdx; timeIdx <= bounds.endIdx; timeIdx++) {
                const value = Number(levels[freqIdx * nTimes + timeIdx]);
                if (Number.isFinite(value)) {
                    bandValues.push(value);
                }
            }
            values[freqIdx] = bandValues.length ? calcLAeq(bandValues) : null;
        }
        return {
            labels: preparedData.frequency_labels || [],
            values
        };
    }

    function chooseDataset(region, sources) {
        if (!sources) return null;
        const min = Math.min(region.start, region.end);
        const max = Math.max(region.start, region.end);

        const logData = sources.log?.data;
        if (logData?.Datetime && logData.LAeq) {
            const laeqLog = sliceTimeSeries(logData.Datetime, logData.LAeq, min, max);
            if (laeqLog.length) {
                return {
                    dataset: 'log',
                    data: logData,
                    laeqValues: laeqLog
                };
            }
        }

        const overviewData = sources.overview?.data;
        if (overviewData?.Datetime && overviewData.LAeq) {
            const laeqOverview = sliceTimeSeries(overviewData.Datetime, overviewData.LAeq, min, max);
            if (laeqOverview.length) {
                return {
                    dataset: 'overview',
                    data: overviewData,
                    laeqValues: laeqOverview
                };
            }
        }

        return null;
    }

    function computeRegionMetrics(region, state, dataCache, models) {
        const sources = models?.timeSeriesSources?.[region.positionId];
        const selection = chooseDataset(region, sources);
        const durationMs = Math.max(0, region.end - region.start);

        if (!selection) {
            return {
                laeq: null,
                lafmax: null,
                la90: null,
                la90Available: false,
                dataResolution: 'none',
                spectrum: { labels: [], values: [] },
                parameter: state?.view?.selectedParameter || null,
                durationMs
            };
        }

        const laeq = calcLAeq(selection.laeqValues);
        let lafmaxValues = selection.laeqValues;
        const lafmaxField = selection.data?.LAFmax;
        if (lafmaxField) {
            const extracted = sliceTimeSeries(selection.data.Datetime, lafmaxField, region.start, region.end);
            if (extracted.length) {
                lafmaxValues = extracted;
            }
        }
        const lafmax = calcLAMax(lafmaxValues);
        const la90 = selection.dataset === 'log' ? calcLA90(selection.laeqValues) : null;

        const selectedParam = state?.view?.selectedParameter;
        const prepared = models?.preparedGlyphData?.[region.positionId];
        let spectralSource = null;
        if (selection.dataset === 'log') {
            spectralSource = prepared?.log?.prepared_params?.[selectedParam];
        }
        if (!spectralSource) {
            spectralSource = prepared?.overview?.prepared_params?.[selectedParam];
        }

        const spectrum = computeSpectrumAverage(spectralSource, region.start, region.end);

        return {
            laeq,
            lafmax,
            la90,
            la90Available: selection.dataset === 'log' && la90 !== null,
            dataResolution: selection.dataset,
            spectrum,
            parameter: selectedParam || null,
            durationMs
        };
    }

    function hasSpectralDataForParam(prepared, parameter) {
        if (!prepared || !parameter) return false;
        const log = prepared?.log?.prepared_params?.[parameter];
        if (log) return true;
        const overview = prepared?.overview?.prepared_params?.[parameter];
        return Boolean(overview);
    }

    function hasSpectrumValues(metrics) {
        if (!metrics?.spectrum) return false;
        const values = metrics.spectrum.values;
        if (!Array.isArray(values) || !values.length) return false;
        return values.some(value => Number.isFinite(value));
    }

    function prepareMetricsUpdates(state, dataCache, models) {
        const regionsState = state?.regions;
        if (!regionsState) return [];
        const updates = [];
        const selectedParam = state?.view?.selectedParameter || null;
        regionsState.allIds.forEach(id => {
            const region = regionsState.byId[id];
            if (!region) return;
            const prepared = models?.preparedGlyphData?.[region.positionId];
            const currentMetrics = region.metrics || null;
            const shouldUpdate =
                !currentMetrics
                || currentMetrics.parameter !== selectedParam
                || (currentMetrics.dataResolution === 'none' && hasSpectralDataForParam(prepared, selectedParam))
                || (!hasSpectrumValues(currentMetrics) && hasSpectralDataForParam(prepared, selectedParam));
            if (!shouldUpdate) return;
            const metrics = computeRegionMetrics(region, state, dataCache, models);
            updates.push({ id, metrics });
        });
        return updates;
    }

    function exportRegions(state) {
        const regionsState = state?.regions;
        if (!regionsState) return '[]';
        const exportPayload = regionsState.allIds.map(id => regionsState.byId[id]).filter(Boolean).map(region => ({
            id: region.id,
            positionId: region.positionId,
            start: region.start,
            end: region.end,
            note: region.note || '',
            metrics: region.metrics || null
        }));
        return JSON.stringify(exportPayload, null, 2);
    }

    function importRegions(jsonText) {
        try {
            const parsed = JSON.parse(jsonText);
            if (!Array.isArray(parsed)) {
                throw new Error('Imported data must be an array.');
            }
            return parsed.map(item => ({
                id: Number.isFinite(item?.id) ? item.id : undefined,
                positionId: item?.positionId,
                start: item?.start,
                end: item?.end,
                note: typeof item?.note === 'string' ? item.note : '',
                metrics: item?.metrics || null
            })).filter(region => Number.isFinite(region.start) && Number.isFinite(region.end) && region.positionId);
        } catch (error) {
            console.error('[Regions] Failed to import regions:', error);
            return [];
        }
    }

    function formatDuration(ms) {
        if (!Number.isFinite(ms) || ms <= 0) return '0s';
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        const parts = [];
        if (minutes) parts.push(`${minutes}m`);
        parts.push(`${seconds}s`);
        return parts.join('');
    }

    function formatTimeRange(start, end) {
        const startDate = new Date(Math.min(start, end));
        const endDate = new Date(Math.max(start, end));
        const format = date => date.toISOString().split('T')[1].replace('Z', '');
        return `${format(startDate)}–${format(endDate)}`;
    }

    function formatRegionSummary(region, metrics, positionLabel) {
        const timeRange = formatTimeRange(region.start, region.end);
        const duration = formatDuration(metrics?.durationMs);
        const laeq = metrics?.laeq !== null && metrics?.laeq !== undefined ? metrics.laeq.toFixed(1) : 'N/A';
        const la90 = metrics?.la90Available && metrics?.la90 !== null ? metrics.la90.toFixed(1) : 'N/A';
        const lafmax = metrics?.lafmax !== null && metrics?.lafmax !== undefined ? metrics.lafmax.toFixed(1) : 'N/A';
        return `Region ${region.id}, ${positionLabel}, ${timeRange}, ${duration}, LAeq ${laeq} dB, LAF90 ${la90}, LAFmax ${lafmax} dB`;
    }

    function triggerDownload(filename, text) {
        const blob = new Blob([text], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = filename;
        document.body.appendChild(anchor);
        anchor.click();
        document.body.removeChild(anchor);
        URL.revokeObjectURL(url);
    }

    function handleExport() {
        if (!app.store) {
            console.error('[Regions] Store not available for export.');
            return;
        }
        const json = exportRegions(app.store.getState());
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        triggerDownload(`regions-${timestamp}.json`, json);
    }

    function handleImport() {
        if (!app.store) {
            console.error('[Regions] Store not available for import.');
            return;
        }
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'application/json';
        fileInput.addEventListener('change', event => {
            const file = event.target.files?.[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = () => {
                const regionsArray = importRegions(reader.result);
                if (regionsArray.length) {
                    app.store.dispatch(app.actions.regionReplaceAll(regionsArray));
                }
            };
            reader.readAsText(file);
        });
        fileInput.click();
    }

    const metrics = {
        calcLAeq,
        calcLAMax,
        calcLA90,
        calcAverageSpectrum,
        sliceTimeSeries
    };

    const utils = {
        computeRegionMetrics,
        prepareMetricsUpdates,
        exportRegions,
        importRegions,
        formatRegionSummary,
        handleExport,
        handleImport
    };

    app.features = app.features || {};
    app.features.regions = app.features.regions || {};
    app.features.regions.utils = utils;
    app.features.regions.metrics = metrics;

    app.calcMetrics = metrics;
    app.regions = utils;
})(window.NoiseSurveyApp);
