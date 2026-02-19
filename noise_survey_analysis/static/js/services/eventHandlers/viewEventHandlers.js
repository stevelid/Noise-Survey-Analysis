// noise_survey_analysis/static/js/services/eventHandlers/viewEventHandlers.js

/**
 * @fileoverview View-focused event handlers (viewport, widgets, and visibility).
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const DEBOUNCE_DELAY = 200;

    function debounce(func, delay) {
        let timeout;
        return function (...args) {
            clearTimeout(timeout);
            timeout = setTimeout(() => func.apply(this, args), delay);
        };
    }

    const debouncedRangeUpdate = debounce((min, max) => {
        const thunkCreator = app.thunks && app.thunks.handleViewportChangeIntent;
        if (typeof thunkCreator === 'function') {
            app.store.dispatch(thunkCreator({ min, max }));
            return;
        }
        app.store.dispatch(app.actions.viewportChange(min, max));
    }, DEBOUNCE_DELAY);

    function handleRangeUpdate(cb_obj) {
        debouncedRangeUpdate(cb_obj.start, cb_obj.end);
    }

    function handleParameterChange(value) {
        const thunkCreator = app.thunks && app.thunks.selectParameterIntent;
        if (typeof thunkCreator === 'function') {
            app.store.dispatch(thunkCreator(value));
            return;
        }
        app.store.dispatch(app.actions.paramChange(value));
    }

    function handleViewToggle(isActive) {
        const newViewType = isActive ? 'log' : 'overview';
        app.store.dispatch(app.actions.viewToggle(newViewType));
    }

    function handleHoverToggle(isActive) {
        app.store.dispatch(app.actions.hoverToggle(isActive));
    }

    function handleVisibilityChange(cb_obj, chartName) {
        const isVisible = Array.isArray(cb_obj.active) ? cb_obj.active.includes(0) : Boolean(cb_obj.active);
        app.store.dispatch(app.actions.visibilityChange(chartName, isVisible));
    }

    function handleLogViewThresholdChange(value) {
        const resolution = app.features?.view?.resolution;
        const seconds = resolution?.minutesToSeconds
            ? resolution.minutesToSeconds(value)
            : Number(value) * 60;

        const nextThreshold = {
            mode: Number.isFinite(seconds) && seconds > 0 ? 'manual' : 'auto',
            seconds: Number.isFinite(seconds) && seconds > 0 ? seconds : null
        };

        const getState = app.store && app.store.getState;
        const state = typeof getState === 'function' ? getState() : null;
        const selectLogThreshold = app.features?.view?.selectors?.selectLogThreshold;
        const currentThreshold = (state && typeof selectLogThreshold === 'function')
            ? selectLogThreshold(state)
            : null;

        if (currentThreshold?.mode === 'auto'
            && nextThreshold.mode === 'manual'
            && Number.isFinite(nextThreshold.seconds)
            && resolution?.resolveLogThresholdSeconds) {
            const selectViewState = app.features?.view?.selectors?.selectViewState;
            const viewState = typeof selectViewState === 'function'
                ? selectViewState(state)
                : (state?.view || {});
            const autoSeconds = resolution.resolveLogThresholdSeconds(
                app.registry?.models || {},
                viewState
            );
            if (Number.isFinite(autoSeconds) && Math.abs(autoSeconds - nextThreshold.seconds) < 0.0001) {
                return;
            }
        }

        if (currentThreshold
            && currentThreshold.mode === nextThreshold.mode
            && currentThreshold.seconds === nextThreshold.seconds) {
            return;
        }

        app.store.dispatch(app.actions.logViewThresholdSet(nextThreshold));
    }

    app.services = app.services || {};
    app.services.eventHandlers = app.services.eventHandlers || {};
    app.services.eventHandlers.view = {
        handleRangeUpdate,
        handleParameterChange,
        handleViewToggle,
        handleHoverToggle,
        handleVisibilityChange,
        handleLogViewThresholdChange
    };
})(window.NoiseSurveyApp);
