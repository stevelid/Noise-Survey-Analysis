import { describe, it, expect, vi, beforeEach } from 'vitest';

// Ensure correct load order: state core modules followed by init
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/init.js';

// We'll stub dependencies that app.js orchestrates
let defaultDisplayDetails;

beforeEach(() => {
  vi.restoreAllMocks();
  // Fresh spies before every test
  defaultDisplayDetails = { P1: { line: { reason: ' (Overview)' }, spec: { reason: ' (Overview)' } } };

  window.NoiseSurveyApp.renderers = {
    renderPrimaryCharts: vi.fn(),
    renderFrequencyBar: vi.fn(),
    renderOverlays: vi.fn(),
    renderControlWidgets: vi.fn(),
    renderMarkers: vi.fn(),
    renderRegions: vi.fn(),
    renderActiveTool: vi.fn(),
  };
  window.NoiseSurveyApp.data_processors = {
    updateActiveData: vi.fn().mockReturnValue(defaultDisplayDetails),
    calculateStepSize: vi.fn().mockReturnValue(120000),
    updateActiveFreqBarData: vi.fn(),
  };

  // Minimal registry stub to satisfy initialize call and side-effect wiring
  window.NoiseSurveyApp.registry = {
    initialize: vi.fn().mockImplementation(() => ({
      availablePositions: ['P1'],
      selectedParameter: 'LAeq',
      viewport: { min: 0, max: 1000 },
      chartVisibility: { figure_P1_timeseries: true, figure_P1_spectrogram: true },
      hoverEnabled: true,
    })),
    models: {
      audio_status_source: { patching: { connect: vi.fn() } },
      audio_control_source: { data: {} },
    },
    controllers: {
      positions: {},
      chartsByName: new Map(),
    },
  };

  // Event handlers used by app.js during initialization
  window.NoiseSurveyApp.eventHandlers = {
    handleAudioStatusUpdate: vi.fn(),
    handleKeyPress: vi.fn(),
  };
});

// Import app.js last so it picks up our stubs (no side-effects until init() is called)
import '../noise_survey_analysis/static/js/app.js';

describe('NoiseSurveyApp.app orchestrator', () => {
  it('initialize() should wire listeners, dispatch init, and orchestrate a full update cycle', () => {
    // The public API exposes an `init` object with an `initialize(models)` method
    expect(typeof window.NoiseSurveyApp.init).toBe('object');
    expect(typeof window.NoiseSurveyApp.init.initialize).toBe('function');

    // Act: initialize the app with minimal models
    const ok = window.NoiseSurveyApp.init.initialize({});

    // Assert initialize returned true and registry was used
    expect(ok).toBe(true);
    expect(window.NoiseSurveyApp.registry.initialize).toHaveBeenCalled();

    // on initial load, step size should be calculated and always-run renderers should be invoked
    expect(window.NoiseSurveyApp.data_processors.calculateStepSize).toHaveBeenCalled();
    const primaryDetailsArgs = window.NoiseSurveyApp.renderers.renderPrimaryCharts.mock.calls
      .map(call => call[2])
      .filter(details => details != null);
    expect(primaryDetailsArgs.at(-1)).toBe(defaultDisplayDetails);

    const controlDetailsArgs = window.NoiseSurveyApp.renderers.renderControlWidgets.mock.calls
      .map(call => call[1])
      .filter(details => details != null);
    expect(controlDetailsArgs.at(-1)).toBe(defaultDisplayDetails);

    // Basic sanity: registry initializer was used and keyboard step updated
    expect(window.NoiseSurveyApp.registry.initialize).toHaveBeenCalled();

    // Verify keyboard step size was updated via action dispatch
    const stepAfter = window.NoiseSurveyApp.store.getState().interaction.keyboard.stepSizeMs;
    expect(stepAfter).toBe(120000);
  });

  it('subsequent state updates should orchestrate updates on viewport change', () => {
    // Initialize first
    window.NoiseSurveyApp.init.initialize({});

    // Reset call counts to focus on the new change cycle
    vi.clearAllMocks();

    // Dispatch a viewport change
    window.NoiseSurveyApp.data_processors.updateActiveData.mockReturnValueOnce({
      P1: {
        line: { type: 'log', reason: ' (Log Data)' },
        spec: { type: 'log', reason: ' (Log Data)' },
      },
    });

    window.NoiseSurveyApp.store.dispatch(
      window.NoiseSurveyApp.actions.viewportChange(0, 2000)
    );

    // State reflects the dispatched viewport change
    const vp = window.NoiseSurveyApp.store.getState().view.viewport;
    expect(vp.min).toBe(0);
    expect(vp.max).toBe(2000);

    const details = window.NoiseSurveyApp.store.getState().view.displayDetails;
    expect(details.P1.line).toEqual({ type: 'log', reason: ' (Log Data)' });
    expect(details.P1.spec).toEqual({ type: 'log', reason: ' (Log Data)' });
  });
});
