# JavaScript Tests for Noise Survey Analysis Client-Side Code

This directory contains unit and integration tests for the client-side JavaScript code of the noise-survey-analysis application. The tests use Vitest as the testing framework with JSDOM for DOM simulation.

## Test Structure

The tests are organized to mirror the source file structure:

- `core.test.js`: Tests for utility functions in `static/js/core.js`
- `charts.test.js`: Tests for chart interactions in `static/js/charts.js`
- `frequency.test.js`: Tests for frequency visualization in `static/js/frequency.js`
- `audio.test.js`: Tests for audio playback visualization in `static/js/audio.js`

## Running Tests

To run the tests, use the following npm scripts from the project root:

```bash
# Run all tests once
npm test

# Run tests in watch mode during development
npm run test:watch

# Run tests with the Vitest UI
npm run test:ui

# Generate test coverage report
npm run coverage
```

## Mocking Strategy

The tests use several mocking approaches to handle the Bokeh/browser environment:

1. **Bokeh Models**: Simplified JavaScript objects are used to represent Bokeh models (Charts, Sources, Spans, Labels, etc.)
2. **Window Object**: `vi.stubGlobal('window', mockWindow)` is used to mock the global window object
3. **DOM Elements**: JSDOM is used to simulate DOM elements and events
4. **Core Functions**: Core utility functions are mocked as needed using `vi.mock('./core.js', ...)`

## Testing Considerations

### Bokeh Integration

The client-side code heavily relies on Bokeh models passed from Python. These tests focus on the JavaScript logic while simulating the Bokeh environment using simplified mock objects.

### Global State

Many functions interact with global state stored on the window object. Each test sets up a clean environment using `beforeEach` and restores mocks with `afterEach`.

### DOM Interactions

For tests involving keyboard events or DOM interactions, we use JSDOM to simulate the browser environment.

## Coverage Gaps

Some aspects are challenging to fully test:

1. **Real Bokeh Model Behavior**: Actual Bokeh model behavior might differ from our mocks
2. **Visual Rendering**: Actual visual rendering can't be fully tested
3. **Complex User Interactions**: Multi-step interactions with a real browser environment

These tests provide a baseline for core functionality before refactoring, focusing on logical correctness rather than complete simulation of the browser environment. 