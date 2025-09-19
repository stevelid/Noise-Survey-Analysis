// noise_survey_analysis/static/js/regions.js

/**
 * @fileoverview Helper functions for region management, including metric
 * calculations, import/export utilities, and clipboard formatting.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const calcMetrics = app.calcMetrics || {};

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
            values[freqIdx] = bandValues.length ? calcMetrics.calcLAeq(bandValues) : null;
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
            const laeqLog = calcMetrics.sliceTimeSeries(logData.Datetime, logData.LAeq, min, max);
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
            const laeqOverview = calcMetrics.sliceTimeSeries(overviewData.Datetime, overviewData.LAeq, min, max);
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
                durationMs
            };
        }

        const laeq = calcMetrics.calcLAeq(selection.laeqValues);
        let lafmaxValues = selection.laeqValues;
        const lafmaxField = selection.data?.LAFmax;
        if (lafmaxField) {
            const extracted = calcMetrics.sliceTimeSeries(selection.data.Datetime, lafmaxField, region.start, region.end);
            if (extracted.length) {
                lafmaxValues = extracted;
            }
        }
        const lafmax = calcMetrics.calcLAMax(lafmaxValues);
        const la90 = selection.dataset === 'log' ? calcMetrics.calcLA90(selection.laeqValues) : null;

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
            durationMs
        };
    }

    function prepareMetricsUpdates(state, dataCache, models) {
        const regionsState = state?.markers?.regions;
        if (!regionsState) return [];
        const updates = [];
        regionsState.allIds.forEach(id => {
            const region = regionsState.byId[id];
            if (!region) return;
            if (region.metrics) return;
            const metrics = computeRegionMetrics(region, state, dataCache, models);
            updates.push({ id, metrics });
        });
        return updates;
    }

    function exportRegions(state) {
        const regionsState = state?.markers?.regions;
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

    app.regions = {
        computeRegionMetrics,
        prepareMetricsUpdates,
        exportRegions,
        importRegions,
        formatRegionSummary,
        handleExport,
        handleImport
    };
})(window.NoiseSurveyApp);
