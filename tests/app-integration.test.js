import { describe, it, expect, beforeEach, vi } from 'vitest';

// --- STEP 1: DEFINE THE MOCKS ---
// We will manually attach these to the window object.
const mockRenderers = {
    renderPrimaryCharts: vi.fn(),
    renderOverlays: vi.fn(),
    renderFrequencyBar: vi.fn(),
    renderMarkers: vi.fn(),
    renderControlWidgets: vi.fn(),
    renderRegions: vi.fn(),
};


// --- STEP 2: MANUALLY SET UP THE GLOBAL NAMESPACE BEFORE IMPORTS ---
// This ensures that when the real JS files are imported, their dependencies are already met.
beforeAll(() => {
    window.NoiseSurveyApp = window.NoiseSurveyApp || {};
    window.NoiseSurveyApp.renderers = mockRenderers;
});

// --- STEP 3: IMPORT THE REAL APPLICATION STACK ---
import '../noise_survey_analysis/static/js/store.js';
import '../noise_survey_analysis/static/js/actions.js';
import '../noise_survey_analysis/static/js/reducers.js';
import '../noise_survey_analysis/static/js/calcMetrics.js';
import '../noise_survey_analysis/static/js/comparison-metrics.js';
import '../noise_survey_analysis/static/js/init.js'; // Provides init.reInitializeStore
import '../noise_survey_analysis/static/js/renderers.js'; // Execute mocked factory, attach to app
import '../noise_survey_analysis/static/js/data-processors.js'; // Execute real factory, attach to app
import '../noise_survey_analysis/static/js/registry.js';
import '../noise_survey_analysis/static/js/thunks.js';
import '../noise_survey_analysis/static/js/event-handlers.js';
import '../noise_survey_analysis/static/js/app.js'; // Import app (defines side-effect handlers)


describe('App Orchestration Integration Tests', () => {

    let mockBokehModels;

    beforeEach(() => {
        vi.clearAllMocks();

        // Re-create the store for a clean state
        window.NoiseSurveyApp.init.reInitializeStore();

        // This is the minimal set of models needed for the app to initialize
        mockBokehModels = {
            charts: [{ name: 'figure_P1_timeseries', x_range: { start: 0, end: 100000 } }],
            visibilityCheckBoxes: [{ name: 'visibility_figure_P1_timeseries', active: [0] }],
            paramSelect: { value: 'LAeq' },
            audio_status_source: { patching: { connect: vi.fn() } },
            audio_control_source: { data: {} },
            // Add minimal raw data for the real data processors
            timeSeriesSources: {
                P1: { overview: { data: { Datetime: [0, 1000], LAeq: [50, 50] } } },
                P2: { overview: { data: { Datetime: [0, 1000], LAeq: [50, 50] } } },
            },
            preparedGlyphData: {
                P1: { overview: { prepared_params: { LZeq: {} } } },
                P2: { overview: { prepared_params: { LZeq: {} } } },
            },
        };

        window.NoiseSurveyApp.registry.models = mockBokehModels;

        // Spy on the registry's initialize function to control its output
        vi.spyOn(window.NoiseSurveyApp.registry, 'initialize').mockReturnValue({
            availablePositions: ['P1', 'P2'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 60000 },
            chartVisibility: { figure_P1_timeseries: true, figure_P1_spectrogram: true },
            controllers: { P1: {}, P2: {} },
        });

        // Initialize the app via init.initialize() which sets up subscriptions and triggers first render
        window.NoiseSurveyApp.init.initialize(mockBokehModels);
    });

    // --- Category 1: Heavy Update Scenarios ---
    describe('Category 1: Heavy Update Scenarios', () => {
        it('should trigger a heavy update when the viewport changes', () => {
            vi.useFakeTimers();
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;
            eventHandlers.handleRangeUpdate({ start: 100, end: 200 });
            // Debounced by 200ms
            vi.advanceTimersByTime(250);

            const { viewport } = store.getState().view;
            expect(viewport.min).toBe(100);
            expect(viewport.max).toBe(200);

            expect(renderers.renderPrimaryCharts).toHaveBeenCalled();
            vi.useRealTimers();
        });

        it('should trigger a heavy update when the active parameter changes', () => {
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;
            eventHandlers.handleParameterChange('LCeq');
            expect(store.getState().view.selectedParameter).toBe('LCeq');
            expect(renderers.renderPrimaryCharts).toHaveBeenCalled();
        });

        it('should trigger a heavy update when the view is toggled', () => {
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;
            eventHandlers.handleViewToggle(false);
            expect(store.getState().view.globalViewType).toBe('overview');
            expect(renderers.renderPrimaryCharts).toHaveBeenCalled();
        });

        it('should trigger a heavy update when a chart is hidden', () => {
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;
            const chartName = 'figure_P1_timeseries';
            eventHandlers.handleVisibilityChange({ active: [] }, chartName);
            expect(store.getState().view.chartVisibility[chartName]).toBe(false);
            expect(renderers.renderPrimaryCharts).toHaveBeenCalled();
        });
    });

    // --- Category 2: Light Update Scenarios ---
    describe('Category 2: Light Update Scenarios', () => {
        it('tap sets cursor and calls overlays without primary re-render', () => {
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;
            vi.clearAllMocks();

            // Initial render calls this, so we get a baseline.
            const beforePrimary = renderers.renderPrimaryCharts.mock.calls.length;
            const beforeOverlays = renderers.renderOverlays.mock.calls.length;

            eventHandlers.handleTap({ origin: { name: 'figure_P1_timeseries' }, x: 12345 });

            const tap = store.getState().interaction.tap;
            expect(tap.isActive).toBe(true);
            expect(tap.timestamp).toBe(12345);
            expect(renderers.renderOverlays.mock.calls.length).toBeGreaterThan(beforeOverlays);
            // The key assertion: a light update should NOT re-render the primary charts.
            expect(renderers.renderPrimaryCharts.mock.calls.length).toBe(beforePrimary);
        });

        it('hover activates overlays and frequency bar updates', () => {
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;
            vi.clearAllMocks();

            const beforeOverlays = renderers.renderOverlays.mock.calls.length;
            const beforeFreq = renderers.renderFrequencyBar.mock.calls.length;

            const cb_data = { geometry: { x: 5000, y: 1.0 } };
            eventHandlers.handleChartHover(cb_data, 'figure_P1_spectrogram');

            const hover = store.getState().interaction.hover;
            expect(hover.isActive).toBe(true);
            expect(hover.timestamp).toBe(5000);
            expect(renderers.renderOverlays.mock.calls.length).toBeGreaterThan(beforeOverlays);
            expect(renderers.renderFrequencyBar.mock.calls.length).toBeGreaterThan(beforeFreq);
            // A hover is a light update, so it should not trigger a primary chart re-render.
            expect(renderers.renderPrimaryCharts).not.toHaveBeenCalled();
        });

        it('arrow key navigation updates tap by step and calls overlays', () => {
            const { eventHandlers, store, actions, renderers } = window.NoiseSurveyApp;
            // Arrange: set a tap and an explicit small step size to avoid clamping
            eventHandlers.handleTap({ origin: { name: 'figure_P1_timeseries' }, x: 10000 });
            store.dispatch(actions.stepSizeCalculated(1000)); // 1s step

            const beforeOverlays = renderers.renderOverlays.mock.calls.length;

            // Act
            const e = { key: 'ArrowRight', target: { tagName: 'DIV' }, preventDefault: () => { } };
            eventHandlers.handleKeyPress(e);

            // Assert
            const afterTap = store.getState().interaction.tap;
            expect(afterTap.timestamp).toBe(11000);
            expect(renderers.renderOverlays.mock.calls.length).toBeGreaterThan(beforeOverlays);
        });
    });

    // --- Category 3: Feature-Specific End-to-End Flows ---
    describe('Category 3: Feature-Specific End-to-End Flows', () => {
        it('add and remove a marker triggers renderMarkers and updates state', () => {
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;

            // Part 1: Add marker via double click
            const beforeMarkers = renderers.renderMarkers.mock.calls.length;
            eventHandlers.handleDoubleClick({ origin: { name: 'figure_P1_timeseries' }, x: 50000 });
            expect(store.getState().markers.timestamps).toContain(50000);
            expect(renderers.renderMarkers.mock.calls.length).toBeGreaterThan(beforeMarkers);

            // Part 2: Remove marker via ctrl-tap near the marker
            const beforeMarkers2 = renderers.renderMarkers.mock.calls.length;
            eventHandlers.handleTap({ origin: { name: 'figure_P1_timeseries' }, x: 50100, modifiers: { ctrl: true } });
            expect(store.getState().markers.timestamps).toHaveLength(0);
            expect(renderers.renderMarkers.mock.calls.length).toBeGreaterThan(beforeMarkers2);
        });

        it('clearAllMarkers empties list and re-renders markers', () => {
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;
            // Add a couple markers first
            eventHandlers.handleDoubleClick({ origin: { name: 'figure_P1_timeseries' }, x: 10000 });
            eventHandlers.handleDoubleClick({ origin: { name: 'figure_P1_timeseries' }, x: 20000 });
            expect(store.getState().markers.timestamps.length).toBe(2);

            const beforeMarkers = renderers.renderMarkers.mock.calls.length;
            eventHandlers.clearAllMarkers();
            expect(store.getState().markers.timestamps).toHaveLength(0);
            expect(renderers.renderMarkers.mock.calls.length).toBeGreaterThan(beforeMarkers);
        });

        it('togglePlayPause sends play command and updates UI controls', () => {
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;

            // Set a tap context
            eventHandlers.handleTap({ origin: { name: 'figure_P1_timeseries' }, x: 42000 });
            vi.clearAllMocks();

            const beforeControls = renderers.renderControlWidgets.mock.calls.length;
            eventHandlers.togglePlayPause({ positionId: 'P1', isActive: true });

            expect(store.getState().audio.isPlaying).toBe(true);
            expect(mockBokehModels.audio_control_source.data.command[0]).toBe('play');
            expect(mockBokehModels.audio_control_source.data.position_id[0]).toBe('P1');
            expect(mockBokehModels.audio_control_source.data.value[0]).toBe(42000);
            expect(renderers.renderControlWidgets.mock.calls.length).toBeGreaterThan(beforeControls);
        });

        it('audio status update syncs tap line and triggers overlays', () => {
            const { eventHandlers, store, renderers } = window.NoiseSurveyApp;
            const models = window.NoiseSurveyApp.registry.models;
            models.audio_status_source = {
                data: {
                    is_playing: [true],
                    active_position_id: ['P1'],
                    playback_rate: [1.0],
                    volume_boost: [false],
                    current_time: [33000],
                }
            };

            const beforeOverlays = renderers.renderOverlays.mock.calls.length;
            eventHandlers.handleAudioStatusUpdate();
            const tap = store.getState().interaction.tap;
            expect(tap.isActive).toBe(true);
            expect(tap.timestamp).toBe(33000);
            expect(tap.position).toBe('P1');
            expect(renderers.renderOverlays.mock.calls.length).toBeGreaterThan(beforeOverlays);
        });

        it('key navigation during playback sends play command with new timestamp', () => {
            const { eventHandlers, store, actions } = window.NoiseSurveyApp;


            // Arrange:
            // 1. Set audio playing via a status update.
            store.dispatch(actions.audioStatusUpdate({
                is_playing: [true], active_position_id: ['P1'], playback_rate: [1.0], volume_boost: [false], current_time: [10000]
            }));
            // 2. The above dispatch sets tap time to 10000. Now set a specific step size.
            store.dispatch(actions.stepSizeCalculated(2000));

            const e = { key: 'ArrowRight', target: { tagName: 'DIV' }, preventDefault: () => { } };

            // Act: Simulate the key press. This will dispatch KEY_NAV.
            // The store's subscriber (onStateChange) will then call handleAudioSideEffects.
            eventHandlers.handleKeyPress(e);

            // Assert:
            // 1. The state has the new timestamp.
            const newTs = store.getState().interaction.tap.timestamp;
            expect(newTs).toBe(12000);

            // 2. The side effect sent the correct command with the new timestamp.
            expect(mockBokehModels.audio_control_source.data.command[0]).toBe('play');
            expect(mockBokehModels.audio_control_source.data.position_id[0]).toBe('P1');
            expect(mockBokehModels.audio_control_source.data.value[0]).toBe(12000);
        });

        it('tap on another position while playing switches playback to that position (TDD pending)', () => {
            const { eventHandlers, store, actions, renderers } = window.NoiseSurveyApp;
            const models = window.NoiseSurveyApp.registry.models;
            models.audio_control_source = models.audio_control_source || { data: {} };

            // Arrange: audio playing at P1 @ 10000 via backend status
            store.dispatch(actions.audioStatusUpdate({
                is_playing: [true], active_position_id: ['P1'], playback_rate: [1.0], volume_boost: [false], current_time: [10000]
            }));

            // Act: user taps P2 at 50000
            const beforeControls = renderers.renderControlWidgets.mock.calls.length;
            eventHandlers.handleTap({ origin: { name: 'figure_P2_timeseries' }, x: 50000 });

            // Assert desired behavior (currently unimplemented)
            expect(models.audio_control_source.data.command[0]).toBe('play');
            expect(models.audio_control_source.data.position_id[0]).toBe('P2');
            expect(models.audio_control_source.data.value[0]).toBe(50000);

            // State and UI reflect switch
            expect(store.getState().audio.activePositionId).toBe('P2');
            expect(renderers.renderControlWidgets.mock.calls.length).toBeGreaterThan(beforeControls);
        });
    });
});
