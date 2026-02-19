// noise_survey_analysis/static/js/features/view/viewThunks.js

/**
 * @fileoverview Thunks responsible for view-level intents.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;
    const viewSelectors = app.features?.view?.selectors || {};

    function selectParameterIntent(parameter) {
        return function (dispatch) {
            if (typeof dispatch !== 'function' || !actions?.paramChange) {
                return;
            }
            dispatch(actions.paramChange(parameter));
            app.regions?.invalidateMetricsCache?.();
        };
    }

    function handleTabSwitchIntent(payload) {
        return function (dispatch, getState) {
            if (typeof dispatch !== 'function' || typeof getState !== 'function') {
                return;
            }

            const nextIndexRaw = payload?.newIndex;
            const nextIndex = Number.isFinite(nextIndexRaw) ? nextIndexRaw : Number(nextIndexRaw);
            const resolvedIndex = Number.isFinite(nextIndex) ? nextIndex : 0;

            const state = getState();
            const viewState = viewSelectors.selectViewState
                ? viewSelectors.selectViewState(state)
                : state?.view || {};
            const isComparisonModeActive = viewState.mode === 'comparison';

            if (resolvedIndex === 1) {
                const regionThunks = app.features?.regions?.thunks || {};
                const enterThunkCreator = regionThunks.enterComparisonModeIntent;
                if (typeof enterThunkCreator === 'function') {
                    dispatch(enterThunkCreator());
                }
                return;
            }

            if (isComparisonModeActive) {
                const regionThunks = app.features?.regions?.thunks || {};
                const exitThunkCreator = regionThunks.exitComparisonModeIntent;
                if (typeof exitThunkCreator === 'function') {
                    dispatch(exitThunkCreator());
                }
            }
        };
    }

    function hasAnyStaticLogData(models, positions) {
        if (!Array.isArray(positions) || !positions.length) {
            return false;
        }
        return positions.some(positionId => {
            const hasFlag = Boolean(models?.positionHasLogData?.[positionId]);
            const logData = models?.timeSeriesSources?.[positionId]?.log?.data;
            const hasLoadedData = Array.isArray(logData?.Datetime) && logData.Datetime.length > 0;
            return hasFlag || hasLoadedData;
        });
    }

    function handleViewportChangeIntent(payload) {
        return function (dispatch, getState) {
            if (typeof dispatch !== 'function' || typeof getState !== 'function') {
                return;
            }

            const min = Number(payload?.min);
            const max = Number(payload?.max);
            if (!Number.isFinite(min) || !Number.isFinite(max)) {
                return;
            }

            dispatch(actions.viewportChange(min, max));

            const models = app.registry?.models || {};
            const isServerMode = Boolean(models?.config?.server_mode);
            if (isServerMode) {
                return;
            }

            const state = getState();
            const viewState = viewSelectors.selectViewState
                ? viewSelectors.selectViewState(state)
                : state?.view || {};
            const positions = Array.isArray(viewState.availablePositions) ? viewState.availablePositions : [];

            if (!hasAnyStaticLogData(models, positions)) {
                return;
            }

            const resolution = app.features?.view?.resolution;
            const nextViewType = resolution?.determineViewportViewType
                ? resolution.determineViewportViewType(models, viewState, { min, max })
                : null;
            if (nextViewType !== 'log' && nextViewType !== 'overview') {
                return;
            }
            if (viewState.globalViewType !== nextViewType) {
                dispatch(actions.viewToggle(nextViewType));
            }
        };
    }

    app.features = app.features || {};
    app.features.view = app.features.view || {};
    app.features.view.thunks = {
        ...(app.features.view.thunks || {}),
        handleTabSwitchIntent,
        selectParameterIntent,
        handleViewportChangeIntent
    };
})(window.NoiseSurveyApp);
