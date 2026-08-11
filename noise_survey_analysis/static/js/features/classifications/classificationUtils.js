// noise_survey_analysis/static/js/features/classifications/classificationUtils.js

/**
 * @fileoverview Import/export helpers for classifier interval annotations.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const CSV_COLUMNS = [
        'position_id',
        'source_id',
        'source_label',
        'start',
        'end',
        'state',
        'confidence',
        'description',
        'audio_file',
        'color'
    ];

    function escapeCsvValue(value) {
        if (value === null || value === undefined) {
            return '';
        }
        const text = String(value);
        if (/[",\n\r]/.test(text)) {
            return '"' + text.replace(/"/g, '""') + '"';
        }
        return text;
    }

    function parseCsvRows(csvText) {
        if (typeof csvText !== 'string') {
            return [];
        }
        const rows = [];
        let currentRow = [];
        let currentValue = '';
        let inQuotes = false;

        for (let i = 0; i < csvText.length; i += 1) {
            const char = csvText[i];
            const nextChar = csvText[i + 1];
            if (inQuotes) {
                if (char === '"' && nextChar === '"') {
                    currentValue += '"';
                    i += 1;
                } else if (char === '"') {
                    inQuotes = false;
                } else {
                    currentValue += char;
                }
                continue;
            }
            if (char === '"') {
                inQuotes = true;
            } else if (char === ',') {
                currentRow.push(currentValue);
                currentValue = '';
            } else if (char === '\n') {
                currentRow.push(currentValue);
                rows.push(currentRow);
                currentRow = [];
                currentValue = '';
            } else if (char !== '\r') {
                currentValue += char;
            }
        }

        if (inQuotes) {
            throw new Error('Unterminated quoted field in classifier CSV.');
        }

        currentRow.push(currentValue);
        rows.push(currentRow);
        return rows.filter(row => row.some(cell => String(cell ?? '').trim() !== ''));
    }

    function parseTimestamp(value) {
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
        const parsed = Date.parse(normalized);
        return Number.isNaN(parsed) ? null : parsed;
    }

    function formatTimestamp(timestamp) {
        const numeric = Number(timestamp);
        if (!Number.isFinite(numeric)) {
            return '';
        }
        return new Date(numeric).toISOString();
    }

    function buildColumnIndex(headerRow) {
        const normalized = headerRow.map(cell => String(cell || '').trim().toLowerCase());
        const aliases = {
            position_id: ['position_id', 'positionid', 'position'],
            source_id: ['source_id', 'sourceid', 'source'],
            source_label: ['source_label', 'sourcelabel', 'label'],
            start: ['start', 'start_utc', 'start_time', 'startms', 'start_ms'],
            end: ['end', 'end_utc', 'end_time', 'endms', 'end_ms'],
            state: ['state', 'status'],
            confidence: ['confidence', 'score'],
            description: ['description', 'note', 'notes'],
            audio_file: ['audio_file', 'audiofile', 'file'],
            color: ['color', 'colour']
        };
        const columnIndex = {};
        Object.keys(aliases).forEach(key => {
            const match = aliases[key].find(alias => normalized.includes(alias));
            if (match) {
                columnIndex[key] = normalized.indexOf(match);
            }
        });
        return columnIndex;
    }

    function parseClassificationsCsv(csvText) {
        const rows = parseCsvRows(csvText);
        if (!rows.length) {
            return [];
        }
        const columnIndex = buildColumnIndex(rows[0]);
        if (columnIndex.position_id === undefined || columnIndex.source_id === undefined
            || columnIndex.start === undefined || columnIndex.end === undefined) {
            throw new Error('Classifier CSV must include position_id, source_id, start, and end columns.');
        }

        const entries = [];
        for (let i = 1; i < rows.length; i += 1) {
            const row = rows[i];
            const start = parseTimestamp(row[columnIndex.start]);
            const end = parseTimestamp(row[columnIndex.end]);
            if (!Number.isFinite(start) || !Number.isFinite(end)) {
                continue;
            }
            entries.push({
                positionId: String(row[columnIndex.position_id] || '').trim(),
                sourceId: String(row[columnIndex.source_id] || '').trim(),
                sourceLabel: columnIndex.source_label !== undefined ? String(row[columnIndex.source_label] || '').trim() : '',
                start,
                end,
                state: columnIndex.state !== undefined ? row[columnIndex.state] : 'on',
                confidence: columnIndex.confidence !== undefined ? row[columnIndex.confidence] : null,
                description: columnIndex.description !== undefined ? String(row[columnIndex.description] || '') : '',
                audioFile: columnIndex.audio_file !== undefined ? String(row[columnIndex.audio_file] || '').trim() : '',
                color: columnIndex.color !== undefined ? String(row[columnIndex.color] || '').trim() : ''
            });
        }
        return entries;
    }

    function parseClassificationsJson(jsonText) {
        const parsed = typeof jsonText === 'string' ? JSON.parse(jsonText) : jsonText;
        if (Array.isArray(parsed)) {
            return parsed;
        }
        if (parsed && typeof parsed === 'object') {
            if (Array.isArray(parsed.classifications)) {
                return parsed.classifications;
            }
            if (Array.isArray(parsed.audio_classifications)) {
                return parsed.audio_classifications;
            }
            if (Array.isArray(parsed.annotations)) {
                return parsed.annotations
                    .filter(item => item?.type === 'classification' || item?.type === 'audio_classification')
                    .map(item => item?.data ?? item);
            }
        }
        return [];
    }

    function buildClassificationsCsv(classifications) {
        const rows = [CSV_COLUMNS.join(',')];
        (Array.isArray(classifications) ? classifications : []).forEach(entry => {
            const row = [
                entry?.positionId,
                entry?.sourceId,
                entry?.sourceLabel,
                formatTimestamp(entry?.start),
                formatTimestamp(entry?.end),
                entry?.state,
                entry?.confidence,
                entry?.description,
                entry?.audioFile,
                entry?.color
            ];
            rows.push(row.map(escapeCsvValue).join(','));
        });
        return rows.join('\n');
    }

    const LOW_SCORE_MAX = 0.20;
    const MEDIUM_SCORE_MAX = 0.50;

    function hexToRgb(hex) {
        if (!hex || typeof hex !== 'string') return { r: 128, g: 128, b: 128 };
        let c = hex.replace('#', '').trim();
        if (c.length === 3) c = c.split('').map(x => x + x).join('');
        const num = parseInt(c, 16);
        if (Number.isNaN(num)) return { r: 128, g: 128, b: 128 };
        return {
            r: (num >> 16) & 255,
            g: (num >> 8) & 255,
            b: num & 255
        };
    }

    function rgbToHex(r, g, b) {
        const toHex = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
        return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
    }

    function getShadedColorForScore(baseColor, score) {
        if (!baseColor) return '#2e86ab';
        if (!Number.isFinite(score)) return baseColor;

        const { r, g, b } = hexToRgb(baseColor);
        if (score < LOW_SCORE_MAX) {
            // Light shade (mix 40% white)
            return rgbToHex(r + (255 - r) * 0.4, g + (255 - g) * 0.4, b + (255 - b) * 0.4);
        }
        if (score < MEDIUM_SCORE_MAX) {
            // Base shade
            return baseColor;
        }
        // Dark shade (mix 25% black)
        return rgbToHex(r * 0.75, g * 0.75, b * 0.75);
    }

    app.features = app.features || {};
    app.features.classifications = app.features.classifications || {};
    app.features.classifications.utils = {
        CSV_COLUMNS: CSV_COLUMNS.slice(),
        LOW_SCORE_MAX,
        MEDIUM_SCORE_MAX,
        parseClassificationsCsv,
        parseClassificationsJson,
        buildClassificationsCsv,
        parseTimestamp,
        formatTimestamp,
        getShadedColorForScore
    };
})(window.NoiseSurveyApp);
