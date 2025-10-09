// noise_survey_analysis/static/js/services/session/sessionManager.js

/**
 * @fileoverview Manages workspace save/load actions and bridges them to the
 *               Redux-style store. Exposes a small API on `NoiseSurveyApp.session`
 *               that is used by the Bokeh toolbar dropdown.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const SESSION_FILE_VERSION = 1;
    let initialStateApplied = false;

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
        const markers = Array.isArray(markersInput) ? markersInput : [];
        const regions = Array.isArray(regionsInput) ? regionsInput : [];
        const resolvedState = state || null;
        const dataCache = options?.dataCache ?? app.dataCache;
        const models = options?.models ?? app.registry?.models;
        const bandColumns = collectBandColumns(markers, regions, resolvedState, dataCache, models);
        const bandLookup = new Map(bandColumns.map(entry => [entry.key, entry.column]));
        const header = CSV_HEADER.concat(METRIC_COLUMNS, bandColumns.map(entry => entry.column));

        const rows = [header.join(',')];

        function createBaseRow() {
            const rowData = {};
            header.forEach(column => {
                rowData[column] = '';
            });
            return rowData;
        }

        markers.forEach(marker => {
            const formattedStart = formatTimestampForCsv(marker?.timestamp);
            if (!formattedStart) {
                return;
            }

            const rowData = createBaseRow();
            rowData.type = 'marker';
            rowData.id = Number.isFinite(Number(marker?.id)) ? Number(marker.id) : '';
            rowData.positionId = marker?.positionId ?? '';
            rowData.start_utc = formattedStart;
            rowData.timestamp_utc = formattedStart;
            rowData.note = typeof marker?.note === 'string' ? marker.note : '';
            rowData.color = typeof marker?.color === 'string' ? marker.color : '';

            const metrics = marker?.metrics || null;
            if (metrics) {
                rowData.metrics_parameter = metrics.parameter ?? '';
                rowData.metrics_timestamp_utc = formatTimestampForCsv(metrics.timestamp);
                const broadband = extractMarkerBroadband(marker);
                if (broadband && Number.isFinite(broadband.value)) {
                    rowData.metrics_broadband_value = formatNumberValue(broadband.value);
                    rowData.metrics_broadband_position = broadband.positionId || '';
                }
                const spectrum = extractMarkerSpectrum(marker);
                assignSpectrumValues(rowData, spectrum, bandLookup);
            }

            const row = header.map(column => escapeCsvValue(rowData[column]));
            rows.push(row.join(','));
        });

        regions.forEach(region => {
            const formattedStart = formatTimestampForCsv(region?.start);
            const formattedEnd = formatTimestampForCsv(region?.end);
            if (!formattedStart || !formattedEnd) {
                return;
            }

            const rowData = createBaseRow();
            rowData.type = 'region';
            rowData.id = Number.isFinite(Number(region?.id)) ? Number(region.id) : '';
            rowData.positionId = typeof region?.positionId === 'string' ? region.positionId : '';
            rowData.start_utc = formattedStart;
            rowData.end_utc = formattedEnd;
            rowData.note = typeof region?.note === 'string' ? region.note : '';
            rowData.color = typeof region?.color === 'string' ? region.color : '';

            const regionAreas = Array.isArray(region?.areas) ? region.areas : [];
            const serializedAreas = regionAreas
                .map(area => {
                    const areaStart = formatTimestampForCsv(area?.start);
                    const areaEnd = formatTimestampForCsv(area?.end);
                    if (!areaStart || !areaEnd) {
                        return null;
                    }
                    return { startUtc: areaStart, endUtc: areaEnd };
                })
                .filter(Boolean);
            const areasValue = serializedAreas.length
                ? JSON.stringify(serializedAreas)
                : JSON.stringify([{ startUtc: formattedStart, endUtc: formattedEnd }]);
            rowData.areas = areasValue;

            const metrics = resolveRegionMetrics(region, resolvedState, dataCache, models);
            if (metrics) {
                rowData.metrics_parameter = metrics.parameter ?? '';
                rowData.metrics_data_resolution = metrics.dataResolution ?? '';
                rowData.metrics_duration_ms = formatNumberValue(metrics.durationMs, 0);
                rowData.duration_ms = formatNumberValue(metrics.durationMs, 0);
                rowData.metrics_laeq = formatNumberValue(metrics.laeq);
                rowData.metrics_lafmax = formatNumberValue(metrics.lafmax);
                rowData.metrics_la90 = formatNumberValue(metrics.la90);
                rowData.metrics_la90_available = metrics.la90Available ? 'true' : '';
                const spectrum = extractRegionSpectrum(region, resolvedState, dataCache, models);
                assignSpectrumValues(rowData, spectrum, bandLookup);
                if (metrics.spectrum && typeof metrics.spectrum.source === 'string') {
                    rowData.metrics_spectrum_source = metrics.spectrum.source;
                }
            }

            if (!rowData.duration_ms && Number.isFinite(Number(region?.end)) && Number.isFinite(Number(region?.start))) {
                const duration = Number(region.end) - Number(region.start);
                rowData.duration_ms = formatNumberValue(duration, 0);
            }

            const row = header.map(column => escapeCsvValue(rowData[column]));
            rows.push(row.join(','));
        });

        return rows.join('\n');
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

    function parseAnnotationsCsv(csvText) {
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

        return { markers, regions };
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
            app.store.dispatch(app.actions.regionsAdded(payload));
            const utils = app.features?.regions?.utils;
            if (utils?.invalidateMetricsCache) {
                utils.invalidateMetricsCache();
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
    }

    function applyWorkspaceState(payload) {
        if (!payload || typeof payload !== 'object') {
            console.error('[Session] Invalid workspace payload.');
            return false;
        }

        if (!app.store || typeof app.store.dispatch !== 'function') {
            console.error('[Session] Store not available; cannot apply workspace.');
            return false;
        }

        if (!app.actions || typeof app.actions.rehydrateState !== 'function') {
            console.error('[Session] Rehydrate action is not available.');
            return false;
        }

        const nextState = payload.appState;
        if (!nextState || typeof nextState !== 'object') {
            console.error('[Session] Workspace payload missing appState.');
            return false;
        }

        warnOnSourceMismatch(payload.sourceConfigs);
        app.store.dispatch(app.actions.rehydrateState(nextState));
        if (app.regions?.invalidateMetricsCache) {
            app.regions.invalidateMetricsCache();
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
                }
            };
            reader.readAsText(file);
        });
        fileInput.click();
    }

    function handleMenuAction(action) {
        switch (action) {
            case 'save':
                saveWorkspace();
                break;
            case 'load':
                loadWorkspace();
                break;
            case 'export_annotations_csv':
            case 'export_regions':
                handleExportCsv();
                break;
            case 'import_annotations_csv':
            case 'import_regions':
                handleImportCsv();
                break;
            default:
                console.warn('[Session] Unhandled session menu action:', action);
        }
    }

    function handleExportCsv() {
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
        const csvText = buildAnnotationsCsv(markers, regions, state);
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `annotations-${timestamp}.csv`;
        triggerCsvDownload(filename, csvText);
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

                    const { markers, regions } = parseAnnotationsCsv(fileText);
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

    function applyInitialWorkspaceState() {
        if (initialStateApplied) {
            return false;
        }
        const savedState = app.registry?.models?.savedWorkspaceState;
        if (!savedState || typeof savedState !== 'object') {
            return false;
        }
        const applied = applyWorkspaceState({
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
        METRIC_COLUMNS: METRIC_COLUMNS.slice()
    };

    app.session = {
        saveWorkspace,
        loadWorkspace,
        handleMenuAction,
        applyWorkspaceState,
        applyInitialWorkspaceState,
        handleExportCsv,
        handleImportCsv,
        handleImportAnnotations: handleImportCsv,
        __testHelpers: testHelpers,
    };
})(window.NoiseSurveyApp);
