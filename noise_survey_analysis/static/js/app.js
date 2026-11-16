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
    // A heavy update that was throttled away is replayed on the next frame. The
    // deferred pass compares the state against itself (previousState has already
    // advanced), so it cannot rediscover what changed - this flag carries that
    // intent across, otherwise the throttled update is simply lost and the charts
    // keep showing the pre-pan slice until something else forces a redraw.
    let _deferredHeavyUpdate = false;
    const HEAVY_UPDATE_THROTTLE_MS = 50; // Minimum ms between heavy updates during audio playback

    // The mutable, non-serializable data cache for large data arrays.
    const dataCache = {
        activeLineData: {},
        activeSpectralData: {},
        activeFreqBarData: {},
        _spectrogramCanvasBuffers: {}
    };

    // Server-pushed reservoir updates arrive one Bokeh source at a time, so a single
    // pan lands up to two changes per position (time series + spectrogram). Each one
    // used to force its own heavy update, and a heavy update reprocesses every
    // position, so the work scaled with sources rather than with pans. Coalesce them
    // into one dispatch per frame.
    let _pendingDataRefreshHandle = null;
    const _pendingDataRefreshPositions = new Set();

    function flushPendingDataRefresh() {
        _pendingDataRefreshHandle = null;
        if (!_pendingDataRefreshPositions.size) {
            return;
        }
        const positionIds = Array.from(_pendingDataRefreshPositions);
        _pendingDataRefreshPositions.clear();
        // The payload is advisory: a heavy update rebuilds every visible position.
        app.store.dispatch(app.actions.dataRefreshed(positionIds[0]));
    }

    function scheduleDataRefresh(positionId) {
        _pendingDataRefreshPositions.add(positionId);
        if (_pendingDataRefreshHandle !== null) {
            return;
        }
        _pendingDataRefreshHandle = typeof requestAnimationFrame === 'function'
            ? requestAnimationFrame(flushPendingDataRefresh)
            : setTimeout(flushPendingDataRefresh, 0);
    }

    const logStepSizeByPosition = {};
    const lineDisplayTypeByPosition = {};
    let lastAppliedControlStateUpdateAt = null;
    let lastDisplayDetailsByPosition = {};
    let disposeHtmlPanelEvents = null;

    function disposeAnnotationPanel() {
        disposeHtmlPanelEvents?.();
        disposeHtmlPanelEvents = null;
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

    function syncControlModelsToStore(models) {
        if (models?.paramSelect?.change && typeof models.paramSelect.change.connect === 'function') {
            models.paramSelect.change.connect(() => {
                try {
                    const nextValue = models.paramSelect?.value;
                    const currentValue = app.store?.getState?.()?.view?.selectedParameter;
                    if (typeof nextValue === 'string' && nextValue && nextValue !== currentValue) {
                        app.eventHandlers.handleParameterChange(nextValue);
                    }
                } catch (error) {
                    console.error('[App]', 'Control model sync failed:', error);
                }
            });
        }

        if (models?.viewToggle?.change && typeof models.viewToggle.change.connect === 'function') {
            models.viewToggle.change.connect(() => {
                try {
                    const nextIsLog = Boolean(models.viewToggle?.active);
                    const currentViewType = app.store?.getState?.()?.view?.globalViewType;
                    const nextViewType = nextIsLog ? 'log' : 'overview';
                    if (nextViewType !== currentViewType) {
                        app.eventHandlers.handleViewToggle(nextIsLog);
                    }
                } catch (error) {
                    console.error('[App]', 'Control model sync failed:', error);
                }
            });
        }
    }

    function attachControlStateSource(models) {
        const source = models?.controlStateSource;
        if (!source?.change || typeof source.change.connect !== 'function') {
            return;
        }

        source.change.connect(() => {
            const sourceData = source.data || {};
            const updatedAt = Number(sourceData.updated_at?.[0]);
            if (Number.isFinite(updatedAt) && updatedAt === lastAppliedControlStateUpdateAt) {
                return;
            }
            if (Number.isFinite(updatedAt)) {
                lastAppliedControlStateUpdateAt = updatedAt;
            }

            const desiredParameter = typeof sourceData.parameter?.[0] === 'string'
                ? sourceData.parameter[0]
                : null;
            const desiredViewMode = typeof sourceData.view_mode?.[0] === 'string'
                ? sourceData.view_mode[0]
                : null;
            const currentState = app.store?.getState?.();
            const currentParameter = currentState?.view?.selectedParameter;
            const currentViewType = currentState?.view?.globalViewType;

            if (desiredParameter && desiredParameter !== currentParameter) {
                app.eventHandlers.handleParameterChange(desiredParameter);
            }
            if ((desiredViewMode === 'log' || desiredViewMode === 'overview') && desiredViewMode !== currentViewType) {
                app.eventHandlers.handleViewToggle(desiredViewMode === 'log');
            }

            if (desiredParameter && models?.paramSelect?.value !== desiredParameter) {
                models.paramSelect.value = desiredParameter;
            }

            if ((desiredViewMode === 'log' || desiredViewMode === 'overview') && models?.viewToggle) {
                const desiredActive = desiredViewMode === 'log';
                if (Boolean(models.viewToggle.active) !== desiredActive) {
                    models.viewToggle.active = desiredActive;
                }
            }
        });
    }

    /**
     * The main application entry point, called from the Bokeh template.
     * @param {object} bokehModels - The collection of models passed from Bokeh.
     */
    function initialize(bokehModels) {
        try {
            console.info('[App]', 'Initializing...');
            disposeAnnotationPanel();

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
                const stepCalculator = app.features?.view?.resolution?.computeMedianPositiveStepMs;
                const step = typeof stepCalculator === 'function'
                    ? stepCalculator(datetime, 2000)
                    : undefined;
                if (Number.isFinite(step)) {
                    logStepSizeByPosition[pos] = Math.min(step, 3600000);
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
            attachControlStateSource(models);
            syncControlModelsToStore(models);
            disposeHtmlPanelEvents = app.services?.htmlPanelEvents?.attach(models) || null;
            window.removeEventListener?.('pagehide', disposeAnnotationPanel);
            window.addEventListener?.('pagehide', disposeAnnotationPanel);

            // Listen for server-pushed data updates to log sources (reservoir streaming)
            Object.keys(models.timeSeriesSources || {}).forEach(positionId => {
                const logSource = models.timeSeriesSources[positionId]?.log;
                if (logSource && logSource.change) {
                    logSource.change.connect(() => {
                        scheduleDataRefresh(positionId);
                    });
                }
            });

            // Same for spectrogram sources
            if (models.spectrogramSources) {
                Object.keys(models.spectrogramSources).forEach(positionId => {
                    const logSource = models.spectrogramSources[positionId]?.log;
                    if (logSource && logSource.change) {
                        logSource.change.connect(() => {
                            scheduleDataRefresh(positionId);
                        });
                    }
                });
            }

            // --- 3. SETUP KEYBOARD & OTHER GLOBAL EVENT LISTENERS ---
            document.addEventListener('keydown', app.eventHandlers.handleKeyPress);
            if (typeof app.eventHandlers.handleRegionListDoubleClick === 'function') {
                document.addEventListener('dblclick', app.eventHandlers.handleRegionListDoubleClick);
            }
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
            try {
                kickoffInitialRender();
            } catch (paintError) {
                // Bokeh 3.4.1 may throw _paint_levels errors during first render
                // when image renderers haven't fully initialized. This is non-fatal;
                // subsequent renders will succeed once views are ready.
                console.warn('[App]', 'Non-fatal paint error during initial render:', paintError.message);
            }
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
            if (app.session && typeof app.session.ensureAutomationBridge === 'function') {
                try {
                    app.session.ensureAutomationBridge();
                } catch (error) {
                    console.error('[App]', 'Failed to attach automation bridge:', error);
                }
            }

            console.info('[App]', 'App initialized successfully.');

            return true;
        }
        catch (error) {
            disposeAnnotationPanel();
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
    // Starts at -Infinity so the first error is always reported: seeding it with 0
    // swallowed everything thrown in the first 5s after page load, which is exactly
    // the initial-render window worth seeing.
    // Extra renderers registered by other modules (see registerRenderHook below).
    const renderHooks = [];

    /**
     * Registers a renderer that runs at the end of every onStateChange, after the built-in
     * renderers, inside the same error guard. Registering an existing name replaces it.
     * `fn(state, info)`; info = { prev, isInitialLoad, isHeavyUpdate, dataCache, models, controllers,
     * displayDetailsUpdates, ...renderContext }. Compare `state.x !== info.prev.x` to render only on change.
     * A file that calls this must load after app.js (add it at the end of js/manifest.py).
     */
    function registerRenderHook(name, fn) {
        if (typeof name !== 'string' || !name || typeof fn !== 'function') {
            throw new Error('registerRenderHook requires a name and a function.');
        }
        const existing = renderHooks.findIndex(hook => hook.name === name);
        if (existing >= 0) {
            renderHooks[existing] = { name, fn };
        } else {
            renderHooks.push({ name, fn });
        }
    }

    let _renderErrorCooldown = -Infinity;
    const RENDER_ERROR_COOLDOWN_MS = 5000;

    function _guardedRender(label, fn, context) {
        try {
            return fn();
        } catch (error) {
            const now = performance.now();
            if (now - _renderErrorCooldown > RENDER_ERROR_COOLDOWN_MS) {
                _renderErrorCooldown = now;
                console.error(`[RenderError] ${label}:`, error, context);
            }
        }
    }

    function onStateChange(isInitialLoad = false) {
        let state = app.store.getState();
        const { models, controllers } = app.registry;
        const actionTypes = app.actionTypes || {};
        const previousStateForAudio = previousState;
        const lastActionType = state.system?.lastAction?.type;

        // Capture prev and advance previousState immediately, BEFORE rendering.
        // This prevents nested dispatches (e.g. Bokeh selection callbacks triggered
        // during data-source updates) from having their previousState overwritten
        // when the outer onStateChange finishes.
        const prev = previousState;
        previousState = state;

        // --- A. DETERMINE UPDATE TYPE (HEAVY vs. LIGHT) ---
        const didViewportChange = state.view.viewport !== prev.view.viewport;
        const didRegionJumpHistoryChange = state.view.regionJumpHistory !== prev.view.regionJumpHistory;
        const didRegionNoteFocusRequest = state.view.regionNoteFocusRequestId !== prev.view.regionNoteFocusRequestId;
        const didRegionNoteStatusChange = state.view.regionNoteStatus !== prev.view.regionNoteStatus;
        const didNoticeChange = state.view.notice !== prev.view.notice;
        const didParamChange = state.view.selectedParameter !== prev.view.selectedParameter;
        const didViewToggleChange = state.view.globalViewType !== prev.view.globalViewType;
        const didVisibilityChange = state.view.chartVisibility !== prev.view.chartVisibility;
        const didChartOffsetsChange = state.view.positionChartOffsets !== prev.view.positionChartOffsets;
        if (didChartOffsetsChange && app.regions?.invalidateMetricsCache) {
            app.regions.invalidateMetricsCache();
        }
        const didMarkersChange = state.markers !== prev.markers;
        const didRegionsChange = state.regions !== prev.regions;
        const didActiveDragToolChange = state.interaction.activeDragTool !== prev.interaction.activeDragTool;
        const didActiveSidePanelTabChange = state.view.activeSidePanelTab !== prev.view.activeSidePanelTab;
        const didDisplayTitlesChange = state.view.positionDisplayTitles !== prev.view.positionDisplayTitles;
        const didThresholdChange = state.view.logViewThreshold !== prev.view.logViewThreshold;
        const didPendingRegionChange = state.interaction.pendingRegionStart !== prev.interaction.pendingRegionStart;
        const didTapChange = state.interaction.tap !== prev.interaction.tap;
        const didHoverChange = state.interaction.hover !== prev.interaction.hover;
        const didAudioPositionChange = state.audio.activePositionId !== prev.audio.activePositionId;
        const didDataRefresh = lastActionType === actionTypes.DATA_REFRESHED;
        const didClassificationsChange = state.classifications !== prev.classifications;
        const didAnnotationPanelChange = state.annotationPanel !== prev.annotationPanel;
        const didComparisonChange = state.view.mode !== prev.view.mode
            || state.view.comparison !== prev.view.comparison;
        if (didDataRefresh && app.regions?.invalidatePositionMetrics) {
            app.regions.invalidatePositionMetrics(state.system?.lastAction?.payload?.positionId, state);
        }
        // Undo/redo rewrites region geometry without going through the region thunks,
        // which are what normally drop cached metrics, so the panel would otherwise
        // keep showing the metrics of the bounds that were just undone.
        const isHistoryAction = lastActionType === actionTypes.HISTORY_UNDO
            || lastActionType === actionTypes.HISTORY_REDO;
        if (isHistoryAction && didRegionsChange && app.regions?.invalidateMetricsCache) {
            app.regions.invalidateMetricsCache();
        }

        const wasHeavyUpdateDeferred = _deferredHeavyUpdate;
        _deferredHeavyUpdate = false;

        const isHeavyUpdateRequested = isInitialLoad
            || wasHeavyUpdateDeferred
            || didViewportChange
            || didParamChange
            || didViewToggleChange
            || didVisibilityChange
            || didChartOffsetsChange
            || didDisplayTitlesChange
            || didThresholdChange
            || didDataRefresh;

        // Throttle heavy updates during audio playback to prevent UI lag
        const now = performance.now();
        const isAudioPlaying = state.audio?.isPlaying;
        const timeSinceLastHeavy = now - _lastHeavyUpdateTime;
        const shouldThrottle = isAudioPlaying && timeSinceLastHeavy < HEAVY_UPDATE_THROTTLE_MS;
        
        // Allow heavy update if: not throttled, or it's a critical update (param/view toggle change)
        const isCriticalUpdate = isInitialLoad || didParamChange || didViewToggleChange;
        const isHeavyUpdate = isHeavyUpdateRequested && (!shouldThrottle || isCriticalUpdate);
        
        // If we're throttling a heavy update during audio, schedule it for later
        if (isHeavyUpdateRequested && !isHeavyUpdate) {
            _deferredHeavyUpdate = true;
            if (_pendingHeavyUpdate === null && typeof requestAnimationFrame === 'function') {
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
            lastDisplayDetailsByPosition = displayDetailsUpdates;
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

        const renderContext = {
            lastActionType,
            isHeavyUpdate,
            didParamChange,
            didViewportChange,
            didChartOffsetsChange
        };

        if (didViewportChange && typeof app.renderers?.renderViewport === 'function') {
            _guardedRender('renderViewport', () => {
                app.renderers.renderViewport(state);
            }, renderContext);
        }

        if (isHeavyUpdate) {
            // 3. Render the main charts with the new data
            _guardedRender('renderPrimaryCharts', () => {
                app.renderers.renderPrimaryCharts(state, dataCache, displayDetailsUpdates);
            }, renderContext);
        }

        // Frequency bar only needs updating when hover, tap, parameter, viewport, or audio changes
        const shouldUpdateFreqBar = isHeavyUpdate || didTapChange || didHoverChange || didParamChange || didAudioPositionChange;
        if (shouldUpdateFreqBar) {
            _guardedRender('updateActiveFreqBarData', () => {
                app.data_processors.updateActiveFreqBarData(state, dataCache);
            }, renderContext);
            _guardedRender('renderFrequencyBar', () => {
                app.renderers.renderFrequencyBar(state, dataCache);
            }, renderContext);
        }

        // Always update overlays (tap lines, hover lines, labels)
        _guardedRender('renderOverlays', () => {
            app.renderers.renderOverlays(state, dataCache);
        }, renderContext);

        // Control widgets only need updating when audio, display details, titles, offsets, visibility, parameter, or view toggle changes
        const didAudioChange = state.audio !== prev.audio;
        const shouldUpdateWidgets = isHeavyUpdate || didAudioChange || didDisplayTitlesChange
            || didChartOffsetsChange || didVisibilityChange || didParamChange || didViewToggleChange;
        if (shouldUpdateWidgets) {
            _guardedRender('renderControlWidgets', () => {
                app.renderers.renderControlWidgets(state, displayDetailsUpdates || lastDisplayDetailsByPosition);
            }, renderContext);
        }

        // render the side panel
        if (state.view.sidebarCollapsed !== prev.view?.sidebarCollapsed
            || isInitialLoad || didMarkersChange || didRegionsChange || didClassificationsChange
            || didActiveSidePanelTabChange || didPendingRegionChange || didDataRefresh
            || didAnnotationPanelChange || didComparisonChange
            || (models?.htmlSidePanel && (isHeavyUpdate || didDisplayTitlesChange || didRegionNoteStatusChange))) {
            _guardedRender('renderSidePanel', () => {
                app.renderers.renderSidePanel(state);
            }, renderContext);
        }

        // Always sync markers
        if (isInitialLoad || didMarkersChange) {
            _guardedRender('renderMarkers', () => {
                app.renderers.renderMarkers(state);
            }, renderContext);
        }

        if (isInitialLoad || didRegionsChange || didPendingRegionChange || didRegionJumpHistoryChange
            || didRegionNoteStatusChange) {
            _guardedRender('renderRegions', () => {
                app.renderers.renderRegions(state, dataCache);
            }, renderContext);
        }

        if (isInitialLoad || didClassificationsChange || didChartOffsetsChange) {
            _guardedRender('renderClassifications', () => {
                app.renderers.renderClassifications(state);
            }, renderContext);
        }

        if (app.renderers && typeof app.renderers.renderComparisonMode === 'function') {
            _guardedRender('renderComparisonMode', () => {
                app.renderers.renderComparisonMode(state);
            }, renderContext);
        }

        if ((isInitialLoad || didActiveDragToolChange) && typeof app.renderers.renderActiveTool === 'function') {
            _guardedRender('renderActiveTool', () => {
                app.renderers.renderActiveTool(state, models);
            }, renderContext);
        }

        if (didNoticeChange && state.view.notice && typeof app.renderers?.renderNotice === 'function') {
            _guardedRender('renderNotice', () => {
                app.renderers.renderNotice(state);
            }, renderContext);
        }

        if (didRegionNoteFocusRequest && typeof app.renderers?.focusRegionNoteInput === 'function') {
            _guardedRender('focusRegionNoteInput', () => {
                app.renderers.focusRegionNoteInput();
            }, renderContext);
        }

        renderHooks.forEach(hook => {
            _guardedRender(`renderHook:${hook.name}`, () => {
                hook.fn(state, {
                    ...renderContext,
                    prev,
                    isInitialLoad,
                    dataCache,
                    models,
                    controllers,
                    displayDetailsUpdates
                });
            }, renderContext);
        });

        // --- C. HANDLE SIDE EFFECTS ---
        // These are tasks that interact with the outside world (e.g., Bokeh backend)
        handleAudioSideEffects(state, previousStateForAudio, models);
    }

    /**
     * Manages sending all commands to the audio backend based on state changes.
     * This function is the single point of contact with the audio_control_source.
     */
    function handleAudioSideEffects(current, previous, models) {
        // The store change -> command mapping lives in services/audio/audioCommands.js so the
        // VLC backend (server, via audio_control_source) and the browser backend (clipPlayer)
        // receive exactly the same command and the same offset-adjusted audio time.
        const clipPlayer = app.services?.audio?.clipPlayer;
        const useBrowserPlayer = Boolean(clipPlayer && clipPlayer.isBrowserBackend());

        if (!useBrowserPlayer && !models.audio_control_source) {
            return; // Do nothing if the audio control model isn't present
        }
        if (!current?.system?.lastAction) return;

        const command = app.services?.audio?.deriveAudioCommand?.(current, previous);
        if (!command) return;

        if (useBrowserPlayer) {
            clipPlayer.execute(command, current);
            return;
        }
        models.audio_control_source.data = {
            command: [command.command],
            position_id: [command.position_id],
            value: [command.value]
        };
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
    app.disposeAnnotationPanel = disposeAnnotationPanel;
    app.registerRenderHook = registerRenderHook;


    // Attach the public initialization function (legacy path)
    if (app.init) {
        app.init.initialize = initialize;
    } else {
        // Fallback in case init.js didn't load, though it should have.
        app.init = { initialize: initialize };
    }

})(window.NoiseSurveyApp);
