// noise_survey_analysis/static/js/state-management.js

/**
 * @fileoverview Manages the core state of the Noise Survey application.
 * This file defines the main `_state` object structure and contains the central
 * `dispatchAction` function, which acts as a "reducer." It is responsible for
 * applying simple, direct state mutations based on dispatched actions and
 * orchestrating the subsequent calls to data processors and renderers.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const SpectrogramChart = app.classes.SpectrogramChart;
    const LineChart = app.classes.LineChart;
    const FreqBarChart = app.classes.FreqBarChart;

    let _models = {};
    let _state = {
        data: {
            activeLineData: {},
            activeSpectralData: {},
            activeFreqBarData: {
                levels: [],
                frequency_labels: [],
                sourceposition: null,
                param: null,
                timestamp: null,
                setBy: null,
            },
        },
        view: {
            availablePositions: [],
            globalViewType: 'log',
            selectedParameter: 'LZeq',
            viewport: { min: null, max: null },
            chartVisibility: {},
            displayDetails: {},
            hoverEnabled: true,
        },
        interaction: {
            tap: { isActive: false, timestamp: null, position: null, sourceChartName: null },
            hover: { isActive: false, timestamp: null, position: null, sourceChartName: null, spec_y: null },
            keyboard: { enabled: false, stepSizeMs: 300000 },
        },
        markers: {
            timestamps: [],  // Array of marker timestamps
            enabled: true    // Global toggle for marker visibility
        },
        audio: {
            isPlaying: false,
            activePositionId: null,
            currentTime: 0,
            playbackRate: 1.0,
            volumeBoost: false,
        },
    };
    let _controllers = {
        positions: {},
        chartsByName: new Map(),
    };

    function getState() {
        //return JSON.parse(JSON.stringify(_state));
        return _state; // Return a direct reference to the state. This allows direct mutation, but it is necessary for preserving the complex Bokeh model objects.

    }

    function getModels() {
        return JSON.parse(JSON.stringify(_models));
    }

    function getControllers() {
        return JSON.parse(JSON.stringify(_controllers));
    }


    function initializeState(bokehModels, options) {
        console.info('Initializing state');

        const PositionController = app.classes.PositionController;

        // 1. Populate the internal _models object
        for (const key in bokehModels) {
            _models[key] = bokehModels[key];
        }

        // Look up the audio sources directly from the Bokeh document by name.
        // This is more robust than passing them through multiple JS layers.
        if (window.Bokeh && Bokeh.documents[0]) {
            _models.audio_control_source = Bokeh.documents[0].get_model_by_name('audio_control_source');
            _models.audio_status_source = Bokeh.documents[0].get_model_by_name('audio_status_source');

            if (!_models.audio_control_source) {
                console.warn("JS could not find 'audio_control_source' by name in the Bokeh document. Audio controls will not work.");
            } else {
                console.log("JS successfully found 'audio_control_source' by name.", _models.audio_control_source);
            }
            if (!_models.audio_status_source) {
                console.warn("JS could not find 'audio_status_source' by name in the Bokeh document. Audio status will not update.");
            } else {
                console.log("JS successfully found 'audio_status_source' by name.", _models.audio_status_source);
            }
        } else {
            console.error("Bokeh.documents[0] is not available. Cannot look up audio sources.");
        }

        // transfer the nested audio control widgets into the main _models object
        if (bokehModels.audio_controls) {
            _models.audio_controls = {}; // Ensure the container exists
            for (const posId in bokehModels.audio_controls) {
                _models.audio_controls[posId] = {
                    playToggle: bokehModels.audio_controls[posId].play_toggle,
                    playbackRateButton: bokehModels.audio_controls[posId].playback_rate_button,
                    volumeBoostButton: bokehModels.audio_controls[posId].volume_boost_button
                };
            }
            console.log("Audio control widgets successfully mapped to app.models.");
        }

        // 2. Populate the internal _state and _controllers objects
        _state.view.availablePositions = Array.from(new Set(_models.charts.map(c => {
            const parts = c.name.split('_');
            return parts.length >= 2 ? parts[1] : null;
        }).filter(Boolean)));

        _state.view.selectedParameter = _models.paramSelect?.value || 'LZeq';
        _state.view.viewport = { min: _models.charts[0].x_range.start, max: _models.charts[0].x_range.end };

        _state.view.availablePositions.forEach(pos => {
            _state.view.displayDetails[pos] = { line: { type: 'overview' }, spec: { type: 'overview' } };
            const posController = new PositionController(pos, _models);
            _controllers.positions[pos] = posController;
            posController.charts.forEach(chart => {
                _controllers.chartsByName.set(chart.name, chart);
                const checkbox = _models.visibilityCheckBoxes.find(cb => cb.name === `visibility_${chart.name}`);
                _state.view.chartVisibility[chart.name] = checkbox ? checkbox.active.includes(0) : true;
            });
        });

        console.log("[DEBUG] State initialized successfully:", _state);
    }



    /**
     * The central dispatcher for all application actions.
     * It orchestrates state updates, data processing, and UI rendering.
     * @param {object} action - An object describing the action (e.g., { type: 'TAP', payload: { ... } })
     */
    function dispatchAction(action) {
        //console.log(`[DEBUG] Dispatching action: ${action.type}`, action.payload);

        // --- Step 1: Update the _state object based on the action (This is the "Reducer") ---
        switch (action.type) {
            case 'TAP':
                _state.interaction.tap = {
                    isActive: true,
                    timestamp: action.payload.timestamp,
                    position: action.payload.position,
                    sourceChartName: action.payload.sourceChartName
                };

                // If audio is playing on a DIFFERENT position, this tap should switch the audio source.
                const isPlayingOnAnotherPosition = _state.audio.isPlaying && 
                                                   action.payload.position && 
                                                   action.payload.position !== _state.audio.activePositionId;

                if (isPlayingOnAnotherPosition) {
                    seek(_state.interaction.tap.timestamp, action.payload.position);
                }

                // Clear hover state on tap to prevent conflicting overlays
                _state.interaction.hover.isActive = false;
                break;
            case 'HOVER':
                _state.interaction.hover = action.payload;
                break;
            case 'VIEWPORT_CHANGE':
                _state.view.viewport = action.payload;
                break;
            case 'PARAM_CHANGE':
                _state.view.selectedParameter = action.payload.parameter;
                break;
            case 'VIEW_TOGGLE':
                _state.view.globalViewType = action.payload.newViewType;
                break;
            case 'VISIBILITY_CHANGE':
                _state.view.chartVisibility[action.payload.chartName] = action.payload.isVisible;
                // If a chart is hidden, ensure its hover div is also hidden
                const chart = _controllers.chartsByName.get(action.payload.chartName);
                if (chart instanceof SpectrogramChart && !action.payload.isVisible) {
                    chart.hoverDivModel.visible = false;
                }
                break;
            case 'AUDIO_UPDATE':
                _state.audio.isPlaying = action.payload.status.is_playing[0];
                _state.audio.activePositionId = action.payload.status.active_position_id[0];
                _state.audio.currentTime = action.payload.status.current_time[0];
                _state.audio.playbackRate = action.payload.status.playback_rate[0];
                _state.audio.volumeBoost = action.payload.status.volume_boost[0];

                // If audio is playing, sync the tap/cursor position to the audio time
                if (_state.audio.isPlaying) {
                    _state.interaction.tap.timestamp = _state.audio.currentTime;
                    _state.interaction.tap.isActive = true;
                    _state.interaction.tap.position = _state.audio.activePositionId;
                }
                break;
            case 'AUDIO_PLAY_PAUSE_TOGGLE': {
                const { positionId, isActive } = action.payload;
                const command = isActive ? 'play' : 'pause';
                const timestamp = _state.interaction.tap.timestamp;

                // Predictive UI update: Change the state immediately for a smooth experience.
                if (command === 'play') {
                    _state.audio.isPlaying = true;
                    _state.audio.activePositionId = positionId;
                } else {
                    // Only the active position can be paused.
                    if (_state.audio.activePositionId === positionId) {
                        _state.audio.isPlaying = false;
                    }
                }
                app.renderers.renderAudioControls(); // Re-render controls immediately with the new state.
                _models.audio_control_source.data = { command: [command], position_id: [positionId], value: [timestamp] };
                }
                break;
            case 'KEY_NAV':
                _state.interaction.tap.timestamp = action.payload.newTimestamp;
                _state.interaction.tap.isActive = true;
                // If no position is active, infer from the first available position
                if (!_state.interaction.tap.position && _state.view.availablePositions.length > 0) {
                    _state.interaction.tap.position = _state.view.availablePositions[0];
                }
                break;
            case 'ADD_MARKER': {
                const timestamp = action.payload.timestamp;
                if (!_state.markers.timestamps.includes(timestamp)) {
                    // 1. Update State
                    _state.markers.timestamps.push(timestamp);
                    _state.markers.timestamps.sort((a, b) => a - b);

                    console.log(`[Marker] Added marker at ${new Date(timestamp).toLocaleString()}`);
                }
                break; // State updated. UI will be synced separately.
            }

            case 'REMOVE_MARKER': {
                const timestamp = action.payload.timestamp;
                const viewportWidthMs = _state.view.viewport.max - _state.view.viewport.min;
                const threshold = Math.max(10000, viewportWidthMs * 0.02); // At least 10s threshold
                let closestIndex = -1;
                let closestDistance = Infinity;

                _state.markers.timestamps.forEach((markerTime, index) => {
                    const distance = Math.abs(markerTime - timestamp);
                    if (distance < threshold && distance < closestDistance) {
                        closestDistance = distance;
                        closestIndex = index;
                    }
                });

                if (closestIndex !== -1) {
                    // 1. Update State
                    const removedTimestamp = _state.markers.timestamps.splice(closestIndex, 1)[0];

                    console.log(`[Marker] Removed marker at ${new Date(removedTimestamp).toLocaleString()}`);
                }
                break; // State updated. UI will be synced separately.
            }


            case 'CLEAR_ALL_MARKERS': {
                const markerCount = _state.markers.timestamps.length;
                // 1. Update State
                _state.markers.timestamps = [];

                console.log(`[Marker] Cleared ${markerCount} markers`);
                break; // State updated. UI will be synced separately.
            }

            case 'HOVER_TOGGLE':
                _state.view.hoverEnabled = action.payload.isActive;
                break;

            case 'KEYBOARD_SETUP_COMPLETE':
                _state.interaction.keyboard.enabled = true;
                break;

            case 'INITIAL_LOAD':
                // No specific state change needed; its purpose is to trigger a heavy update.
                break;
            default:
                console.warn(`[DEBUG] Unknown action type: ${action.type}`);
                return;
        }

        // --- Step 2: Decide which rendering path to take and execute it ---
        const isHeavyUpdate = ['VIEWPORT_CHANGE', 'PARAM_CHANGE', 'VIEW_TOGGLE', 'VISIBILITY_CHANGE', 'INITIAL_LOAD'].includes(action.type);

        // Determine if markers need to be updated. This is done outside the heavy update block
        // because marker updates can be triggered by light actions (add/remove marker).
        const needsMarkerUpdate = ['ADD_MARKER', 'REMOVE_MARKER', 'CLEAR_ALL_MARKERS', 'INITIAL_LOAD'].includes(action.type);

        if (isHeavyUpdate) {
            app.data_processors.updateActiveData(_state.view, _state.data, _models);

            const newStepSize = app.data_processors.calculateStepSize(_state); //shouldnt really be passing state (unsafe). should use getState() for this and pass only state.data
            if (newStepSize !== _state.interaction.keyboard.stepSizeMs) {
                _state.interaction.keyboard.stepSizeMs = newStepSize;
                console.log(`[DEBUG] Step size updated to ${newStepSize}ms`);
            }

            app.renderers.renderPrimaryCharts(_state);

        }
        else {
            // If it's not a heavy update, it's a light one (e.g., TAP, HOVER, AUDIO_UPDATE, KEY_NAV).
            app.data_processors.updateActiveFreqBarData(_state.view, _state.data, _models);
            app.renderers.renderOverlays();
        }

        // --- Step 3: Perform specific post-rendering updates ---

        // Sync marker visuals if the state changed or on initial load.
        if (needsMarkerUpdate) {
            app.renderers.renderMarkers();
        }

        if (action.type === 'TAP' || action.type === 'KEY_NAV') {
            // Only seek if audio is already playing. A simple tap shouldn't start audio.
            if (_state.audio.isPlaying) {
                const seekTime = action.payload.newTimestamp || action.payload.timestamp;
                seek(seekTime, _state.interaction.tap.position);
            }
        }
        if (action.type === 'AUDIO_UPDATE') {
            app.renderers.renderAudioControls(); // This only needs to run when audio status itself changes.
        }
    }

    
    function seek(time, positionId) {
        if (!_models.audio_control_source) {
            console.warn("Audio controls are disabled in static mode.");
            return;
        }
        const pos = positionId || _state.audio.activePositionId;
        if (pos === null || pos === undefined) return;
        console.log(`Sending seek command for position ${pos} to time ${new Date(time).toLocaleString()}`);
        _models.audio_control_source.data = { command: ['seek'], position_id: [pos], value: [time] };
    }

    // Attach the public functions to the global object
    app.state = {
        initializeState: initializeState,
        dispatchAction: dispatchAction,
        getState: getState,
    };
    app.models = _models;
    app.controllers = _controllers;

})(window.NoiseSurveyApp);
