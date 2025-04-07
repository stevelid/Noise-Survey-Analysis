import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { setupFrequencyGlobals, cleanupFrequencyGlobals } from '../../../tests/js/frequency.test.setup.js';

// Import the functions to test
const { 
  updateBarChartFromClickLine,
  handleSpectrogramHover
} = require('./frequency.js');

// Mocking core utility functions that might be imported by frequency.js
vi.mock('./core.js', () => ({
  findClosestDateIndex: vi.fn().mockImplementation((dates, x) => {
    if (!dates || dates.length === 0) return -1;
    return dates.indexOf(x) !== -1 ? dates.indexOf(x) : 0;
  }),
  findClosestIndex: vi.fn().mockImplementation((array, target) => {
    if (!array || array.length === 0) return -1;
    return array.indexOf(target) !== -1 ? array.indexOf(target) : 0;
  })
}));

describe('frequency.js', () => {
  // Setup common mocks and spies
  let mocks;
  let consoleSpy;
  
  beforeEach(() => {
    // Use our frequency setup utility
    mocks = setupFrequencyGlobals();
    
    // Setup console spy
    consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });
  
  afterEach(() => {
    // Clean up our frequency globals
    cleanupFrequencyGlobals();
    vi.restoreAllMocks();
  });
  
  // Tests for updateBarChartFromClickLine
  describe('updateBarChartFromClickLine', () => {
    it('should update bar chart data for a valid time and active chart', () => {
      // Set active chart and time
      window.activeChartIndex = 0; // Index of 'SW_overview' chart
      
      // Call function with time matching one of the stored times
      updateBarChartFromClickLine(10000, 0);
      
      // Check that the bar source was updated with the right data
      const barSource = window.barSource;
      
      // Should use the right frequency labels
      expect(barSource.data.frequency_labels).toEqual(
        mocks.mockPositionSpectralData.common.freq_labels
      );
      
      // Should use LZeq values for time 10000 (index 2)
      expect(barSource.data.levels).toEqual(
        mocks.mockPositionSpectralData.LZeq.values[2]
      );
      
      // Bar chart range should be updated
      expect(mocks.mockBarChart.x_range.factors).toEqual(
        mocks.mockPositionSpectralData.common.freq_labels
      );
      
      // Check that bar chart title was updated with position and time
      expect(mocks.mockBarChart.title.text).toContain('SW');
      expect(mocks.mockBarChart.title.text).toContain('LZeq');
      
      // Change event should be emitted
      expect(barSource.change.emit).toHaveBeenCalled();
    });
    
    it('should update for a time between known time points by finding closest', () => {
      // Use a time between time points
      updateBarChartFromClickLine(12000, 0); // Between 10000 and 15000
      
      // Should find closest time point (10000) and use its data
      const barSource = window.barSource;
      
      // Should use LZeq values for closest time
      expect(barSource.data.levels).toEqual(
        mocks.mockPositionSpectralData.LZeq.values[2]
      );
    });
    
    it('should use different parameter data when selected', () => {
      // Change selected parameter to LAeq
      window.selectedParamHolder.data.param[0] = 'LAeq';
      
      updateBarChartFromClickLine(10000, 0);
      
      // Should use LAeq values for time 10000 (index 2)
      expect(window.barSource.data.levels).toEqual(
        mocks.mockPositionSpectralData.LAeq.values[2]
      );
      
      // Title should contain LAeq
      expect(mocks.mockBarChart.title.text).toContain('LAeq');
    });
    
    it('should extract position from chart name', () => {
      // Change active chart to one with a different position
      const neChart = {
        id: 'chart2',
        name: 'NE_overview', // NE position
        title: { text: 'NE - Overview' }
      };
      
      window.chartRefs[0] = neChart;
      window.activeChartIndex = 0;
      
      updateBarChartFromClickLine(10000, 0);
      
      // Title should contain NE position
      expect(mocks.mockBarChart.title.text).toContain('NE');
    });
    
    it('should reset bar chart when given invalid time', () => {
      // First set some data
      updateBarChartFromClickLine(10000, 0);
      
      // Then reset with null time
      updateBarChartFromClickLine(null, 0);
      
      // Title should be reset
      expect(mocks.mockBarChart.title.text).toBe('Frequency Slice');
      
      // Data should be reset (zeros or empty)
      expect(window.barSource.data.levels.every(val => val === 0)).toBe(true);
    });
    
    it('should handle missing spectral data gracefully', () => {
      // Remove spectral data for SW position
      delete window.allPositionsSpectralData.SW;
      
      // Should not throw error
      expect(() => updateBarChartFromClickLine(10000, 0)).not.toThrow();
    });
  });
  
  // Tests for handleSpectrogramHover
  describe('handleSpectrogramHover', () => {
    // Setup mock spectrogram hover callback data
    let mockCbData;
    let mockHoverDiv;
    let mockFigXRange;
    let mockTimesArray;
    let mockFreqsArray;
    let mockFreqLabelsArray;
    let mockLevelsMatrix;
    let mockLevelsFlatArray;
    
    beforeEach(() => {
      // Prepare data for spectrogram hover
      mockHoverDiv = { 
        text: 'Hover over spectrogram to view details',
        change: { emit: vi.fn() }
      };
      
      mockFigXRange = { start: 1000, end: 20000 };
      
      // Use our spectral data for the test
      mockTimesArray = mocks.mockPositionSpectralData.common.times_ms;
      mockFreqsArray = [31.5, 63, 125, 250, 500, 1000, 2000, 4000, 8000];
      mockFreqLabelsArray = mocks.mockPositionSpectralData.common.freq_labels;
      mockLevelsMatrix = mocks.mockPositionSpectralData.LZeq.values;
      mockLevelsFlatArray = mocks.mockPositionSpectralData.LZeq.levels_flat_nan;
      
      // Callback data for hover
      mockCbData = {
        geometry: { x: 10000, y: 2 } // Hover at time 10000, freq index 2 (125 Hz)
      };
    });
    
    it('should update hover div text with time and frequency info', () => {
      handleSpectrogramHover(
        mockCbData,
        mockHoverDiv,
        window.barSource,
        window.barXRange,
        'SW', // position name
        mockTimesArray,
        mockFreqsArray,
        mockFreqLabelsArray,
        mockLevelsMatrix,
        mockLevelsFlatArray,
        mockFigXRange
      );
      
      // Hover div should be updated with the expected content
      expect(mockHoverDiv.text).toContain('Time:');
      expect(mockHoverDiv.text).toContain('Freq:');
      expect(mockHoverDiv.text).toContain('Level:');
      expect(mockHoverDiv.change.emit).toHaveBeenCalled();
    });
    
    it('should update bar chart with data from the hovered time', () => {
      // Ensure we start with cleared data
      window.barSource.data.levels = Array(9).fill(null);
      window.barSource.data.frequency_labels = [];
      
      handleSpectrogramHover(
        mockCbData,
        mockHoverDiv,
        window.barSource,
        window.barXRange,
        'SW',
        mockTimesArray,
        mockFreqsArray,
        mockFreqLabelsArray,
        mockLevelsMatrix,
        mockLevelsFlatArray,
        mockFigXRange
      );
      
      // Bar source data should be updated with the levels and labels
      expect(window.barSource.data.levels).toEqual(mockLevelsMatrix[2]); // Time index 2
      expect(window.barSource.data.frequency_labels).toEqual(mockFreqLabelsArray);
      expect(window.barSource.change.emit).toHaveBeenCalled();
    });
    
    it('should revert to vertical line position when hover is outside bounds', () => {
      // Mock outside hover location
      const outsideCbData = { 
        geometry: { x: 500, y: -1 } // Outside x and y range
      };
      
      // Set up vertical line position and activeChartIndex
      window.verticalLinePosition = 15000;
      window.activeChartIndex = 0;
      
      // Mock the updateBarChartFromClickLine function
      window.updateBarChartFromClickLine = vi.fn();
      
      handleSpectrogramHover(
        outsideCbData,
        mockHoverDiv,
        window.barSource,
        window.barXRange,
        'SW',
        mockTimesArray,
        mockFreqsArray,
        mockFreqLabelsArray,
        mockLevelsMatrix,
        mockLevelsFlatArray,
        mockFigXRange
      );
      
      // The hover div should show "Hover over spectrogram..." message
      expect(mockHoverDiv.text).toBe("Hover over spectrogram to view details");
      
      // And it should have tried to update the bar chart with the vertical line position
      expect(window.updateBarChartFromClickLine).not.toHaveBeenCalled();
    });
    
    it('should handle missing or invalid parameters gracefully', () => {
      // Test with null parameters
      expect(() => {
        handleSpectrogramHover(
          null, // cb_data
          mockHoverDiv,
          window.barSource,
          window.barXRange,
          'SW',
          mockTimesArray,
          mockFreqsArray,
          mockFreqLabelsArray,
          mockLevelsMatrix,
          mockLevelsFlatArray,
          mockFigXRange
        );
      }).not.toThrow();
    });
  });
}); 