// noise_survey_analysis/static/js/features/regions/regionThunks.js

/**
 * @fileoverview Thunks handling region and comparison workflows.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;
    const MIN_REGION_WIDTH_MS = 1;

    const viewSelectors = app.features?.view?.selectors || {};
    const regionSelectors = app.features?.regions?.selectors || {};

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
            const viewState = viewSelectors.selectViewState ? viewSelectors.selectViewState(state) : state?.view;
            if (!viewState || viewState.mode !== 'comparison') {
                return;
            }

            const rawStart = Number(payload?.start);
            const rawEnd = Number(payload?.end);
            const hasBounds = Number.isFinite(rawStart) && Number.isFinite(rawEnd) && rawStart !== rawEnd;

            const nextStart = hasBounds ? Math.min(rawStart, rawEnd) : null;
            const nextEnd = hasBounds ? Math.max(rawStart, rawEnd) : null;

            const currentComparison = viewSelectors.selectComparisonState
                ? viewSelectors.selectComparisonState(state)
                : viewState.comparison || {};

            if (currentComparison.start === nextStart && currentComparison.end === nextEnd) {
                return;
            }

            dispatch(actions.comparisonSliceUpdated(nextStart, nextEnd));
        };
    }

    function createRegionsFromComparisonIntent() {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') return;

            const state = getState();
            const viewState = viewSelectors.selectViewState ? viewSelectors.selectViewState(state) : state?.view || {};
            const comparisonState = viewSelectors.selectComparisonState ? viewSelectors.selectComparisonState(state) : viewState.comparison || {};

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
            if (!actions || typeof getState !== 'function') return;
            const { key, modifiers = {} } = payload || {};
            const direction = key === 'ArrowRight' ? 1 : key === 'ArrowLeft' ? -1 : 0;
            if (!direction) return;

            const state = getState();
            const regionsState = regionSelectors.selectRegionsState
                ? regionSelectors.selectRegionsState(state)
                : state?.regions;
            const selectedId = regionsState?.selectedId;
            if (!selectedId) return;
            const region = regionsState.byId[selectedId];
            if (!region) return;

            if (!modifiers.shift && !modifiers.alt) {
                return;
            }

            const stepSize = Number.isFinite(state?.interaction?.keyboard?.stepSizeMs)
                ? state.interaction.keyboard.stepSizeMs
                : 1000;
            const delta = direction * stepSize;
            const viewport = viewSelectors.selectViewport ? viewSelectors.selectViewport(state) : state?.view?.viewport || {};
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

    app.features = app.features || {};
    app.features.regions = app.features.regions || {};
    app.features.regions.thunks = {
        enterComparisonModeIntent,
        exitComparisonModeIntent,
        updateIncludedPositionsIntent,
        updateComparisonSliceIntent,
        createRegionsFromComparisonIntent,
        createRegionIntent,
        resizeSelectedRegionIntent
    };
})(window.NoiseSurveyApp);
