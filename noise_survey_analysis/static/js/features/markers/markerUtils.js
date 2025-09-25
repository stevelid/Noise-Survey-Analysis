// noise_survey_analysis/static/js/features/markers/markerUtils.js

/**
 * @fileoverview Utility helpers for working with marker annotations.
 *
 * The functions in this module are presentation-free helpers that handle
 * CSV import/export plus lightweight formatting for marker entities. They do
 * not mutate application state directly; instead they provide normalised
 * data that can be passed into reducers or action creators.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const CSV_HEADER = ['id', 'timestamp_ms', 'note', 'color', 'metrics_json', 'selected'];

    /**
     * Escapes a string value so it can be safely embedded inside a CSV cell.
     *
     * @param {string|number|null|undefined} value - Raw value that should be serialised.
     * @returns {string} CSV-safe representation of the supplied value.
     */
    function escapeCsvValue(value) {
        if (value === null || value === undefined) {
            return '';
        }
        const stringValue = String(value);
        if (!/[",\n]/.test(stringValue)) {
            return stringValue;
        }
        const escaped = stringValue.replace(/"/g, '""');
        return `"${escaped}"`;
    }

    /**
     * Splits a CSV line into individual cell values.
     * This lightweight parser supports quoted cells and escaped quotes.
     *
     * @param {string} line - Single CSV record.
     * @returns {string[]} Parsed cell values.
     */
    function parseCsvLine(line) {
        const cells = [];
        let current = '';
        let inQuotes = false;
        for (let i = 0; i < line.length; i++) {
            const char = line[i];
            if (char === '"') {
                if (inQuotes && line[i + 1] === '"') {
                    current += '"';
                    i += 1;
                } else {
                    inQuotes = !inQuotes;
                }
                continue;
            }
            if (char === ',' && !inQuotes) {
                cells.push(current.trim());
                current = '';
                continue;
            }
            current += char;
        }
        cells.push(current.trim());
        return cells;
    }

    /**
     * Serialises the current marker state to a CSV string.
     *
     * @param {Object} state - The global Redux-style state that contains the markers slice.
     * @returns {string} CSV payload describing all markers.
     */
    function formatMarkersCsv(state) {
        const markersState = state?.markers;
        if (!markersState || !Array.isArray(markersState.allIds)) {
            return `${CSV_HEADER.join(',')}\n`;
        }
        const rows = markersState.allIds
            .map(id => markersState.byId?.[id])
            .filter(Boolean)
            .map(marker => {
                const metricsJson = marker.metrics ? JSON.stringify(marker.metrics) : '';
                const selected = markersState.selectedId === marker.id ? 'true' : '';
                return [
                    escapeCsvValue(marker.id),
                    escapeCsvValue(marker.timestamp),
                    escapeCsvValue(marker.note || ''),
                    escapeCsvValue(marker.color || ''),
                    escapeCsvValue(metricsJson),
                    escapeCsvValue(selected)
                ].join(',');
            });
        return [CSV_HEADER.join(','), ...rows].join('\n');
    }

    /**
     * Parses a CSV payload and returns normalised marker objects that can be
     * supplied to the reducer via the `markersReplace` action.
     *
     * @param {string} csvText - Raw CSV input.
     * @returns {{ markers: Array<Object>, selectedId: number|null }} Parsed marker data.
     */
    function parseMarkersCsv(csvText) {
        if (typeof csvText !== 'string' || !csvText.trim()) {
            return { markers: [], selectedId: null };
        }
        const lines = csvText.split(/\r?\n/).filter(line => line.trim().length);
        if (!lines.length) {
            return { markers: [], selectedId: null };
        }
        const headerCells = parseCsvLine(lines[0]).map(cell => cell.toLowerCase());
        const indices = {
            id: headerCells.indexOf('id'),
            timestamp: headerCells.indexOf('timestamp_ms'),
            note: headerCells.indexOf('note'),
            color: headerCells.indexOf('color'),
            metrics: headerCells.indexOf('metrics_json'),
            selected: headerCells.indexOf('selected')
        };

        const markers = [];
        let selectedId = null;
        for (let i = 1; i < lines.length; i++) {
            const cells = parseCsvLine(lines[i]);
            if (cells.length === 0) {
                continue;
            }
            const timestampCell = indices.timestamp !== -1 ? cells[indices.timestamp] : undefined;
            const timestamp = Number(timestampCell);
            if (!Number.isFinite(timestamp)) {
                continue;
            }
            const idCell = indices.id !== -1 ? cells[indices.id] : undefined;
            const id = Number(idCell);
            const marker = {
                id: Number.isFinite(id) && id > 0 ? id : undefined,
                timestamp,
                note: indices.note !== -1 ? (cells[indices.note] || '') : '',
                color: indices.color !== -1 ? (cells[indices.color] || '') : undefined,
                metrics: null
            };
            if (indices.metrics !== -1) {
                const rawMetrics = cells[indices.metrics];
                if (rawMetrics) {
                    try {
                        const normalisedJson = rawMetrics.replace(/""/g, '"');
                        marker.metrics = JSON.parse(normalisedJson);
                    } catch (error) {
                        console.warn('[Markers] Failed to parse metrics JSON from CSV row:', error);
                    }
                }
            }
            if (indices.selected !== -1) {
                const isSelected = cells[indices.selected]?.toLowerCase() === 'true';
                if (isSelected && Number.isFinite(id)) {
                    selectedId = id;
                }
            }
            markers.push(marker);
        }
        return { markers, selectedId: Number.isFinite(selectedId) ? selectedId : null };
    }

    app.features = app.features || {};
    app.features.markers = app.features.markers || {};
    app.features.markers.utils = {
        formatMarkersCsv,
        parseMarkersCsv,
        escapeCsvValue
    };
})(window.NoiseSurveyApp);
