import { describe, it, expect, beforeAll, vi } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/services/session/sessionManager.js';

let helpers;

beforeAll(() => {
    helpers = window.NoiseSurveyApp?.session?.__testHelpers;
    if (!helpers) {
        throw new Error('Session CSV helpers are not available.');
    }
});

describe('Annotation CSV helpers', () => {
    it('formats timestamps in Excel-friendly UTC format', () => {
        const timestamp = Date.UTC(2023, 0, 15, 13, 45, 12, 34);
        expect(helpers.formatTimestampForCsv(timestamp)).toBe('2023-01-15 13:45:12.034');
    });

    it('builds and parses CSV containing markers and regions', () => {
        const markerTimestamp = Date.UTC(2024, 2, 10, 9, 8, 7, 123);
        const regionStart = Date.UTC(2024, 2, 10, 9, 0, 0, 0);
        const regionEnd = Date.UTC(2024, 2, 10, 9, 30, 0, 456);

        const csv = helpers.buildAnnotationsCsv(
            [{
                id: 2,
                timestamp: markerTimestamp,
                note: 'Marker, "note"',
                color: '#ff00ff',
                positionId: 'P1',
                metrics: {
                    parameter: 'LZeq',
                    timestamp: markerTimestamp,
                    broadband: [{ positionId: 'P1', value: 48.23 }],
                    spectral: [{ positionId: 'P1', labels: ['63', '125'], values: [40.5, 41.25] }]
                }
            }],
            [{
                id: 5,
                positionId: 'P1',
                start: regionStart,
                end: regionEnd,
                areas: [{ start: regionStart, end: regionEnd }],
                note: 'Region note',
                color: '#123456',
                metrics: {
                    laeq: 55.1234,
                    lafmax: 71.6,
                    la90: 42.987,
                    la90Available: true,
                    dataResolution: 'log',
                    durationMs: 30 * 60 * 1000,
                    parameter: 'LAeq',
                    spectrum: { labels: ['63', '125'], values: [32.1, 28.9], source: 'log' }
                }
            }],
            null
        );

        const lines = csv.split('\n');
        const headerCells = lines[0].split(',');
        expect(headerCells.slice(0, helpers.CSV_HEADER.length)).toEqual(helpers.CSV_HEADER);
        expect(headerCells).toEqual(expect.arrayContaining(helpers.METRIC_COLUMNS));
        expect(headerCells).toEqual(expect.arrayContaining(['band_63', 'band_125']));
        expect(lines).toHaveLength(3);
        expect(lines[1]).toContain('marker');
        expect(lines[2]).toContain('region');
        expect(lines[1]).toContain('2024-03-10 09:08:07.123');
        expect(lines[2]).toContain('2024-03-10 09:30:00.456');
        expect(lines[1]).toContain('48.23');
        expect(lines[1]).toContain('40.5');
        expect(lines[2]).toContain('55.123');
        expect(lines[2]).toContain('71.6');
        expect(lines[2]).toContain('true');

        const { markers, regions } = helpers.parseAnnotationsCsv(csv);
        expect(markers).toHaveLength(1);
        expect(regions).toHaveLength(1);

        const [marker] = markers;
        expect(marker.timestamp).toBe(markerTimestamp);
        expect(marker.note).toBe('Marker, "note"');
        expect(marker.color).toBe('#ff00ff');

        const [region] = regions;
        expect(region.positionId).toBe('P1');
        expect(region.start).toBe(regionStart);
        expect(region.end).toBe(regionEnd);
        expect(region.areas).toEqual([{ start: regionStart, end: regionEnd }]);
        expect(region.note).toBe('Region note');
        expect(region.color).toBe('#123456');
    });

    it('preserves multi-area regions through CSV round-trip', () => {
        const firstStart = Date.UTC(2024, 4, 1, 12, 0, 0, 0);
        const firstEnd = Date.UTC(2024, 4, 1, 12, 5, 0, 0);
        const secondStart = Date.UTC(2024, 4, 1, 12, 10, 0, 0);
        const secondEnd = Date.UTC(2024, 4, 1, 12, 15, 0, 0);

        const csv = helpers.buildAnnotationsCsv([], [{
            id: 7,
            positionId: 'P2',
            start: firstStart,
            end: secondEnd,
            areas: [
                { start: firstStart, end: firstEnd },
                { start: secondStart, end: secondEnd }
            ],
            note: 'Multi area',
            color: '#abcdef'
        }], null);

        const { regions } = helpers.parseAnnotationsCsv(csv);
        expect(regions).toHaveLength(1);

        const [region] = regions;
        expect(region.positionId).toBe('P2');
        expect(region.start).toBe(firstStart);
        expect(region.end).toBe(secondEnd);
        expect(region.areas).toEqual([
            { start: firstStart, end: firstEnd },
            { start: secondStart, end: secondEnd }
        ]);
        expect(region.note).toBe('Multi area');
        expect(region.color).toBe('#abcdef');
    });

    it('parses timestamps without fractional seconds', () => {
        const csv = [
            helpers.CSV_HEADER.join(','),
            'marker,1,,2024-03-10 09:08:07,,Quick note,#abcdef'
        ].join('\n');

        const { markers } = helpers.parseAnnotationsCsv(csv);
        expect(markers).toHaveLength(1);
        expect(markers[0].timestamp).toBe(Date.UTC(2024, 2, 10, 9, 8, 7));
    });
});

describe('Annotation CSV region offset provenance', () => {
    it('includes provenance columns in the header', () => {
        const csv = helpers.buildAnnotationsCsv([], [{
            id: 1, positionId: 'P1',
            start: Date.UTC(2024, 0, 1, 10, 0, 0),
            end: Date.UTC(2024, 0, 1, 11, 0, 0),
            areas: [{ start: Date.UTC(2024, 0, 1, 10, 0, 0), end: Date.UTC(2024, 0, 1, 11, 0, 0) }],
            note: ''
        }], null);

        const headerCells = csv.split('\n')[0].split(',');
        expect(headerCells).toContain('chart_offset_ms');
        expect(headerCells).toContain('source_start_utc');
        expect(headerCells).toContain('source_end_utc');
        expect(headerCells).toContain('source_areas');
        // CSV_HEADER columns remain at the front
        expect(headerCells.slice(0, helpers.CSV_HEADER.length)).toEqual(helpers.CSV_HEADER);
    });

    it('emits source times offset-shifted from display times for a region with non-zero offset', () => {
        const displayStart = Date.UTC(2024, 0, 1, 10, 0, 0, 0);
        const displayEnd   = Date.UTC(2024, 0, 1, 11, 0, 0, 0);
        const offsetMs = 5 * 60 * 1000; // 300 000 ms

        const region = {
            id: 99, positionId: 'P1',
            start: displayStart, end: displayEnd,
            areas: [{ start: displayStart, end: displayEnd }],
            note: 'offset test', color: '#aabbcc'
        };
        const state = { view: { selectedParameter: 'LAeq', positionChartOffsets: { P1: offsetMs } } };

        const csv = helpers.buildAnnotationsCsv([], [region], state);
        const lines = csv.split('\n');
        const regionRow = lines[1];

        // Display times stay unchanged
        expect(regionRow).toContain('2024-01-01 10:00:00.000');
        expect(regionRow).toContain('2024-01-01 11:00:00.000');

        // Provenance: offset value and source-shifted timestamps
        const sourceStart = helpers.formatTimestampForCsv(displayStart - offsetMs);
        const sourceEnd   = helpers.formatTimestampForCsv(displayEnd - offsetMs);
        expect(regionRow).toContain(String(offsetMs));   // chart_offset_ms
        expect(regionRow).toContain(sourceStart);         // source_start_utc
        expect(regionRow).toContain(sourceEnd);           // source_end_utc
        // source_areas JSON contains both source timestamps
        expect(regionRow).toContain(sourceStart.replace(/ /g, ' '));
        expect(regionRow).toContain(sourceEnd.replace(/ /g, ' '));
    });

    it('source times equal display times and offset is 0 when no offset is set', () => {
        const displayStart = Date.UTC(2024, 0, 2, 12, 0, 0, 0);
        const displayEnd   = Date.UTC(2024, 0, 2, 12, 30, 0, 0);

        const region = {
            id: 100, positionId: 'P2',
            start: displayStart, end: displayEnd,
            areas: [{ start: displayStart, end: displayEnd }],
            note: ''
        };
        const state = { view: { selectedParameter: 'LAeq' } }; // no positionChartOffsets

        const csv = helpers.buildAnnotationsCsv([], [region], state);
        const lines = csv.split('\n');
        const regionRow = lines[1];

        const displayStartStr = helpers.formatTimestampForCsv(displayStart);
        const displayEndStr   = helpers.formatTimestampForCsv(displayEnd);

        // Source timestamps equal display timestamps (both appear in the row)
        expect(regionRow).toContain(displayStartStr);
        expect(regionRow).toContain(displayEndStr);
        // The row must not contain any timestamp earlier than displayStart
        // (which would indicate a spurious non-zero offset was applied)
        expect(regionRow).not.toContain(helpers.formatTimestampForCsv(displayStart - 1));

        // chart_offset_ms = 0: use a regex anchored between commas to avoid
        // false positives from quoted JSON fields containing commas
        expect(regionRow).toMatch(/,0,/);
    });

    it('leaves provenance columns blank for marker rows', () => {
        const markerTime = Date.UTC(2024, 0, 3, 8, 0, 0, 0);
        const marker = { id: 1, timestamp: markerTime, note: 'test', positionId: 'P1' };
        const state = { view: { positionChartOffsets: { P1: 9999 } } };

        const csv = helpers.buildAnnotationsCsv([marker], [], state);
        const lines = csv.split('\n');
        const headerCells = lines[0].split(',');
        const markerRow = lines[1];
        const rawCells = markerRow.split(',');

        expect(rawCells[headerCells.indexOf('chart_offset_ms')]).toBe('');
        expect(rawCells[headerCells.indexOf('source_start_utc')]).toBe('');
        expect(rawCells[headerCells.indexOf('source_end_utc')]).toBe('');
    });

    it('CSV import without provenance columns remains backward-compatible', () => {
        // Older CSV with only the base CSV_HEADER columns
        const oldCsv = [
            helpers.CSV_HEADER.join(','),
            'region,5,P1,2024-01-01 10:00:00.000,2024-01-01 11:00:00.000,note,#abc,'
        ].join('\n');

        const { regions } = helpers.parseAnnotationsCsv(oldCsv);
        expect(regions).toHaveLength(1);
        expect(regions[0].positionId).toBe('P1');
        expect(regions[0].start).toBe(Date.UTC(2024, 0, 1, 10, 0, 0, 0));
        expect(regions[0].end).toBe(Date.UTC(2024, 0, 1, 11, 0, 0, 0));
    });

    it('CSV import ignores unknown provenance columns without error', () => {
        // New-format CSV that includes provenance columns — import should still work
        const state = { view: { selectedParameter: 'LAeq', positionChartOffsets: { P1: 60000 } } };
        const region = {
            id: 7, positionId: 'P1',
            start: Date.UTC(2024, 0, 4, 9, 0, 0, 0),
            end:   Date.UTC(2024, 0, 4, 10, 0, 0, 0),
            areas: [{ start: Date.UTC(2024, 0, 4, 9, 0, 0, 0), end: Date.UTC(2024, 0, 4, 10, 0, 0, 0) }],
            note: ''
        };
        const csv = helpers.buildAnnotationsCsv([], [region], state);

        const { regions } = helpers.parseAnnotationsCsv(csv);
        expect(regions).toHaveLength(1);
        // display start/end are preserved (not offset-shifted)
        expect(regions[0].start).toBe(region.start);
        expect(regions[0].end).toBe(region.end);
    });
});

describe('Session automation bridge', () => {
    it('exports ensureAutomationBridge and handles a set_parameter command', () => {
        const app = window.NoiseSurveyApp;
        const connect = vi.fn();
        const emit = vi.fn();
        const handleParameterChange = vi.fn();

        app.registry = app.registry || {};
        app.registry.models = {
            automationCommandSource: {
                data: {
                    request_id: ['req-1'],
                    command: ['set_parameter'],
                    payload: [JSON.stringify({ value: 'LAFmax' })],
                },
                change: { connect },
            },
            automationResultSource: {
                data: {},
                change: { emit },
            },
        };
        app.services = app.services || {};
        app.services.eventHandlers = app.services.eventHandlers || {};
        app.services.eventHandlers.view = { handleParameterChange };

        expect(typeof app.session.ensureAutomationBridge).toBe('function');
        expect(app.session.ensureAutomationBridge()).toBe(true);

        expect(connect).toHaveBeenCalledOnce();
        expect(handleParameterChange).toHaveBeenCalledWith('LAFmax');
        expect(app.registry.models.automationResultSource.data.success).toEqual([true]);
        expect(emit).toHaveBeenCalledOnce();
    });
});
