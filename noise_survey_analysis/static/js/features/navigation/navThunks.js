// noise_survey_analysis/static/js/features/navigation/navThunks.js

/**
 * @fileoverview Keyboard / wheel navigation intents: zoom, pan, fit, zoom to region, position focus,
 * spectrogram modes, solo, y mode. Merged into app.features.layout.thunks (so thunks.js exposes them
 * on app.thunks). All viewport changes are clamped to the master x range here, because setting a
 * range from code bypasses the tools' own clamping.
 *
 * Position focus is UI-only state (which position the keys act on), kept in app.layoutRuntime
 * rather than the store so the layout slice shape stays unchanged.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const math = () => app.layoutMath;

    const runtime = app.layoutRuntime = app.layoutRuntime || {
        focusedPositionId: null,
        focusListeners: []
    };

    runtime.setFocus = function setFocus(positionId) {
        if (runtime.focusedPositionId === positionId) return;
        runtime.focusedPositionId = positionId;
        runtime.focusListeners.forEach(listener => {
            try { listener(positionId); } catch (error) { console.error('[Layout] focus listener failed', error); }
        });
    };

    function orderedPositions(state) {
        const available = state?.view?.availablePositions || [];
        return app.features.layout.selectors.selectOrderedPositions(state, available);
    }

    /** The position the keys act on: explicit focus, else the tapped / audio position, else the first. */
    runtime.resolveFocus = function resolveFocus(state) {
        const order = orderedPositions(state);
        const candidates = [runtime.focusedPositionId, state?.interaction?.tap?.position, state?.audio?.activePositionId];
        for (const candidate of candidates) {
            if (candidate && order.includes(candidate)) return candidate;
        }
        return order[0] || null;
    };

    /** Master x range limits: {bounds:{min,max}|null, minInterval}. */
    function getRangeLimits() {
        const range = app.registry?.models?.charts?.[0]?.x_range;
        const raw = range?.bounds;
        let bounds = null;
        if (Array.isArray(raw) && Number.isFinite(raw[0]) && Number.isFinite(raw[1])) {
            bounds = { min: raw[0], max: raw[1] };
        } else if (raw && Number.isFinite(raw.start) && Number.isFinite(raw.end)) {
            bounds = { min: raw.start, max: raw.end };
        }
        const minInterval = Number.isFinite(range?.min_interval) ? range.min_interval : 1000;
        return { bounds, minInterval };
    }

    function currentViewport(state) {
        const viewport = state?.view?.viewport;
        if (Number.isFinite(viewport?.min) && Number.isFinite(viewport?.max) && viewport.min < viewport.max) {
            return { min: viewport.min, max: viewport.max };
        }
        const range = app.registry?.models?.charts?.[0]?.x_range;
        if (Number.isFinite(range?.start) && Number.isFinite(range?.end)) {
            return { min: range.start, max: range.end };
        }
        return null;
    }

    function commitViewport(dispatch, next) {
        if (!next || !(next.min < next.max)) return;
        dispatch(app.thunks.handleViewportChangeIntent({ min: next.min, max: next.max }));
    }

    /** factor < 1 zooms in. Anchor defaults to the tap line when it is inside the window. */
    function zoomIntent({ factor = 0.5, anchor } = {}) {
        return (dispatch, getState) => {
            const state = getState();
            const viewport = currentViewport(state);
            if (!viewport) return;
            const tap = state?.interaction?.tap;
            const pivot = Number.isFinite(anchor) ? anchor : (tap?.isActive ? tap.timestamp : undefined);
            const { bounds, minInterval } = getRangeLimits();
            const next = math().zoomRange(viewport, factor, pivot, bounds, minInterval);
            if (next.min !== viewport.min || next.max !== viewport.max) commitViewport(dispatch, next);
        };
    }

    function panIntent({ fraction = 0.25 } = {}) {
        return (dispatch, getState) => {
            const viewport = currentViewport(getState());
            if (!viewport) return;
            const { bounds, minInterval } = getRangeLimits();
            const next = math().panRange(viewport, fraction, bounds, minInterval);
            if (next.min !== viewport.min || next.max !== viewport.max) commitViewport(dispatch, next);
        };
    }

    function fitAllIntent() {
        return (dispatch) => {
            const { bounds } = getRangeLimits();
            if (bounds) commitViewport(dispatch, { min: bounds.min, max: bounds.max });
        };
    }

    function zoomToSelectedRegionIntent() {
        return (dispatch, getState) => {
            const state = getState();
            const region = app.features?.regions?.selectors?.selectSelectedRegion?.(state);
            if (!region) {
                dispatch(app.actions.noticeShown('Select a region first (then Z zooms to it).', 'info'));
                return;
            }
            const areas = app.features.regions.selectors.getRegionAreas?.(region) || [region];
            const extent = math().paddedExtent(areas, 0.1);
            if (!extent) return;
            const { bounds, minInterval } = getRangeLimits();
            const next = math().clampRange(extent.min, extent.max, bounds, minInterval);
            // regionViewportCentered records the previous window so B returns to it.
            dispatch(app.actions.regionViewportCentered(next.min, next.max));
        };
    }

    function scrollPositionIntoView(positionId) {
        const layout = app.registry?.models?.positionLayouts?.[positionId];
        if (!layout || !window.Bokeh?.index) return;
        try {
            const view = window.Bokeh.index.find_one ? window.Bokeh.index.find_one(layout) : null;
            view?.el?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' });
        } catch (error) {
            // Cosmetic only.
        }
    }

    /** Up / Down: focus the previous / next position and scroll it into view. */
    function focusPositionIntent({ delta = 1 } = {}) {
        return (dispatch, getState) => {
            const state = getState();
            const order = orderedPositions(state);
            const index = math().stepIndex(order.length, order.indexOf(runtime.resolveFocus(state)), delta);
            if (index < 0) return;
            runtime.setFocus(order[index]);
            scrollPositionIntoView(order[index]);
        };
    }

    /** Alt+Up / Alt+Down: move the focused position. */
    function moveFocusedPositionIntent({ delta = 1 } = {}) {
        return (dispatch, getState) => {
            const positionId = runtime.resolveFocus(getState());
            if (!positionId) return;
            dispatch(app.thunks.movePositionIntent({ positionId, delta }));
            runtime.setFocus(positionId);
            scrollPositionIntoView(positionId);
        };
    }

    /** Header chevron: full <-> strip (hidden goes back to full). */
    function cycleSpectrogramModeIntent({ positionId } = {}) {
        return (dispatch, getState) => {
            const state = getState();
            const id = positionId || runtime.resolveFocus(state);
            if (!id) return;
            const current = app.features.layout.selectors.selectSpectrogramMode(state, id);
            dispatch(app.actions.layoutSpectrogramModeSet(id, math().cycleSpectrogramMode(current)));
        };
    }

    /** Shift+S: every position gets the mode the focused one is about to take. */
    function cycleAllSpectrogramModesIntent() {
        return (dispatch, getState) => {
            const state = getState();
            const focused = runtime.resolveFocus(state);
            if (!focused) return;
            const current = app.features.layout.selectors.selectSpectrogramMode(state, focused);
            const next = math().cycleSpectrogramMode(current);
            orderedPositions(state).forEach(id => dispatch(app.actions.layoutSpectrogramModeSet(id, next)));
        };
    }

    function cycleYAxisModeIntent() {
        return (dispatch, getState) => {
            const mode = app.features.layout.selectors.selectYAxisMode(getState());
            dispatch(app.actions.layoutYAxisModeSet(math().cycleYMode(mode)));
        };
    }

    function toggleWheelZoomLockIntent() {
        return (dispatch, getState) => {
            dispatch(app.actions.layoutWheelZoomLockSet(!app.features.layout.selectors.selectWheelZoomLock(getState())));
        };
    }

    function toggleFrequencyDockIntent() {
        return (dispatch, getState) => {
            dispatch(app.actions.layoutFrequencyDockOpenSet(!app.features.layout.selectors.selectFrequencyDockOpen(getState())));
        };
    }

    /** O: show only the focused position; pressing again restores the previous visibility. */
    function soloPositionIntent() {
        return (dispatch, getState) => {
            const state = getState();
            const soloType = app.features.layout.constants.LAYOUT_SOLO_SAVED_SET;
            const saved = state?.layout?.soloSaved;
            if (saved) {
                // The restore state lives in the (autosaved) layout slice, so O still undoes a solo after a reload.
                Object.keys(saved).forEach(name => dispatch(app.actions.visibilityChange(name, saved[name])));
                dispatch({ type: soloType, payload: { saved: null } });
                return;
            }
            const focused = runtime.resolveFocus(state);
            if (!focused) return;
            const visibility = state?.view?.chartVisibility || {};
            dispatch({ type: soloType, payload: { saved: { ...visibility } } });
            Object.keys(visibility).forEach(name => {
                const keep = name === `figure_${focused}_timeseries` || name === `figure_${focused}_spectrogram`;
                if (!keep && visibility[name]) dispatch(app.actions.visibilityChange(name, false));
            });
        };
    }

    app.features = app.features || {};
    app.features.layout = app.features.layout || {};
    app.features.navigation = { getRangeLimits };
    app.features.layout.thunks = {
        ...(app.features.layout.thunks || {}),
        zoomIntent,
        panIntent,
        fitAllIntent,
        zoomToSelectedRegionIntent,
        focusPositionIntent,
        moveFocusedPositionIntent,
        cycleSpectrogramModeIntent,
        cycleAllSpectrogramModesIntent,
        cycleYAxisModeIntent,
        toggleWheelZoomLockIntent,
        toggleFrequencyDockIntent,
        soloPositionIntent
    };
})(window.NoiseSurveyApp);
