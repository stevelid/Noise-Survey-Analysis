// static/js/core.test.js

// Import Vitest functions and the function to test
import { describe, it, expect } from 'vitest';
// Adjust the path based on your structure - this assumes test file is in the same directory
// If tests/js/core.test.js, use '../../static/js/core.js' etc.
const { findClosestDateIndex, findClosestIndex } = require('./core.js'); // Use require for CommonJS export

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
})