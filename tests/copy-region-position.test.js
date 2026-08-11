import { beforeEach, describe, expect, it } from 'vitest';

import './loadCoreModules.js';

const { createStore, actions, rootReducer, thunks } = window.NoiseSurveyApp;

describe('region copy position intents', () => {
    let store;

    beforeEach(() => {
        store = createStore(rootReducer);
        window.NoiseSurveyApp.store = store;
        window.NoiseSurveyApp.registry = { controllers: {}, models: {} };
        store.dispatch(actions.initializeState({
            availablePositions: ['P1', 'P2', 'P6'],
            positionDisplayTitles: { P1: 'Position 1', P2: 'Position 2', P6: 'Position 6' },
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 5000 },
            chartVisibility: {}
        }));
        store.dispatch(actions.regionsAdded([{
            positionId: 'P1',
            areas: [
                { start: 1000, end: 2000 },
                { start: 3000, end: 4500 }
            ],
            note: 'Plant cycle',
            color: '#123456'
        }]));
    });

    it('copies the selected region to only the requested available position', () => {
        store.dispatch(thunks.copyRegionToPositionIntent('P6'));

        const state = store.getState();
        expect(state.regions.allIds).toHaveLength(2);
        expect(state.regions.byId[1].positionId).toBe('P1');
        expect(state.regions.byId[2]).toMatchObject({
            positionId: 'P6',
            areas: [
                { start: 1000, end: 2000 },
                { start: 3000, end: 4500 }
            ],
            note: 'Plant cycle',
            color: '#123456'
        });
        expect(Object.values(state.regions.byId).some(region => region.positionId === 'P2')).toBe(false);
    });

    it('ignores a target position that is not available', () => {
        store.dispatch(thunks.copyRegionToPositionIntent('P9'));

        expect(store.getState().regions.allIds).toEqual([1]);
    });

    it('retains the existing copy-to-all behaviour', () => {
        store.dispatch(thunks.copyRegionToAllPositionsIntent());

        const state = store.getState();
        const copiedPositions = state.regions.allIds
            .map(id => state.regions.byId[id].positionId)
            .filter(positionId => positionId !== 'P1');
        expect(copiedPositions).toEqual(['P2', 'P6']);
    });
});
