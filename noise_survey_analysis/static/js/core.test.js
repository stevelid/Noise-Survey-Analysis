// static/js/core.test.js

// Import Vitest functions and the function to test
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
// Adjust the path based on your structure - this assumes test file is in the same directory
// If tests/js/core.test.js, use '../../static/js/core.js' etc.
const { findClosestDateIndex, findClosestIndex, createLabelText, positionLabel, calculateStepSize } = require('./core.js'); // Use require for CommonJS export

// 'describe' groups related tests
describe('findClosestDateIndex', () => {
  const testDates = [
    1000, // 1 second
    5000, // 5 seconds
    10000, // 10 seconds
    20000, // 20 seconds
    60000, // 60 seconds
  ];

  // 'it' defines an individual test case
  it('should return the correct index for an exact match', () => {
    // Arrange
    const targetTime = 10000;
    // Act
    const index = findClosestDateIndex(testDates, targetTime);
    // Assert using 'expect'
    expect(index).toBe(2); // Expect index of 10000 to be 2
  });

  it('should return the index of the closest date (lower)', () => {
    const targetTime = 11000; // Closest to 10000
    const index = findClosestDateIndex(testDates, targetTime);
    expect(index).toBe(2);
  });

  it('should return the index of the closest date (higher)', () => {
    const targetTime = 19000; // Closest to 20000
    const index = findClosestDateIndex(testDates, targetTime);
    expect(index).toBe(3);
  });

  it('should return the first index if target is before start', () => {
    const targetTime = 500; // Before 1000
    const index = findClosestDateIndex(testDates, targetTime);
    expect(index).toBe(0);
  });

  it('should return the last index if target is after end', () => {
    const targetTime = 70000; // After 60000
    const index = findClosestDateIndex(testDates, targetTime);
    expect(index).toBe(4);
  });

   it('should return 0 for a single element array', () => {
    const index = findClosestDateIndex([15000], 12000);
    expect(index).toBe(0);
   });

  it('should return -1 for an empty array', () => {
    const index = findClosestDateIndex([], 10000);
    expect(index).toBe(-1);
  });

   it('should return -1 for invalid dates array', () => {
    expect(findClosestDateIndex(null, 10000)).toBe(-1);
    expect(findClosestDateIndex(undefined, 10000)).toBe(-1);
   });

   it('should return -1 for invalid target time', () => {
       expect(findClosestDateIndex(testDates, null)).toBe(-1);
       expect(findClosestDateIndex(testDates, undefined)).toBe(-1);
       // Depending on implementation, NaN might need specific check
       // expect(findClosestDateIndex(testDates, NaN)).toBe(-1);
   });
});

// Tests for findClosestIndex function
describe('findClosestIndex', () => {
  it('should find the closest value in an array', () => {
    const array = [10, 20, 30, 40, 50];
    expect(findClosestIndex(array, 25)).toBe(1); // Closest to 20
    expect(findClosestIndex(array, 35)).toBe(2); // Closest to 30
  });
  
  it('should return first index if target is before start', () => {
    const array = [10, 20, 30];
    expect(findClosestIndex(array, 5)).toBe(0);
  });
  
  it('should return last index if target is after end', () => {
    const array = [10, 20, 30];
    expect(findClosestIndex(array, 35)).toBe(2);
  });
  
  it('should return -1 for empty array', () => {
    expect(findClosestIndex([], 10)).toBe(-1);
  });
  
  it('should return -1 for invalid inputs', () => {
    expect(findClosestIndex(null, 10)).toBe(-1);
    expect(findClosestIndex(undefined, 10)).toBe(-1);
  });
});

// Tests for createLabelText function
describe('createLabelText', () => {
  // Mock date to ensure consistent format in tests
  let originalDate;
  
  beforeEach(() => {
    originalDate = global.Date;
    // Mock Date to ensure consistent output for toLocaleString
    global.Date = class extends Date {
      constructor(timestamp) {
        super(timestamp);
      }
      toLocaleString() {
        return '1/1/2023, 10:00:00 AM';
      }
    };
  });
  
  afterEach(() => {
    global.Date = originalDate;
  });
  
  it('should create label text with timestamp and all metrics', () => {
    // Mock source with data
    const mockSource = {
      data: {
        Datetime: [1672574400000], // 2023-01-01 10:00:00
        LAeq: [65.2],
        LAFmax: [75.3],
        LAF10: [68.4]
      }
    };
    
    const result = createLabelText(mockSource, 0);
    
    // Check if timestamp is formatted
    expect(result).toContain('Time: 1/1/2023, 10:00:00 AM');
    
    // Check if metrics are formatted correctly
    expect(result).toContain('LAeq: 65.2 dB');
    expect(result).toContain('LAFmax: 75.3 dB');
    expect(result).toContain('LAF10: 68.4 dB');
  });
  
  it('should handle numeric values that need formatting', () => {
    const mockSource = {
      data: {
        Datetime: [1672574400000],
        LAeq: [65.25], // Should be rounded to 1 decimal place
        LAFmax: [75.36],
        LAF10: [68]
      }
    };
    
    const result = createLabelText(mockSource, 0);
    
    expect(result).toContain('LAeq: 65.3 dB'); // Rounded to 1 decimal
    expect(result).toContain('LAFmax: 75.4 dB'); // Rounded to 1 decimal
    expect(result).toContain('LAF10: 68.0 dB'); // Formatted with 1 decimal
  });
  
  it('should handle undefined or NaN values', () => {
    const mockSource = {
      data: {
        Datetime: [1672574400000],
        LAeq: [65.2],
        LAFmax: [undefined],
        LAF10: [NaN],
        LZeq: ['invalid']
      }
    };
    
    const result = createLabelText(mockSource, 0);
    
    expect(result).toContain('LAeq: 65.2 dB');
    // Should skip undefined, NaN and non-numeric values
    expect(result).not.toContain('LAFmax');
    expect(result).not.toContain('LAF10');
    expect(result).not.toContain('LZeq');
  });
  
  it('should skip non-metric columns', () => {
    const mockSource = {
      data: {
        Datetime: [1672574400000],
        index: [0],
        LAeq: [65.2]
      }
    };
    
    const result = createLabelText(mockSource, 0);
    
    expect(result).toContain('LAeq: 65.2 dB');
    expect(result).not.toContain('index:');
  });
});

// Tests for positionLabel function
describe('positionLabel', () => {
  it('should position label to the right when x is in left half of chart', () => {
    // Mock label and chart
    const mockLabel = {
      x: 0,
      y: 0,
      text_align: '',
      text_baseline: ''
    };
    
    const mockChart = {
      x_range: { start: 1000, end: 5000 },
      y_range: { start: 30, end: 90 }
    };
    
    // Position in left half (1000-3000)
    positionLabel(2000, mockChart, mockLabel);
    
    // Label should be to the right of the line
    expect(mockLabel.x).toBeGreaterThan(2000);
    expect(mockLabel.text_align).toBe('left');
    expect(mockLabel.text_baseline).toBe('middle');
    
    // Check y position is in the middle of the range
    expect(mockLabel.y).toBe(60); // (90 + 30) / 2
  });
  
  it('should position label to the left when x is in right half of chart', () => {
    const mockLabel = {
      x: 0,
      y: 0,
      text_align: '',
      text_baseline: ''
    };
    
    const mockChart = {
      x_range: { start: 1000, end: 5000 },
      y_range: { start: 30, end: 90 }
    };
    
    // Position in right half (3000-5000)
    positionLabel(4000, mockChart, mockLabel);
    
    // Label should be to the left of the line
    expect(mockLabel.x).toBeLessThan(4000);
    expect(mockLabel.text_align).toBe('right');
    expect(mockLabel.text_baseline).toBe('middle');
  });
  
  it('should handle edge case at exactly middle of chart', () => {
    const mockLabel = {
      x: 0,
      y: 0,
      text_align: '',
      text_baseline: ''
    };
    
    const mockChart = {
      x_range: { start: 1000, end: 5000 },
      y_range: { start: 30, end: 90 }
    };
    
    // Position at exactly the middle (3000)
    positionLabel(3000, mockChart, mockLabel);
    
    // Implementation might choose either left or right
    // Just ensure text_align is set to either 'left' or 'right'
    expect(['left', 'right']).toContain(mockLabel.text_align);
    expect(mockLabel.text_baseline).toBe('middle');
  });
});

// Tests for calculateStepSize function
describe('calculateStepSize', () => {
  it('should calculate step size based on time intervals for many points', () => {
    const mockSource = {
      data: {
        Datetime: [
          1000,  // 1 second
          61000, // 1 minute + 1 second
          121000, // 2 minutes + 1 second
          181000, // 3 minutes + 1 second
          241000  // 4 minutes + 1 second
        ]
      }
    };
    
    // Average interval is 60,000 ms (1 minute)
    const stepSize = calculateStepSize(mockSource);
    
    // The function typically returns average interval * 5
    expect(stepSize).toBe(60000 * 5);
  });
  
  it('should return default step size for few points', () => {
    const mockSource = {
      data: {
        Datetime: [1000, 61000] // Just 2 points
      }
    };
    
    const stepSize = calculateStepSize(mockSource);
    
    // Default step size is typically 300,000 ms (5 minutes)
    expect(stepSize).toBe(300000);
  });
  
  it('should return default step size for empty data', () => {
    const mockSource = {
      data: {
        Datetime: []
      }
    };
    
    const stepSize = calculateStepSize(mockSource);
    expect(stepSize).toBe(300000);
  });
  
  it('should handle missing Datetime array', () => {
    const mockSource = {
      data: {}
    };
    
    const stepSize = calculateStepSize(mockSource);
    expect(stepSize).toBe(300000);
  });
  
  it('should handle null or undefined source', () => {
    expect(calculateStepSize(null)).toBe(300000);
    expect(calculateStepSize(undefined)).toBe(300000);
  });
});