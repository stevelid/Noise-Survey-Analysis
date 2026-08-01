// noise_survey_analysis/static/utils.js

/**
 * @fileoverview Contains utility functions used throughout the Noise Survey application.
 * These functions are designed to be generic and reusable across different components.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    /**
     * Index of the first element >= target, or -1 if every element is smaller.
     *
     * Requires `values` to be sorted ascending. Every timestamp array in the app is:
     * source frames are sorted on merge, and chunk slices and synthetic display grids
     * inherit that ordering.
     *
     * @param {Array<number>|TypedArray} values - Ascending numeric array.
     * @param {number} target - Value to search for.
     * @returns {number} Matching index, or -1.
     */
    function firstIndexAtOrAfter(values, target) {
        if (!values || values.length === 0) {
            return -1;
        }
        let low = 0;
        let high = values.length;
        while (low < high) {
            const mid = (low + high) >>> 1;
            if (values[mid] >= target) {
                high = mid;
            } else {
                low = mid + 1;
            }
        }
        return low < values.length ? low : -1;
    }

    /**
     * Index of the last element <= target, or -1 if every element is larger.
     *
     * Same ascending-order requirement as `firstIndexAtOrAfter`.
     *
     * @param {Array<number>|TypedArray} values - Ascending numeric array.
     * @param {number} target - Value to search for.
     * @returns {number} Matching index, or -1.
     */
    function lastIndexAtOrBefore(values, target) {
        if (!values || values.length === 0) {
            return -1;
        }
        let low = 0;
        let high = values.length;
        while (low < high) {
            const mid = (low + high) >>> 1;
            if (values[mid] <= target) {
                low = mid + 1;
            } else {
                high = mid;
            }
        }
        return low - 1;
    }

    function findAssociatedDateIndex(activeData, timestamp) {
        if (!activeData || !activeData.Datetime || activeData.Datetime.length === 0) {
            return -1;
        }
        return lastIndexAtOrBefore(activeData.Datetime, timestamp);
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
        if (inEditable) {
            return true;
        }

        // Fallback for synthetic/test events that don't provide composedPath().
        const target = ev && ev.target;
        const targetTag = typeof target?.tagName === 'string'
            ? target.tagName.toLowerCase()
            : '';
        if (targetTag === 'input' || targetTag === 'textarea' || targetTag === 'select') {
            return true;
        }
        if (target?.isContentEditable === true) {
            return true;
        }
        if (target instanceof Element) {
            if (target.matches?.('textarea, input, [contenteditable="true"]')) return true;
            if (target.classList?.contains('bk-input')) return true;
            if (target.classList?.contains('bk-textareainput')) return true;
        }
        return false;
    }

    app.utils = {
        findAssociatedDateIndex: findAssociatedDateIndex,
        firstIndexAtOrAfter: firstIndexAtOrAfter,
        lastIndexAtOrBefore: lastIndexAtOrBefore,
        isEditableEvent: isEditableEvent
    };
})(window.NoiseSurveyApp);
