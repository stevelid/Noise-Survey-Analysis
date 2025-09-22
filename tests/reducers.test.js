// noise_survey_analysis/static/js/tests/reducers.test.js

import { describe, it, expect } from 'vitest';

// Import source files for side effects to enable coverage tracking.
// This populates the global window.NoiseSurveyApp object.
import './loadCoreModules.js';

// Now we can safely destructure from the global object.
const { rootReducer, initialState, actions } = window.NoiseSurveyApp;

describe('rootReducer', () => {

    it('should return the initial state', () => {
        const result = rootReducer(undefined, {});
        // rootReducer always records the last action; normalize it for comparison
        const comparable = {
            ...result,
            system: { ...result.system, lastAction: null }
        };
        expect(comparable).toEqual(initialState);
    });

    describe('Interaction Actions', () => {
        it('should handle TAP action', () => {
            const state = rootReducer(initialState, actions.tap(12345, 'P1', 'line_P1'));
            expect(state.interaction.tap).toEqual({ isActive: true, timestamp: 12345, position: 'P1', sourceChartName: 'line_P1' });
        });

        it('should handle HOVER action', () => {
            const payload = { isActive: true, timestamp: 54321, position: 'P1', sourceChartName: 'line_P1', spec_y: 100 };
            const state = rootReducer(initialState, actions.hover(payload));
            expect(state.interaction.hover).toEqual(payload);
        });

        it('should handle KEY_NAV action for right navigation', () => {
            let state = {
                ...initialState,
                interaction: {
                    ...initialState.interaction,
                    tap: { isActive: true, timestamp: 10000, position: 'P1', sourceChartName: 'line_P1' }
                },
                view: {
                    ...initialState.view,
                    viewport: { min: 0, max: 20000 }
                }
            };
            const newState = rootReducer(state, actions.keyNav('right'));
            expect(newState.interaction.tap.timestamp).toBe(20000); // Should be clamped to max viewport
        });

        it('should update the active drag tool', () => {
            const state = rootReducer(initialState, actions.dragToolChanged('box_select'));
            expect(state.interaction.activeDragTool).toBe('box_select');
        });
    });

    describe('View Actions', () => {
        it('should handle VIEWPORT_CHANGE action', () => {
            const state = rootReducer(initialState, actions.viewportChange(1000, 5000));
            expect(state.view.viewport).toEqual({ min: 1000, max: 5000 });
        });

        it('should handle PARAM_CHANGE action', () => {
            const state = rootReducer(initialState, actions.paramChange('LAeq'));
            expect(state.view.selectedParameter).toBe('LAeq');
        });

        it('should handle VISIBILITY_CHANGE action', () => {
            const state = rootReducer(initialState, actions.visibilityChange('line_P1', false));
            expect(state.view.chartVisibility['line_P1']).toBe(false);
        });
    });

    describe('Comparison Mode actions', () => {
        it('should enter comparison mode with all positions included', () => {
            const baseState = {
                ...initialState,
                view: {
                    ...initialState.view,
                    availablePositions: ['P1', 'P2'],
                    comparison: { ...initialState.view.comparison, includedPositions: [] }
                }
            };
            const state = rootReducer(baseState, actions.comparisonModeEntered());
            expect(state.view.mode).toBe('comparison');
            expect(state.view.comparison.isActive).toBe(true);
            expect(state.view.comparison.includedPositions).toEqual(['P1', 'P2']);
        });

        it('should exit comparison mode and reset comparison state', () => {
            const baseState = {
                ...initialState,
                view: {
                    ...initialState.view,
                    mode: 'comparison',
                    availablePositions: ['P1'],
                    comparison: {
                        isActive: true,
                        start: 10,
                        end: 20,
                        includedPositions: ['P1']
                    }
                }
            };
            const state = rootReducer(baseState, actions.comparisonModeExited());
            expect(state.view.mode).toBe('normal');
            expect(state.view.comparison.isActive).toBe(false);
            expect(state.view.comparison.includedPositions).toEqual(['P1']);
            expect(state.view.comparison.start).toBeNull();
            expect(state.view.comparison.end).toBeNull();
        });

        it('should update included positions based on available ordering', () => {
            const baseState = {
                ...initialState,
                view: {
                    ...initialState.view,
                    mode: 'comparison',
                    availablePositions: ['P1', 'P2', 'P3'],
                    comparison: {
                        ...initialState.view.comparison,
                        isActive: true,
                        includedPositions: ['P1', 'P2']
                    }
                }
            };
            const state = rootReducer(baseState, actions.comparisonPositionsUpdated(['P3', 'P2', 'P2', 'PX']));
            expect(state.view.comparison.includedPositions).toEqual(['P2', 'P3']);
        });

        it('should update comparison slice with normalized bounds', () => {
            const baseState = {
                ...initialState,
                view: {
                    ...initialState.view,
                    comparison: {
                        ...initialState.view.comparison,
                        start: null,
                        end: null
                    }
                }
            };
            const state = rootReducer(baseState, actions.comparisonSliceUpdated(3000, 1000));
            expect(state.view.comparison.start).toBe(1000);
            expect(state.view.comparison.end).toBe(3000);
        });

        it('should clear comparison slice when bounds are invalid', () => {
            const baseState = {
                ...initialState,
                view: {
                    ...initialState.view,
                    comparison: {
                        ...initialState.view.comparison,
                        start: 1000,
                        end: 2000
                    }
                }
            };
            const state = rootReducer(baseState, actions.comparisonSliceUpdated(NaN, Infinity));
            expect(state.view.comparison.start).toBeNull();
            expect(state.view.comparison.end).toBeNull();
        });
    });

    describe('Marker Actions', () => {
        it('should handle ADD_MARKER action', () => {
            const state = rootReducer(initialState, actions.addMarker(12345));
            expect(state.markers.timestamps).toEqual([12345]);
        });

        it('should handle REMOVE_MARKER action', () => {
            let state = rootReducer(initialState, actions.addMarker(12345));
            state = rootReducer(state, actions.removeMarker(12340)); // Click near the marker
            expect(state.markers.timestamps).toEqual([]);
        });

        it('should handle CLEAR_ALL_MARKERS action', () => {
            let state = rootReducer(initialState, actions.addMarker(100));
            state = rootReducer(state, actions.addMarker(200));
            state = rootReducer(state, actions.clearAllMarkers());
            expect(state.markers.timestamps).toEqual([]);
        });
    });

    describe('Region Actions', () => {
        it('should add a region and select it', () => {
            const state = rootReducer(initialState, actions.regionAdd('P1', 2000, 1000));
            const region = state.regions.byId[1];
            expect(region.start).toBe(1000);
            expect(region.end).toBe(2000);
            expect(state.regions.selectedId).toBe(1);
        });

        it('should update region bounds and reset metrics', () => {
            let state = rootReducer(initialState, actions.regionAdd('P1', 1000, 2000));
            state = rootReducer(state, actions.regionSetMetrics(1, { laeq: 50 }));
            state = rootReducer(state, actions.regionUpdate(1, { end: 4000 }));
            const region = state.regions.byId[1];
            expect(region.end).toBe(4000);
            expect(region.metrics).toBeNull();
        });

        it('should remove a region and clear selection', () => {
            let state = rootReducer(initialState, actions.regionAdd('P1', 1000, 2000));
            state = rootReducer(state, actions.regionRemove(1));
            expect(state.regions.allIds).toHaveLength(0);
            expect(state.regions.selectedId).toBeNull();
            expect(state.regions.counter).toBe(2);
        });

        it('should continue incrementing counters after removals', () => {
            let state = rootReducer(initialState, actions.regionAdd('P1', 1000, 2000));
            state = rootReducer(state, actions.regionAdd('P1', 3000, 4000));
            expect(state.regions.counter).toBe(3);
            state = rootReducer(state, actions.regionRemove(2));
            expect(state.regions.counter).toBe(3);
            state = rootReducer(state, actions.regionAdd('P1', 5000, 6000));
            expect(state.regions.byId[3]).toBeTruthy();
            expect(state.regions.counter).toBe(4);
        });

        it('should set notes without affecting other fields', () => {
            let state = rootReducer(initialState, actions.regionAdd('P1', 1000, 2000));
            state = rootReducer(state, actions.regionSetNote(1, 'Important observation'));
            expect(state.regions.byId[1].note).toBe('Important observation');
        });

        it('should replace all regions from payload', () => {
            const regions = [
                { id: 7, positionId: 'P1', start: 100, end: 200, note: 'A' },
                { positionId: 'P2', start: 300, end: 500 }
            ];
            const state = rootReducer(initialState, actions.regionReplaceAll(regions));
            expect(state.regions.allIds).toHaveLength(2);
            expect(state.regions.byId[7].note).toBe('A');
        });

        it('should add multiple regions in a single batch', () => {
            const batch = [
                { positionId: 'P1', start: 400, end: 800 },
                { positionId: 'P2', start: 500, end: 900 }
            ];
            const state = rootReducer(initialState, actions.regionsAdded(batch));
            expect(state.regions.allIds).toEqual([1, 2]);
            expect(state.regions.byId[1]).toMatchObject({ positionId: 'P1', start: 400, end: 800 });
            expect(state.regions.byId[2]).toMatchObject({ positionId: 'P2', start: 500, end: 900 });
            expect(state.regions.counter).toBe(3);
            expect(state.regions.selectedId).toBe(1);
        });

        it('should clear regions when replace payload is empty', () => {
            let state = rootReducer(initialState, actions.regionAdd('P1', 100, 200));
            state = rootReducer(state, actions.regionReplaceAll([]));
            expect(state.regions.allIds).toEqual([]);
        });
    });

    describe('Audio Actions', () => {
        it('should handle AUDIO_STATUS_UPDATE action', () => {
            const status = {
                is_playing: [true],
                active_position_id: ['P1'],
                current_time: [123],
                playback_rate: [1.5],
                volume_boost: [true]
            };
            const state = rootReducer(initialState, actions.audioStatusUpdate(status));
            expect(state.audio.isPlaying).toBe(true);
            expect(state.audio.activePositionId).toBe('P1');
            expect(state.interaction.tap.timestamp).toBe(123);
        });

        it('should handle AUDIO_PLAY_PAUSE_TOGGLE action for playing', () => {
            const state = rootReducer(initialState, actions.audioPlayPauseToggle('P1', true));
            expect(state.audio.isPlaying).toBe(true);
            expect(state.audio.activePositionId).toBe('P1');
        });
    });
});