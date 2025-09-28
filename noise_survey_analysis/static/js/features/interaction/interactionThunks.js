// noise_survey_analysis/static/js/features/interaction/interactionThunks.js

/**
 * @fileoverview Thunks for handling interaction-driven intents.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;
    const regionSelectors = app.features?.regions?.selectors || {};
    const markerSelectors = app.features?.markers?.selectors || {};
    const viewSelectors = app.features?.view?.selectors || {};
    const MIN_REGION_WIDTH_MS = 1;
    const MARKER_HIT_RATIO = 0.02;
    const MARKER_MIN_THRESHOLD_MS = 1000;

    function handleTapIntent(payload) {
        return function (dispatch, getState) {
            if (!actions) return;
            const { timestamp, positionId, chartName, modifiers = {} } = payload || {};
            if (!Number.isFinite(timestamp) || !positionId || !chartName) return;

            const state = getState();
            const isCtrl = Boolean(modifiers.ctrl);
            const isShift = Boolean(modifiers.shift);

            const viewport = typeof viewSelectors.selectViewport === 'function'
                ? viewSelectors.selectViewport(state)
                : state?.view?.viewport || {};
            const viewportWidth = Number(viewport?.max) - Number(viewport?.min) || 0;
            const markerThreshold = Math.max(Math.abs(viewportWidth) * MARKER_HIT_RATIO, MARKER_MIN_THRESHOLD_MS);

            if (!isShift && !isCtrl) {
                //select nearest marker
                const { marker: closestMarker, distance } =
                    typeof markerSelectors.selectClosestMarkerToTimestamp === 'function'
                        ? markerSelectors.selectClosestMarkerToTimestamp(state, timestamp, positionId)
                        : { marker: null, distance: Infinity };

                if (closestMarker && distance <= markerThreshold) {
                    const selectMarkerThunk = app.features?.markers?.thunks?.selectMarkerIntent;
                    if (typeof selectMarkerThunk === 'function') {
                        dispatch(selectMarkerThunk(closestMarker.id));
                    }

                    // This is the shared logic from both branches.
                    dispatch(actions.tap(closestMarker.timestamp, positionId, chartName));
                    return;
                }
            }

            const regionHit = regionSelectors.selectRegionByTimestamp
                ? regionSelectors.selectRegionByTimestamp(state, positionId, timestamp)
                : null;

            if (isShift) {
                if (!state?.interaction?.tap?.isActive) return;
                const previousTap = state.interaction.tap.timestamp;
                if (!Number.isFinite(previousTap)) return;

                const start = Math.min(previousTap, timestamp);
                const end = Math.max(previousTap, timestamp);
                if (Math.abs(end - start) < MIN_REGION_WIDTH_MS) return;

                dispatch(actions.regionAdd(positionId, start, end));
            }

            if (isCtrl && regionHit) {
                const areas = Array.isArray(regionHit.areas) ? regionHit.areas : [];
                const targetIndex = areas.findIndex(area => {
                    if (!area) return false;
                    const areaStart = Number(area.start);
                    const areaEnd = Number(area.end);
                    if (!Number.isFinite(areaStart) || !Number.isFinite(areaEnd)) {
                        return false;
                    }
                    return timestamp >= areaStart && timestamp <= areaEnd;
                });

                if (areas.length <= 1 || targetIndex === -1) {
                    dispatch(actions.regionRemove(regionHit.id));
                } else {
                    const nextAreas = areas.filter((_, index) => index !== targetIndex);
                    dispatch(actions.regionUpdate(regionHit.id, { areas: nextAreas }));
                }
                return;
            }

            if (regionHit) {
                const selectRegionThunk = app.features?.regions?.thunks?.selectRegionIntent;
                if (typeof selectRegionThunk === 'function') {
                    dispatch(selectRegionThunk(regionHit.id));
                } else {
                    dispatch(actions.regionSelect(regionHit.id));
                    if (typeof actions.markerSelect === 'function') {
                        dispatch(actions.markerSelect(null));
                    }
                }
            } else {
                dispatch(actions.regionClearSelection());
            }

            if (isCtrl) {
                const { marker, distance } = typeof markerSelectors.selectClosestMarkerToTimestamp === 'function'
                    ? markerSelectors.selectClosestMarkerToTimestamp(state, timestamp, positionId)
                    : { marker: null, distance: Infinity };

                if (marker && distance <= Math.max(markerThreshold, MARKER_MIN_THRESHOLD_MS) && typeof actions.markerRemove === 'function') {
                    dispatch(actions.markerRemove(marker.id));
                }
                return;
            }

            dispatch(actions.tap(timestamp, positionId, chartName));
        };
    }

    function handleKeyboardShortcutIntent(payload) {
        return function (dispatch, getState) {
            if (!actions) return;

            const rawKey = typeof payload?.key === 'string' ? payload.key : '';
            const code = typeof payload?.code === 'string' ? payload.code : '';
            const normalizedKey = rawKey.toLowerCase();
            const ctrlKey = Boolean(payload?.ctrlKey);
            const altKey = Boolean(payload?.altKey);

            const thunks = app.thunks || {};

            if (code === 'Space' || rawKey === ' ' || rawKey === 'Spacebar') {
                const toggleThunk = thunks.togglePlaybackFromKeyboardIntent;
                if (typeof toggleThunk !== 'function') {
                    console.error('[InteractionThunk] Missing togglePlaybackFromKeyboardIntent thunk.');
                    return;
                }
                dispatch(toggleThunk());
                return;
            }

            if (rawKey === 'Escape') {
                if (typeof actions.regionCreationCancelled === 'function') {
                    dispatch(actions.regionCreationCancelled());
                }
                return;
            }

            if (normalizedKey === 'm') {
                const markerThunk = thunks.createMarkerIntent;
                if (typeof markerThunk !== 'function') {
                    console.error('[InteractionThunk] Missing marker creation thunk.');
                    return;
                }
                console.log('[InteractionThunk] dispatching createMarkerIntent'); // DEBUG
                dispatch(markerThunk({}));
                return;
            }

            if (normalizedKey === 'r') {
                const toggleRegionThunk = thunks.toggleRegionCreationIntent;
                if (typeof toggleRegionThunk !== 'function') {
                    console.error('[InteractionThunk] Missing toggleRegionCreationIntent thunk.');
                    return;
                }
                dispatch(toggleRegionThunk());
                return;
            }

            if (rawKey !== 'ArrowLeft' && rawKey !== 'ArrowRight') {
                return;
            }

            if (ctrlKey || altKey) {
                const state = typeof getState === 'function' ? getState() : null;
                const selectedMarker = state && typeof markerSelectors.selectSelectedMarker === 'function'
                    ? markerSelectors.selectSelectedMarker(state)
                    : null;

                if (ctrlKey && selectedMarker) {
                    const nudgeMarkerThunk = thunks.nudgeSelectedMarkerIntent;
                    if (typeof nudgeMarkerThunk !== 'function') {
                        console.error('[InteractionThunk] Missing nudgeSelectedMarkerIntent thunk.');
                        return;
                    }
                    dispatch(nudgeMarkerThunk({ key: rawKey }));
                    return;
                }

                const resizeRegionThunk = thunks.resizeSelectedRegionIntent;
                if (typeof resizeRegionThunk !== 'function') {
                    console.error('[InteractionThunk] Missing resizeSelectedRegionIntent thunk.');
                    return;
                }

                const modifiers = {};
                if (ctrlKey) {
                    modifiers.ctrl = true;
                }
                if (altKey) {
                    modifiers.alt = true;
                }

                dispatch(resizeRegionThunk({
                    key: rawKey,
                    modifiers
                }));
                return;
            }

            const nudgeTapThunk = thunks.nudgeTapLineIntent;
            if (typeof nudgeTapThunk !== 'function') {
                console.error('[InteractionThunk] Missing nudgeTapLineIntent thunk.');
                return;
            }

            dispatch(nudgeTapThunk({ key: rawKey }));
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

    app.features = app.features || {};
    app.features.interaction = app.features.interaction || {};
    app.features.interaction.thunks = {
        handleTapIntent,
        handleKeyboardShortcutIntent,
        nudgeTapLineIntent
    };
})(window.NoiseSurveyApp);
