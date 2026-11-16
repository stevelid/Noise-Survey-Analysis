import { describe, it, expect, vi, beforeAll } from 'vitest';
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/features/regions/annotationMetrics.js';
import '../noise_survey_analysis/static/js/services/session/annotationCsv.js';
import '../noise_survey_analysis/static/js/services/session/sessionManager.js';

let helpers;
beforeAll(() => { helpers = window.NoiseSurveyApp.session.__testHelpers; });

function fakeTimers() {
    let now = 0;
    let next = 1;
    const timers = new Map();
    return {
        now: () => now,
        setTimer: (fn, ms) => { const id = next++; timers.set(id, { fn, at: now + ms }); return id; },
        clearTimer: id => { timers.delete(id); },
        advance(ms) {
            const target = now + ms;
            for (;;) {
                const due = [...timers.entries()].filter(([, t]) => t.at <= target).sort((a, b) => a[1].at - b[1].at)[0];
                if (!due) break;
                now = due[1].at;
                timers.delete(due[0]);
                due[1].fn();
            }
            now = target;
        },
    };
}

describe('autosave scheduler', () => {
    it('waits 2 s after the last change', () => {
        const t = fakeTimers();
        const flush = vi.fn();
        const s = helpers.createAutosaveScheduler({ flush, ...t });
        s.notify();
        t.advance(1500);
        s.notify();
        t.advance(1500);
        expect(flush).not.toHaveBeenCalled();
        t.advance(600);
        expect(flush).toHaveBeenCalledTimes(1);
    });

    it('flushes at the 15 s maximum wait under a steady stream of changes', () => {
        const t = fakeTimers();
        const flush = vi.fn();
        const s = helpers.createAutosaveScheduler({ flush, ...t });
        for (let i = 0; i < 20; i += 1) { s.notify(); t.advance(1000); }
        expect(flush.mock.calls.length).toBeGreaterThanOrEqual(1);
        expect(flush.mock.calls.length).toBeLessThanOrEqual(2);
    });

    it('flushNow runs only when a change is pending', () => {
        const t = fakeTimers();
        const flush = vi.fn();
        const s = helpers.createAutosaveScheduler({ flush, ...t });
        s.flushNow();
        expect(flush).not.toHaveBeenCalled();
        s.notify();
        s.flushNow();
        expect(flush).toHaveBeenCalledTimes(1);
        t.advance(5000);
        expect(flush).toHaveBeenCalledTimes(1);
    });
});

describe('selectPersistableState', () => {
    const state = {
        view: { availablePositions: ['P1'], positionChartOffsets: { P1: 5000 }, notice: { text: 'x' },
            regionJumpHistory: [1], regionNoteFocusRequestId: 4, selectedParameter: 'LAeq' },
        interaction: { hover: { isActive: true } },
        audio: { isPlaying: true },
        system: { lastAction: {} },
        markers: { byId: { 1: { id: 1 } }, allIds: [1] },
        regions: { byId: { 1: { id: 1 } }, allIds: [1], metricsRevision: 9, isMergeModeActive: true, addAreaTargetId: 3 },
        layout: { positionOrder: ['P1'] },
        annotationPanel: { clearMarkersPending: true, filters: {} },
        classifications: { byId: {}, allIds: [] },
    };

    it('drops hover, audio, system and one-shot signals but keeps annotations, layout and offsets', () => {
        const persisted = window.NoiseSurveyApp.session.selectPersistableState(state);
        expect(persisted.interaction).toBeUndefined();
        expect(persisted.audio).toBeUndefined();
        expect(persisted.system).toBeUndefined();
        expect(persisted.view.notice).toBeUndefined();
        expect(persisted.view.regionJumpHistory).toBeUndefined();
        expect(persisted.view.positionChartOffsets).toEqual({ P1: 5000 });
        expect(persisted.view.selectedParameter).toBe('LAeq');
        expect(persisted.regions.metricsRevision).toBeUndefined();
        expect(persisted.regions.byId[1]).toEqual({ id: 1 });
        expect(persisted.markers.allIds).toEqual([1]);
        expect(persisted.layout.positionOrder).toEqual(['P1']);
        expect(persisted.annotationPanel.clearMarkersPending).toBeUndefined();
    });

    it('does not mutate the store state', () => {
        window.NoiseSurveyApp.session.selectPersistableState(state);
        expect(state.view.notice).toEqual({ text: 'x' });
        expect(state.interaction).toBeDefined();
    });

    it('watches only annotation, layout and offset slices', () => {
        const a = helpers.autosaveWatchedRefs(state);
        const b = helpers.autosaveWatchedRefs({ ...state, interaction: { hover: { isActive: false } }, audio: {} });
        expect(a).toEqual(b);
        expect(a.every((ref, i) => ref === b[i])).toBe(true);
    });
});

describe('what counts as a user change (no write at startup)', () => {
    const s = { regions: { byId: {}, allIds: [], categories: {} }, markers: { byId: {}, allIds: [] }, layout: {},
        view: { positionChartOffsets: {}, positionAudioOffsets: {}, positionDisplayTitles: {} }, classifications: { byId: {} } };
    const refs = state => helpers.autosaveWatchedRefs(state);
    it('ignores init and early layout set-up', () => {
        const next = { ...s, layout: { fit: true } };
        expect(helpers.isUserAutosaveChange(refs(s), refs(next), 'INITIALIZE_STATE', 10)).toBe(false);
        expect(helpers.isUserAutosaveChange(refs(s), refs(next), 'layout/spectrogramModeSet', 500)).toBe(false);
        expect(helpers.isUserAutosaveChange(refs(s), refs(next), 'view/someInit', 9000)).toBe(false);
    });
    it('counts annotation, offset and later layout changes', () => {
        const withRegion = { ...s, regions: { ...s.regions, byId: { 1: {} } } };
        expect(helpers.isUserAutosaveChange(refs(s), refs(withRegion), 'regions/regionAdded', 10)).toBe(true);
        const offset = { ...s, view: { ...s.view, positionChartOffsets: { P1: 1 } } };
        expect(helpers.isUserAutosaveChange(refs(s), refs(offset), 'view/positionChartOffsetSet', 10)).toBe(true);
        const layout = { ...s, layout: { positionOrder: ['a'] } };
        expect(helpers.isUserAutosaveChange(refs(s), refs(layout), 'layout/positionOrderSet', 9000)).toBe(true);
    });
});

describe('autosave status and static decode', () => {
    it('ignores non-autosave tags and accepts autosave ones', () => {
        expect(helpers.handleAutosaveStatus('r', 'info', 'm', '')).toBe(false);
        expect(helpers.handleAutosaveStatus('r', 'info', 'Saved', 'autosave:ok:3:2026-11-15T12:04:00+00:00')).toBe(true);
    });

    it('decodes uint8 codes (integer grid -> Int16, half-dB grid -> Float32)', () => {
        const ints = helpers.decodeQuantizedLevels(new Uint8Array([0, 5, 255]), 20, 1);
        expect(ints).toBeInstanceOf(Int16Array);
        expect(Array.from(ints)).toEqual([20, 25, 275]);
        const halves = helpers.decodeQuantizedLevels(new Uint8Array([0, 1, 3]), 10.5, 0.5);
        expect(Array.from(halves)).toEqual([10.5, 11, 12]);
    });

    it('decodeStaticPayload decodes log sources in place and aliases the shared parameter lazily', () => {
        const models = {
            spectrogramSources: { P1: { log: { data: {
                parameter: ['LZeq'], quant_offset_db: [30], quant_step_db: [1],
                levels_flat_transposed: [new Uint8Array([0, 1, 2])], times_ms: [new Float64Array([1, 2, 3])] } } } },
            preparedGlyphData: { P1: { log: { prepared_params: {
                LZeq: { shared_with_log_source: true, levels_flat_transposed: null, times_ms: null },
                LAeq: { levels_flat_transposed: new Uint8Array([0, 4]), quant_offset_db: 40, quant_step_db: 1 } } } } },
        };
        window.NoiseSurveyApp.session.decodeStaticPayload(models);
        expect(Array.from(models.spectrogramSources.P1.log.data.levels_flat_transposed[0])).toEqual([30, 31, 32]);
        const params = models.preparedGlyphData.P1.log.prepared_params;
        expect(Array.from(params.LZeq.levels_flat_transposed)).toEqual([30, 31, 32]);
        expect(Array.from(params.LZeq.times_ms)).toEqual([1, 2, 3]);
        expect(Array.from(params.LAeq.levels_flat_transposed)).toEqual([40, 44]);
        window.NoiseSurveyApp.session.decodeStaticPayload(models); // idempotent
        expect(Array.from(models.spectrogramSources.P1.log.data.levels_flat_transposed[0])).toEqual([30, 31, 32]);
    });
});
