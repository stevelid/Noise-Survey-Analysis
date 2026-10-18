import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/features/annotations/panelSelectors.js';
import '../noise_survey_analysis/static/js/features/annotations/panelThunks.js';
import '../noise_survey_analysis/static/js/services/panels/htmlPanelEvents.js';
import '../noise_survey_analysis/static/js/services/panels/htmlPanelRenderer.js';

const app = window.NoiseSurveyApp;
const feature = app.features.annotationPanel;
const renderer = app.services.htmlPanelRenderer;
const events = app.services.htmlPanelEvents;
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
let host, root, models, originalMetrics;

function setupDom() {
    host = document.createElement('div');
    root = host.attachShadow({ mode: 'open' }); document.body.appendChild(host);
    let text = '';
    const model = { id: 'html-panel-test' };
    Object.defineProperty(model, 'text', { get: () => text, set: value => { text = value; root.innerHTML = value; } });
    models = { htmlSidePanel: model, htmlSidePanelRoot: root };
    app.registry = { models };
    events.attach(models);
    renderer.render(app.store.getState(), models, app.dataCache);
    app.store.subscribe(() => renderer.render(app.store.getState(), models, app.dataCache));
}

describe('HTML annotation panel', () => {
    beforeEach(() => {
        const base = app.createInitialState();
        base.view.availablePositions = ['P1', 'P2'];
        base.view.positionDisplayTitles = { P1: 'Garden', P2: 'Roadside' };
        app.store = app.createStore((state, action) => {
            const next = app.rootReducer(state || base, action);
            return { ...next, annotationPanel: feature.reducer(state?.annotationPanel, action) };
        });
        app.store.dispatch(app.actions.regionsAdded([{ id: 1, positionId: 'P1', start: 1000, end: 2000, note: 'Dog bark', categoryId: 'dog-bark', meterStates: { P1: 'present', P2: 'unchecked' } }]));
        app.store.dispatch(app.actions.regionSelect(1));
        app.dataCache = {};
        originalMetrics = app.regions.getRegionMetrics;
        app.regions.getRegionMetrics = vi.fn(() => ({ laeq: 45, lafmax: 55, la90: 38, dataResolution: 'log', spectrum: { labels: ['63 Hz'], values: [32] } }));
    });
    afterEach(() => { events.dispose(); host?.remove(); app.regions.getRegionMetrics = originalMetrics; vi.restoreAllMocks(); });

    it('escapes text and rejects CSS injection in user colours', () => {
        const state = structuredClone(app.store.getState());
        state.regions.byId[1].note = '<img src=x onerror="bad()"> & notes';
        state.regions.byId[1].color = 'red;position:fixed';
        state.view.positionDisplayTitles.P2 = '<script>bad()</script>';
        state.regions.categories.byId['dog-bark'].label = 'Dogs " & <b>';
        const html = renderer.buildHtml(state, {}, {});
        const template = document.createElement('template'); template.innerHTML = html;
        expect(template.content.querySelector('script,img')).toBeNull();
        expect(html).toContain('&lt;img'); expect(html).toContain('&lt;script&gt;');
        expect(html).not.toContain('background:red;position');
        expect(template.content.querySelector('textarea').value).toBe(state.regions.byId[1].note);
    });

    it('calculates metrics only for the selected region, one request per meter', () => {
        app.store.dispatch(app.actions.regionsAdded([{ id: 2, positionId: 'P2', start: 3000, end: 4000 }]));
        app.store.dispatch(app.actions.regionSelect(1));
        renderer.buildHtml(app.store.getState(), {}, {});
        expect(app.regions.getRegionMetrics).toHaveBeenCalledTimes(2);
        expect(app.regions.getRegionMetrics.mock.calls.map(call => call[4].positionId)).toEqual(['P1', 'P2']);
        app.regions.getRegionMetrics.mockClear();
        app.store.dispatch(app.actions.regionClearSelection());
        renderer.buildHtml(app.store.getState(), {}, {});
        expect(app.regions.getRegionMetrics).not.toHaveBeenCalled();
    });

    it('does not calculate region metrics on hidden tabs', () => {
        app.store.dispatch(app.actions.setActiveSidePanelTab(1));
        renderer.buildHtml(app.store.getState(), {}, {});
        app.store.dispatch(app.actions.setActiveSidePanelTab(2));
        renderer.buildHtml(app.store.getState(), {}, {});
        expect(app.regions.getRegionMetrics).not.toHaveBeenCalled();
    });

    it('filters without changing annotation entities', () => {
        const before = app.store.getState().regions;
        app.store.dispatch(feature.thunks.panelCommandIntent('filter', { field: 'presentAt', value: 'P2' }));
        expect(feature.selectors.selectPanelData(app.store.getState()).regions).toHaveLength(0);
        expect(app.store.getState().regions).toBe(before);
    });

    it('binds once, cycles meter states and leaves the seek cursor unchanged', async () => {
        setupDom(); events.attach(models); events.attach(models);
        const before = app.store.getState().interaction.tap;
        root.querySelector('[data-action="cycle-meter"][data-meter="P2"]').click();
        await tick();
        expect(app.store.getState().regions.byId[1].meterStates.P2).toBe('present');
        expect(app.store.getState().interaction.tap).toBe(before);
        root.querySelector('[data-action="cycle-meter"][data-meter="P2"]').click();
        expect(app.store.getState().regions.byId[1].meterStates.P2).toBe('absent');
    });

    it('preserves drafts, caret, scroll and expanded sections through replacement', async () => {
        setupDom(); await tick();
        let textarea = root.querySelector('textarea'); textarea.focus(); textarea.value = 'A draft'; textarea.setSelectionRange(2, 5);
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        root.querySelector('details[data-key="region-secondary"]').open = true;
        root.querySelector('[data-scroll-key="panel"]').scrollTop = 120;
        // Change another field so Bokeh replaces the HTML while the note is dirty.
        app.store.dispatch(app.actions.regionSetColor(1, '#123456'));
        await tick(); textarea = root.querySelector('textarea');
        expect(textarea.value).toBe('A draft'); expect(root.activeElement).toBe(textarea);
        expect([textarea.selectionStart, textarea.selectionEnd]).toEqual([2, 5]);
        expect(root.querySelector('[data-scroll-key="panel"]').scrollTop).toBe(120);
        expect(root.querySelector('details[data-key="region-secondary"]').open).toBe(true);
        expect(app.store.getState().regions.byId[1].note).toBe('Dog bark');
    });

    it('commits notes with Ctrl+Enter and cancels drafts with Escape', async () => {
        setupDom(); await tick();
        let textarea = root.querySelector('textarea'); textarea.value = 'Saved note';
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', ctrlKey: true, bubbles: true }));
        await tick(); expect(app.store.getState().regions.byId[1].note).toBe('Saved note');
        textarea = root.querySelector('textarea'); textarea.value = 'Discard me';
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        textarea.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        expect(textarea.value).toBe('Saved note');
    });

    it('requires the explicit second action before clearing marker snapshots', () => {
        app.store.dispatch(app.actions.markerAdd(1500, { note: 'Saved', metrics: { broadband: [] } }));
        const dispatch = (command, payload) => app.store.dispatch(feature.thunks.panelCommandIntent(command, payload));
        dispatch('confirm-clear-markers'); expect(app.store.getState().markers.allIds).toHaveLength(1);
        dispatch('clear-markers'); expect(app.store.getState().markers.allIds).toHaveLength(1);
        dispatch('confirm-clear-markers'); expect(app.store.getState().markers.allIds).toHaveLength(0);
    });

    it('keeps classification selection passive and sorts scores numerically', () => {
        app.store.dispatch(app.actions.classificationsAdded([
            { id: 1, positionId: 'P1', sourceId: 'dog', start: 1000, end: 2000, confidence: .12 },
            { id: 2, positionId: 'P1', sourceId: 'dog', start: 3000, end: 4000, confidence: .9 }
        ]));
        const before = app.store.getState();
        app.store.dispatch(feature.thunks.panelCommandIntent('select-classification', { id: 2 }));
        app.store.dispatch(feature.thunks.panelCommandIntent('classification-sort', { value: 'score' }));
        const after = app.store.getState();
        expect(after.interaction.tap).toBe(before.interaction.tap); expect(after.view.viewport).toBe(before.view.viewport); expect(after.audio).toBe(before.audio);
        expect(feature.selectors.selectPanelData(after).classifications.map(entry => entry.id)).toEqual([2, 1]);
    });

    it('disposes listeners so detached controls cannot dispatch', () => {
        setupDom(); const control = root.querySelector('[data-action="cycle-meter"][data-meter="P2"]');
        events.dispose(); control.click();
        expect(app.store.getState().regions.byId[1].meterStates.P2).toBe('unchecked');
    });
});
