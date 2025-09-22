// noise_survey_analysis/static/js/features/interaction/interactionThunks.js

/**
 * @fileoverview Thunks for handling interaction-driven intents.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;
    const regionSelectors = app.features?.regions?.selectors || {};
    const MIN_REGION_WIDTH_MS = 1;

    function handleTapIntent(payload) {
        return function (dispatch, getState) {
            if (!actions) return;
            const { timestamp, positionId, chartName, modifiers = {} } = payload || {};
            if (!Number.isFinite(timestamp) || !positionId || !chartName) return;

            const state = getState();
            const regionHit = regionSelectors.selectRegionByTimestamp
                ? regionSelectors.selectRegionByTimestamp(state, positionId, timestamp)
                : null;
            const isCtrl = Boolean(modifiers.ctrl);
            const isShift = Boolean(modifiers.shift);

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
                dispatch(actions.removeMarker(timestamp));
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
