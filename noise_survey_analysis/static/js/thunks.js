// noise_survey_analysis/static/js/thunks.js

/**
 * @fileoverview Defines thunk/intents responsible for handling higher-level UI intents
 * that require access to application state. These functions interpret normalised event
 * payloads and dispatch semantic actions.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;
    const MIN_REGION_WIDTH_MS = 1;

    function enterComparisonModeIntent() {
        return function (dispatch) {
            if (!actions) return;
            dispatch(actions.comparisonModeEntered());
        };
    }

    function exitComparisonModeIntent() {
        return function (dispatch) {
            if (!actions) return;
            dispatch(actions.comparisonModeExited());
        };
    }

    function updateIncludedPositionsIntent(payload) {
        return function (dispatch) {
            if (!actions) return;
            const includedPositions = Array.isArray(payload?.includedPositions)
                ? payload.includedPositions
                : [];
            dispatch(actions.comparisonPositionsUpdated(includedPositions));
        };
    }

    function updateComparisonSliceIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') return;

            const state = getState();
            if (state?.view?.mode !== 'comparison') {
                return;
            }

            const rawStart = Number(payload?.start);
            const rawEnd = Number(payload?.end);
            const hasBounds = Number.isFinite(rawStart) && Number.isFinite(rawEnd) && rawStart !== rawEnd;

            const nextStart = hasBounds ? Math.min(rawStart, rawEnd) : null;
            const nextEnd = hasBounds ? Math.max(rawStart, rawEnd) : null;

            const currentStart = state.view.comparison.start;
            const currentEnd = state.view.comparison.end;

            if (currentStart === nextStart && currentEnd === nextEnd) {
                return;
            }

            dispatch(actions.comparisonSliceUpdated(nextStart, nextEnd));
        };
    }

    function createRegionsFromComparisonIntent() {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') return;

            const state = getState();
            const viewState = state?.view || {};
            const comparisonState = viewState.comparison || {};

            if (viewState.mode !== 'comparison' || !comparisonState.isActive) {
                return;
            }

            const rawStart = Number(comparisonState.start);
            const rawEnd = Number(comparisonState.end);
            if (!Number.isFinite(rawStart) || !Number.isFinite(rawEnd) || rawStart === rawEnd) {
                return;
            }

            const start = Math.min(rawStart, rawEnd);
            const end = Math.max(rawStart, rawEnd);

            const includedPositions = Array.isArray(comparisonState.includedPositions)
                ? comparisonState.includedPositions
                : [];

            if (!includedPositions.length) {
                return;
            }

            const regions = includedPositions
                .filter(positionId => typeof positionId === 'string' && positionId)
                .map(positionId => ({ positionId, start, end }));

            if (!regions.length) {
                return;
            }

            dispatch(actions.regionsAdded(regions));
            dispatch(actions.comparisonModeExited());
        };
    }

    function findRegionByTimestamp(state, positionId, timestamp) {
        const regionsState = state?.markers?.regions;
        if (!regionsState || !positionId || !Number.isFinite(timestamp)) return null;
        const { byId, allIds } = regionsState;
        for (let i = allIds.length - 1; i >= 0; i--) {
            const region = byId[allIds[i]];
            if (!region || region.positionId !== positionId) continue;
            if (timestamp >= region.start && timestamp <= region.end) {
                return region;
            }
        }
        return null;
    }

    function handleTapIntent(payload) {
        return function (dispatch, getState) {
            if (!actions) return;
            const { timestamp, positionId, chartName, modifiers = {} } = payload || {};
            if (!Number.isFinite(timestamp) || !positionId || !chartName) return;

            const state = getState();
            const regionHit = findRegionByTimestamp(state, positionId, timestamp);
            const isCtrl = Boolean(modifiers.ctrl);
            const isShift = Boolean(modifiers.shift);

            //No action on shift + tap
            if (isShift){
                //making a new region between the existing tap point and the new tap point
                if(!state.interaction.tap.isActive) return;
                const prevoiusTapPoint = state.interaction.tap.timestamp;
                if(!Number.isFinite(prevoiusTapPoint)) return;
                
                const start = Math.min(prevoiusTapPoint, timestamp);
                const end = Math.max(prevoiusTapPoint, timestamp);
                if(Math.abs(end - start) < MIN_REGION_WIDTH_MS) return;
                
                dispatch(actions.regionAdd(positionId, start, end));                
            };
            
            if (isCtrl && regionHit) {
                dispatch(actions.regionRemove(regionHit.id));
                return;
            }

            if (regionHit) {
                dispatch(actions.regionSelect(regionHit.id));
            } else {
                dispatch(actions.regionClearSelection());
            }

            if (isCtrl) {
                dispatch(actions.removeMarker(timestamp));
                return;
            }

            dispatch(actions.tap(timestamp, positionId, chartName));
        };
    }

    function createRegionIntent(payload) {
        return function (dispatch) {
            if (!actions) return;
            const { positionId, start, end } = payload || {};
            if (!positionId || !Number.isFinite(start) || !Number.isFinite(end)) return;
            if (Math.abs(end - start) < MIN_REGION_WIDTH_MS) return;

            dispatch(actions.regionAdd(positionId, start, end));
        };
    }

    function resizeSelectedRegionIntent(payload) {
        return function (dispatch, getState) {
            if (!actions) return;
            const { key, modifiers = {} } = payload || {};
            const direction = key === 'ArrowRight' ? 1 : key === 'ArrowLeft' ? -1 : 0;
            if (!direction) return;

            const state = getState();
            const selectedId = state?.markers?.regions?.selectedId;
            if (!selectedId) return;
            const region = state.markers.regions.byId[selectedId];
            if (!region) return;

            if (!modifiers.shift && !modifiers.alt) {
                return;
            }

            const stepSize = Number.isFinite(state?.interaction?.keyboard?.stepSizeMs)
                ? state.interaction.keyboard.stepSizeMs
                : 1000;
            const delta = direction * stepSize;
            const viewport = state?.view?.viewport || {};
            const viewportMin = Number.isFinite(viewport.min) ? viewport.min : -Infinity;
            const viewportMax = Number.isFinite(viewport.max) ? viewport.max : Infinity;

            if (modifiers.shift) {
                const rawEnd = region.end + delta;
                const minEnd = region.start + MIN_REGION_WIDTH_MS;
                const clampedEnd = Math.min(Math.max(minEnd, rawEnd), viewportMax);
                if (clampedEnd !== region.end) {
                    dispatch(actions.regionUpdate(region.id, { end: clampedEnd }));
                }
                return;
            }

            if (modifiers.alt) {
                const rawStart = region.start + delta;
                const maxStart = region.end - MIN_REGION_WIDTH_MS;
                const clampedStart = Math.max(Math.min(maxStart, rawStart), viewportMin);
                if (clampedStart !== region.start) {
                    dispatch(actions.regionUpdate(region.id, { start: clampedStart }));
                }
            }
        };
    }

    function nudgeTapLineIntent(payload) {
        return function (dispatch) {
            if (!actions) return;
            const { key } = payload || {};
            if (key !== 'ArrowLeft' && key !== 'ArrowRight') return;
            const direction = key === 'ArrowLeft' ? 'left' : 'right';
            dispatch(actions.keyNav(direction));
        };
    }

    function togglePlayPauseIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') return;

            const positionId = typeof payload?.positionId === 'string' ? payload.positionId : null;
            const isActive = typeof payload?.isActive === 'boolean' ? payload.isActive : null;
            if (!positionId || isActive === null) {
                return;
            }

            const state = getState();
            const audioState = state?.audio;
            if (!audioState) {
                return;
            }

            const { isPlaying, activePositionId } = audioState;

            if (isActive) {
                if (isPlaying && activePositionId === positionId) {
                    return;
                }
            } else {
                if (!isPlaying || activePositionId !== positionId) {
                    return;
                }
            }

            dispatch(actions.audioPlayPauseToggle(positionId, isActive));
        };
    }

    function changePlaybackRateIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') return;

            const positionId = typeof payload?.positionId === 'string' ? payload.positionId : null;
            if (!positionId) {
                return;
            }

            const state = getState();
            const audioState = state?.audio;
            if (!audioState || audioState.activePositionId !== positionId) {
                return;
            }

            const requestedRate = Number(payload?.playbackRate);
            if (Number.isFinite(requestedRate) && requestedRate === audioState.playbackRate) {
                return;
            }

            dispatch(actions.audioRateChangeRequest(positionId));
        };
    }

    function toggleVolumeBoostIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') return;

            const positionId = typeof payload?.positionId === 'string' ? payload.positionId : null;
            const isBoostActive = typeof payload?.isBoostActive === 'boolean' ? payload.isBoostActive : null;
            if (!positionId || isBoostActive === null) {
                return;
            }

            const state = getState();
            const audioState = state?.audio;
            if (!audioState || audioState.activePositionId !== positionId) {
                return;
            }

            if (audioState.volumeBoost === isBoostActive) {
                return;
            }

            dispatch(actions.audioBoostToggleRequest(positionId, isBoostActive));
        };
    }

    app.thunks = {
        enterComparisonModeIntent,
        exitComparisonModeIntent,
        updateIncludedPositionsIntent,
        updateComparisonSliceIntent,
        createRegionsFromComparisonIntent,
        handleTapIntent,
        createRegionIntent,
        resizeSelectedRegionIntent,
        nudgeTapLineIntent,
        togglePlayPauseIntent,
        changePlaybackRateIntent,
        toggleVolumeBoostIntent
    };
})(window.NoiseSurveyApp);
