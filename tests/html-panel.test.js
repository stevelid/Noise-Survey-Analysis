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
        app.store.dispatch(feature.actions.panelSettingsChanged({ metricsVisible: true }));
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

    it('starts with metrics collapsed and preserves the explicit choice through workspace state rehydration', () => {
        setupDom();
        expect(root.querySelector('[data-action="metrics-visible"]').getAttribute('aria-expanded')).toBe('false');
        expect(app.regions.getRegionMetrics).not.toHaveBeenCalled();
        for (const expected of [true, false]) {
            app.store.dispatch(feature.thunks.panelCommandIntent('metrics-visible'));
            const restored = app.rootReducer(undefined, app.actions.rehydrateState(JSON.parse(JSON.stringify(app.store.getState()))));
            expect(feature.selectors.selectPanelState(restored).metricsVisible).toBe(expected);
        }
    });

    it('uses a native picker without converting inherited category colour into an override', async () => {
        setupDom(); await tick();
        let picker = root.querySelector('[data-key="region-color:1"]');
        const inherited = app.annotationModel.effectiveColor(app.store.getState().regions.byId[1], app.store.getState().regions.categories);
        expect(picker.type).toBe('color');
        expect(picker.value).toBe(inherited);
        expect(app.store.getState().regions.byId[1].color).toBeFalsy();
        picker.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }));
        picker.focus(); picker.value = '#123456';
        picker.dispatchEvent(new Event('input', { bubbles: true }));
        picker.dispatchEvent(new Event('change', { bubbles: true }));
        expect(picker.isConnected).toBe(true);
        picker.blur(); await tick();
        expect(app.store.getState().regions.byId[1].color).toBe('#123456');
        root.querySelector('[data-action="region-color"][data-value=""]').click(); await tick();
        expect(app.store.getState().regions.byId[1].color).toBeNull();
        expect(root.querySelector('[data-key="region-color:1"]').value).toBe(inherited);
        app.store.dispatch(app.actions.regionSetColor(1, 'red')); await tick();
        picker = root.querySelector('[data-key="region-color:1"]');
        expect(picker.value).toBe('#ff0000');
        expect(app.store.getState().regions.byId[1].color).toBe('red');
    });

    it('does not calculate region metrics on hidden tabs', () => {
        app.store.dispatch(app.actions.setActiveSidePanelTab(1));
        renderer.buildHtml(app.store.getState(), {}, {});
        app.store.dispatch(app.actions.setActiveSidePanelTab(2));
        renderer.buildHtml(app.store.getState(), {}, {});
        expect(app.regions.getRegionMetrics).not.toHaveBeenCalled();
    });

    it('loads the origin spectrum on demand while the per-meter metrics table stays collapsed', async () => {
        setupDom(); await tick();
        expect(app.regions.getRegionMetrics).not.toHaveBeenCalled();
        const spectrum = root.querySelector('details[data-key="region-spectrum"]');
        spectrum.open = true;
        spectrum.dispatchEvent(new Event('toggle'));
        await tick();
        expect(app.store.getState().annotationPanel.metricsVisible).toBe(false);
        expect(app.store.getState().annotationPanel.spectrumVisible).toBe(true);
        expect(app.regions.getRegionMetrics).toHaveBeenCalledTimes(1);
        expect(app.regions.getRegionMetrics.mock.calls[0][4].positionId).toBe('P1');
        const rendered = root.querySelector('details[data-key="region-spectrum"]');
        expect(rendered.open).toBe(true);
        expect(rendered.querySelector('table').textContent).toContain('63 Hz');
        expect(root.querySelector('[data-action="metrics-visible"]').getAttribute('aria-expanded')).toBe('false');
        rendered.open = false; rendered.dispatchEvent(new Event('toggle')); await tick();
        expect(app.regions.getRegionMetrics).toHaveBeenCalledTimes(1);
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

    it('preserves details scroll for the same region and starts a different region at the top', async () => {
        app.store.dispatch(app.actions.regionsAdded([{ id: 2, positionId: 'P1', start: 3000, end: 4000 }]));
        app.store.dispatch(app.actions.regionSelect(1));
        setupDom(); await tick();
        root.querySelector('[data-scroll-key="selected-region:1"]').scrollTop = 80;
        app.store.dispatch(app.actions.regionSetColor(1, '#123456')); await tick();
        expect(root.querySelector('[data-scroll-key="selected-region:1"]').scrollTop).toBe(80);
        app.store.dispatch(app.actions.regionSelect(2)); await tick();
        expect(root.querySelector('[data-scroll-key="selected-region:2"]').scrollTop).toBe(0);
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

    it('saves a dirty note and selects the clicked region without replacing its button before click', async () => {
        app.store.dispatch(app.actions.regionsAdded([{ id: 2, positionId: 'P2', start: 3000, end: 4000 }]));
        app.store.dispatch(app.actions.regionSelect(1));
        setupDom(); await tick();
        const textarea = root.querySelector('textarea[data-action="region-note"]');
        textarea.focus(); textarea.value = 'Saved while selecting region two';
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        const button = root.querySelector('button[data-action="select-region"][data-id="2"]');
        // Model browser ordering: mousedown focuses the button, firing change
        // and blur before mouseup/click unless its default is prevented.
        const down = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 });
        button.dispatchEvent(down);
        if (!down.defaultPrevented) {
            textarea.dispatchEvent(new Event('change', { bubbles: true }));
            textarea.blur(); button.focus();
        }
        expect(down.defaultPrevented).toBe(true);
        expect(button.isConnected).toBe(true);
        expect(app.store.getState().regions.byId[1].note).toBe('Dog bark');
        button.click(); await tick();
        expect(app.store.getState().regions.byId[1].note).toBe('Saved while selecting region two');
        expect(app.features.regions.selectors.selectSelectedRegion(app.store.getState()).id).toBe(2);
    });

    it('flushes a marker draft before changing tabs and leaves keyboard button activation available', async () => {
        app.store.dispatch(app.actions.markerAdd(1500, { note: 'Original marker' }));
        const marker = app.features.markers.selectors.selectAllMarkers(app.store.getState())[0];
        app.store.dispatch(feature.thunks.panelCommandIntent('select-marker', { id: marker.id }));
        app.store.dispatch(app.actions.setActiveSidePanelTab(1));
        setupDom(); await tick();
        const textarea = root.querySelector('textarea[data-action="marker-note"]');
        textarea.focus(); textarea.value = 'Marker draft';
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        const button = root.querySelector('button[data-action="tab"][data-value="0"]');
        const down = new MouseEvent('pointerdown', { bubbles: true, cancelable: true, button: 0 });
        button.dispatchEvent(down); expect(down.defaultPrevented).toBe(true);
        button.click(); await tick();
        expect(app.store.getState().markers.byId[marker.id].note).toBe('Marker draft');
        const tab = root.querySelector('button[data-action="tab"][data-value="1"]');
        tab.focus();
        const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true });
        tab.dispatchEvent(enter); expect(enter.defaultPrevented).toBe(false);
        const cleanPointer = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 });
        tab.dispatchEvent(cleanPointer); expect(cleanPointer.defaultPrevented).toBe(false);
        tab.click();
        expect(app.store.getState().view.activeSidePanelTab).toBe(1);
    });

    it('saves a dirty note while opening a disclosure and restores summary focus', async () => {
        setupDom(); await tick();
        const textarea = root.querySelector('textarea[data-action="region-note"]');
        textarea.focus(); textarea.value = 'Saved while opening actions';
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        const summary = root.querySelector('details[data-key="region-secondary"] > summary');
        const down = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 });
        summary.dispatchEvent(down);
        expect(down.defaultPrevented).toBe(true);
        summary.click(); await tick();
        expect(app.store.getState().regions.byId[1].note).toBe('Saved while opening actions');
        const details = root.querySelector('details[data-key="region-secondary"]');
        expect(details.open).toBe(true);
        expect(root.activeElement).toBe(details.querySelector('summary'));
        app.store.dispatch(app.actions.regionSetColor(1, '#123456'));
        await tick();
        expect(root.activeElement).toBe(root.querySelector('details[data-key="region-secondary"] > summary'));
    });

    it('saves dirty notes before Tab and Shift+Tab and restores the intended neighbouring field', async () => {
        setupDom(); await tick();
        for (const [shiftKey, expectedKey] of [[false, 'region-color:1'], [true, 'region-category:1']]) {
            const textarea = root.querySelector('textarea[data-action="region-note"]');
            textarea.focus(); textarea.value = `Saved with shift=${shiftKey}`;
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            const tab = new KeyboardEvent('keydown', { key: 'Tab', shiftKey, bubbles: true, cancelable: true });
            textarea.dispatchEvent(tab); await tick();
            expect(tab.defaultPrevented).toBe(true);
            expect(app.store.getState().regions.byId[1].note).toBe(`Saved with shift=${shiftKey}`);
            expect(root.activeElement?.dataset.key).toBe(expectedKey);
        }
        const clean = root.querySelector('textarea[data-action="region-note"]');
        clean.focus();
        const nativeTab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true });
        clean.dispatchEvent(nativeTab);
        expect(nativeTab.defaultPrevented).toBe(false);
    });

    it('keeps native form targets alive while a dirty note saves on pointer blur', async () => {
        setupDom(); await tick();
        for (const [key, value] of [['region-category:1', 'traffic'], ['region-color:1', '#123456']]) {
            const textarea = root.querySelector('textarea[data-action="region-note"]');
            textarea.focus(); textarea.value = `Saved before ${key}`;
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
            const target = root.querySelector(`[data-key="${key}"]`);
            const down = new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 });
            target.dispatchEvent(down);
            expect(down.defaultPrevented).toBe(false);
            textarea.dispatchEvent(new Event('change', { bubbles: true }));
            textarea.blur(); target.focus();
            expect(app.store.getState().regions.byId[1].note).toBe(`Saved before ${key}`);
            expect(target.isConnected).toBe(true);
            expect(root.activeElement).toBe(target);
            target.value = value;
            target.dispatchEvent(new Event('change', { bubbles: true }));
            if (target.tagName === 'INPUT') target.blur();
            await tick();
            expect(events.shouldDeferRender(models)).toBe(false);
        }
        expect(app.store.getState().regions.byId[1].categoryId).toBe('traffic');
        expect(app.store.getState().regions.byId[1].color).toBe('#123456');
    });

    it('releases deferred rendering after an unchanged control loses focus', async () => {
        setupDom(); await tick();
        const textarea = root.querySelector('textarea[data-action="region-note"]');
        textarea.focus(); textarea.value = 'Saved without changing category';
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        const category = root.querySelector('[data-action="region-category"]');
        category.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
        textarea.blur(); category.focus();
        expect(events.shouldDeferRender(models)).toBe(true);
        category.blur(); await tick();
        expect(events.shouldDeferRender(models)).toBe(false);
        expect(root.querySelector('[data-action="select-region"][data-id="1"]').textContent).toBe('Saved without changing category');
        expect(app.store.getState().regions.byId[1].note).toBe('Saved without changing category');
    });

    it.each(['region', 'summary', 'colour'])('preserves the first %s click after leaving a protected form control', async kind => {
        app.store.dispatch(app.actions.regionsAdded([{ id: 2, positionId: 'P1', start: 3000, end: 4000 }]));
        app.store.dispatch(app.actions.regionSelect(1));
        setupDom(); await tick();
        const textarea = root.querySelector('textarea[data-action="region-note"]');
        textarea.focus(); textarea.value = `Saved before ${kind}`;
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        const form = root.querySelector(`[data-key="${kind === 'colour' ? 'region-color:1' : 'region-category:1'}"]`);
        form.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
        textarea.blur(); form.focus();
        const target = kind === 'summary'
            ? root.querySelector('details[data-key="region-secondary"] > summary')
            : root.querySelector('[data-action="select-region"][data-id="2"]');
        target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
        if (kind === 'colour') {
            form.value = '#123456'; form.dispatchEvent(new Event('change', { bubbles: true }));
        }
        form.blur(); target.focus(); await tick();
        expect(target.isConnected).toBe(true);
        target.click(); await tick();
        expect(events.shouldDeferRender(models)).toBe(false);
        expect(app.store.getState().regions.byId[1].note).toBe(`Saved before ${kind}`);
        if (kind === 'summary') expect(root.querySelector('details[data-key="region-secondary"]').open).toBe(true);
        else expect(app.store.getState().regions.selectedId).toBe(2);
        if (kind === 'colour') expect(app.store.getState().regions.byId[1].color).toBe('#123456');
    });

    it('releases an abandoned pointer-click guard without losing the saved note', async () => {
        setupDom(); await tick();
        const textarea = root.querySelector('textarea[data-action="region-note"]');
        textarea.focus(); textarea.value = 'Saved before cancelled pointer';
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        const category = root.querySelector('[data-action="region-category"]');
        category.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
        textarea.blur(); category.focus();
        const summary = root.querySelector('details[data-key="region-secondary"] > summary');
        summary.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }));
        category.blur(); await tick();
        expect(events.shouldDeferRender(models)).toBe(true);
        window.dispatchEvent(new Event('pointercancel')); await tick();
        expect(events.shouldDeferRender(models)).toBe(false);
        expect(root.querySelector('[data-action="select-region"][data-id="1"]').textContent).toBe('Saved before cancelled pointer');
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

    it('hides annotation overlays without deleting or filtering their lists', () => {
        app.store.dispatch(app.actions.markerAdd(1500));
        app.store.dispatch(app.actions.classificationsAdded([
            { id: 1, positionId: 'P1', sourceId: 'dog', start: 1000, end: 2000 }
        ]));
        const before = feature.selectors.selectPanelData(app.store.getState());
        setupDom();
        for (const field of ['regions', 'markers', 'classifications']) {
            const control = root.querySelector(`[data-action="annotation-visibility"][data-field="${field}"]`);
            control.checked = false;
            control.dispatchEvent(new Event('change', { bubbles: true }));
        }
        const state = app.store.getState();
        const after = feature.selectors.selectPanelData(state);
        expect(state.regions.overlaysVisible).toBe(false);
        expect(state.markers.enabled).toBe(false);
        expect(state.classifications.overlaysVisible).toBe(false);
        expect(after.regions).toEqual(before.regions);
        expect(after.markers).toEqual(before.markers);
        expect(after.classifications).toEqual(before.classifications);
    });

    it('fits the sticky sidebar below the toolbar across Bokeh shadow boundaries', () => {
        const toolbar = document.createElement('div');
        toolbar.className = 'nsa-dashboard-controls';
        toolbar.getBoundingClientRect = () => ({ top: 0, bottom: 70, height: 70 });
        document.body.appendChild(toolbar);
        try {
            setupDom();
            host.classList.add('nsa-annotation-inner');
            events.dispose(); events.attach(models);
            expect(host.style.top).toBe('82px');
            expect(root.querySelector('[data-scroll-key="panel"]').style.maxHeight)
                .toBe(`${Math.floor(window.innerHeight - 82 - 12)}px`);
            toolbar.getBoundingClientRect = () => ({ top: -100, bottom: -30, height: 70 });
            // Reattachment models a viewport refit without changing Redux.
            const before = app.store.getState();
            events.dispose(); events.attach(models);
            expect(host.style.top).toBe('12px');
            expect(app.store.getState()).toBe(before);
        } finally { toolbar.remove(); }
    });
});
