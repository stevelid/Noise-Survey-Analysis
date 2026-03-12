import { describe, it, expect, beforeEach } from 'vitest';

// Import module for side-effects
import '../noise_survey_analysis/static/js/features/view/viewResolution.js';
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

  function buildStreamedLogSource({
    start = 1000,
    n_times = 3,
    reported_n_times = n_times,
    n_freqs = 4,
    time_step = 100,
    chunk_time_length = n_times,
  } = {}) {
    const times_ms = Array.from({ length: n_times }, (_, t) => start + (t * time_step));
    const levels = Array.from({ length: n_freqs * chunk_time_length }, (_, idx) => idx + 1);
    const frequencies_hz = [100, 200, 300, 400].slice(0, n_freqs);
    const frequency_labels = frequencies_hz.map(hz => `${hz} Hz`);

    return {
      times_ms: [times_ms],
      levels_flat_transposed: [levels],
      frequency_labels: [frequency_labels],
      frequencies_hz: [frequencies_hz],
      n_times: [reported_n_times],
      n_freqs: [n_freqs],
      chunk_time_length: [chunk_time_length],
      time_step: [time_step],
      min_val: [0],
      max_val: [100],
      initial_glyph_data_x: [[times_ms[0]]],
      initial_glyph_data_y: [[-0.5]],
      initial_glyph_data_dw: [[chunk_time_length * time_step]],
      initial_glyph_data_dh: [[n_freqs]],
      initial_glyph_data_image: [levels],
    };
  }

  it('log happy path: uses chunked log data with freq slicing and sets y-range', () => {
    const position = 'P1';
    const viewState = {
      globalViewType: 'log',
      selectedParameter: 'LAeq',
      viewport: { min: 0, max: 3 }, // targetChunkStartTimeIdx = 0 for chunk_time_length=3
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
    expect(details.type).toBe('log');
    expect(details.reason).toBe(' (Log Data)');
  });

  it('zoomed out: falls back to overview with reason and initial glyph image', () => {
    const position = 'P1';
    const viewState = {
      globalViewType: 'log',
      availablePositions: [position],
      selectedParameter: 'LAeq',
      viewport: { min: 0, max: 6000 }, // pointsInView = 6000 > MAX_SPECTRAL_POINTS_TO_RENDER
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
    expect(details.reason).toBe(' - Overview - zoom in for Log');
    expect(details.type).toBe('overview');
    // Overview fallback extracts from backing levels_flat_transposed via getPreparedSpectrogramChunk
    // Image size is n_freqs * n_times (full overview), not n_freqs * chunk_time_length
    expect(rep.image[0].length).toBe(overview.n_freqs * overview.n_times);
  });

  it('no log data: falls back to overview', () => {
    const position = 'P1';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 0, max: 3 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 1, 3);
    const models = {
      preparedGlyphData: { [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } } },
      config: { spectrogram_freq_range_hz: [100, 400] },
    };
    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    expect(details.reason).toBe(' (Overview)');
    expect(details.type).toBe('overview');
    expect(viewState.displayDetails).toBeUndefined();
  });

  it('missing config: returns chunk image without y-range slicing', () => {
    const position = 'P1';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 0, max: 3 } };
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
  });

  it('out-of-range freqs: falls back to full chunk image', () => {
    const position = 'P1';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 0, max: 3 } };
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
  });

  it('streamed chunk-only payload reconstructs self-consistent chunk-local log data', () => {
    const position = 'P_streamed';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1000, max: 1200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    const streamedLogSource = buildStreamedLogSource();
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: streamedLogSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const active = dataState.activeSpectralData[position];

    expect(details.type).toBe('log');
    expect(active.n_times).toBe(active.times_ms.length);
    expect(active.levels_flat_transposed.length).toBe(active.n_freqs * active.n_times);
    expect(active.source_replacement.image[0].length).toBe(active.n_freqs * active.n_times);
  });

  it('streamed chunk-only payload must not leak mismatched full-buffer metadata into active state', () => {
    const position = 'P_streamed_mismatch';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1000, max: 1200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    const streamedLogSource = buildStreamedLogSource({ reported_n_times: 9, chunk_time_length: 3, n_times: 3 });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: streamedLogSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const active = dataState.activeSpectralData[position];

    // Chunk-only payloads normalize inconsistent server metadata down to the
    // actual chunk-local backing data that can be rendered safely.
    expect(active.n_times).toBe(3);
    expect(active.times_ms.length).toBe(3);
    // levels length should match n_freqs * chunk_time_length for chunk-only payloads
    expect(active.levels_flat_transposed.length).toBe(active.n_freqs * active.chunk_time_length);
  });

  it('streamed chunk-only payload outside viewport coverage falls back to overview', () => {
    const position = 'P_streamed_fallback';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 4000, max: 4200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    const streamedLogSource = buildStreamedLogSource();
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: streamedLogSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);

    expect(details.type).toBe('overview');
    // Overview fallback extracts from backing levels_flat_transposed via getPreparedSpectrogramChunk
    const rep = dataState.activeSpectralData[position].source_replacement;
    expect(rep).toBeTruthy();
    expect(rep.image[0].length).toBe(overview.n_freqs * overview.n_times);
  });

  // --- Reservoir payload tests ---

  function buildReservoirLogSource({
    start = 1000,
    n_times = 9,
    n_freqs = 4,
    time_step = 100,
    chunk_time_length = 3,
    parameter = 'LAeq',
    initial_dw = null,
    repeated_tail_count = 0,
  } = {}) {
    const times_ms = Array.from({ length: n_times }, (_, t) => start + (t * time_step));
    if (repeated_tail_count > 0 && repeated_tail_count < n_times) {
      const repeatValue = times_ms[n_times - repeated_tail_count - 1];
      for (let idx = n_times - repeated_tail_count; idx < n_times; idx += 1) {
        times_ms[idx] = repeatValue;
      }
    }
    const levels = new Float32Array(n_freqs * n_times);
    for (let f = 0; f < n_freqs; f++) {
      for (let t = 0; t < n_times; t++) {
        levels[f * n_times + t] = f * 10 + t;
      }
    }
    const frequencies_hz = [100, 200, 300, 400].slice(0, n_freqs);
    const frequency_labels = frequencies_hz.map(hz => `${hz} Hz`);
    const initImage = levels.slice(0, n_freqs * chunk_time_length);
    const initialDw = initial_dw ?? (chunk_time_length * time_step);

    return {
      times_ms: [times_ms],
      levels_flat_transposed: [levels],
      parameter: [parameter],
      frequency_labels: [frequency_labels],
      frequencies_hz: [frequencies_hz],
      n_times: [n_times],
      n_freqs: [n_freqs],
      chunk_time_length: [chunk_time_length],
      time_step: [time_step],
      min_val: [0],
      max_val: [100],
      initial_glyph_data_x: [[times_ms[0]]],
      initial_glyph_data_y: [[-0.5]],
      initial_glyph_data_dw: [[initialDw]],
      initial_glyph_data_dh: [[n_freqs]],
      initial_glyph_data_image: [initImage],
      is_reservoir_payload: [true],
    };
  }

  it('payload normalization handles typed arrays from reservoir', () => {
    const position = 'P_typed';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1000, max: 1200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    // Build reservoir with Float32Array levels and plain array times
    const reservoirSource = buildReservoirLogSource();
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const active = dataState.activeSpectralData[position];

    expect(details.type).toBe('log');
    // Float32Array levels should be preserved through normalization
    expect(active.levels_flat_transposed).toBeInstanceOf(Float32Array);
    expect(active.n_times).toBe(9); // Full reservoir, not just chunk_time_length
  });

  it('reservoir ingestion populates backing data correctly', () => {
    const position = 'P_reservoir';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1000, max: 1200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    const reservoirSource = buildReservoirLogSource({ n_times: 9, chunk_time_length: 3 });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const active = dataState.activeSpectralData[position];

    expect(details.type).toBe('log');
    expect(active._isReservoirPayload).toBe(true);
    expect(active.n_times).toBe(9);
    expect(active.chunk_time_length).toBe(3);
    expect(active.levels_flat_transposed.length).toBe(4 * 9); // n_freqs * reservoir_n_times
    expect(active.times_ms.length).toBe(9);
  });

  it('client-side extraction from reservoir returns fixed display shape', () => {
    const position = 'P_reservoir_display';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1000, max: 1200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    const reservoirSource = buildReservoirLogSource({ n_times: 9, chunk_time_length: 3, n_freqs: 4 });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const rep = dataState.activeSpectralData[position].source_replacement;

    // Display image must be exactly chunk_time_length * n_freqs (fixed display size)
    expect(rep.image[0].length).toBe(4 * 3); // n_freqs * chunk_time_length
  });

  it('panning inside reservoir does not change backing data', () => {
    const position = 'P_pan_inside';
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    const reservoirSource = buildReservoirLogSource({ start: 1000, n_times: 9, chunk_time_length: 3, time_step: 100 });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    // First render at viewport 1000-1200
    const dataState1 = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const viewState1 = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1000, max: 1200 } };
    dataProcessors.updateActiveSpectralData(position, viewState1, dataState1, models);

    // Pan to viewport 1300-1500 (still inside reservoir which covers 1000-1800)
    const dataState2 = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const viewState2 = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1300, max: 1500 } };
    dataProcessors.updateActiveSpectralData(position, viewState2, dataState2, models);

    // Both should produce log data from the same reservoir
    expect(dataState1.activeSpectralData[position]._isReservoirPayload).toBe(true);
    expect(dataState2.activeSpectralData[position]._isReservoirPayload).toBe(true);
    // Both should have the same backing reservoir data
    expect(dataState1.activeSpectralData[position].n_times).toBe(9);
    expect(dataState2.activeSpectralData[position].n_times).toBe(9);
    // Display images should be fixed chunk size
    expect(dataState1.activeSpectralData[position].source_replacement.image[0].length).toBe(4 * 3);
    expect(dataState2.activeSpectralData[position].source_replacement.image[0].length).toBe(4 * 3);
  });

  it('uses full reservoir bounds instead of initial display chunk for readiness', () => {
    const position = 'P_reservoir_bounds';
    const overview = buildSpectralPrepared(60, 4, 100, 9);
    const reservoirSource = buildReservoirLogSource({
      start: 1000,
      n_times: 45,
      chunk_time_length: 9,
      n_freqs: 4,
      time_step: 100,
      // Initial glyph only describes the fixed display chunk, not the full reservoir.
      initial_dw: 900,
    });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 3600 },
    };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const viewState = {
      globalViewType: 'log',
      selectedParameter: 'LAeq',
      // Inside the full reservoir (1000-5400 ms) but outside the initial 900 ms chunk.
      viewport: { min: 2800, max: 3600 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);

    expect(details.type).toBe('log');
    expect(details.statusCode).toBe('log_displayed');
    expect(dataState.activeSpectralData[position].dataViewType).toBe('log');
    expect(dataState.activeSpectralData[position].source_replacement.image[0].length).toBe(4 * 9);
  });

  it('allows log display near the far edge when viewport still fits inside the reservoir', () => {
    const position = 'P_reservoir_far_edge';
    const overview = buildSpectralPrepared(60, 4, 100, 9);
    const reservoirSource = buildReservoirLogSource({
      start: 1000,
      n_times: 45,
      chunk_time_length: 9,
      n_freqs: 4,
      time_step: 100,
      initial_dw: 900,
    });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 3600 },
    };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const viewState = {
      globalViewType: 'log',
      selectedParameter: 'LAeq',
      // Near the far edge, but still within the full reservoir.
      viewport: { min: 4600, max: 5400 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);

    expect(details.type).toBe('log');
    expect(details.statusCode).toBe('log_displayed');
    expect(dataState.activeSpectralData[position].dataViewType).toBe('log');
  });

  it('preserves fixed chunk width when a reservoir tail is padded', () => {
    const position = 'P_reservoir_padded_tail';
    const overview = buildSpectralPrepared(60, 4, 100, 9);
    const reservoirSource = buildReservoirLogSource({
      start: 1000,
      n_times: 9,
      chunk_time_length: 9,
      n_freqs: 4,
      time_step: 100,
      repeated_tail_count: 2,
      initial_dw: 900,
    });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 3600 },
    };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const viewState = {
      globalViewType: 'log',
      selectedParameter: 'LAeq',
      viewport: { min: 1100, max: 1500 },
    };

    dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const replacement = dataState.activeSpectralData[position].source_replacement;

    expect(replacement.x[0]).toBe(1000);
    expect(replacement.dw[0]).toBe(900);
    expect(replacement.times_ms[0]).toBe(1000);
    expect(replacement.times_ms[replacement.times_ms.length - 1]).toBe(1800);
  });

  it('reservoir outside viewport coverage falls back to overview', () => {
    const position = 'P_reservoir_fallback';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 5000, max: 5200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    // Reservoir covers 1000-1800, viewport is 5000-5200 — no coverage
    const reservoirSource = buildReservoirLogSource({ start: 1000, n_times: 9, chunk_time_length: 3, time_step: 100 });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);

    expect(details.type).toBe('overview');
    // Overview fallback extracts from backing levels_flat_transposed
    const rep = dataState.activeSpectralData[position].source_replacement;
    expect(rep).toBeTruthy();
    expect(rep.image[0].length).toBe(overview.n_freqs * overview.n_times);
  });

  it('partial reservoir overlap falls back instead of stretching stale log data', () => {
    const position = 'P_reservoir_partial_overlap';
    const overview = buildSpectralPrepared(60, 4, 100, 9);
    const reservoirSource = buildReservoirLogSource({
      start: 1000,
      n_times: 45,
      chunk_time_length: 9,
      n_freqs: 4,
      time_step: 100,
      initial_dw: 900,
    });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 3600 },
    };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const viewState = {
      globalViewType: 'log',
      selectedParameter: 'LAeq',
      // Partial overlap with the full reservoir should conservatively fall back.
      viewport: { min: 5000, max: 5800 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);

    expect(details.type).toBe('overview');
    expect(details.statusCode).toBe('loading_log');
    expect(dataState.activeSpectralData[position].dataViewType).toBe('overview');
  });

  it('streamed parameter mismatch falls back with parameter_sync status', () => {
    const position = 'P_parameter_mismatch';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1000, max: 1200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    const reservoirSource = buildReservoirLogSource({ parameter: 'LZeq' });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);

    expect(details.type).toBe('overview');
    expect(details.statusCode).toBe('parameter_sync');
    expect(details.parameterMismatch).toBe(true);
  });

  it('fixed-size image painting with reservoir does not cause size mismatch', () => {
    const position = 'P_no_mismatch';
    const n_freqs = 4;
    const chunk_time_length = 3;
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1000, max: 1200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, n_freqs, 100, chunk_time_length);
    const reservoirSource = buildReservoirLogSource({ n_times: 12, chunk_time_length, n_freqs });
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const rep = dataState.activeSpectralData[position].source_replacement;

    // The painted image must always be exactly chunk_time_length * n_freqs
    // regardless of how wide the reservoir is
    expect(rep.image[0].length).toBe(n_freqs * chunk_time_length);
    // Ensure no undefined or NaN values in the image
    const imageArr = Array.from(rep.image[0]);
    expect(imageArr.every(v => Number.isFinite(v))).toBe(true);
  });

  it('payload normalization handles Float64Array times from reservoir', () => {
    const position = 'P_f64';
    const viewState = { globalViewType: 'log', selectedParameter: 'LAeq', viewport: { min: 1000, max: 1200 } };
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const overview = buildSpectralPrepared(6, 4, 100, 3);
    // Use Float64Array for times (simulating what Bokeh sends for NumPy float64 arrays)
    const reservoirSource = buildReservoirLogSource();
    const typedTimes = new Float64Array(reservoirSource.times_ms[0]);
    reservoirSource.times_ms = [typedTimes];
    const models = {
      preparedGlyphData: {
        [position]: { overview: { prepared_params: { LAeq: overview } }, log: { prepared_params: { LAeq: null } } },
      },
      spectrogramSources: {
        [position]: { log: { data: reservoirSource } },
      },
      positionHasLogData: { [position]: true },
      config: { spectrogram_freq_range_hz: [100, 400], log_view_max_viewport_seconds: 300 },
    };

    const details = dataProcessors.updateActiveSpectralData(position, viewState, dataState, models);
    const active = dataState.activeSpectralData[position];

    expect(details.type).toBe('log');
    // Float64Array times are correctly unwrapped from the payload normalization layer.
    // Note: active.times_ms may be a plain array because createOffsetArray always returns Array,
    // but the underlying unwrapping must correctly handle typed arrays without errors.
    expect(active.n_times).toBe(9);
    expect(active.times_ms.length).toBe(9);
    // Verify the values are correct (same as original typed array)
    expect(active.times_ms[0]).toBe(typedTimes[0]);
    expect(active.times_ms[8]).toBe(typedTimes[8]);
  });
});
