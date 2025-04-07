// frequency.test.setup.js
// Mock globals used in frequency.js to avoid test failures

// Setup mock spectral data
function createMockSpectralData() {
  return {
    common: {
      n_freqs: 9,
      times_ms: [1000, 5000, 10000, 15000, 20000],
      freq_labels: ['31.5 Hz', '63 Hz', '125 Hz', '250 Hz', '500 Hz', '1000 Hz', '2000 Hz', '4000 Hz', '8000 Hz'],
      frequency_labels_str: ['31.5 Hz', '63 Hz', '125 Hz', '250 Hz', '500 Hz', '1000 Hz', '2000 Hz', '4000 Hz', '8000 Hz']
    },
    LZeq: {
      values: [
        [45, 50, 55, 60, 58, 56, 52, 48, 42], // Time 1
        [46, 51, 56, 61, 59, 57, 53, 49, 43], // Time 2
        [47, 52, 57, 62, 60, 58, 54, 50, 44], // Time 3
        [48, 53, 58, 63, 61, 59, 55, 51, 45], // Time 4
        [49, 54, 59, 64, 62, 60, 56, 52, 46]  // Time 5
      ],
      levels_flat_nan: [45, 50, 55, 60, 58, 56, 52, 48, 42, 46, 51, 56, 61, 59, 57, 53, 49, 43, 47, 52, 57, 62, 60, 58, 54, 50, 44, 48, 53, 58, 63, 61, 59, 55, 51, 45, 49, 54, 59, 64, 62, 60, 56, 52, 46]
    },
    LAeq: {
      values: [
        [40, 45, 50, 55, 53, 51, 47, 43, 37], // Time 1
        [41, 46, 51, 56, 54, 52, 48, 44, 38], // Time 2
        [42, 47, 52, 57, 55, 53, 49, 45, 39], // Time 3
        [43, 48, 53, 58, 56, 54, 50, 46, 40], // Time 4
        [44, 49, 54, 59, 57, 55, 51, 47, 41]  // Time 5
      ],
      levels_flat_nan: [40, 45, 50, 55, 53, 51, 47, 43, 37, 41, 46, 51, 56, 54, 52, 48, 44, 38, 42, 47, 52, 57, 55, 53, 49, 45, 39, 43, 48, 53, 58, 56, 54, 50, 46, 40, 44, 49, 54, 59, 57, 55, 51, 47, 41]
    }
  };
}

// Setup global window variables for frequency.js
function setupFrequencyGlobals() {
  // Create mocks for charts
  const mockBarChart = {
    name: 'frequency_bar',
    title: { text: 'Frequency Slice' },
    x_range: { factors: [] }
  };
  
  const mockChartRefs = [
    { id: 'chart1', name: 'SW_overview', title: { text: 'SW - Overview' } },
    mockBarChart
  ];
  
  // Create mock for bar source
  const mockBarSource = {
    data: {
      levels: [],
      frequency_labels: []
    },
    change: {
      emit: vi.fn()
    }
  };
  
  // Create mock for bar x range
  const mockBarXRange = { factors: [] };
  
  // Create mock for selected parameter holder
  const mockSelectedParamHolder = {
    data: {
      param: ['LZeq']
    }
  };
  
  // Create spectral data
  const mockPositionSpectralData = createMockSpectralData();
  
  // Set up window globals
  window.chartRefs = mockChartRefs;
  window.barSource = mockBarSource;
  window.barXRange = mockBarXRange;
  window.selectedParamHolder = mockSelectedParamHolder;
  window.allPositionsSpectralData = {
    SW: mockPositionSpectralData,
    NE: mockPositionSpectralData
  };
  window.activeChartIndex = 0;
  window.selectedParam = 'LZeq';
  window.verticalLinePosition = 0;
  window.updateBarChartFromClickLine = vi.fn();
  
  // Mock console methods
  global.console = {
    log: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  };
  
  // Return references for direct test access
  return {
    mockBarChart,
    mockChartRefs,
    mockBarSource,
    mockBarXRange,
    mockSelectedParamHolder,
    mockPositionSpectralData
  };
}

// Clean up globals after tests
function cleanupFrequencyGlobals() {
  delete window.chartRefs;
  delete window.barSource;
  delete window.barXRange;
  delete window.selectedParamHolder;
  delete window.allPositionsSpectralData;
  delete window.activeChartIndex;
  delete window.selectedParam;
  delete window.verticalLinePosition;
  delete window.updateBarChartFromClickLine;
  
  vi.restoreAllMocks();
}

module.exports = {
  createMockSpectralData,
  setupFrequencyGlobals,
  cleanupFrequencyGlobals
}; 