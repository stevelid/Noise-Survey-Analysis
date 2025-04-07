// charts.test.setup.js
// Mock globals used in charts.js to avoid test failures

// Setup global variables that handleTap depends on
function setupGlobals() {
  global.globalInitialized = true;
  global.globalChartRefs = [
    { 
      id: 'chart1',
      name: 'SW_overview', 
      title: { text: 'SW - Overview' },
      x_range: { start: 1000, end: 5000 },
      y_range: { start: 30, end: 90 }
    },
    {
      id: 'chart2',
      name: 'frequency_bar',
      title: { text: 'Frequency Slice' },
      x_range: { factors: [] }
    }
  ];
  global.globalClickLineModels = [
    { visible: true, location: 0 },
    { visible: true, location: 0 }
  ];
  global.globalLabelModels = [
    { visible: true, text: '', x: 0, y: 0, text_align: '', text_baseline: '' },
    { visible: true, text: '', x: 0, y: 0, text_align: '', text_baseline: '' }
  ];
  global.globalPlaybackSource = {
    data: { current_time: [0] },
    change: { emit: vi.fn() }
  };
  
  // Set window properties
  window.chartRefs = global.globalChartRefs;
  window.clickLineModels = global.globalClickLineModels;
  window.labelModels = global.globalLabelModels;
  window.playback_source = global.globalPlaybackSource;
  window.activeChartIndex = 0;
  window.verticalLinePosition = 3000;
  window.updateTapLinePositions = vi.fn();
  window.updatePlaybackSource = vi.fn();
  window.updateBarChartFromClickLine = vi.fn();
  window.hideAllLinesAndLabels = vi.fn();
  window.getActiveChartIndex = vi.fn().mockReturnValue(0);
  
  // Mock sources with valid Datetime arrays
  window.sources = {
    'SW_overview': {
      data: {
        Datetime: [1000, 2000, 3000, 4000, 5000],
        LAeq: [50, 55, 52, 58, 53]
      }
    }
  };
  
  // Mock console methods
  global.console = {
    log: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  };
}

// Clean up globals to avoid test contamination
function cleanupGlobals() {
  delete global.globalInitialized;
  delete global.globalChartRefs;
  delete global.globalClickLineModels;
  delete global.globalLabelModels;
  delete global.globalPlaybackSource;
  
  // Clean window properties
  delete window.chartRefs;
  delete window.clickLineModels;
  delete window.labelModels;
  delete window.playback_source;
  delete window.activeChartIndex;
  delete window.verticalLinePosition;
  delete window.updateTapLinePositions;
  delete window.updatePlaybackSource;
  delete window.updateBarChartFromClickLine;
  delete window.hideAllLinesAndLabels;
  delete window.getActiveChartIndex;
  delete window.sources;
  
  vi.restoreAllMocks();
}

module.exports = {
  setupGlobals,
  cleanupGlobals
}; 