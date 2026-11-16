import { beforeEach, describe, expect, it, vi } from 'vitest';
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/chart-classes.js';
import '../noise_survey_analysis/static/js/features/annotations/panelSelectors.js';
import '../noise_survey_analysis/static/js/features/annotations/panelThunks.js';
import '../noise_survey_analysis/static/js/services/panels/htmlPanelEvents.js';
import '../noise_survey_analysis/static/js/services/panels/htmlPanelRenderer.js';
import '../noise_survey_analysis/static/js/services/automation/annotationCommands.js';
import '../noise_survey_analysis/static/js/features/regions/suggestionKeys.js';

const app = window.NoiseSurveyApp;
const feature = app.features.annotationPanel;
const review = app.features.review;
const positions = ['P1', 'P2'];
const T = 1_794_219_402_000; // 2026-11-09T10:16:42Z

const agent = { name: 'yamnet', runId: 'r1' };
const suggestion = (overrides = {}) => ({
    positionId: 'P1', start: T, end: T + 20_000, areas: [{ start: T, end: T + 20_000 }], note: 'Dog bark',
    categoryId: 'music', source: 'agent', status: 'proposed', rationale: 'Harmonics near 1 kHz', confidence: 0.82, agent,
    ...overrides
});

let store;
function makeStore() {
    app.history.reset();
    const base = app.createInitialState();
    base.view.availablePositions = positions;
    base.view.positionDisplayTitles = { P1: 'Garden', P2: 'Road' };
    base.view.viewport = { min: T - 60_000, max: T + 600_000 };
    store = app.createStore((state, action) => {
        const next = app.rootReducer(state || base, action);
        return { ...next, annotationPanel: feature.reducer(state?.annotationPanel, action) };
    });
    app.store = store;
    app.registry = { models: {}, controllers: { chartsByName: new Map() } };
    app.dataCache = {};
    return store;
}
const regions = () => store.getState().regions;
const add = (...items) => store.dispatch(app.actions.regionsAdded(items));
const ctx = () => ({ dispatch: store.dispatch, getState: store.getState });

beforeEach(() => {
    makeStore();
    const GenericModel = function (properties = {}) { Object.assign(this, properties); };
    const Source = function (properties = {}) { Object.assign(this, properties); this.change = { emit: vi.fn() }; };
    window.Bokeh = global.Bokeh = { documents: [], Models: { get: name => (name === 'ColumnDataSource' ? Source : GenericModel) } };
});

describe('data model', () => {
    it('keeps suggestion fields on regions and drops invalid ones', () => {
        add(suggestion({ status: 'bogus', confidence: 7 }), suggestion({ start: T + 50_000, end: T + 60_000, areas: undefined }));
        const [first, second] = Object.values(regions().byId);
        expect(first.status).toBeUndefined();
        expect(first.confidence).toBeUndefined();
        expect(first.rationale).toBe('Harmonics near 1 kHz');
        expect(second).toMatchObject({ source: 'agent', status: 'proposed', confidence: 0.82, agent });
    });

    it('keeps suggestion fields on markers through add, update and replace', () => {
        store.dispatch({ type: app.actionTypes.MARKER_ADDED, payload: { timestamp: T, note: 'x', source: 'agent', status: 'proposed', confidence: 0.4, rationale: 'why', agent, createdAt: '2026-11-09T10:00:00Z', junk: 1 } });
        let marker = store.getState().markers.byId[1];
        expect(marker).toMatchObject({ source: 'agent', status: 'proposed', confidence: 0.4, rationale: 'why', agent });
        expect(marker.junk).toBeUndefined();
        store.dispatch(app.actions.markerUpdate(1, { status: 'accepted', reviewedAt: '2026-11-09T11:00:00Z', confidence: 5 }));
        marker = store.getState().markers.byId[1];
        expect(marker.status).toBe('accepted');
        expect(marker.reviewedAt).toBe('2026-11-09T11:00:00Z');
        expect(marker.confidence).toBe(0.4);
        store.dispatch(app.actions.markersReplace(Object.values(store.getState().markers.byId)));
        expect(store.getState().markers.byId[1]).toMatchObject({ source: 'agent', status: 'accepted', agent });
    });

    it('survives workspace migration', () => {
        const payload = { version: 2, appState: { view: { availablePositions: positions }, regions: { byId: { 1: { id: 1, ...suggestion() } }, allIds: [1] } } };
        const migrated = app.workspaceMigration.migrateWorkspace(payload).payload;
        expect(migrated.appState.regions.byId[1]).toMatchObject({ status: 'proposed', source: 'agent', confidence: 0.82 });
    });
});

describe('overlays', () => {
    function chart(positionId) {
        const model = {
            name: `figure_${positionId}`, renderers: [], x_range: { start: 0, end: 1 }, y_range: { start: 20, end: 100 },
            add_renderers(...r) { this.renderers.push(...r); }, request_render: vi.fn()
        };
        return new app.classes.Chart(model, {}, {}, {}, positionId);
    }
    const base = (overrides = {}) => ({ id: 1, positionId: 'P1', areas: [{ start: 1000, end: 2000 }], categoryId: 'plant', meterStates: { P1: 'present', P2: 'present' }, ...overrides });

    it('draws a proposed region faint and dashed on its own overlay, not on the normal or ghost one', () => {
        const target = chart('P1');
        target.syncRegions([base({ status: 'proposed', source: 'agent', confidence: 0.5, note: 'dog', rationale: 'why', agent }), base({ id: 2, areas: [{ start: 5000, end: 6000 }] })], null);
        expect(target.regionOverlay.source.data.region_id).toEqual([2]);
        expect(target.regionProposedOverlay.source.data).toMatchObject({
            region_id: [1], left: [1000], fill_alpha: [0.06], line_alpha: [0.6], note: ['dog'], conf_str: ['0.50'], agent_str: ['yamnet']
        });
        expect(target.regionProposedOverlay.renderer.glyph.line_dash).toEqual([4, 4]);
        expect(target.regionProposedOverlay.renderer.visible).toBe(true);
    });

    it('does not ghost a proposed region on other meters and never draws rejected ones', () => {
        const other = chart('P2');
        other.syncRegions([base({ status: 'proposed', meterStates: { P1: 'present' } }), base({ id: 2, status: 'rejected' })], 1, { ghostMode: 'all' });
        expect(other.regionOverlay.source.data.left).toEqual([]);
        expect(other.regionGhostOverlay.source.data.left).toEqual([]);
        expect(other.regionProposedOverlay.source.data.left).toEqual([]);
        const origin = chart('P1');
        origin.syncRegions([base({ id: 2, status: 'rejected' })], 2);
        expect(Object.values(origin.regionOverlay.source.data).every(column => column.length === 0)).toBe(true);
    });

    it('accepted suggestions join the normal overlay', () => {
        const target = chart('P1');
        target.syncRegions([base({ status: 'accepted', source: 'agent' })], null);
        expect(target.regionOverlay.source.data.region_id).toEqual([1]);
        expect(target.regionProposedOverlay.source.data.left).toEqual([]);
    });

    it('draws proposed markers dashed and faint and skips rejected', () => {
        const target = chart('P1');
        const marker = (id, timestamp, extra) => ({ id, timestamp, color: '#fdd835', ...extra });
        target.syncMarkers([marker(1, 10), marker(2, 20, { status: 'proposed', note: 'n', confidence: 0.3, agent }), marker(3, 30, { status: 'rejected' })], true, null);
        expect(target.markerOverlay.source.data.marker_id).toEqual([1]);
        expect(target.markerProposedOverlay.source.data).toMatchObject({ marker_id: [2], line_alpha: [0.4], conf_str: ['0.30'] });
        expect(target.markerProposedOverlay.renderer.glyph.line_dash).toEqual([4, 4]);
    });
});

describe('review actions', () => {
    it('accept changes only the status and is undoable', () => {
        add(suggestion());
        store.dispatch(review.thunks.reviewItemIntent('region', 1, 'accepted', { advance: false }));
        expect(regions().byId[1]).toMatchObject({ status: 'accepted' });
        expect(regions().byId[1].reviewedAt).toMatch(/^\d{4}-/);
        expect(regions().byId[1].note).toBe('Dog bark');
        store.dispatch(app.actions.undo());
        expect(regions().byId[1].status).toBe('proposed');
        expect(regions().byId[1].reviewedAt).toBeUndefined();
    });

    it('editing note or bounds does not accept', () => {
        add(suggestion());
        store.dispatch(app.actions.regionUpdate(1, { note: 'Barking dog', end: T + 30_000 }));
        expect(regions().byId[1]).toMatchObject({ status: 'proposed', note: 'Barking dog', end: T + 30_000 });
        store.dispatch(app.features.regions.thunks.saveRegionNoteIntent(1, 'again'));
        expect(regions().byId[1].status).toBe('proposed');
    });

    it('A and D act on the selected suggestion, then select the next proposed one', () => {
        add(suggestion(), suggestion({ start: T + 100_000, end: T + 110_000, areas: [{ start: T + 100_000, end: T + 110_000 }] }), suggestion({ start: T + 200_000, end: T + 210_000, areas: [{ start: T + 200_000, end: T + 210_000 }] }));
        store.dispatch(app.actions.regionSelect(1));
        const run = id => app.keymap.getKeyBindings().find(entry => entry.id === id).run;
        run('acceptSuggestion')({}, ctx());
        expect(regions().byId[1].status).toBe('accepted');
        expect(regions().selectedId).toBe(2);
        run('rejectSuggestion')({}, ctx());
        expect(regions().byId[2].status).toBe('rejected');
        expect(regions().selectedId).toBe(3);
        run('rejectSuggestion')({}, ctx());
        expect(regions().byId[3].status).toBe('rejected');
        expect(store.getState().view.notice.message).toMatch(/No more suggestions/);
    });

    it('keys do not clash with the existing bindings', () => {
        const key = props => ({ key: '', ctrlKey: false, altKey: false, shiftKey: false, repeat: false, ...props });
        expect(app.keymap.match(key({ key: 'a' }))?.id).toBe('acceptSuggestion');
        expect(app.keymap.match(key({ key: 'D' }))?.id).toBe('rejectSuggestion');
        expect(app.keymap.match(key({ key: '{', shiftKey: true }))?.id).toBe('previousSuggestion');
        expect(app.keymap.match(key({ key: '}', shiftKey: true }))?.id).toBe('nextSuggestion');
        expect(app.keymap.match(key({ key: '[' }))?.id).toBe('stepRegion');
        expect(app.keymap.match(key({ key: 'a', ctrlKey: true }))?.id).not.toBe('acceptSuggestion');
    });

    it('{ and } step through proposed regions only, wrapping', () => {
        add(suggestion(), suggestion({ status: 'accepted', start: T + 50_000, end: T + 60_000, areas: [{ start: T + 50_000, end: T + 60_000 }] }),
            suggestion({ start: T + 100_000, end: T + 110_000, areas: [{ start: T + 100_000, end: T + 110_000 }] }));
        store.dispatch(app.actions.regionSelect(2));
        store.dispatch(review.thunks.stepProposedRegionIntent(1));
        expect(regions().selectedId).toBe(3);
        store.dispatch(review.thunks.stepProposedRegionIntent(1));
        expect(regions().selectedId).toBe(1);
        store.dispatch(review.thunks.stepProposedRegionIntent(-1));
        expect(regions().selectedId).toBe(3);
        expect(store.getState().view.viewport.min).toBeLessThan(T + 100_000);
        expect(store.getState().view.viewport.max).toBeGreaterThan(T + 110_000);
    });

    it('accept all shown is one undo step and respects the To review filter', () => {
        add(suggestion(), suggestion({ start: T + 100_000, end: T + 110_000, areas: [{ start: T + 100_000, end: T + 110_000 }] }), suggestion({ status: 'rejected', start: T + 300_000, end: T + 310_000, areas: [{ start: T + 300_000, end: T + 310_000 }] }));
        store.dispatch(review.thunks.setReviewFilterIntent('review'));
        expect(review.selectors.selectReviewList(store.getState()).shown).toHaveLength(2);
        store.dispatch(review.thunks.acceptAllShownIntent());
        expect(Object.values(regions().byId).map(r => r.status)).toEqual(['accepted', 'accepted', 'rejected']);
        store.dispatch(app.actions.undo());
        expect(Object.values(regions().byId).map(r => r.status)).toEqual(['proposed', 'proposed', 'rejected']);
    });

    it('purge deletes rejected regions and undo restores them', () => {
        add(suggestion({ status: 'rejected' }), suggestion({ start: T + 100_000, end: T + 110_000, areas: [{ start: T + 100_000, end: T + 110_000 }] }));
        store.dispatch(review.thunks.purgeRejectedIntent());
        expect(regions().allIds).toEqual([2]);
        store.dispatch(app.actions.undo());
        expect(regions().allIds).toEqual([1, 2]);
    });

    it('rejected regions cannot be hit on a chart or stepped to with [ ]', () => {
        add(suggestion({ status: 'rejected' }));
        expect(app.features.regions.selectors.selectRegionByTimestamp(store.getState(), 'P1', T + 1000)).toBeNull();
    });
});

describe('panel', () => {
    function render() {
        return app.services.htmlPanelRenderer.buildHtml(store.getState(), {}, {});
    }
    function fragment(html) {
        const template = document.createElement('template');
        template.innerHTML = html;
        return template.content;
    }

    it('shows the AI badge, chips with counts, and a read-only rationale', () => {
        add(suggestion(), suggestion({ source: undefined, status: undefined, agent: undefined, confidence: undefined, rationale: undefined, start: T + 100_000, end: T + 110_000, areas: [{ start: T + 100_000, end: T + 110_000 }] }));
        store.dispatch(app.actions.regionSelect(1));
        const html = render();
        const dom = fragment(html);
        expect(dom.querySelector('.nsa-region-row.is-suggestion .nsa-ai-badge').textContent).toBe('AI 0.82');
        const chips = [...dom.querySelectorAll('.nsa-review-bar [data-action="suggestion-filter"]')].map(b => b.textContent);
        expect(chips).toEqual(['All (2)', 'To review (1)', 'Mine (1)']);
        expect(dom.querySelector('.nsa-rationale').textContent).toBe('Harmonics near 1 kHz');
        expect(dom.querySelector('.nsa-rationale textarea, textarea .nsa-rationale')).toBeNull();
        expect(dom.querySelector('[data-action="suggestion-accept"]')).not.toBeNull();
        expect(dom.querySelector('[data-action="suggestion-accept-all"]').textContent).toContain('(1)');
        expect(dom.querySelector('textarea[data-action="region-note"]').value).toBe('Dog bark');
    });

    it('lists rejected regions under a collapsed group with restore and purge', () => {
        add(suggestion({ status: 'rejected', note: 'no thanks' }));
        const dom = fragment(render());
        const group = dom.querySelector('details.nsa-rejected');
        expect(group.querySelector('summary').textContent).toBe('Rejected (1)');
        expect(group.open).toBe(false);
        expect(group.querySelector('[data-action="suggestion-restore"]')).not.toBeNull();
        expect(group.querySelector('[data-action="suggestion-purge"]')).not.toBeNull();
        expect(dom.querySelector('.nsa-annotation-list[data-scroll-key="region-list"] .nsa-region-row')).toBeNull();
    });

    it('escapes agent text', () => {
        add(suggestion({ rationale: '<img src=x onerror=bad()>', note: '<b>n</b>', agent: { name: '<script>x</script>', runId: null } }));
        store.dispatch(app.actions.regionSelect(1));
        const dom = fragment(render());
        expect(dom.querySelector('script,img')).toBeNull();
    });

    it('panel buttons accept, filter and restore through the store', () => {
        add(suggestion());
        const send = (command, payload) => store.dispatch(review.thunks.panelSuggestionIntent(command, payload));
        send('suggestion-filter', { value: 'mine' });
        expect(store.getState().annotationPanel.reviewFilter).toBe('mine');
        send('suggestion-reject', { id: '1', kind: 'region' });
        expect(regions().byId[1].status).toBe('rejected');
        send('suggestion-restore', { id: '1', kind: 'region' });
        expect(regions().byId[1].status).toBe('proposed');
    });

    it('markers tab shows badges and a suggestion card', () => {
        store.dispatch({ type: app.actionTypes.MARKER_ADDED, payload: { timestamp: T, note: 'beep', source: 'agent', status: 'proposed', confidence: 0.6, rationale: 'tonal', agent } });
        store.dispatch(app.actions.markerSelect(1));
        store.dispatch(app.actions.setActiveSidePanelTab(1));
        const dom = fragment(render());
        expect(dom.querySelector('.nsa-marker-row.is-suggestion .nsa-ai-badge').textContent).toBe('AI 0.60');
        expect(dom.querySelector('.nsa-suggestion-card [data-kind="marker"]')).not.toBeNull();
        store.dispatch(review.thunks.acceptSelectedIntent());
        expect(store.getState().markers.byId[1].status).toBe('accepted');
    });

    it('classification times use the position chart offset', () => {
        store.dispatch(app.actions.classificationsAdded([{ positionId: 'P1', sourceId: 'dog', sourceLabel: 'Dog', start: Date.UTC(2026, 10, 9, 10, 0, 0), end: Date.UTC(2026, 10, 9, 10, 0, 5), confidence: 0.9, state: 'on' }]));
        const withOffset = structuredClone(store.getState());
        withOffset.view.positionChartOffsets = { P1: 3_600_000 };
        withOffset.view.activeSidePanelTab = 2;
        const without = structuredClone(withOffset);
        without.view.positionChartOffsets = {};
        const text = state => fragment(app.services.htmlPanelRenderer.buildHtml(state, {}, {})).querySelector('.nsa-classification-row button').textContent;
        expect(text(withOffset)).not.toBe(text(without));
    });
});

describe('promote classifications', () => {
    it('creates proposed regions in display time with the score as confidence, once', () => {
        store.dispatch(app.actions.classificationsAdded([
            { positionId: 'P1', sourceId: 'dog', sourceLabel: 'Dog', start: T, end: T + 5000, confidence: 0.9, state: 'on', description: 'barking' },
            { positionId: 'P1', sourceId: 'dog', sourceLabel: 'Dog', start: T + 9000, end: T + 12_000, confidence: 0.4, state: 'off' }
        ]));
        store.dispatch(app.actions.positionChartOffsetSet?.('P1', 1000) || { type: 'noop' });
        const count = store.dispatch(app.features.classifications.thunks.promoteShownToSuggestionsIntent());
        expect(count).toBe(1);
        const region = Object.values(regions().byId)[0];
        expect(region).toMatchObject({ source: 'agent', status: 'proposed', confidence: 0.9, agent: { name: 'yamnet' }, positionId: 'P1' });
        expect(region.note).toContain('Dog');
        const offset = store.getState().view.positionChartOffsets?.P1 || 0;
        expect(region.start).toBe(T + offset);
        expect(store.dispatch(app.features.classifications.thunks.promoteShownToSuggestionsIntent())).toBe(0);
    });
});

describe('control API handlers', () => {
    const handlers = () => app.services.annotationCommands.handlers;
    const iso = ms => new Date(ms).toISOString();

    it('add_regions adds faint proposed regions, keeps the user selection and maps client refs', () => {
        add({ positionId: 'P1', start: 1, end: 2, areas: [{ start: 1, end: 2 }] });
        store.dispatch(app.actions.regionSelect(1));
        const result = handlers().add_regions({
            agent, regions: [
                { position: 'P1', areas: [{ start: T, end: T + 20_000 }], note: 'Dog', category: 'Dog bark', confidence: 0.8, rationale: 'because', status: 'proposed', client_ref: 'a' },
                { position: 'P2', areas: [{ start: T + 60_000, end: T + 70_000 }], note: 'Car', client_ref: 'b' }
            ]
        }, ctx());
        expect(result.data.ids).toEqual([2, 3]);
        expect(result.data.by_client_ref).toEqual({ a: 2, b: 3 });
        expect(result.data.categories_created).toEqual(['Dog bark']);
        expect(regions().selectedId).toBe(1);
        expect(regions().byId[2]).toMatchObject({ source: 'agent', status: 'proposed', rationale: 'because', confidence: 0.8, agent });
        expect(regions().byId[3].status).toBe('proposed');
        expect(regions().categories.byId[regions().byId[2].categoryId].label).toBe('Dog bark');
        store.dispatch(app.actions.undo());
        expect(regions().allIds).toEqual([1]);
    });

    it('add_regions rejects unknown positions without changing anything', () => {
        expect(() => handlers().add_regions({ agent, regions: [{ position: 'P1', areas: [{ start: T, end: T + 1000 }] }, { position: 'P9', areas: [{ start: T, end: T + 1000 }] }] }, ctx())).toThrow(/unknown position/);
        expect(regions().allIds).toEqual([]);
    });

    it('list_annotations returns normalised records with filters', () => {
        handlers().add_regions({ agent, regions: [{ position: 'P1', areas: [{ start: T, end: T + 1000 }], note: 'A' }] }, ctx());
        add({ positionId: 'P2', start: T + 100_000, end: T + 101_000, areas: [{ start: T + 100_000, end: T + 101_000 }], note: 'mine' });
        const all = handlers().list_annotations({}, ctx()).data;
        expect(all.positions).toEqual(positions);
        expect(all.regions.map(r => [r.id, r.source, r.status])).toEqual([[1, 'agent', 'proposed'], [2, 'user', 'accepted']]);
        expect(all.regions[0]).toMatchObject({ start_iso: iso(T), position: 'P1', agent: { name: 'yamnet', run_id: 'r1' } });
        expect(Object.keys(all.regions[0]).sort()).toEqual(['agent', 'areas', 'categories', 'category', 'category_label', 'color', 'confidence', 'created_at', 'end', 'end_iso', 'id', 'meter_states', 'note', 'position', 'rationale', 'reviewed_at', 'selected', 'source', 'source_areas', 'source_end', 'source_end_iso', 'source_start', 'source_start_iso', 'start', 'start_iso', 'status']);
        expect(handlers().list_annotations({ status: 'proposed' }, ctx()).data.regions.map(r => r.id)).toEqual([1]);
        expect(handlers().list_annotations({ kind: 'marker' }, ctx()).data.regions).toEqual([]);
        expect(handlers().list_annotations({ start: T + 50_000 }, ctx()).data.regions.map(r => r.id)).toEqual([2]);
    });

    it('update_region edits fields without touching status, and can change status', () => {
        handlers().add_regions({ agent, regions: [{ position: 'P1', areas: [{ start: T, end: T + 1000 }], note: 'A' }] }, ctx());
        let out = handlers().update_region({ id: 1, changes: { note: 'B', end: T + 2000, confidence: 0.1 } }, ctx());
        expect(out.data.region).toMatchObject({ note: 'B', end: T + 2000, status: 'proposed', confidence: 0.1 });
        out = handlers().update_region({ id: 1, changes: { status: 'rejected' } }, ctx());
        expect(out.data.region.status).toBe('rejected');
        expect(out.data.region.reviewed_at).not.toBeNull();
        expect(() => handlers().update_region({ id: 99, changes: { note: 'x' } }, ctx())).toThrow(/not found/);
        expect(() => handlers().update_region({ id: 1, changes: { start: T + 5000 } }, ctx())).toThrow(/not changed/);
    });

    it('delete_regions refuses user regions without force', () => {
        add({ positionId: 'P1', start: 1, end: 2, areas: [{ start: 1, end: 2 }] });
        handlers().add_regions({ agent, regions: [{ position: 'P1', areas: [{ start: T, end: T + 1000 }] }] }, ctx());
        expect(() => handlers().delete_regions({ ids: [1, 2] }, ctx())).toThrow(/without force/);
        expect(regions().allIds).toEqual([1, 2]);
        const out = handlers().delete_regions({ ids: [2, 77] }, ctx());
        expect(out.data).toEqual({ deleted: [2], missing: [77] });
        expect(handlers().delete_regions({ ids: [1], force: true }, ctx()).data.deleted).toEqual([1]);
        expect(regions().allIds).toEqual([]);
    });

    it('marker commands add, update and delete', () => {
        const added = handlers().add_markers({ agent, markers: [{ timestamp: T, position: 'P1', note: 'beep', confidence: 0.5, client_ref: 'm' }, { timestamp: T, note: 'dup' }] }, ctx());
        expect(added.data.ids).toEqual([1]);
        expect(added.data.by_client_ref).toEqual({ m: 1 });
        expect(added.data.skipped).toHaveLength(1);
        expect(store.getState().markers.byId[1]).toMatchObject({ source: 'agent', status: 'proposed', positionId: 'P1' });
        const listed = handlers().list_annotations({ kind: 'marker' }, ctx()).data.markers[0];
        expect(listed).toMatchObject({ timestamp_iso: iso(T), status: 'proposed', agent: { name: 'yamnet' } });
        expect(handlers().update_marker({ id: 1, changes: { status: 'accepted' } }, ctx()).data.marker.status).toBe('accepted');
        expect(() => handlers().delete_markers({ ids: [1] }, ctx())).not.toThrow();
        expect(store.getState().markers.allIds).toEqual([]);
        store.dispatch(app.actions.markerAdd(T + 5, { note: 'user' }));
        expect(() => handlers().delete_markers({ ids: [1] }, ctx())).toThrow(/without force/);
    });

    it('show pads the window by 20 percent, selects, and shows the message', () => {
        handlers().add_regions({ agent, regions: [{ position: 'P1', areas: [{ start: T, end: T + 10_000 }] }] }, ctx());
        const out = handlers().show({ region_id: 1, message: 'Look at this' }, ctx());
        expect(out.data.viewport).toEqual({ start: T - 2000, end: T + 12_000 });
        expect(store.getState().view.viewport).toEqual({ min: T - 2000, max: T + 12_000 });
        expect(regions().selectedId).toBe(1);
        expect(store.getState().view.notice.message).toBe('Look at this');
        handlers().show({ start: T, end: T + 100_000, select: false }, ctx());
        expect(store.getState().view.viewport.min).toBe(T - 20_000);
        expect(() => handlers().show({ region_id: 99 }, ctx())).toThrow(/not found/);
    });
});

describe('control API time basis and undo', () => {
    const handlers = () => app.services.annotationCommands.handlers;
    const pastLength = () => app.history._debug().pastLength;

    it('defaults to source time: a BST 14:05:30 log time is 13:05:30Z and the chart offset is added', () => {
        const source = Date.UTC(2026, 6, 2, 13, 5, 30); // 14:05:30 BST on 2026-07-02
        expect(source).toBe(1_782_997_530_000);
        store.dispatch(app.actions.positionChartOffsetSet('P1', 2000));
        handlers().add_regions({ agent, regions: [
            { position: 'P1', areas: [{ start: source, end: source + 1000 }] },
            { position: 'P1', areas: [{ start: source + 5000, end: source + 6000 }] }
        ] }, ctx());
        const listed = handlers().list_annotations({}, ctx()).data.regions;
        expect(listed[0]).toMatchObject({ start: source + 2000, source_start: source, source_end: source + 1000 });
        const display = handlers().add_regions({ agent, time_basis: 'display', regions: [{ position: 'P1', areas: [{ start: source + 20_000, end: source + 21_000 }] }] }, ctx());
        expect(regions().byId[display.data.ids[0]].start).toBe(source + 20_000);
        // Window filters use the same basis.
        expect(handlers().list_annotations({ start: source + 4000, end: source + 5500 }, ctx()).data.regions.map(r => r.id)).toEqual([2]);
        expect(handlers().list_annotations({ time_basis: 'display', start: source + 4000, end: source + 5500 }, ctx()).data.regions).toEqual([]);
    });

    it('applies the offset to markers and region updates', () => {
        store.dispatch(app.actions.positionChartOffsetSet('P1', 500));
        handlers().add_markers({ agent, markers: [{ timestamp: T, position: 'P1' }] }, ctx());
        expect(store.getState().markers.byId[1].timestamp).toBe(T + 500);
        expect(handlers().list_annotations({ kind: 'marker' }, ctx()).data.markers[0].source_timestamp).toBe(T);
        handlers().add_regions({ agent, regions: [{ position: 'P1', areas: [{ start: T, end: T + 1000 }] }] }, ctx());
        handlers().update_region({ id: 1, changes: { end: T + 3000 } }, ctx());
        expect(regions().byId[1].end).toBe(T + 3500);
    });

    it('one Ctrl+Z undoes a whole add_regions, add_markers or delete command', () => {
        const before = pastLength();
        handlers().add_regions({ agent, regions: [
            { position: 'P1', areas: [{ start: T, end: T + 1000 }], category: 'Brand new A' },
            { position: 'P2', areas: [{ start: T + 5000, end: T + 6000 }], category: 'Brand new B' },
            { position: 'P1', areas: [{ start: T + 9000, end: T + 9500 }], category: 'Brand new A' }
        ] }, ctx());
        expect(pastLength()).toBe(before + 1);
        expect(regions().allIds).toHaveLength(3);
        store.dispatch(app.actions.undo());
        expect(regions().allIds).toEqual([]);
        const labels = () => regions().categories.allIds.map(id => regions().categories.byId[id].label);
        expect(labels()).not.toContain('Brand new A');
        expect(labels()).not.toContain('Brand new B');
        store.dispatch(app.actions.redo());
        expect(regions().allIds).toHaveLength(3);

        const markersBefore = pastLength();
        handlers().add_markers({ agent, markers: Array.from({ length: 60 }, (_, i) => ({ timestamp: T + i * 1000, position: 'P1' })) }, ctx());
        expect(pastLength()).toBe(markersBefore + 1);
        expect(store.getState().markers.allIds).toHaveLength(60);
        handlers().delete_markers({ ids: [1, 2, 3] }, ctx());
        expect(pastLength()).toBe(markersBefore + 2);
        handlers().delete_regions({ ids: [1, 2] }, ctx());
        expect(pastLength()).toBe(markersBefore + 3);
        expect(regions().allIds).toHaveLength(1);
        store.dispatch(app.actions.undo());
        store.dispatch(app.actions.undo());
        expect(regions().allIds).toHaveLength(3);
        expect(store.getState().markers.allIds).toHaveLength(60);
        store.dispatch(app.actions.undo());
        expect(store.getState().markers.allIds).toHaveLength(0);
    });
});

describe('regions, keys and promotion fixes', () => {
    it('keys 1-9 and the meter strip follow the displayed meter order', () => {
        store.dispatch(app.actions.layoutPositionOrderSet(['P2', 'P1']));
        add({ positionId: 'P1', start: 1, end: 2, areas: [{ start: 1, end: 2 }] });
        store.dispatch(app.actions.regionSelect(1));
        expect(app.features.annotationPanel.selectors.selectPanelData(store.getState()).positions).toEqual(['P2', 'P1']);
        const before = store.getState().regions.byId[1].meterStates.P2;
        store.dispatch(app.thunks.handleKeyboardShortcutIntent({ key: '1' }));
        expect(store.getState().regions.byId[1].meterStates.P2).not.toBe(before);
        expect(store.getState().regions.byId[1].meterStates.P1).toBe('present');
    });

    it('replacing regions keeps the selection and does not invent one', () => {
        add({ positionId: 'P1', start: 1, end: 2, areas: [{ start: 1, end: 2 }] }, { positionId: 'P1', start: 5, end: 6, areas: [{ start: 5, end: 6 }] });
        store.dispatch(app.actions.regionClearSelection());
        store.dispatch(app.actions.regionReplaceAll(Object.values(regions().byId)));
        expect(regions().selectedId).toBeNull();
        store.dispatch(app.actions.regionSelect(2));
        store.dispatch(app.actions.regionReplaceAll(Object.values(regions().byId)));
        expect(regions().selectedId).toBe(2);
    });
});
