// noise_survey_analysis/static/js/event-handlers.js

/**
 * @fileoverview Contains all event handler functions for the Noise Survey application.
 * These functions are directly connected to Bokeh widget and plot events (e.g., tap, hover,
 * range updates). Their primary role is to interpret the raw event data from Bokeh
 * and translate it into a structured action object that can be dispatched to the
 * state management module. They should contain no application logic.
 */


window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    // --- Dependencies ---
    const { actions } = app;

    const DEBOUNCE_DELAY = 200; // ms

    // --- Helper Functions ---
    const _getChartPositionByName = (chartName) => {
        if (!chartName) return null;
        const parts = chartName.split('_');
        return parts.length >= 2 ? parts[1] : null;
    };

    /**
     * Debounces a function call, ensuring it's only executed after a certain delay.
     * @param {function} func - The function to debounce.
     * @param {number} delay - The delay in milliseconds.
     * @returns {function} The debounced function.
     */
    function debounce(func, delay) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), delay);
        };
    }

    // --- Event Handlers ---

    function handleTap(cb_obj) {
        const chartName = cb_obj?.origin?.name;
        if (!chartName || chartName === 'frequency_bar') return;
        const positionId = _getChartPositionByName(chartName);
        if (!positionId) return;
        const timestamp = cb_obj?.x;
        if (!Number.isFinite(timestamp)) return;

        const thunkCreator = app.thunks && app.thunks.handleTapIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing handleTapIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        dispatch(thunkCreator({
            timestamp,
            positionId,
            chartName,
            modifiers: {
                ctrl: Boolean(cb_obj?.modifiers?.ctrl)
            }
        }));
    }

    function handleRegionBoxSelect(cb_obj) {
        const modelName = cb_obj?.model?.name;
        if (!modelName || modelName === 'frequency_bar') return;

        const geometry = cb_obj?.geometry;
        if (!geometry || geometry.type !== 'rect') return;

        const x0 = geometry.x0;
        const x1 = geometry.x1;
        if (!Number.isFinite(x0) || !Number.isFinite(x1)) return;

        const positionId = _getChartPositionByName(modelName);
        if (!positionId) return;

        const dispatch = app.store && app.store.dispatch;
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        const comparisonThunk = app.thunks && app.thunks.updateComparisonSliceIntent;
        if (typeof comparisonThunk === 'function') {
            dispatch(comparisonThunk({
                start: x0,
                end: x1,
                positionId,
                sourceChartName: modelName,
                final: Boolean(cb_obj?.final)
            }));
        }

        if (!cb_obj?.final || !cb_obj?.modifiers?.shift) {
            return;
        }

        const thunkCreator = app.thunks && app.thunks.createRegionIntent;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing createRegionIntent thunk.');
            return;
        }

        dispatch(thunkCreator({
            positionId,
            start: x0,
            end: x1
        }));
    }

    function handleChartHover(cb_data, chartName) {
        const geometry = cb_data.geometry;
        const isActive = geometry && Number.isFinite(geometry.x);
        if (isActive) {
            app.store.dispatch(actions.hover({
                isActive: true,
                sourceChartName: chartName,
                timestamp: geometry.x,
                spec_y: geometry.y,
                position: _getChartPositionByName(chartName),
            }));
        } else {
            app.store.dispatch(actions.hover({
                isActive: false,
            }));
        }
    }

    const debouncedRangeUpdate = debounce((min, max) => {
        app.store.dispatch(actions.viewportChange(min, max));
    }, DEBOUNCE_DELAY);

    function handleRangeUpdate(cb_obj) {
        debouncedRangeUpdate(cb_obj.start, cb_obj.end);
    }

    function handleDoubleClick(cb_obj) {
        if (cb_obj.origin.name === 'frequency_bar') return;
        app.store.dispatch(actions.addMarker(cb_obj.x));
    }

    function clearAllMarkers() {
        app.store.dispatch(actions.clearAllMarkers());
    }

    function handleParameterChange(value) {
        app.store.dispatch(actions.paramChange(value));
    }

    function handleViewToggle(isActive, toggleWidget) {
        const newViewType = isActive ? 'log' : 'overview';
        app.store.dispatch(actions.viewToggle(newViewType));
        if (toggleWidget) { //TODO: move this to a renderer
            toggleWidget.label = isActive ? "Log View Enabled" : "Log View Disabled";
        }
    }

    function handleHoverToggle(isActive, toggleWidget) {
        app.store.dispatch(actions.hoverToggle(isActive));
        if (toggleWidget) { //TODO: move this to a renderer
            toggleWidget.label = isActive ? "Hover Enabled" : "Hover Disabled";
        }
    }

    function handleVisibilityChange(cb_obj, chartName) {
        const isVisible = Array.isArray(cb_obj.active) ? cb_obj.active.includes(0) : Boolean(cb_obj.active);
        app.store.dispatch(actions.visibilityChange(chartName, isVisible));
    }

    function handleAudioStatusUpdate() {
        const status = app.registry.models.audio_status_source.data;
        app.store.dispatch(actions.audioStatusUpdate(status));
    }

    function togglePlayPause(payload) {
        const thunkCreator = app.thunks && app.thunks.togglePlayPauseIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing togglePlayPauseIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        dispatch(thunkCreator({
            positionId: payload?.positionId,
            isActive: payload?.isActive
        }));
    }

    function handlePlaybackRateChange(payload) {
        const thunkCreator = app.thunks && app.thunks.changePlaybackRateIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing changePlaybackRateIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        dispatch(thunkCreator({
            positionId: payload?.positionId,
            playbackRate: payload?.playbackRate
        }));
    }

    function handleVolumeBoostToggle(payload) {
        const thunkCreator = app.thunks && app.thunks.toggleVolumeBoostIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing toggleVolumeBoostIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        dispatch(thunkCreator({
            positionId: payload?.positionId,
            isBoostActive: payload?.isBoostActive
        }));
    }

    function handleStartComparison() {
        const thunkCreator = app.thunks && app.thunks.enterComparisonModeIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing enterComparisonModeIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }
        dispatch(thunkCreator());
    }

    function handleFinishComparison() {
        const thunkCreator = app.thunks && app.thunks.exitComparisonModeIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing exitComparisonModeIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }
        dispatch(thunkCreator());
    }

    function handleComparisonPositionsChange(positionIds) {
        const thunkCreator = app.thunks && app.thunks.updateIncludedPositionsIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing updateIncludedPositionsIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }
        const payload = Array.isArray(positionIds) ? positionIds : [];
        dispatch(thunkCreator({ includedPositions: payload }));
    }

    function handleComparisonMakeRegions() {
        const thunkCreator = app.thunks && app.thunks.createRegionsFromComparisonIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing createRegionsFromComparisonIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }
        dispatch(thunkCreator());
    }

    function handleKeyPress(e) {
        const targetTagName = e.target.tagName.toLowerCase();
        if (targetTagName === 'input' || targetTagName === 'textarea' || targetTagName === 'select') return;

        if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') {
            return;
        }

        if (e.shiftKey || e.altKey) {
            e.preventDefault();
            const thunkCreator = app.thunks && app.thunks.resizeSelectedRegionIntent;
            const dispatch = app.store && app.store.dispatch;
            if (typeof thunkCreator !== 'function') {
                console.error('[EventHandler] Missing resizeSelectedRegionIntent thunk.');
                return;
            }
            if (typeof dispatch !== 'function') {
                console.error('[EventHandler] Store is not available for dispatch.');
                return;
            }

            dispatch(thunkCreator({
                key: e.key,
                modifiers: {
                    shift: Boolean(e.shiftKey),
                    alt: Boolean(e.altKey)
                }
            }));
            return;
        }

        e.preventDefault();
        const thunkCreator = app.thunks && app.thunks.nudgeTapLineIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing nudgeTapLineIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        dispatch(thunkCreator({ key: e.key }));
    }



    /**
         * Wraps a function with error handling that identifies the function name
         * @param {Function} fn - The function to wrap
         * @param {string} fnName - The name of the function for error reporting
         * @returns {Function} The wrapped function
         */
    function withErrorHandling(fn, fnName) {
        return function (...args) {
            try {
                return fn.apply(this, args);
            } catch (error) {
                console.error(`[EventHandler Error] Function '${fnName}' failed:`, error);
                console.error('Arguments:', args);
                // Re-throw to allow debugging, or handle gracefully
                throw error;
            }
        };
    }

    // Attach the public functions to the global object with error handling
    app.eventHandlers = {
        handleTap: withErrorHandling(handleTap, 'handleTap'),
        handleChartHover: withErrorHandling(handleChartHover, 'handleChartHover'),
        handleRangeUpdate: withErrorHandling(handleRangeUpdate, 'handleRangeUpdate'),
        handleDoubleClick: withErrorHandling(handleDoubleClick, 'handleDoubleClick'),
        handleRegionBoxSelect: withErrorHandling(handleRegionBoxSelect, 'handleRegionBoxSelect'),
        handleParameterChange: withErrorHandling(handleParameterChange, 'handleParameterChange'),
        handleViewToggle: withErrorHandling(handleViewToggle, 'handleViewToggle'),
        handleHoverToggle: withErrorHandling(handleHoverToggle, 'handleHoverToggle'),
        handleVisibilityChange: withErrorHandling(handleVisibilityChange, 'handleVisibilityChange'),
        handleAudioStatusUpdate: withErrorHandling(handleAudioStatusUpdate, 'handleAudioStatusUpdate'),
        togglePlayPause: withErrorHandling(togglePlayPause, 'togglePlayPause'),
        handlePlaybackRateChange: withErrorHandling(handlePlaybackRateChange, 'handlePlaybackRateChange'),
        handleVolumeBoostToggle: withErrorHandling(handleVolumeBoostToggle, 'handleVolumeBoostToggle'),
        handleKeyPress: withErrorHandling(handleKeyPress, 'handleKeyPress'),
        clearAllMarkers: withErrorHandling(clearAllMarkers, 'clearAllMarkers'),
        handleStartComparison: withErrorHandling(handleStartComparison, 'handleStartComparison'),
        handleFinishComparison: withErrorHandling(handleFinishComparison, 'handleFinishComparison'),
        handleComparisonPositionsChange: withErrorHandling(handleComparisonPositionsChange, 'handleComparisonPositionsChange'),
        handleComparisonMakeRegions: withErrorHandling(handleComparisonMakeRegions, 'handleComparisonMakeRegions')
    };
})(window.NoiseSurveyApp);
