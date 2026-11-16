// noise_survey_analysis/static/js/services/layout/layoutMath.js

/**
 * @fileoverview Pure maths for the compact layout and navigation: zoom/pan with clamping, the
 * fit-to-window height split, y-axis auto-fit and small mode cycles. No DOM, no store, so every
 * function is unit tested (tests/layout-math.test.js).
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const DEFAULT_MIN_INTERVAL_MS = 1000;

    function isFiniteNumber(value) {
        return typeof value === 'number' && Number.isFinite(value);
    }

    /**
     * Clamps a window to bounds. The width is limited to [minInterval, bounds width] and the window
     * is shifted (not squeezed) to fit inside the bounds.
     * @returns {{min:number,max:number}}
     */
    function clampRange(min, max, bounds, minInterval = DEFAULT_MIN_INTERVAL_MS) {
        let width = max - min;
        if (!(width > 0)) width = minInterval;
        width = Math.max(width, minInterval);
        const hasBounds = bounds && isFiniteNumber(bounds.min) && isFiniteNumber(bounds.max) && bounds.max > bounds.min;
        if (!hasBounds) {
            return { min, max: min + width };
        }
        width = Math.min(width, bounds.max - bounds.min);
        let lo = min;
        if (lo < bounds.min) lo = bounds.min;
        if (lo + width > bounds.max) lo = bounds.max - width;
        return { min: lo, max: lo + width };
    }

    /**
     * Zoom about an anchor. factor < 1 zooms in (the window width is multiplied by factor).
     * The anchor keeps its relative position in the window when possible. A window that is already
     * at its limit is returned unchanged.
     */
    function zoomRange(viewport, factor, anchor, bounds, minInterval = DEFAULT_MIN_INTERVAL_MS) {
        const { min, max } = viewport;
        const width = max - min;
        if (!(width > 0) || !(factor > 0)) return { min, max };
        const centre = min + width / 2;
        const pivot = isFiniteNumber(anchor) && anchor >= min && anchor <= max ? anchor : centre;
        const ratio = (pivot - min) / width;
        const boundsWidth = bounds && isFiniteNumber(bounds.min) && isFiniteNumber(bounds.max) ? bounds.max - bounds.min : Infinity;
        const nextWidth = Math.min(Math.max(width * factor, minInterval), boundsWidth);
        const nextMin = pivot - ratio * nextWidth;
        return clampRange(nextMin, nextMin + nextWidth, bounds, minInterval);
    }

    /** Pan by a fraction of the window width (positive = later). Stops at the bounds. */
    function panRange(viewport, fraction, bounds, minInterval = DEFAULT_MIN_INTERVAL_MS) {
        const width = viewport.max - viewport.min;
        const shift = width * fraction;
        return clampRange(viewport.min + shift, viewport.max + shift, bounds, minInterval);
    }

    /** Smallest window containing every [start,end] area, padded by padFraction of its width on each side. */
    function paddedExtent(areas, padFraction = 0.1) {
        let lo = Infinity;
        let hi = -Infinity;
        (areas || []).forEach(area => {
            const start = Number(area?.start);
            const end = Number(area?.end);
            if (Number.isFinite(start) && Number.isFinite(end)) {
                lo = Math.min(lo, start, end);
                hi = Math.max(hi, start, end);
            }
        });
        if (!Number.isFinite(lo) || !Number.isFinite(hi)) return null;
        const width = Math.max(hi - lo, 1);
        return { min: lo - width * padFraction, max: hi + width * padFraction };
    }

    /**
     * Splits the chart budget between positions.
     *
     * Each position gets one equal flexible unit; a collapsed spectrogram keeps a fixed strip and gives
     * the rest of its unit to the time series. If any row would fall below the minimums, every row uses
     * the fixed heights and the page scrolls (4+ positions).
     *
     * @param {object} opts
     * @param {number} opts.budget  px available for all figures (windowHeight minus every other element)
     * @param {Array<{id:string, specMode:'full'|'strip'|'hidden'}>} opts.positions  visible positions
     * @returns {{fits:boolean, heights:Object<string,{ts:number,spec:number}>}}
     */
    function computeFit(opts) {
        const {
            budget, positions,
            ratio = 0.55, stripHeight = 26, minTs = 110, minSpec = 80, fixedTs = 220, fixedSpec = 160
        } = opts;
        const list = Array.isArray(positions) ? positions : [];
        const heights = {};
        const fixed = () => {
            list.forEach(({ id, specMode }) => {
                heights[id] = {
                    ts: fixedTs,
                    spec: specMode === 'strip' ? stripHeight : (specMode === 'hidden' ? 0 : fixedSpec)
                };
            });
            return { fits: false, heights };
        };
        if (!list.length || !(budget > 0)) return fixed();

        const stripped = list.filter(item => item.specMode === 'strip').length;
        const unit = (budget - stripped * stripHeight) / list.length;
        let ok = unit > 0;
        const raw = {};
        list.forEach(({ id, specMode }) => {
            if (specMode === 'strip') {
                raw[id] = { ts: unit, spec: stripHeight };
                ok = ok && unit >= minTs;
            } else if (specMode === 'hidden') {
                raw[id] = { ts: unit, spec: 0 };
                ok = ok && unit >= minTs;
            } else {
                raw[id] = { ts: unit * ratio, spec: unit * (1 - ratio) };
                ok = ok && raw[id].ts >= minTs && raw[id].spec >= minSpec;
            }
        });
        if (!ok) return fixed();

        let used = 0;
        list.forEach(({ id }) => {
            const spec = Math.round(raw[id].spec);
            const ts = Math.floor(raw[id].ts);
            heights[id] = { ts, spec };
            used += ts + spec;
        });
        // Hand any rounding remainder to the first time series so the sum equals the budget.
        const remainder = Math.floor(budget) - used;
        if (remainder > 0) heights[list[0].id].ts += remainder;
        return { fits: true, heights };
    }

    function floorTo(value, step) { return Math.floor(value / step) * step; }
    function ceilTo(value, step) { return Math.ceil(value / step) * step; }

    /** Target y window for a data extent: padded 3 dB, rounded out to 5 dB, at least minSpan wide. */
    function targetYRange(extent, opts = {}) {
        const { pad = 3, step = 5, minSpan = 20 } = opts;
        if (!extent || !isFiniteNumber(extent.min) || !isFiniteNumber(extent.max)) return null;
        let lo = floorTo(extent.min - pad, step);
        let hi = ceilTo(extent.max + pad, step);
        if (hi - lo < minSpan) {
            const span = ceilTo(minSpan, step);
            lo = floorTo((lo + hi) / 2 - span / 2, step);
            hi = lo + span;
            // Rounding the start down can leave the top short of the data; widen by one step.
            if (hi < extent.max + pad) hi += step;
        }
        return { start: lo, end: hi };
    }

    /**
     * Decides whether to move the y window. Returns the new {start,end}, or null to leave it alone.
     * It changes only when data leaves the current window or the window is much wider than needed,
     * so the axis does not jitter while panning.
     */
    function nextYRange(current, extent, opts = {}) {
        const { slack = 15 } = opts;
        const target = targetYRange(extent, opts);
        if (!target) return null;
        if (!current || !isFiniteNumber(current.start) || !isFiniteNumber(current.end)) return target;
        const leaves = extent.min < current.start || extent.max > current.end;
        const tooWide = (current.end - current.start) - (target.end - target.start) > slack;
        if (!leaves && !tooWide) return null;
        return target;
    }

    function unionExtent(extents) {
        let min = Infinity;
        let max = -Infinity;
        (extents || []).forEach(extent => {
            if (extent && isFiniteNumber(extent.min) && isFiniteNumber(extent.max)) {
                min = Math.min(min, extent.min);
                max = Math.max(max, extent.max);
            }
        });
        return Number.isFinite(min) && Number.isFinite(max) ? { min, max } : null;
    }

    function lowerBound(array, value) {
        let lo = 0;
        let hi = array.length;
        while (lo < hi) {
            const mid = (lo + hi) >>> 1;
            if (array[mid] < value) lo = mid + 1; else hi = mid;
        }
        return lo;
    }

    /**
     * Min/max of the finite values of the given columns whose Datetime lies in [from, to].
     * `data` is a column dictionary with a sorted `Datetime` array.
     */
    function visibleExtent(data, columns, from, to) {
        const time = data?.Datetime;
        if (!time || !time.length) return null;
        const start = Number.isFinite(from) ? lowerBound(time, from) : 0;
        let end = Number.isFinite(to) ? lowerBound(time, to + 1) : time.length;
        end = Math.min(end, time.length);
        let min = Infinity;
        let max = -Infinity;
        (columns || []).forEach(name => {
            const column = data[name];
            if (!column || typeof column.length !== 'number') return;
            for (let i = start; i < end; i += 1) {
                const value = column[i];
                if (value === null || value === undefined || !Number.isFinite(value)) continue;
                if (value < min) min = value;
                if (value > max) max = value;
            }
        });
        return Number.isFinite(min) && Number.isFinite(max) ? { min, max } : null;
    }

    function cycleSpectrogramMode(mode) {
        return mode === 'full' || !mode ? 'strip' : 'full';
    }

    function cycleYMode(mode) {
        const order = ['auto', 'shared', 'locked'];
        return order[(Math.max(0, order.indexOf(mode)) + 1) % order.length];
    }

    /** Which chart carries the time labels for a position: the lowest visible one. */
    function timeLabelChart(specMode, specVisible = true) {
        return specMode === 'full' && specVisible ? 'spectrogram' : 'timeseries';
    }

    /** Index of the next/previous entry, wrapping nowhere (stops at the ends). */
    function stepIndex(length, current, delta) {
        if (!length) return -1;
        if (current < 0) return delta > 0 ? 0 : length - 1;
        return Math.min(length - 1, Math.max(0, current + delta));
    }

    app.layoutMath = {
        clampRange,
        zoomRange,
        panRange,
        paddedExtent,
        computeFit,
        targetYRange,
        nextYRange,
        unionExtent,
        visibleExtent,
        cycleSpectrogramMode,
        cycleYMode,
        timeLabelChart,
        stepIndex
    };
})(window.NoiseSurveyApp);
