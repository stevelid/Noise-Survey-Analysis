// noise_survey_analysis/static/js/core/rootReducer.js

/**
 * @fileoverview Root reducer that orchestrates feature reducers.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const markerSelectionActionTypes = new Set([
        actionTypes.MARKER_ADDED,
        actionTypes.MARKER_SELECTED,
        actionTypes.MARKERS_REPLACED
    ]);

    const regionSelectionActionTypes = new Set([
        actionTypes.REGION_ADDED,
        actionTypes.REGIONS_ADDED,
        actionTypes.REGION_SELECTED,
        actionTypes.REGIONS_REPLACED
    ]);

    function normalizeSelectedId(value) {
        return Number.isFinite(value) ? value : null;
    }

    const viewFeature = app.features?.view || {};
    const interactionFeature = app.features?.interaction || {};
    const markersFeature = app.features?.markers || {};
    const regionsFeature = app.features?.regions || {};
    const audioFeature = app.features?.audio || {};

    const initialSystemState = {
        initialized: false,
        lastAction: null
    };

    function deepClone(value) {
        return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
    }

    function createInitialState() {
        return {
            view: deepClone(viewFeature.initialState),
            interaction: deepClone(interactionFeature.initialState),
            markers: deepClone(markersFeature.initialState),
            regions: deepClone(regionsFeature.initialState),
            audio: deepClone(audioFeature.initialState),
            system: deepClone(initialSystemState)
        };
    }

    function systemReducer(state = initialSystemState, action) {
        switch (action.type) {
            case actionTypes.INITIALIZE_STATE:
                return {
                    ...state,
                    initialized: true
                };

            default:
                return state;
        }
    }

    function rootReducer(state, action) {
        const previousState = state ?? createInitialState();

        if (action.type === actionTypes.STATE_REHYDRATED) {
            const providedState = action?.payload?.state;
            if (!providedState || typeof providedState !== 'object') {
                console.error('[RootReducer] STATE_REHYDRATED dispatched without a valid state payload.');
                return previousState;
            }

            const baseState = createInitialState();

            let mergedState = {
                view: providedState.view ? { ...baseState.view, ...providedState.view } : baseState.view,
                interaction: providedState.interaction ? { ...baseState.interaction, ...providedState.interaction } : baseState.interaction,
                markers: providedState.markers ? { ...baseState.markers, ...providedState.markers } : baseState.markers,
                regions: providedState.regions ? { ...baseState.regions, ...providedState.regions } : baseState.regions,
                audio: providedState.audio ? { ...baseState.audio, ...providedState.audio } : baseState.audio,
                system: { ...baseState.system, ...(providedState.system || {}), initialized: true },
            };

            const rehydratedMarkerSelected = normalizeSelectedId(mergedState?.markers?.selectedId);
            const rehydratedRegionSelected = normalizeSelectedId(mergedState?.regions?.selectedId);

            if (rehydratedMarkerSelected !== null && rehydratedRegionSelected !== null) {
                const lastActionType = providedState?.system?.lastAction?.type;
                const prefersMarker = markerSelectionActionTypes.has(lastActionType);
                const prefersRegion = regionSelectionActionTypes.has(lastActionType);

                let preferredSlice = null;
                if (prefersMarker && !prefersRegion) {
                    preferredSlice = 'marker';
                } else if (prefersRegion && !prefersMarker) {
                    preferredSlice = 'region';
                } else if (prefersRegion) {
                    preferredSlice = 'region';
                } else if (prefersMarker) {
                    preferredSlice = 'marker';
                } else {
                    preferredSlice = 'region';
                }

                if (preferredSlice === 'marker') {
                    mergedState = {
                        ...mergedState,
                        regions: {
                            ...mergedState.regions,
                            selectedId: null,
                            isMergeModeActive: false,
                        }
                    };
                } else {
                    mergedState = {
                        ...mergedState,
                        markers: {
                            ...mergedState.markers,
                            selectedId: null,
                        }
                    };
                }
            }

            return {
                ...mergedState,
                system: {
                    ...mergedState.system,
                    lastAction: action,
                },
            };
        }

        const nextView = typeof viewFeature.viewReducer === 'function'
            ? viewFeature.viewReducer(previousState.view, action)
            : previousState.view;

        const nextInteraction = typeof interactionFeature.interactionReducer === 'function'
            ? interactionFeature.interactionReducer(previousState.interaction, action, previousState)
            : previousState.interaction;

        const nextMarkers = typeof markersFeature.markersReducer === 'function'
            ? markersFeature.markersReducer(previousState.markers, action, previousState)
            : previousState.markers;

        const nextRegions = typeof regionsFeature.regionsReducer === 'function'
            ? regionsFeature.regionsReducer(previousState.regions, action)
            : previousState.regions;

        const nextAudio = typeof audioFeature.audioReducer === 'function'
            ? audioFeature.audioReducer(previousState.audio, action)
            : previousState.audio;

        const nextSystem = systemReducer(previousState.system, action);

        const prevMarkerSelected = normalizeSelectedId(previousState?.markers?.selectedId);
        const prevRegionSelected = normalizeSelectedId(previousState?.regions?.selectedId);
        const nextMarkerSelected = normalizeSelectedId(nextMarkers?.selectedId);
        const nextRegionSelected = normalizeSelectedId(nextRegions?.selectedId);

        const markerSelectionChanged = nextMarkerSelected !== null && nextMarkerSelected !== prevMarkerSelected;
        const regionSelectionChanged = nextRegionSelected !== null && nextRegionSelected !== prevRegionSelected;

        let markersResult = nextMarkers;
        let regionsResult = nextRegions;

        let preferredSelection = null;
        if (markerSelectionActionTypes.has(action.type)) {
            preferredSelection = 'marker';
        } else if (regionSelectionActionTypes.has(action.type)) {
            preferredSelection = 'region';
        } else if (regionSelectionChanged && !markerSelectionChanged) {
            preferredSelection = 'region';
        } else if (markerSelectionChanged && !regionSelectionChanged) {
            preferredSelection = 'marker';
        } else if (regionSelectionChanged) {
            preferredSelection = 'region';
        } else if (markerSelectionChanged) {
            preferredSelection = 'marker';
        }

        if (preferredSelection === 'marker' && nextMarkerSelected !== null && nextRegionSelected !== null) {
            regionsResult = {
                ...nextRegions,
                selectedId: null,
                isMergeModeActive: false
            };
        } else if (preferredSelection === 'region' && nextRegionSelected !== null && nextMarkerSelected !== null) {
            markersResult = {
                ...nextMarkers,
                selectedId: null
            };
        }

        const finalMarkerSelected = normalizeSelectedId(markersResult?.selectedId);
        const finalRegionSelected = normalizeSelectedId(regionsResult?.selectedId);
        if (finalMarkerSelected !== null && finalRegionSelected !== null) {
            if (preferredSelection === 'marker') {
                regionsResult = {
                    ...regionsResult,
                    selectedId: null,
                    isMergeModeActive: false
                };
            } else {
                markersResult = {
                    ...markersResult,
                    selectedId: null
                };
            }
        }

        const combinedState = {
            view: nextView,
            interaction: nextInteraction,
            markers: markersResult,
            regions: regionsResult,
            audio: nextAudio,
            system: nextSystem
        };

        return {
            ...combinedState,
            system: {
                ...combinedState.system,
                lastAction: action
            }
        };
    }

    const initialState = createInitialState();

    app.rootReducer = rootReducer;
    app.initialState = initialState;
    app.createInitialState = createInitialState;
})(window.NoiseSurveyApp);
