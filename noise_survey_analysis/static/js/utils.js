// noise_survey_analysis/static/utils.js

/**
 * @fileoverview Contains utility functions used throughout the Noise Survey application.
 * These functions are designed to be generic and reusable across different components.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    function findAssociatedDateIndex(activeData, timestamp) {
        if (!activeData || !activeData.Datetime || activeData.Datetime.length === 0) {
            return -1;
        }
        for (let i = activeData.Datetime.length - 1; i >= 0; i--) {
            if (activeData.Datetime[i] <= timestamp) return i;
        }
        return -1;
    }

    /**
     * Determines if a keyboard event originated from an editable element.
     * Walks the composed path (including nodes inside Bokeh's shadow roots) to detect
     * native editables and Bokeh widget classes.
     *
     * @param {KeyboardEvent} ev - The keyboard event to check.
     * @returns {boolean} True if the event originated from an editable element.
     */
    function isEditableEvent(ev) {
        // Walk the composed path (includes nodes inside Bokeh's shadow roots)
        const path = ev.composedPath ? ev.composedPath() : [];
        const inEditable = path.some((el) => {
            if (!(el instanceof Element)) return false;
            // Native editables and Bokeh widget classes
            if (el.matches?.('textarea, input, [contenteditable="true"]')) return true;
            if (el.classList?.contains('bk-input')) return true;
            if (el.classList?.contains('bk-textareainput')) return true;
            return false;
        });
        return inEditable;
    }

    app.utils = {
        findAssociatedDateIndex: findAssociatedDateIndex,
        isEditableEvent: isEditableEvent
    };
})(window.NoiseSurveyApp);