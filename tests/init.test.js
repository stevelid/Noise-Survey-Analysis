import { describe, it, expect } from 'vitest';

// This test ensures init.js creates the store when prerequisites are present
// and that load order is correct (actions -> reducers -> init)

describe('NoiseSurveyApp.init (store creation)', () => {
  it('should create a global store when createStore, actions, and rootReducer are loaded in order', async () => {
    // Load Store first (no side-effects needing actions)
    await import('./loadCoreModules.js');
    // Now create the store via init.js (which depends on createStore + rootReducer)
    await import('../noise_survey_analysis/static/js/init.js');

    const app = window.NoiseSurveyApp;
    expect(app.store).toBeTruthy();
    expect(typeof app.store.getState).toBe('function');

    const state = app.store.getState();
    // Spot-check a few initial state properties from reducers.js
    expect(state.view.globalViewType).toBe('log');
    expect(state.interaction.keyboard.stepSizeMs).toBe(300000);
  });
});
