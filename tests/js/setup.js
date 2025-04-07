import { vi } from 'vitest';

/**
 * Creates a mock window object with common properties used by the noise-survey-analysis app
 * @returns {Object} Mock window object
 */
export function createMockWindow() {
  return {
    chartRefs: [],
    sources: {},
    clickLineModels: [],
    labelModels: [],
    playback_source: {
      data: { current_time: [0] },
      change: { emit: vi.fn() }
    },
    play_button_model: { disabled: false },
    pause_button_model: { disabled: true },
    verticalLinePosition: 0,
    activeChartIndex: -1,
    stepSize: 300000, // 5 minutes in ms
    keyboardNavigationEnabled: false,
    barSource: {
      data: { levels: [], frequency_labels: [] },
      change: { emit: vi.fn() }
    },
    barXRange: { factors: [] },
    hoverInfoDiv: { text: '' },
    selectedParamHolder: { data: { param: ['LZeq'] } },
    spectralFigures: {},
    allPositionsSpectralData: {},
    // Utility functions often attached to window
    updateAllLines: vi.fn(),
    findClosestDateIndex: vi.fn(),
    findClosestIndex: vi.fn(),
    createLabelText: vi.fn(),
    positionLabel: vi.fn(),
    calculateStepSize: vi.fn(),
    updateBarChartFromClickLine: vi.fn(),
    updateTapLinePositions: vi.fn(),
    hideAllLinesAndLabels: vi.fn(),
    getActiveChartIndex: vi.fn()
  };
}

/**
 * Creates a mock Bokeh chart model
 * @param {string} id - Chart ID
 * @param {string} name - Chart name (usually includes position)
 * @param {string} title - Chart title text
 * @param {number} xStart - X range start 
 * @param {number} xEnd - X range end
 * @param {number} yStart - Y range start
 * @param {number} yEnd - Y range end
 * @returns {Object} Mock chart object
 */
export function createMockChart(id, name, title, xStart, xEnd, yStart, yEnd) {
  return {
    id: id,
    name: name,
    title: { text: title },
    x_range: { start: xStart, end: xEnd },
    y_range: { start: yStart, end: yEnd },
    // Add mock select_one method if needed by tests
    select_one: vi.fn()
  };
}

/**
 * Creates a mock Bokeh ColumnDataSource
 * @param {Object} data - Data object with column arrays
 * @returns {Object} Mock source object
 */
export function createMockSource(data) {
  return {
    data: data,
    change: { emit: vi.fn() },
    on_change: vi.fn()
  };
}

/**
 * Creates a mock Bokeh Span (vertical or horizontal line)
 * @param {number} location - Line position
 * @param {boolean} visible - Visibility state
 * @param {string} dimensionType - Span dimension ('height' or 'width')
 * @returns {Object} Mock span object
 */
export function createMockSpan(location, visible = false, dimensionType = 'height') {
  return {
    location: location,
    visible: visible,
    dimension: dimensionType
  };
}

/**
 * Creates a mock Bokeh Label
 * @param {string} text - Label text
 * @param {boolean} visible - Visibility state
 * @param {number} x - X position
 * @param {number} y - Y position
 * @returns {Object} Mock label object
 */
export function createMockLabel(text = '', visible = false, x = 0, y = 0) {
  return {
    text: text,
    visible: visible,
    x: x,
    y: y,
    x_offset: 0,
    y_offset: 0,
    text_align: 'left',
    text_baseline: 'middle'
  };
}

/**
 * Creates sample spectral data for a position
 * @param {string} position - Position name (e.g., 'SW')
 * @param {Array} timePoints - Array of time points (milliseconds)
 * @param {Array} freqBands - Array of frequency bands
 * @returns {Object} Mock spectral data for the position
 */
export function createMockSpectralData(position, timePoints, freqBands) {
  const freqLabels = freqBands.map(f => f.toString() + ' Hz');
  
  // Create sample data matrices for parameters
  const lzeqValues = [];
  const laeqValues = [];
  
  // Generate sample values for each time point
  for (let t = 0; t < timePoints.length; t++) {
    const lzeqRow = [];
    const laeqRow = [];
    
    for (let f = 0; f < freqBands.length; f++) {
      // Sample values: LZeq slightly higher than LAeq
      lzeqRow.push(40 + 5 * Math.sin(t) + f);
      laeqRow.push(35 + 5 * Math.sin(t) + f);
    }
    
    lzeqValues.push(lzeqRow);
    laeqValues.push(laeqRow);
  }
  
  // Return a structured object for this position
  return {
    [position]: {
      common: {
        freq_bands: freqBands,
        freq_labels: freqLabels,
        n_freqs: freqBands.length,
        times_ms: timePoints
      },
      LZeq: { values: lzeqValues },
      LAeq: { values: laeqValues }
    }
  };
}

/**
 * Sets up a realistic DOM environment for keyboard tests
 */
export function setupDomEnvironment() {
  // Mock document with querySelector for play/pause buttons
  global.document = {
    querySelector: vi.fn(selector => {
      if (selector === '#play-button') {
        return { click: vi.fn(), disabled: false };
      }
      if (selector === '#pause-button') {
        return { click: vi.fn(), disabled: true };
      }
      return null;
    }),
    addEventListener: vi.fn()
  };
}

/**
 * Cleans up DOM mocks and restores the environment
 */
export function cleanupDomEnvironment() {
  delete global.document;
}

// Export a default config that can be imported in tests
export default {
  createMockWindow,
  createMockChart,
  createMockSource,
  createMockSpan,
  createMockLabel,
  createMockSpectralData,
  setupDomEnvironment,
  cleanupDomEnvironment
}; 