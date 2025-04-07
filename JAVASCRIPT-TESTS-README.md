# JavaScript Tests Implementation for noise-survey-analysis

This README provides an overview of the JavaScript test implementation for the client-side code of the noise-survey-analysis application.

## What's Implemented

A complete suite of unit and integration tests has been created for the existing client-side JavaScript code:

1. **Core Functions Tests** (`core.test.js`):
   - Tests for utility functions like `findClosestDateIndex`, `findClosestIndex`
   - Tests for label creation and positioning with `createLabelText`, `positionLabel`
   - Tests for data navigation with `calculateStepSize`

2. **Chart Interaction Tests** (`charts.test.js`):
   - Tests for chart line updates with `updateChartLine`, `updateTapLinePositions`
   - Tests for event handlers like `handleHover`, `handleTap`
   - Tests for keyboard navigation with `handleKeyPress`, `enableKeyboardNavigation`
   - Tests for utility functions like `getActiveChartIndex`, `hideAllLinesAndLabels`

3. **Frequency Visualization Tests** (`frequency.test.js`):
   - Tests for frequency bar chart updates with `updateBarChartFromClickLine`
   - Tests for spectrogram interaction with `handleSpectrogramHover`

4. **Audio Playback Tests** (`audio.test.js`):
   - Tests for playback visualization with `updatePlaybackPosition`, `initializeAudioVisualization`
   - Tests for playback control with `onPlayButtonClick`, `onPauseButtonClick`, `onStopButtonClick`

5. **Test Utilities** (`setup.js`):
   - Shared functions to create mock Bokeh models
   - Mock window object creation
   - DOM environment setup for keyboard tests
   - Mock spectral data generation

## Test Design Approach

The tests follow these design principles:

1. **Isolation**: Each test function is tested in isolation with mocked dependencies
2. **Mock Bokeh Environment**: Simplified JavaScript objects simulate Bokeh models
3. **Global State Management**: Window objects are mocked and reset between tests
4. **JSDOM Integration**: DOM interactions are tested using JSDOM simulation

## Running the Tests

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

## Test Directory Structure

```
tests/
  └── js/
      ├── README.md          # JS tests documentation
      └── setup.js           # Shared test utilities and mock factories
noise_survey_analysis/
  └── static/
      └── js/
          ├── core.js        # Source code
          ├── core.test.js   # Tests alongside source
          ├── charts.js
          ├── charts.test.js
          ├── frequency.js
          ├── frequency.test.js
          ├── audio.js
          └── audio.test.js
```

## Mocking Strategy

The tests use a layered mocking approach:

1. **Window Object**: Global window state is mocked using `vi.stubGlobal`
2. **Bokeh Models**: Chart, Source, Span, Label models are mocked as simple objects
3. **DOM Elements**: JSDOM provides DOM element simulation
4. **Event Objects**: Mock event objects simulate user interactions

## Testing Limitations

The tests focus on JavaScript logic rather than visual correctness:

1. **Bokeh Integration**: Real Bokeh interaction is simplified
2. **Visual Output**: Actual chart rendering is not tested
3. **Full User Journeys**: Complex interaction sequences are not fully tested

## Next Steps

These tests establish a baseline for the existing code before refactoring. As the code is refactored:

1. Run tests to ensure functionality is preserved
2. Update tests as code patterns change
3. Consider adding end-to-end tests for critical user flows 