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
                color: '#ff00ff'
            }],
            [{
                id: 5,
                positionId: 'P1',
                start: regionStart,
                end: regionEnd,
                note: 'Region note',
                color: '#123456'
            }]
        );

        const lines = csv.split('\n');
        expect(lines[0]).toBe(helpers.CSV_HEADER.join(','));
        expect(lines).toHaveLength(3);
        expect(lines[1]).toContain('marker');
        expect(lines[2]).toContain('region');
        expect(lines[1]).toContain('2024-03-10 09:08:07.123');
        expect(lines[2]).toContain('2024-03-10 09:30:00.456');

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
