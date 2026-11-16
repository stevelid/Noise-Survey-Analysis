import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/services/layout/layoutMath.js';
import '../noise_survey_analysis/static/js/features/navigation/navThunks.js';
import '../noise_survey_analysis/static/js/services/wheelController.js';
import '../noise_survey_analysis/static/js/services/helpOverlay.js';
import '../noise_survey_analysis/static/js/services/eventHandlers/viewEventHandlers.js';
import '../noise_survey_analysis/static/js/services/eventHandlers.js';
import '../noise_survey_analysis/static/js/features/regions/annotationMetrics.js';
import '../noise_survey_analysis/static/js/services/session/annotationCsv.js';
import '../noise_survey_analysis/static/js/services/session/sessionManager.js';

const app = window.NoiseSurveyApp;

describe('Solo (O) keeps its restore state in the layout slice', () => {
    const reducer = app.features.layout.layoutReducer;
    const setType = app.features.layout.constants.LAYOUT_SOLO_SAVED_SET;

    it('the reducer stores and clears the saved visibility', () => {
        const saved = { figure_P1_timeseries: true, figure_P2_timeseries: true };
        let layout = reducer(undefined, { type: setType, payload: { saved } });
        expect(layout.soloSaved).toEqual(saved);
        expect(reducer(layout, { type: setType, payload: { saved: null } }).soloSaved).toBeNull();
        expect(reducer(layout, { type: setType, payload: { saved: 'nope' } })).toBe(layout);
    });

    it('O hides the others, and a second O (even after a reload) restores from the slice', () => {
        let state = {
            view: { chartVisibility: { figure_P1_timeseries: true, figure_P2_timeseries: true }, availablePositions: ['P1', 'P2'] },
            layout: { positionOrder: null, spectrogramMode: {}, soloSaved: null },
        };
        app.layoutRuntime.resolveFocus = () => 'P1';
        const dispatch = vi.fn(action => {
            if (action.type === setType) state = { ...state, layout: reducer(state.layout, action) };
            else if (action.type === app.actionTypes.VISIBILITY_CHANGE) {
                const { chartName, isVisible } = action.payload;
                state = { ...state, view: { ...state.view, chartVisibility: { ...state.view.chartVisibility, [chartName]: isVisible } } };
            }
        });
        app.features.layout.thunks.soloPositionIntent()(dispatch, () => state);
        expect(state.view.chartVisibility).toEqual({ figure_P1_timeseries: true, figure_P2_timeseries: false });
        expect(state.layout.soloSaved).toEqual({ figure_P1_timeseries: true, figure_P2_timeseries: true });
        // "Reload": the runtime is gone but the layout slice persisted.
        app.features.layout.thunks.soloPositionIntent()(dispatch, () => state);
        expect(state.layout.soloSaved).toBeNull();
        expect(state.view.chartVisibility).toEqual({ figure_P1_timeseries: true, figure_P2_timeseries: true });
    });
});

describe('help overlay swallows keys for the app', () => {
    afterEach(() => app.services.helpOverlay.close());

    it('letters and arrows never reach the document handler while it is open; Esc closes it', () => {
        const seen = vi.fn();
        document.addEventListener('keydown', seen);
        app.services.helpOverlay.open();
        document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'o', bubbles: true }));
        document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
        expect(seen).not.toHaveBeenCalled();
        expect(app.services.helpOverlay.isOpen()).toBe(true);
        document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        expect(app.services.helpOverlay.isOpen()).toBe(false);
        document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'o', bubbles: true }));
        expect(seen).toHaveBeenCalledTimes(1);
        document.removeEventListener('keydown', seen);
    });
});

describe('Ctrl+S inside a text field', () => {
    beforeEach(() => {
        app.store = { dispatch: vi.fn(), getState: () => ({}) };
    });

    it('saves and blurs the field instead of opening the browser Save dialog', () => {
        const run = vi.fn();
        app.keymap.registerKeyBindings([{ id: 'saveWorkspaceNow', keys: ['s'], ctrl: true, alt: false, shift: false,
            intent: 'saveWorkspaceNow', group: 'Edit', description: 'Save', run }]);
        const blur = vi.fn();
        const preventDefault = vi.fn();
        app.eventHandlers.handleKeyPress({ key: 's', ctrlKey: true, altKey: false, shiftKey: false, preventDefault,
            target: { tagName: 'TEXTAREA', blur, isContentEditable: false } });
        expect(preventDefault).toHaveBeenCalled();
        expect(blur).toHaveBeenCalled();
        expect(run).toHaveBeenCalledTimes(1);
        app.keymap.unregisterKeyBinding('saveWorkspaceNow');
    });
});

describe('wheel scheme tolerance', () => {
    it('a 3 px fit overflow does not turn the wheel into page scroll', () => {
        const doc = document.documentElement;
        Object.defineProperty(doc, 'scrollHeight', { configurable: true, value: 1003 });
        Object.defineProperty(window, 'innerHeight', { configurable: true, value: 1000 });
        expect(app.services.wheelController.pageScrolls()).toBe(false);
        Object.defineProperty(doc, 'scrollHeight', { configurable: true, value: 1010 });
        expect(app.services.wheelController.pageScrolls()).toBe(true);
        delete doc.scrollHeight;
    });
});

describe('static page storage', () => {
    const helpers = () => app.session.__testHelpers;
    let store;

    beforeEach(() => {
        store = {};
        vi.stubGlobal('localStorage', {
            getItem: key => (key in store ? store[key] : null),
            setItem: (key, value) => { store[key] = String(value); },
        });
        Object.defineProperty(window, 'localStorage', { configurable: true, value: globalThis.localStorage });
        app.store = { getState: () => ({ regions: { byId: {}, allIds: [] }, markers: { byId: {}, allIds: [] }, view: {}, layout: {} }) };
    });

    afterEach(() => {
        document.head.querySelectorAll('meta[name="nsa-export-id"]').forEach(node => node.remove());
        vi.unstubAllGlobals();
    });

    it('keys saved edits on the export id baked into the page', () => {
        app.registry = { models: { config: { static_document: true }, jobNumber: '6645' } };
        const meta = document.createElement('meta');
        meta.name = 'nsa-export-id';
        meta.content = 'abc123def456';
        document.head.appendChild(meta);
        expect(helpers().flushAutosave()).toBe(true);
        expect(Object.keys(store)).toHaveLength(1);
        expect(Object.keys(store)[0].endsWith('6645:abc123def456')).toBe(true);
        meta.content = 'newerexport00';
        helpers().flushAutosave();
        expect(Object.keys(store)).toHaveLength(2);
    });

    it('a live page without a session-action source yet is not treated as static', () => {
        app.registry = { models: { config: { static_document: false }, jobNumber: '6645' } };
        expect(helpers().flushAutosave()).toBe(false);
        expect(Object.keys(store)).toHaveLength(0);
    });

    it('the pagehide flush is marked final so a reloaded tab can adopt it', () => {
        const actionSource = { data: {} };
        app.registry = { models: { config: { static_document: false }, jobNumber: '6645', sessionActionSource: actionSource } };
        helpers().flushAutosave({ final: true });
        expect(actionSource.data.command).toEqual(['autosave_workspace']);
        expect(actionSource.data.payload[0].final).toBe(true);
        helpers().flushAutosave();
        expect(actionSource.data.payload[0].final).toBeUndefined();
    });
});
