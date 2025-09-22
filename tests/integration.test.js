import { describe, it, expect, beforeEach } from 'vitest';

// Load the full application stack to test integration
import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/init.js';
import '../noise_survey_analysis/static/js/services/eventHandlers.js';

describe('Application Integration Tests', () => {
  let store;
  let eventHandlers;

  beforeEach(() => {
    // Re-initialize the store before each test to ensure isolation
    window.NoiseSurveyApp.init.reInitializeStore();
    store = window.NoiseSurveyApp.store;
    eventHandlers = window.NoiseSurveyApp.eventHandlers;
  });

  it('handleParameterChange should update the selectedParameter in the store', () => {
    const initialParam = store.getState().view.selectedParameter;
    expect(initialParam).not.toBe('LCeq');

    // Act: Simulate the user changing the parameter via the event handler
    eventHandlers.handleParameterChange('LCeq');

    // Assert: The state in the real store has been updated
    const updatedParam = store.getState().view.selectedParameter;
    expect(updatedParam).toBe('LCeq');
  });

  it('handleTap should update the tap state in the store', () => {
    const initialState = store.getState().interaction.tap;
    expect(initialState.isActive).toBe(false);

    // Act: Simulate a tap event
    const tapEvent = { origin: { name: 'figure_P1_timeseries' }, x: 500 };
    eventHandlers.handleTap(tapEvent);

    // Assert: The tap state is now active with the correct details
    const updatedState = store.getState().interaction.tap;
    expect(updatedState.isActive).toBe(true);
    expect(updatedState.timestamp).toBe(500);
    expect(updatedState.position).toBe('P1');
    expect(updatedState.sourceChartName).toBe('figure_P1_timeseries');
  });

  it('handleViewToggle should update the globalViewType in the store', () => {
    const initialView = store.getState().view.globalViewType;
    expect(initialView).toBe('log'); // Default is 'log'

    // Act: Simulate toggling the view to overview
    eventHandlers.handleViewToggle(false); // false for 'overview'

    // Assert: The view type has changed
    const updatedView = store.getState().view.globalViewType;
    expect(updatedView).toBe('overview');
  });
});
