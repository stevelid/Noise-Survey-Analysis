import { describe, expect, it, vi } from 'vitest';
import { execFileSync } from 'node:child_process';
import '../noise_survey_analysis/static/js/features/regions/annotationModel.js';
import '../noise_survey_analysis/static/js/features/regions/annotationMetrics.js';
import '../noise_survey_analysis/static/js/features/regions/regionUtils.js';
import '../noise_survey_analysis/static/js/services/session/annotationCsv.js';

const app = window.NoiseSurveyApp;
const engine = app.annotationMetrics;

describe('shared authoritative metric contract', () => {
    it('energy-averages equal-duration 60 and 70 dB samples to 67.4036 dB', () => {
        const result = engine.computeSamples({ Datetime: [0, 1000], LAeq: [60, 70] }, [{ start: 0, end: 2000 }]);
        expect(result.laeq).toBeCloseTo(67.4036268949, 8);
        expect(result.lafmax).toBeNull();
        expect(result.la90).toBe(60);
        expect(result.percentileMethod).toContain('indicative');
    });

    it('retains genuine maxima and percentile-only data when LAeq is unavailable', () => {
        const entity = { positionId: 'P1', areas: [{ start: 0, end: 2000 }] };
        const models = { timeSeriesSources: { P1: { log: { data: { Datetime: [0, 1000], LAFmax: [75, 80] } } } } };
        const maximum = engine.computeRegion(entity, {}, models);
        expect(maximum.dataResolution).toBe('log');
        expect(maximum.laeq).toBeNull();
        expect(maximum.lafmax).toBe(80);
        expect(maximum.lafmaxAvailable).toBe(true);
        expect(maximum.missingReasons.join('; ')).toContain('LAeq column unavailable');
        models.timeSeriesSources.P1.log.data = { Datetime: [0, 1000], LAF: [40, 50] };
        const percentile = engine.computeRegion(entity, {}, models);
        expect(percentile.dataResolution).toBe('log');
        expect(percentile.laeq).toBeNull();
        expect(percentile.la90).toBe(40);
    });

    it('keeps usable partial log broadband and spectra when no overview is available', () => {
        const entity = { positionId: 'P1', areas: [{ start: 0, end: 4000 }] };
        const models = { timeSeriesSources: { P1: { log: { data: { Datetime: [0, 1000], LAeq: [60, 70] } } } },
            preparedGlyphData: { P1: { log: { prepared_params: { LZeq: {
                times_ms: [0, 1000], n_times: 2, time_step: 1000, frequency_labels: ['63 Hz'], levels_flat_transposed: [60, 70]
            } } } } } };
        const result = engine.computeRegion(entity, {}, models);
        expect(result.dataResolution).toBe('log');
        expect(result.coverage).toBe(0.5);
        expect(result.laeq).toBeCloseTo(67.4036268949, 6);
        expect(result.missingReasons.join('; ')).toContain('incomplete timestamp coverage');
        expect(result.spectra.LZeq.source).toBe('log');
        expect(result.spectra.LZeq.coverage).toBe(0.5);
        expect(result.spectra.LZeq.values[0]).toBeCloseTo(67.4036268949, 6);
        expect(result.spectra.LZeq.missingReasons.join('; ')).toContain('incomplete timestamp coverage');
    });

    it('agrees with Python within 0.05 dB for partial samples, areas, offsets and pooled context', () => {
        const data = { Datetime: [-3000, -2000, -1000, 0, 1000, 2000, 3000, 4000],
            LAeq: [40, 41, 42, 60, 70, 45, 46, 47], LAF: [35, 36, 37, 55, 65, 40, 41, 42],
            LAFmax: [50, 51, 52, 75, 80, 55, 56, 57] };
        const areas = [{ start: 1250, end: 2500 }, { start: 2750, end: 3000 }];
        const context = [{ start: -2000, end: 1000 }, { start: 3000, end: 6000 }];
        const js = engine.computeSamples(data, areas, { chartOffsetMs: 1000, contextAreas: context, minContextS: 1 });
        const script = `import json,sys,pandas as pd\nfrom dataclasses import asdict\nfrom noise_survey_analysis.core.annotation_metrics import compute_region_metrics\np=json.load(sys.stdin)\nf=pd.DataFrame(p['data'])\nf['Datetime']=pd.to_datetime(f['Datetime'],unit='ms',utc=True)\nr=compute_region_metrics(f,p['areas'],chart_offset_ms=1000,context_areas=p['context'],min_context_s=1)\nprint(json.dumps(asdict(r)))`;
        const python = JSON.parse(execFileSync('python', ['-c', script], {
            input: JSON.stringify({ data, areas, context }), encoding: 'utf8', cwd: process.cwd()
        }));
        [['laeq', 'LAeq_dB'], ['lafmax', 'LAFmax_dB'], ['la90', 'LAF90_dB'],
            ['backgroundLA90', 'background_LA90_dB'], ['backgroundLAeq', 'background_LAeq_dB']].forEach(([left, right]) => {
            expect(js[left]).not.toBeNull();
            expect(Math.abs(js[left] - python[right])).toBeLessThan(0.05);
        });
        expect(js.contextDurationS).toBeCloseTo(python.context_duration_s, 6);
    });

    it('flags coarse resolution, drops LAFmax and matches Python for overview data', () => {
        const data = { Datetime: [0, 300000, 600000, 900000], LAeq: [44.1, 50, 52, 60],
            LAFmax: [70, 75, 76, 80], LAF90: [40, 41, 42, 55] };
        const small = [{ start: 10000, end: 30000 }];
        const coarse = engine.computeSamples(data, small, { resolution: 'overview', sampleIntervalS: 300 });
        expect(coarse.coarseResolution).toBe(true);
        expect(coarse.coarseResolutionReason).toContain('5-min data longer than the event');
        expect(coarse.lafmax).toBeNull();
        expect(coarse.missingReasons.join(';')).not.toContain('LAFmax');
        const wide = [{ start: 0, end: 1200000 }];
        const js = engine.computeSamples(data, wide, { resolution: 'overview', sampleIntervalS: 300 });
        expect(js.coarseResolution).toBe(false);
        expect(js.la90).toBe(41);
        expect(js.percentileMethod).toContain('median of logged LAF90');
        const script = `import json,sys,pandas as pd
from dataclasses import asdict
from noise_survey_analysis.core.annotation_metrics import compute_region_metrics
p=json.load(sys.stdin)
f=pd.DataFrame(p['data'])
f['Datetime']=pd.to_datetime(f['Datetime'],unit='ms',utc=True)
out=[asdict(compute_region_metrics(f,a,resolution='overview',sample_interval_s=300)) for a in (p['small'],p['wide'])]
print(json.dumps(out))`;
        const [pyCoarse, pyWide] = JSON.parse(execFileSync('python', ['-c', script], {
            input: JSON.stringify({ data, small, wide }), encoding: 'utf8', cwd: process.cwd() }));
        expect(pyCoarse.coarse_resolution).toBe(true);
        expect(pyCoarse.LAFmax_dB).toBeNull();
        expect(pyCoarse.coarse_resolution_reason).toBe(coarse.coarseResolutionReason);
        expect(pyWide.LAF90_dB).toBe(js.la90);
        expect(pyWide.percentile_method).toBe(js.percentileMethod);
    });

    it('applies the same coarse rule as Python: 1 s keeps LAFmax; 300 s is coarse below 30 min', () => {
        const fast = { Datetime: Array.from({ length: 20 }, (_, i) => i * 1000), LAeq: Array(20).fill(50), LAFmax: Array.from({ length: 20 }, (_, i) => 60 + i) };
        const short = engine.computeSamples(fast, [{ start: 5000, end: 7000 }], { sampleIntervalS: 1 });
        expect(short.coarseResolution).toBe(false);
        expect(short.lafmax).toBe(66);
        const slow = { Datetime: Array.from({ length: 10 }, (_, i) => i * 300000), LAeq: Array(10).fill(50), LAFmax: Array(10).fill(60) };
        [[20000, true], [600000, true], [1800000, false]].forEach(([end, expected]) => {
            const r = engine.computeSamples(slow, [{ start: 0, end }], { resolution: 'overview', sampleIntervalS: 300 });
            expect(r.coarseResolution).toBe(expected);
            expect(r.lafmax === null).toBe(expected);
        });
    });

    it('does not stretch fast-level samples across gaps or silently accept a partial log buffer', () => {
        const region = { positionId: 'P1', areas: [{ start: 0, end: 4000 }] };
        const models = { timeSeriesSources: { P1: {
            log: { data: { Datetime: [0, 1000], LAeq: [80, 80] } },
            overview: { data: { Datetime: [0, 4000], LAeq: [50, 50] } }
        } } };
        expect(engine.computeRegion(region, {}, models).dataResolution).toBe('overview');
        expect(engine.computeRegion(region, {}, models, { resolution: 'log' }).coverage).toBe(0.5);
        // Three native samples establish the independent 1 s LAeq cadence.
        const value = engine.computeSamples({ Datetime: [0, 100, 200, 1000, 1100, 1200, 2000, 2100, 2200],
            LAeq: [60, null, null, 70, null, null, 80, null, null], LAF: [40, 41, 42, 50, 51, 52, 60, 61, 62] }, [{ start: 0, end: 2000 }]);
        expect(value.laeq).toBeCloseTo(67.4036, 4);
        expect(value.coverage).toBe(1);
    });

    it('does not infer a ten-second fast-level hold from two sparse readings on a one-second grid', () => {
        const data = { Datetime: Array.from({ length: 11 }, (_, index) => index * 1000),
            LAeq: Array(11).fill(60), LAF: [40, ...Array(9).fill(null), 80] };
        const result = engine.computeSamples(data, [{ start: 0, end: 11000 }], {
            contextAreas: [{ start: 1000, end: 10000 }], minContextS: 1
        });
        expect(result.coverage).toBe(1);
        expect(result.contextDurationS).toBe(0);
        expect(result.backgroundLA90).toBeNull();
    });

    it('accepts explicit independent native cadence when only two LAeq samples are available', () => {
        const data = { Datetime: Array.from({ length: 20 }, (_, index) => index * 100),
            LAeq: [60, ...Array(9).fill(null), 70, ...Array(9).fill(null)] };
        const uncertain = engine.computeSamples(data, [{ start: 0, end: 2000 }]);
        expect(uncertain.coverage).toBeCloseTo(.1);
        const known = engine.computeSamples(data, [{ start: 0, end: 2000 }], { columnSampleIntervalsS: { LAeq: 1 } });
        expect(known.coverage).toBe(1);
        expect(known.laeq).toBeCloseTo(67.4036268949, 6);
    });

    it('reads streamed spectral reservoir data and labels overview fallback explicitly', () => {
        const region = { positionId: 'P1', areas: [{ start: 0, end: 2000 }] };
        const models = { timeSeriesSources: { P1: { log: { data: { Datetime: [0, 1000], LAeq: [60, 70] } } } },
            spectrogramSources: { P1: { log: { data: {
                parameter: ['LZeq'], times_ms: [new Float64Array([0, 1000])],
                levels_flat_transposed: [new Float32Array([60, 70])], frequency_labels: [['63 Hz']], n_times: [2], time_step: [1000]
            } } } } };
        const value = engine.computeRegion(region, {}, models);
        expect(value.spectra.LZeq.values[0]).toBeCloseTo(67.4036268949, 6);
        expect(value.spectra.LZeq.source).toBe('log');
        models.spectrogramSources.P1.log.data.times_ms = [[1000]];
        models.spectrogramSources.P1.log.data.levels_flat_transposed = [[90]];
        models.spectrogramSources.P1.log.data.n_times = [1];
        models.preparedGlyphData = { P1: { overview: { prepared_params: { LZeq: {
            times_ms: [0, 2000], time_step: 2000, frequency_labels: ['63 Hz'], n_times: 2, levels_flat_transposed: [45, 45]
        } } } } };
        expect(engine.computeRegion(region, {}, models).spectra.LZeq.source).toBe('overview');
    });
});

describe('sectioned analysis CSV', () => {
    it('defaults to annotation-only without invoking metrics, retaining geometry, provenance and snapshots', () => {
        const region = app.annotationModel.normalizeRegion({ id: 9, positionId: 'P1',
            areas: [{ start: 2000, end: 4000 }, { start: 5000, end: 6000 }], note: 'Quick, "copy"',
            categoryId: 'plant', meterStates: { P2: 'absent' } }, ['P1', 'P2']);
        const markers = [{ id: 1, timestamp: 2500, note: 'Peak', color: '#abcdef', metrics: { P1: 70 } }];
        const state = { view: { availablePositions: ['P1', 'P2'], positionChartOffsets: { P1: 1000 } } };
        const compute = vi.spyOn(engine, 'computeRegion').mockImplementation(() => { throw new Error('Quick export must not compute metrics'); });
        try {
            // Even the both-resolutions preference must not turn a quick export into analysis.
            const csv = app.annotationCsv.buildAnnotationsCsv(markers, [region], state, { include_all_resolutions: true });
            const rows = app.annotationCsv.parseCsvRows(csv);
            expect(rows.filter(row => /^\[[A-Z_]+\]$/.test(row[0])).map(row => row[0])).toEqual(['[REGIONS]', '[MARKERS]', '[NOTES]']);
            const exported = app.annotationCsv.readSection(rows, 'REGIONS')[0];
            expect(exported).toMatchObject({ duration_s: '3', chart_offset_ms: '1000', source_start: '1970-01-01 00:00:01.000',
                source_areas: JSON.stringify([{ start: 1000, end: 3000 }, { start: 4000, end: 5000 }]),
                LAeq_dB: '', LAFmax_dB: '', data_resolution: '', sample_interval_s: '', coverage: '' });
            expect(app.annotationCsv.readSection(rows, 'NOTES')).toContainEqual({ key: 'export_mode', value: 'annotations' });
            const restored = app.annotationCsv.parseAnnotationsCsv(csv);
            expect(restored.regions).toEqual([region]);
            expect(restored.markers).toEqual(markers);
            expect(compute).not.toHaveBeenCalled();
        } finally { compute.mockRestore(); }
    });

    it('leaves proposed and rejected suggestions out by default and keeps provenance on the rest', () => {
        const agent = { name: 'yamnet', runId: 'r1' };
        const make = (id, status, extra = {}) => app.annotationModel.normalizeRegion({ id, positionId: 'P1',
            areas: [{ start: id * 10000, end: id * 10000 + 1000 }], source: 'agent', status, agent, rationale: 'because, "yes"', confidence: 0.8, ...extra }, ['P1']);
        const regions = [make(1, 'accepted'), make(2, 'proposed'), make(3, 'rejected'),
            app.annotationModel.normalizeRegion({ id: 4, positionId: 'P1', areas: [{ start: 50000, end: 51000 }] }, ['P1'])];
        const markers = [{ id: 1, timestamp: 1000, status: 'accepted', source: 'agent', agent }, { id: 2, timestamp: 2000, status: 'proposed', source: 'agent', agent }, { id: 3, timestamp: 3000, status: 'rejected', source: 'agent' }];
        const state = { view: { availablePositions: ['P1'] } };
        const csv = app.annotationCsv.buildAnnotationsCsv(markers, regions, state);
        const rows = app.annotationCsv.parseCsvRows(csv);
        expect(app.annotationCsv.readSection(rows, 'REGIONS').map(row => row.id)).toEqual(['1', '4']);
        expect(app.annotationCsv.readSection(rows, 'MARKERS').map(row => row.id)).toEqual(['1']);
        const restored = app.annotationCsv.parseAnnotationsCsv(csv);
        expect(restored.regions[0]).toMatchObject({ source: 'agent', status: 'accepted', confidence: 0.8, rationale: 'because, "yes"', agent });
        expect(restored.regions[1].status).toBeUndefined();
        expect(restored.markers[0]).toMatchObject({ source: 'agent', status: 'accepted', agent });
        const withProposed = app.annotationCsv.parseAnnotationsCsv(app.annotationCsv.buildAnnotationsCsv(markers, regions, state, { include_proposed: true }));
        expect(withProposed.regions.map(region => [region.id, region.status])).toEqual([[1, 'accepted'], [2, 'proposed'], [4, undefined]]);
        expect(withProposed.markers.map(marker => marker.status)).toEqual(['accepted', 'proposed']);
    });

    it('quick export works without a loaded metrics engine', () => {
        const saved = app.annotationMetrics;
        try {
            delete app.annotationMetrics;
            const csv = app.annotationCsv.buildAnnotationsCsv([], [{ id: 1, positionId: 'P1', start: 0, end: 1000 }]);
            expect(app.annotationCsv.readSection(app.annotationCsv.parseCsvRows(csv), 'REGIONS')).toHaveLength(1);
            expect(() => app.annotationCsv.buildAnnotationsCsv([], [], {}, { mode: 'full' })).toThrow('metrics engine');
        } finally { app.annotationMetrics = saved; }
    });

    it('round-trips region identity, all meter states, categories, marker snapshots and multiline text', () => {
        const categories = app.annotationModel.normalizeCatalog();
        const regions = [app.annotationModel.normalizeRegion({ id: 4, positionId: 'P1', areas: [{ start: 0, end: 2000 }],
            categoryIds: ['plant', 'speech'], categoryId: 'plant', color: null, note: 'Fan, "night"\n[OVERALL]\nUnicode: café', meterStates: { P2: 'absent', P3: 'unchecked' } }, ['P1', 'P2', 'P3'])];
        const state = { regions: { byId: { 4: regions[0] }, allIds: [4], categories }, view: { availablePositions: ['P1', 'P2', 'P3'], positionChartOffsets: { P2: 1000 } } };
        const markers = [{ id: 8, timestamp: 1000, note: 'Peak', color: '#abcdef', metrics: { broadband: [{ positionId: 'P1', value: 70 }] } }];
        const csv = app.annotationCsv.buildAnnotationsCsv(markers, regions, state, { models: {}, mode: 'full' });
        const result = app.annotationCsv.parseAnnotationsCsv(csv);
        expect(result.regions).toEqual(regions);
        expect(result.categories).toEqual(categories);
        expect(result.markers).toEqual(markers);
        const overall = app.annotationCsv.readSection(app.annotationCsv.parseCsvRows(csv), 'OVERALL');
        expect(overall).toHaveLength(3);
        expect(overall.map(row => row.state)).toEqual(['present', 'absent', 'unchecked']);
        expect(result.metadata.chart_offsets_ms).toEqual({ P2: 1000 });
    });

    it('exports both resolutions only when requested and frequency-orders canonical band columns', () => {
        const region = { id: 1, positionId: 'P1', areas: [{ start: 0, end: 2000 }] };
        const data = { Datetime: [0, 1000], LAeq: [60, 70] };
        const prepared = { times_ms: [0, 1000], n_times: 2, time_step: 1000,
            frequency_labels: ['1 kHz', '63 Hz'], levels_flat_transposed: [60, 70, 50, 50] };
        const models = { timeSeriesSources: { P1: { log: { data }, overview: { data } } },
            preparedGlyphData: { P1: { log: { prepared_params: { LZeq: prepared } }, overview: { prepared_params: { LZeq: prepared } } } } };
        const state = { view: { availablePositions: ['P1'] } };
        const best = app.annotationCsv.parseCsvRows(app.annotationCsv.buildAnnotationsCsv([], [region], state, { models, mode: 'full' }));
        const both = app.annotationCsv.parseCsvRows(app.annotationCsv.buildAnnotationsCsv([], [region], state, { models, mode: 'full', include_all_resolutions: true }));
        expect(app.annotationCsv.readSection(best, 'OVERALL')).toHaveLength(1);
        expect(app.annotationCsv.readSection(both, 'OVERALL')).toHaveLength(2);
        const header = best[best.findIndex(row => row[0] === '[SPECTRAL]') + 1];
        expect(header.slice(-2)).toEqual(['63Hz', '1000Hz']);
    });

    it('includes log spectra in dual-resolution exports even without log broadband data', () => {
        const region = { id: 1, positionId: 'P1', areas: [{ start: 0, end: 2000 }] };
        const prepared = { times_ms: [0, 1000], n_times: 2, time_step: 1000,
            frequency_labels: ['63 Hz'], levels_flat_transposed: [60, 70] };
        const models = { timeSeriesSources: { P1: { overview: { data: { Datetime: [0, 1000], LAeq: [40, 40] } } } },
            preparedGlyphData: { P1: { log: { prepared_params: { LZeq: prepared } }, overview: { prepared_params: { LZeq: prepared } } } } };
        const csv = app.annotationCsv.buildAnnotationsCsv([], [region], {}, { models, mode: 'full', include_all_resolutions: true });
        const spectral = app.annotationCsv.readSection(app.annotationCsv.parseCsvRows(csv), 'SPECTRAL');
        expect(spectral.map(row => row.data_resolution)).toEqual(['log', 'overview']);
        expect(Number(spectral[0]['63Hz'])).toBeCloseTo(67.4036268949, 6);
    });

    it('labels both requested OVERALL resolutions even for a spectral-only meter', () => {
        const entity = { id: 1, positionId: 'P1', areas: [{ start: 0, end: 2000 }] };
        const prepared = { times_ms: [0, 1000], n_times: 2, time_step: 1000,
            frequency_labels: ['63 Hz'], levels_flat_transposed: [60, 70] };
        const models = { preparedGlyphData: { P1: { log: { prepared_params: { LZeq: prepared } },
            overview: { prepared_params: { LZeq: prepared } } } } };
        const csv = app.annotationCsv.buildAnnotationsCsv([], [entity], {}, { models, mode: 'full', include_all_resolutions: true });
        const rows = app.annotationCsv.readSection(app.annotationCsv.parseCsvRows(csv), 'OVERALL');
        expect(rows.map(row => row.data_resolution)).toEqual(['log', 'overview']);
        rows.forEach(row => {
            expect(row.LAeq_dB).toBe('');
            expect(row.LAFmax_dB).toBe('');
            expect(row.missing_reasons).toContain('LAeq column unavailable');
        });
    });
});

describe('bounded geometry-sensitive metric cache', () => {
    it('distinguishes explicit native sample periods from inferred cadence', () => {
        app.regions.invalidateMetricsCache();
        const region = { id: 1, positionId: 'P1', areas: [{ start: 0, end: 2000 }] };
        const models = { timeSeriesSources: { P1: { log: { data: {
            Datetime: [0, 100, 200, 1000, 1100, 1200], LAeq: [60, null, null, 70, null, null]
        } } } } };
        const inferred = app.regions.getRegionMetrics(region, {}, {}, models, { resolution: 'log' });
        const explicit = app.regions.getRegionMetrics(region, {}, {}, models,
            { resolution: 'log', columnSampleIntervalsS: { LAeq: 1 } });
        expect(inferred.coverage).toBeCloseTo(.1);
        expect(explicit.coverage).toBe(1);
        expect(explicit).not.toBe(inferred);
    });
    it('reuses notes/colours/categories and invalidates only changed background geometry/presence', () => {
        const utils = app.regions;
        utils.invalidateMetricsCache();
        const target = { id: 1, positionId: 'P1', areas: [{ start: 2000, end: 3000 }], note: 'First' };
        const other = { id: 2, positionId: 'P2', meterStates: { P1: 'present' }, areas: [{ start: 1000, end: 2000 }] };
        const state = { view: { selectedParameter: 'LAeq' }, regions: { allIds: [1, 2], byId: { 1: target, 2: other } } };
        const models = { timeSeriesSources: { P1: { log: { data: {
            Datetime: [0, 1000, 2000, 3000, 4000, 5000], LAeq: [40, 70, 60, 40, 40, 40]
        } } } } };
        const options = { backgroundWindowS: 2, minContextS: 1 };
        const first = utils.getRegionMetrics(target, state, {}, models, options);
        const renamed = { ...target, note: 'Rewritten', color: '#abcdef', categoryId: 'traffic' };
        const textOnly = { ...state, regions: { ...state.regions, byId: { 1: renamed, 2: { ...other, note: 'Other note' } } } };
        expect(utils.getRegionMetrics(renamed, textOnly, {}, models, options)).toBe(first);
        const moved = { ...textOnly, regions: { ...state.regions, byId: { 1: renamed, 2: { ...other, areas: [{ start: 5000, end: 6000 }] } } } };
        const changed = utils.getRegionMetrics(renamed, moved, {}, models, options);
        expect(changed).not.toBe(first);
        expect(changed.backgroundLAeq).toBeGreaterThan(first.backgroundLAeq);
        const absent = { ...textOnly, regions: { ...state.regions, byId: { 1: renamed, 2: { ...other, meterStates: { P1: 'absent' } } } } };
        expect(utils.getRegionMetrics(renamed, absent, {}, models, options)).not.toBe(first);
    });

    it('evicts the oldest metric result after the 2048-entry limit', () => {
        const utils = app.regions;
        utils.invalidateMetricsCache();
        const entity = { id: 1, positionId: 'P1', areas: [{ start: 0, end: 1000 }] };
        const first = utils.getRegionMetrics(entity, {}, {}, {});
        for (let id = 2; id <= 2049; id++) utils.getRegionMetrics({ ...entity, id }, {}, {}, {});
        expect(utils.getRegionMetrics(entity, {}, {}, {})).not.toBe(first);
    });
});

describe('local time basis and resolution labelling in the region export', () => {
    const csvFor = (region, models, state = { view: { availablePositions: ['P1'] } }, options = {}) => app.annotationCsv.buildAnnotationsCsv(
        [], [region], state, { models, mode: 'full', ...options });
    const regionsRow = csv => app.annotationCsv.readSection(app.annotationCsv.parseCsvRows(csv), 'REGIONS')[0];

    it('keeps UTC start/end but adds naive BST columns that match the instrument log text', () => {
        // Log says 2026-09-02 10:57:00 (BST); the true instant is 09:57:00 UTC.
        const start = Date.UTC(2026, 8, 2, 9, 57, 0);
        const region = { id: 1, positionId: 'P1', areas: [{ start, end: start + 60000 }] };
        const row = regionsRow(csvFor(region, {}));
        expect(row.start).toBe('2026-09-02 09:57:00.000');
        expect(row.start_local).toBe('2026-09-02 10:57:00.000');
        expect(row.end_local).toBe('2026-09-02 10:58:00.000');
        expect(row.source_start_local).toBe(row.start_local);
    });

    it('adds ISO start_utc/end_utc/timezone to regions and timestamp_utc/position to markers without disturbing old columns', () => {
        const start = Date.UTC(2026, 8, 2, 9, 57, 0);
        const region = { id: 1, positionId: 'P1', areas: [{ start, end: start + 60000 }] };
        const marker = { id: 4, timestamp: start + 5000, note: 'Siren', color: '#fdd835', positionId: 'P1', metrics: { P1: { LAeq: 70 } } };
        const csv = app.annotationCsv.buildAnnotationsCsv([marker, { id: 5, timestamp: start, note: '' }], [region],
            { view: { availablePositions: ['P1'] } }, { models: {} });
        const rows = app.annotationCsv.parseCsvRows(csv);
        const row = app.annotationCsv.readSection(rows, 'REGIONS')[0];
        expect(row.start_utc).toBe('2026-09-02T09:57:00.000Z');
        expect(row.end_utc).toBe('2026-09-02T09:58:00.000Z');
        expect(row.timezone).toBe('Europe/London');
        expect(row.start).toBe('2026-09-02 09:57:00.000');
        expect(row.start_local).toBe('2026-09-02 10:57:00.000');
        expect(row).toHaveProperty('data_resolution');
        expect(row).toHaveProperty('source_start_local');
        const markers = app.annotationCsv.readSection(rows, 'MARKERS');
        expect(markers[0]).toMatchObject({ id: '4', timestamp: '2026-09-02 09:57:05.000', timestamp_utc: '2026-09-02T09:57:05.000Z',
            timezone: 'Europe/London', position: 'P1', note: 'Siren' });
        expect(JSON.parse(markers[0].metrics)).toEqual({ P1: { LAeq: 70 } });
        expect(markers[1].position).toBe('');
        const restored = app.annotationCsv.parseAnnotationsCsv(csv);
        expect(restored.markers[0].positionId).toBe('P1');
        expect(restored.markers[1]).not.toHaveProperty('positionId');
        expect(restored.regions).toHaveLength(1);
        expect(restored.regions[0].meterStates).toEqual({ P1: 'present' });
    });

    it('uses GMT in winter, the configured timezone, and subtracts chart offset for source_*_local', () => {
        const winter = Date.UTC(2026, 0, 15, 10, 0, 0);
        const region = { id: 1, positionId: 'P1', areas: [{ start: winter, end: winter + 1000 }] };
        expect(regionsRow(csvFor(region, {})).start_local).toBe('2026-01-15 10:00:00.000');
        expect(regionsRow(csvFor(region, { config: { timezone: 'Europe/Paris' } })).start_local).toBe('2026-01-15 11:00:00.000');
        const state = { view: { availablePositions: ['P1'], positionChartOffsets: { P1: 3600000 } } };
        const row = regionsRow(csvFor(region, {}, state));
        expect(row.start_local).toBe('2026-01-15 10:00:00.000');
        expect(row.source_start_local).toBe('2026-01-15 09:00:00.000');
        const notes = app.annotationCsv.readSection(app.annotationCsv.parseCsvRows(csvFor(region, {})), 'NOTES');
        expect(notes).toContainEqual({ key: 'local_time_zone', value: 'Europe/London' });
    });

    it('labels the metric resolution, reports A-weighted LAeq, and never emits an LZeq broadband label', () => {
        const region = { id: 1, positionId: 'P1', areas: [{ start: 0, end: 2000 }] };
        const logOnly = { timeSeriesSources: { P1: { log: { data: { Datetime: [0, 1000], LAeq: [60, 70] } } } } };
        const both = { timeSeriesSources: { P1: { log: { data: { Datetime: [0, 1000], LAeq: [60, 70] } },
            overview: { data: { Datetime: [0], LAeq: [50] } } } } };
        const overviewOnly = { timeSeriesSources: { P1: { overview: { data: { Datetime: [0, 1000], LAeq: [50, 50] } } } } };
        expect(regionsRow(csvFor(region, logOnly)).data_resolution).toBe('log');
        const preferred = regionsRow(csvFor(region, both));
        expect(preferred.data_resolution).toBe('log');
        expect(Number(preferred.LAeq_dB)).toBeCloseTo(67.4036, 3);
        expect(regionsRow(csvFor(region, overviewOnly)).data_resolution).toBe('overview');
        const header = app.annotationCsv.parseCsvRows(csvFor(region, logOnly)).find(row => row.includes('LAeq_dB'));
        expect(header).not.toContain('metrics_parameter');
        expect(header).toContain('data_resolution');
    });
});

