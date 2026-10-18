// noise_survey_analysis/static/js/features/regions/regionUtils.js

/**
 * @fileoverview Region utilities including metric calculations and import/export helpers.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    // Module-level cache for computed metrics (outside Redux state)
    const _metricsCache = new Map();
    const METRICS_CACHE_LIMIT = 2048;
    const exclusionSignatures = new WeakMap();
    const sourceIdentities = new WeakMap();
    let nextSourceIdentity = 1;
    function sourceIdentity(value) {
        if (!value || typeof value !== 'object') return 0;
        if (!sourceIdentities.has(value)) sourceIdentities.set(value, nextSourceIdentity++);
        return sourceIdentities.get(value);
    }

    function backgroundGeometrySignature(state, meter) {
        const byId = state?.regions?.byId;
        if (!byId) return '[]';
        let signatures = exclusionSignatures.get(byId);
        if (!signatures) { signatures = new Map(); exclusionSignatures.set(byId, signatures); }
        if (!signatures.has(meter)) {
            const areas = (state.regions.allIds || Object.keys(byId)).map(id => byId[id]).filter(region =>
                region && (region.positionId === meter || region.meterStates?.[meter] === 'present'))
                .flatMap(getRegionAreas);
            signatures.set(meter, JSON.stringify(app.annotationMetrics.union(areas)));
        }
        return signatures.get(meter);
    }

    function getChartOffsetMs(region, state) {
        if (!region || !state?.view?.positionChartOffsets) {
            return 0;
        }
        const raw = Number(state.view.positionChartOffsets[region.positionId]);
        return Number.isFinite(raw) ? raw : 0;
    }

    function getSourceQueryAreas(displayAreas, offsetMs) {
        if (!Array.isArray(displayAreas) || !displayAreas.length) {
            return [];
        }
        if (!Number.isFinite(offsetMs) || offsetMs === 0) {
            return displayAreas;
        }
        return displayAreas.map(area => ({
            start: Number(area.start) - offsetMs,
            end: Number(area.end) - offsetMs
        }));
    }

    function toFiniteArray(values) {
        if (!values) return [];
        if (Array.isArray(values) || ArrayBuffer.isView(values)) {
            const result = [];
            for (let i = 0; i < values.length; i++) {
                const raw = values[i];
                const value = Number(raw);
                if (raw !== null && raw !== undefined && raw !== '' && Number.isFinite(value)) {
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
        return app.annotationMetrics.energy(finiteValues, finiteValues.map(() => 1));
    }

    function calcLAMax(values) {
        const finiteValues = toFiniteArray(values);
        return app.annotationMetrics.maximum(finiteValues, finiteValues.map(() => 1));
    }

    function calcLA90(values) {
        const finiteValues = toFiniteArray(values);
        return app.annotationMetrics.percentile(finiteValues, finiteValues.map(() => 1));
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
                const raw = values[i];
                const value = Number(raw);
                if (raw !== null && raw !== undefined && raw !== '' && Number.isFinite(value)) {
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

    function computeRegionMetrics(region, state, dataCache, models, options = {}) {
        if (!region) return null;
        if (!app.annotationMetrics) throw new Error('Annotation metrics engine is not loaded.');
        return app.annotationMetrics.computeRegion(region, state, models, options);
    }

    /**
     * Gets metrics for a region, using cache if available.
     * Calculates and caches if not found.
     */
    function getRegionMetrics(region, state, dataCache, models, options = {}) {
        if (!region) {
            return null;
        }
        const regionId = region.id ?? 'unknown';
        const parameter = options.parameter || state?.view?.selectedParameter || '';
        const meter = options.positionId || options.meterId || region.positionId;
        // A manual recalculation follows the displayed series. Explicit export
        // requests can still ask for auto/best data independently of the view.
        const resolution = options.resolution
            || dataCache?.activeLineData?.[meter]?.dataViewType || 'auto';
        const offsetMs = getChartOffsetMs({ ...region, positionId: meter }, state);
        const sources = models?.timeSeriesSources?.[meter];
        const spectral = models?.preparedGlyphData?.[meter];
        const streamed = models?.spectrogramSources?.[meter]?.log?.data;
        const revision = [sourceIdentity(sources?.log?.data), sourceIdentity(sources?.overview?.data),
            sourceIdentity(spectral?.log?.prepared_params), sourceIdentity(spectral?.overview?.prepared_params),
            sourceIdentity(streamed), sourceIdentity(streamed?.levels_flat_transposed), sourceIdentity(streamed?.times_ms),
            backgroundGeometrySignature(state, meter), state?.regions?.metricsRevision || 0];
        const background = [options.backgroundWindowS ?? state?.annotationPanel?.backgroundWindowS ?? 300,
            options.minContextS ?? state?.annotationPanel?.minContextS ?? 60];
        const cacheKey = `${regionId}_${JSON.stringify([meter, parameter, offsetMs, resolution, getRegionAreas(region), revision, background])}`;

        if (!options?.force && _metricsCache.has(cacheKey)) {
            return _metricsCache.get(cacheKey);
        }

        const metrics = computeRegionMetrics(region, state, dataCache, models, { ...options, resolution });
        _metricsCache.set(cacheKey, metrics);
        // FIFO bounds long sessions without making ordinary cache reads mutate
        // ordering. Text/colour/category edits reuse the same geometry key.
        while (_metricsCache.size > METRICS_CACHE_LIMIT) _metricsCache.delete(_metricsCache.keys().next().value);
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

    /** Invalidates metrics for regions belonging to one refreshed position. */
    function invalidatePositionMetrics(positionId, state) {
        if (positionId === undefined || positionId === null) return;
        const regionsState = state?.regions;
        if (!regionsState?.byId || !Array.isArray(regionsState.allIds)) return;
        const positionKey = String(positionId);
        regionsState.allIds.forEach(regionId => {
            const region = regionsState.byId[regionId];
            if (region && (String(region.positionId) === positionKey || Object.hasOwn(region.meterStates || {}, positionKey))) {
                invalidateRegionMetrics(regionId);
            }
        });
    }

    function exportRegions(state, dataCache, models) {
        const regionsState = state?.regions;
        if (!regionsState) return '[]';
        const exportPayload = regionsState.allIds
            .map(id => regionsState.byId[id])
            .filter(Boolean)
            .map(region => {
                const metrics = getRegionMetrics(region, state, dataCache, models);
                const displayAreas = getRegionAreas(region);
                const offsetMs = metrics?.chartOffsetMs ?? 0;
                const sourceAreas = getSourceQueryAreas(displayAreas, offsetMs);
                return {
                    id: region.id,
                    positionId: region.positionId,
                    areas: displayAreas.map(area => ({ start: area.start, end: area.end })),
                    start: region.start,
                    end: region.end,
                    chartOffsetMs: offsetMs,
                    sourceAreas: sourceAreas.map(area => ({ start: area.start, end: area.end })),
                    note: region.note || '',
                    metrics: metrics,
                    dataSource: metrics?.dataResolution ?? 'none',
                    spectrumDataSource: metrics?.spectrum?.source ?? 'none',
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
                    color: typeof item?.color === 'string' ? item.color : undefined,
                    ...(item?.categoryId ? { categoryId: item.categoryId } : {}),
                    ...(item?.meterStates ? { meterStates: item.meterStates } : {})
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
        invalidatePositionMetrics,
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



