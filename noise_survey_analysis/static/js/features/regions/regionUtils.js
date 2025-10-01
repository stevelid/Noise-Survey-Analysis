// noise_survey_analysis/static/js/features/regions/regionUtils.js

/**
 * @fileoverview Region utilities including metric calculations and import/export helpers.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    // Module-level cache for computed metrics (outside Redux state)
    const _metricsCache = new Map(); // key: `${regionId}_${parameter}`, value: metrics object

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

    function getRegionAreas(region) {
        if (!region) return [];
        if (Array.isArray(region.areas) && region.areas.length) {
            return region.areas;
        }
        if (Number.isFinite(region.start) && Number.isFinite(region.end)) {
            return [{ start: region.start, end: region.end }];
        }
        return [];
    }

    function sumAreaDurations(areas) {
        if (!Array.isArray(areas) || !areas.length) return 0;
        return areas.reduce((total, area) => {
            const start = Number(area?.start);
            const end = Number(area?.end);
            if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
                return total;
            }
            return total + (end - start);
        }, 0);
    }

    function sliceTimeSeriesForAreas(timestamps, values, areas) {
        if (!Array.isArray(areas) || !areas.length) return [];
        const aggregated = [];
        areas.forEach(area => {
            const start = Number(area?.start);
            const end = Number(area?.end);
            if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
                return;
            }
            const slice = sliceTimeSeries(timestamps, values, start, end);
            if (slice.length) {
                aggregated.push(...slice);
            }
        });
        return aggregated;
    }
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

    function computeSpectrumAverage(preparedData, areas) {
        if (!preparedData || !preparedData.levels_flat_transposed) {
            return { labels: [], values: [] };
        }
        const validAreas = Array.isArray(areas) && areas.length ? areas : [];
        if (!validAreas.length) {
            return { labels: preparedData.frequency_labels || [], values: [] };
        }
        const times = preparedData.times_ms;
        const levels = preparedData.levels_flat_transposed;
        const nFreqs = preparedData.n_freqs;
        const nTimes = preparedData.n_times;
        if (!Array.isArray(times) || !levels || !Number.isFinite(nFreqs) || !Number.isFinite(nTimes)) {
            return { labels: preparedData.frequency_labels || [], values: [] };
        }

        const energySums = new Array(nFreqs).fill(0);
        const counts = new Array(nFreqs).fill(0);

        validAreas.forEach(area => {
            const start = Number(area?.start);
            const end = Number(area?.end);
            if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
                return;
            }
            const range = clampRangeIndices(times, start, end);
            if (!range) {
                return;
            }
            for (let freqIndex = 0; freqIndex < nFreqs; freqIndex++) {
                for (let timeIndex = range.startIdx; range && timeIndex <= range.endIdx; timeIndex++) {
                    const value = levels[freqIndex * nTimes + timeIndex];
                    if (!Number.isFinite(value)) continue;
                    energySums[freqIndex] += Math.pow(10, value / 10);
                    counts[freqIndex] += 1;
                }
            }
        });

        const values = energySums.map((sum, idx) => {
            if (!counts[idx] || sum <= EPSILON) {
                return null;
            }
            return 10 * Math.log10(sum / counts[idx]);
        });

        return {
            labels: preparedData.frequency_labels || [],
            values
        };
    }

    function chooseDataset(region, sources) {
        if (!sources) return null;
        const areas = getRegionAreas(region);
        if (!areas.length) return null;

        const logData = sources.log?.data;
        if (logData?.Datetime && logData.LAeq) {
            const laeqLog = sliceTimeSeriesForAreas(logData.Datetime, logData.LAeq, areas);
            if (laeqLog.length) {
                let la90Log = null;
                if (logData.LAF90) {
                    const slicedLA90 = sliceTimeSeriesForAreas(logData.Datetime, logData.LAF90, areas);
                    if (slicedLA90.length) {
                        la90Log = slicedLA90;
                    }
                }
                return {
                    dataset: 'log',
                    data: logData,
                    laeqValues: laeqLog,
                    la90Values: la90Log
                };
            }
        }

        const overviewData = sources.overview?.data;
        if (overviewData?.Datetime && overviewData.LAeq) {
            const laeqOverview = sliceTimeSeriesForAreas(overviewData.Datetime, overviewData.LAeq, areas);
            if (laeqOverview.length) {
                let la90Overview = null;
                if (overviewData.LAF90) {
                    const slicedLA90 = sliceTimeSeriesForAreas(overviewData.Datetime, overviewData.LAF90, areas);
                    if (slicedLA90.length) {
                        la90Overview = slicedLA90;
                    }
                }
                return {
                    dataset: 'overview',
                    data: overviewData,
                    laeqValues: laeqOverview,
                    la90Values: la90Overview
                };
            }
        }

        return null;
    }

    function computeRegionMetrics(region, state, dataCache, models) {
        const areas = getRegionAreas(region);
        const durationMs = sumAreaDurations(areas);
        const sources = models?.timeSeriesSources?.[region.positionId];
        const selection = chooseDataset(region, sources);

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
            const extracted = sliceTimeSeriesForAreas(selection.data.Datetime, lafmaxField, areas);
            if (extracted.length) {
                lafmaxValues = extracted;
            }
        }
        const lafmax = calcLAMax(lafmaxValues);
        
        let la90 = null;
        if (selection.dataset === 'log') {
            if (Array.isArray(selection.la90Values) && selection.la90Values.length > 0) {
                console.log("[computeRegionMetrics] calculating LA90 from log LA90 values"); //debugging
                la90 = calcLA90(selection.la90Values);
            } else {
                console.log("[computeRegionMetrics] calculating LA90 from log LAeq values"); //debugging
                la90 = calcLA90(selection.laeqValues);
            }
        } else if (selection.dataset === 'overview') {
            if (Array.isArray(selection.la90Values) && selection.la90Values.length > 0) {
                console.log("[computeRegionMetrics] calculating LA90 from overview LA90 values"); //debugging
                la90 = calcLA90(selection.la90Values);
            } else {
                console.log("[computeRegionMetrics] calculating LA90 from overview LAeq values"); //debugging
                la90 = calcLA90(selection.laeqValues);
            }
        }

        const selectedParam = state?.view?.selectedParameter;
        const prepared = models?.preparedGlyphData?.[region.positionId];
        const logSpectral = prepared?.log?.prepared_params?.[selectedParam];
        const overviewSpectral = prepared?.overview?.prepared_params?.[selectedParam];

        let spectrumSource = null;
        let spectrum = { labels: [], values: [] };
        if (logSpectral) {
            spectrumSource = 'log';
            spectrum = computeSpectrumAverage(logSpectral, areas);
        } else if (overviewSpectral) {
            spectrumSource = 'overview';
            spectrum = computeSpectrumAverage(overviewSpectral, areas);
        }
        if (spectrum && typeof spectrum === 'object') {
            spectrum.source = spectrumSource;
        }

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

    /**
     * Gets metrics for a region, using cache if available.
     * Calculates and caches if not found.
     */
    function getRegionMetrics(region, state, dataCache, models) {
        if (!region) {
            return null;
        }
        const regionId = region.id ?? 'unknown';
        const parameter = state?.view?.selectedParameter ?? '';
        const cacheKey = `${regionId}_${parameter}`;

        if (_metricsCache.has(cacheKey)) {
            return _metricsCache.get(cacheKey);
        }

        const metrics = computeRegionMetrics(region, state, dataCache, models);
        _metricsCache.set(cacheKey, metrics);
        return metrics;
    }

    /**
     * Invalidates the entire metrics cache.
     * Call this when parameters change or data reloads.
     */
    function invalidateMetricsCache() {
        _metricsCache.clear();
    }

    /**
     * Invalidates cache for a specific region.
     * Call this when a region's boundaries change.
     */
    function invalidateRegionMetrics(regionId) {
        if (regionId === undefined || regionId === null) {
            return;
        }
        const prefix = `${regionId}_`;
        const keysToDelete = [];
        _metricsCache.forEach((_, key) => {
            if (key.startsWith(prefix)) {
                keysToDelete.push(key);
            }
        });
        keysToDelete.forEach(key => _metricsCache.delete(key));
    }

    function exportRegions(state, dataCache, models) {
        const regionsState = state?.regions;
        if (!regionsState) return '[]';
        const exportPayload = regionsState.allIds
            .map(id => regionsState.byId[id])
            .filter(Boolean)
            .map(region => {
                const metrics = getRegionMetrics(region, state, dataCache, models);
                return {
                    id: region.id,
                    positionId: region.positionId,
                    areas: getRegionAreas(region).map(area => ({ start: area.start, end: area.end })),
                    start: region.start,
                    end: region.end,
                    note: region.note || '',
                    metrics: metrics,
                    color: typeof region.color === 'string' ? region.color : null
                };
            });
        return JSON.stringify(exportPayload, null, 2);
    }

    function importRegions(jsonText) {
        try {
            const parsed = JSON.parse(jsonText);
            if (!Array.isArray(parsed)) {
                throw new Error('Imported data must be an array.');
            }
            return parsed.map(item => {
                const positionId = item?.positionId;
                const rawAreas = Array.isArray(item?.areas) && item.areas.length
                    ? item.areas
                    : [{ start: item?.start, end: item?.end }];
                const areas = rawAreas
                    .map(area => ({ start: Number(area?.start), end: Number(area?.end) }))
                    .filter(area => Number.isFinite(area.start) && Number.isFinite(area.end) && area.start !== area.end);
                if (!positionId || !areas.length) {
                    return null;
                }
                return {
                    id: Number.isFinite(item?.id) ? item.id : undefined,
                    positionId,
                    areas,
                    note: typeof item?.note === 'string' ? item.note : '',
                    color: typeof item?.color === 'string' ? item.color : undefined
                };
            }).filter(Boolean);
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
        if (!Number.isFinite(start) || !Number.isFinite(end)) return 'N/A';
        const startDate = new Date(Math.min(start, end));
        const endDate = new Date(Math.max(start, end));
        const format = date => date.toISOString().split('T')[1].replace('Z', '');
        return `${format(startDate)}-${format(endDate)}`;
    }

    function formatAreaList(areas) {
        if (!Array.isArray(areas) || !areas.length) return 'N/A';
        return areas.map(area => formatTimeRange(area.start, area.end)).join(' + ');
    }

    function normaliseSpectrumForClipboard(spectrum) {
        if (!spectrum || typeof spectrum !== 'object') {
            return { labels: [], values: [] };
        }
        const labels = Array.isArray(spectrum.labels)
            ? spectrum.labels
            : Array.isArray(spectrum.bands)
                ? spectrum.bands
                : [];
        const values = Array.isArray(spectrum.values)
            ? spectrum.values
            : Array.isArray(spectrum.band_values)
                ? spectrum.band_values
                : [];
        return { labels, values };
    }

    function formatSpectrumClipboardText(spectrum) {
        const { labels, values } = normaliseSpectrumForClipboard(spectrum);
        if (!labels.length || !values.length) {
            return '';
        }
        const rows = ['Band\tLAeq (dB)'];
        for (let i = 0; i < labels.length; i++) {
            const label = labels[i];
            const value = Number(values[i]);
            const formattedValue = Number.isFinite(value) ? value.toFixed(1) : 'N/A';
            rows.push(`${label}\t${formattedValue}`);
        }
        return rows.join('\n');
    }

    function formatRegionSummary(region, metrics, positionLabel) {
        const areas = getRegionAreas(region);
        const timeDescription = formatAreaList(areas);
        const duration = formatDuration(metrics?.durationMs);
        const laeq = metrics?.laeq !== null && metrics?.laeq !== undefined ? metrics.laeq.toFixed(1) : 'N/A';
        const la90 = metrics?.la90Available && metrics?.la90 !== null ? metrics.la90.toFixed(1) : 'N/A';
        const lafmax = metrics?.lafmax !== null && metrics?.lafmax !== undefined ? metrics.lafmax.toFixed(1) : 'N/A';
        return `Region ${region.id}, ${positionLabel}, ${timeDescription}, ${duration}, LAeq ${laeq} dB, LAF90 ${la90}, LAFmax ${lafmax} dB`;
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
        const json = exportRegions(app.store.getState(), app.dataCache, app.registry?.models);
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
                    app.store.dispatch(app.actions.regionsAdded(regionsArray));
                    invalidateMetricsCache();
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
        getRegionMetrics,
        invalidateMetricsCache,
        invalidateRegionMetrics,
        exportRegions,
        importRegions,
        formatRegionSummary,
        formatSpectrumClipboardText,
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



