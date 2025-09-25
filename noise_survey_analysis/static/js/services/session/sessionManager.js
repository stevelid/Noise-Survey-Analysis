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

    const CSV_HEADER = ['type', 'id', 'positionId', 'start_utc', 'end_utc', 'note', 'color'];

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

    function buildAnnotationsCsv(markersInput, regionsInput) {
        const rows = [CSV_HEADER.join(',')];
        const markers = Array.isArray(markersInput) ? markersInput : [];
        const regions = Array.isArray(regionsInput) ? regionsInput : [];

        markers.forEach(marker => {
            const formattedStart = formatTimestampForCsv(marker?.timestamp);
            if (!formattedStart) {
                return;
            }

            const row = [
                'marker',
                Number.isFinite(Number(marker?.id)) ? Number(marker.id) : '',
                marker?.positionId ?? '',
                formattedStart,
                '',
                typeof marker?.note === 'string' ? marker.note : '',
                typeof marker?.color === 'string' ? marker.color : ''
            ];

            rows.push(row.map(escapeCsvValue).join(','));
        });

        regions.forEach(region => {
            const formattedStart = formatTimestampForCsv(region?.start);
            const formattedEnd = formatTimestampForCsv(region?.end);
            if (!formattedStart || !formattedEnd) {
                return;
            }

            const row = [
                'region',
                Number.isFinite(Number(region?.id)) ? Number(region.id) : '',
                typeof region?.positionId === 'string' ? region.positionId : '',
                formattedStart,
                formattedEnd,
                typeof region?.note === 'string' ? region.note : '',
                typeof region?.color === 'string' ? region.color : ''
            ];

            rows.push(row.map(escapeCsvValue).join(','));
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
                    const region = {
                        positionId,
                        start: normalizedStart,
                        end: normalizedEnd,
                        areas: [{ start: normalizedStart, end: normalizedEnd }],
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
        const csvText = buildAnnotationsCsv(markers, regions);
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
        fileInput.accept = '.csv,text/csv';
        fileInput.addEventListener('change', event => {
            const file = event.target?.files?.[0];
            if (!file) {
                return;
            }

            const reader = new FileReader();
            reader.onload = () => {
                try {
                    const csvText = typeof reader.result === 'string' ? reader.result : '';
                    const { markers, regions } = parseAnnotationsCsv(csvText);
                    if (Array.isArray(markers)) {
                        app.store.dispatch(app.actions.markersReplace(markers));
                    }
                    if (Array.isArray(regions)) {
                        app.store.dispatch(app.actions.regionReplaceAll(regions));
                    }
                    console.info('[Session] Annotation import complete.');
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
        CSV_HEADER: CSV_HEADER.slice()
    };

    app.session = {
        saveWorkspace,
        loadWorkspace,
        handleMenuAction,
        applyWorkspaceState,
        applyInitialWorkspaceState,
        handleExportCsv,
        handleImportCsv,
        __testHelpers: testHelpers,
    };
})(window.NoiseSurveyApp);
