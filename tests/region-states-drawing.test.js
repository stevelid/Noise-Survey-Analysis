import { beforeEach, describe, expect, it, vi } from 'vitest';
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/chart-classes.js';
import '../noise_survey_analysis/static/js/services/eventHandlers.js';

const app = window.NoiseSurveyApp;
const positions = ['P1', 'P2', 'P3', 'P4'];
const annotation = (overrides = {}) => ({
    id: 1, positionId: 'P1', areas: [{ start: 1000, end: 2000 }],
    categoryId: 'plant', color: null,
    meterStates: { P1: 'present', P2: 'present', P3: 'absent', P4: 'unchecked' },
    ...overrides
});

function chart(positionId) {
    const model = {
        name: `figure_${positionId}_timeseries`, renderers: [],
        x_range: { start: 0, end: 10000 }, y_range: { start: 20, end: 100 },
        add_renderers(...renderers) { this.renderers.push(...renderers); },
        request_render: vi.fn()
    };
    return new app.classes.Chart(model, {}, {}, {}, positionId);
}

function store() {
    const result = app.createStore(app.rootReducer);
    app.store = result;
    app.registry = { models: {}, controllers: { chartsByName: new Map() } };
    result.dispatch(app.actions.initializeState({ availablePositions: positions, selectedParameter: 'LAeq',
        chartVisibility: {}, viewport: { min: 0, max: 10000 } }));
    result.dispatch(app.actions.regionsAdded([annotation()]));
    return result;
}

beforeEach(() => {
    app.history.reset();
    const GenericModel = function (properties = {}) { Object.assign(this, properties); };
    const Source = function (properties = {}) { Object.assign(this, properties); this.change = { emit: vi.fn() }; };
    window.Bokeh = global.Bokeh = {
        documents: [], Models: { get: name => name === 'ColumnDataSource' ? Source : GenericModel }
    };
});

describe('multi-meter Quad overlays', () => {
    it('uses category colours for present and a neutral checked style for absent', () => {
        const categories = app.annotationModel.normalizeCatalog();
        const present = chart('P2');
        present.syncRegions([annotation()], 1, { categories });
        expect(present.regionOverlay.source.data).toMatchObject({
            left: [1000], right: [2000], fill_color: ['#388e3c'], state: ['present'], meter_id: ['P2'], area_index: [0]
        });
        const absent = chart('P3');
        absent.syncRegions([annotation()], 1, { categories, ghostMode: 'off' });
        expect(absent.regionOverlay.source.data.state).toEqual(['absent']);
        expect(absent.regionOverlay.source.data.fill_color).toEqual(['#94a3b8']);
        expect(absent.regionGhostOverlay.source.data.left).toEqual([]);
    });

    it('draws a dashed ghost only for the selected region by default', () => {
        const target = chart('P4');
        target.syncRegions([annotation(), annotation({ id: 2, areas: [{ start: 3000, end: 4000 }] })], 1);
        expect(target.regionOverlay.source.data.left).toEqual([]);
        expect(target.regionGhostOverlay.source.data.left).toEqual([1000]);
        expect(target.regionGhostOverlay.source.data.region_id).toEqual([1]);
        expect(target.regionGhostOverlay.source.data.state).toEqual(['unchecked']);
        expect(target.regionGhostOverlay.renderer.glyph.line_dash).toEqual([6, 4]);
        expect(target.regionGhostOverlay.source.data.fill_alpha[0]).toBeLessThan(0.08);
        target.syncRegions([annotation()], 1, { ghostMode: 'off' });
        expect(target.regionGhostOverlay.renderer.visible).toBe(false);
    });

    it('handles every area and preserves aligned timestamps without applying offsets twice', () => {
        const target = chart('P4');
        const shifted = annotation({ areas: [{ start: 11000, end: 12000 }, { start: 13000, end: 14000 }] });
        target.syncRegions([shifted], 1, { ghostMode: 'all', chartOffsetMs: 10000 });
        expect(target.regionGhostOverlay.source.data.left).toEqual([11000, 13000]);
        expect(target.regionGhostOverlay.source.data.area_index).toEqual([0, 1]);
        expect(target.regionGhostOverlay.source.data.meter_id).toEqual(['P4', 'P4']);
    });

    it('keeps two renderers per chart for 300 regions across repeated updates', () => {
        const regions = Array.from({ length: 300 }, (_, index) => annotation({ id: index + 1,
            areas: [{ start: index * 3000, end: index * 3000 + 2000 }] }));
        const charts = positions.map(chart);
        charts.forEach(target => {
            target.syncRegions(regions, 1, { ghostMode: 'all' });
            target.syncRegions(regions, 2, { ghostMode: 'all' });
            expect(target.model.renderers).toHaveLength(2);
            expect(target.regionOverlay.source.data.left.length + target.regionGhostOverlay.source.data.left.length).toBe(300);
            target.syncRegions([], null);
            expect(target.regionOverlay.renderer.visible).toBe(false);
            expect(target.regionGhostOverlay.renderer.visible).toBe(false);
        });
    });
});

describe('meter review interaction', () => {
    it('cycles a selected ghost through all states without moving the tap cursor', () => {
        const result = store();
        result.dispatch(app.actions.tap(500, 'P1', 'figure_P1_timeseries'));
        const tap = result.getState().interaction.tap;
        const click = { timestamp: 1500, positionId: 'P4', chartName: 'figure_P4_timeseries', modifiers: {} };
        ['present', 'absent', 'unchecked'].forEach(expected => {
            result.dispatch(app.thunks.handleTapIntent(click));
            expect(result.getState().regions.byId[1].meterStates.P4).toBe(expected);
            expect(result.getState().interaction.tap).toEqual(tap);
        });
    });

    it('does not cycle hidden ghosts, hidden overlays, origin bands or modified clicks', () => {
        const result = store();
        const click = { timestamp: 1500, positionId: 'P4', chartName: 'figure_P4_timeseries', modifiers: {} };
        result.dispatch(app.thunks.setRegionGhostModeIntent('off'));
        result.dispatch(app.thunks.handleTapIntent(click));
        expect(result.getState().regions.byId[1].meterStates.P4).toBe('unchecked');
        result.dispatch(app.actions.regionSelect(1));
        result.dispatch(app.thunks.setRegionGhostModeIntent('all'));
        result.dispatch(app.actions.regionVisibilitySet({ showOverlays: false }));
        result.dispatch(app.thunks.handleTapIntent(click));
        expect(result.getState().regions.byId[1].meterStates.P4).toBe('unchecked');
        result.dispatch(app.actions.regionVisibilitySet({ showOverlays: true }));
        result.dispatch(app.actions.regionSelect(1));
        result.dispatch(app.thunks.handleTapIntent({ ...click, modifiers: { alt: true } }));
        expect(result.getState().regions.byId[1].meterStates.P4).toBe('unchecked');
        result.dispatch(app.actions.regionSelect(1));
        result.dispatch(app.thunks.handleTapIntent({ ...click, positionId: 'P1' }));
        expect(result.getState().regions.byId[1].meterStates.P1).toBe('present');
    });

    it('uses number keys in display order, with origin, repeat and modifier guards', () => {
        const result = store();
        result.dispatch(app.actions.initializeState({ availablePositions: ['P4', 'P1', 'P2', 'P3'], selectedParameter: 'LAeq',
            chartVisibility: {}, viewport: { min: 0, max: 10000 } }));
        result.dispatch(app.thunks.handleKeyboardShortcutIntent({ key: '1' }));
        expect(result.getState().regions.byId[1].meterStates.P4).toBe('present');
        result.dispatch(app.thunks.handleKeyboardShortcutIntent({ key: '2' }));
        expect(result.getState().regions.byId[1].meterStates.P1).toBe('present');
        [{ repeat: true }, { ctrlKey: true }, { metaKey: true }, { altKey: true }, { shiftKey: true }, { isEditable: true }].forEach(extra => {
            result.dispatch(app.thunks.handleKeyboardShortcutIntent({ key: '1', ...extra }));
            expect(result.getState().regions.byId[1].meterStates.P4).toBe('present');
        });
    });

    it('leaves classification taps passive ahead of band interactions', () => {
        const result = store();
        result.dispatch(app.actions.classificationsAdded([{ id: 1, positionId: 'P4', sourceId: 'dog', start: 1000, end: 2000 }]));
        app.registry.controllers.chartsByName.set('figure_P4_timeseries', {
            classificationOverlay: { renderer: { visible: true }, source: { data: {
                left: [1000], right: [2000], bottom: [0], top: [10], classification_id: [1]
            } } }
        });
        const tap = result.getState().interaction.tap;
        app.eventHandlers.handleTap({ x: 1500, y: 5, origin: { name: 'figure_P4_timeseries' } });
        expect(result.getState().classifications.selectedId).toBe(1);
        expect(result.getState().interaction.tap).toEqual(tap);
        expect(result.getState().regions.byId[1].meterStates.P4).toBe('unchecked');
    });

    it('ignores meter shortcuts while typing and never stores ghost settings in undo history', () => {
        const result = store();
        const input = document.createElement('textarea');
        document.body.appendChild(input);
        input.focus();
        app.eventHandlers.handleKeyPress({ key: '4', code: 'Digit4', target: input, composedPath: () => [input], preventDefault: vi.fn() });
        expect(result.getState().regions.byId[1].meterStates.P4).toBe('unchecked');
        input.remove();
        app.history.reset();
        result.dispatch(app.thunks.setRegionGhostModeIntent('all'));
        expect(result.getState().regions.ghostMode).toBe('all');
        expect(app.history._debug().pastLength).toBe(0);
    });
});
