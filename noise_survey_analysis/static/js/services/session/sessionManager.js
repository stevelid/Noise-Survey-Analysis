// noise_survey_analysis/static/js/services/session/sessionManager.js

/**
 * @fileoverview Manages workspace save/load actions and bridges them to the
 *               Redux-style store. Exposes a small API on `NoiseSurveyApp.session`
 *               that is used by the Bokeh toolbar dropdown.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const SESSION_FILE_VERSION = 2;
    let initialStateApplied = false;
    let sessionStatusListenerAttached = false;
    let automationListenerAttached = false;
    let automationAttachRetryTimer = null;
    let automationAttachRetryCount = 0;
    let lastSessionStatusUpdateAt = null;
    let lastAutomationRequestId = null;
    let lastTriggeredRequestId = null;
    let toastContainer = null;
    const AUTOMATION_ATTACH_RETRY_DELAY_MS = 150;
    const AUTOMATION_ATTACH_MAX_RETRIES = 40;

    function ensureToastContainer() {
        if (toastContainer && document.body?.contains(toastContainer)) {
            return toastContainer;
        }

        const container = document.createElement('div');
        container.id = 'session-toast-container';
        container.style.position = 'fixed';
        container.style.top = '16px';
        container.style.right = '16px';
        container.style.display = 'flex';
        container.style.flexDirection = 'column';
        container.style.gap = '8px';
        container.style.zIndex = '10000';
        container.style.pointerEvents = 'none';
        document.body.appendChild(container);
        toastContainer = container;
        return toastContainer;
    }

    function showToast(message, level = 'info', durationMs = 3200) {
        if (!message || !document?.body) {
            return;
        }
        const container = ensureToastContainer();
        if (!container) {
            return;
        }

        const toast = document.createElement('div');
        toast.textContent = String(message);
        toast.style.maxWidth = '420px';
        toast.style.padding = '10px 12px';
        toast.style.borderRadius = '6px';
        toast.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.22)';
        toast.style.fontSize = '12px';
        toast.style.lineHeight = '1.35';
        toast.style.color = '#ffffff';
        toast.style.pointerEvents = 'auto';
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 160ms ease';

        if (level === 'error') {
            toast.style.background = '#b42318';
        } else if (level === 'warning') {
            toast.style.background = '#b54708';
        } else {
            toast.style.background = '#175cd3';
        }

        container.appendChild(toast);
        requestAnimationFrame(() => {
            toast.style.opacity = '1';
        });

        const timeoutMs = Number.isFinite(Number(durationMs)) ? Number(durationMs) : 3200;
        window.setTimeout(() => {
            toast.style.opacity = '0';
            window.setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 180);
        }, timeoutMs);
    }

    function triggerJsonDownload(filename, jsonText) {
        try {
            const blob = new Blob([jsonText], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = filename;
            document.body.appendChild(anchor);
            anchor.click();
            document.body.removeChild(anchor);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('[Session] Failed to trigger download:', error);
        }
    }

    function triggerCsvDownload(filename, csvText) {
        try {
            const blob = new Blob([csvText], { type: 'text/csv' });
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = filename;
            document.body.appendChild(anchor);
            anchor.click();
            document.body.removeChild(anchor);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('[Session] Failed to trigger CSV download:', error);
        }
    }

    const CSV_HEADER = ['type', 'id', 'positionId', 'start_utc', 'end_utc', 'note', 'color', 'areas'];
    const METRIC_COLUMNS = [
        'timestamp_utc',
        'duration_ms',
        'metrics_parameter',
        'metrics_data_resolution',
        'metrics_duration_ms',
        'metrics_laeq',
        'metrics_lafmax',
        'metrics_la90',
        'metrics_la90_available',
        'metrics_broadband_value',
        'metrics_broadband_position',
        'metrics_timestamp_utc',
        'metrics_spectrum_source'
    ];

    // Provenance columns added after CSV_HEADER; import parser ignores them (not in CSV_HEADER).
    const PROVENANCE_COLUMNS = ['chart_offset_ms', 'source_start_utc', 'source_end_utc', 'source_areas'];

    // Mirrors getChartOffsetMs from regionUtils — CSV export uses the same offset convention
    // as the region metric source-query logic.
    function getCsvExportOffsetMs(region, state) {
        if (!region || !state?.view?.positionChartOffsets) return 0;
        const raw = Number(state.view.positionChartOffsets[region.positionId]);
        return Number.isFinite(raw) ? raw : 0;
    }

    function escapeCsvValue(value) {
        if (value === null || value === undefined) {
            return '';
        }
        const stringValue = String(value);
        if (/[",\n\r]/.test(stringValue)) {
            return '"' + stringValue.replace(/"/g, '""') + '"';
        }
        return stringValue;
    }

    function formatTimestampForCsv(timestamp) {
        const numericTimestamp = Number(timestamp);
        if (!Number.isFinite(numericTimestamp)) {
            return '';
        }
        const date = new Date(numericTimestamp);
        if (Number.isNaN(date.getTime())) {
            return '';
        }

        const pad = (value, length) => String(value).padStart(length, '0');

        return [
            `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1, 2)}-${pad(date.getUTCDate(), 2)}`,
            `${pad(date.getUTCHours(), 2)}:${pad(date.getUTCMinutes(), 2)}:${pad(date.getUTCSeconds(), 2)}.${pad(date.getUTCMilliseconds(), 3)}`
        ].join(' ');
    }

    function parseTimestampFromCsv(value) {
        if (value === null || value === undefined) {
            return null;
        }

        if (typeof value === 'number') {
            return Number.isFinite(value) ? value : null;
        }

        const trimmed = String(value).trim();
        if (!trimmed) {
            return null;
        }

        const numeric = Number(trimmed);
        if (Number.isFinite(numeric)) {
            return numeric;
        }

        let normalized = trimmed.replace(' ', 'T');
        if (!/[zZ]|[+-]\d\d:?\d\d$/.test(normalized)) {
            normalized += 'Z';
        }

        let parsed = Date.parse(normalized);
        if (!Number.isNaN(parsed)) {
            return parsed;
        }

        const fallbackMatch = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,3}))?(?:Z)?$/);
        if (fallbackMatch) {
            const [, year, month, day, hours, minutes, seconds, millis] = fallbackMatch;
            const millisecondValue = millis ? Number(String(millis).padEnd(3, '0')) : 0;
            return Date.UTC(
                Number(year),
                Number(month) - 1,
                Number(day),
                Number(hours),
                Number(minutes),
                Number(seconds),
                millisecondValue
            );
        }

        throw new Error(`Invalid timestamp value: ${value}`);
    }

    function formatNumberValue(value, decimals = null) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) {
            return '';
        }
        if (decimals === 0) {
            return String(Math.round(numeric));
        }
        if (Number.isInteger(numeric)) {
            return String(numeric);
        }
        const precision = Number.isInteger(decimals) && decimals >= 0 ? decimals : 3;
        const factor = Math.pow(10, precision);
        return String(Math.round(numeric * factor) / factor);
    }

    function normaliseBandKey(label) {
        if (label === null || label === undefined) {
            return null;
        }
        const trimmed = String(label).trim();
        if (!trimmed) {
            return null;
        }
        return trimmed.toLowerCase();
    }

    function compareBandLabels(a, b) {
        return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
    }

    function makeBandColumnName(label, usedNames) {
        const raw = String(label)
            .trim()
            .replace(/\s+/g, '_')
            .replace(/[^0-9a-zA-Z_]+/g, '_')
            .replace(/_+/g, '_')
            .replace(/^_+|_+$/g, '');
        const base = raw ? `band_${raw}` : 'band_value';
        let candidate = base;
        let suffix = 2;
        while (usedNames.has(candidate)) {
            candidate = `${base}_${suffix}`;
            suffix += 1;
        }
        usedNames.add(candidate);
        return candidate;
    }

    function extractMarkerBroadband(marker) {
        const metrics = marker?.metrics;
        if (!metrics) {
            return null;
        }
        const broadbandEntries = Array.isArray(metrics.broadband) ? metrics.broadband : [];
        if (!broadbandEntries.length) {
            return null;
        }
        const markerPosition = typeof marker?.positionId === 'string' ? marker.positionId : null;
        let entry = markerPosition
            ? broadbandEntries.find(item => item?.positionId === markerPosition)
            : null;
        if (!entry) {
            entry = broadbandEntries.find(item => Number.isFinite(Number(item?.value))) || null;
        }
        if (!entry) {
            return null;
        }
        const value = Number(entry.value);
        return {
            positionId: typeof entry.positionId === 'string' ? entry.positionId : markerPosition || '',
            value: Number.isFinite(value) ? value : null
        };
    }

    function extractMarkerSpectrum(marker) {
        const metrics = marker?.metrics;
        if (!metrics) {
            return { labels: [], values: [] };
        }
        const spectralEntries = Array.isArray(metrics.spectral) ? metrics.spectral : [];
        let snapshot = null;
        const markerPosition = typeof marker?.positionId === 'string' ? marker.positionId : null;
        if (markerPosition) {
            snapshot = spectralEntries.find(item => item?.positionId === markerPosition) || null;
        }
        if (!snapshot && spectralEntries.length) {
            snapshot = spectralEntries[0];
        }
        if (!snapshot) {
            return { labels: [], values: [] };
        }
        const labels = Array.isArray(snapshot.labels)
            ? snapshot.labels
            : Array.isArray(snapshot.bands)
                ? snapshot.bands
                : [];
        const values = Array.isArray(snapshot.values)
            ? snapshot.values
            : Array.isArray(snapshot.band_values)
                ? snapshot.band_values
                : [];
        return { labels, values };
    }

    function resolveRegionMetrics(region, state, dataCache, models) {
        const utils = app.features?.regions?.utils || {};
        if (!state && region?.metrics) {
            return region.metrics;
        }
        if (utils.getRegionMetrics && state) {
            return utils.getRegionMetrics(region, state, dataCache, models);
        }
        return region?.metrics || null;
    }

    function extractRegionSpectrum(region, state, dataCache, models) {
        const spectrum = resolveRegionMetrics(region, state, dataCache, models)?.spectrum || {};
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
        return {
            labels,
            values
        };
    }

    function collectBandColumns(markers, regions, state, dataCache, models) {
        const labelSet = new Map();

        function addLabels(labels) {
            if (!Array.isArray(labels)) {
                return;
            }
            labels.forEach(label => {
                const key = normaliseBandKey(label);
                if (!key || labelSet.has(key)) {
                    return;
                }
                labelSet.set(key, String(label));
            });
        }

        markers.forEach(marker => {
            const spectrum = extractMarkerSpectrum(marker);
            addLabels(spectrum.labels);
        });
        regions.forEach(region => {
            const spectrum = extractRegionSpectrum(region, state, dataCache, models);
            addLabels(spectrum.labels);
        });

        const sortedLabels = Array.from(labelSet.values()).sort(compareBandLabels);
        const usedNames = new Set();
        return sortedLabels.map(label => ({
            label,
            key: normaliseBandKey(label),
            column: makeBandColumnName(label, usedNames)
        }));
    }

    function assignSpectrumValues(rowData, spectrum, bandLookup) {
        if (!spectrum) {
            return;
        }
        const labels = Array.isArray(spectrum.labels) ? spectrum.labels : [];
        const values = Array.isArray(spectrum.values) ? spectrum.values : [];
        for (let i = 0; i < labels.length; i++) {
            const key = normaliseBandKey(labels[i]);
            if (!key) {
                continue;
            }
            const column = bandLookup.get(key);
            if (!column) {
                continue;
            }
            rowData[column] = formatNumberValue(values[i]);
        }
    }

    function buildAnnotationsCsv(markersInput, regionsInput, state, options = {}) {
        if (!app.annotationCsv) throw new Error('Sectioned annotation CSV module is not loaded.');
        return app.annotationCsv.buildAnnotationsCsv(markersInput, regionsInput, state, options);
    }

    function parseCsvRows(text) {
        if (typeof text !== 'string') {
            return [];
        }

        const rows = [];
        let currentValue = '';
        let currentRow = [];
        let inQuotes = false;

        for (let index = 0; index < text.length; index++) {
            const char = text[index];
            if (inQuotes) {
                if (char === '"') {
                    if (text[index + 1] === '"') {
                        currentValue += '"';
                        index += 1;
                    } else {
                        inQuotes = false;
                    }
                } else {
                    currentValue += char;
                }
            } else if (char === '"') {
                inQuotes = true;
            } else if (char === ',') {
                currentRow.push(currentValue);
                currentValue = '';
            } else if (char === '\r' || char === '\n') {
                currentRow.push(currentValue);
                currentValue = '';
                if (char === '\r' && text[index + 1] === '\n') {
                    index += 1;
                }
                rows.push(currentRow);
                currentRow = [];
            } else {
                currentValue += char;
            }
        }

        if (inQuotes) {
            throw new Error('Unterminated quoted field in CSV data.');
        }

        currentRow.push(currentValue);
        rows.push(currentRow);

        return rows.filter(row => row.some(cell => String(cell ?? '').trim() !== ''));
    }

    function parseLegacyAnnotationsCsv(csvText) {
        const rows = parseCsvRows(csvText);
        if (!rows.length) {
            return { markers: [], regions: [] };
        }

        const headerRow = rows[0].map(cell => String(cell || '').trim().toLowerCase());
        const columnIndex = {};
        CSV_HEADER.forEach(column => {
            const index = headerRow.indexOf(column.toLowerCase());
            if (index >= 0) {
                columnIndex[column] = index;
            }
        });

        if (columnIndex.type === undefined || columnIndex.start_utc === undefined) {
            throw new Error('[Session] CSV is missing required annotation columns.');
        }

        const markers = [];
        const regions = [];

        for (let i = 1; i < rows.length; i++) {
            const row = rows[i];
            if (!row || !row.length || row.every(cell => String(cell || '').trim() === '')) {
                continue;
            }

            const typeValue = String(row[columnIndex.type] || '').trim().toLowerCase();
            const idCell = columnIndex.id !== undefined ? row[columnIndex.id] : undefined;
            const parsedId = Number(idCell);
            const id = Number.isFinite(parsedId) && parsedId > 0 ? parsedId : undefined;
            const positionValue = columnIndex.positionId !== undefined ? row[columnIndex.positionId] : '';
            const positionId = positionValue == null ? '' : String(positionValue).trim();
            const startValue = columnIndex.start_utc !== undefined ? row[columnIndex.start_utc] : '';
            const endValue = columnIndex.end_utc !== undefined ? row[columnIndex.end_utc] : '';
            const noteCell = columnIndex.note !== undefined ? row[columnIndex.note] : '';
            const colorCell = columnIndex.color !== undefined ? row[columnIndex.color] : '';

            const areasCell = columnIndex.areas !== undefined ? row[columnIndex.areas] : '';
            const note = noteCell == null ? '' : String(noteCell);
            const color = colorCell == null ? '' : String(colorCell).trim();

            try {
                if (typeValue === 'marker') {
                    const startTimestamp = parseTimestampFromCsv(startValue);
                    if (!Number.isFinite(startTimestamp)) {
                        continue;
                    }
                    const marker = {
                        timestamp: startTimestamp,
                        note
                    };
                    if (id !== undefined) {
                        marker.id = id;
                    }
                    if (color) {
                        marker.color = color;
                    }
                    if (positionId) {
                        marker.positionId = positionId;
                    }
                    markers.push(marker);
                } else if (typeValue === 'region') {
                    const startTimestamp = parseTimestampFromCsv(startValue);
                    const endTimestamp = parseTimestampFromCsv(endValue);
                    if (!Number.isFinite(startTimestamp) || !Number.isFinite(endTimestamp)) {
                        continue;
                    }
                    if (!positionId) {
                        continue;
                    }
                    const normalizedStart = Math.min(startTimestamp, endTimestamp);
                    const normalizedEnd = Math.max(startTimestamp, endTimestamp);
                    if (normalizedStart === normalizedEnd) {
                        continue;
                    }

                    let parsedAreas = [];
                    if (areasCell !== undefined && areasCell !== null && String(areasCell).trim() !== '') {
                        try {
                            const areasValue = JSON.parse(String(areasCell));
                            const areaArray = Array.isArray(areasValue) ? areasValue : [areasValue];
                            areaArray.forEach(areaEntry => {
                                if (areaEntry == null) {
                                    return;
                                }
                                let startCandidate;
                                let endCandidate;
                                if (Array.isArray(areaEntry)) {
                                    [startCandidate, endCandidate] = areaEntry;
                                } else if (typeof areaEntry === 'object') {
                                    startCandidate = areaEntry.startUtc ?? areaEntry.start ?? areaEntry.start_utc;
                                    endCandidate = areaEntry.endUtc ?? areaEntry.end ?? areaEntry.end_utc;
                                } else {
                                    const [startPart, endPart] = String(areaEntry).split(/\s*[,;|]\s*/);
                                    startCandidate = startPart;
                                    endCandidate = endPart;
                                }
                                const areaStart = parseTimestampFromCsv(startCandidate);
                                const areaEnd = parseTimestampFromCsv(endCandidate);
                                if (!Number.isFinite(areaStart) || !Number.isFinite(areaEnd)) {
                                    return;
                                }
                                const normalizedAreaStart = Math.min(areaStart, areaEnd);
                                const normalizedAreaEnd = Math.max(areaStart, areaEnd);
                                if (normalizedAreaStart === normalizedAreaEnd) {
                                    return;
                                }
                                parsedAreas.push({ start: normalizedAreaStart, end: normalizedAreaEnd });
                            });
                        } catch (error) {
                            console.warn('[Session] Failed to parse region areas from CSV:', error);
                            parsedAreas = [];
                        }
                    }

                    if (!parsedAreas.length) {
                        parsedAreas = [{ start: normalizedStart, end: normalizedEnd }];
                    }

                    const combinedStart = parsedAreas.reduce(
                        (minStart, area) => Math.min(minStart, area.start),
                        parsedAreas[0].start
                    );
                    const combinedEnd = parsedAreas.reduce(
                        (maxEnd, area) => Math.max(maxEnd, area.end),
                        parsedAreas[0].end
                    );

                    const region = {
                        positionId,
                        start: combinedStart,
                        end: combinedEnd,
                        areas: parsedAreas,
                        note
                    };
                    if (id !== undefined) {
                        region.id = id;
                    }
                    if (color) {
                        region.color = color;
                    }
                    regions.push(region);
                } else {
                    console.warn('[Session] Unrecognised annotation type in CSV:', row[columnIndex.type]);
                }
            } catch (error) {
                console.warn('[Session] Skipping invalid annotation row:', error);
            }
        }

        const positions = app.store?.getState?.()?.view?.availablePositions || [];
        const consolidation = app.annotationModel?.consolidateLegacyRegions?.(regions, positions);
        return consolidation
            ? { markers, regions: consolidation.regions, mergedCount: consolidation.mergedCount }
            : { markers, regions, mergedCount: 0 };
    }

    function parseAnnotationsCsv(csvText) {
        const rows = app.annotationCsv?.parseCsvRows(csvText);
        if (rows?.some(row => row[0]?.trim() === '[REGIONS]')) return app.annotationCsv.parseAnnotationsCsv(csvText);
        return parseLegacyAnnotationsCsv(csvText);
    }

    function normaliseMarkerFromJson(entry) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        const timestampCandidate = entry.timestamp ?? entry.timestampMs ?? entry.timestamp_ms ?? entry.time ?? entry.timeUtc ?? entry.time_utc;
        const timestamp = Number(timestampCandidate);
        if (!Number.isFinite(timestamp)) {
            return null;
        }
        const marker = {
            timestamp,
            note: typeof entry.note === 'string' ? entry.note : ''
        };
        const idCandidate = Number(entry.id);
        if (Number.isFinite(idCandidate) && idCandidate > 0) {
            marker.id = idCandidate;
        }
        if (typeof entry.color === 'string' && entry.color) {
            marker.color = entry.color;
        }
        const positionCandidate = entry.positionId ?? entry.position_id ?? entry.position;
        if (typeof positionCandidate === 'string' && positionCandidate) {
            marker.positionId = positionCandidate;
        }
        if (entry.metrics && typeof entry.metrics === 'object') {
            marker.metrics = entry.metrics;
        }
        return marker;
    }

    function importMarkersFromJson(entries) {
        if (!Array.isArray(entries) || !entries.length) {
            return false;
        }
        if (!app.store || typeof app.store.dispatch !== 'function') {
            console.error('[Session] Store not available; cannot import markers.');
            return false;
        }
        if (!app.actions || typeof app.actions.markersReplace !== 'function') {
            console.error('[Session] Marker replace action is unavailable.');
            return false;
        }
        const normalised = entries
            .map(normaliseMarkerFromJson)
            .filter(Boolean);
        if (!normalised.length) {
            return false;
        }
        app.store.dispatch(app.actions.markersReplace(normalised));
        return true;
    }

    function importRegionsFromJson(entries) {
        if (!Array.isArray(entries) || !entries.length) {
            return false;
        }
        if (!app.store || typeof app.store.dispatch !== 'function') {
            console.error('[Session] Store not available; cannot import regions.');
            return false;
        }
        if (!app.actions || typeof app.actions.regionsAdded !== 'function') {
            console.error('[Session] Region add action is unavailable.');
            return false;
        }
        const importRegionsFn = app.features?.regions?.utils?.importRegions;
        if (typeof importRegionsFn !== 'function') {
            console.error('[Session] Region import utility is unavailable.');
            return false;
        }
        try {
            const payload = importRegionsFn(JSON.stringify(entries));
            if (!Array.isArray(payload) || !payload.length) {
                return false;
            }
            const positions = app.store.getState()?.view?.availablePositions || [];
            const consolidated = app.annotationModel?.consolidateLegacyRegions?.(payload, positions)
                || { regions: payload, mergedCount: 0 };
            app.store.dispatch(app.actions.regionsAdded(consolidated.regions));
            if (consolidated.mergedCount) showToast(`Merged ${consolidated.mergedCount} legacy region copies across meters.`);
            const utils = app.features?.regions?.utils;
            if (utils?.invalidateMetricsCache) {
                utils.invalidateMetricsCache();
            }
            // Pre-compute metrics for all imported regions so spectrum data is available
            if (typeof utils?.getRegionMetrics === 'function') {
                const state = app.store.getState();
                const models = app.registry?.models;
                const dataCache = app.dataCache;
                const regionsState = state?.regions;
                if (regionsState?.allIds && regionsState?.byId) {
                    regionsState.allIds.forEach(id => {
                        const region = regionsState.byId[id];
                        if (region) {
                            utils.getRegionMetrics(region, state, dataCache, models);
                        }
                    });
                }
            }
            return true;
        } catch (error) {
            console.error('[Session] Failed to import regions from JSON:', error);
            return false;
        }
    }

    function importAnnotationsFromJson(jsonText) {
        if (typeof jsonText !== 'string') {
            throw new Error('Annotation payload must be a string.');
        }
        let parsed;
        try {
            parsed = JSON.parse(jsonText);
        } catch (error) {
            throw new Error('Invalid JSON annotation file.');
        }

        let imported = false;
        if (Array.isArray(parsed)) {
            imported = importRegionsFromJson(parsed) || imported;
        } else if (parsed && typeof parsed === 'object') {
            if (Array.isArray(parsed.classifications)) {
                try {
                    imported = importClassificationEntries(parsed.classifications) > 0 || imported;
                } catch (error) {
                    console.warn('[Session] Classification JSON import skipped:', error);
                }
            }
            if (Array.isArray(parsed.regions)) {
                imported = importRegionsFromJson(parsed.regions) || imported;
            }
            if (Array.isArray(parsed.markers)) {
                imported = importMarkersFromJson(parsed.markers) || imported;
            }
            if (!imported && Array.isArray(parsed.annotations)) {
                const annotations = parsed.annotations;
                const markerCandidates = annotations.filter(item => item?.type === 'marker').map(item => item?.data ?? item);
                const regionCandidates = annotations.filter(item => item?.type === 'region').map(item => item?.data ?? item);
                imported = importMarkersFromJson(markerCandidates) || imported;
                imported = importRegionsFromJson(regionCandidates) || imported;
            }
        }

        if (!imported) {
            throw new Error('No annotations found in JSON file.');
        }
        return true;
    }

    function shouldTreatContentAsJson(filename, fileText) {
        if (typeof filename === 'string' && /\.json$/i.test(filename)) {
            return true;
        }
        const trimmed = typeof fileText === 'string' ? fileText.trim() : '';
        if (!trimmed) {
            return false;
        }
        return trimmed.startsWith('{') || trimmed.startsWith('[');
    }

    function getCurrentSourceConfigs() {
        const configs = app.registry?.models?.sourceConfigs;
        return Array.isArray(configs) ? configs : [];
    }

    function canonicalizeConfigs(configs) {
        if (!Array.isArray(configs)) {
            return '';
        }
        try {
            return configs
                .map(cfg => JSON.stringify(cfg ?? {}))
                .sort()
                .join('|');
        } catch (error) {
            console.warn('[Session] Unable to canonicalize source configs for comparison:', error);
            return '';
        }
    }

    function warnOnSourceMismatch(savedConfigs) {
        if (!Array.isArray(savedConfigs) || savedConfigs.length === 0) {
            return;
        }
        const currentKey = canonicalizeConfigs(getCurrentSourceConfigs());
        const savedKey = canonicalizeConfigs(savedConfigs);
        if (currentKey && savedKey && currentKey !== savedKey) {
            console.warn('[Session] Saved workspace references different source files than the ones currently loaded. Reload the matching data sources to ensure results are accurate before continuing.');
            showToast('This workspace was saved for different source files than the ones loaded. Regions may not line up with the data; reload the matching data sources.', 'warning', 8000);
        }
    }

    function buildWorkspacePayload(state) {
        return {
            version: SESSION_FILE_VERSION,
            savedAt: new Date().toISOString(),
            sourceConfigs: getCurrentSourceConfigs(),
            appState: state,
        };
    }

    function saveWorkspace() {
        if (!app.store || typeof app.store.getState !== 'function') {
            console.error('[Session] Store not available; cannot save workspace.');
            return;
        }
        const state = app.store.getState();
        const payload = buildWorkspacePayload(state);
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `workspace-${timestamp}.json`;
        const jsonText = JSON.stringify(payload, null, 2);
        triggerJsonDownload(filename, jsonText);
        // A named snapshot is a deliberate save: make sure the autosave copy is current too.
        if (autosaveScheduler && autosaveArmed) { autosaveScheduler.cancel(); flushAutosave(); }
    }

    function applyWorkspaceState(payload) {
        if (!payload || typeof payload !== 'object') {
            console.error('[Session] Invalid workspace payload.');
            showToast('Workspace file is not a valid workspace.', 'error', 6000);
            return false;
        }

        if (!app.store || typeof app.store.dispatch !== 'function') {
            console.error('[Session] Store not available; cannot apply workspace.');
            showToast('Cannot load workspace: the dashboard is not ready yet.', 'error', 6000);
            return false;
        }

        if (!app.actions || typeof app.actions.rehydrateState !== 'function') {
            console.error('[Session] Rehydrate action is not available.');
            showToast('Cannot load workspace: the dashboard is not ready yet.', 'error', 6000);
            return false;
        }

        let migrated;
        try {
            migrated = app.workspaceMigration.migrateWorkspace(payload);
        } catch (error) {
            showToast(error.message || 'Unable to load workspace.', 'error');
            return false;
        }
        const nextState = migrated.payload.appState;
        if (!nextState || typeof nextState !== 'object') {
            console.error('[Session] Workspace payload missing appState.');
            showToast('Workspace file has no appState to restore.', 'error', 6000);
            return false;
        }

        warnOnSourceMismatch(payload.sourceConfigs);
        app.store.dispatch(app.actions.rehydrateState(nextState));
        if (migrated.mergedCount) {
            showToast(`Merged ${migrated.mergedCount} legacy region copies across meters.`);
        }
        if (app.regions?.invalidateMetricsCache) {
            app.regions.invalidateMetricsCache();
        }
        // Pre-compute metrics for all regions so spectrum data is recalculated from actual data
        const utils = app.features?.regions?.utils;
        if (typeof utils?.getRegionMetrics === 'function') {
            const state = app.store.getState();
            const models = app.registry?.models;
            const dataCache = app.dataCache;
            const regionsState = state?.regions;
            if (regionsState?.allIds && regionsState?.byId) {
                regionsState.allIds.forEach(id => {
                    const region = regionsState.byId[id];
                    if (region) {
                        utils.getRegionMetrics(region, state, dataCache, models);
                    }
                });
            }
        }
        return true;
    }

    function loadWorkspace() {
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'application/json';
        fileInput.addEventListener('change', event => {
            const file = event.target?.files?.[0];
            if (!file) {
                return;
            }

            const reader = new FileReader();
            reader.onload = () => {
                try {
                    const payload = JSON.parse(reader.result);
                    const applied = applyWorkspaceState(payload);
                    if (applied) {
                        console.info('[Session] Workspace restored successfully.');
                    }
                } catch (error) {
                    console.error('[Session] Failed to parse workspace file:', error);
                    showToast(`Could not read workspace file: ${error?.message || error}`, 'error', 6000);
                }
            };
            reader.onerror = () => {
                console.error('[Session] Failed to read workspace file:', reader.error);
                showToast('Could not read the workspace file.', 'error', 6000);
            };
            reader.readAsText(file);
        });
        fileInput.click();
    }

    function getSessionActionSource() {
        return app.registry?.models?.sessionActionSource || null;
    }

    function getSessionStatusSource() {
        return app.registry?.models?.sessionStatusSource || null;
    }

    function getAutomationCommandSource() {
        return app.registry?.models?.automationCommandSource || null;
    }

    function getAutomationResultSource() {
        return app.registry?.models?.automationResultSource || null;
    }

    function scheduleAutomationBridgeRetry() {
        if (automationListenerAttached || automationAttachRetryTimer || automationAttachRetryCount >= AUTOMATION_ATTACH_MAX_RETRIES) {
            return;
        }
        automationAttachRetryCount += 1;
        automationAttachRetryTimer = window.setTimeout(() => {
            automationAttachRetryTimer = null;
            ensureAutomationBridge();
        }, AUTOMATION_ATTACH_RETRY_DELAY_MS);
    }

    function reportSessionStatus(sourceData) {
        if (!sourceData || typeof sourceData !== 'object') {
            return;
        }

        const updatedAt = Number(sourceData.updated_at?.[0]);
        if (Number.isFinite(updatedAt)) {
            if (updatedAt === lastSessionStatusUpdateAt) {
                return;
            }
            lastSessionStatusUpdateAt = updatedAt;
        }

        const level = typeof sourceData.level?.[0] === 'string' ? sourceData.level[0] : 'info';
        const done = Boolean(sourceData.done?.[0]);
        const message = typeof sourceData.message?.[0] === 'string' ? sourceData.message[0] : '';
        if (!message) {
            return;
        }

        const statusRequestId = sourceData.request_id?.[0];
        const statusTag = sourceData.output_path?.[0];
        if (handleAutosaveStatus(statusRequestId, level, message, statusTag)) {
            // Routine autosave results only update the small indicator; problems also toast.
            if (done) showToast(message, level, level === 'error' ? 5500 : 6000);
            return;
        }

        if (level === 'error') {
            console.error('[Session]', message);
        } else if (level === 'warning') {
            console.warn('[Session]', message);
        } else {
            console.info('[Session]', message);
        }

        if (done) {
            const duration = level === 'error' ? 5500 : 3800;
            showToast(message, level, duration);
        }
    }

    function ensureSessionStatusListener() {
        if (sessionStatusListenerAttached) {
            return;
        }
        const statusSource = getSessionStatusSource();
        if (!statusSource || !statusSource.change || typeof statusSource.change.connect !== 'function') {
            return;
        }

        statusSource.change.connect(() => {
            reportSessionStatus(statusSource.data);
        });
        sessionStatusListenerAttached = true;
    }

    function publishAutomationResult(requestId, success, message, data = null) {
        const resultSource = getAutomationResultSource();
        if (!resultSource) {
            return;
        }

        let serializedData = data;
        if (data !== null && data !== undefined) {
            try {
                serializedData = JSON.stringify(data);
            } catch (error) {
                serializedData = String(data);
            }
        }

        resultSource.data = {
            request_id: [requestId || null],
            success: [Boolean(success)],
            message: [typeof message === 'string' ? message : String(message || '')],
            data: [serializedData ?? null],
            updated_at: [Date.now()]
        };
        if (resultSource.change && typeof resultSource.change.emit === 'function') {
            resultSource.change.emit();
        }
    }

    // Automation commands sent by the Python control bridge (control/session_bridge.py).
    // Each handler is `(payload, { dispatch, getState }) => ({ success?, message?, data? })` and may
    // throw; a throw (or `success: false`) is reported back as a failed result. Add commands from
    // other files with `app.session.registerAutomationCommand(name, handler)`.
    const automationCommands = new Map();

    function registerAutomationCommand(name, handler) {
        if (typeof name !== 'string' || !name || typeof handler !== 'function') {
            throw new Error('registerAutomationCommand requires a command name and a handler function.');
        }
        automationCommands.set(name, handler);
    }

    registerAutomationCommand('set_parameter', (payload) => {
        const value = typeof payload?.value === 'string' ? payload.value : null;
        if (!value) {
            throw new Error('set_parameter requires a value.');
        }
        const handler = app.services?.eventHandlers?.view?.handleParameterChange;
        if (typeof handler !== 'function') {
            throw new Error('Parameter change handler is unavailable.');
        }
        handler(value);
        return { success: true, message: `Parameter updated to ${value}.` };
    });

    registerAutomationCommand('set_view_mode', (payload) => {
        const value = typeof payload?.value === 'string' ? payload.value : null;
        if (value !== 'log' && value !== 'overview') {
            throw new Error("set_view_mode requires 'log' or 'overview'.");
        }
        const handler = app.services?.eventHandlers?.view?.handleViewToggle;
        if (typeof handler !== 'function') {
            throw new Error('View toggle handler is unavailable.');
        }
        handler(value === 'log');
        return { success: true, message: `View mode updated to ${value}.` };
    });

    registerAutomationCommand('export_annotations', (payload) => {
        if (!handleExportFullResolution(payload || {})) throw new Error('Full-resolution export could not be started.');
        return { success: true, message: 'Full-resolution annotation export started.' };
    });

    registerAutomationCommand('apply_workspace', (payload) => {
        const workspacePayload = payload?.payload;
        if (!workspacePayload || typeof workspacePayload !== 'object') {
            throw new Error('apply_workspace requires a workspace payload.');
        }
        const applied = applyWorkspaceState(workspacePayload);
        if (!applied) {
            throw new Error('Workspace payload could not be applied.');
        }
        return { success: true, message: 'Workspace applied.' };
    });

    function executeAutomationCommand(command, payload) {
        const handler = automationCommands.get(command);
        if (typeof handler !== 'function') {
            throw new Error(`Unsupported automation command '${command}'.`);
        }
        const context = {
            dispatch: (...args) => app.store.dispatch(...args),
            getState: () => app.store.getState()
        };
        return handler(payload, context) || {};
    }

    function handleAutomationCommand(sourceData) {
        const requestId = typeof sourceData?.request_id?.[0] === 'string'
            ? sourceData.request_id[0]
            : '';
        if (!requestId || requestId === lastAutomationRequestId) {
            return;
        }
        lastAutomationRequestId = requestId;

        const command = typeof sourceData?.command?.[0] === 'string'
            ? sourceData.command[0]
            : '';
        try {
            const rawPayload = sourceData?.payload?.[0];
            let payload = {};
            if (typeof rawPayload === 'string' && rawPayload) {
                payload = JSON.parse(rawPayload);
            } else if (rawPayload && typeof rawPayload === 'object') {
                payload = rawPayload;
            }
            const result = executeAutomationCommand(command, payload);
            publishAutomationResult(requestId, result?.success !== false, result?.message || 'OK', result?.data ?? null);
        } catch (error) {
            console.error('[Session] Automation command failed:', error);
            publishAutomationResult(requestId, false, error?.message || String(error));
        }
    }

    function ensureAutomationBridge() {
        if (automationListenerAttached) {
            return true;
        }
        const commandSource = getAutomationCommandSource();
        if (!commandSource || !commandSource.change || typeof commandSource.change.connect !== 'function') {
            scheduleAutomationBridgeRetry();
            return false;
        }

        if (automationAttachRetryTimer) {
            window.clearTimeout(automationAttachRetryTimer);
            automationAttachRetryTimer = null;
        }
        automationAttachRetryCount = 0;

        commandSource.change.connect(() => {
            handleAutomationCommand(commandSource.data);
        });
        automationListenerAttached = true;
        handleAutomationCommand(commandSource.data);
        return true;
    }

    function triggerServerSessionAction(command, payload) {
        const actionSource = getSessionActionSource();
        if (!actionSource || !actionSource.data) {
            return false;
        }

        const requestId = `${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
        lastTriggeredRequestId = requestId;
        // Assign `data` as a whole rather than mutating its columns in place.
        // Bokeh only emits a document patch when the property itself is set, so
        // an in-place mutation plus change.emit() notifies BokehJS listeners but
        // never reaches the server, and the Python on_change handler never runs.
        actionSource.data = {
            command: [command],
            request_id: [requestId],
            payload: [payload ?? null],
        };
        return true;
    }

    function handleGenerateStaticHtml() {
        if (window.location?.protocol === 'file:') {
            showToast('Static HTML generation is only available in live server mode.', 'warning', 4500);
            return;
        }

        ensureSessionStatusListener();
        // Send what is on screen so the file carries current annotations, layout and offsets.
        const currentState = app.store?.getState?.();
        const sent = triggerServerSessionAction('generate_static_html', {
            workspace: currentState ? buildWorkspacePayload(selectPersistableState(currentState)) : null
        });
        if (!sent) {
            showToast('Static HTML export is unavailable in this session.', 'error', 5000);
            console.error('[Session] Session action source is unavailable.');
            return;
        }
        showToast('Static HTML export started. You can keep using the dashboard.', 'info', 3000);
        console.info('[Session] Static HTML export requested.');
    }

    function handleExportFullResolution(options = {}) {
        if (window.location?.protocol === 'file:') {
            showToast('Full-resolution export is only available in live server mode.', 'warning');
            return false;
        }
        const state = app.store?.getState?.();
        if (!state) return false;
        ensureSessionStatusListener();
        const sent = triggerServerSessionAction('export_annotations', {
            workspace: buildWorkspacePayload(state),
            output_path: options.output_path,
            include_proposed: Boolean(options.include_proposed ?? options.includeProposed ?? false),
            include_all_resolutions: Boolean(options.include_all_resolutions ?? options.includeAllResolutions ?? state.annotationPanel?.includeAllResolutions),
            background_window_s: options.background_window_s ?? state.annotationPanel?.backgroundWindowS ?? 300,
            min_context_s: options.min_context_s ?? state.annotationPanel?.minContextS ?? 60
        });
        if (sent) showToast('Full-resolution annotation export started. You can keep using the dashboard.');
        else showToast('Full-resolution export is unavailable in this session.', 'error');
        return sent;
    }

    function handleSaveSetupToConfig() {
        if (window.location?.protocol === 'file:') {
            showToast('Saving to config is only available in live server mode.', 'warning', 4500);
            return;
        }

        ensureSessionStatusListener();
        const sent = triggerServerSessionAction('save_setup_to_config', null);
        if (!sent) {
            showToast('Saving to config is unavailable in this session.', 'error', 5000);
            console.error('[Session] Session action source is unavailable.');
            return;
        }
        console.info('[Session] Save setup to config requested.');
    }

    function handleMenuAction(action) {
        switch (action) {
            case 'save_setup_to_config':
                handleSaveSetupToConfig();
                break;
            case 'save':
                saveWorkspace();
                break;
            case 'load':
                loadWorkspace();
                break;
            case 'export_annotations_full_resolution':
                handleExportFullResolution();
                break;
            case 'export_annotations_csv':
            case 'export_regions':
                handleExportCsv({ mode: 'annotations' });
                break;
            case 'export_annotations_analysis_csv':
                handleExportCsv({ mode: 'full' });
                break;
            case 'import_annotations_csv':
            case 'import_regions':
                handleImportCsv();
                break;
            case 'export_classifications_csv':
                handleExportClassifications();
                break;
            case 'import_classifications':
            case 'import_classifications_csv':
                handleImportClassifications();
                break;
            case 'generate_static_html':
                handleGenerateStaticHtml();
                break;
            default:
                console.warn('[Session] Unhandled session menu action:', action);
        }
    }

    function handleExportCsv(options = {}) {
        if (!app.store || typeof app.store.getState !== 'function') {
            console.error('[Session] Store not available; cannot export annotations.');
            return;
        }

        const state = app.store.getState();
        const selectAllRegions = app.features?.regions?.selectors?.selectAllRegions;
        const selectAllMarkers = app.features?.markers?.selectors?.selectAllMarkers;

        if (typeof selectAllRegions !== 'function' || typeof selectAllMarkers !== 'function') {
            console.error('[Session] Annotation selectors are not available.');
            return;
        }

        const regions = selectAllRegions(state) || [];
        const markers = selectAllMarkers(state) || [];
        const csvText = buildAnnotationsCsv(markers, regions, state, options);
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const prefix = options.mode === 'full' ? 'annotations-analysis' : 'annotations';
        const filename = `${prefix}-${timestamp}.csv`;
        triggerCsvDownload(filename, csvText);
    }

    function handleExportClassifications() {
        if (!app.store || typeof app.store.getState !== 'function') {
            console.error('[Session] Store not available; cannot export classifications.');
            return;
        }
        const selectAllClassifications = app.features?.classifications?.selectors?.selectAllClassifications;
        const buildClassificationsCsv = app.features?.classifications?.utils?.buildClassificationsCsv;
        if (typeof selectAllClassifications !== 'function' || typeof buildClassificationsCsv !== 'function') {
            console.error('[Session] Classification export helpers are unavailable.');
            return;
        }
        const classifications = selectAllClassifications(app.store.getState());
        const csvText = buildClassificationsCsv(classifications);
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        triggerCsvDownload(`classifications-${timestamp}.csv`, csvText);
    }

    function importClassificationEntries(entries) {
        if (!Array.isArray(entries) || !entries.length) {
            throw new Error('No classifier intervals found in file.');
        }
        if (!app.actions?.classificationsAdded || !app.actions?.classificationsReplaceAll
            || typeof app.store?.dispatch !== 'function') {
            throw new Error('Classification store actions are unavailable.');
        }
        const existing = app.store.getState()?.classifications || {};
        const existingIds = Array.isArray(existing.allIds) ? existing.allIds : [];

        // One CSV is imported per target sound, so the default is to ADD to what
        // is already loaded. Replacing needs an explicit choice.
        let replace = false;
        if (existingIds.length && typeof window.confirm === 'function') {
            const addToExisting = window.confirm(
                `${existingIds.length} classifier interval(s) are already loaded.\n\n`
                + 'OK = add the imported intervals to the existing ones.\n'
                + 'Cancel = replace all existing intervals with the imported ones.'
            );
            replace = !addToExisting;
        }

        if (replace) {
            app.store.dispatch(app.actions.classificationsReplaceAll(entries));
            const count = app.store.getState()?.classifications?.allIds?.length || 0;
            if (!count) {
                throw new Error('No valid classifier intervals were imported.');
            }
            return { added: count, skipped: 0, total: count, replaced: true };
        }

        // Mirrors the reducer's normalisation (source id defaults to 'source').
        const keyOf = entry => [
            entry?.positionId ?? entry?.position_id ?? entry?.position ?? '',
            String(entry?.sourceId ?? entry?.source_id ?? entry?.source ?? '').trim() || 'source',
            Math.min(Number(entry?.start ?? entry?.startMs ?? entry?.start_ms),
                Number(entry?.end ?? entry?.endMs ?? entry?.end_ms)),
        ].map(part => String(part).trim()).join('|');
        const seen = new Set(existingIds.map(id => keyOf(existing.byId?.[id])));
        const fresh = [];
        entries.forEach(entry => {
            const key = keyOf(entry);
            if (seen.has(key)) return;
            seen.add(key);
            fresh.push(entry);
        });
        const skipped = entries.length - fresh.length;
        if (!fresh.length) {
            if (!existingIds.length) {
                throw new Error('No valid classifier intervals were imported.');
            }
            return { added: 0, skipped, total: existingIds.length, replaced: false };
        }

        const previousSelectedId = existing.selectedId ?? null;
        app.store.dispatch(app.actions.classificationsAdded(fresh));
        const after = app.store.getState()?.classifications || {};
        const total = Array.isArray(after.allIds) ? after.allIds.length : 0;
        const added = total - existingIds.length;
        if (added <= 0 && !existingIds.length) {
            throw new Error('No valid classifier intervals were imported.');
        }
        // The reducer selects the last imported row; keep the user's selection.
        if (previousSelectedId !== null && typeof app.actions.classificationSelect === 'function') {
            app.store.dispatch(app.actions.classificationSelect(previousSelectedId));
        }
        return { added: Math.max(added, 0), skipped, total, replaced: false };
    }

    function handleImportClassifications() {
        if (!app.store || typeof app.store.dispatch !== 'function') {
            console.error('[Session] Store not available; cannot import classifications.');
            return;
        }

        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = '.csv,text/csv,application/json,.json';
        fileInput.addEventListener('change', event => {
            const file = event.target?.files?.[0];
            if (!file) {
                return;
            }

            const reader = new FileReader();
            reader.onload = () => {
                const fileText = typeof reader.result === 'string' ? reader.result : '';
                const utils = app.features?.classifications?.utils || {};
                try {
                    const treatAsJson = shouldTreatContentAsJson(file.name, fileText);
                    const entries = treatAsJson
                        ? (typeof utils.parseClassificationsJson === 'function' ? utils.parseClassificationsJson(fileText) : [])
                        : (typeof utils.parseClassificationsCsv === 'function' ? utils.parseClassificationsCsv(fileText) : []);
                    const outcome = importClassificationEntries(entries);
                    const message = outcome.replaced
                        ? `Replaced classifications with ${outcome.added} interval(s).`
                        : `Added ${outcome.added} classifier interval(s)`
                            + (outcome.skipped ? ` (${outcome.skipped} duplicate(s) skipped)` : '')
                            + `; ${outcome.total} total.`;
                    console.info(`[Session] ${message}`);
                    showToast(message, 'info', 3500);
                } catch (error) {
                    console.error('[Session] Failed to import classifications:', error);
                    showToast(error?.message || 'Failed to import classifications.', 'error', 5000);
                }
            };
            reader.onerror = () => {
                console.error('[Session] Failed to read classification file:', reader.error);
            };
            reader.readAsText(file);
            event.target.value = '';
        });
        fileInput.click();
    }

    function handleImportCsv() {
        if (!app.store || typeof app.store.dispatch !== 'function') {
            console.error('[Session] Store not available; cannot import annotations.');
            return;
        }

        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = '.csv,text/csv,application/json,.json';
        fileInput.addEventListener('change', event => {
            const file = event.target?.files?.[0];
            if (!file) {
                return;
            }

            const reader = new FileReader();
            reader.onload = () => {
                const fileText = typeof reader.result === 'string' ? reader.result : '';
                const treatAsJson = shouldTreatContentAsJson(file.name, fileText);
                try {
                    if (treatAsJson) {
                        importAnnotationsFromJson(fileText);
                        console.info('[Session] Annotation JSON import complete.');
                        return;
                    }

                    const { markers, regions, mergedCount, categories, metadata } = parseAnnotationsCsv(fileText);
                    if (categories && app.actions?.regionCategoryCatalogSet) app.store.dispatch(app.actions.regionCategoryCatalogSet(categories));
                    if (metadata?.meters && app.actions?.positionDisplayTitlesSet) {
                        app.store.dispatch(app.actions.positionDisplayTitlesSet(Object.fromEntries(metadata.meters.map(meter => [meter.id, meter.title]))));
                    }
                    Object.entries(metadata?.chart_offsets_ms || {}).forEach(([meter, offset]) => {
                        if (app.store.getState()?.view?.availablePositions?.includes(meter) && Number.isFinite(Number(offset))) {
                            app.store.dispatch(app.actions.positionChartOffsetSet(meter, Number(offset)));
                        }
                    });
                    if (mergedCount) showToast(`Merged ${mergedCount} legacy region copies across meters.`);
                    if (Array.isArray(markers)) {
                        if (typeof app.actions?.markersReplace === 'function') {
                            app.store.dispatch(app.actions.markersReplace(markers));
                        } else {
                            console.error('[Session] Marker replace action is unavailable.');
                        }
                    }
                    if (Array.isArray(regions)) {
                        if (typeof app.actions?.regionReplaceAll === 'function') {
                            app.store.dispatch(app.actions.regionReplaceAll(regions));
                            if (typeof app.regions?.invalidateMetricsCache === 'function') {
                                app.regions.invalidateMetricsCache();
                            }
                        } else {
                            console.error('[Session] Region replace action is unavailable.');
                        }
                    }
                    console.info('[Session] Annotation CSV import complete.');
                } catch (error) {
                    console.error('[Session] Failed to import annotations:', error);
                }
            };
            reader.onerror = () => {
                console.error('[Session] Failed to read annotation file:', reader.error);
            };
            reader.readAsText(file);
            event.target.value = '';
        });
        fileInput.click();
    }

    // ------------------------------------------------------------------------------------------
    // Autosave (live: server writes <config>.workspace.json; static: browser localStorage)
    // ------------------------------------------------------------------------------------------
    const AUTOSAVE_DELAY_MS = 2000;
    const AUTOSAVE_MAX_WAIT_MS = 15000;
    const STATIC_STORAGE_PREFIX = 'nsa.static.workspace.v1.';
    const TRANSIENT_VIEW_KEYS = ['regionJumpHistory', 'lastRegionJumpViewport', 'regionNoteFocusRequestId',
        'regionNoteStatus', 'notice'];
    const TRANSIENT_REGION_KEYS = ['addAreaTargetId', 'isMergeModeActive', 'metricsRevision'];

    let autosaveStarted = false;
    let autosaveRev = 0;
    let autosaveSessionId = null;
    let autosaveScheduler = null;
    let autosaveIndicator = null;
    let autosaveLastRefs = null;
    let autosaveArmed = false;
    let staticBaseSignature = 'none';
    const pendingAutosaveRequests = new Set();

    function isStaticDocument() {
        // Only the exporter marks a page static. A live page whose session-action source attaches
        // late must still save to the server, not to localStorage.
        return app.registry?.models?.config?.static_document === true;
    }

    /** Content hash the static exporter bakes into the page (<meta name="nsa-export-id">), or ''. */
    function staticExportId() {
        try {
            return document.querySelector('meta[name="nsa-export-id"]')?.getAttribute('content') || '';
        } catch (error) {
            return '';
        }
    }

    /** The slices worth keeping: no hover/tap, audio transport, undo history or one-shot UI signals. */
    function selectPersistableState(state) {
        if (!state || typeof state !== 'object') return {};
        const omit = (source, keys) => {
            const copy = { ...(source || {}) };
            keys.forEach(key => { delete copy[key]; });
            return copy;
        };
        const persisted = {
            view: omit(state.view, TRANSIENT_VIEW_KEYS),
            markers: state.markers,
            classifications: state.classifications,
            regions: omit(state.regions, TRANSIENT_REGION_KEYS),
            layout: state.layout,
        };
        if (state.annotationPanel) persisted.annotationPanel = omit(state.annotationPanel, ['clearMarkersPending']);
        Object.keys(persisted).forEach(key => { if (persisted[key] === undefined) delete persisted[key]; });
        return persisted;
    }

    /** References whose change means "something worth saving happened". */
    function autosaveWatchedRefs(state) {
        const s = state || {};
        return [s.regions?.byId, s.regions?.allIds, s.regions?.categories, s.markers?.byId, s.markers?.allIds,
            s.layout, s.view?.positionChartOffsets, s.view?.positionAudioOffsets, s.view?.positionDisplayTitles,
            s.classifications?.byId];
    }

    function refsDiffer(a, b) {
        if (!a || !b || a.length !== b.length) return true;
        for (let i = 0; i < a.length; i += 1) if (a[i] !== b[i]) return true;
        return false;
    }

    /** Debounce with a maximum wait: `notify()` on every change; `flush` runs 2 s after the last one
     *  and never more than 15 s after the first unsaved one. Timers are injectable for tests. */
    function createAutosaveScheduler(options) {
        const delayMs = options.delayMs ?? AUTOSAVE_DELAY_MS;
        const maxWaitMs = options.maxWaitMs ?? AUTOSAVE_MAX_WAIT_MS;
        const setTimer = options.setTimer || ((fn, ms) => window.setTimeout(fn, ms));
        const clearTimer = options.clearTimer || (id => window.clearTimeout(id));
        const now = options.now || (() => Date.now());
        let timer = null;
        let firstPendingAt = null;
        function run() {
            if (timer !== null) clearTimer(timer);
            timer = null;
            firstPendingAt = null;
            options.flush();
        }
        return {
            notify() {
                const t = now();
                if (firstPendingAt === null) firstPendingAt = t;
                if (timer !== null) clearTimer(timer);
                timer = setTimer(run, Math.max(0, Math.min(delayMs, firstPendingAt + maxWaitMs - t)));
            },
            flushNow() { if (firstPendingAt !== null) run(); },
            cancel() { if (timer !== null) clearTimer(timer); timer = null; firstPendingAt = null; },
            get pending() { return firstPendingAt !== null; },
        };
    }

    function ensureAutosaveIndicator() {
        if (autosaveIndicator && document.body?.contains(autosaveIndicator)) return autosaveIndicator;
        if (!document?.body) return null;
        const el = document.createElement('div');
        el.id = 'nsa-autosave-indicator';
        el.style.cssText = 'position:fixed;right:10px;bottom:6px;z-index:9000;font:11px/1.2 sans-serif;'
            + 'color:#475467;background:rgba(255,255,255,0.8);padding:2px 6px;border-radius:4px;'
            + 'pointer-events:none;opacity:0.75;';
        document.body.appendChild(el);
        autosaveIndicator = el;
        return el;
    }

    function setAutosaveIndicator(text, tone) {
        const el = ensureAutosaveIndicator();
        if (!el) return;
        el.textContent = text;
        el.style.color = tone === 'error' ? '#b42318' : (tone === 'warning' ? '#b54708' : '#475467');
    }

    function clockText(iso) {
        const date = iso ? new Date(iso) : new Date();
        const valid = Number.isFinite(date.getTime()) ? date : new Date();
        return `${String(valid.getHours()).padStart(2, '0')}:${String(valid.getMinutes()).padStart(2, '0')}`;
    }

    function staticStorageKey() {
        const job = app.registry?.models?.jobNumber;
        // Keyed on the export too, so edits made on an older export never shadow a newer one.
        const exportId = staticExportId();
        return STATIC_STORAGE_PREFIX + (job || (window.location?.pathname || 'page')) + (exportId ? `:${exportId}` : '');
    }

    function stateSignature(appState) {
        const regions = appState?.regions || {};
        const markers = appState?.markers || {};
        return `${Object.keys(regions.byId || {}).length}:${Object.keys(markers.byId || {}).length}:`
            + `${regions.counter ?? 0}:${markers.counter ?? 0}`;
    }

    function readStaticLocalState() {
        try {
            const raw = window.localStorage.getItem(staticStorageKey());
            if (!raw) return null;
            const stored = JSON.parse(raw);
            // Edits made on top of a different exported snapshot would shadow a newer export.
            if (stored && stored.baseSignature === staticBaseSignature && stored.appState) return stored.appState;
        } catch (error) { /* storage blocked or corrupt: ignore */ }
        return null;
    }

    function writeStaticLocalState(appState) {
        try {
            window.localStorage.setItem(staticStorageKey(), JSON.stringify({
                baseSignature: staticBaseSignature, savedAt: new Date().toISOString(), appState }));
            return true;
        } catch (error) {
            return false;
        }
    }

    /** " | Log 5 s" when the exporter averaged the 1 s spectrogram to keep the file small. */
    function staticStepNote() {
        const step = Number(app.registry?.models?.config?.static_log_step_s);
        return Number.isFinite(step) && step > 0 ? ` | Spectrogram: Log ${step} s` : '';
    }

    function flushAutosave(options) {
        if (!app.store?.getState) return false;
        const persistable = selectPersistableState(app.store.getState());
        if (isStaticDocument()) {
            const ok = writeStaticLocalState(persistable);
            setAutosaveIndicator(ok ? `Saved in this browser ${clockText()}${staticStepNote()}` : 'Browser storage unavailable',
                ok ? 'info' : 'warning');
            return ok;
        }
        autosaveRev += 1;
        const payload = { ...buildWorkspacePayload(persistable), sessionId: autosaveSessionId, rev: autosaveRev };
        // The pagehide flush is this tab's last word: a tab opened by a reload may adopt it.
        if (options && options.final === true) payload.final = true;
        const sent = triggerServerSessionAction('autosave_workspace', payload);
        if (sent) {
            pendingAutosaveRequests.add(lastTriggeredRequestId);
            setAutosaveIndicator('Saving...', 'info');
        }
        return sent;
    }

    /** Called from the session status listener. Returns true when the status was an autosave one. */
    function handleAutosaveStatus(requestId, level, message, tag) {
        if (typeof tag !== 'string' || !tag.startsWith('autosave:')) return false;
        pendingAutosaveRequests.delete(requestId);
        const parts = tag.split(':');
        const status = parts[1];
        const savedAt = parts.slice(3).join(':');
        if (status === 'ok') setAutosaveIndicator(`Saved ${clockText(savedAt)}`, 'info');
        else if (status === 'unavailable') setAutosaveIndicator('Autosave off (no config)', 'warning');
        else if (status === 'conflict') setAutosaveIndicator('Not saved: newer copy open elsewhere', 'warning');
        else setAutosaveIndicator('Autosave failed', 'error');
        return true;
    }

    const LAYOUT_REF_INDEX = 5;  // position of `layout` in autosaveWatchedRefs
    const AUTOSAVE_SETTLE_MS = 3000;

    /** True when the change between two watched-ref snapshots came from the user. Init/rehydration
     *  never counts; a layout-only change counts only for a layout action after the page has settled. */
    function isUserAutosaveChange(previousRefs, nextRefs, actionType, sinceStartMs) {
        // The startup restore runs before autosave starts, so a rehydration seen here is a deliberate
        // "Load workspace" / apply_workspace and counts as a user change.
        const { INITIALIZE_STATE } = app.actionTypes || {};
        if (actionType === '@@INIT' || actionType === INITIALIZE_STATE) return false;
        const annotationChanged = nextRefs.some((ref, i) => i !== LAYOUT_REF_INDEX && ref !== previousRefs[i]);
        if (annotationChanged) return true;
        return typeof actionType === 'string' && actionType.startsWith('layout/') && sinceStartMs > AUTOSAVE_SETTLE_MS;
    }

    function startAutosave() {
        if (autosaveStarted || !app.store?.subscribe) return false;
        autosaveStarted = true;
        autosaveSessionId = `${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 10)}`;
        autosaveLastRefs = autosaveWatchedRefs(app.store.getState());
        autosaveScheduler = createAutosaveScheduler({ flush: flushAutosave });
        const startedAt = Date.now();
        app.store.subscribe(() => {
            const state = app.store.getState();
            const refs = autosaveWatchedRefs(state);
            if (!refsDiffer(refs, autosaveLastRefs)) return;
            const previous = autosaveLastRefs;
            autosaveLastRefs = refs;
            // Nothing is written until the user has changed something: init, rehydration and layout
            // set-up after load must never replace a good autosave with a blank or default state.
            if (!autosaveArmed) {
                if (!isUserAutosaveChange(previous, refs, state.system?.lastAction?.type, Date.now() - startedAt)) return;
                autosaveArmed = true;
            }
            autosaveScheduler.notify();
        });
        const flushNow = () => autosaveScheduler.flushNow();
        window.addEventListener('pagehide', () => {
            if (autosaveScheduler.pending) { autosaveScheduler.cancel(); flushAutosave({ final: true }); }
        });
        document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'hidden') flushNow(); });
        if (app.keymap?.registerKeyBindings) {
            app.keymap.registerKeyBindings([{
                id: 'saveWorkspaceNow', keys: ['s'], ctrl: true, alt: false, shift: false, intent: 'saveWorkspaceNow',
                group: 'Edit', label: 'Ctrl+S', description: 'Save annotations now (autosave also runs by itself)',
                run: () => { autosaveScheduler.cancel(); flushAutosave(); }
            }]);
        }
        setAutosaveIndicator(isStaticDocument() ? `Edits kept in this browser${staticStepNote()}` : 'Autosave on', 'info');
        return true;
    }

    // Quantised static spectra (see visualization/static_payload.py) are decoded before first render.
    function decodeQuantizedLevels(codes, offset, step) {
        const integral = Number.isInteger(offset) && Number.isInteger(step);
        const out = integral ? new Int16Array(codes.length) : new Float32Array(codes.length);
        for (let i = 0; i < codes.length; i += 1) out[i] = codes[i] * step + offset;
        return out;
    }

    function isCodeArray(value) {
        return value && ArrayBuffer.isView(value) && value.BYTES_PER_ELEMENT === 1;
    }

    function decodeStaticPayload(models) {
        const spectrogramSources = models?.spectrogramSources || {};
        Object.keys(spectrogramSources).forEach(position => {
            const data = spectrogramSources[position]?.log?.data;
            const column = data?.levels_flat_transposed;
            if (!data?.quant_step_db || !column || !isCodeArray(column[0])) return;
            column[0] = decodeQuantizedLevels(column[0], Number(data.quant_offset_db?.[0]) || 0, Number(data.quant_step_db[0]) || 1);
        });
        const prepared = models?.preparedGlyphData || {};
        Object.keys(prepared).forEach(position => {
            const params = prepared[position]?.log?.prepared_params || {};
            Object.keys(params).forEach(param => {
                const entry = params[param];
                if (!entry || typeof entry !== 'object') return;
                if (entry.shared_with_log_source) {
                    const data = spectrogramSources[position]?.log?.data;
                    if (data?.parameter?.[0] === param) {
                        entry.levels_flat_transposed = data.levels_flat_transposed?.[0];
                        entry.times_ms = data.times_ms?.[0];
                    }
                } else if (entry.quant_step_db != null && isCodeArray(entry.levels_flat_transposed)) {
                    const codes = entry.levels_flat_transposed;
                    const offset = Number(entry.quant_offset_db) || 0;
                    const step = Number(entry.quant_step_db) || 1;
                    let decoded = null;
                    // Decode on first use: only the parameters actually viewed cost memory.
                    Object.defineProperty(entry, 'levels_flat_transposed', {
                        configurable: true, enumerable: true,
                        get() { if (!decoded) decoded = decodeQuantizedLevels(codes, offset, step); return decoded; },
                        set(value) { decoded = value; },
                    });
                }
            });
        });
        return models;
    }

    function applyInitialWorkspaceState() {
        try {
            return applyInitialWorkspaceStateInner();
        } finally {
            // Autosave starts only after the saved state is restored, so the restore itself is the
            // baseline and an empty fresh state is never written over a good autosave.
            try { startAutosave(); } catch (error) { console.error('[Session] Autosave could not start:', error); }
        }
    }

    function applyInitialWorkspaceStateInner() {
        ensureSessionStatusListener();
        if (initialStateApplied) {
            return false;
        }
        let savedState = app.registry?.models?.savedWorkspaceState;
        if (isStaticDocument()) {
            staticBaseSignature = stateSignature(savedState);
            const local = readStaticLocalState();
            if (local) savedState = local;
        }
        if (!savedState || typeof savedState !== 'object') {
            return false;
        }
        const applied = applyWorkspaceState({
            version: SESSION_FILE_VERSION,
            appState: savedState,
            sourceConfigs: getCurrentSourceConfigs(),
        });
        if (applied) {
            initialStateApplied = true;
            app.registry.models.savedWorkspaceState = null;
        }
        return applied;
    }

    const testHelpers = {
        formatTimestampForCsv,
        parseTimestampFromCsv,
        buildAnnotationsCsv,
        parseAnnotationsCsv,
        CSV_HEADER: CSV_HEADER.slice(),
        METRIC_COLUMNS: METRIC_COLUMNS.slice(),
        PROVENANCE_COLUMNS: PROVENANCE_COLUMNS.slice(),
        importClassificationEntries,
        selectPersistableState,
        createAutosaveScheduler,
        autosaveWatchedRefs,
        isUserAutosaveChange,
        decodeQuantizedLevels,
        handleAutosaveStatus,
        flushAutosave,
        startAutosave
    };

    app.session = {
        saveWorkspace,
        loadWorkspace,
        handleMenuAction,
        applyWorkspaceState,
        applyInitialWorkspaceState,
        selectPersistableState,
        decodeStaticPayload,
        flushAutosave,
        handleExportCsv,
        handleExportFullResolution,
        handleImportCsv,
        handleExportClassifications,
        handleImportClassifications,
        handleGenerateStaticHtml,
        handleImportAnnotations: handleImportCsv,
        ensureSessionStatusListener,
        ensureAutomationBridge,
        registerAutomationCommand,
        showToast,
        __testHelpers: testHelpers,
    };
})(window.NoiseSurveyApp);
