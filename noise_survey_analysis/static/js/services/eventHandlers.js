// noise_survey_analysis/static/js/services/eventHandlers.js

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

    // --- Helper Functions ---
    const _getChartPositionByName = (chartName) => {
        if (!chartName) return null;
        // Chart names follow "figure_{positionId}_{chartType}" and position ids
        // may themselves contain underscores, so strip the known prefix/suffix
        // (mirrors the availablePositions derivation in registry.js) instead of
        // splitting on '_', which truncates ids like "971-4_2026-02-02".
        const prefix = 'figure_';
        const suffixes = ['_timeseries', '_spectrogram'];
        if (chartName.startsWith(prefix)) {
            const stripped = chartName.slice(prefix.length);
            for (const suffix of suffixes) {
                if (stripped.endsWith(suffix)) {
                    const positionId = stripped.slice(0, -suffix.length);
                    return positionId || null;
                }
            }
        }
        const parts = chartName.split('_');
        return parts.length >= 2 ? parts[1] : null;
    };

    function _getClassificationHit(chartName, timestamp, y) {
        if (!Number.isFinite(timestamp) || !Number.isFinite(y)) {
            return null;
        }

        const chartsByName = app.registry?.controllers?.chartsByName;
        const chart = chartsByName && typeof chartsByName.get === 'function'
            ? chartsByName.get(chartName)
            : null;
        const overlay = chart?.classificationOverlay;
        if (!overlay?.renderer?.visible || !overlay?.source?.data) {
            return null;
        }

        const data = overlay.source.data;
        const left = data.left;
        const right = data.right;
        const bottom = data.bottom;
        const top = data.top;
        const ids = data.classification_id;
        const length = Math.min(
            Number(left?.length) || 0,
            Number(right?.length) || 0,
            Number(bottom?.length) || 0,
            Number(top?.length) || 0,
            Number(ids?.length) || 0
        );

        for (let index = 0; index < length; index += 1) {
            const leftValue = Number(left[index]);
            const rightValue = Number(right[index]);
            const bottomValue = Number(bottom[index]);
            const topValue = Number(top[index]);
            if (!Number.isFinite(leftValue) || !Number.isFinite(rightValue)
                || !Number.isFinite(bottomValue) || !Number.isFinite(topValue)) {
                continue;
            }
            if (timestamp >= leftValue && timestamp <= rightValue
                && y >= Math.min(bottomValue, topValue)
                && y <= Math.max(bottomValue, topValue)) {
                return {
                    index,
                    id: Number(ids[index])
                };
            }
        }

        return null;
    }

    // --- Event Handlers ---

    function handleTap(cb_obj) {
        const chartName = cb_obj?.origin?.name || cb_obj?.model?.name;
        if (!chartName || chartName === 'frequency_bar') return;
        const positionId = _getChartPositionByName(chartName);
        if (!positionId) return;
        const timestamp = cb_obj?.x;
        if (!Number.isFinite(timestamp)) return;

        // A classification quad lives on the same plot-level tap surface. A
        // hit must select the classification without turning a review click
        // into an audio seek.
        const classificationHit = _getClassificationHit(chartName, timestamp, Number(cb_obj?.y));
        if (classificationHit) {
            const selectIntent = app.features?.classifications?.thunks?.selectClassificationIntent;
            const dispatch = app.store && app.store.dispatch;
            if (Number.isFinite(classificationHit.id)
                && typeof selectIntent === 'function'
                && typeof dispatch === 'function') {
                dispatch(selectIntent(classificationHit.id));
            }
            return;
        }

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

        const modifiers = {
            ctrl: Boolean(cb_obj?.modifiers?.ctrl)
        };
        if (cb_obj?.modifiers?.shift) {
            modifiers.shift = true;
        }

        dispatch(thunkCreator({
            timestamp,
            positionId,
            chartName,
            modifiers
        }));
    }

    function handleRegionListDoubleClick(event) {
        const path = typeof event?.composedPath === 'function' ? event.composedPath() : [];
        const hasClass = (node, name) => node?.classList?.contains?.(name);
        if (!path.some(node => hasClass(node, 'region-panel-table'))
            || !path.some(node => hasClass(node, 'slick-row'))) return;

        const source = app.registry?.models?.regionPanelSource;
        const indices = source?.selected?.indices;
        if (!Array.isArray(indices) || indices.length !== 1) return;
        const regionId = Number(source?.data?.id?.[indices[0]]);
        const intent = app.thunks?.centerViewportOnRegionIntent;
        if (Number.isFinite(regionId) && typeof intent === 'function'
            && typeof app.store?.dispatch === 'function') {
            app.store.dispatch(intent(regionId));
        }
    }

    function handleRegionBoxSelect(cb_obj) {
        const chartName = cb_obj?.origin?.name || cb_obj?.model?.name;
        if (!chartName || chartName === 'frequency_bar') return;

        const geometry = cb_obj?.geometry;
        if (!geometry || geometry.type !== 'rect') return;

        const x0 = geometry.x0;
        const x1 = geometry.x1;
        if (!Number.isFinite(x0) || !Number.isFinite(x1)) return;

        const positionId = _getChartPositionByName(chartName);
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
                sourceChartName: chartName,
                final: Boolean(cb_obj?.final)
            }));
        }

        if (!cb_obj?.final) {
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

    function handleRangeUpdate(cb_obj) {
        const handler = app.services?.eventHandlers?.view?.handleRangeUpdate;
        if (typeof handler === 'function') {
            handler(cb_obj);
        }
    }

    function handleDoubleClick(cb_obj) {
        const chartName = cb_obj?.origin?.name || cb_obj?.model?.name;
        if (!chartName || chartName === 'frequency_bar') return;
        const positionId = _getChartPositionByName(chartName);
        if (!positionId) return;
        const timestamp = cb_obj?.x;
        if (!Number.isFinite(timestamp)) return;
        
        const thunkCreator = app.thunks && app.thunks.createMarkerIntent;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing createMarkerIntent thunk.');
            return;
        }
    
        app.store.dispatch(thunkCreator({ timestamp: timestamp, positionId: positionId }));
    }

    function clearAllMarkers() {
        if (typeof actions?.markersReplace !== 'function') {
            console.error('[EventHandler] markersReplace action creator is not available.');
            return;
        }
        app.store.dispatch(actions.markersReplace([]));
    }

    function handleParameterChange(value) {
        const handler = app.services?.eventHandlers?.view?.handleParameterChange;
        if (typeof handler === 'function') {
            handler(value);
        }
    }

    function handleViewToggle(isActive) {
        const handler = app.services?.eventHandlers?.view?.handleViewToggle;
        if (typeof handler === 'function') {
            handler(isActive);
        }
    }

    function handleHoverToggle(isActive) {
        const handler = app.services?.eventHandlers?.view?.handleHoverToggle;
        if (typeof handler === 'function') {
            handler(isActive);
        }
    }

    function handleVisibilityChange(cb_obj, chartName) {
        const handler = app.services?.eventHandlers?.view?.handleVisibilityChange;
        if (typeof handler === 'function') {
            handler(cb_obj, chartName);
        }
    }

    function handleAutoRegions() {
        const thunkCreator = app.thunks && app.thunks.createAutoRegionsIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing createAutoRegionsIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        dispatch(thunkCreator());
    }

    function handleAudioStatusUpdate() {
        const status = app.registry.models.audio_status_source?.data;
        const thunkCreator = app.thunks && app.thunks.handleAudioStatusUpdateIntent;
        const dispatch = app.store && app.store.dispatch;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing handleAudioStatusUpdateIntent thunk.');
            return;
        }
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        dispatch(thunkCreator(status));
    }

    function dispatchOffsetUpdate(actionCreator, payload) {
        const dispatch = app.store && app.store.dispatch;
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        const positionId = typeof payload?.positionId === 'string' ? payload.positionId : null;
        if (!positionId || typeof actionCreator !== 'function') {
            return;
        }

        const offsetSecondsRaw = Number(payload?.offsetSeconds);
        const offsetSeconds = Number.isFinite(offsetSecondsRaw) ? offsetSecondsRaw : 0;

        dispatch(actionCreator(positionId, offsetSeconds * 1000));
    }

    function handlePositionChartOffsetChange(payload) {
        dispatchOffsetUpdate(actions.positionChartOffsetSet, payload);
    }

    function handlePositionAudioOffsetChange(payload) {
        dispatchOffsetUpdate(actions.positionAudioOffsetSet, payload);
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

    function handleLogViewThresholdChange(value) {
        const handler = app.services?.eventHandlers?.view?.handleLogViewThresholdChange;
        if (typeof handler === 'function') {
            handler(value);
        }
    }

    function handleKeyPress(e) {
        // Ignore keyboard events from editable elements
        if (app.utils && typeof app.utils.isEditableEvent === 'function') {
            if (app.utils.isEditableEvent(e)) {
                // Esc or Ctrl+Enter in the region note leaves the field. Blurring
                // commits the note and hands the keyboard back to chart shortcuts.
                const path = typeof e.composedPath === 'function' ? e.composedPath() : [];
                const isLeaveNoteKey = e.key === 'Escape'
                    || (e.key === 'Enter' && (e.ctrlKey || e.metaKey));
                if (isLeaveNoteKey && path.some(node => node?.classList?.contains?.('region-note-input'))) {
                    const textarea = path.find(node => node?.tagName === 'TEXTAREA');
                    textarea?.blur?.();
                    e.preventDefault?.();
                }
                return;
            }
        }

        const dispatch = app.store && app.store.dispatch;
        if (typeof dispatch !== 'function') {
            console.error('[EventHandler] Store is not available for dispatch.');
            return;
        }

        const thunkCreator = app.thunks && app.thunks.handleKeyboardShortcutIntent;
        if (typeof thunkCreator !== 'function') {
            console.error('[EventHandler] Missing handleKeyboardShortcutIntent thunk.');
            return;
        }

        const rawKey = typeof e.key === 'string' ? e.key : '';
        const normalizedKey = rawKey.toLowerCase();
        const code = typeof e.code === 'string' ? e.code : '';

        const isCtrlOrMeta = Boolean(e.ctrlKey) || Boolean(e.metaKey);

        // Undo/redo: handle before the general key filter
        if (isCtrlOrMeta && normalizedKey === 'z' && !e.shiftKey) {
            if (typeof e.preventDefault === 'function') e.preventDefault();
            const undoRedoThunk = app.thunks && app.thunks.handleUndoRedoIntent;
            if (typeof undoRedoThunk === 'function') {
                dispatch(undoRedoThunk({ direction: 'undo' }));
            }
            return;
        }
        if (isCtrlOrMeta && (normalizedKey === 'y' || (normalizedKey === 'z' && e.shiftKey))) {
            if (typeof e.preventDefault === 'function') e.preventDefault();
            const undoRedoThunk = app.thunks && app.thunks.handleUndoRedoIntent;
            if (typeof undoRedoThunk === 'function') {
                dispatch(undoRedoThunk({ direction: 'redo' }));
            }
            return;
        }

        const isSpace = code === 'Space' || rawKey === ' ' || rawKey === 'Spacebar';
        const isEscape = rawKey === 'Escape';
        const isMarkerKey = normalizedKey === 'm';
        const isRegionKey = normalizedKey === 'r';
        const isNoteKey = normalizedKey === 'n' && !isCtrlOrMeta && !e.altKey;
        const isBackKey = normalizedKey === 'b' && !isCtrlOrMeta && !e.altKey;
        const isRegionStepKey = (rawKey === '[' || rawKey === ']') && !isCtrlOrMeta && !e.altKey;
        const isPreviewKey = normalizedKey === 'p';
        const isArrowKey = rawKey === 'ArrowLeft' || rawKey === 'ArrowRight';
        const isDeleteKey = rawKey === 'Delete' || rawKey === 'Backspace';

        if (isPreviewKey && !isCtrlOrMeta) {
            if (typeof e.preventDefault === 'function') e.preventDefault();
            const previewThunk = app.features?.classifications?.thunks?.previewSelectedClassificationIntent;
            if (typeof previewThunk === 'function') {
                dispatch(previewThunk());
            }
            return;
        }

        const isShortcutKey = isSpace || isEscape || isMarkerKey || isRegionKey || isNoteKey
            || isBackKey || isRegionStepKey || isArrowKey || isDeleteKey;
        if (!isShortcutKey) {
            return;
        }
        if (typeof e.preventDefault === 'function') {
            e.preventDefault();
        }

        dispatch(thunkCreator({
            key: rawKey,
            code,
            ctrlKey: Boolean(e.ctrlKey),
            altKey: Boolean(e.altKey)
        }));
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
                console.error(`[EventHandler Error] Stack trace:`, error.stack);
                console.error('[EventHandler Error] Arguments:', args);
                // Don't re-throw - allow the app to continue gracefully
                // The error has been logged with full context for debugging
            }
        };
    }

    // Attach the public functions to the global object with error handling
    app.eventHandlers = {
        handleTap: withErrorHandling(handleTap, 'handleTap'),
        handleRegionListDoubleClick: withErrorHandling(handleRegionListDoubleClick, 'handleRegionListDoubleClick'),
        handleChartHover: withErrorHandling(handleChartHover, 'handleChartHover'),
        handleRangeUpdate: withErrorHandling(handleRangeUpdate, 'handleRangeUpdate'),
        handleDoubleClick: withErrorHandling(handleDoubleClick, 'handleDoubleClick'),
        handleRegionBoxSelect: withErrorHandling(handleRegionBoxSelect, 'handleRegionBoxSelect'),
        handleParameterChange: withErrorHandling(handleParameterChange, 'handleParameterChange'),
        handleViewToggle: withErrorHandling(handleViewToggle, 'handleViewToggle'),
        handleHoverToggle: withErrorHandling(handleHoverToggle, 'handleHoverToggle'),
        handleVisibilityChange: withErrorHandling(handleVisibilityChange, 'handleVisibilityChange'),
        handleAudioStatusUpdate: withErrorHandling(handleAudioStatusUpdate, 'handleAudioStatusUpdate'),
        handlePositionChartOffsetChange: withErrorHandling(handlePositionChartOffsetChange, 'handlePositionChartOffsetChange'),
        handlePositionAudioOffsetChange: withErrorHandling(handlePositionAudioOffsetChange, 'handlePositionAudioOffsetChange'),
        togglePlayPause: withErrorHandling(togglePlayPause, 'togglePlayPause'),
        handlePlaybackRateChange: withErrorHandling(handlePlaybackRateChange, 'handlePlaybackRateChange'),
        handleVolumeBoostToggle: withErrorHandling(handleVolumeBoostToggle, 'handleVolumeBoostToggle'),
        handleKeyPress: withErrorHandling(handleKeyPress, 'handleKeyPress'),
        clearAllMarkers: withErrorHandling(clearAllMarkers, 'clearAllMarkers'),
        handleAutoRegions: withErrorHandling(handleAutoRegions, 'handleAutoRegions'),
        handleStartComparison: withErrorHandling(handleStartComparison, 'handleStartComparison'),
        handleFinishComparison: withErrorHandling(handleFinishComparison, 'handleFinishComparison'),
        handleComparisonPositionsChange: withErrorHandling(handleComparisonPositionsChange, 'handleComparisonPositionsChange'),
        handleComparisonMakeRegions: withErrorHandling(handleComparisonMakeRegions, 'handleComparisonMakeRegions'),
        handleLogViewThresholdChange: withErrorHandling(handleLogViewThresholdChange, 'handleLogViewThresholdChange')
    };
})(window.NoiseSurveyApp);
