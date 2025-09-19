// noise_survey_analysis/static/js/app.js

/**
 * @fileoverview Main entry point and orchestrator for the Noise Survey application.
 * This file is responsible for:
 * 1. Initializing all modules (Registry, Store).
 * 2. Subscribing to the store to listen for state changes.
 * 3. Acting as the central controller that triggers data processing, rendering,
 *    and other side effects in response to state changes.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    // --- Module-level variables ---
    let previousState; // used to track state changes

    // The mutable, non-serializable data cache for large data arrays.
    const dataCache = {
        activeLineData: {},
        activeSpectralData: {},
        activeFreqBarData: {},
        _spectrogramCanvasBuffers: {}
    };

    /**
     * The main application entry point, called from the Bokeh template.
     * @param {object} bokehModels - The collection of models passed from Bokeh.
     */
    function initialize(bokehModels) {
        try {
            console.info('[App]', 'Initializing...');

            // --- 1. INITIALISE THE REGISTRY & STORE ---
            const initialStatePayload = app.registry.initialize(bokehModels);

            // Expand the cache for each available position before the first render
            initialStatePayload.availablePositions.forEach(pos => {
                dataCache.activeLineData[pos] = {};
                dataCache.activeSpectralData[pos] = {};
            });

            app.store.dispatch(app.actions.initializeState(initialStatePayload));

            // --- 2. CONNECT BOKEH EVENT LISTENERS ---
            const { models } = app.registry;
            if (models.audio_status_source) {
                // This listener dispatches an action when Python sends new audio status
                models.audio_status_source.patching.connect(app.eventHandlers.handleAudioStatusUpdate);
            }

            // --- 3. SETUP KEYBOARD & OTHER GLOBAL EVENT LISTENERS ---
            document.addEventListener('keydown', app.eventHandlers.handleKeyPress);
            app.store.dispatch(app.actions.keyboardSetupComplete());

            // --- 4. SUBSCRIBE TO STORE CHANGES ---
            previousState = app.store.getState();
            app.store.subscribe(onStateChange);

            // --- 5. KICK OFF THE FIRST RENDER ---
            // Trigger the first data processing and render pass manually.
            onStateChange(true); // Pass a flag to indicate it's the initial load

            console.info('[App]', 'App initialized successfully.');

            return true;
        }
        catch (error) {
            console.error('[App]', 'Error initializing app:', error);
            return false;
        }
    }

    /**
     * The master controller function, called by the store after EVERY state update.
     * It compares the new state to the previous state to determine what changed,
     * then orchestrates all necessary data processing, rendering, and side effects.
     * @param {boolean} [isInitialLoad=false] - A flag to force a full update.
     */
    function onStateChange(isInitialLoad = false) {
        const state = app.store.getState();
        const { models, controllers } = app.registry;

        // --- A. DETERMINE UPDATE TYPE (HEAVY vs. LIGHT) ---
        // These state changes require re-calculating the main chart data
        const didViewportChange = state.view.viewport !== previousState.view.viewport;
        const didParamChange = state.view.selectedParameter !== previousState.view.selectedParameter;
        const didViewToggleChange = state.view.globalViewType !== previousState.view.globalViewType;
        const didVisibilityChange = state.view.chartVisibility !== previousState.view.chartVisibility;
        const didMarkersChange = state.markers.timestamps !== previousState.markers.timestamps;
        const didRegionsChange = state.markers.regions !== previousState.markers.regions;

        const isHeavyUpdate = isInitialLoad || didViewportChange || didParamChange || didViewToggleChange || didVisibilityChange;

        // --- B. ORCHESTRATE DATA PROCESSING & RENDERING ---
        if (isHeavyUpdate) {
            // 1. Process heavy data (time series, spectrograms)
            app.data_processors.updateActiveData(state.view, dataCache, app.registry.models);

            // 2. Calculate new step size based on new data 
            const newStepSize = app.data_processors.calculateStepSize(state, dataCache);
            if (newStepSize !== state.interaction.keyboard.stepSizeMs) {
                app.store.dispatch(app.actions.stepSizeCalculated(newStepSize));
            }

            // 3. Render the main charts with the new data
            app.renderers.renderPrimaryCharts(state, dataCache);
        }

        // Always update the frequency bar, as it depends on hover/tap (light changes)
        app.data_processors.updateActiveFreqBarData(state, dataCache);
        app.renderers.renderFrequencyBar(state, dataCache);

        // Always update overlays (tap lines, hover lines, labels)
        app.renderers.renderOverlays(state, dataCache);

        // Always keep UI widgets in sync with the stat
        app.renderers.renderControlWidgets(state);

        // Always sync markers
        if (isInitialLoad || didMarkersChange) {
            app.renderers.renderMarkers(state);
        }

        if (isInitialLoad || didRegionsChange) {
            app.renderers.renderRegions(state, dataCache);
        }

        if ((isInitialLoad || didRegionsChange) && app.regions?.prepareMetricsUpdates) {
            const updates = app.regions.prepareMetricsUpdates(state, dataCache, models) || [];
            updates.forEach(update => {
                app.store.dispatch(app.actions.regionSetMetrics(update.id, update.metrics));
            });
        }

        if (app.renderers && typeof app.renderers.renderComparisonMode === 'function') {
            app.renderers.renderComparisonMode(state);
        }

        // --- C. HANDLE SIDE EFFECTS ---
        // These are tasks that interact with the outside world (e.g., Bokeh backend)
        handleAudioSideEffects(state, previousState, models);

        // --- D. CLEANUP ---
        // Update previousState for the next cycle
        previousState = state;
    }

    /**
     * Manages sending all commands to the audio backend based on state changes.
     * This function is the single point of contact with the audio_control_source.
     */
    function handleAudioSideEffects(current, previous, models) {
        const { actionTypes } = app;
        const lastAction = current.system.lastAction;
        if (!lastAction) return;
    
        // --- A. Handle User-Initiated Playback (Tap, KeyNav, or Play Button) ---
        const wasUserInitiatedPlayback = (
            lastAction.type === actionTypes.TAP || 
            lastAction.type === actionTypes.KEY_NAV ||
            (lastAction.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE && lastAction.payload.isActive) // Play only
        );
    
        if (wasUserInitiatedPlayback) {
            // A tap, key nav, or "play" button press is an explicit intent to hear audio.
            // We always send a 'play' command.
            const position = lastAction.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE 
                ? lastAction.payload.positionId 
                : current.interaction.tap.position;
    
            const timestamp = current.interaction.tap.timestamp;
    
            console.log(`[Side Effect] Sending 'play' command for ${position} @ ${new Date(timestamp).toLocaleTimeString()}`);
            models.audio_control_source.data = {
                command: ['play'],
                position_id: [position],
                value: [timestamp]
            };
            return; // This was the primary action, no other audio commands needed.
        }
        
        // --- B. Handle Pause Button ---
        if (lastAction.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE && !lastAction.payload.isActive) {
            console.log(`[Side Effect] Sending 'pause' command for ${lastAction.payload.positionId}`);
            models.audio_control_source.data = {
                command: ['pause'],
                position_id: [lastAction.payload.positionId],
                value: [null] // Value not needed for pause
            };
            return;
        }
    
        // --- C. Handle Secondary Audio Control Changes (Rate, Boost) ---
        // These actions only modify the currently playing stream, they don't start it.

        // Did the playback rate change due to a user request?
        if (current.audio.playbackRate !== previous.audio.playbackRate && lastAction.type === actionTypes.AUDIO_RATE_CHANGE_REQUEST) {
            console.log(`[Side Effect] Sending 'set_rate' command: ${current.audio.playbackRate}`);
            models.audio_control_source.data = {
                command: ['set_rate'],
                position_id: [current.audio.activePositionId],
                value: [current.audio.playbackRate]
            };
        }

        // Did the volume boost state change due to a user request?
        if (current.audio.volumeBoost !== previous.audio.volumeBoost && lastAction.type === actionTypes.AUDIO_BOOST_TOGGLE_REQUEST) {
            console.log(`[Side Effect] Sending 'toggle_boost' command: ${current.audio.volumeBoost}`);
            models.audio_control_source.data = {
                command: ['toggle_boost'],
                position_id: [current.audio.activePositionId],
                value: [current.audio.volumeBoost]
            };
        }
        // --- C. Handle Play/Pause Toggle from UI Buttons ---
        if (lastAction.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE) {
            const { positionId, isActive } = lastAction.payload;
            const command = isActive ? 'play' : 'pause';
            // Use the current tap timestamp as the starting point for playback
            const timestamp = current.interaction.tap.timestamp;

            console.log(`[Side Effect] Sending '${command}' command for ${positionId} @ ${new Date(timestamp).toLocaleTimeString()}`);
            models.audio_control_source.data = {
                command: [command],
                position_id: [positionId],
                value: [timestamp]
            };
            return;
        }
    }


    // Expose side-effect handlers for orchestrator in init.js
    app.handleAudioSideEffects = handleAudioSideEffects;


    // Attach the public initialization function (legacy path)
    if (app.init) {
        app.init.initialize = initialize;
    } else {
        // Fallback in case init.js didn't load, though it should have.
        app.init = { initialize: initialize };
    }

})(window.NoiseSurveyApp);