import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Import source files for side effects to enable coverage tracking.
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/services/eventHandlers.js';

// Now we can safely destructure from the global object.
const { createStore, actions, rootReducer, eventHandlers } = window.NoiseSurveyApp;

describe('NoiseSurveyApp.eventHandlers', () => {
    let store;
    let dispatchSpy;
    let handleTapIntentSpy;
    let createRegionIntentSpy;
    let resizeSelectedRegionIntentSpy;
    let nudgeTapLineIntentSpy;
    let updateComparisonSliceIntentSpy;
    let createRegionsFromComparisonIntentSpy;
    let togglePlayPauseIntentSpy;
    let changePlaybackRateIntentSpy;
    let toggleVolumeBoostIntentSpy;

    beforeEach(() => {
        vi.useFakeTimers();

        // Create a fresh store and spy for each test
        store = createStore(rootReducer);
        dispatchSpy = vi.spyOn(store, 'dispatch');

        // Mock the global app object that event handlers expect
        window.NoiseSurveyApp.store = store;
        window.NoiseSurveyApp.registry = {
            models: {
                audio_control_source: { data: {} },
                audio_status_source: { data: {} }
            },
            controllers: {
                chartsByName: new Map()
            }
        };

        handleTapIntentSpy = vi.spyOn(window.NoiseSurveyApp.thunks, 'handleTapIntent').mockImplementation(() => () => {});
        createRegionIntentSpy = vi.spyOn(window.NoiseSurveyApp.thunks, 'createRegionIntent').mockImplementation(() => () => {});
        resizeSelectedRegionIntentSpy = vi.spyOn(window.NoiseSurveyApp.thunks, 'resizeSelectedRegionIntent').mockImplementation(() => () => {});
        nudgeTapLineIntentSpy = vi.spyOn(window.NoiseSurveyApp.thunks, 'nudgeTapLineIntent').mockImplementation(() => () => {});
        updateComparisonSliceIntentSpy = vi.spyOn(window.NoiseSurveyApp.thunks, 'updateComparisonSliceIntent').mockImplementation(() => () => {});
        createRegionsFromComparisonIntentSpy = vi.spyOn(window.NoiseSurveyApp.thunks, 'createRegionsFromComparisonIntent').mockImplementation(() => () => {});
        togglePlayPauseIntentSpy = vi.spyOn(window.NoiseSurveyApp.thunks, 'togglePlayPauseIntent').mockImplementation(() => () => {});
        changePlaybackRateIntentSpy = vi.spyOn(window.NoiseSurveyApp.thunks, 'changePlaybackRateIntent').mockImplementation(() => () => {});
        toggleVolumeBoostIntentSpy = vi.spyOn(window.NoiseSurveyApp.thunks, 'toggleVolumeBoostIntent').mockImplementation(() => () => {});
    });

    afterEach(() => {
        vi.useRealTimers();
        vi.restoreAllMocks();
        vi.clearAllMocks();
    });

    describe('handleTap', () => {
        it('should dispatch a TAP intent', () => {
            const cb_obj = { origin: { name: 'figure_P1_timeseries' }, x: 12345 };
            eventHandlers.handleTap(cb_obj);
            expect(handleTapIntentSpy).toHaveBeenCalledWith({
                timestamp: 12345,
                positionId: 'P1',
                chartName: 'figure_P1_timeseries',
                modifiers: { ctrl: false }
            });
            expect(dispatchSpy).toHaveBeenCalledWith(expect.any(Function));
        });

        it('should dispatch a ctrl+tap intent when ctrl held', () => {
            const cb_obj = { origin: { name: 'figure_P1_timeseries' }, x: 12345, modifiers: { ctrl: true } };
            eventHandlers.handleTap(cb_obj);
            expect(handleTapIntentSpy).toHaveBeenCalledWith({
                timestamp: 12345,
                positionId: 'P1',
                chartName: 'figure_P1_timeseries',
                modifiers: { ctrl: true }
            });
            expect(dispatchSpy).toHaveBeenCalledWith(expect.any(Function));
        });
    });

    describe('handleRegionBoxSelect', () => {
        it('should add a region when shift-drag completes (shiftKey flag)', () => {
            const geometryEvent = {
                model: { name: 'figure_P1_timeseries' },
                final: true,
                shiftKey: true,
                geometry: { type: 'rect', x0: 1000, x1: 2000 }
            };
            eventHandlers.handleRegionBoxSelect(geometryEvent);
            expect(updateComparisonSliceIntentSpy).toHaveBeenCalledWith({
                start: 1000,
                end: 2000,
                positionId: 'P1',
                sourceChartName: 'figure_P1_timeseries',
                final: true
            });
            expect(createRegionIntentSpy).toHaveBeenCalledWith({
                positionId: 'P1',
                start: 1000,
                end: 2000
            });
            expect(dispatchSpy).toHaveBeenCalledTimes(2);
        });

        it('should ignore drag updates until final shift release', () => {
            const geometryEvent = {
                model: { name: 'figure_P1_timeseries' },
                final: false,
                modifiers: { shift: true },
                geometry: { type: 'rect', x0: 1000, x1: 2000 }
            };
            eventHandlers.handleRegionBoxSelect(geometryEvent);
            expect(updateComparisonSliceIntentSpy).toHaveBeenCalledWith({
                start: 1000,
                end: 2000,
                positionId: 'P1',
                sourceChartName: 'figure_P1_timeseries',
                final: false
            });
            expect(createRegionIntentSpy).not.toHaveBeenCalled();
            expect(dispatchSpy).toHaveBeenCalledTimes(1);
        });
    });

    describe('handleComparisonMakeRegions', () => {
        it('should dispatch the createRegionsFromComparisonIntent thunk', () => {
            eventHandlers.handleComparisonMakeRegions();
            expect(createRegionsFromComparisonIntentSpy).toHaveBeenCalledWith();
            expect(dispatchSpy).toHaveBeenCalledWith(expect.any(Function));
        });
    });

    describe('handleDoubleClick', () => {
        it('should dispatch an ADD_MARKER action', () => {
            const cb_obj = { origin: { name: 'figure_P1_timeseries' }, x: 54321 };
            eventHandlers.handleDoubleClick(cb_obj);
            expect(dispatchSpy).toHaveBeenCalledWith(actions.addMarker(54321));
        });
    });

    describe('handleRangeUpdate', () => {
        it('should dispatch a VIEWPORT_CHANGE action after debounce', () => {
            const cb_obj = { start: 100, end: 200 };
            eventHandlers.handleRangeUpdate(cb_obj);
            vi.advanceTimersByTime(250);
            expect(dispatchSpy).toHaveBeenCalledWith(actions.viewportChange(100, 200));
        });
    });

    describe('handleParameterChange', () => {
        it('should dispatch a PARAM_CHANGE action', () => {
            eventHandlers.handleParameterChange('LAeq');
            expect(dispatchSpy).toHaveBeenCalledWith(actions.paramChange('LAeq'));
        });
    });

    describe('handleVisibilityChange', () => {
        it('should dispatch a VISIBILITY_CHANGE action', () => {
            const cb_obj = { active: [0] }; // Represents 'visible'
            eventHandlers.handleVisibilityChange(cb_obj, 'line_P1');
            expect(dispatchSpy).toHaveBeenCalledWith(actions.visibilityChange('line_P1', true));
        });
    });

    describe('handleAudioStatusUpdate', () => {
        it('should dispatch an AUDIO_STATUS_UPDATE action', () => {
            const mockStatus = {
                is_playing: [true],
                active_position_id: ['P1'],
                current_time: [123],
                playback_rate: [1.0],
                volume_boost: [false]
            };
            window.NoiseSurveyApp.registry.models.audio_status_source.data = mockStatus;
            eventHandlers.handleAudioStatusUpdate();
            expect(dispatchSpy).toHaveBeenCalledWith(actions.audioStatusUpdate(mockStatus));
        });
    });

    describe('togglePlayPause', () => {
        it('should dispatch the togglePlayPauseIntent thunk', () => {
            const payload = { positionId: 'P1', isActive: true };
            eventHandlers.togglePlayPause(payload);
            expect(togglePlayPauseIntentSpy).toHaveBeenCalledWith(payload);
            expect(dispatchSpy).toHaveBeenCalledWith(expect.any(Function));
        });
    });

    describe('handleKeyPress', () => {
        it('should dispatch KEY_NAV action on ArrowLeft', () => {
            // Set initial state for tap to be active
            window.NoiseSurveyApp.store.dispatch(actions.tap(10000, 'P1', 'line_P1'));
            const event = { key: 'ArrowLeft', preventDefault: vi.fn(), target: { tagName: 'div' } };
            eventHandlers.handleKeyPress(event);
            expect(event.preventDefault).toHaveBeenCalled();
            expect(nudgeTapLineIntentSpy).toHaveBeenCalledWith({ key: 'ArrowLeft' });
        });

        it('should nudge the right edge when alt+ArrowRight is pressed', () => {
            const event = { key: 'ArrowRight', altKey: true, ctrlKey: false, preventDefault: vi.fn(), target: { tagName: 'div' } };
            eventHandlers.handleKeyPress(event);
            expect(event.preventDefault).toHaveBeenCalled();
            expect(resizeSelectedRegionIntentSpy).toHaveBeenCalledWith({
                key: 'ArrowRight',
                modifiers: { alt: true }
            });
        });

        it('should nudge the left edge when ctrl+ArrowLeft is pressed', () => {
            const event = { key: 'ArrowLeft', ctrlKey: true, altKey: false, preventDefault: vi.fn(), target: { tagName: 'div' } };
            eventHandlers.handleKeyPress(event);
            expect(event.preventDefault).toHaveBeenCalled();
            expect(resizeSelectedRegionIntentSpy).toHaveBeenCalledWith({
                key: 'ArrowLeft',
                modifiers: { ctrl: true }
            });
        });
    });
});