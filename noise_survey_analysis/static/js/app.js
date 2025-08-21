// noise_survey_analysis/static/js/app.js

/**
 * @fileoverview Main entry point for the Noise Survey application.
 * This file is responsible for initializing the application, wiring together all the
 * modules (state, processors, renderers, event handlers), and exposing the
 * public API to the Bokeh template. It acts as the central orchestrator
 * but contains minimal application logic itself.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    function initialize(models, options) {
        try {
            console.info('[NoiseSurveyApp]', 'Initializing...');

            // 1. Tell the state manager to initialize itself with the models
            app.state.initializeState(models, options);

            // 2. Connect event handlers to Bokeh models
            // This is "wiring," which is a perfect job for app.js
            console.log("[DEBUG] Models loaded: ", models);
            console.log("[DEBUG] Connecting event handlers...");
            const liveModels = app.models; // Get the populated models
            if (liveModels.audio_status_source) {
                liveModels.audio_status_source.patching.connect(app.eventHandlers.handleAudioStatusUpdate);
            }

            //keyboard setup
            const state = app.state.getState(); // Get the current state
            if (!state.interaction.keyboard.enabled) {
                document.addEventListener('keydown', app.eventHandlers.handleKeyPress);
                app.state.dispatchAction({ type: 'KEYBOARD_SETUP_COMPLETE' });
            }

            // 3. Kick off the first render by dispatching the INITIAL_LOAD action
            app.state.dispatchAction({ type: 'INITIAL_LOAD' });

            console.info('[NoiseSurveyApp]', 'App initialized successfully.');
            return true;

        }
        catch (error) {
            console.error('[NoiseSurveyApp]', 'Error initializing app:', error);
            return false;
        }
    }

    // Attach the final public API
    app.init = initialize;

})(window.NoiseSurveyApp);