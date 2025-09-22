
import { describe, it, expect, beforeEach, vi } from 'vitest';

import './loadCoreModules.js';

// Load necessary modules from the app's namespace
const {
    regionsReducer,
    initialState: initialRegionsState
} = window.NoiseSurveyApp.features.regions;
const { actions } = window.NoiseSurveyApp;
const {
    createRegionIntent,
    mergeRegionIntoSelectedIntent
} = window.NoiseSurveyApp.features.regions.thunks;
const {
    selectRegionByTimestamp
} = window.NoiseSurveyApp.features.regions.selectors;


describe('Region Management (Multi-Area)', () => {

    let state;

    beforeEach(() => {
        state = initialRegionsState;
    });

    describe('Regions Reducer', () => {

        it('should handle initial state', () => {
            expect(regionsReducer(undefined, {})).toEqual(initialRegionsState);
        });

        it('should handle REGION_ADDED', () => {
            const action = actions.regionAdd('P1', 100, 200);
            const newState = regionsReducer(state, action);
            expect(newState.allIds).toHaveLength(1);
            const region = newState.byId[newState.allIds[0]];
            expect(region.positionId).toBe('P1');
            expect(region.areas).toEqual([{ start: 100, end: 200 }]);
            expect(region.start).toBe(100);
            expect(region.end).toBe(200);
            expect(region.color).toBe('#1e88e5');
        });

        it('should handle REGION_UPDATED with new areas', () => {
            // First, add a region
            let newState = regionsReducer(state, actions.regionAdd('P1', 100, 200));
            const regionId = newState.allIds[0];

            // Now, update it with new areas
            const updatedAreas = [{ start: 50, end: 150 }, { start: 180, end: 250 }];
            const action = actions.regionUpdate(regionId, { areas: updatedAreas });
            newState = regionsReducer(newState, action);

            const updatedRegion = newState.byId[regionId];
            expect(updatedRegion.areas).toEqual([{ start: 50, end: 150 }, { start: 180, end: 250 }]);
            expect(updatedRegion.start).toBe(50);
            expect(updatedRegion.end).toBe(250);
        });

        it('should handle REGION_REMOVED', () => {
            let newState = regionsReducer(state, actions.regionAdd('P1', 100, 200));
            const regionId = newState.allIds[0];
            const action = actions.regionRemove(regionId);
            newState = regionsReducer(newState, action);
            expect(newState.allIds).toHaveLength(0);
            expect(newState.byId[regionId]).toBeUndefined();
        });

        it('should handle REGION_ADD_AREA_MODE_SET', () => {
            let newState = regionsReducer(state, actions.regionAdd('P1', 100, 200));
            const regionId = newState.allIds[0];
            const action = actions.regionSetAddAreaMode(regionId);
            newState = regionsReducer(newState, action);
            expect(newState.addAreaTargetId).toBe(regionId);
        });

        it('should handle REGION_COLOR_SET', () => {
            let newState = regionsReducer(state, actions.regionAdd('P1', 100, 200));
            const regionId = newState.allIds[0];
            newState = regionsReducer(newState, actions.regionSetColor(regionId, '#ff00ff'));
            expect(newState.byId[regionId].color).toBe('#ff00ff');
        });
    });

    describe('Region Thunks', () => {

        it('createRegionIntent should add a new area to a target region', () => {
            const dispatch = vi.fn();
            const getState = () => ({
                regions: {
                    ...initialRegionsState,
                    byId: { 1: { id: 1, positionId: 'P1', areas: [{ start: 100, end: 200 }] } },
                    allIds: [1],
                    addAreaTargetId: 1,
                    selectedId: null
                }
            });

            const thunk = createRegionIntent({ positionId: 'P1', start: 250, end: 300 });
            thunk(dispatch, getState);

            expect(dispatch).toHaveBeenCalledWith(
                actions.regionUpdate(1, { areas: [{ start: 100, end: 200 }, { start: 250, end: 300 }] })
            );
            expect(dispatch).toHaveBeenCalledWith(actions.regionSelect(1));
            expect(dispatch).not.toHaveBeenCalledWith(actions.regionSetAddAreaMode(null));
        });

        it('mergeRegionIntoSelectedIntent should merge two regions', () => {
            const dispatch = vi.fn();
            const getState = () => ({
                regions: {
                    ...initialRegionsState,
                    byId: {
                        1: { id: 1, positionId: 'P1', areas: [{ start: 100, end: 200 }] },
                        2: { id: 2, positionId: 'P1', areas: [{ start: 300, end: 400 }] }
                    },
                    allIds: [1, 2],
                    selectedId: 1
                }
            });

            const thunk = mergeRegionIntoSelectedIntent(2);
            thunk(dispatch, getState);

            expect(dispatch).toHaveBeenCalledWith(
                actions.regionUpdate(1, { areas: [{ start: 100, end: 200 }, { start: 300, end: 400 }] })
            );
            expect(dispatch).toHaveBeenCalledWith(actions.regionRemove(2));
        });
    });

    describe('Region Selectors', () => {

        it('selectRegionByTimestamp should find a region with multiple areas', () => {
            const currentState = {
                regions: {
                    ...initialRegionsState,
                    byId: {
                        1: {
                            id: 1,
                            positionId: 'P1',
                            areas: [{ start: 100, end: 200 }, { start: 300, end: 400 }]
                        }
                    },
                    allIds: [1]
                }
            };

            // Timestamp within the first area
            let region = selectRegionByTimestamp(currentState, 'P1', 150);
            expect(region).not.toBeNull();
            expect(region.id).toBe(1);

            // Timestamp within the second area
            region = selectRegionByTimestamp(currentState, 'P1', 350);
            expect(region).not.toBeNull();
            expect(region.id).toBe(1);

            // Timestamp between areas
            region = selectRegionByTimestamp(currentState, 'P1', 250);
            expect(region).toBeNull();
        });
    });
});
