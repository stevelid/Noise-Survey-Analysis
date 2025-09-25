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
                const markersForPosition = typeof markerSelectors.selectMarkersByPosition === 'function'
                    ? markerSelectors.selectMarkersByPosition(state, positionId)
                    : [];

                if (markersForPosition.length) {
                    let closestMarker = null;
                    let smallestDistance = Infinity;
                    markersForPosition.forEach(marker => {
                        const markerTimestamp = Number(marker?.timestamp);
                        if (!Number.isFinite(markerTimestamp)) {
                            return;
                        }
                        const distance = Math.abs(markerTimestamp - timestamp);
                        if (distance < smallestDistance) {
                            smallestDistance = distance;
                            closestMarker = marker;
                        }
                    });

                    if (closestMarker && smallestDistance <= markerThreshold) {
                        dispatch(actions.markerSelect(closestMarker.id));
                        dispatch(actions.tap(closestMarker.timestamp, positionId, chartName));
                        return;
                    }
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
                dispatch(actions.regionSelect(regionHit.id));
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
        nudgeTapLineIntent
    };
})(window.NoiseSurveyApp);
