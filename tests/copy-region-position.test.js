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

    it('marks the selected sound present only at the requested available meter', () => {
        store.dispatch(thunks.copyRegionToPositionIntent('P6'));

        const state = store.getState();
        expect(state.regions.allIds).toHaveLength(1);
        expect(state.regions.byId[1].positionId).toBe('P1');
        expect(state.regions.byId[1]).toMatchObject({
            positionId: 'P1',
            meterStates: { P1: 'present', P2: 'unchecked', P6: 'present' },
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

    it('marks the same region present at all meters without creating copies', () => {
        store.dispatch(thunks.copyRegionToAllPositionsIntent());

        const state = store.getState();
        expect(state.regions.allIds).toEqual([1]);
        expect(state.regions.byId[1].meterStates).toEqual({ P1: 'present', P2: 'present', P6: 'present' });
    });
});
