// noise_survey_analysis/static/js/reducers.js

/**
 * @fileoverview Contains the root reducer for the application's state.
 * The reducer is a pure function that takes the previous state and an action,
 * and returns the next state.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    // --- Dependencies ---
    const { actionTypes } = app; //TODO: move to a separate file (split reducer) approach

    const initialComparisonState = {
        isActive: false,
        start: null,
        end: null,
        includedPositions: []
    };

    const initialState = {
        view: {
            availablePositions: [],
            globalViewType: 'log', // 'log' or 'overview'
            selectedParameter: 'LZeq', //default parameter
            viewport: { min: null, max: null },
            chartVisibility: {},
            displayDetails: {},
            hoverEnabled: true,
            mode: 'normal',
            comparison: { ...initialComparisonState },
        },
        interaction: {
            tap: { isActive: false, timestamp: null, position: null, sourceChartName: null },
            hover: { isActive: false, timestamp: null, position: null, sourceChartName: null, spec_y: null },
            keyboard: { enabled: false, stepSizeMs: 300000 },
        },
        markers: {
            timestamps: [],  // Array of marker timestamps
            enabled: true,   // Global toggle for marker visibility
            regions: {
                byId: {},
                allIds: [],
                selectedId: null,
                counter: 1
            }
        },
        audio: {
            isPlaying: false,
            activePositionId: null,
            playbackRate: 1.0,
            volumeBoost: false,
        },
        system: {
            initialized: false,
            lastAction: null, 
        }
    };

    function normalizeRegionBounds(start, end) {
        if (!Number.isFinite(start) || !Number.isFinite(end)) {
            return null;
        }
        if (start === end) {
            return null;
        }
        const normalizedStart = Math.min(start, end);
        const normalizedEnd = Math.max(start, end);
        return { start: normalizedStart, end: normalizedEnd };
    }

    function appReducer(state = initialState, action) {

        switch (action.type) {

            // --- Initialize Actions ---

            case actionTypes.INITIALIZE_STATE:
                return {
                    ...state,
                    view: {
                        ...state.view,
                        availablePositions: action.payload.availablePositions,
                        selectedParameter: action.payload.selectedParameter,
                        viewport: action.payload.viewport,
                        chartVisibility: action.payload.chartVisibility,
                        mode: 'normal',
                        comparison: {
                            ...initialComparisonState,
                            includedPositions: Array.isArray(action.payload.availablePositions)
                                ? [...action.payload.availablePositions]
                                : []
                        },
                    },
                    system: {
                        ...state.system,
                        initialized: true,
                    }
                };

            // --- Interaction Actions ---
            case actionTypes.TAP:
                return {
                    ...state,
                    interaction: {
                        ...state.interaction,
                        tap: { ...action.payload, isActive: true },
                        hover: { ...state.interaction.hover } // Reset hover
                    },
                    // Optimistically update the active audio position to match the tap.
                    // This ensures the UI state is immediately consistent with the user's action.
                    audio: {
                        ...state.audio,
                        activePositionId: action.payload.position
                    }
                };

            case actionTypes.HOVER:
                return {
                    ...state,
                    interaction: {
                        ...state.interaction,
                        hover: { ...action.payload },
                    }
                };

            case actionTypes.KEY_NAV: {
                if (!state.interaction.tap.isActive) {
                    return state;
                }
                const currentTime = state.interaction.tap.timestamp;
                const step = state.interaction.keyboard.stepSizeMs;
                const { min, max } = state.view.viewport;

                let newTimestamp = action.payload.direction === 'left'
                    ? currentTime - step
                    : currentTime + step;

                newTimestamp = Math.max(min, Math.min(max, newTimestamp));

                return {
                    ...state,
                    interaction: {
                        ...state.interaction,
                        tap: {
                            ...state.interaction.tap,
                            timestamp: newTimestamp
                        }
                    }
                };
            }

            // --- View Actions ---
            case actionTypes.VIEWPORT_CHANGE:
                return {
                    ...state,
                    view: {
                        ...state.view,
                        viewport: action.payload
                    }
                };

            case actionTypes.PARAM_CHANGE:
                return {
                    ...state,
                    view: {
                        ...state.view,
                        selectedParameter: action.payload.parameter
                    }
                };

            case actionTypes.VIEW_TOGGLE:
                return {
                    ...state,
                    view: {
                        ...state.view,
                        globalViewType: action.payload.newViewType
                    }
                };

            case actionTypes.VISIBILITY_CHANGE:
                return {
                    ...state,
                    view: {
                        ...state.view,
                        chartVisibility: {
                            ...state.view.chartVisibility,
                            [action.payload.chartName]: action.payload.isVisible
                        }
                    }
                };

            case actionTypes.HOVER_TOGGLE:
                return {
                    ...state,
                    view: {
                        ...state.view,
                        hoverEnabled: action.payload.isActive
                    }
                };

            case actionTypes.COMPARISON_MODE_ENTERED: {
                const availablePositions = Array.isArray(state.view.availablePositions)
                    ? state.view.availablePositions
                    : [];
                return {
                    ...state,
                    view: {
                        ...state.view,
                        mode: 'comparison',
                        comparison: {
                            ...state.view.comparison,
                            isActive: true,
                            start: null,
                            end: null,
                            includedPositions: [...availablePositions]
                        }
                    }
                };
            }

            case actionTypes.COMPARISON_MODE_EXITED: {
                const availablePositions = Array.isArray(state.view.availablePositions)
                    ? state.view.availablePositions
                    : [];
                return {
                    ...state,
                    view: {
                        ...state.view,
                        mode: 'normal',
                        comparison: {
                            ...initialComparisonState,
                            includedPositions: [...availablePositions]
                        }
                    }
                };
            }

            case actionTypes.COMPARISON_POSITIONS_UPDATED: {
                const availablePositions = Array.isArray(state.view.availablePositions)
                    ? state.view.availablePositions
                    : [];
                const incoming = Array.isArray(action.payload?.includedPositions)
                    ? action.payload.includedPositions
                    : [];
                const incomingSet = new Set(incoming);
                const filtered = availablePositions.filter(pos => incomingSet.has(pos));
                return {
                    ...state,
                    view: {
                        ...state.view,
                        comparison: {
                            ...state.view.comparison,
                            includedPositions: filtered
                        }
                    }
                };
            }

            case actionTypes.COMPARISON_SLICE_UPDATED: {
                const rawStart = Number(action.payload?.start);
                const rawEnd = Number(action.payload?.end);
                const hasValidBounds = Number.isFinite(rawStart) && Number.isFinite(rawEnd) && rawStart !== rawEnd;

                const nextStart = hasValidBounds ? Math.min(rawStart, rawEnd) : null;
                const nextEnd = hasValidBounds ? Math.max(rawStart, rawEnd) : null;

                if (state.view.comparison.start === nextStart && state.view.comparison.end === nextEnd) {
                    return state;
                }

                return {
                    ...state,
                    view: {
                        ...state.view,
                        comparison: {
                            ...state.view.comparison,
                            start: nextStart,
                            end: nextEnd
                        }
                    }
                };
            }

            // --- Marker Actions ---
            case actionTypes.ADD_MARKER: {
                if (!state.markers.timestamps.includes(action.payload.timestamp)) {
                    const newTimestamps = [...state.markers.timestamps, action.payload.timestamp];
                    newTimestamps.sort((a, b) => a - b);
                    return {
                        ...state,
                        markers: {
                            ...state.markers,
                            timestamps: newTimestamps
                        }
                    };
                }
            };

            case actionTypes.REMOVE_MARKER: {
                //find the closest marker to the click timestamp
                const { clickTimestamp } = action.payload;
                const viewportWidthMs = state.view.viewport.max - state.view.viewport.min;
                const threshold = Math.max(viewportWidthMs * 0.02, 10000); // At least 10s threshold

                let closestIndex = -1;
                let closestDistance = Infinity;

                state.markers.timestamps.forEach((markerTime, index) => {
                    const distance = Math.abs(markerTime - clickTimestamp);
                    if (distance < threshold && distance < closestDistance) {
                        closestDistance = distance;
                        closestIndex = index;
                    }
                });

                if (closestIndex === -1) return state; //no change

                const newTimestamps = state.markers.timestamps.filter((_, index) => index !== closestIndex);
                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        timestamps: newTimestamps
                    }
                };
            };

            case actionTypes.CLEAR_ALL_MARKERS:
                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        timestamps: []
                    }
                };

            case actionTypes.REGION_ADDED: {
                const { positionId, start, end } = action.payload;
                if (!positionId) return state;
                const bounds = normalizeRegionBounds(start, end);
                if (!bounds) return state;

                const currentRegions = state.markers.regions;
                const id = currentRegions.counter;
                const newRegion = {
                    id,
                    positionId,
                    start: bounds.start,
                    end: bounds.end,
                    note: '',
                    metrics: null
                };

                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        regions: {
                            byId: { ...currentRegions.byId, [id]: newRegion },
                            allIds: [...currentRegions.allIds, id],
                            selectedId: id,
                            counter: id + 1
                        }
                    }
                };
            }

            case actionTypes.REGION_UPDATED: {
                const { id, changes } = action.payload || {};
                if (!id || !changes) return state;
                const currentRegions = state.markers.regions;
                const existing = currentRegions.byId[id];
                if (!existing) return state;

                let updated = { ...existing, ...changes };
                if (Object.prototype.hasOwnProperty.call(changes, 'start') || Object.prototype.hasOwnProperty.call(changes, 'end')) {
                    const candidateBounds = normalizeRegionBounds(
                        Object.prototype.hasOwnProperty.call(changes, 'start') ? changes.start : existing.start,
                        Object.prototype.hasOwnProperty.call(changes, 'end') ? changes.end : existing.end
                    );
                    if (!candidateBounds) {
                        return state;
                    }
                    updated.start = candidateBounds.start;
                    updated.end = candidateBounds.end;
                    updated.metrics = null;
                }

                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        regions: {
                            ...currentRegions,
                            byId: { ...currentRegions.byId, [id]: updated }
                        }
                    }
                };
            }

            case actionTypes.REGION_REMOVED: {
                const { id } = action.payload || {};
                const currentRegions = state.markers.regions;
                if (!id || !currentRegions.byId[id]) return state;
                const newById = { ...currentRegions.byId };
                delete newById[id];
                const newAllIds = currentRegions.allIds.filter(regionId => regionId !== id);
                const newSelectedId = currentRegions.selectedId === id ? null : currentRegions.selectedId;
                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        regions: {
                            ...currentRegions,
                            byId: newById,
                            allIds: newAllIds,
                            selectedId: newSelectedId
                        }
                    }
                };
            }

            case actionTypes.REGION_SELECTED: {
                const { id } = action.payload || {};
                const currentRegions = state.markers.regions;
                const nextSelected = id && currentRegions.byId[id] ? id : null;
                if (currentRegions.selectedId === nextSelected) return state;
                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        regions: {
                            ...currentRegions,
                            selectedId: nextSelected
                        }
                    }
                };
            }

            case actionTypes.REGION_SELECTION_CLEARED: {
                const currentRegions = state.markers.regions;
                if (currentRegions.selectedId === null) return state;
                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        regions: {
                            ...currentRegions,
                            selectedId: null
                        }
                    }
                };
            }

            case actionTypes.REGION_NOTE_SET: {
                const { id, note } = action.payload || {};
                const currentRegions = state.markers.regions;
                const region = currentRegions.byId[id];
                if (!region) return state;
                if (region.note === note) return state;
                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        regions: {
                            ...currentRegions,
                            byId: {
                                ...currentRegions.byId,
                                [id]: { ...region, note: typeof note === 'string' ? note : '' }
                            }
                        }
                    }
                };
            }

            case actionTypes.REGION_METRICS_SET: {
                const { id, metrics } = action.payload || {};
                const currentRegions = state.markers.regions;
                const region = currentRegions.byId[id];
                if (!region) return state;
                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        regions: {
                            ...currentRegions,
                            byId: {
                                ...currentRegions.byId,
                                [id]: { ...region, metrics: metrics || null }
                            }
                        }
                    }
                };
            }

            case actionTypes.REGIONS_REPLACED: {
                const incoming = Array.isArray(action.payload?.regions) ? action.payload.regions : [];
                if (incoming.length === 0) {
                    return {
                        ...state,
                        markers: {
                            ...state.markers,
                            regions: {
                                byId: {},
                                allIds: [],
                                selectedId: null,
                                counter: 1
                            }
                        }
                    };
                }

                const byId = {};
                const allIds = [];
                let maxId = 0;
                let nextGeneratedId = state.markers.regions.counter;

                incoming.forEach(region => {
                    if (!region) return;
                    const bounds = normalizeRegionBounds(region.start, region.end);
                    if (!bounds) return;
                    const positionId = region.positionId;
                    if (!positionId) return;

                    let candidateId = Number.isFinite(region.id) ? region.id : nextGeneratedId++;
                    while (byId[candidateId]) {
                        candidateId = nextGeneratedId++;
                    }
                    maxId = Math.max(maxId, candidateId);

                    byId[candidateId] = {
                        id: candidateId,
                        positionId,
                        start: bounds.start,
                        end: bounds.end,
                        note: typeof region.note === 'string' ? region.note : '',
                        metrics: region.metrics || null
                    };
                    allIds.push(candidateId);
                });

                const selectedId = byId[state.markers.regions.selectedId]
                    ? state.markers.regions.selectedId
                    : (allIds[0] ?? null);

                return {
                    ...state,
                    markers: {
                        ...state.markers,
                        regions: {
                            byId,
                            allIds,
                            selectedId,
                            counter: Math.max(maxId + 1, state.markers.regions.counter, 1)
                        }
                    }
                };
            }

            // --- Audio Actions

            case actionTypes.AUDIO_STATUS_UPDATE:
                // Update the state based on feedback from the Python backend
                return {
                    ...state,
                    audio: {
                        ...state.audio,
                        isPlaying: action.payload.status.is_playing[0],
                        activePositionId: action.payload.status.active_position_id[0],
                        playbackRate: action.payload.status.playback_rate[0],
                        volumeBoost: action.payload.status.volume_boost[0],
                    },
                    // sync the tap/cursor position to the audio time if playing
                    interaction: {
                        ...state.interaction,
                        tap: action.payload.status.is_playing[0]
                            ? {
                                isActive: true,
                                timestamp: action.payload.status.current_time[0],
                                position: action.payload.status.active_position_id[0],
                            }
                            : state.interaction.tap
                    }
                }

            case actionTypes.AUDIO_PLAY_PAUSE_TOGGLE: {
                const { positionId, isActive } = action.payload;
                if (isActive) { // Play request
                    return {
                        ...state,
                        audio: {
                            ...state.audio,
                            isPlaying: true,
                            activePositionId: positionId,
                        }
                    };
                } else { // Pause request
                    if (state.audio.activePositionId === positionId) {
                        return {
                            ...state,
                            audio: {
                                ...state.audio,
                                isPlaying: false,
                            }
                        };
                    }
                }
                return state;
            }

            // --- System Actions ---
            case actionTypes.KEYBOARD_SETUP_COMPLETE:
                return {
                    ...state,
                    interaction: { ...state.interaction, keyboard: { ...state.interaction.keyboard, enabled: true } }
                };

            case actionTypes.STEP_SIZE_CALCULATED:
                return {
                    ...state,
                    interaction: { ...state.interaction, keyboard: { ...state.interaction.keyboard, stepSizeMs: action.payload.stepSizeMs } }
                };

            default:
                // For any unhandled actions, return the current state
                return state;
        }
    }


    /**
     * A wrapper around the appReducer that orchestrates all state changes, 
     * recording the last action type.
     * @param {object} state - The current state of the application.
     * @param {object} action - The action to be processed.
     * @returns {object} The new state of the application.
     */
    function rootReducer(state, action) {
        const nextState = appReducer(state, action);
        return {
            ...nextState,
            system: {
                ...nextState.system,
                lastAction: action
            }
        };
    }
        

    // Attach the reducer and initial state to the global app object
    app.rootReducer = rootReducer;
    app.initialState = initialState;


})(window.NoiseSurveyApp);