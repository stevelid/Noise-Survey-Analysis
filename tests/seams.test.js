import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Tests for the WP0 extension points: keymap, layout slice, automation command registry,
// render hooks, and overlay re-sync on y_range change.
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/init.js';
import '../noise_survey_analysis/static/js/chart-classes.js';
import '../noise_survey_analysis/static/js/services/session/sessionManager.js';
import '../noise_survey_analysis/static/js/services/eventHandlers/viewEventHandlers.js';
import '../noise_survey_analysis/static/js/services/eventHandlers.js';
import '../noise_survey_analysis/static/js/app.js';

const app = window.NoiseSurveyApp;

describe('keymap', () => {
    const key = (props) => ({ key: '', ctrlKey: false, altKey: false, shiftKey: false, repeat: false, ...props });

    it('matches every existing shortcut to the intent the old handler used', () => {
        const expectations = [
            [{ key: ' ', code: 'Space' }, 'togglePlayback'],
            [{ key: 'Escape' }, 'escape'],
            [{ key: 'M' }, 'createMarker'],
            [{ key: 'r' }, 'toggleRegionCreation'],
            [{ key: 'n' }, 'focusRegionNote'],
            [{ key: 'b' }, 'returnToPreviousView'],
            [{ key: '[' }, 'stepRegion'],
            [{ key: ']' }, 'stepRegion'],
            [{ key: 'ArrowLeft', ctrlKey: true }, 'arrowNudge'],
            [{ key: 'ArrowRight', altKey: true }, 'arrowNudge'],
            [{ key: 'Delete' }, 'deleteSelection'],
            [{ key: 'Backspace' }, 'deleteSelection'],
            [{ key: '4' }, 'cycleMeterState'],
            [{ key: 'e' }, 'metricEq'],
            [{ key: 'X' }, 'metricFmax'],
            [{ key: 'l' }, 'metricL90'],
            [{ key: 'p' }, 'previewClassification'],
            [{ key: 'z', ctrlKey: true }, 'undo'],
            [{ key: 'y', ctrlKey: true }, 'redo'],
            [{ key: 'Z', ctrlKey: true, shiftKey: true }, 'redoShiftZ'],
            [{ key: 'z', metaKey: true }, 'undo']
        ];
        expectations.forEach(([event, id]) => {
            expect(app.keymap.match(key(event))?.id, JSON.stringify(event)).toBe(id);
        });
    });

    it('keeps the modifier restrictions of the old handler', () => {
        const none = [
            { key: 'n', ctrlKey: true }, { key: 'b', altKey: true }, { key: '[', ctrlKey: true },
            { key: '4', shiftKey: true }, { key: '4', repeat: true }, { key: 'e', shiftKey: true },
            { key: 'e', ctrlKey: true }, { key: 'p', ctrlKey: true }, { key: 'q' }, { key: 'Enter' }
        ];
        none.forEach(event => expect(app.keymap.match(key(event)), JSON.stringify(event)).toBeNull());
    });

    it('registerKeyBindings adds keys, later entries win, and ids replace in place', () => {
        const run = vi.fn();
        expect(app.keymap.registerKeyBindings([
            { id: 'test.zoomIn', keys: ['+', '='], ctrl: false, intent: 'zoomIn', group: 'Navigation', description: 'Zoom in', run },
            { id: 'test.panRight', keys: ['ArrowRight'], shift: true, intent: 'panRight', group: 'Navigation', description: 'Pan', run },
            { keys: [] }
        ])).toBe(2);

        expect(app.keymap.match(key({ key: '+' })).run).toBe(run);
        // More specific later binding overrides the built-in arrow, without touching it.
        expect(app.keymap.match(key({ key: 'ArrowRight', shiftKey: true })).id).toBe('test.panRight');
        expect(app.keymap.match(key({ key: 'ArrowRight' })).id).toBe('arrowNudge');

        const before = app.keymap.getKeyBindings().length;
        app.keymap.registerKeyBindings([{ id: 'test.zoomIn', keys: ['+'], intent: 'zoomIn' }]);
        expect(app.keymap.getKeyBindings().length).toBe(before);
        expect(app.keymap.match(key({ key: '=' }))).toBeNull();

        expect(app.keymap.unregisterKeyBinding('test.zoomIn')).toBe(true);
        expect(app.keymap.unregisterKeyBinding('test.panRight')).toBe(true);
    });

    it('getKeyBindingsForHelp returns grouped rows and hides aliases', () => {
        const rows = app.keymap.getKeyBindingsForHelp();
        expect(rows.length).toBeGreaterThan(10);
        expect(rows.every(row => row.group && row.keys && row.description)).toBe(true);
        expect(rows.find(row => row.id === 'redoShiftZ')).toBeUndefined();
        expect(rows.find(row => row.id === 'togglePlayback').keys).toBe('Space');
    });

    it('handleKeyPress runs the handler of a registered binding', () => {
        const run = vi.fn();
        app.keymap.registerKeyBindings([{ id: 'test.run', keys: ['F9'], intent: 'test', run }]);
        const event = key({ key: 'F9', preventDefault: vi.fn(), target: document.body });
        app.eventHandlers.handleKeyPress(event);
        expect(event.preventDefault).toHaveBeenCalled();
        expect(run).toHaveBeenCalledWith(event, expect.objectContaining({ dispatch: expect.any(Function), getState: expect.any(Function) }));
        app.keymap.unregisterKeyBinding('test.run');
    });
});

describe('layout slice', () => {
    beforeEach(() => {
        app.init.reInitializeStore();
    });

    it('starts with the documented initial state', () => {
        expect(app.store.getState().layout).toEqual({
            positionOrder: null,
            spectrogramMode: {},
            yAxisMode: 'auto',
            fitToWindow: true,
            wheelZoomLock: false,
            frequencyDockOpen: false,
            soloSaved: null
        });
    });

    it('applies the setter actions and ignores invalid input', () => {
        const { dispatch, getState } = app.store;
        dispatch(app.actions.layoutPositionOrderSet(['P2', 'P1']));
        dispatch(app.actions.layoutSpectrogramModeSet('P1', 'strip'));
        dispatch(app.actions.layoutSpectrogramModeSet('P2', 'bogus'));
        dispatch(app.actions.layoutYAxisModeSet('shared'));
        dispatch(app.actions.layoutYAxisModeSet('nonsense'));
        dispatch(app.actions.layoutFitToWindowSet(false));
        dispatch(app.actions.layoutWheelZoomLockSet(true));
        dispatch(app.actions.layoutFrequencyDockOpenSet(true));
        expect(getState().layout).toEqual({
            positionOrder: ['P2', 'P1'],
            spectrogramMode: { P1: 'strip' },
            yAxisMode: 'shared',
            fitToWindow: false,
            wheelZoomLock: true,
            frequencyDockOpen: true,
            soloSaved: null
        });
        dispatch(app.actions.layoutPositionOrderSet(null));
        expect(getState().layout.positionOrder).toBeNull();
    });

    it('does not change the layout object for no-op actions and is not part of undo', () => {
        const before = app.store.getState().layout;
        app.store.dispatch(app.actions.layoutYAxisModeSet('auto'));
        expect(app.store.getState().layout).toBe(before);
    });

    it('selectors resolve order against the available positions', () => {
        const { selectOrderedPositions, selectSpectrogramMode } = app.features.layout.selectors;
        app.store.dispatch(app.actions.layoutPositionOrderSet(['P3', 'PX', 'P1']));
        const state = app.store.getState();
        expect(selectOrderedPositions(state, ['P1', 'P2', 'P3'])).toEqual(['P3', 'P1', 'P2']);
        expect(selectSpectrogramMode(state, 'P1')).toBe('full');
    });

    it('thunk movePositionIntent moves a position within the effective order', () => {
        const dispatch = vi.fn();
        const getState = () => ({ view: { availablePositions: ['P1', 'P2', 'P3'] }, layout: { positionOrder: null } });
        app.thunks.movePositionIntent({ positionId: 'P1', delta: 1 })(dispatch, getState);
        expect(dispatch).toHaveBeenCalledWith(app.actions.layoutPositionOrderSet(['P2', 'P1', 'P3']));
        dispatch.mockClear();
        app.thunks.movePositionIntent({ positionId: 'P1', delta: -1 })(dispatch, getState);
        expect(dispatch).not.toHaveBeenCalled();
    });

    it('survives workspace rehydration', () => {
        app.store.dispatch(app.actions.layoutYAxisModeSet('locked'));
        const saved = JSON.parse(JSON.stringify(app.store.getState()));
        app.init.reInitializeStore();
        expect(app.store.getState().layout.yAxisMode).toBe('auto');
        app.store.dispatch(app.actions.rehydrateState(saved));
        expect(app.store.getState().layout.yAxisMode).toBe('locked');
        // A workspace saved before the slice existed keeps the defaults.
        const { layout, ...legacy } = saved;
        app.store.dispatch(app.actions.rehydrateState(legacy));
        expect(app.store.getState().layout.yAxisMode).toBe('auto');
    });
});

describe('automation command registry', () => {
    // sessionManager attaches its listener once per module load, so keep one fake source and
    // call the captured listener for each command.
    let listener = null;
    let seq = 0;
    const commandSource = { data: {}, change: { connect: (fn) => { listener = fn; } } };
    const resultSource = { data: {}, change: { emit: vi.fn() } };

    const send = (command, payload) => {
        app.registry = app.registry || {};
        app.registry.models = {
            ...(app.registry.models || {}),
            automationCommandSource: commandSource,
            automationResultSource: resultSource
        };
        seq += 1;
        commandSource.data = {
            request_id: [`seam-req-${seq}`],
            command: [command],
            payload: [JSON.stringify(payload || {})]
        };
        if (listener) listener(); else app.session.ensureAutomationBridge();
        return resultSource.data;
    };

    it('exposes registerAutomationCommand and returns handler data to Python', () => {
        expect(typeof app.session.registerAutomationCommand).toBe('function');
        const handler = vi.fn(() => ({ success: true, message: 'Counted.', data: { count: 3 } }));
        app.session.registerAutomationCommand('test_count', handler);
        const result = send('test_count', { a: 1 });
        expect(handler).toHaveBeenCalledWith({ a: 1 }, expect.objectContaining({ dispatch: expect.any(Function), getState: expect.any(Function) }));
        expect(result.success).toEqual([true]);
        expect(JSON.parse(result.data[0])).toEqual({ count: 3 });
        expect(result.message).toEqual(['Counted.']);
    });

    it('still serves the original commands through the registry', () => {
        const handleParameterChange = vi.fn();
        app.services = app.services || {};
        app.services.eventHandlers = app.services.eventHandlers || {};
        app.services.eventHandlers.view = { handleParameterChange };
        const result = send('set_parameter', { value: 'LAFmax' });
        expect(handleParameterChange).toHaveBeenCalledWith('LAFmax');
        expect(result.success).toEqual([true]);
    });

    it('reports success:false and thrown errors as failed results', () => {
        app.session.registerAutomationCommand('test_soft_fail', () => ({ success: false, message: 'Nope' }));
        app.session.registerAutomationCommand('test_throws', () => { throw new Error('Boom'); });
        const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});

        let result = send('test_soft_fail');
        expect(result.success).toEqual([false]);
        expect(result.message).toEqual(['Nope']);

        result = send('test_throws');
        expect(result.success).toEqual([false]);
        expect(result.message).toEqual(['Boom']);

        result = send('test_unknown_command');
        expect(result.success).toEqual([false]);
        expect(result.message[0]).toContain("Unsupported automation command 'test_unknown_command'");
        consoleError.mockRestore();
    });

    it('rejects invalid registrations', () => {
        expect(() => app.session.registerAutomationCommand('', () => {})).toThrow();
        expect(() => app.session.registerAutomationCommand('x', null)).toThrow();
    });
});

describe('render hooks', () => {
    beforeEach(() => {
        app.renderers = {
            renderViewport: vi.fn(), renderPrimaryCharts: vi.fn(), renderFrequencyBar: vi.fn(), renderOverlays: vi.fn(),
            renderControlWidgets: vi.fn(), renderMarkers: vi.fn(), renderRegions: vi.fn(), renderClassifications: vi.fn(),
            renderSidePanel: vi.fn(), renderActiveTool: vi.fn()
        };
        app.data_processors = {
            updateActiveData: vi.fn().mockReturnValue({}),
            calculateStepSize: vi.fn().mockReturnValue(1000),
            updateActiveFreqBarData: vi.fn()
        };
        app.registry = {
            initialize: vi.fn().mockReturnValue({ availablePositions: ['P1'], selectedParameter: 'LAeq', viewport: { min: 0, max: 1000 }, chartVisibility: {}, hoverEnabled: true }),
            models: { audio_status_source: { patching: { connect: vi.fn() } }, audio_control_source: { data: {} } },
            controllers: { positions: {}, chartsByName: new Map() }
        };
        app.eventHandlers = { ...app.eventHandlers, handleAudioStatusUpdate: vi.fn(), handleKeyPress: vi.fn() };
    });

    afterEach(() => { vi.restoreAllMocks(); });

    it('calls registered hooks after a state change with the previous state', () => {
        const hook = vi.fn();
        app.registerRenderHook('test.hook', hook);
        app.init.initialize({});
        hook.mockClear();

        app.store.dispatch(app.actions.layoutYAxisModeSet('locked'));
        expect(hook).toHaveBeenCalledTimes(1);
        const [state, info] = hook.mock.calls[0];
        expect(state.layout.yAxisMode).toBe('locked');
        expect(info.prev.layout.yAxisMode).toBe('auto');
        expect(info).toHaveProperty('isInitialLoad', false);
        expect(info).toHaveProperty('models');
    });

    it('replaces a hook registered under the same name and isolates a throwing hook', () => {
        const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
        const first = vi.fn();
        const second = vi.fn();
        const failing = vi.fn(() => { throw new Error('hook failed'); });
        app.registerRenderHook('test.replace', first);
        app.registerRenderHook('test.replace', second);
        app.registerRenderHook('test.failing', failing);
        app.init.initialize({});
        first.mockClear();
        second.mockClear();

        app.store.dispatch(app.actions.layoutFitToWindowSet(false));
        expect(first).not.toHaveBeenCalled();
        expect(second).toHaveBeenCalled();
        expect(failing).toHaveBeenCalled();
        expect(consoleError.mock.calls.some(([message]) => String(message).includes('renderHook:test.failing'))).toBe(true);
        // Registered hooks must not leak into other tests.
        app.registerRenderHook('test.replace', () => {});
        app.registerRenderHook('test.failing', () => {});
        app.registerRenderHook('test.hook', () => {});
    });
});

describe('overlay re-sync on y_range change', () => {
    it('rebuilds region, marker and classification overlays when y_range start/end change', () => {
        const MockSource = function (props = {}) { this.data = props.data || {}; this.change = { emit: vi.fn() }; };
        const doc = {
            add_model: vi.fn(model => model),
            create_model: (type, props) => (type === 'ColumnDataSource' ? new MockSource(props) : { type, ...props, visible: props.visible })
        };
        window.Bokeh = {
            documents: [doc],
            Models: { get: vi.fn(name => (['ColumnDataSource', 'Quad', 'Segment', 'GlyphRenderer', 'LabelSet', 'CustomJS', 'HoverTool'].includes(name)
                ? function (props = {}) { Object.assign(this, props); this.change = { emit: vi.fn() }; } : null)) }
        };

        const listeners = [];
        const yRange = { start: 0, end: 10, change: { connect: (fn) => listeners.push(fn) } };
        const chartModel = {
            name: 'figure_P1_timeseries',
            add_glyph: vi.fn(function (glyph, source) { const renderer = { glyph, data_source: source, visible: false }; this.renderers.push(renderer); return renderer; }),
            renderers: [],
            request_render: vi.fn(),
            x_range: { start: 0, end: 100 },
            y_range: yRange
        };
        const chart = new app.classes.Chart(chartModel, { change: { emit: vi.fn() } }, {}, {}, 'P1');

        chart.syncRegions([{ id: 1, positionId: 'P1', start: 10, end: 20 }], 1);
        chart.syncMarkers([{ id: 4, timestamp: 15 }], true, 4);
        expect(chart.regionOverlay.source.data.bottom).toEqual([0]);
        expect(chart.regionOverlay.source.data.top).toEqual([10]);
        expect(chart.markerOverlay.source.data.y1).toEqual([10]);
        expect(listeners).toHaveLength(1);

        yRange.start = 40;
        yRange.end = 75;
        listeners.forEach(fn => fn());

        expect(chart.regionOverlay.source.data.bottom).toEqual([40]);
        expect(chart.regionOverlay.source.data.top).toEqual([75]);
        expect(chart.markerOverlay.source.data.y0).toEqual([40]);
        expect(chart.markerOverlay.source.data.y1).toEqual([75]);

        // A change event that leaves start/end alone does nothing.
        const spy = vi.spyOn(chart, 'syncRegions');
        listeners.forEach(fn => fn());
        expect(spy).not.toHaveBeenCalled();
    });
});
