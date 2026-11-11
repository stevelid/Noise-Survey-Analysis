import { beforeEach, describe, expect, it } from 'vitest';
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/features/annotations/panelSelectors.js';
import '../noise_survey_analysis/static/js/features/annotations/panelThunks.js';
const app = window.NoiseSurveyApp;
const intents = app.features.regions.thunks;
const panel = app.features.annotationPanel;
let store;
const records = [
 { id: 1, positionId: 'P1', start: 10000, end: 20000, note: 'Dog', categoryId: 'dog-bark', color: '#abcdef', meterStates: { P1: 'present', P2: 'present' } },
 { id: 2, positionId: 'P1', start: 15000, end: 25000, note: 'Traffic', categoryId: 'traffic', meterStates: { P1: 'present', P2: 'absent' } },
 { id: 3, positionId: 'P1', start: 30000, end: 40000, note: 'Plant', categoryId: 'plant', meterStates: { P1: 'present', P2: 'present' } }
];
beforeEach(() => {
 app.history.reset();
 store = app.createStore(app.rootReducer); app.store = store;
 app.registry = { models: {}, controllers: {} };
 store.dispatch(app.actions.initializeState({ availablePositions: ['P1', 'P2'], viewport: { min: 0, max: 50000 }, selectedParameter: 'LZeq' }));
 store.dispatch(app.actions.regionsAdded(records)); store.dispatch(app.actions.regionSelect(1)); app.history.reset();
});
describe('reversible multi-region merge', () => {
 it('merges atomically and restores original overlapping geometry, notes, categories, colours and checks', () => {
  const before = structuredClone(store.getState().regions.byId);
  store.dispatch(intents.mergeRegionsIntent([1, 2, 3]));
  expect(app.history._debug().pastLength).toBe(1);
  expect(store.getState().regions.byId[1].meterStates.P2).toBe('unchecked');
  expect(store.getState().regions.byId[1].areas).toEqual([{ start: 10000, end: 25000 }, { start: 30000, end: 40000 }]);
  store.dispatch(app.actions.regionSetNote(1, 'An edit after merge'));
  store.dispatch(intents.unmergeSelectedRegionIntent());
  expect(store.getState().regions.byId).toEqual(before);
  expect(store.getState().regions.selectedId).toBe(1);
  store.dispatch(app.actions.undo());
  expect(store.getState().regions.byId[1].note).toBe('An edit after merge');
 });
 it('rejects different origin meters without changing regions', () => {
  store.dispatch(app.actions.regionsAdded([{ ...records[2], id: 4, positionId: 'P2' }]));
  const before = store.getState().regions;
  store.dispatch(intents.mergeRegionsIntent([1, 4]));
  expect(store.getState().regions).toBe(before);
 });
 it('restores an earlier merged object, then its originals, after workspace and CSV round trips', () => {
  store.dispatch(intents.mergeRegionsIntent([1, 2]));
  const firstMerge = structuredClone(store.getState().regions.byId[1]);
  store.dispatch(intents.mergeRegionsIntent([1, 3]));
  const payload = {version: 2, appState: JSON.parse(JSON.stringify(store.getState()))};
  const restored = app.workspaceMigration.migrateWorkspace(payload).payload.appState;
  store.dispatch(app.actions.rehydrateState(restored));
  const csv = app.annotationCsv.buildAnnotationsCsv([], Object.values(store.getState().regions.byId), store.getState());
  const parsed = app.annotationCsv.parseAnnotationsCsv(csv);
  store.dispatch(app.actions.regionReplaceAll(parsed.regions)); store.dispatch(app.actions.regionSelect(1));
  store.dispatch(intents.unmergeSelectedRegionIntent());
  expect(store.getState().regions.byId[1]).toEqual(firstMerge);
  store.dispatch(intents.unmergeSelectedRegionIntent());
  expect(Object.values(store.getState().regions.byId).map(r => r.note).sort()).toEqual(['Dog', 'Plant', 'Traffic']);
 });
 it('preserves provenance through region JSON and avoids overwriting colliding IDs on unmerge', () => {
  store.dispatch(intents.mergeRegionsIntent([1, 2]));
  const merged = store.getState().regions.byId[1];
  const json = app.features.regions.utils.exportRegions(store.getState(), {}, {});
  const imported = app.features.regions.utils.importRegions(json);
  expect(imported.find(r => r.id === 1).mergeSources).toEqual(merged.mergeSources);
  store.dispatch(app.actions.regionsAdded([{ ...records[2], id: 2, note: 'Unrelated' }]));
  store.dispatch(app.actions.regionSelect(1)); store.dispatch(intents.unmergeSelectedRegionIntent());
  expect(store.getState().regions.byId[2].note).toBe('Unrelated');
  expect(Object.values(store.getState().regions.byId).map(r => r.note)).toContain('Traffic');
  expect(store.getState().regions.counter).toBeGreaterThan(Math.max(...store.getState().regions.allIds));
 });
 it('adds and applies an inline category and plays exactly from the selected origin start', () => {
  store.dispatch(panel.thunks.panelCommandIntent('create-region-category', { label: 'Aircraft', color: '#123456' }));
  expect(store.getState().regions.byId[1].categoryId).toBe('aircraft');
  expect(store.getState().regions.categories.byId.aircraft.label).toBe('Aircraft');
  store.dispatch(intents.playSelectedRegionIntent());
  expect(store.getState().interaction.tap).toMatchObject({ timestamp: 10000, position: 'P1' });
  expect(store.getState().audio).toMatchObject({ isPlaying: true, activePositionId: 'P1' });
 });
});
