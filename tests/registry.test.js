import { describe, it, expect, beforeEach, vi } from 'vitest';

// Ensure global app object exists
window.NoiseSurveyApp = window.NoiseSurveyApp || {};

// Import registry to attach app.registry
import '../noise_survey_analysis/static/js/registry.js';

describe('NoiseSurveyApp.registry.initialize', () => {
  beforeEach(() => {
    vi.restoreAllMocks();

    // Stub Bokeh document API used by registry
    window.Bokeh = {
      documents: [
        {
          get_model_by_name: vi.fn((name) => {
            if (name === 'audio_control_source') return { data: { control: true } };
            if (name === 'audio_status_source') return { data: { status: true } };
            return null;
          }),
        },
      ],
    };

    // Stub PositionController so registry can populate controllers
    window.NoiseSurveyApp.classes = {
      PositionController: vi.fn().mockImplementation((posId, models) => {
        // Create charts for this position from provided models
        const charts = models.charts
          .filter((c) => c.name.includes(`figure_${posId}_`))
          .map((c) => ({ name: c.name }));
        return {
          id: posId,
          charts,
        };
      }),
    };
  });

  it('should initialize models, controllers, and return correct initial state payload', () => {
    const bokehModels = {
      charts: [
        { name: 'figure_P1_timeseries', x_range: { start: 0, end: 100 } },
        { name: 'figure_P1_spectrogram', x_range: { start: 0, end: 100 }, y_range: { start: 0, end: 10 } },
      ],
      chartsSources: [],
      labels: [],
      hoverLines: [],
      hoverDivs: [{ name: 'P1_spectrogram_hover_div' }],
      visibilityCheckBoxes: [
        { name: 'visibility_figure_P1_timeseries', active: [0] },
        { name: 'visibility_figure_P1_spectrogram', active: [] },
      ],
      paramSelect: { value: 'LZeq' },
      audio_controls: {
        P1: {
          play_toggle: {},
          playback_rate_button: {},
          volume_boost_button: {},
        },
      },
    };

    const payload = window.NoiseSurveyApp.registry.initialize(bokehModels);

    // Payload expectations
    expect(payload.availablePositions).toEqual(['P1']);
    expect(payload.selectedParameter).toBe('LZeq');
    expect(payload.viewport).toEqual({ min: 0, max: 100 });
    expect(payload.chartVisibility).toEqual({
      figure_P1_timeseries: true,
      figure_P1_spectrogram: false,
    });

    // Models should include audio sources resolved via Bokeh doc
    const models = window.NoiseSurveyApp.registry.models;
    expect(models.audio_control_source?.data?.control).toBe(true);
    expect(models.audio_status_source?.data?.status).toBe(true);

    // Controllers should be populated with mapped charts
    const controllers = window.NoiseSurveyApp.registry.controllers;
    expect(controllers.positions.P1).toBeTruthy();
    expect(controllers.chartsByName.get('figure_P1_timeseries')).toBeTruthy();
    expect(controllers.chartsByName.get('figure_P1_spectrogram')).toBeTruthy();
  });
});
