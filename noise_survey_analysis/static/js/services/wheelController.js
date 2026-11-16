// noise_survey_analysis/static/js/services/wheelController.js

/**
 * @fileoverview Wheel scheme for the charts.
 *
 *   - The wheel zooms when the page does not scroll, or Ctrl/Meta is held, or the user locked it (W).
 *   - Otherwise the wheel scrolls the page (the chart never sees the event).
 *   - Shift + wheel pans the time axis.
 *
 * Bokeh 3.4.1 has no modifier option on WheelZoomTool, so instead of swapping toolbar.active_scroll
 * this listens in the capture phase on the window and stops events that must not reach the tool.
 * The tool stays active and calls preventDefault itself when it handles a wheel event, which is also
 * what keeps Ctrl+wheel from zooming the browser page.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const PAGE_SCROLL_TOLERANCE_PX = 4;  // a 1-3 px fit overflow must not turn the wheel into page scroll
    const PAN_FRACTION_PER_100_DELTA = 0.1;
    const MAX_PAN_FRACTION = 0.3;

    /** Pure decision, exported for tests. Returns 'zoom' | 'scroll' | 'pan'. */
    function decideWheelAction({ ctrl, shift, locked, pageScrolls }) {
        if (shift) return 'pan';
        if (ctrl || locked || !pageScrolls) return 'zoom';
        return 'scroll';
    }

    function pageScrolls() {
        const doc = document.documentElement;
        return doc.scrollHeight > window.innerHeight + PAGE_SCROLL_TOLERANCE_PX;
    }

    function isOverChart(event) {
        const path = typeof event.composedPath === 'function' ? event.composedPath() : [];
        return path.some(node => node?.classList?.contains?.('bk-events'));
    }

    function wheelDelta(event) {
        return Math.abs(event.deltaY) >= Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
    }

    function onWheel(event) {
        if (!app.store || !isOverChart(event)) return;
        const state = app.store.getState();
        const action = decideWheelAction({
            ctrl: event.ctrlKey || event.metaKey,
            shift: event.shiftKey,
            locked: Boolean(state?.layout?.wheelZoomLock),
            pageScrolls: pageScrolls()
        });
        if (action === 'zoom') {
            return; // Bokeh's wheel zoom handles it (and calls preventDefault)
        }
        // Keep the event from the Bokeh tool in both remaining cases.
        event.stopImmediatePropagation();
        if (action === 'pan') {
            event.preventDefault();
            const delta = wheelDelta(event);
            if (!delta) return;
            const magnitude = Math.min(MAX_PAN_FRACTION, Math.abs(delta) / 100 * PAN_FRACTION_PER_100_DELTA);
            app.store.dispatch(app.thunks.panIntent({ fraction: Math.sign(delta) * magnitude }));
        }
        // 'scroll': no preventDefault, so the browser scrolls the page.
    }

    function attach() {
        if (typeof window === 'undefined' || attach.done) return;
        attach.done = true;
        window.addEventListener('wheel', onWheel, { capture: true, passive: false });
    }

    attach();
    app.services = app.services || {};
    app.services.wheelController = { decideWheelAction, pageScrolls, onWheel, attach };
})(window.NoiseSurveyApp);
