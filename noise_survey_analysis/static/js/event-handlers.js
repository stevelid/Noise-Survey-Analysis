// noise_survey_analysis/static/js/event-handlers.js

/**
 * @fileoverview Contains all event handler functions for the Noise Survey application.
 * These functions are directly connected to Bokeh widget and plot events (e.g., tap, hover,
 * range updates). Their primary role is to interpret the raw event data from Bokeh
 * and translate it into a structured action object that can be dispatched to the
 * state management module.
 */


window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function(app) {
    'use strict';

const DEBOUNCE_DELAY = 50; // ms

let _dispatchAction = app.state.dispatchAction;
let _getState = app.state.getState;
let _controllers = app.controllers;
let _models = app.models;

/**
 * Debounces a function call, ensuring it's only executed after a certain delay.
 * @param {function} func - The function to debounce.
 * @param {number} delay - The delay in milliseconds.
 * @returns {function} The debounced function.
 */
function debounce(func, delay) {
    let timeout;
    return function (...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}

function handleTap(cb_obj) {
    const chartName = cb_obj.origin.name;
    const positionId = _getChartPositionByName(chartName);

    console.log(cb_obj);

    // Check if Ctrl key is pressed for marker removal
    if (cb_obj.modifiers && cb_obj.modifiers.ctrl) {
        _dispatchAction({
            type: 'REMOVE_MARKER',
            payload: {
                timestamp: cb_obj.x,
                position: positionId
            }
        });
        return; // Stop further processing
    }

    if (chartName === 'frequency_bar') return;
    // If no modifier key, it's a normal tap
    _dispatchAction({
        type: 'TAP',
        payload: {
            timestamp: cb_obj.x,
            position: positionId,
            sourceChartName: chartName
        }
    });
}

function handleChartHover(cb_data, chartName) {
    const geometry = cb_data.geometry;
    const isActive = geometry && Number.isFinite(geometry.x);
    if (isActive) {
        _dispatchAction({
            type: 'HOVER',
            payload: {
                isActive: true,
                sourceChartName: chartName,
                timestamp: geometry.x,
                spec_y: geometry.y,
                position: _getChartPositionByName(chartName),
            }
        });
    }
    else {
        _dispatchAction({ type: 'HOVER', payload: { isActive: false } });
    }
}

const debouncedRangeUpdate = debounce((cb_obj) => {
    _dispatchAction({
        type: 'VIEWPORT_CHANGE',
        payload: {
            min: cb_obj.start,
            max: cb_obj.end
        }
    });
}, 200); // Debounce by 200ms

function handleRangeUpdate(cb_obj) {
    debouncedRangeUpdate(cb_obj);
}

function handleDoubleClick(cb_obj) {
    const chartName = cb_obj.origin.name;
    if (chartName === 'frequency_bar') return;
    _dispatchAction({
        type: 'ADD_MARKER',
        payload: { timestamp: cb_obj.x }
    });
}

function clearAllMarkers() {
    _dispatchAction({ type: 'CLEAR_ALL_MARKERS' });
}

function handleParameterChange(value) {
    _dispatchAction({
        type: 'PARAM_CHANGE',
        payload: {
            parameter: value
        }
    });
}

function handleViewToggle(isActive, toggleWidget) {
    const newViewType = isActive ? 'log' : 'overview';
    _dispatchAction({
        type: 'VIEW_TOGGLE',
        payload: {
            newViewType: newViewType
        }
    });
    if (toggleWidget) {
        toggleWidget.label = isActive ? "Log View Enabled" : "Log View Disabled";
    }
}

function handleHoverToggle(isActive, toggleWidget) {
    _dispatchAction({
        type: 'HOVER_TOGGLE',
        payload: {
            isActive: isActive
        }
    });
    if (toggleWidget) { //???this might not be needed here???
        toggleWidget.label = isActive ? "Hover Enabled" : "Hover Disabled";
    }
    // If hover is disabled, immediately hide all hover effects
    if (!isActive) {
        _controllers.chartsByName.forEach(chart => {
            chart.hideHoverLine();
            chart.hideLabel();
        });
    }
}

function handleVisibilityChange(cb_obj, chartName) {
    const isVisible = Array.isArray(cb_obj.active) ? cb_obj.active.includes(0) : Boolean(cb_obj.active);
    _dispatchAction({ type: 'VISIBILITY_CHANGE', payload: { chartName: chartName, isVisible: isVisible } });
}

function handleAudioStatusUpdate() {
    const status = _models.audio_status_source.data;
    _dispatchAction({ type: 'AUDIO_UPDATE', payload: { status: status } });
}

/**
 * Handles a click on a Play/Pause toggle button.
 * This function's role is to dispatch a clear, semantic action to the state manager.
 * @param {string} positionId - The ID of the position whose button was clicked.
 * @param {boolean} isActive - The new state of the button (true if "Play" was just activated).
 */
function togglePlayPause(positionId, isActive) {    
    _dispatchAction({ type: 'AUDIO_PLAY_PAUSE_TOGGLE', payload: { positionId, isActive } });
}

function handlePlaybackRateChange(positionId) {
    const _state = app.state.getState();
    const currentRate = _state.audio.playbackRate;
    const rates = [1.0, 1.5, 2.0, 4.0, 0.5];
    const currentIndex = rates.indexOf(currentRate);
    const nextIndex = (currentIndex + 1) % rates.length;
    const newRate = rates[nextIndex];

    console.log(`Changing playback rate for ${positionId} from ${currentRate}x to ${newRate}x`);
    _models.audio_control_source.data = { command: ['set_rate'], position_id: [positionId], value: [newRate] };
    // This also needs to be a full data replacement to trigger Python
}

function handleVolumeBoostToggle(positionId, isBoostActive) {
    console.log(`Toggling volume boost for ${positionId} to: ${isBoostActive}`);
    _models.audio_control_source.data = { 
        command: ['toggle_boost'], 
        position_id: [positionId], 
        value: [isBoostActive]  // Send true or false
    };
}

function handleKeyPress(e) {
    const _state = app.state.getState();
    const targetTagName = e.target.tagName.toLowerCase();
    if (targetTagName === 'input' || targetTagName === 'textarea' || targetTagName === 'select') return;

    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault();
        let currentX = _state.interaction.tap.timestamp || _state.view.viewport.min || 0;
        const step = _state.interaction.keyboard.stepSizeMs || 300000;
        let newX = e.key === 'ArrowLeft' ? currentX - step : currentX + step;
        newX = Math.max(_state.view.viewport.min, Math.min(_state.view.viewport.max, newX));

        _dispatchAction({
            type: 'KEY_NAV',
            payload: {
                newTimestamp: newX
            }
        });
    }
}



function _getChartPositionByName(chartName) {
    if (!chartName) return null;
    const parts = chartName.split('_');
    if (parts.length >= 2) {
        // Simply return the parsed position name, e.g., 'East' or 'West'
        return parts[1];
    }
    return null;
}

/**
     * Wraps a function with error handling that identifies the function name
     * @param {Function} fn - The function to wrap
     * @param {string} fnName - The name of the function for error reporting
     * @returns {Function} The wrapped function
     */
    function withErrorHandling(fn, fnName) {
        return function(...args) {
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
        handleParameterChange: withErrorHandling(handleParameterChange, 'handleParameterChange'),
        handleViewToggle: withErrorHandling(handleViewToggle, 'handleViewToggle'),
        handleHoverToggle: withErrorHandling(handleHoverToggle, 'handleHoverToggle'),
        handleVisibilityChange: withErrorHandling(handleVisibilityChange, 'handleVisibilityChange'),
        handleAudioStatusUpdate: withErrorHandling(handleAudioStatusUpdate, 'handleAudioStatusUpdate'),
        togglePlayPause: withErrorHandling(togglePlayPause, 'togglePlayPause'),
        handlePlaybackRateChange: withErrorHandling(handlePlaybackRateChange, 'handlePlaybackRateChange'),
        handleVolumeBoostToggle: withErrorHandling(handleVolumeBoostToggle, 'handleVolumeBoostToggle'),
        handleKeyPress: withErrorHandling(handleKeyPress, 'handleKeyPress'),
        clearAllMarkers: withErrorHandling(clearAllMarkers, 'clearAllMarkers')
    };
})(window.NoiseSurveyApp);
