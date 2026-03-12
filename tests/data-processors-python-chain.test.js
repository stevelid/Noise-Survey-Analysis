import { beforeAll, describe, expect, it } from 'vitest';
import { execFileSync } from 'node:child_process';
import path from 'node:path';

import '../noise_survey_analysis/static/js/features/view/viewResolution.js';
import '../noise_survey_analysis/static/js/data-processors.js';

describe('Python -> JS spectrogram streaming contract', () => {
  let fixture;
  let dataProcessors;

  beforeAll(() => {
    const scriptPath = path.resolve(process.cwd(), 'tests/helpers/generate_spectrogram_chain_fixture.py');
    const stdout = execFileSync('python', [scriptPath], {
      cwd: process.cwd(),
      encoding: 'utf8',
      maxBuffer: 8 * 1024 * 1024,
    });

    fixture = JSON.parse(stdout);
    dataProcessors = window.NoiseSurveyApp.data_processors;
  });

  function clone(value) {
    if (typeof globalThis.structuredClone === 'function') {
      return globalThis.structuredClone(value);
    }
    return JSON.parse(JSON.stringify(value));
  }

  function buildOverviewPrepared() {
    const n_times = 12;
    const n_freqs = 2;
    const time_step = 60_000;
    const start = 1_704_067_200_000;
    const times_ms = Array.from({ length: n_times }, (_, idx) => start + (idx * time_step));
    const levels = new Float32Array(n_freqs * n_times);

    for (let freqIdx = 0; freqIdx < n_freqs; freqIdx += 1) {
      for (let timeIdx = 0; timeIdx < n_times; timeIdx += 1) {
        levels[(freqIdx * n_times) + timeIdx] = 55 + freqIdx + timeIdx;
      }
    }

    return {
      frequency_labels: ['100 Hz', '200 Hz'],
      frequencies_hz: [100, 200],
      n_times,
      n_times_real: n_times,
      n_freqs,
      chunk_time_length: n_times,
      time_step,
      times_ms,
      levels_flat_transposed: levels,
      min_val: 40,
      max_val: 90,
      min_time: times_ms[0],
      max_time: times_ms[n_times - 1],
      initial_glyph_data: {
        x: [times_ms[0]],
        y: [-0.5],
        dw: [n_times * time_step],
        dh: [n_freqs],
        image: [levels],
      },
    };
  }

  function buildModels(payload = fixture.logPayload) {
    return {
      preparedGlyphData: {
        [fixture.position]: {
          overview: { prepared_params: { [fixture.parameter]: buildOverviewPrepared() } },
          log: { prepared_params: { [fixture.parameter]: null } },
        },
      },
      spectrogramSources: {
        [fixture.position]: { log: { data: clone(payload) } },
      },
      positionHasLogData: { [fixture.position]: true },
      config: clone(fixture.config),
    };
  }

  function runViewportCase(caseSpec) {
    const dataState = { activeSpectralData: {}, _spectrogramCanvasBuffers: {} };
    const viewState = {
      globalViewType: 'log',
      availablePositions: [fixture.position],
      selectedParameter: fixture.parameter,
      viewport: { min: caseSpec.min, max: caseSpec.max },
    };
    const details = dataProcessors.updateActiveSpectralData(
      fixture.position,
      viewState,
      dataState,
      buildModels(),
    );

    return {
      details,
      active: dataState.activeSpectralData[fixture.position],
    };
  }

  it('python fixture exposes a full reservoir wider than the initial display chunk', () => {
    const payload = fixture.logPayload;
    const reservoirStart = payload.times_ms[0][0];
    const reservoirEnd = payload.times_ms[0][payload.times_ms[0].length - 1];
    const initialChunkStart = payload.initial_glyph_data_x[0][0];
    const initialChunkWidth = payload.initial_glyph_data_dw[0][0];

    expect(payload.is_reservoir_payload[0]).toBe(true);
    expect(fixture.reservoirBounds).toEqual([reservoirStart, reservoirEnd]);
    expect((reservoirEnd - reservoirStart)).toBeGreaterThan(initialChunkWidth);
    expect(initialChunkStart).toBe(reservoirStart);
  });

  it('displays log spectrogram beyond the initial chunk when viewport is still inside the reservoir', () => {
    const { details, active } = runViewportCase(fixture.cases.inside_reservoir_beyond_initial_chunk);

    expect(details.type).toBe('log');
    expect(details.statusCode).toBe('log_displayed');
    expect(active.dataViewType).toBe('log');
    expect(active.displayDetails.statusCode).toBe('log_displayed');
  });

  it('displays log spectrogram near the far edge when viewport still fits inside the reservoir', () => {
    const { details, active } = runViewportCase(fixture.cases.near_far_edge_inside_reservoir);

    expect(details.type).toBe('log');
    expect(details.statusCode).toBe('log_displayed');
    expect(active.dataViewType).toBe('log');
  });

  it('falls back to overview when viewport only partially overlaps the reservoir on the right', () => {
    const { details, active } = runViewportCase(fixture.cases.partial_overlap_right);

    expect(details.type).toBe('overview');
    expect(details.statusCode).toBe('loading_log');
    expect(active.dataViewType).toBe('overview');
  });

  it('falls back to overview when viewport only partially overlaps the reservoir on the left', () => {
    const { details, active } = runViewportCase(fixture.cases.partial_overlap_left);

    expect(details.type).toBe('overview');
    expect(details.statusCode).toBe('loading_log');
    expect(active.dataViewType).toBe('overview');
  });

  it('falls back to overview with zoom_required when viewport exceeds the spectrogram threshold', () => {
    const { details, active } = runViewportCase(fixture.cases.oversized_viewport);

    expect(details.type).toBe('overview');
    expect(details.statusCode).toBe('zoom_required');
    expect(details.requiresZoom).toBe(true);
    expect(active.dataViewType).toBe('overview');
  });
});
