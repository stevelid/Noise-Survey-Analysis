// noise_survey_analysis/static/js/renderers.js

/**
 * @fileoverview Contains all rendering functions that update the UI of the Noise Survey app.
 * These functions take the fully processed application state as input and are responsible
 * for updating the properties of the Bokeh models (e.g., chart data sources, line visibility,
 * label text). They are "presentational" and should contain minimal logic, focusing
 * only on translating the state into visuals.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    // Dependencies are accessed dynamically within each function (e.g., `app.registry.models`)
    // to ensure they are not stale, especially in test environments.
    const regionsModule = app.regions;
    function getActions() {
        return app.actions || {};
    }
    const REGION_PANEL_STYLE = `
        <style>
            .region-panel-root { font-family: 'Segoe UI', sans-serif; font-size: 12px; display: flex; flex-direction: column; gap: 8px; }
            .region-list { display: flex; flex-direction: column; gap: 4px; }
            .region-entry { border: 1px solid #ddd; border-radius: 4px; padding: 6px; cursor: pointer; background: #fff; transition: background 0.2s; }
            .region-entry:hover { background: #f5f5f5; }
            .region-entry.selected { border-color: #64b5f6; background: #e3f2fd; }
            .region-entry__header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
            .region-entry__meta { color: #555; font-size: 11px; margin-top: 2px; }
            .region-entry button { background: transparent; border: none; color: #c62828; cursor: pointer; font-size: 11px; }
            .region-detail { border-top: 1px solid #ddd; padding-top: 8px; }
            .region-detail textarea { width: 100%; min-height: 80px; padding: 6px; font-family: 'Segoe UI', sans-serif; font-size: 12px; box-sizing: border-box; }
            .region-metrics table { width: 100%; border-collapse: collapse; margin-top: 6px; }
            .region-metrics th, .region-metrics td { text-align: left; padding: 4px; border-bottom: 1px solid #eee; }
            .region-metrics .metric-disabled { color: #999; }
            .region-spectrum { display: flex; align-items: flex-end; gap: 2px; margin-top: 8px; min-height: 60px; border: 1px solid #eee; padding: 4px; }
            .region-spectrum .bar { width: 6px; background: #64b5f6; transition: opacity 0.2s; }
            .region-spectrum .bar:hover { opacity: 0.7; }
            .region-spectrum .bar-empty { background: #cfd8dc; }
            .region-panel-empty { color: #666; font-style: italic; }
            .region-detail__header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
            .region-detail__header span { font-weight: 600; }
            .region-detail button { padding: 4px 6px; font-size: 11px; cursor: pointer; }
        </style>
    `;

    const debounce = (fn, delay = 200) => {
        let timerId;
        return function (...args) {
            clearTimeout(timerId);
            timerId = setTimeout(() => fn.apply(this, args), delay);
        };
    };

    function escapeHtml(value) {
        if (typeof value !== 'string') return '';
        return value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatTime(timestamp) {
        if (!Number.isFinite(timestamp)) return 'N/A';
        const date = new Date(timestamp);
        return date.toLocaleTimeString([], { hour12: false });
    }

    function formatDuration(ms) {
        if (!Number.isFinite(ms) || ms <= 0) return '0s';
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        const parts = [];
        if (minutes) parts.push(`${minutes}m`);
        parts.push(`${seconds}s`);
        return parts.join('');
    }

    const COMPARISON_METRICS_STYLE = `
        <style>
            .comparison-metrics-table { width: 100%; border-collapse: collapse; font-size: 12px; }
            .comparison-metrics-table th, .comparison-metrics-table td {
                border: 1px solid #ddd;
                padding: 4px 6px;
                text-align: center;
            }
            .comparison-metrics-table th {
                background-color: #f5f5f5;
                font-weight: 600;
            }
            .comparison-metrics-table__placeholder {
                font-style: italic;
                color: #666;
            }
        </style>
    `;

    const COMPARISON_METRICS_EMPTY_HTML = `${COMPARISON_METRICS_STYLE}
        <table class="comparison-metrics-table">
            <thead>
                <tr>
                    <th>Position</th>
                    <th>Duration</th>
                    <th>LAeq</th>
                    <th>LAFmax</th>
                    <th>LA90</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="comparison-metrics-table__placeholder" colspan="5">Select a time slice to populate metrics.</td>
                </tr>
            </tbody>
        </table>`;

    const COMPARISON_SPECTRUM_EMPTY_HTML = `
        <table class="comparison-frequency-table" style="width:100%; border-collapse: collapse; font-size:12px;">
            <thead>
                <tr>
                    <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Position</th>
                    <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Dataset</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td colspan="2" style="border:1px solid #ddd; padding:6px; text-align:center; font-style:italic; color:#666;">
                        Select a time slice to view averaged spectra.
                    </td>
                </tr>
            </tbody>
        </table>
    `;

    const DEFAULT_COMPARISON_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'];

    function buildComparisonMetricsTable(rows) {
        if (!Array.isArray(rows) || !rows.length) {
            return COMPARISON_METRICS_EMPTY_HTML;
        }
        const bodyHtml = rows.map(row => {
            const positionCell = escapeHtml(String(row.positionId || '—'));
            const durationCell = formatDuration(row.durationMs);
            const laeqCell = Number.isFinite(row.laeq) ? row.laeq.toFixed(1) : 'N/A';
            const lafmaxCell = Number.isFinite(row.lafmax) ? row.lafmax.toFixed(1) : 'N/A';
            const la90Cell = row.la90Available && Number.isFinite(row.la90)
                ? row.la90.toFixed(1)
                : 'N/A';
            return `<tr><td>${positionCell}</td><td>${durationCell}</td><td>${laeqCell}</td><td>${lafmaxCell}</td><td>${la90Cell}</td></tr>`;
        }).join('');
        return `${COMPARISON_METRICS_STYLE}
            <table class="comparison-metrics-table">
                <thead>
                    <tr>
                        <th>Position</th>
                        <th>Duration</th>
                        <th>LAeq</th>
                        <th>LAFmax</th>
                        <th>LA90</th>
                    </tr>
                </thead>
                <tbody>${bodyHtml}</tbody>
            </table>`;
    }

    function buildComparisonSpectrumTable(series) {
        if (!Array.isArray(series) || !series.length) {
            return COMPARISON_SPECTRUM_EMPTY_HTML;
        }
        const rowsHtml = series.map(entry => {
            const positionCell = escapeHtml(String(entry?.positionId || '—'));
            const datasetLabel = entry?.dataset === 'log'
                ? 'Log'
                : entry?.dataset === 'overview'
                    ? 'Overview'
                    : 'No Data';
            return `<tr><td style="border:1px solid #ddd; padding:4px;">${positionCell}</td><td style="border:1px solid #ddd; padding:4px;">${datasetLabel}</td></tr>`;
        }).join('');
        return `
            <table class="comparison-frequency-table" style="width:100%; border-collapse: collapse; font-size:12px;">
                <thead>
                    <tr>
                        <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Position</th>
                        <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Dataset</th>
                    </tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
            </table>
        `;
    }

    function ensureComparisonSliceSpans(chart) {
        if (!chart || !chart.model) return null;
        if (chart._comparisonSliceSpans) {
            return chart._comparisonSliceSpans;
        }
        const doc = window.Bokeh?.documents?.[0];
        if (!doc || typeof doc.create_model !== 'function' || typeof doc.add_model !== 'function') {
            return null;
        }
        try {
            const startSpan = doc.add_model(doc.create_model('Span', {
                location: 0,
                dimension: 'height',
                line_color: '#d81b60',
                line_width: 2,
                level: 'overlay',
                visible: false,
                name: `comparison_slice_start_${chart.name}`
            }));
            const endSpan = doc.add_model(doc.create_model('Span', {
                location: 0,
                dimension: 'height',
                line_color: '#1e88e5',
                line_width: 2,
                level: 'overlay',
                visible: false,
                name: `comparison_slice_end_${chart.name}`
            }));
            chart.model.add_layout(startSpan);
            chart.model.add_layout(endSpan);
            chart._comparisonSliceSpans = { start: startSpan, end: endSpan };
            return chart._comparisonSliceSpans;
        } catch (error) {
            console.error('[Renderers] Failed to initialize comparison slice spans:', error);
            return null;
        }
    }

    function setComparisonSliceVisibility(chart, isVisible, start, end) {
        const spans = ensureComparisonSliceSpans(chart);
        if (!spans) return;
        if (isVisible && Number.isFinite(start) && Number.isFinite(end)) {
            spans.start.location = start;
            spans.end.location = end;
            spans.start.visible = true;
            spans.end.visible = true;
        } else {
            spans.start.visible = false;
            spans.end.visible = false;
        }
    }

    function updateComparisonSliceLines(controllersByPosition, isActive, start, end) {
        Object.keys(controllersByPosition || {}).forEach(positionId => {
            const controller = controllersByPosition[positionId];
            if (!controller) return;
            setComparisonSliceVisibility(controller.timeSeriesChart, isActive, start, end);
            setComparisonSliceVisibility(controller.spectrogramChart, isActive, start, end);
        });
    }

    function updateComparisonFrequencyVisualization(models, spectrum) {
        const source = models.comparisonFrequencySource;
        const figure = models.comparisonFrequencyFigure;
        const tableDiv = models.comparisonFrequencyTable;
        const labels = Array.isArray(spectrum?.labels) ? spectrum.labels : [];
        const series = Array.isArray(spectrum?.series) ? spectrum.series : [];
        const palette = Array.isArray(models.comparisonFrequencyPalette) && models.comparisonFrequencyPalette.length
            ? models.comparisonFrequencyPalette
            : DEFAULT_COMPARISON_COLORS;

        if (!source) {
            return;
        }

        if (!labels.length || !series.length) {
            source.data = { x: [], level: [], position: [], color: [] };
            if (figure?.x_range) {
                figure.x_range.factors = [];
            }
            if (tableDiv) {
                tableDiv.text = COMPARISON_SPECTRUM_EMPTY_HTML;
            }
            return;
        }

        const xValues = [];
        const levels = [];
        const positions = [];
        const colors = [];
        const factors = [];

        series.forEach((entry, index) => {
            const positionId = entry?.positionId || `Series ${index + 1}`;
            const color = palette[index % palette.length];
            const values = Array.isArray(entry?.values) ? entry.values : [];
            labels.forEach((label, labelIndex) => {
                const tuple = [String(label ?? `Band ${labelIndex + 1}`), positionId];
                factors.push(tuple);
                xValues.push(tuple);
                const numericValue = Number(values[labelIndex]);
                levels.push(Number.isFinite(numericValue) ? numericValue : null);
                positions.push(positionId);
                colors.push(color);
            });
        });

        source.data = {
            x: xValues,
            level: levels,
            position: positions,
            color: colors
        };
        if (figure?.x_range) {
            figure.x_range.factors = factors;
        }
        if (tableDiv) {
            tableDiv.text = buildComparisonSpectrumTable(series);
        }
    }

    /**
         * Updates the primary data sources of the main charts.
         * This is a HEAVY operation and should only be called when the underlying
         * data view (zoom level, parameter, log/overview) changes.
         */
    function renderPrimaryCharts(state, dataCache) {
        const { controllers } = app.registry;
        if (!controllers?.positions) return;

        for (const posId in controllers.positions) {
            const controller = controllers.positions[posId];
            const tsChartName = `figure_${posId}_timeseries`;
            const specChartName = `figure_${posId}_spectrogram`;

            // Explicitly set visibility for each chart based on the state
            if (controller.timeSeriesChart) {
                controller.timeSeriesChart.setVisible(state.view.chartVisibility[tsChartName]);
            }
            if (controller.spectrogramChart) {
                const isSpecVisible = state.view.chartVisibility[specChartName];
                controller.spectrogramChart.setVisible(isSpecVisible);
                if (controller.spectrogramChart.hoverDivModel) {
                    controller.spectrogramChart.hoverDivModel.visible = isSpecVisible;
                }
            }
            // Update the data for the controller if any of its charts are visible
            controller.updateAllCharts(state, dataCache);
        }
    }

    /**
     * Updates lightweight UI overlays like lines and labels.
     * This is a LIGHT operation and can be called frequently.
     */
    function renderOverlays(state, dataCache) {
        renderTapLines(state);
        renderLabels(state);
        renderHoverEffects(state, dataCache);
        renderSummaryTable(state, dataCache);
    }

    function renderAllVisuals(state, dataCache) {
        // This function is now deprecated. All rendering should go through _dispatchAction.
        // It's kept for backward compatibility during refactoring, but will be removed.
        console.warn("[DEBUG] renderAllVisuals() called. This function is deprecated. Use app.state.dispatchAction instead.");
        renderPrimaryCharts(state, dataCache);
        renderOverlays(state, dataCache);
        renderFrequencyBar(state, dataCache);
    }

    function renderHoverEffects(state, dataCache) {
        const { controllers } = app.registry;
        const SpectrogramChart = app.classes.SpectrogramChart;
        if (!controllers || !SpectrogramChart) return;

        const hoverState = state.interaction.hover;

        // The data processing is now handled in onStateChange, so we just need to render.
        renderFrequencyBar(state, dataCache);

        // Only render hover effects if hover is enabled
        if (state.view.hoverEnabled) {
            controllers.chartsByName.forEach(chart => {
                if (hoverState.isActive) {
                    chart.renderHoverLine(hoverState.timestamp);
                }
                else {
                    chart.hideHoverLine();
                }

                if (chart instanceof SpectrogramChart) {
                    chart.renderHoverDetails(hoverState, dataCache.activeFreqBarData);
                }
            });
        } else {
            // If hover is disabled, hide all hover lines
            controllers.chartsByName.forEach(chart => {
                chart.hideHoverLine();
            });
        }

        // After updating hover effects, re-render the labels with the new context
        renderLabels(state);
    }

    function renderTapLines(state) {
        const { models } = app.registry;
        if (!models?.clickLines) return;

        const { isActive, timestamp } = state.interaction.tap;
        models.clickLines.forEach(line => {
            if (line) {
                line.location = timestamp;
                line.visible = isActive;
            }
        });
    }

    function renderLabels(state) {
        const { controllers } = app.registry;
        if (!controllers?.chartsByName) return;

        const hoverState = state.interaction.hover;
        const tapState = state.interaction.tap;

        // If no interaction is active, hide all labels and exit.
        if (!hoverState.isActive && !tapState.isActive) {
            controllers.chartsByName.forEach(chart => chart.hideLabel());
            return;
        }

        controllers.chartsByName.forEach(chart => {
            // For the chart being hovered, its label is tied to the hover line (only if hover is enabled).
            if (hoverState.isActive && chart.name === hoverState.sourceChartName && state.view.hoverEnabled) {
                const text = chart.getLabelText(hoverState.timestamp);
                chart.renderLabel(hoverState.timestamp, text);
            }
            // For all other charts, their labels are tied to the tap line, if it's active.
            else if (tapState.isActive) {
                const text = chart.getLabelText(tapState.timestamp);
                chart.renderLabel(tapState.timestamp, text);
            }
            // If a chart isn't being hovered and there's no active tap, hide its label.
            else {
                chart.hideLabel();
            }
        });
    }

    /**
    * Iterates through all charts and tells them to synchronize their
    * marker visuals with the central state.
    */
    function renderMarkers(state) {
        const { controllers } = app.registry;
        if (!controllers?.chartsByName) return;

        controllers.chartsByName.forEach(chart => {
            chart.syncMarkers(state.markers.timestamps, state.markers.enabled);
        });
    }

    function buildRegionListHtml(regionList, selectedId) {
        if (!regionList.length) {
            return `<div class="region-panel-empty">No regions defined.</div>`;
        }
        return regionList.map(region => {
            const isSelected = region.id === selectedId;
            const range = `${formatTime(region.start)} – ${formatTime(region.end)}`;
            const duration = formatDuration(Math.max(0, region.end - region.start));
            return `
                <div class="region-entry${isSelected ? ' selected' : ''}" data-region-entry="${region.id}">
                    <div class="region-entry__header">
                        <span>Region ${region.id} – ${escapeHtml(region.positionId || '')}</span>
                        <button type="button" data-region-delete="${region.id}">Delete</button>
                    </div>
                    <div class="region-entry__meta">${range} (${duration})</div>
                </div>
            `;
        }).join('');
    }

    function buildSpectrumHtml(spectrum) {
        if (!spectrum || !Array.isArray(spectrum.labels) || !Array.isArray(spectrum.values) || !spectrum.values.length) {
            return `<div class="region-spectrum region-spectrum--empty">No spectrum data.</div>`;
        }
        const numericValues = spectrum.values.filter(value => Number.isFinite(value));
        if (!numericValues.length) {
            return `<div class="region-spectrum region-spectrum--empty">No spectrum data.</div>`;
        }
        const minVal = Math.min(...numericValues);
        const maxVal = Math.max(...numericValues);
        const range = Math.max(maxVal - minVal, 1);
        const bars = spectrum.labels.map((label, index) => {
            const value = spectrum.values[index];
            if (!Number.isFinite(value)) {
                return `<div class="bar bar-empty" title="${escapeHtml(label)}: N/A"></div>`;
            }
            const height = Math.max(4, ((value - minVal) / range) * 100);
            return `<div class="bar" style="height:${height}%;" title="${escapeHtml(label)}: ${value.toFixed(1)} dB"></div>`;
        }).join('');
        return `<div class="region-spectrum">${bars}</div>`;
    }

    function buildRegionDetailHtml(region, state) {
        if (!region) {
            return `<div class="region-detail-empty">Select a region to view details.</div>`;
        }
        const metrics = region.metrics || {};
        const laeq = Number.isFinite(metrics.laeq) ? metrics.laeq.toFixed(1) : 'N/A';
        const lafmax = Number.isFinite(metrics.lafmax) ? metrics.lafmax.toFixed(1) : 'N/A';
        const la90Value = metrics.la90Available && Number.isFinite(metrics.la90) ? metrics.la90.toFixed(1) : 'N/A';
        const la90Class = metrics.la90Available && Number.isFinite(metrics.la90) ? '' : 'metric-disabled';
        const duration = formatDuration(metrics.durationMs);
        const dataSourceLabel = metrics.dataResolution === 'log' ? 'Log data' : (metrics.dataResolution === 'overview' ? 'Overview data' : 'No data');
        const note = escapeHtml(region.note || '');
        const copyId = region.id;
        const spectrumHtml = buildSpectrumHtml(metrics.spectrum);

        return `
            <div class="region-detail__header">
                <span>Region ${region.id} – ${escapeHtml(region.positionId || '')}</span>
                <button type="button" data-region-copy="${copyId}">Copy line</button>
            </div>
            <div class="region-detail__meta">Duration: ${duration} · Source: ${dataSourceLabel}</div>
            <label>Notes</label>
            <textarea data-region-note="${region.id}" placeholder="Add notes...">${note}</textarea>
            <div class="region-metrics">
                <table>
                    <tr><th>Metric</th><th>Value</th></tr>
                    <tr><td>LAeq</td><td>${laeq} dB</td></tr>
                    <tr><td>LAFmax</td><td>${lafmax} dB</td></tr>
                    <tr><td class="${la90Class}">LAF90</td><td class="${la90Class}">${la90Value === 'N/A' ? 'N/A' : la90Value + ' dB'}</td></tr>
                </table>
            </div>
            <div class="region-spectrum__title">Average Spectrum</div>
            ${spectrumHtml}
        `;
    }

    function buildRegionPanelHtml(regionList, selectedId, state) {
        const listHtml = buildRegionListHtml(regionList, selectedId);
        const selectedRegion = regionList.find(region => region.id === selectedId) || regionList[0] || null;
        const detailHtml = buildRegionDetailHtml(selectedRegion, state);
        return `${REGION_PANEL_STYLE}<div class="region-panel-root"><div class="region-list">${listHtml}</div><div class="region-detail">${detailHtml}</div></div>`;
    }

    const regionPanelObservers = new WeakMap();

    function getPanelRoot(panelDiv) {
        if (!panelDiv) return null;

        const candidates = [];

        if (panelDiv.el) {
            candidates.push(panelDiv.el);
        }

        if (panelDiv.id) {
            const view = window.Bokeh?.index?.[panelDiv.id];
            if (view) {
                if (view.shadow_el) {
                    candidates.push(view.shadow_el);
                }
                if (view.el?.shadowRoot) {
                    candidates.push(view.el.shadowRoot);
                }
                if (view.el) {
                    candidates.push(view.el);
                }
            }
            const hostById = document.getElementById(panelDiv.id);
            if (hostById) {
                candidates.push(hostById);
            }
        }

        const ShadowRootCtor = window.ShadowRoot;

        for (const candidate of candidates) {
            if (!candidate) continue;
            if (ShadowRootCtor && candidate instanceof ShadowRootCtor) {
                return candidate;
            }
            if (ShadowRootCtor && candidate.shadowRoot instanceof ShadowRootCtor) {
                return candidate.shadowRoot;
            }
            if (typeof candidate.querySelector === 'function') {
                return candidate;
            }
        }

        return null;
    }

    function bindRegionPanelListeners(root) {
        if (!root || typeof root.querySelectorAll !== 'function') {
            return;
        }
        root.querySelectorAll('[data-region-entry]').forEach(entry => {
            if (entry.dataset.bound === 'true') return;
            entry.dataset.bound = 'true';
            entry.addEventListener('click', () => {
                const id = Number(entry.getAttribute('data-region-entry'));
                if (Number.isFinite(id)) {
                    const actions = getActions();
                    if (actions?.regionSelect && typeof app.store?.dispatch === 'function') {
                        app.store.dispatch(actions.regionSelect(id));
                    }
                }
            });
        });

        root.querySelectorAll('[data-region-delete]').forEach(button => {
            if (button.dataset.bound === 'true') return;
            button.dataset.bound = 'true';
            button.addEventListener('click', event => {
                event.stopPropagation();
                const id = Number(button.getAttribute('data-region-delete'));
                if (Number.isFinite(id)) {
                    const actions = getActions();
                    if (actions?.regionRemove && typeof app.store?.dispatch === 'function') {
                        app.store.dispatch(actions.regionRemove(id));
                    }
                }
            });
        });

        const noteField = root.querySelector('[data-region-note]');
        if (noteField && noteField.dataset.bound !== 'true') {
            noteField.dataset.bound = 'true';
            const regionId = Number(noteField.getAttribute('data-region-note'));
            const debounced = debounce(value => {
                if (Number.isFinite(regionId)) {
                    const actions = getActions();
                    if (actions?.regionSetNote && typeof app.store?.dispatch === 'function') {
                        app.store.dispatch(actions.regionSetNote(regionId, value));
                    }
                }
            }, 250);
            noteField.addEventListener('input', event => {
                debounced(event.target.value);
            });
        }

        const copyButton = root.querySelector('[data-region-copy]');
        if (copyButton && copyButton.dataset.bound !== 'true') {
            copyButton.dataset.bound = 'true';
            copyButton.addEventListener('click', () => {
                const id = Number(copyButton.getAttribute('data-region-copy'));
                if (Number.isFinite(id)) {
                    handleCopyRegion(id);
                }
            });
        }
    }

    function attachRegionPanelListeners(panelDiv) {
        if (!panelDiv) return;

        const root = getPanelRoot(panelDiv);
        if (root) {
            bindRegionPanelListeners(root);
            return;
        }

        if (typeof window.MutationObserver !== 'function') {
            return;
        }

        if (regionPanelObservers.has(panelDiv)) {
            return;
        }

        const observer = new window.MutationObserver(() => {
            const resolvedRoot = getPanelRoot(panelDiv);
            if (!resolvedRoot) {
                return;
            }

            observer.disconnect();
            regionPanelObservers.delete(panelDiv);
            bindRegionPanelListeners(resolvedRoot);
        });

        const target = document.body || document.documentElement;
        if (!target) {
            return;
        }

        regionPanelObservers.set(panelDiv, observer);
        observer.observe(target, { childList: true, subtree: true });
    }

    function handleCopyRegion(id) {
        if (!regionsModule?.formatRegionSummary) return;
        const state = app.store.getState();
        const region = state?.markers?.regions?.byId?.[id];
        if (!region) return;
        const text = regionsModule.formatRegionSummary(region, region.metrics, region.positionId || '');
        if (navigator?.clipboard?.writeText) {
            navigator.clipboard.writeText(text).catch(error => console.error('Clipboard write failed:', error));
            return;
        }
        const temp = document.createElement('textarea');
        temp.value = text;
        document.body.appendChild(temp);
        temp.select();
        try {
            document.execCommand('copy');
        } catch (error) {
            console.error('Fallback clipboard copy failed:', error);
        }
        document.body.removeChild(temp);
    }

    function renderRegionPanel(panelDiv, regionList, selectedId, state) {
        if (!panelDiv) return;
        const html = buildRegionPanelHtml(regionList, selectedId, state);
        if (panelDiv.text !== html) {
            panelDiv.text = html;
            setTimeout(() => attachRegionPanelListeners(panelDiv), 0);
        } else {
            attachRegionPanelListeners(panelDiv);
        }
    }

    function renderRegions(state, dataCache) {
        const { controllers, models } = app.registry;
        const regionsState = state?.markers?.regions;
        if (!regionsState) return;
        const regionList = regionsState.allIds.map(id => regionsState.byId[id]).filter(Boolean);

        if (controllers?.chartsByName) {
            controllers.chartsByName.forEach(chart => {
                if (typeof chart.syncRegions === 'function') {
                    chart.syncRegions(regionList, regionsState.selectedId);
                }
            });
        }

        renderRegionPanel(models?.regionPanelDiv, regionList, regionsState.selectedId, state);
    }

    function renderFrequencyTable(state, dataCache) {
        const { models } = app.registry;
        if (!models) return;

        const tableDiv = models.freqTableDiv;

        if (!tableDiv) {
            console.error("Frequency table div model not found.");
            return;
        }

        // Get tap context for independent table data processing
        const { isActive, timestamp, position } = state.interaction.tap;

        if (!isActive || !timestamp || !position) {
            tableDiv.text = "<p>Tap on a time series chart to populate this table.</p>";
            return;
        }

        // Get the full spectral data for the tapped position and timestamp
        const activeSpectralData = dataCache.activeSpectralData[position];
        if (!activeSpectralData?.times_ms?.length || !activeSpectralData.frequencies_hz) {
            tableDiv.text = "<p>No frequency data available for selected position.</p>";
            return;
        }

        const closestTimeIdx = activeSpectralData.times_ms.findLastIndex(time => time <= timestamp);
        if (closestTimeIdx === -1) {
            tableDiv.text = "<p>No data available at selected time.</p>";
            return;
        }

        // Apply independent frequency slicing for table's specific range
        const tableFreqRange = models?.config?.freq_table_freq_range_hz;
        let labels, levels;

        if (tableFreqRange && activeSpectralData.frequencies_hz) {
            const [tableMinHz, tableMaxHz] = tableFreqRange;
            const table_start_idx = activeSpectralData.frequencies_hz.findIndex(f => f >= tableMinHz);
            const table_end_idx = activeSpectralData.frequencies_hz.findLastIndex(f => f <= tableMaxHz);

            if (table_start_idx !== -1 && table_end_idx !== -1) {
                // Extract data for the table's frequency range
                const tableFreqCount = (table_end_idx - table_start_idx) + 1;
                labels = activeSpectralData.frequency_labels.slice(table_start_idx, table_end_idx + 1);

                const tableLevelsSlice = new Float32Array(tableFreqCount);
                for (let i = 0; i < tableFreqCount; i++) {
                    const globalFreqIdx = table_start_idx + i;
                    tableLevelsSlice[i] = activeSpectralData.levels_flat_transposed[globalFreqIdx * activeSpectralData.n_times + closestTimeIdx];
                }
                levels = Array.from(tableLevelsSlice);
            } else {
                // Fallback if no frequencies found in table range
                labels = activeSpectralData.frequency_labels;
                const freqDataSlice = new Float32Array(activeSpectralData.n_freqs);
                for (let i = 0; i < activeSpectralData.n_freqs; i++) {
                    freqDataSlice[i] = activeSpectralData.levels_flat_transposed[i * activeSpectralData.n_times + closestTimeIdx];
                }
                levels = Array.from(freqDataSlice);
            }
        } else {
            // Fallback if config is missing - use full range
            labels = activeSpectralData.frequency_labels;
            const freqDataSlice = new Float32Array(activeSpectralData.n_freqs);
            for (let i = 0; i < activeSpectralData.n_freqs; i++) {
                freqDataSlice[i] = activeSpectralData.levels_flat_transposed[i * activeSpectralData.n_times + closestTimeIdx];
            }
            levels = Array.from(freqDataSlice);
        }

        if (!labels || labels.length === 0) {
            tableDiv.text = "<p>Frequency bands not available.</p>";
            return;
        }

        let tableHtml = `
        <style>
            .freq-html-table { border-collapse: collapse; width: 100%; font-size: 0.9em; table-layout: fixed; }
            .freq-html-table th, .freq-html-table td { border: 1px solid #ddd; padding: 6px; text-align: center; white-space: nowrap; }
            .freq-html-table th { background-color: #f2f2f2; font-weight: bold; }
        </style>
        <table class="freq-html-table">
            <tr>`;

        labels.forEach(label => {
            tableHtml += `<th title=\"${label}\">${label}</th>`;
        });

        tableHtml += `</tr><tr>`;

        // Display the levels data
        levels.forEach(level => {
            const levelNum = (level === null || isNaN(level)) ? NaN : parseFloat(level);
            const levelText = isNaN(levelNum) ? 'N/A' : levelNum.toFixed(1);
            tableHtml += `<td>${levelText}</td>`;
        });

        tableHtml += `</tr></table>`;
        tableDiv.text = tableHtml;
    }

    function renderFrequencyBar(state, dataCache) {
        const { models } = app.registry;
        if (!models) return;

        const freqData = dataCache.activeFreqBarData;
        models.barSource.data = {
            'levels': freqData.levels,
            'frequency_labels': freqData.frequency_labels
        };
        models.barChart.x_range.factors = freqData.frequency_labels;
        models.barChart.title.text = `Slice: ${freqData.sourceposition} | ${freqData.param} @ ${new Date(freqData.timestamp).toLocaleTimeString()} | by ${freqData.setBy}`;
        models.barSource.change.emit();

        // Also update the HTML table
        renderFrequencyTable(state, dataCache);
    }

    const PLAYING_BACKGROUND_COLOR = '#e6f0ff'; // A light blue to highlight the active chart
    const DEFAULT_BACKGROUND_COLOR = '#ffffff'; // Standard white background

    function renderControlWidgets(state) {
        const { models, controllers } = app.registry;
        if (!models || !controllers) return;

        const { isPlaying, activePositionId, playbackRate, volumeBoost } = state.audio;

        state.view.availablePositions.forEach(pos => {
            const controller = controllers.positions[pos];
            const controls = models.audio_controls[pos];
            const isThisPositionActive = isPlaying && activePositionId === pos;

            // --- Update Chart Visuals (Title and Background) ---
            if (controller && controller.timeSeriesChart) {
                const tsChart = controller.timeSeriesChart;
                // Base title comes from the state's displayDetails
                const baseTitle = `${pos} - Time History${state.view.displayDetails[pos].line.reason}`;
                tsChart.model.title.text = isThisPositionActive ? `${baseTitle} (▶ PLAYING)` : baseTitle;
                tsChart.model.background_fill_color = isThisPositionActive ? PLAYING_BACKGROUND_COLOR : DEFAULT_BACKGROUND_COLOR;
            }
            if (controller && controller.spectrogramChart) {
                const specChart = controller.spectrogramChart;
                const baseTitle = `${pos} - ${state.view.selectedParameter} Spectrogram${state.view.displayDetails[pos].spec.reason}`;
                specChart.model.title.text = isThisPositionActive ? `${baseTitle} (▶ PLAYING)` : baseTitle;
                specChart.model.background_fill_color = isThisPositionActive ? PLAYING_BACKGROUND_COLOR : DEFAULT_BACKGROUND_COLOR;
            }

            // --- Update Control Widget Visuals ---
            if (controls) {
                // Update Play/Pause button state, label, and color
                if (controls.playToggle.active !== isThisPositionActive) {
                    controls.playToggle.active = isThisPositionActive;
                }
                controls.playToggle.label = isThisPositionActive ? "Pause" : "Play";
                controls.playToggle.button_type = isThisPositionActive ? 'primary' : 'success'; // Blue when playing, green when ready

                // Update playback rate button label (always reflects current rate)
                controls.playbackRateButton.label = `${playbackRate.toFixed(1)}x`;

                // Update volume boost toggle and color
                const isBoostActiveForThisPos = isThisPositionActive && volumeBoost;
                controls.volumeBoostButton.active = isBoostActiveForThisPos;
                controls.volumeBoostButton.button_type = isBoostActiveForThisPos ? 'warning' : 'light'; // 'warning' (orange) when active, 'light' (grey) otherwise
            }
        });
    }

    function renderSummaryTable(state, dataCache) {
        const { models } = app.registry;
        if (!models) return;

        const tableDiv = models.summaryTableDiv;
        if (!tableDiv) {
            console.error("Summary table div model not found.");
            return;
        }

        const { isActive, timestamp } = state.interaction.tap;

        const initialDoc = new DOMParser().parseFromString(tableDiv.text, 'text/html');
        const headerCells = initialDoc.querySelectorAll("thead th:not(.position-header)");
        const parameters = Array.from(headerCells).map(th => th.textContent.trim());

        let tableBodyHtml = '';

        if (!isActive || !timestamp) {
            tableBodyHtml = `<tr><td class='placeholder' colspan='${parameters.length + 1}'>Tap on a time series chart to populate this table.</td></tr>`;
        } else {
            // Add timestamp info row
            const timestampStr = new Date(timestamp).toLocaleString();
            tableBodyHtml += `<tr><td class='timestamp-info' colspan='${parameters.length + 1}'>Values at: ${timestampStr}</td></tr>`;

            state.view.availablePositions.forEach(pos => {
                let rowHtml = `<tr><td class="position-header">${pos}</td>`;
                const activeLineData = dataCache.activeLineData[pos];

                if (activeLineData && activeLineData.Datetime && activeLineData.Datetime.length > 0) {
                    const idx = app.utils.findAssociatedDateIndex(activeLineData, timestamp);

                    if (idx !== -1) {
                        parameters.forEach(param => {
                            const value = activeLineData[param]?.[idx];
                            const formattedValue = (value === null || value === undefined || isNaN(value))
                                ? 'N/A'
                                : parseFloat(value).toFixed(1);
                            rowHtml += `<td>${formattedValue}</td>`;
                        });
                    } else {
                        // Data exists for position, but not at this timestamp
                        parameters.forEach(() => rowHtml += `<td>N/A</td>`);
                    }
                } else {
                    // No data loaded for this position
                    parameters.forEach(() => rowHtml += `<td>No Data</td>`);
                }
                rowHtml += `</tr>`;
                tableBodyHtml += rowHtml;
            });
        }

        // Use regex to replace only the content of the <tbody> tag, preserving the header and style
        const newTableHtml = tableDiv.text.replace(/<tbody>[\s\S]*<\/tbody>/, `<tbody>${tableBodyHtml}</tbody>`);
        tableDiv.text = newTableHtml;
    }

    function renderComparisonMode(state) {
        const { models, controllers } = app.registry;
        if (!models) return;

        const viewState = state?.view || {};
        const comparisonState = viewState.comparison || {};
        const isComparisonActive = viewState.mode === 'comparison';

        if (models.regionPanelLayout) {
            models.regionPanelLayout.visible = !isComparisonActive;
        }
        if (models.comparisonPanelLayout) {
            models.comparisonPanelLayout.visible = isComparisonActive;
        }
        if (models.frequencyBarLayout) {
            models.frequencyBarLayout.visible = !isComparisonActive;
        }
        if (models.comparisonFrequencyLayout) {
            models.comparisonFrequencyLayout.visible = isComparisonActive;
        }

        if (models.startComparisonButton) {
            models.startComparisonButton.disabled = isComparisonActive;
        }
        if (models.comparisonFinishButton) {
            models.comparisonFinishButton.disabled = !isComparisonActive;
        }
        const hasSlice = Number.isFinite(comparisonState.start) && Number.isFinite(comparisonState.end);
        if (models.comparisonMakeRegionsButton) {
            models.comparisonMakeRegionsButton.disabled = !(isComparisonActive && hasSlice);
        }

        const selector = models.comparisonPositionSelector;
        if (selector) {
            selector.disabled = !isComparisonActive;
            const orderedPositions = Array.isArray(models.comparisonPositionIds)
                ? models.comparisonPositionIds
                : [];
            const includedPositions = Array.isArray(comparisonState.includedPositions)
                ? comparisonState.includedPositions
                : [];
            const desiredActive = includedPositions
                .map(positionId => orderedPositions.indexOf(positionId))
                .filter(index => index >= 0)
                .sort((a, b) => a - b);

            const isDifferentLength = selector.active.length !== desiredActive.length;
            const hasDifferentValues = !isDifferentLength && selector.active.some((value, idx) => value !== desiredActive[idx]);
            if (isDifferentLength || hasDifferentValues) {
                selector.active = desiredActive;
            }
        }

        const includedPositions = Array.isArray(comparisonState.includedPositions)
            ? comparisonState.includedPositions
            : [];
        const includedSet = new Set(includedPositions);
        const controllersByPosition = controllers?.positions || {};
        const chartVisibility = viewState.chartVisibility || {};

        Object.keys(controllersByPosition).forEach(positionId => {
            const controller = controllersByPosition[positionId];
            if (!controller || !controller.timeSeriesChart) {
                return;
            }
            const chartName = `figure_${positionId}_timeseries`;
            const baseVisible = Object.prototype.hasOwnProperty.call(chartVisibility, chartName)
                ? Boolean(chartVisibility[chartName])
                : true;
            const shouldBeVisible = !isComparisonActive || includedSet.has(positionId);
            controller.timeSeriesChart.setVisible(baseVisible && shouldBeVisible);
        });

        updateComparisonSliceLines(controllersByPosition, isComparisonActive && hasSlice, comparisonState.start, comparisonState.end);

        if (!isComparisonActive || !hasSlice || !includedPositions.length) {
            if (models.comparisonMetricsDiv) {
                models.comparisonMetricsDiv.text = COMPARISON_METRICS_EMPTY_HTML;
            }
            updateComparisonFrequencyVisualization(models, null);
            return;
        }

        const processor = app.comparisonMetrics?.processComparisonSliceMetrics;
        if (typeof processor !== 'function') {
            return;
        }

        const metricsResult = processor({
            start: comparisonState.start,
            end: comparisonState.end,
            positionIds: includedPositions,
            timeSeriesSources: models.timeSeriesSources,
            preparedGlyphData: models.preparedGlyphData,
            selectedParameter: viewState.selectedParameter
        }) || {};

        if (models.comparisonMetricsDiv) {
            models.comparisonMetricsDiv.text = buildComparisonMetricsTable(metricsResult.metricsRows || []);
        }

        updateComparisonFrequencyVisualization(models, metricsResult.spectrum);
    }

    function renderActiveTool(state, models) {
        const desired = state?.interaction?.activeDragTool === 'box_select' ? 'box_select' : 'pan';
        const charts = Array.isArray(models?.charts) ? models.charts : [];

        charts.forEach(chart => {
            if (!chart?.toolbar) {
                return;
            }

            const tools = Array.isArray(chart.toolbar.tools) ? chart.toolbar.tools : [];
            let panTool = null;
            let boxSelectTool = null;

            tools.forEach(tool => {
                if (!tool) {
                    return;
                }
                const typeName = typeof tool.type === 'string' ? tool.type.toLowerCase() : '';
                const ctorName = typeof tool.constructor?.name === 'string' ? tool.constructor.name.toLowerCase() : '';
                const toolName = typeof tool.tool_name === 'string' ? tool.tool_name.toLowerCase() : '';

                if (!panTool && (typeName === 'pantool' || ctorName === 'pantool' || toolName === 'pan')) {
                    panTool = tool;
                    return;
                }

                const isBoxSelectName = toolName.includes('box select');
                const isBoxSelectType = typeName === 'boxselecttool' || ctorName === 'boxselecttool' || typeName.includes('boxselect') || ctorName.includes('boxselect');
                if (!boxSelectTool && (isBoxSelectName || isBoxSelectType)) {
                    boxSelectTool = tool;
                }
            });

            let targetTool = null;
            if (desired === 'box_select') {
                targetTool = boxSelectTool || panTool || null;
            } else {
                targetTool = panTool || boxSelectTool || null;
            }

            if (targetTool && chart.toolbar.active_drag !== targetTool) {
                chart.toolbar.active_drag = targetTool;
            }
        });
    }

    // Attach the public functions to the global object
    app.renderers = {
        renderPrimaryCharts: renderPrimaryCharts,
        renderOverlays: renderOverlays,
        renderAllVisuals: renderAllVisuals,
        renderHoverEffects: renderHoverEffects,
        renderTapLines: renderTapLines,
        renderLabels: renderLabels,
        renderMarkers: renderMarkers,
        renderRegions: renderRegions,
        renderFrequencyTable: renderFrequencyTable,
        renderFrequencyBar: renderFrequencyBar,
        renderControlWidgets: renderControlWidgets,
        renderSummaryTable: renderSummaryTable,
        renderComparisonMode: renderComparisonMode,
        renderActiveTool: renderActiveTool,
        //formatTime: formatTime
    };
})(window.NoiseSurveyApp);
