import { describe, it, expect } from 'vitest';
import './loadCoreModules.js';

const app = window.NoiseSurveyApp;
const region = (id, positionId, start = 1000) => ({ id, positionId, start, end: 2000, note: 'Dog', color: '#e65100' });
function workspace(version = 1) {
    return { version, sourceConfigs: [], appState: { view: { availablePositions: ['P1', 'P2', 'P3'] },
        regions: { allIds: [1, 2], byId: { 1: region(1, 'P1'), 2: region(2, 'P2', 1001) } } } };
}

describe('workspace v2 upgrades', () => {
    it('consolidates legacy copies, preserves input and assigns unchecked meters', () => {
        const payload = workspace();
        const original = JSON.stringify(payload);
        const result = app.workspaceMigration.migrateWorkspace(payload);
        expect(JSON.stringify(payload)).toBe(original);
        expect(result.mergedCount).toBe(1);
        expect(result.payload.version).toBe(2);
        expect(result.payload.appState.regions.byId[1].meterStates).toEqual({ P1: 'present', P2: 'present', P3: 'unchecked' });
        expect(result.payload.appState.regions.byId[1].color).toBe('#e65100');
    });
    it('never consolidates distinct v2 annotations or accepts a future version', () => {
        expect(app.workspaceMigration.migrateWorkspace(workspace(2)).mergedCount).toBe(0);
        expect(() => app.workspaceMigration.migrateWorkspace(workspace(3))).toThrow('Unsupported workspace version');
    });
    it('does not join across tolerance chains or the same origin', () => {
        const payload = workspace();
        payload.appState.regions.byId[3] = region(3, 'P3', 1002);
        payload.appState.regions.allIds.push(3);
        const result = app.workspaceMigration.migrateWorkspace(payload);
        expect(result.mergedCount).toBe(1);
        expect(result.payload.appState.regions.allIds).toHaveLength(2);
        payload.appState.regions.byId[2].positionId = 'P1';
        delete payload.appState.regions.byId[3];
        payload.appState.regions.allIds = [1, 2];
        expect(app.workspaceMigration.migrateWorkspace(payload).mergedCount).toBe(0);
    });
    it('caches separately for each target meter and explicit resolution', () => {
        const entity = region(1, 'P1');
        const source = value => ({ data: { Datetime: [1000, 1500], LAeq: [value, value] } });
        const models = { timeSeriesSources: {
            P1: { log: source(40), overview: source(50) },
            P2: { log: source(60), overview: source(70) },
        } };
        const state = { view: { selectedParameter: 'LAeq' } };
        const utils = app.features.regions.utils;
        utils.invalidateMetricsCache();
        expect(utils.getRegionMetrics(entity, state, {}, models, { positionId: 'P1' }).laeq).toBeCloseTo(40);
        expect(utils.getRegionMetrics(entity, state, {}, models, { positionId: 'P2' }).laeq).toBeCloseTo(60);
        expect(utils.getRegionMetrics(entity, state, {}, models, { positionId: 'P2', resolution: 'overview' }).laeq).toBeCloseTo(70);
    });
});
