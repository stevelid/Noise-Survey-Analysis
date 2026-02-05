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
    let _lastHeavyUpdateTime = 0; // Timestamp of last heavy update for throttling
    let _pendingHeavyUpdate = null; // Pending heavy update RAF handle
    const HEAVY_UPDATE_THROTTLE_MS = 50; // Minimum ms between heavy updates during audio playback

    // The mutable, non-serializable data cache for large data arrays.
    const dataCache = {
        activeLineData: {},
        activeSpectralData: {},
        activeFreqBarData: {},
        _spectrogramCanvasBuffers: {}
    };

    const logStepSizeByPosition = {};
    const lineDisplayTypeByPosition = {};

    function computeMedianPositiveStep(datetime) {
        if (!datetime || datetime.length < 2) {
            return;
        }

        const diffs = [];
        const maxPairs = Math.min(datetime.length - 1, 2000);
        for (let i = 0; i < maxPairs; i++) {
            const a = Number(datetime[i]);
            const b = Number(datetime[i + 1]);
            const diff = b - a;
            if (Number.isFinite(diff) && diff > 0) {
                diffs.push(diff);
            }
        }

        if (!diffs.length) {
            return;
        }

        diffs.sort((x, y) => x - y);
        let step = diffs[Math.floor(diffs.length / 2)];

        const oneHour = 3600000;
        step = Math.min(step, oneHour);
        return step;
    }

    app.dataCache = dataCache;

    function handleDragToolKeyDown(event) {
        if (event.key !== 'Shift') {
            return;
        }
        const state = app.store.getState();
        if (state?.interaction?.activeDragTool !== 'box_select') {
            app.store.dispatch(app.actions.dragToolChanged('box_select'));
        }
    }

    function handleDragToolKeyUp(event) {
        if (event.key !== 'Shift') {
            return;
        }
        const state = app.store.getState();
        if (state?.interaction?.activeDragTool !== 'pan') {
            app.store.dispatch(app.actions.dragToolChanged('pan'));
        }
    }

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

            const { models } = app.registry;
            initialStatePayload.availablePositions.forEach(pos => {
                const datetime = models?.timeSeriesSources?.[pos]?.log?.data?.Datetime;
                const step = computeMedianPositiveStep(datetime);
                if (Number.isFinite(step)) {
                    logStepSizeByPosition[pos] = step;
                }
            });

            app.store.dispatch(app.actions.initializeState(initialStatePayload));
            if (app.data_processors?.calculateStepSize) {
                app.data_processors.calculateStepSize(app.store.getState(), dataCache);
            }

            // --- 2. CONNECT BOKEH EVENT LISTENERS ---
            if (models.audio_status_source) {
                models.audio_status_source.patching.connect(app.eventHandlers.handleAudioStatusUpdate);
            }

            // Listen for server-pushed data updates to log sources (reservoir streaming)
            Object.keys(models.timeSeriesSources || {}).forEach(positionId => {
                const logSource = models.timeSeriesSources[positionId]?.log;
                if (logSource && logSource.change) {
                    logSource.change.connect(() => {
                        app.store.dispatch(app.actions.dataRefreshed(positionId));
                    });
                }
            });

            // Same for spectrogram sources
            if (models.spectrogramSources) {
                Object.keys(models.spectrogramSources).forEach(positionId => {
                    const logSource = models.spectrogramSources[positionId]?.log;
                    if (logSource && logSource.change) {
                        logSource.change.connect(() => {
                            app.store.dispatch(app.actions.dataRefreshed(positionId));
                        });
                    }
                });
            }

            // --- 3. SETUP KEYBOARD & OTHER GLOBAL EVENT LISTENERS ---
            document.addEventListener('keydown', app.eventHandlers.handleKeyPress);
            document.addEventListener('keydown', handleDragToolKeyDown);
            document.addEventListener('keyup', handleDragToolKeyUp);
            app.store.dispatch(app.actions.keyboardSetupComplete());

            // --- 4. SUBSCRIBE TO STORE CHANGES ---
            previousState = app.store.getState();
            app.store.subscribe(onStateChange);

            // --- 5. KICK OFF THE FIRST RENDER ---
            let didInitialRender = false;
            const kickoffInitialRender = () => {
                if (didInitialRender) {
                    return;
                }
                didInitialRender = true;
                onStateChange(true);
            };
            kickoffInitialRender();
            if (typeof requestAnimationFrame === 'function') {
                requestAnimationFrame(kickoffInitialRender);
            } else {
                setTimeout(kickoffInitialRender, 0);
            }

            if (app.session && typeof app.session.applyInitialWorkspaceState === 'function') {
                try {
                    app.session.applyInitialWorkspaceState();
                } catch (error) {
                    console.error('[App]', 'Failed to apply initial workspace state:', error);
                }
            }

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
        let state = app.store.getState();
        const { models, controllers } = app.registry;
        const actionTypes = app.actionTypes || {};
        const previousStateForAudio = previousState;
        const lastActionType = state.system?.lastAction?.type;
    
        // --- A. DETERMINE UPDATE TYPE (HEAVY vs. LIGHT) ---
        const didViewportChange = state.view.viewport !== previousState.view.viewport;
        const didParamChange = state.view.selectedParameter !== previousState.view.selectedParameter;
        const didViewToggleChange = state.view.globalViewType !== previousState.view.globalViewType;
        const didVisibilityChange = state.view.chartVisibility !== previousState.view.chartVisibility;
        const didChartOffsetsChange = state.view.positionChartOffsets !== previousState.view.positionChartOffsets;
        const didMarkersChange = state.markers !== previousState.markers;
        const didRegionsChange = state.regions !== previousState.regions;
        const didActiveDragToolChange = state.interaction.activeDragTool !== previousState.interaction.activeDragTool;
        const didActiveSidePanelTabChange = state.view.activeSidePanelTab !== previousState.view.activeSidePanelTab;
        const didDisplayTitlesChange = state.view.positionDisplayTitles !== previousState.view.positionDisplayTitles;
        const didPendingRegionChange = state.interaction.pendingRegionStart !== previousState.interaction.pendingRegionStart;
        const didTapChange = state.interaction.tap !== previousState.interaction.tap;
        const didAudioPositionChange = state.audio.activePositionId !== previousState.audio.activePositionId;
        const didDataRefresh = lastActionType === actionTypes.DATA_REFRESHED;

        const isHeavyUpdateRequested = isInitialLoad
            || didViewportChange
            || didParamChange
            || didViewToggleChange
            || didVisibilityChange
            || didChartOffsetsChange
            || didDisplayTitlesChange
            || didDataRefresh;

        // Throttle heavy updates during audio playback to prevent UI lag
        const now = performance.now();
        const isAudioPlaying = state.audio?.isPlaying;
        const timeSinceLastHeavy = now - _lastHeavyUpdateTime;
        const shouldThrottle = isAudioPlaying && timeSinceLastHeavy < HEAVY_UPDATE_THROTTLE_MS;
        
        // Allow heavy update if: not throttled, or it's a critical update (param/view toggle change)
        const isCriticalUpdate = isInitialLoad || didParamChange || didViewToggleChange;
        const isHeavyUpdate = isHeavyUpdateRequested && (!shouldThrottle || isCriticalUpdate);
        
        // If we're throttling a viewport change during audio, schedule it for later
        if (isHeavyUpdateRequested && shouldThrottle && !isCriticalUpdate && didViewportChange) {
            if (_pendingHeavyUpdate === null) {
                _pendingHeavyUpdate = requestAnimationFrame(() => {
                    _pendingHeavyUpdate = null;
                    // Re-trigger state change processing
                    onStateChange(false);
                });
            }
        }
        
        // --- B. ORCHESTRATE DATA PROCESSING & RENDERING ---
        let displayDetailsUpdates = null;

        if (isHeavyUpdate) {
            _lastHeavyUpdateTime = now;
            // 1. Process heavy data (time series, spectrograms)
            if (app.data_processors?.updateActiveData) {
                displayDetailsUpdates = app.data_processors.updateActiveData(state.view, dataCache, app.registry.models) || {};
            }
        }

        if (displayDetailsUpdates) {
            Object.keys(displayDetailsUpdates).forEach(positionId => {
                const lineType = displayDetailsUpdates?.[positionId]?.line?.type;
                if (typeof lineType === 'string') {
                    lineDisplayTypeByPosition[positionId] = lineType;
                }
            });
        }

        const shouldUpdateStep = !isInitialLoad
            ? (isHeavyUpdate || didTapChange || didAudioPositionChange)
            : true;

        if (shouldUpdateStep && lastActionType !== actionTypes.STEP_SIZE_CALCULATED) {
            const focusedPositionId = state.interaction.tap.position || state.audio.activePositionId;
            if (focusedPositionId) {
                const lineType = displayDetailsUpdates?.[focusedPositionId]?.line?.type
                    || lineDisplayTypeByPosition[focusedPositionId];

                const newStepSize = lineType === 'log' && Number.isFinite(logStepSizeByPosition[focusedPositionId])
                    ? logStepSizeByPosition[focusedPositionId]
                    : (app.data_processors?.calculateStepSize
                        ? app.data_processors.calculateStepSize(state, dataCache)
                        : undefined);

                if (Number.isFinite(newStepSize) && newStepSize !== state.interaction.keyboard.stepSizeMs) {
                    app.store.dispatch(app.actions.stepSizeCalculated(newStepSize));
                }
            } else if (isInitialLoad && app.data_processors?.calculateStepSize) {
                const newStepSize = app.data_processors.calculateStepSize(state, dataCache);
                if (Number.isFinite(newStepSize) && newStepSize !== state.interaction.keyboard.stepSizeMs) {
                    app.store.dispatch(app.actions.stepSizeCalculated(newStepSize));
                }
            }
        }

        if (isHeavyUpdate) {
            // 3. Render the main charts with the new data
            app.renderers.renderPrimaryCharts(state, dataCache, displayDetailsUpdates);
        }

        // Always update the frequency bar, as it depends on hover/tap (light changes)
        app.data_processors.updateActiveFreqBarData(state, dataCache);
        app.renderers.renderFrequencyBar(state, dataCache);

        // Always update overlays (tap lines, hover lines, labels)
        app.renderers.renderOverlays(state, dataCache);

        // Always keep UI widgets in sync with the state
        app.renderers.renderControlWidgets(state, displayDetailsUpdates);

        // render the side panel
        if (didMarkersChange || didRegionsChange || didActiveSidePanelTabChange || didPendingRegionChange) {
            const currentPanelState = {
                lastActionType: state.system.lastAction?.type,
                markers: state.markers,
                regions: state.regions,
                activeSidePanelTab: state.view.activeSidePanelTab,
                desiredIndex: state.view.desiredIndex,
                didMarkersChange: didMarkersChange,
                didRegionsChange: didRegionsChange,
                didActiveSidePanelTabChange: didActiveSidePanelTabChange
            };

            app.renderers.renderSidePanel(state);
        }

        // Always sync markers
        
        if (isInitialLoad || didMarkersChange) {
            app.renderers.renderMarkers(state);
        }

        if (isInitialLoad || didRegionsChange || didPendingRegionChange) {
            app.renderers.renderRegions(state, dataCache);
        }


        if (app.renderers && typeof app.renderers.renderComparisonMode === 'function') {
            app.renderers.renderComparisonMode(state);
        }

        if ((isInitialLoad || didActiveDragToolChange) && typeof app.renderers.renderActiveTool === 'function') {
            app.renderers.renderActiveTool(state, models);
        }

        // --- C. HANDLE SIDE EFFECTS ---
        // These are tasks that interact with the outside world (e.g., Bokeh backend)
        handleAudioSideEffects(state, previousStateForAudio, models);

        // --- D. CLEANUP ---
        // Update previousState for the next cycle
        previousState = state;
    }

    /**
     * Manages sending all commands to the audio backend based on state changes.
     * This function is the single point of contact with the audio_control_source.
     */
    function handleAudioSideEffects(current, previous, models) {
        if (!models.audio_control_source) {
            return; // Do nothing if the audio control model isn't present
        }

        const { actionTypes } = app;
        const lastAction = current.system.lastAction;
        if (!lastAction) return;
    
        // --- A. Handle User-Initiated Playback (Tap, KeyNav, or Play Button) ---
        const audioWasPlayingPreviously = Boolean(previous?.audio?.isPlaying);
        const wasTapPlayback = lastAction.type === actionTypes.TAP && audioWasPlayingPreviously;
        const wasKeyNavPlayback = lastAction.type === actionTypes.KEY_NAV && audioWasPlayingPreviously;
        const wasPlayToggleRequest = lastAction.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE && lastAction.payload.isActive;
        const shouldSendPlayCommand = wasTapPlayback || wasKeyNavPlayback || wasPlayToggleRequest;

        if (shouldSendPlayCommand) {
            // A tap, key nav, or "play" button press is an explicit intent to hear audio.
            // We always send a 'play' command.
            const tapState = current?.interaction?.tap || {};
            const position = wasPlayToggleRequest
                ? lastAction.payload.positionId
                : tapState.position || current.audio.activePositionId || previous?.audio?.activePositionId;

            let timestamp = Number(tapState.timestamp);
            if (!Number.isFinite(timestamp)) {
                timestamp = Number(previous?.interaction?.tap?.timestamp);
            }

            if (!position || !Number.isFinite(timestamp)) {
                console.warn('[Side Effect] Skipping play command due to missing context.', { position, timestamp });
                return;
            }

            const offsetMs = Number(current?.view?.positionEffectiveOffsets?.[position]) || 0;
            const actualTimestamp = Math.round(timestamp - offsetMs);
            if (!Number.isFinite(actualTimestamp)) {
                console.warn('[Side Effect] Skipping play command due to invalid adjusted timestamp.', {
                    position,
                    timestamp,
                    offsetMs
                });
                return;
            }

            console.log(`[Side Effect] Sending 'play' command for ${position} @ ${new Date(timestamp).toLocaleTimeString()} (actual ${new Date(actualTimestamp).toLocaleTimeString()})`);
            models.audio_control_source.data = {
                command: ['play'],
                position_id: [position],
                value: [actualTimestamp]
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
    }

    function normalizeTitleUpdates(titles) {
        if (!titles || typeof titles !== 'object') {
            return {};
        }
        const normalized = {};
        Object.keys(titles).forEach(key => {
            if (typeof titles[key] === 'string') {
                normalized[key] = titles[key];
            }
        });
        return normalized;
    }

    function setPositionDisplayTitles(titlesById) {
        const normalized = normalizeTitleUpdates(titlesById);
        if (!Object.keys(normalized).length) {
            return false;
        }
        if (!app.store || !app.actions?.positionDisplayTitlesSet) {
            console.error('[App] Cannot set display titles because store or action is unavailable.');
            return false;
        }
        app.store.dispatch(app.actions.positionDisplayTitlesSet(normalized));
        return true;
    }

    function setPositionDisplayTitle(positionId, title) {
        if (typeof positionId !== 'string') {
            console.error('[App] positionId must be a string when setting a display title.');
            return false;
        }
        return setPositionDisplayTitles({ [positionId]: title });
    }


    // Expose side-effect handlers for orchestrator in init.js
    app.handleAudioSideEffects = handleAudioSideEffects;
    app.setPositionDisplayTitles = setPositionDisplayTitles;
    app.setPositionDisplayTitle = setPositionDisplayTitle;


    // Attach the public initialization function (legacy path)
    if (app.init) {
        app.init.initialize = initialize;
    } else {
        // Fallback in case init.js didn't load, though it should have.
        app.init = { initialize: initialize };
    }

})(window.NoiseSurveyApp);
