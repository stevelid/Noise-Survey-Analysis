// noise_survey_analysis/static/js/tests/reducers.test.js

import { describe, it, expect } from 'vitest';

// Import source files for side effects to enable coverage tracking.
// This populates the global window.NoiseSurveyApp object.
import '../noise_survey_analysis/static/js/actions.js';
import '../noise_survey_analysis/static/js/reducers.js';

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