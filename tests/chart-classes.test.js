import { describe, it, expect, beforeEach, vi } from 'vitest';

// Load the module under test
import '../noise_survey_analysis/static/js/chart-classes.js';

describe('NoiseSurveyApp.classes', () => {
  let classes;

  beforeEach(() => {
    vi.restoreAllMocks();
    classes = window.NoiseSurveyApp.classes;

    // Minimal Bokeh-like chart and glyph models
    global.Bokeh = {
      documents: [
        {
          add_model: (m) => m,
          create_model: (type, props) => ({ type, ...props }),
        },
      ],
    };
  });

  it('TimeSeriesChart.update should set source data and title with reason', () => {
    const chartModel = { name: 'figure_P1_timeseries', title: { text: '' }, x_range: { start: 0, end: 100 }, y_range: { start: 0, end: 1 } };
    const sourceModel = { data: {}, change: { emit: vi.fn() } };
    const labelModel = {}; const hoverLineModel = {};

    const ts = new classes.TimeSeriesChart(chartModel, sourceModel, labelModel, hoverLineModel, 'P1');
    vi.spyOn(ts, 'render');

    const activeLineData = { Datetime: [0, 1000], LAeq: [50, 60] };
    ts.update(activeLineData, { reason: ' (Overview)' });

    expect(ts.activeData).toBe(activeLineData);
    expect(ts.source.data).toBe(activeLineData);
    expect(chartModel.title.text).toContain('P1 - Time History (Overview)');
    expect(ts.render).toHaveBeenCalled();
  });

  it('TimeSeriesChart.getLabelText should format values at index', () => {
    // Mock util used by getLabelText
    window.NoiseSurveyApp.utils = {
      findAssociatedDateIndex: vi.fn().mockReturnValue(1),
    };

    const ts = new classes.TimeSeriesChart(
      { name: 'figure_P1_timeseries', title: { text: '' }, x_range: { start: 0, end: 100 }, y_range: { start: 0, end: 1 } },
      { data: {}, change: { emit: vi.fn() } },
      {},
      {},
      'P1'
    );

    ts.activeData = { Datetime: [0, 1], LAeq: [50.234, 60.345], LCeq: [70, 80] };
    const text = ts.getLabelText(1);
    expect(text).toContain('LAeq: 60.3 dB');
    expect(text).toContain('LCeq: 80.0 dB');
  });

  it('SpectrogramChart.update should replace image data and set y-range for slicing', () => {
    const imageDataArray = new Float32Array(4);
    const imageRenderer = {
      glyph: { type: 'Image', x: 0, y: 0, dw: 0, dh: 0 },
      data_source: { data: { image: [imageDataArray] }, change: { emit: vi.fn() } },
    };

    const chartModel = {
      name: 'figure_P1_spectrogram',
      title: { text: '' },
      renderers: [imageRenderer],
      yaxis: { ticker: {}, major_label_overrides: {} },
      y_range: { start: 0, end: 3 },
    };

    const spec = new classes.SpectrogramChart(chartModel, {}, {}, { text: '' }, 'P1');
    vi.spyOn(spec, 'render');

    const replacement = {
      image: [new Float32Array([1, 2, 3, 4])],
      x: [10],
      dw: [20],
      y: [0],
      dh: [3],
      y_range_start: 1.5,
      y_range_end: 2.5,
      visible_freq_indices: [2],
      visible_frequency_labels: ['3000 Hz'],
    };

    const activeSpectralData = { source_replacement: replacement };
    spec.update(activeSpectralData, { reason: ' (Log Data)' }, 'LAeq');

    expect(chartModel.title.text).toContain('P1 - LAeq Spectrogram (Log Data)');
    expect(spec.source.data.image[0]).toEqual(replacement.image[0]);
    expect(spec.imageRenderer.glyph.x).toBe(10);
    expect(spec.imageRenderer.glyph.dw).toBe(20);
    expect(chartModel.y_range.start).toBe(1.5);
    expect(chartModel.y_range.end).toBe(2.5);
    expect(spec.render).toHaveBeenCalled();
  });

  it('Chart.syncMarkers should add, remove, and hide markers correctly', () => {
    // Base Chart with stubs
    const chartModel = { name: 'figure_P1_timeseries', add_layout: vi.fn(), remove_layout: vi.fn(), x_range: { start: 0, end: 100 }, y_range: { start: 0, end: 1 } };
    const sourceModel = { change: { emit: vi.fn() } };
    const chart = new classes.Chart(chartModel, sourceModel, {}, {}, 'P1');

    // Add markers 100, 200
    chart.syncMarkers([100, 200], true);
    expect(chart.markerModels).toHaveLength(2);
    expect(chartModel.add_layout).toHaveBeenCalledTimes(2);
    expect(sourceModel.change.emit).toHaveBeenCalled();

    // Replace one and add one (remove 100, add 300)
    chart.syncMarkers([200, 300], true);
    expect(chart.markerModels.map(m => m.location).sort()).toEqual([200, 300]);
    expect(chartModel.remove_layout).toHaveBeenCalledTimes(1);

    // Hide markers when disabled
    chart.syncMarkers([200, 300], false);
    expect(chart.markerModels.every(m => m.visible === false)).toBe(true);
  });

  it('Chart label and hover line methods should set visibility and positions', () => {
    const labelModel = { visible: false, x: 0, y: 0, text_align: 'left', text: '' };
    const hoverLineModel = { visible: false, location: null };
    const chartModel = { name: 'figure_P1_timeseries', x_range: { start: 0, end: 100 }, y_range: { start: 0, end: 50 } };
    const chart = new classes.Chart(chartModel, { change: { emit: vi.fn() } }, labelModel, hoverLineModel, 'P1');

    // Render label on the right side of middle
    chart.renderLabel(90, 'Text');
    expect(labelModel.visible).toBe(true);
    expect(labelModel.text_align).toBe('right');
    expect(labelModel.text).toBe('Text');
    chart.hideLabel();
    expect(labelModel.visible).toBe(false);

    // Hover line
    chart.renderHoverLine(42);
    expect(hoverLineModel.visible).toBe(true);
    expect(hoverLineModel.location).toBe(42);
    chart.hideHoverLine();
    expect(hoverLineModel.visible).toBe(false);
  });

  it('SpectrogramChart.renderHoverDetails should render when relevant and fallback otherwise', () => {
    const imageRenderer = { glyph: { type: 'Image' }, data_source: { data: { image: [new Float32Array(4)] }, change: { emit: vi.fn() } } };
    const chartModel = { name: 'figure_P1_spectrogram', renderers: [imageRenderer], title: { text: '' }, yaxis: { ticker: {}, major_label_overrides: {} } };
    const hoverDiv = { text: '' };
    const spec = new classes.SpectrogramChart(chartModel, {}, {}, hoverDiv, 'P1');

    // Not relevant path
    spec.renderHoverDetails({ isActive: false, sourceChartName: 'figure_P1_spectrogram', timestamp: 0, spec_y: 0 }, { setBy: 'tap', frequency_labels: [], levels: [] });
    expect(hoverDiv.text).toContain('Hover over spectrogram for details');

    // Relevant path
    const freqBarData = { setBy: 'hover', frequency_labels: ['100 Hz', '200 Hz', '300 Hz'], levels: [10, 20, 30], param: 'LAeq' };
    const hoverState = { isActive: true, sourceChartName: 'figure_P1_spectrogram', timestamp: Date.now(), spec_y: 1.2 };
    spec.renderHoverDetails(hoverState, freqBarData);
    expect(hoverDiv.text).toContain('<b>Freq:</b> 200 Hz');
    expect(hoverDiv.text).toContain('LAeq');
  });

  it('PositionController should initialize charts and link companions', () => {
    const specRenderer = {
      glyph: { type: 'Image' },
      data_source: {
        data: { image: [new Float32Array(1)] },
        change: { emit: vi.fn() },
      },
    };

    const models = {
      charts: [
        {
          name: 'figure_P1_timeseries',
          x_range: {},
          y_range: {},
          add_layout: vi.fn(),
          remove_layout: vi.fn(),
          renderers: [],
        },
        {
          name: 'figure_P1_spectrogram',
          x_range: {},
          y_range: {},
          add_layout: vi.fn(),
          remove_layout: vi.fn(),
          renderers: [specRenderer],
        },
      ],
      chartsSources: [
        { name: 'source_P1_timeseries', data: {}, change: { emit: vi.fn() } },
      ],
      labels: [
        { name: 'label_P1_timeseries' },
        { name: 'label_P1_spectrogram' },
      ],
      hoverLines: [
        { name: 'hoverline_P1_timeseries' },
        { name: 'hoverline_P1_spectrogram' },
      ],
      hoverDivs: [
        { name: 'P1_spectrogram_hover_div' },
      ],
    };

    const pc = new classes.PositionController('P1', models);
    expect(pc.timeSeriesChart).toBeTruthy();
    expect(pc.spectrogramChart).toBeTruthy();
    // Spectrogram should have its time series companion set
    expect(pc.spectrogramChart.timeSeriesCompanion).toBe(pc.timeSeriesChart);
  });

  it('SpectrogramChart.update should update y-axis ticks when visible info provided', () => {
    const imageRenderer = { glyph: { type: 'Image' }, data_source: { data: { image: [new Float32Array(2)] }, change: { emit: vi.fn() } } };
    const chartModel = { name: 'figure_P1_spectrogram', renderers: [imageRenderer], title: { text: '' }, yaxis: { ticker: {}, major_label_overrides: {} }, y_range: { start: 0, end: 1 } };
    const spec = new classes.SpectrogramChart(chartModel, {}, {}, { text: '' }, 'P1');
    const replacement = {
      image: [new Float32Array([1, 2])], x: [0], dw: [2], y: [0], dh: [1],
      visible_freq_indices: [0, 1], visible_frequency_labels: ['1000 Hz', '2000 Hz'], y_range_start: 0, y_range_end: 1,
    };
    spec.update({ source_replacement: replacement }, { reason: ' (Log Data)' }, 'LAeq');
    expect(chartModel.yaxis.ticker.ticks).toEqual([0, 1]);
    expect(chartModel.yaxis.major_label_overrides[0]).toBe('1000');
    expect(chartModel.yaxis.major_label_overrides[1]).toBe('2000');
  });

  it('SpectrogramChart.getLabelText should fallback when no companion, and delegate when companion present', () => {
    const imageRenderer = { glyph: { type: 'Image' }, data_source: { data: { image: [new Float32Array(1)] }, change: { emit: vi.fn() } } };
    const chartModel = { name: 'figure_P1_spectrogram', renderers: [imageRenderer], title: { text: '' } };
    const spec = new classes.SpectrogramChart(chartModel, {}, {}, { text: '' }, 'P1');
    const txt = spec.getLabelText(0);
    expect(txt).toContain('Spectrogram Hover');

    const companion = { getLabelText: vi.fn().mockReturnValue('TS Label') };
    spec.setTimeSeriesCompanion(companion);
    expect(spec.getLabelText(123)).toBe('TS Label');
  });

  it('Chart.setVisible should toggle visibility', () => {
    const chartModel = { name: 'figure_P1_timeseries', visible: false, x_range: { start: 0, end: 1 }, y_range: { start: 0, end: 1 } };
    const chart = new classes.Chart(chartModel, { change: { emit: vi.fn() } }, {}, {}, 'P1');
    chart.setVisible(true);
    expect(chartModel.visible).toBe(true);
    // Setting same value should not change
    chart.setVisible(true);
    expect(chartModel.visible).toBe(true);
  });

  it('Chart.renderHoverLine should log error if hoverLineModel missing', () => {
    const chartModel = { name: 'figure_P1_timeseries' };
    const chart = new classes.Chart(chartModel, { change: { emit: vi.fn() } }, {}, undefined, 'P1');
    chart.renderHoverLine(123); // should not throw
  });

  it('Chart.update should throw when not implemented by subclass', () => {
    const chart = new classes.Chart({ name: 'any' }, { change: { emit: vi.fn() } }, {}, {}, 'P1');
    expect(() => chart.update()).toThrowError('Update method must be implemented by subclass.');
  });

  it('syncMarkers should still render when Bokeh document is missing', () => {
    const originalDocs = global.Bokeh.documents;
    global.Bokeh.documents = [];
    const chartModel = { name: 'figure_P1_timeseries', add_layout: vi.fn(), remove_layout: vi.fn(), x_range: { start: 0, end: 1 }, y_range: { start: 0, end: 1 } };
    const sourceModel = { change: { emit: vi.fn() } };
    const chart = new classes.Chart(chartModel, sourceModel, {}, {}, 'P1');
    chart.syncMarkers([100], true);
    expect(sourceModel.change.emit).toHaveBeenCalled();
    expect(chart.markerModels.length).toBe(0);
    global.Bokeh.documents = originalDocs;
  });

  it('SpectrogramChart.update handles mismatched image sizes gracefully', () => {
    const srcArray = new Float32Array(4);
    const imageRenderer = { glyph: { type: 'Image', x: 0, y: 0, dw: 0, dh: 0 }, data_source: { data: { image: [srcArray] }, change: { emit: vi.fn() } } };
    const chartModel = { name: 'figure_P1_spectrogram', renderers: [imageRenderer], title: { text: '' }, yaxis: { ticker: {}, major_label_overrides: {} }, y_range: { start: 0, end: 1 } };
    const spec = new classes.SpectrogramChart(chartModel, {}, {}, { text: '' }, 'P1');
    const replacement = { image: [new Float32Array([1, 2, 3])], x: [1], dw: [1], y: [0], dh: [1], visible_freq_indices: [0], visible_frequency_labels: ['1000 Hz'], y_range_start: 0, y_range_end: 0.5 };
    spec.update({ source_replacement: replacement }, { reason: ' (Log Data)' }, 'LAeq');
    // still updates glyph and y_range despite mismatch
    expect(spec.imageRenderer.glyph.x).toBe(1);
    expect(chartModel.y_range.end).toBe(0.5);
  });
});
