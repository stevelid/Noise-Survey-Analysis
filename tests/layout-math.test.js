import { describe, it, expect, vi } from 'vitest';
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/services/layout/layoutMath.js';
import '../noise_survey_analysis/static/js/features/navigation/navThunks.js';
import '../noise_survey_analysis/static/js/services/wheelController.js';
import '../noise_survey_analysis/static/js/services/helpOverlay.js';

const app = window.NoiseSurveyApp;
const m = app.layoutMath;

describe('zoom and pan maths', () => {
    const bounds = { min: 0, max: 1000000 };

    it('zooms in around the anchor keeping its relative position', () => {
        const next = m.zoomRange({ min: 100000, max: 200000 }, 0.5, 150000, bounds, 1000);
        expect(next.max - next.min).toBe(50000);
        expect(next.min).toBe(125000);
    });

    it('zooms about the centre when the anchor is outside the window', () => {
        const next = m.zoomRange({ min: 100000, max: 200000 }, 0.5, 900000, bounds, 1000);
        expect(next).toEqual({ min: 125000, max: 175000 });
    });

    it('clamps zoom-out to the data range and zoom-in to the minimum interval', () => {
        expect(m.zoomRange({ min: 0, max: 800000 }, 2, 400000, bounds, 1000)).toEqual({ min: 0, max: 1000000 });
        const tiny = m.zoomRange({ min: 5000, max: 6500 }, 0.1, 5500, bounds, 1000);
        expect(tiny.max - tiny.min).toBe(1000);
    });

    it('shifts a window that would leave the bounds instead of squeezing it', () => {
        expect(m.clampRange(-500, 1500, bounds, 1000)).toEqual({ min: 0, max: 2000 });
        expect(m.clampRange(999000, 1001000, bounds, 1000)).toEqual({ min: 998000, max: 1000000 });
    });

    it('pans by a fraction of the window and stops at the edges', () => {
        expect(m.panRange({ min: 100000, max: 200000 }, 0.25, bounds)).toEqual({ min: 125000, max: 225000 });
        expect(m.panRange({ min: 10000, max: 110000 }, -0.5, bounds)).toEqual({ min: 0, max: 100000 });
        expect(m.panRange({ min: 900000, max: 1000000 }, 0.5, bounds)).toEqual({ min: 900000, max: 1000000 });
    });

    it('pads the extent of region areas', () => {
        expect(m.paddedExtent([{ start: 1000, end: 2000 }, { start: 3000, end: 5000 }], 0.1)).toEqual({ min: 600, max: 5400 });
        expect(m.paddedExtent([], 0.1)).toBeNull();
    });
});

describe('fit to window', () => {
    const three = ['P1', 'P2', 'P3'].map(id => ({ id, specMode: 'full' }));

    it('splits a 1920x1000 budget across 3 positions and fills it exactly', () => {
        const result = m.computeFit({ budget: 810, positions: three });
        expect(result.fits).toBe(true);
        const total = Object.values(result.heights).reduce((sum, h) => sum + h.ts + h.spec, 0);
        expect(total).toBe(810);
        expect(result.heights.P2.ts).toBeGreaterThanOrEqual(110);
        expect(result.heights.P2.spec).toBeGreaterThanOrEqual(80);
    });

    it('gives the time series the space of a collapsed spectrogram, keeping a 26 px strip', () => {
        const positions = [{ id: 'P1', specMode: 'strip' }, { id: 'P2', specMode: 'full' }, { id: 'P3', specMode: 'full' }];
        const result = m.computeFit({ budget: 810, positions });
        expect(result.heights.P1.spec).toBe(26);
        expect(result.heights.P1.ts).toBeGreaterThan(result.heights.P2.ts);
        const total = Object.values(result.heights).reduce((sum, h) => sum + h.ts + h.spec, 0);
        expect(total).toBe(810);
    });

    it('hidden spectrograms take no height', () => {
        const result = m.computeFit({ budget: 400, positions: [{ id: 'P1', specMode: 'hidden' }, { id: 'P2', specMode: 'hidden' }] });
        expect(result.fits).toBe(true);
        expect(result.heights.P1.spec).toBe(0);
    });

    it('falls back to fixed heights (page scrolls) when rows would be too small', () => {
        const five = ['A', 'B', 'C', 'D', 'E'].map(id => ({ id, specMode: 'full' }));
        const result = m.computeFit({ budget: 810, positions: five });
        expect(result.fits).toBe(false);
        expect(result.heights.A).toEqual({ ts: 220, spec: 160 });
    });
});

describe('y auto-fit', () => {
    it('pads 3 dB, rounds out to 5 dB and keeps at least 20 dB', () => {
        expect(m.targetYRange({ min: 41.2, max: 63.9 })).toEqual({ start: 35, end: 70 });
        expect(m.targetYRange({ min: 50, max: 52 })).toEqual({ start: 40, end: 60 });
        expect(m.targetYRange(null)).toBeNull();
    });

    it('only moves when data leaves the window or it is much too wide', () => {
        const current = { start: 35, end: 70 };
        expect(m.nextYRange(current, { min: 42, max: 60 })).toBeNull();
        expect(m.nextYRange(current, { min: 42, max: 75 })).toEqual({ start: 35, end: 80 });
        expect(m.nextYRange({ start: 20, end: 100 }, { min: 45, max: 55 })).toEqual({ start: 40, end: 60 });
        expect(m.nextYRange(null, { min: 45, max: 55 })).toEqual({ start: 40, end: 60 });
    });

    it('computes the visible extent of the requested columns inside the viewport only', () => {
        const data = { Datetime: [0, 10, 20, 30, 40], LAeq: [50, 40, NaN, 70, 90], LAFmax: [60, 65, 66, 67, 99] };
        expect(m.visibleExtent(data, ['LAeq', 'LAFmax'], 10, 30)).toEqual({ min: 40, max: 70 });
        expect(m.visibleExtent(data, ['LAeq'], 100, 200)).toBeNull();
        expect(m.visibleExtent({}, ['LAeq'], 0, 1)).toBeNull();
    });

    it('unions extents for the shared mode', () => {
        expect(m.unionExtent([{ min: 40, max: 50 }, null, { min: 35, max: 45 }])).toEqual({ min: 35, max: 50 });
    });
});

describe('mode cycles and labels', () => {
    it('cycles spectrogram and y modes', () => {
        expect(m.cycleSpectrogramMode('full')).toBe('strip');
        expect(m.cycleSpectrogramMode('strip')).toBe('full');
        expect(m.cycleSpectrogramMode('hidden')).toBe('full');
        expect(['auto', 'shared', 'locked', 'auto'].map((x, i, a) => m.cycleYMode(a[i - 1] || 'locked'))).toEqual(['auto', 'shared', 'locked', 'auto']);
    });

    it('puts the time labels under the lowest visible chart', () => {
        expect(m.timeLabelChart('full', true)).toBe('spectrogram');
        expect(m.timeLabelChart('strip', true)).toBe('timeseries');
        expect(m.timeLabelChart('full', false)).toBe('timeseries');
        expect(m.timeLabelChart('hidden', true)).toBe('timeseries');
    });

    it('steps focus without wrapping', () => {
        expect(m.stepIndex(3, 0, -1)).toBe(0);
        expect(m.stepIndex(3, 2, 1)).toBe(2);
        expect(m.stepIndex(3, -1, 1)).toBe(0);
    });
});

describe('wheel decision', () => {
    const decide = app.services.wheelController.decideWheelAction;
    it('zooms when the page does not scroll, with Ctrl, or locked; scrolls otherwise; Shift pans', () => {
        expect(decide({ pageScrolls: false })).toBe('zoom');
        expect(decide({ pageScrolls: true })).toBe('scroll');
        expect(decide({ pageScrolls: true, ctrl: true })).toBe('zoom');
        expect(decide({ pageScrolls: true, locked: true })).toBe('zoom');
        expect(decide({ pageScrolls: true, shift: true })).toBe('pan');
        expect(decide({ pageScrolls: false, shift: true })).toBe('pan');
    });
});

describe('navigation thunks', () => {
    function setup(viewport = { min: 100000, max: 200000 }) {
        const state = {
            view: { availablePositions: ['P1', 'P2', 'P3'], viewport, chartVisibility: {} },
            layout: { positionOrder: null, spectrogramMode: {} },
            interaction: { tap: { isActive: false } }, audio: {}
        };
        app.registry = app.registry || { models: {}, controllers: { positions: {} } };
        app.registry.models = app.registry.models || {};
        // thunks.js loads before navThunks.js in this test; the bundle order does the merge itself.
        app.thunks = { ...app.thunks, ...app.features.layout.thunks };
        app.registry.models.charts = [{ x_range: { bounds: [0, 1000000], min_interval: 1000, start: 0, end: 1 } }];
        const dispatch = vi.fn();
        app.thunks.handleViewportChangeIntent = vi.fn((payload) => ({ type: 'vp', payload }));
        return { state, dispatch, getState: () => state };
    }

    it('zoomIntent commits a clamped viewport through the viewport thunk', () => {
        const { dispatch, getState } = setup();
        app.thunks.zoomIntent({ factor: 0.5 })(dispatch, getState);
        expect(app.thunks.handleViewportChangeIntent).toHaveBeenCalledWith({ min: 125000, max: 175000 });
    });

    it('panIntent and fitAllIntent respect the bounds', () => {
        const { dispatch, getState } = setup({ min: 900000, max: 1000000 });
        app.thunks.panIntent({ fraction: 0.5 })(dispatch, getState);
        expect(app.thunks.handleViewportChangeIntent).not.toHaveBeenCalled();
        app.thunks.fitAllIntent()(dispatch, getState);
        expect(app.thunks.handleViewportChangeIntent).toHaveBeenCalledWith({ min: 0, max: 1000000 });
    });

    it('focus steps through the displayed order and Alt+arrow moves the focused position', () => {
        const { state, dispatch, getState } = setup();
        app.layoutRuntime.focusedPositionId = null;
        app.thunks.focusPositionIntent({ delta: 1 })(dispatch, getState);
        expect(app.layoutRuntime.focusedPositionId).toBe('P2');
        app.thunks.moveFocusedPositionIntent({ delta: -1 })(dispatch, getState);
        expect(dispatch).toHaveBeenCalled();
        void state;
    });

    it('cycleSpectrogramModeIntent dispatches the next mode', () => {
        const { dispatch, getState } = setup();
        app.thunks.cycleSpectrogramModeIntent({ positionId: 'P2' })(dispatch, getState);
        expect(dispatch).toHaveBeenCalledWith(app.actions.layoutSpectrogramModeSet('P2', 'strip'));
    });
});

describe('help overlay', () => {
    it('is generated from the keymap and closes on Esc', () => {
        app.keymap.registerKeyBindings([{ id: 'test.help', keys: ['q'], group: 'Tests', description: 'Registered later', intent: 'x' }]);
        const html = app.services.helpOverlay.buildHtml();
        expect(html).toContain('Registered later');
        expect(html).toContain('Mouse');
        app.services.helpOverlay.open();
        expect(document.querySelector('.nsa-help-overlay')).not.toBeNull();
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        expect(document.querySelector('.nsa-help-overlay')).toBeNull();
        app.keymap.unregisterKeyBinding('test.help');
    });
});
