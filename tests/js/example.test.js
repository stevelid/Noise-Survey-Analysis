// example.test.js
import { describe, it, expect } from 'vitest';

// A simple function to test
function sum(a, b) {
  return a + b;
}

describe('Example Test Suite', () => {
  it('adds 1 + 2 to equal 3', () => {
    expect(sum(1, 2)).toBe(3);
  });

  it('concatenates strings', () => {
    expect(sum('hello ', 'world')).toBe('hello world');
  });

  it('demonstrates different assertions', () => {
    // Object equality
    expect({ name: 'John' }).toEqual({ name: 'John' });
    
    // Truthiness
    expect(true).toBeTruthy();
    expect(false).toBeFalsy();
    
    // Arrays
    expect([1, 2, 3]).toContain(2);
    
    // Negations
    expect(5).not.toBe(10);
  });
}); 