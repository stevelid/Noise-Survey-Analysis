import { beforeEach, describe, expect, it } from 'vitest';
import '../noise_survey_analysis/static/js/features/regions/annotationModel.js';
import './loadCoreModules.js';

const app = window.NoiseSurveyApp;
const model = app.annotationModel;
const positions = ['P1', 'P2', 'P3', 'P4'];
const intents = app.features.regions.thunks;

function region(overrides = {}) {
    return { id: 1, positionId: 'P1', areas: [{ start: 1000, end: 2000 }], note: '', ...overrides };
}

function freshStore() {
    const store = app.createStore(app.rootReducer);
    app.store = store;
    app.registry = { models: {}, controllers: {} };
    store.dispatch(app.actions.initializeState({
        availablePositions: positions,
        positionDisplayTitles: { P3: 'Rear boundary' },
        selectedParameter: 'LZeq', viewport: { min: 0, max: 10000 }, chartVisibility: {}
    }));
    return store;
}

beforeEach(() => app.history.reset());

describe('annotation normalization', () => {
    it('sets origin present and other meters unchecked, retaining unavailable meter states', () => {
        expect(model.normalizeRegion(region({ meterStates: { P1: 'absent', P9: 'absent' } }), positions)).toMatchObject({
            categoryId: 'other', color: null,
            meterStates: { P1: 'present', P2: 'unchecked', P3: 'unchecked', P4: 'unchecked', P9: 'absent' }
        });
    });

    it('uses category colour unless there is a valid override', () => {
        const catalog = model.normalizeCatalog();
        expect(model.effectiveColor({ categoryId: 'plant', color: null }, catalog)).toBe('#388e3c');
        expect(model.effectiveColor({ categoryId: 'plant', color: '#abcdef' }, catalog)).toBe('#abcdef');
        expect(model.normalizeColor('red; background:url(example)')).toBeNull();
        expect(model.normalizeColor('" onmouseover="alert(1)')).toBeNull();
    });

    it('normalizes overlapping areas without changing input and rejects zero width', () => {
        const original = region({ areas: [{ start: 3000, end: 1000 }, { start: 2000, end: 4000 }] });
        const before = JSON.stringify(original);
        expect(model.normalizeRegion(original).areas).toEqual([{ start: 1000, end: 4000 }]);
        expect(JSON.stringify(original)).toBe(before);
        expect(model.normalizeRegion(region({ areas: [{ start: 1, end: 1 }] }))).toBeNull();
    });

    it('keeps catalog IDs through renaming and guarantees Other', () => {
        const catalog = model.normalizeCatalog([{ id: 'road', label: 'Traffic noise', color: '#123456' }]);
        expect(catalog.allIds).toEqual(['road', 'other']);
        expect(catalog.byId.road.label).toBe('Traffic noise');
        expect(model.normalizeCatalog([{ id: '__proto__', label: 'unsafe' }]).allIds).toEqual(['other']);
    });

    it.each([
        ['unchecked', 'unchecked', 'unchecked', false],
        ['unchecked', 'present', 'present', false],
        ['unchecked', 'absent', 'absent', false],
        ['present', 'unchecked', 'present', false],
        ['absent', 'unchecked', 'absent', false],
        ['present', 'present', 'present', false],
        ['absent', 'absent', 'absent', false],
        ['present', 'absent', 'unchecked', true],
        ['absent', 'present', 'unchecked', true]
    ])('merges %s and %s as %s', (left, right, expected, conflict) => {
        expect(model.mergeMeterStates({ P2: left }, { P2: right }, ['P2'])).toEqual({
            states: { P2: expected }, conflicts: conflict ? ['P2'] : []
        });
    });

    it('consolidates legacy copies within 1 ms using fixed representatives and nonempty evidence', () => {
        const copies = [
            region({ note: 'Dog  bark', color: '#111111' }),
            region({ id: 2, positionId: 'P2', note: 'Dog bark', color: '#222222', areas: [{ start: 1001, end: 2001 }] }),
            region({ id: 3, positionId: 'P3', note: 'Dog bark', color: '#333333', areas: [{ start: 1002, end: 2002 }] })
        ];
        const result = model.consolidateLegacyRegions(copies, positions);
        expect(result.mergedCount).toBe(1);
        expect(result.regions).toHaveLength(2);
        expect(result.regions[0].meterStates).toMatchObject({ P1: 'present', P2: 'present', P3: 'unchecked' });
        expect(model.consolidateLegacyRegions([
            region({ color: '#111111' }), region({ id: 2, positionId: 'P2', color: '#222222' })
        ], positions).mergedCount).toBe(0);
        expect(model.consolidateLegacyRegions([
            region({ note: 'same' }), region({ id: 2, note: 'same' })
        ], positions).mergedCount).toBe(0);
    });
});

describe('annotation operations and history', () => {
    it('changes meter states and categories undoably, preserving the origin', () => {
        const store = freshStore();
        store.dispatch(app.actions.regionsAdded([region()]));
        app.history.reset();
        store.dispatch(intents.setRegionMeterStateIntent(1, 'P2', 'absent'));
        store.dispatch(intents.setRegionCategoryIntent(1, 'traffic'));
        expect(store.getState().regions.byId[1]).toMatchObject({ categoryId: 'traffic', meterStates: { P2: 'absent' } });
        store.dispatch(app.actions.undo());
        expect(store.getState().regions.byId[1].categoryId).toBe('other');
        store.dispatch(app.actions.undo());
        expect(store.getState().regions.byId[1].meterStates.P2).toBeUndefined();
        store.dispatch(intents.setRegionMeterStateIntent(1, 'P1', 'absent'));
        expect(store.getState().regions.byId[1].meterStates.P1).toBe('present');
    });

    it('deletes a category and reassigns its regions in one undo step', () => {
        const store = freshStore();
        store.dispatch(app.actions.regionsAdded([region({ categoryId: 'plant' })]));
        app.history.reset();
        store.dispatch(intents.deleteCategoryIntent('plant'));
        expect(store.getState().regions.categories.byId.plant).toBeUndefined();
        expect(store.getState().regions.byId[1].categoryId).toBe('other');
        expect(app.history._debug().pastLength).toBe(1);
        store.dispatch(app.actions.undo());
        expect(store.getState().regions.categories.byId.plant).toBeDefined();
        expect(store.getState().regions.byId[1].categoryId).toBe('plant');
    });

    it('merges in one transition and reports contradictory meter states for re-check', () => {
        const store = freshStore();
        store.dispatch(app.actions.regionsAdded([
            region({ note: 'First', categoryId: 'plant', color: '#123456', meterStates: { P2: 'unchecked', P3: 'present', P4: 'absent' } }),
            region({ id: 2, note: 'Second', areas: [{ start: 3000, end: 4000 }], meterStates: { P2: 'present', P3: 'absent', P4: 'unchecked' } })
        ]));
        store.dispatch(app.actions.regionSelect(1));
        store.dispatch(app.actions.regionSetAddAreaMode(2));
        const original = structuredClone(store.getState().regions);
        app.history.reset();
        store.dispatch(intents.mergeRegionIntoSelectedIntent(2));
        expect(app.history._debug().pastLength).toBe(1);
        expect(store.getState().regions.byId[1]).toMatchObject({
            id: 1, positionId: 'P1', categoryId: 'plant', color: '#123456', note: 'First\nSecond',
            meterStates: { P1: 'present', P2: 'present', P3: 'unchecked', P4: 'absent' },
            areas: [{ start: 1000, end: 2000 }, { start: 3000, end: 4000 }]
        });
        expect(store.getState().view.notice.message).toContain('Rear boundary');
        expect(store.getState().regions.addAreaTargetId).toBeNull();
        store.dispatch(app.actions.undo());
        expect(store.getState().regions).toEqual(original);
        store.dispatch(app.actions.redo());
        expect(store.getState().regions.allIds).toEqual([1]);
    });

    it('splits atomically, retaining category, colour and states for each area', () => {
        const store = freshStore();
        store.dispatch(app.actions.regionsAdded([region({ categoryId: 'plant', color: '#123456', meterStates: { P2: 'absent' },
            areas: [{ start: 1000, end: 2000 }, { start: 3000, end: 4000 }] })]));
        app.history.reset();
        store.dispatch(intents.splitSelectedRegionIntent());
        expect(app.history._debug().pastLength).toBe(1);
        const regions = Object.values(store.getState().regions.byId);
        expect(regions).toHaveLength(2);
        regions.forEach(item => expect(item).toMatchObject({ categoryId: 'plant', color: '#123456', meterStates: { P2: 'absent' } }));
        store.dispatch(app.actions.undo());
        expect(store.getState().regions.allIds).toEqual([1]);
        expect(store.getState().regions.byId[1].areas).toHaveLength(2);
    });

    it('creates a single comparison region and marks included meters present', () => {
        const store = freshStore();
        store.dispatch(app.actions.comparisonModeEntered());
        store.dispatch(app.actions.comparisonPositionsUpdated(['P3', 'P1']));
        store.dispatch(app.actions.comparisonSliceUpdated(1000, 2000));
        store.dispatch(intents.createRegionsFromComparisonIntent());
        expect(store.getState().regions.allIds).toHaveLength(1);
        expect(store.getState().regions.byId[1]).toMatchObject({
            positionId: 'P1', meterStates: { P1: 'present', P2: 'unchecked', P3: 'present', P4: 'unchecked' }
        });
    });

    it('keeps categories when replacing the region list', () => {
        const store = freshStore();
        const id = store.dispatch(intents.createCategoryIntent({ label: 'Aircraft', color: '#abcdef' }));
        store.dispatch(app.actions.regionReplaceAll([]));
        expect(store.getState().regions.categories.byId[id].label).toBe('Aircraft');
    });
});

describe('civil-time automatic periods', () => {
    it('includes the first partial night and handles spring/autumn clock changes', () => {
        const build = app.features.regions.__test__.buildDailyIntervals;
        const spring = build({ min: Date.parse('2026-03-28T23:00:00Z'), max: Date.parse('2026-03-29T08:00:00Z'), count: 1 }, 'nighttime');
        expect(spring).toEqual([{ start: Date.parse('2026-03-28T23:00:00Z'), end: Date.parse('2026-03-29T06:00:00Z') }]);
        const autumn = build({ min: Date.parse('2026-10-24T22:00:00Z'), max: Date.parse('2026-10-25T08:00:00Z'), count: 1 }, 'nighttime');
        expect(autumn).toEqual([{ start: Date.parse('2026-10-24T22:00:00Z'), end: Date.parse('2026-10-25T07:00:00Z') }]);
    });
});
