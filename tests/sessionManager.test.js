import { describe, it, expect, beforeAll, vi } from 'vitest';
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/features/regions/annotationMetrics.js';
import '../noise_survey_analysis/static/js/services/session/annotationCsv.js';
import '../noise_survey_analysis/static/js/services/session/sessionManager.js';

let helpers;
beforeAll(() => { helpers = window.NoiseSurveyApp.session.__testHelpers; });
const app = window.NoiseSurveyApp;
const section = (text, name) => app.annotationCsv.readSection(app.annotationCsv.parseCsvRows(text), name);

describe('Annotation CSV helpers', () => {
    it('formats and parses Excel-compatible UTC timestamps', () => {
        const value = Date.UTC(2023, 0, 15, 13, 45, 12, 34);
        expect(helpers.formatTimestampForCsv(value)).toBe('2023-01-15 13:45:12.034');
        expect(helpers.parseTimestampFromCsv('2023-01-15 13:45:12.034')).toBe(value);
        expect(helpers.parseTimestampFromCsv('2023-01-15 13:45:12')).toBe(value - 34);
    });

    it('exports annotation fields before separate overall/spectral sections', () => {
        const region = { id: 5, positionId: 'P1', areas: [{ start: 1000, end: 3000 }], note: 'Region, "night"', color: '#123456' };
        const csv = helpers.buildAnnotationsCsv([{ id: 2, timestamp: 1500, note: 'Marker', color: '#ff00ff', metrics: { test: 1 } }], [region], {}, { mode: 'full' });
        expect(csv.startsWith('NSA annotations export,format=2')).toBe(true);
        expect(section(csv, 'REGIONS')[0]).toMatchObject({ id: '5', note: 'Region, "night"', origin_meter: 'P1', colour: '#123456' });
        expect(section(csv, 'OVERALL')).toHaveLength(1);
        expect(section(csv, 'NOTES').some(row => row.key === 'caveats' && row.value.includes('indicative'))).toBe(true);
        const result = helpers.parseAnnotationsCsv(csv);
        expect(result.regions[0]).toMatchObject({ id: 5, positionId: 'P1', note: region.note, areas: region.areas });
        expect(result.markers[0].metrics).toEqual({ test: 1 });
    });

    it('preserves multi-area geometry and category/meter states across round trips', () => {
        const region = app.annotationModel.normalizeRegion({ id: 7, positionId: 'P2',
            areas: [{ start: 1000, end: 2000 }, { start: 3000, end: 4000 }], categoryId: 'plant', note: 'Two events', color: null,
            meterStates: { P1: 'absent', P3: 'unchecked' } }, ['P1', 'P2', 'P3']);
        const state = { view: { availablePositions: ['P1', 'P2', 'P3'] }, regions: { categories: app.annotationModel.normalizeCatalog() } };
        const csv = helpers.buildAnnotationsCsv([], [region], state);
        expect(helpers.parseAnnotationsCsv(csv).regions).toEqual([region]);
    });

    it('retains old unsectioned CSV imports with no provenance or metric columns', () => {
        const old = [helpers.CSV_HEADER.join(','), 'region,5,P1,2024-01-01 10:00:00,2024-01-01 11:00:00,note,#abc,'].join('\n');
        const result = helpers.parseAnnotationsCsv(old);
        expect(result.regions).toHaveLength(1);
        expect(result.regions[0]).toMatchObject({ positionId: 'P1', start: Date.UTC(2024, 0, 1, 10), end: Date.UTC(2024, 0, 1, 11) });
    });
});

describe('Annotation CSV source provenance', () => {
    it('exports source times with the target offset and displays untouched annotation times', () => {
        const state = { view: { availablePositions: ['P1'], positionChartOffsets: { P1: 1000 } } };
        const region = { id: 7, positionId: 'P1', areas: [{ start: 2000, end: 4000 }], note: '' };
        const models = { timeSeriesSources: { P1: { log: { data: { Datetime: [1000, 2000], LAeq: [60, 70] } } } } };
        const csv = helpers.buildAnnotationsCsv([], [region], state, { models, mode: 'full' });
        const row = section(csv, 'REGIONS')[0];
        expect(row.chart_offset_ms).toBe('1000');
        expect(row.start).toBe('1970-01-01 00:00:02.000');
        expect(row.source_start).toBe('1970-01-01 00:00:01.000');
        expect(Number(row.LAeq_dB)).toBeCloseTo(67.4036, 4);
        expect(helpers.parseAnnotationsCsv(csv).regions[0].start).toBe(2000);
    });

    it('retains indicative overview LAF90 in OVERALL and labels its method', () => {
        const region = { id: 1, positionId: 'P1', areas: [{ start: 0, end: 1000 }] };
        const models = { timeSeriesSources: { P1: { overview: { data: { Datetime: [0, 1000], LAeq: [50, 60] } } } } };
        const csv = helpers.buildAnnotationsCsv([], [region], {}, { models, mode: 'full' });
        const row = section(csv, 'OVERALL')[0];
        expect(row.data_resolution).toBe('overview');
        expect(Number(row.LAF90_dB)).toBe(50);
        expect(row.percentile_method).toContain('indicative');
        expect(row.LAFmax_dB).toBe('');
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
