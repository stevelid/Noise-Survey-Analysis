import { describe, it, expect, beforeEach, vi } from 'vitest';

// Load modules in order
import '../noise_survey_analysis/static/js/actions.js';
import '../noise_survey_analysis/static/js/event-handlers.js';

describe('NoiseSurveyApp.eventHandlers (extra coverage)', () => {
  let dispatchAction;

  beforeEach(() => {
    vi.restoreAllMocks();
    dispatchAction = vi.fn();
    window.NoiseSurveyApp.store = { dispatch: dispatchAction, getState: () => ({ interaction: { tap: { timestamp: 123 } } }) };
    window.NoiseSurveyApp.registry = {
      models: {
        audio_status_source: { data: { is_playing: true, position_id: 'P1' } },
        audio_control_source: { data: {} },
      },
    };
  });

  it('handleTap with ctrl modifier should dispatch removeMarker', () => {
    const cb_obj = { origin: { name: 'figure_P1_timeseries' }, x: 100, modifiers: { ctrl: true } };
    window.NoiseSurveyApp.eventHandlers.handleTap(cb_obj);
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.removeMarker(100));
  });

  it('handleChartHover with no geometry should dispatch inactive hover', () => {
    const cb_data = { geometry: null };
    window.NoiseSurveyApp.eventHandlers.handleChartHover(cb_data, 'figure_P1_timeseries');
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.hover({ isActive: false }));
  });

  it('handleKeyPress should ignore events from input elements', () => {
    const event = { key: 'ArrowLeft', target: { tagName: 'INPUT' } };
    window.NoiseSurveyApp.eventHandlers.handleKeyPress(event);
    expect(dispatchAction).not.toHaveBeenCalled();
  });

  it('togglePlayPause with isActive=false should send pause command', () => {
    // This test now focuses on the action dispatching, not the side effect,
    // as side effects are handled by the app orchestrator, not the event handler itself.
    window.NoiseSurveyApp.eventHandlers.togglePlayPause('P1', false);
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.audioPlayPauseToggle('P1', false));
  });

  it('handleAudioStatusUpdate should dispatch the status from the model', () => {
    window.NoiseSurveyApp.eventHandlers.handleAudioStatusUpdate();
    const expectedStatus = { is_playing: true, position_id: 'P1' };
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.audioStatusUpdate(expectedStatus));
  });

  it('withErrorHandling should catch and log errors from wrapped functions', () => {
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Make an internal dependency of a wrapped function fail
    window.NoiseSurveyApp.store.dispatch.mockImplementation(() => {
      throw new Error('Dispatch Failed');
    });

    const cb_obj = { origin: { name: 'figure_P1_timeseries' }, x: 100, modifiers: {} };

    // Call the public, wrapped handler and expect it to re-throw
    expect(() => window.NoiseSurveyApp.eventHandlers.handleTap(cb_obj)).toThrow('Dispatch Failed');

    // Verify the wrapper caught and logged the specific error
    expect(errorSpy).toHaveBeenCalledWith(
      "[EventHandler Error] Function 'handleTap' failed:",
      expect.any(Error)
    );

    errorSpy.mockRestore();
  });

  it('handleChartHover with geometry should dispatch active hover', () => {
    const cb_data = { geometry: { x: 456, y: 1.23 } };
    window.NoiseSurveyApp.eventHandlers.handleChartHover(cb_data, 'figure_P2_spectrogram');
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.hover({
      isActive: true,
      sourceChartName: 'figure_P2_spectrogram',
      timestamp: 456,
      spec_y: 1.23,
      position: 'P2',
    }));
  });

  it('clearAllMarkers should dispatch the corresponding action', () => {
    window.NoiseSurveyApp.eventHandlers.clearAllMarkers();
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.clearAllMarkers());
  });

  it('handleViewToggle should dispatch action and update widget label', () => {
    const toggleWidget = { label: '' };
    window.NoiseSurveyApp.eventHandlers.handleViewToggle(true, toggleWidget);
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.viewToggle('log'));
    expect(toggleWidget.label).toBe('Log View Enabled');
  });

  it('handleHoverToggle should dispatch action and update widget label', () => {
    const toggleWidget = { label: '' };
    window.NoiseSurveyApp.eventHandlers.handleHoverToggle(false, toggleWidget);
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.hoverToggle(false));
    expect(toggleWidget.label).toBe('Hover Disabled');
  });

  it('handlePlaybackRateChange should dispatch the correct request action', () => {
    window.NoiseSurveyApp.eventHandlers.handlePlaybackRateChange('P1');
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.audioRateChangeRequest('P1'));
  });

  it('handleVolumeBoostToggle should dispatch the correct request action', () => {
    window.NoiseSurveyApp.eventHandlers.handleVolumeBoostToggle('P1', true);
    expect(dispatchAction).toHaveBeenCalledWith(window.NoiseSurveyApp.actions.audioBoostToggleRequest('P1', true));
  });

  it('handleTap should ignore events from frequency_bar', () => {
    const cb_obj = { origin: { name: 'frequency_bar' }, x: 100, modifiers: {} };
    window.NoiseSurveyApp.eventHandlers.handleTap(cb_obj);
    expect(dispatchAction).not.toHaveBeenCalled();
  });
});
