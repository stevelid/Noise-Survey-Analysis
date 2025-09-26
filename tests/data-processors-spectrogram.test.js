import { describe, it, expect, beforeEach } from 'vitest';

// Import module for side-effects
import '../noise_survey_analysis/static/js/data-processors.js';

describe('NoiseSurveyApp.data_processors.updateActiveSpectralData (spectrogram paths)', () => {
  let dataProcessors;

  beforeEach(() => {
    dataProcessors = window.NoiseSurveyApp.data_processors;
  });

  function buildSpectralPrepared(n_times = 6, n_freqs = 4, time_step = 1, chunk_time_length = 3) {
    const times_ms = Array.from({ length: n_times }, (_, t) => t * time_step);
    const levels = new Float32Array(n_freqs * n_times);
    for (let f = 0; f < n_freqs; f++) {
      for (let t = 0; t < n_times; t++) {
        levels[f * n_times + t] = f * 10 + t; // simple pattern f*10 + t
      }
    }
    const initImage = new Float32Array(n_freqs * chunk_time_length); // placeholder
    const frequencies_hz = [100, 200, 300, 400].slice(0, n_freqs);
    const frequency_labels = frequencies_hz.map(hz => `${hz} Hz`);

    return {
      times_ms,
      time_step,
      n_times,
      n_freqs,
      chunk_time_length,
      levels_flat_transposed: levels,
      initial_glyph_data: { image: [initImage], x: [0], dw: [chunk_time_length * time_step], y: 0, dh: n_freqs },
      frequencies_hz,
      frequency_labels,
      min_val: 0,
    };
  }

  it('log happy path: uses chunked log data with freq slicing and sets y-range', () => {
    const position = 'P1';
    const viewState = {
      globalViewType: 'log',
      selectedParameter: 'LAeq',
      viewport: { min: 0, max: 3 }, // targetChunkStartTimeIdx = 0 for chunk_time_length=3
      displayDetails: {},
    };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const log = buildSpectralPrepared(6, 4, 1, 3);
    const overview = buildSpectralPrepared(6, 4, 1, 3);
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: log } } },
      },
      config: { spectrogram_freq_range_hz: [200, 300] },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);

    const rep = dataState.activeSpectralData[position].source_replacement;
    expect(rep).toBeTruthy();
    expect(rep.y_range_start).toBe(0.5); // start index (1) - 0.5
    expect(rep.y_range_end).toBe(2.5); // (end index 2) + 0.5
    // Verify visible labels and indices
    expect(rep.visible_frequency_labels).toEqual(['200 Hz', '300 Hz']);
    expect(rep.visible_freq_indices).toEqual([1, 2]);
    // Verify that copied canvas buffer retains visible rows and is correct size
    expect(rep.image[0].length).toBe(log.n_freqs * log.chunk_time_length);
    expect(details?.type).toBe('log');
    expect(details?.reason).toBe(' (Log Data)');
    expect(viewState.displayDetails).toEqual({});
  });

  it('zoomed out: falls back to overview with reason and initial glyph image', () => {
    const position = 'P1';
    const viewState = {
      globalViewType: 'log',
      selectedParameter: 'LAeq',
      viewport: { min: 0, max: 6000 }, // pointsInView = 6000 > MAX_SPECTRAL_POINTS_TO_RENDER
      displayDetails: {},
    };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const log = buildSpectralPrepared(6, 4, 1, 3);
    const overview = buildSpectralPrepared(6, 4, 1, 3);
    // Make initial glyph image distinguishable
    overview.initial_glyph_data.image[0].fill(42);
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: log } } },
      },
      config: { spectrogram_freq_range_hz: [100, 400] },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const rep = dataState.activeSpectralData[position].source_replacement;
    expect(details?.type).toBe('overview');
    expect(details?.reason).toBe(' - Zoom in for Log Data');
    // Should use overview image buffer size
    expect(rep.image[0]).toEqual(overview.initial_glyph_data.image[0]);
    expect(viewState.displayDetails).toEqual({});
  });

  it('no log data: falls back to overview with specific reason', () => {
    const position = 'P1';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 0, max: 3 }, displayDetails: {} };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 1, 3);
    const models = {
      preparedGlyphData: { [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } } },
      config: { spectrogram_freq_range_hz: [100, 400] },
    };
    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    expect(details?.type).toBe('overview');
    expect(details?.reason).toBe(' (No Log Data Available)');
    expect(viewState.displayDetails).toEqual({});
  });

  it('missing config: returns chunk image without y-range slicing', () => {
    const position = 'P1';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 0, max: 3 }, displayDetails: {} };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const log = buildSpectralPrepared(6, 4, 1, 3);
    const models = {
      preparedGlyphData: { [position]: { overview: { prepared_params: { LAeq: log } }, log: { prepared_params: { LAeq: log } } } },
      // No config provided
    };
    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const rep = dataState.activeSpectralData[position].source_replacement;
    // Should have a chunk-sized image with no y_range metadata
    expect(rep.image[0].length).toBe(log.n_freqs * log.chunk_time_length);
    expect(rep.y_range_start).toBeUndefined();
    expect(rep.y_range_end).toBeUndefined();
    expect(details?.type).toBe('log');
    expect(details?.reason).toBe(' (Log Data)');
    expect(viewState.displayDetails).toEqual({});
  });

  it('out-of-range freqs: falls back to full chunk image', () => {
    const position = 'P1';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 0, max: 3 }, displayDetails: {} };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const log = buildSpectralPrepared(6, 4, 1, 3);
    const models = {
      preparedGlyphData: { [position]: { overview: { prepared_params: { LAeq: log } }, log: { prepared_params: { LAeq: log } } } },
      config: { spectrogram_freq_range_hz: [5000, 8000] },
    };
    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const rep = dataState.activeSpectralData[position].source_replacement;
    // Should be the full chunk (fallback path)
    expect(rep.image[0].length).toBe(log.n_freqs * log.chunk_time_length);
    expect(rep.y_range_start).toBeUndefined();
    expect(rep.y_range_end).toBeUndefined();
    expect(details?.type).toBe('log');
    expect(details?.reason).toBe(' (Log Data)');
    expect(viewState.displayDetails).toEqual({});
  });
});
