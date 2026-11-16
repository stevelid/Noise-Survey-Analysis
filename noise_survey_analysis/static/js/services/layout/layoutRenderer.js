// noise_survey_analysis/static/js/services/layout/layoutRenderer.js

/**
 * @fileoverview Applies the `layout` slice to the Bokeh models (render hook, loads after app.js):
 *
 *   - position order        charts_stack_layout.children
 *   - spectrogram modes     full / strip / hidden: figure.visible, axes, borders, height
 *   - fit to window         figure heights from the window height (layoutMath.computeFit)
 *   - time labels           only under the lowest visible chart of each position
 *   - y auto-fit            auto / shared / locked (layoutMath.nextYRange)
 *   - header strip          status text, chevron, focus accent, loading banner
 *   - frequency dock        visibility and the --nsa-dock-h CSS variable the annotation panel uses
 *   - toolbar widgets       fit / y mode / wheel lock mirrors
 *
 * Everything is idempotent: each setter compares before writing, because Bokeh model writes sync
 * back to the server and trigger layout.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const STRIP_HEIGHT = 26;
    const MIN_TS = 110;
    const MIN_SPEC = 80;
    const FIXED_TS = 220;
    const FIXED_SPEC = 160;
    const TS_SHARE = 0.55;
    const BOTTOM_MARGIN = 6;
    const BANNER_DELAY_MS = 600;
    const MAX_SHAVE_ATTEMPTS = 3;       // times the measured page overflow is shaved off the budget
    const MAX_UNSETTLED_FRAMES = 30;    // frames to wait for Bokeh to finish laying out a height change
    const VIEW_POLL_MS = 50;
    const VIEW_POLL_LIMIT = 100;        // 5 s

    const fitState = { reduce: 0, attempt: 0, unsettled: 0, frame: 0, lastFits: false, observer: null, observed: null };
    const loadingSince = {};
    let last = { layout: null, visibility: null, viewport: null, yMode: null };
    let started = false;
    let bannerTimer = null;

    function models() { return app.registry?.models || {}; }
    function controllers() { return app.registry?.controllers || {}; }

    function viewOf(model) {
        try {
            const index = window.Bokeh?.index;
            if (!index || !model) return null;
            if (typeof index.find_one === 'function') return index.find_one(model);
            if (typeof index.get_one === 'function') return index.get_one(model);
        } catch (error) { /* view not built yet */ }
        return null;
    }

    /** Axis renderers of a BokehJS figure ('x' = below/above, 'y' = left/right). */
    function axesOf(figure, dimension) {
        const lists = dimension === 'x' ? [figure?.below, figure?.above] : [figure?.left, figure?.right];
        return lists.flatMap(list => Array.isArray(list) ? list : []).filter(item => item && 'ticker' in item);
    }

    function safe(label, fn) {
        try { return fn(); } catch (error) { console.warn(`[Layout] ${label} failed:`, error); return undefined; }
    }

    function setIfChanged(target, key, value) {
        if (target && target[key] !== value) target[key] = value;
    }

    function orderedPositions(state) {
        return app.features.layout.selectors.selectOrderedPositions(state, state?.view?.availablePositions || []);
    }

    function chartVisible(state, name) {
        const visibility = state?.view?.chartVisibility || {};
        return Object.prototype.hasOwnProperty.call(visibility, name) ? Boolean(visibility[name]) : true;
    }

    function figures(positionId) {
        const controller = controllers().positions?.[positionId];
        return { ts: controller?.timeSeriesChart?.model || null, spec: controller?.spectrogramChart?.model || null };
    }

    // ---- order -------------------------------------------------------------------------------

    function syncOrder(state) {
        const stack = models().chartsStackLayout;
        const layouts = models().positionLayouts || {};
        if (!stack || !layouts) return;
        const wanted = orderedPositions(state).map(id => layouts[id]).filter(Boolean);
        const current = stack.children || [];
        const same = wanted.length === current.length && wanted.every((item, index) => item === current[index]);
        if (!same && wanted.length === current.length) {
            stack.children = wanted;
        }
    }

    // ---- spectrogram modes + time labels -----------------------------------------------------

    function specModeOf(state, positionId) {
        return app.features.layout.selectors.selectSpectrogramMode(state, positionId);
    }

    function syncSpectrogramAndAxes(state) {
        const selectors = app.features.layout.selectors;
        orderedPositions(state).forEach(positionId => {
            const { ts, spec } = figures(positionId);
            const mode = selectors.selectSpectrogramMode(state, positionId);
            const specWanted = chartVisible(state, `figure_${positionId}_spectrogram`) && mode !== 'hidden';
            const controls = models().positionControls?.[positionId];
            const hoverDiv = controls?.hover_div || controllers().positions?.[positionId]?.spectrogramChart?.hoverDivModel;

            if (spec) {
                if (mode === 'hidden') {
                    setIfChanged(spec, 'visible', false);
                    setIfChanged(hoverDiv, 'visible', false);
                } else if (specWanted) {
                    setIfChanged(spec, 'visible', true);
                }
                const isStrip = mode === 'strip';
                axesOf(spec, 'y').forEach(axis => setIfChanged(axis, 'visible', !isStrip));
                const labelsHere = app.layoutMath.timeLabelChart(mode, specWanted) === 'spectrogram';
                axesOf(spec, 'x').forEach(axis => setIfChanged(axis, 'visible', labelsHere && !isStrip));
                setIfChanged(spec, 'min_border_top', isStrip ? 1 : 2);
                setIfChanged(spec, 'min_border_bottom', isStrip ? 1 : 2);
            }
            if (ts) {
                const labelsHere = app.layoutMath.timeLabelChart(mode, specWanted && !!spec) === 'timeseries';
                axesOf(ts, 'x').forEach(axis => setIfChanged(axis, 'visible', labelsHere));
            }
        });
    }

    // ---- fit to window -----------------------------------------------------------------------

    function setHeight(figure, height) {
        if (figure && Number.isFinite(height) && height > 0 && figure.height !== height) {
            figure.height = height;
        }
    }

    /**
     * Sum of the figures' heights, both as the models say and as laid out in the DOM. They differ while
     * Bokeh has not re-laid out after a height change, in which case the measurement is not trusted.
     */
    function currentFigureHeights(state, positions) {
        let model = 0;
        let dom = 0;
        positions.forEach(({ id, specMode }) => {
            const { ts, spec } = figures(id);
            [ts, specMode === 'hidden' ? null : spec].forEach(figure => {
                if (!figure || figure.visible === false) return;
                model += figure.height || 0;
                dom += viewOf(figure)?.el?.getBoundingClientRect?.().height || 0;
            });
        });
        return { model, dom, settled: Math.abs(model - dom) <= 2 };
    }

    function visiblePositions(state) {
        return orderedPositions(state)
            .filter(id => chartVisible(state, `figure_${id}_timeseries`) || chartVisible(state, `figure_${id}_spectrogram`))
            .map(id => ({ id, specMode: specModeOf(state, id) }));
    }

    function applyHeights(positions, heights) {
        positions.forEach(({ id, specMode }) => {
            const { ts, spec } = figures(id);
            const h = heights[id];
            if (!h) return;
            setHeight(ts, h.ts);
            if (spec && specMode !== 'hidden') setHeight(spec, h.spec);
        });
    }

    function applyFit(state) {
        const positions = visiblePositions(state);
        if (!positions.length) return;
        const math = app.layoutMath;
        const common = { ratio: TS_SHARE, stripHeight: STRIP_HEIGHT, minTs: MIN_TS, minSpec: MIN_SPEC, fixedTs: FIXED_TS, fixedSpec: FIXED_SPEC };

        if (!app.features.layout.selectors.selectFitToWindow(state)) {
            applyHeights(positions, math.computeFit({ ...common, budget: 0, positions }).heights);
            fitState.lastFits = false;
            return;
        }

        const stackView = viewOf(models().chartsStackLayout);
        const rect = stackView?.el?.getBoundingClientRect?.();
        if (!rect || !rect.height) {
            // Not laid out yet: use a rough guess so the first paint is close, refined below.
            return;
        }
        const measured = currentFigureHeights(state, positions);
        if (!measured.settled) {
            // Bokeh is still laying out the last height change; look again next frame (bounded).
            if (fitState.unsettled < MAX_UNSETTLED_FRAMES) { fitState.unsettled += 1; requestFitFrame(); }
            return;
        }
        fitState.unsettled = 0;
        if (fitState.lastFits) {
            // The page should not scroll: shave any measured overflow off the budget. The stack resizing
            // after this pass wakes the ResizeObserver, which measures again.
            const overflow = document.documentElement.scrollHeight - window.innerHeight;
            if (overflow > 0 && fitState.attempt < MAX_SHAVE_ATTEMPTS) {
                fitState.attempt += 1;
                fitState.reduce = Math.min(300, fitState.reduce + overflow);
            } else if (overflow <= 0) {
                fitState.attempt = 0;
            }
        }
        const top = rect.top + (window.scrollY || 0);
        const overhead = rect.height - measured.dom;
        const budget = window.innerHeight - top - overhead - BOTTOM_MARGIN - fitState.reduce;
        const result = math.computeFit({ ...common, budget, positions });
        fitState.lastFits = result.fits;
        if (!result.fits) { fitState.reduce = 0; fitState.attempt = 0; }
        applyHeights(positions, result.heights);
    }

    function requestFitFrame() {
        if (fitState.frame) return;
        const run = () => {
            fitState.frame = 0;
            const state = app.store?.getState?.();
            if (state) safe('fit', () => applyFit(state));
        };
        fitState.frame = typeof requestAnimationFrame === 'function' ? requestAnimationFrame(run) : setTimeout(run, 0);
    }

    function scheduleFit(resetReduce = false) {
        if (resetReduce) { fitState.reduce = 0; fitState.attempt = 0; }
        fitState.unsettled = 0;
        requestFitFrame();
    }

    // ---- y fit -------------------------------------------------------------------------------

    function lineColumns(figure) {
        const names = [];
        (figure?.renderers || []).forEach(renderer => {
            const ySpec = renderer?.glyph?.y;
            const field = typeof ySpec === 'string' ? ySpec : ySpec?.field;
            if (field && renderer.visible !== false && renderer?.glyph?.type !== 'Image') names.push(field);
        });
        return names;
    }

    function isFittableRange(range) {
        return range && range.follow === undefined && Number.isFinite(range.start) && Number.isFinite(range.end);
    }

    function applyYFit(state, dataCache, forceTarget) {
        const mode = app.features.layout.selectors.selectYAxisMode(state);
        if (mode === 'locked') return;
        const math = app.layoutMath;
        const viewport = state.view?.viewport;
        const from = Number.isFinite(viewport?.min) ? viewport.min : undefined;
        const to = Number.isFinite(viewport?.max) ? viewport.max : undefined;

        const entries = [];
        orderedPositions(state).forEach(id => {
            if (!chartVisible(state, `figure_${id}_timeseries`)) return;
            const { ts } = figures(id);
            if (!isFittableRange(ts?.y_range)) return;
            const extent = math.visibleExtent(dataCache?.activeLineData?.[id], lineColumns(ts), from, to);
            entries.push({ ts, extent });
        });
        const shared = mode === 'shared' ? math.unionExtent(entries.map(entry => entry.extent)) : null;

        entries.forEach(({ ts, extent }) => {
            const use = mode === 'shared' ? shared : extent;
            if (!use) return;
            const current = { start: ts.y_range.start, end: ts.y_range.end };
            const next = forceTarget ? math.targetYRange(use) : math.nextYRange(current, use);
            if (next && (next.start !== current.start || next.end !== current.end)) {
                ts.y_range.start = next.start;
                ts.y_range.end = next.end;
            }
        });
    }

    // ---- header strip ------------------------------------------------------------------------

    function formatStep(positionId) {
        const time = models().timeSeriesSources?.[positionId]?.log?.data?.Datetime;
        const calc = app.features?.view?.resolution?.computeMedianPositiveStepMs;
        const step = typeof calc === 'function' && time && time.length > 1 ? calc(time, 2000) : NaN;
        if (!Number.isFinite(step) || step <= 0) return 'log';
        if (step < 1000) return `${Math.round(step)} ms`;
        if (step < 60000) return `${Number((step / 1000).toFixed(1))} s`;
        return `${Math.round(step / 60000)} min`;
    }

    function statusHtml(details) {
        const line = details?.line || details?.spec || details?.spectrogram || null;
        if (!line) return '';
        const type = line.type === 'log' ? 'LOG' : (line.type === 'overview' ? 'OVERVIEW' : '');
        const colour = line.type === 'log' ? '#047857' : '#475569';
        let extra = '';
        if (line.isLoading) extra = " <span style='color:#9a3412'>&middot; loading</span>";
        else if (line.requiresZoom) extra = " <span style='color:#2563eb'>&middot; zoom in for log</span>";
        return type ? `<b style='color:${colour}'>${type}</b>${extra}` : '';
    }

    function detailsFor(positionId, state) {
        const controller = controllers().positions?.[positionId];
        return {
            line: controller?.timeSeriesChart?.lastDisplayDetails || null,
            spec: controller?.spectrogramChart?.lastDisplayDetails || null
        };
    }

    function syncHeaders(state) {
        const selectors = app.features.layout.selectors;
        const focused = app.layoutRuntime?.resolveFocus?.(state);
        orderedPositions(state).forEach(positionId => {
            const controls = models().positionControls?.[positionId];
            if (!controls) return;
            const details = detailsFor(positionId, state);

            const html = statusHtml(details);
            if (controls.status_div && controls.status_div.text !== html) controls.status_div.text = html;

            const mode = selectors.selectSpectrogramMode(state, positionId);
            const chevron = { full: 'Spec ▾', strip: 'Spec ▴', hidden: 'Spec ▸' }[mode] || 'Spec ▾';
            setIfChanged(controls.spec_button, 'label', chevron);

            const row = controls.header_row;
            if (row) {
                const wantFocus = positionId === focused;
                const classes = row.css_classes || [];
                const has = classes.includes('nsa-focused');
                if (wantFocus !== has) {
                    row.css_classes = wantFocus
                        ? [...classes, 'nsa-focused']
                        : classes.filter(name => name !== 'nsa-focused');
                }
            }

            const loading = Boolean(details.line?.isLoading || details.spec?.isLoading)
                && state.view?.globalViewType === 'log';
            if (loading) {
                if (loadingSince[positionId] === undefined) loadingSince[positionId] = Date.now();
            } else {
                delete loadingSince[positionId];
            }
            syncBanner(positionId, controls);
        });
        scheduleBannerCheck();
    }

    function syncBanner(positionId, controls) {
        const banner = controls?.banner_div;
        if (!banner) return;
        const since = loadingSince[positionId];
        const show = since !== undefined && Date.now() - since >= BANNER_DELAY_MS;
        if (show) {
            const text = `Loading ${formatStep(positionId)} data for ${positionId} - overview shown meanwhile`;
            if (banner.text !== text) banner.text = text;
        }
        setIfChanged(banner, 'visible', show);
    }

    function scheduleBannerCheck() {
        if (bannerTimer !== null) return;
        const pending = Object.keys(loadingSince).length > 0;
        if (!pending) return;
        bannerTimer = setTimeout(() => {
            bannerTimer = null;
            Object.keys(loadingSince).forEach(positionId => syncBanner(positionId, models().positionControls?.[positionId]));
            scheduleBannerCheck();
        }, 300);
    }

    // ---- toolbar mirrors and dock ------------------------------------------------------------

    function syncToolbar(state) {
        const controls = models().layoutControls;
        const selectors = app.features.layout.selectors;
        if (!controls) return;
        setIfChanged(controls.fit_toggle, 'active', selectors.selectFitToWindow(state));
        setIfChanged(controls.wheel_toggle, 'active', selectors.selectWheelZoomLock(state));
        setIfChanged(controls.y_mode_button, 'label', `Y: ${selectors.selectYAxisMode(state)}`);
    }

    function syncDock(state) {
        const open = app.features.layout.selectors.selectFrequencyDockOpen(state);
        setIfChanged(models().frequencyDockInner, 'visible', open);
        scheduleDockMeasure();
    }

    let dockTimer = null;
    function scheduleDockMeasure() {
        clearTimeout(dockTimer);
        dockTimer = setTimeout(measureDock, 120);
    }

    function measureDock() {
        const view = viewOf(models().frequencyDockLayout);
        const height = view?.el?.getBoundingClientRect?.().height;
        if (!Number.isFinite(height) || typeof document === 'undefined') return;
        const value = `${Math.ceil(height)}px`;
        const root = document.documentElement.style;
        if (root.getPropertyValue('--nsa-dock-h') !== value) {
            root.setProperty('--nsa-dock-h', value);
            scheduleFit();
        }
    }

    let observedDock = null;
    function observeLayout() {
        if (typeof ResizeObserver !== 'function') return;
        const stackEl = viewOf(models().chartsStackLayout)?.el;
        if (stackEl && fitState.observed !== stackEl) {
            fitState.observed = stackEl;
            fitState.observer?.disconnect?.();
            fitState.observer = new ResizeObserver(() => requestFitFrame());
            fitState.observer.observe(stackEl);
        }
        const dockEl = viewOf(models().frequencyDockLayout)?.el;
        if (dockEl && observedDock !== dockEl) {
            observedDock = dockEl;
            new ResizeObserver(() => scheduleDockMeasure()).observe(dockEl);
            scheduleDockMeasure();
        }
    }

    // ---- hook --------------------------------------------------------------------------------

    function applyAll(state, dataCache, flags) {
        const { all, layoutChanged, visibilityChanged, heavy, yChange, headerChange, yForce } = flags;
        if (all || layoutChanged) {
            safe('order', () => syncOrder(state));
            safe('toolbar', () => syncToolbar(state));
            safe('dock', () => syncDock(state));
        }
        if (all || layoutChanged || visibilityChanged || heavy) {
            safe('spectrogram', () => syncSpectrogramAndAxes(state));
        }
        if (all || layoutChanged || visibilityChanged) {
            safe('fit', () => scheduleFit());
        }
        if (all || yChange) {
            safe('yfit', () => applyYFit(state, dataCache, yForce));
        }
        if (all || headerChange) {
            safe('headers', () => syncHeaders(state));
        }
    }

    function start(state) {
        if (started) return;
        started = true;
        window.addEventListener('resize', () => scheduleFit(true));
        if (app.layoutRuntime) {
            app.layoutRuntime.focusListeners.push(() => safe('focus', () => syncHeaders(app.store.getState())));
        }
        // The frequency slice dock is open by default; a restored workspace overrides this. The saved
        // state is the bare app state (but accept a full workspace payload too). start() runs before
        // the saved state is applied, so decide in the timeout, after the restore.
        const saved = models().savedWorkspaceState;
        const hasSavedLayout = Boolean(saved?.layout || saved?.appState?.layout);
        if (!hasSavedLayout) {
            setTimeout(() => {
                if (!app.store.getState().layout?.frequencyDockOpen) {
                    app.store.dispatch(app.actions.layoutFrequencyDockOpenSet(true));
                }
            }, 0);
        }
        // Bokeh builds the views asynchronously after the first render (a colour bar even initialises
        // its layout later than its figure), so write layout properties only once the views are done,
        // in one idle pass. After that the ResizeObserver keeps the fit current.
        whenViewsReady(() => {
            safe('observe', observeLayout);
            applyAll(app.store.getState(), app.dataCache, { all: true, yForce: false });
        });
    }

    function allViewsFinished(state) {
        const finished = (model) => {
            const view = viewOf(model);
            return Boolean(view) && (typeof view.has_finished !== 'function' || view.has_finished());
        };
        if (!finished(models().chartsStackLayout)) return false;
        return orderedPositions(state).every(id => {
            const { ts, spec } = figures(id);
            return (!ts || finished(ts)) && (!spec || finished(spec));
        });
    }

    function whenViewsReady(callback) {
        let polls = 0;
        const attempt = () => {
            polls += 1;
            const state = app.store?.getState?.();
            const ready = safe('views', () => state && allViewsFinished(state));
            if (!ready && polls < VIEW_POLL_LIMIT) { setTimeout(attempt, VIEW_POLL_MS); return; }
            const idle = typeof window.requestIdleCallback === 'function'
                ? (fn) => window.requestIdleCallback(fn, { timeout: 500 })
                : (fn) => setTimeout(fn, 0);
            idle(() => safe('initial-layout', callback));
        };
        setTimeout(attempt, 0);
    }

    function render(state, info) {
        if (!models().chartsStackLayout) return;
        const { prev, isInitialLoad, isHeavyUpdate, dataCache } = info;
        if (isInitialLoad) start(state);

        const layoutChanged = state.layout !== last.layout;
        const visibilityChanged = state.view?.chartVisibility !== last.visibility;
        const viewportChanged = state.view?.viewport !== last.viewport;
        const yModeChanged = state.layout?.yAxisMode !== last.yMode;
        const firstPass = last.layout === null;
        last = {
            layout: state.layout, visibility: state.view?.chartVisibility,
            viewport: state.view?.viewport, yMode: state.layout?.yAxisMode
        };
        // Views are not built during the very first render; start() re-applies everything shortly after.
        if (isInitialLoad && firstPass) return;

        applyAll(state, dataCache, {
            all: false,
            layoutChanged,
            visibilityChanged,
            heavy: isHeavyUpdate,
            yChange: isHeavyUpdate || viewportChanged || yModeChanged,
            yForce: yModeChanged,
            headerChange: isHeavyUpdate || layoutChanged
                || state.view?.positionChartOffsets !== prev?.view?.positionChartOffsets
                || state.interaction?.tap !== prev?.interaction?.tap
        });
    }

    app.layoutRenderer = { render, applyFit, applyYFit, syncOrder, measureDock, fitState };
    if (typeof app.registerRenderHook === 'function') {
        app.registerRenderHook('layout', render);
    }
})(window.NoiseSurveyApp);
