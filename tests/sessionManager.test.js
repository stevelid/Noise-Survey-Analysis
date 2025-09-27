import { describe, it, expect, beforeAll } from 'vitest';

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
            }]
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
        }]);

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
