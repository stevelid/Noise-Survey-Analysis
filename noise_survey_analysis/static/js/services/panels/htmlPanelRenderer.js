/** Store-to-HTML rendering only. Event binding and restoration live separately. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    const STATE_SYMBOLS = { present: '●', absent: '✕', unchecked: '○' };
    const TAB_LABELS = ['Regions', 'Markers', 'Classifications'];
    const e = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
    const checked = value => value ? ' checked' : '';
    const disabled = value => value ? ' disabled' : '';
    const selected = (a, b) => a === b ? ' selected' : '';
    const color = value => app.annotationModel.normalizeColor(value, '#1e88e5');
    const level = value => Number.isFinite(value) ? value.toFixed(1) : '—';
    const timestamp = value => Number.isFinite(value) ? new Date(value).toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) : '—';

    function duration(region) {
        const seconds = Math.round(app.annotationModel.normalizeAreas(region).reduce((sum, area) => sum + area.end - area.start, 0) / 1000);
        return seconds >= 3600 ? `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    }

    function option(value, label, current) { return `<option value="${e(value)}"${selected(value, current)}>${e(label)}</option>`; }

    function button(action, text, attrs = '') { return `<button type="button" data-action="${action}" ${attrs}>${e(text)}</button>`; }
    // Meter buttons share stable annotation/meter keys for delegated events.

    function meterStrip(region, data, state) {
        const selectors = app.features.regions.selectors;
        return `<div class="nsa-meter-strip" aria-label="Meter states">${data.positions.map(meter => {
            const status = selectors.selectRegionMeterState(state, region, meter);
            const title = app.features.annotationPanel.selectors.selectMeterTitle(state, meter);
            return button('cycle-meter', `${title} ${STATE_SYMBOLS[status]}`, `class="nsa-meter nsa-meter--${status}" data-id="${e(region.id)}" data-meter="${e(meter)}" title="${e(title)}: ${status}${meter === region.positionId ? ' (origin)' : '; click to change'}" aria-label="${e(title)}: ${status}"${disabled(meter === region.positionId)}`);
        }).join('')}</div>`;
    }
    // Calculate only the selected annotation; list rows never request metrics.

    function metricsTable(region, data, state, models, cache) {
        const byMeter = {};
        const rows = data.positions.map(meter => {
            try { byMeter[meter] = app.regions.getRegionMetrics(region, state, cache, models, { positionId: meter }); }
            catch (error) { byMeter[meter] = { dataResolution: 'unavailable' }; }
            const metrics = byMeter[meter] || {};
            return `<tr>
            <th scope="row">${e(app.features.annotationPanel.selectors.selectMeterTitle(state, meter))}</th>
            <td>${level(metrics.laeq)}</td>
            <td>${level(metrics.lafmax)}</td>
            <td>${level(metrics.la90)}</td>
            <td>${e(metrics.dataResolution || 'unavailable')}</td>
            </tr>`;
        }).join('');
        return { byMeter, html: `<div class="nsa-table-wrap">
            <table>
            <caption>Levels, dB</caption>
            <thead>
            <tr>
            <th>Meter</th>
            <th>LAeq</th>
            <th>LAFmax</th>
            <th>LAF90</th>
            <th>Resolution</th>
            </tr>
            </thead>
            <tbody>${rows}</tbody>
            </table>
            </div>
            <p class="nsa-help">Overview and 1 s LAF90 estimates are indicative.</p>` };
    }

    function spectrumTable(metrics) {
        const spectrum = metrics?.spectrum;
        if (!spectrum?.labels?.length) return '<p class="nsa-help">No spectral data for this selection.</p>';
        return `<table>
            <caption>${e(metrics.spectrumParameter || metrics.parameter || 'Spectrum')} · ${e(spectrum.source || metrics.dataResolution)}</caption>
            <thead>
            <tr>
            <th>Band</th>
            <th>Level, dB</th>
            </tr>
            </thead>
            <tbody>${spectrum.labels.map((label, index) => `<tr>
            <th>${e(label)}</th>
            <td>${level(spectrum.values?.[index])}</td>
            </tr>`).join('')}</tbody>
            </table>`;
    }

    function categoryEditor(data) {
        return `<details data-key="category-editor">
            <summary>Categories</summary>
            <p class="nsa-help">Category colours apply unless a region has an override. Deleting a category reassigns its regions to Other.</p>${data.categories.allIds.map(id => {
            const category = data.categories.byId[id];
            return `<div class="nsa-category-editor">
            <input aria-label="Category name" data-key="category-label:${e(id)}" data-action="update-category" data-category="${e(id)}" data-field="label" value="${e(category.label)}">
            <input aria-label="Category colour" data-key="category-color:${e(id)}" data-action="update-category" data-category="${e(id)}" data-field="color" value="${e(color(category.color))}" type="color">${button('delete-category', 'Delete', `data-category="${e(id)}"${disabled(id === 'other')}`)}</div>`;
        }).join('')}<form data-action="create-category">
            <label>New category<input name="label" data-key="new-category-label" required maxlength="100">
            </label>
            <label>Colour<input name="color" data-key="new-category-color" type="color" value="#1e88e5">
            </label>
            <button type="submit">Add category</button>
            </form>
            </details>`;
    }

    function creationStatus(state) {
        const pending = state.interaction?.pendingRegionStart;
        if (pending) return `<p class="nsa-help" role="status">Region start: ${e(timestamp(pending.timestamp))}. Press R again to finish, or Esc to cancel.</p>`;
        return state.regions.addAreaTargetId ? '<p class="nsa-help" role="status">Adding areas to the selected region. Shift+drag another area, then choose Finish adding areas.</p>' : '';
    }

    function exportSettings(data) {
        return `<details data-key="export-settings">
            <summary>Export and background settings</summary>
            <label>Context either side of each area (seconds)
                <input type="number" min="0" step="60" data-key="background-window" data-action="export-setting" data-field="backgroundWindowS" value="${Number(data.ui.backgroundWindowS)}">
            </label>
            <label>Minimum usable context (seconds)
                <input type="number" min="0" step="10" data-key="minimum-context" data-action="export-setting" data-field="minContextS" value="${Number(data.ui.minContextS)}">
            </label>
            <label class="nsa-check">
            <input type="checkbox" data-action="export-setting" data-field="includeAllResolutions"${checked(data.ui.includeAllResolutions)}>Include both log and overview rows</label>
            <p class="nsa-help">Background reports LA90 and LAeq of pooled context samples, excluding regions present at that meter. Standard exports use the best available resolution.</p>
        </details>`;
    }
    // Selected details, review filters/list, then collapsed secondary actions.

    function regionPanel(data, state, models, cache) {
        const region = data.region;
        let originMetrics;
        let details = '<p class="nsa-help">Select a region from the list or a chart. Shift+drag creates a region; R twice marks its bounds.</p>';
        if (region) {
            const categoryOptions = data.categories.allIds.map(id => option(id, data.categories.byId[id].label, region.categoryId)).join('');
            const metrics = data.ui.metricsVisible ? metricsTable(region, data, state, models, cache) : null;
            originMetrics = metrics?.byMeter?.[region.positionId];
            details = `<section class="nsa-selected">
            <h3>Selected region</h3>${meterStrip(region, data, state)}<p class="nsa-help">● Present · ✕ Absent · ○ Unchecked</p>
            <label>Category<select data-key="region-category:${e(region.id)}" data-action="region-category" data-id="${e(region.id)}">${categoryOptions}</select>
            </label>
            <label>Notes<textarea rows="3" data-key="region-note:${e(region.id)}" data-action="region-note" data-id="${e(region.id)}">${e(region.note)}</textarea>
            </label>
            <p class="nsa-help">Notes save on leaving the field or Ctrl+Enter; Esc cancels a draft.</p>
            <div class="nsa-inline">
            <label>Colour override<input data-key="region-color:${e(region.id)}" data-action="region-color" data-id="${e(region.id)}" value="${e(region.color || '')}" placeholder="Category colour" maxlength="30">
            </label>${button('region-color', 'Use category', `data-id="${e(region.id)}" data-value=""`)}</div>
            <div class="nsa-buttons">${button('centre-region', 'Centre')}
                ${button('back', 'Back (B)')}
                ${button('delete-region', 'Delete', 'class="nsa-danger"')}</div>${button('metrics-visible', data.ui.metricsVisible ? 'Hide metrics' : 'Show metrics')}
            ${metrics?.html || ''}</section>`;
        }
        const filters = data.ui.filters;
        const list = data.regions.map(item => `<article class="nsa-region-row${region?.id === item.id ? ' is-selected' : ''}">
            <div class="nsa-region-heading">
            <span class="nsa-swatch" style="background:${e(app.annotationModel.effectiveColor(item, data.categories))}"></span>${button('select-region', item.name || item.note?.trim().slice(0, 80) || data.categories.byId[item.categoryId]?.label || `Region ${item.id}`, `data-id="${e(item.id)}" class="nsa-row-button"`)}</div>
            <div class="nsa-help">${e(timestamp(item.start))} · ${e(duration(item))}</div>${meterStrip(item, data, state)}</article>`).join('');
        const mergeOptions = data.allRegions.filter(item => region && item.id !== region.id && item.positionId === region.positionId).map(item => option(String(item.id), item.note || `Region ${item.id}`, '')).join('');
        return `${creationStatus(state)}
            ${details}
            <section>
            <h3>Regions <small>${data.regions.length} / ${data.allRegions.length}</small>
            </h3>
            <div class="nsa-filters">
            <label>Category<select data-key="filter-category" data-action="filter" data-field="categoryId">${option('', 'All categories', filters.categoryId)}${data.categories.allIds.map(id => option(id, data.categories.byId[id].label, filters.categoryId)).join('')}</select>
            </label>
            <label>Present at<select data-key="filter-meter" data-action="filter" data-field="presentAt">${option('', 'Any meter', filters.presentAt)}${data.positions.map(id => option(id, app.features.annotationPanel.selectors.selectMeterTitle(state, id), filters.presentAt)).join('')}</select>
            </label>
            <label class="nsa-check">
            <input type="checkbox" data-action="filter" data-field="onlyOneMeter"${checked(filters.onlyOneMeter)}>Present at one meter only</label>
            <label class="nsa-check">
            <input type="checkbox" data-action="filter" data-field="hasUnchecked"${checked(filters.hasUnchecked)}>Has unchecked meters</label>
            </div>
            <div class="nsa-annotation-list" data-scroll-key="region-list">${list || '<p class="nsa-help">No regions match these filters.</p>'}</div>
            </section>
            <details data-key="region-secondary">
            <summary>Actions and settings</summary>
            <label>Unchecked bands<select data-key="ghost-mode" data-action="ghost-mode">${[['off', 'Off'], ['selected', 'Selected region only'], ['all', 'All regions']].map(([value, label]) => option(value, label, state.regions.ghostMode || 'selected')).join('')}</select>
            </label>
            <div class="nsa-buttons">${button('add-area', state.regions.addAreaTargetId ? 'Finish adding areas' : 'Add area', disabled(!region))}
                ${button('split-region', 'Split areas', disabled(!region || region.areas.length < 2))}
                ${button('auto-periods', 'Auto Day & Night')}
                ${button('recalculate', 'Recalculate', disabled(!region))}
                ${button('copy-summary', 'Copy summary', disabled(!region))}</div>
            <label>Merge into selected region<select data-key="merge-region" data-action="merge-region"${disabled(!region || !mergeOptions)}>${option('', 'Choose another region…', '')}${mergeOptions}</select>
            </label>
            <details data-key="region-spectrum">
            <summary>Average spectrum</summary>${spectrumTable(originMetrics)}
                ${button('copy-spectrum', 'Copy spectrum', disabled(!region))}</details>${exportSettings(data)}
            ${categoryEditor(data)}</details>`;
    }
    // Marker snapshots stay separate from live region calculations.

    function markerPanel(data, state) {
        const marker = data.marker;
        const rows = marker?.metrics?.broadband || [];
        const spectral = marker?.metrics?.spectral || [];
        const detail = marker ? `<section>
            <h3>Selected marker</h3>
            <p>${e(timestamp(marker.timestamp))}</p>
            <label>Notes<textarea rows="3" data-action="marker-note" data-id="${e(marker.id)}" data-key="marker-note:${e(marker.id)}">${e(marker.note)}</textarea>
            </label>
            <label>Colour<input data-action="marker-color" data-id="${e(marker.id)}" data-key="marker-color:${e(marker.id)}" value="${e(color(marker.color))}">
            </label>
            <div class="nsa-buttons">${button('copy-marker', 'Copy snapshot')}
                ${button('delete-marker', 'Delete marker', `data-id="${e(marker.id)}" class="nsa-danger"`)}</div>
            <table>
            <caption>Saved metric snapshot</caption>
            <thead>
            <tr>
            <th>Meter</th>
            <th>Parameter</th>
            <th>dB</th>
            </tr>
            </thead>
            <tbody>${rows.map(row => `<tr>
            <th>${e(app.features.annotationPanel.selectors.selectMeterTitle(state, row.positionId))}</th>
            <td>${e(row.parameter)}</td>
            <td>${level(row.value)}</td>
            </tr>`).join('')}</tbody>
            </table>${spectral.map(row => `<details data-key="marker-spectrum:${e(row.positionId)}">
            <summary>${e(app.features.annotationPanel.selectors.selectMeterTitle(state, row.positionId))} spectrum</summary>${spectrumTable({ spectrum: row, parameter: marker.metrics.parameter })}</details>`).join('')}</section>` : '<p class="nsa-help">M or double-click adds a marker on every chart. Select one to view its saved snapshot.</p>';
        return `${detail}<h3>Markers <small>${data.markers.length}</small>
            </h3>
            <div class="nsa-annotation-list" data-scroll-key="marker-list">${data.markers.map(item => `<article class="nsa-marker-row${item.id === marker?.id ? ' is-selected' : ''}">
            <span class="nsa-swatch" style="background:${e(color(item.color))}"></span>${button('select-marker', `${timestamp(item.timestamp)} · ${item.note || 'Marker'}`, `data-id="${e(item.id)}" class="nsa-row-button"`)}</article>`).join('')}</div>${data.ui.clearMarkersPending ? `<div class="nsa-confirm" role="alert">Clear all ${data.markers.length} markers? Notes and snapshots will be removed.<div class="nsa-buttons">${button('confirm-clear-markers', 'Clear all markers', 'class="nsa-danger"')}
                ${button('cancel-clear-markers', 'Cancel')}</div>
            </div>` : button('clear-markers', 'Clear all markers…', disabled(!data.markers.length))}`;
    }
    // Passive selection and explicit preview remain separate controls.

    function classificationPanel(data, state) {
        const entry = data.classification;
        const visible = entry && data.classifications.some(item => item.id === entry.id);
        const filters = data.classificationFilters;
        const detail = entry ? `<section>
            <h3>${e(entry.sourceLabel || entry.sourceId)}</h3>
            <p>${e(timestamp(entry.start))} – ${e(timestamp(entry.end))}</p>
            <p>${e(app.features.annotationPanel.selectors.selectMeterTitle(state, entry.positionId))} · Score ${Number.isFinite(entry.confidence) ? entry.confidence.toFixed(2) : 'unscored'} · ${e(entry.state || '')}</p>
            <p>${e(entry.description)}</p>${!visible ? '<p role="status">Selected classification is hidden by current filters.</p>' : ''}<div class="nsa-buttons">${button('preview-classification', 'Preview (P)')}
                ${button('elevate-classification', 'Elevate to Region')}</div>
            </section>` : '<p class="nsa-help">Selecting a classification leaves the cursor, viewport and audio unchanged. P explicitly previews it.</p>';
        return `${detail}<h3>Classifications <small>Showing ${data.classifications.length} of ${data.classificationCounts.total}</small>
            </h3>
            <label>Minimum score <output>${Number(filters.minimumScore || 0).toFixed(2)}</output>
            <input type="range" min="0" max="1" step="0.01" value="${Number(filters.minimumScore || 0)}" data-key="classification-score" data-action="classification-score">
            </label>
            <details data-key="classification-sources">
            <summary>Sources (${data.classificationSources.filter(source => source.visible).length}/${data.classificationSources.length})</summary>
            <div class="nsa-buttons">${button('classification-sources-all', 'All', 'data-value="true"')}
                ${button('classification-sources-all', 'None', 'data-value="false"')}</div>${data.classificationSources.map(source => `<label class="nsa-check">
            <input type="checkbox" data-action="classification-source" data-source="${e(source.sourceId)}"${checked(source.visible)}>
            <span class="nsa-swatch" style="background:${e(color(source.color))}"></span>${e(source.sourceLabel)} (${source.count})</label>`).join('')}</details>${data.classificationCounts.supportingCount ? `<div class="nsa-inline">
            <label class="nsa-check">
            <input type="checkbox" data-action="classification-role" data-field="showDirect"${checked(filters.showDirect !== false)}>Direct</label>
            <label class="nsa-check">
            <input type="checkbox" data-action="classification-role" data-field="showSupporting"${checked(filters.showSupporting)}>Supporting</label>
            </div>` : ''}<label>Sort<select data-action="classification-sort" data-key="classification-sort">${[['start', 'Start'], ['score', 'Score (highest first)'], ['source', 'Source'], ['state', 'State'], ['meter', 'Meter']].map(([value, label]) => option(value, label, data.ui.classificationSort)).join('')}</select>
            </label>
            <div class="nsa-annotation-list" data-scroll-key="classification-list">${data.classifications.map(item => `<article class="nsa-classification-row${entry?.id === item.id ? ' is-selected' : ''}">
            <span class="nsa-swatch" style="background:${e(color(item.color))}"></span>${button('select-classification', `${item.sourceLabel || item.sourceId} · ${timestamp(item.start)} · ${Number.isFinite(item.confidence) ? item.confidence.toFixed(2) : 'unscored'} · ${item.state || ''}`, `data-id="${e(item.id)}" class="nsa-row-button"`)}</article>`).join('') || '<p class="nsa-help">No classifications match these filters.</p>'}</div>`;
    }

    function comparisonPanel(data, state, models, cache) {
        const comparison = state.view.comparison || {};
        const included = comparison.includedPositions || [];
        const hasBounds = Number.isFinite(comparison.start) && Number.isFinite(comparison.end);
        // Reuse the region engine and meter/offset contract for the comparison slice.
        const pseudoRegion = hasBounds && included.length ? { id: 'comparison', positionId: included[0], start: comparison.start, end: comparison.end, areas: [{ start: comparison.start, end: comparison.end }] } : null;
        const metrics = pseudoRegion ? metricsTable(pseudoRegion, { ...data, positions: included }, state, models, cache).html : '<p class="nsa-help">Choose a comparison slice on a chart.</p>';
        return `<h3>Comparison</h3>${data.positions.map(meter => `<label class="nsa-check">
            <input type="checkbox" data-action="comparison-meter" data-meter="${e(meter)}"${checked(included.includes(meter))}>${e(app.features.annotationPanel.selectors.selectMeterTitle(state, meter))}</label>`).join('')}<p>${hasBounds ? `${e(timestamp(comparison.start))} – ${e(timestamp(comparison.end))}` : 'No slice selected'}</p>${metrics}<div class="nsa-buttons">${button('comparison-create', 'Make Region', disabled(!pseudoRegion))}
                ${button('comparison-finish', 'Finish comparison')}</div>`;
    }

    function displaySettings(state) {
        return `<details data-key="annotation-visibility">
            <summary>Annotation visibility</summary>
            <label class="nsa-check">
            <input type="checkbox" data-action="annotation-visibility" data-field="regions"${checked(state.regions?.overlaysVisible !== false)}>Region bands</label>
            <label class="nsa-check">
            <input type="checkbox" data-action="annotation-visibility" data-field="markers"${checked(state.markers?.enabled !== false)}>Marker lines</label>
            <label class="nsa-check">
            <input type="checkbox" data-action="annotation-visibility" data-field="classifications"${checked(state.classifications?.overlaysVisible !== false)}>Classification bands</label>
            <p class="nsa-help">Hiding bands or lines keeps their annotations and lists available.</p>
        </details>`;
    }
    // Rendering produces markup only; event binding lives in htmlPanelEvents.

    function buildHtml(state, models, cache) {
        const data = app.features.annotationPanel.selectors.selectPanelData(state);
        const tab = Math.max(0, Math.min(2, Number(state.view?.activeSidePanelTab) || 0));
        const comparison = state.view?.mode === 'comparison';
        const content = comparison ? comparisonPanel(data, state, models, cache) : tab === 1 ? markerPanel(data, state) : tab === 2 ? classificationPanel(data, state) : regionPanel(data, state, models, cache);
        return `<div class="nsa-annotation-panel" data-nsa-panel="annotations" data-nsa-model="${e(models?.htmlSidePanel?.id || '')}">
            <nav role="tablist" aria-label="Annotations">${TAB_LABELS.map((label, index) => button('tab', label, `role="tab" data-value="${index}" data-key="tab:${index}" aria-selected="${!comparison && tab === index}"${disabled(comparison)}`)).join('')}</nav>
            <div class="nsa-panel-scroll" data-scroll-key="panel">
            <div role="tabpanel" aria-label="${comparison ? 'Comparison' : TAB_LABELS[tab]}">${content}
            ${displaySettings(state)}</div>
            </div>
            </div>`;
    }

    // Retain only the latest paint while a native form interaction owns the
    // existing DOM. The event lifecycle can flush it without reading the store.
    const deferredRenders = new WeakMap();
    function flushDeferredRender(models) {
        const pending = models?.htmlSidePanel && deferredRenders.get(models.htmlSidePanel);
        if (pending) render(pending.state, pending.models, pending.cache);
    }
    function discardDeferredRender(models) {
        if (models?.htmlSidePanel) deferredRenders.delete(models.htmlSidePanel);
    }
    function render(state, models, cache) {
        const model = models?.htmlSidePanel;
        if (!model) return;
        if (app.services.htmlPanelEvents?.shouldDeferRender(models)) {
            deferredRenders.set(model, { state, models, cache });
            return;
        }
        deferredRenders.delete(model);
        const html = buildHtml(state, models, cache);
        if (model.text === html) return;
        app.services.htmlPanelEvents?.capture(models);
        model.text = html;
    }
    app.services = app.services || {};
    app.services.htmlPanelRenderer = { render, flushDeferredRender, discardDeferredRender, buildHtml, escapeHtml: e };
})(window.NoiseSurveyApp);
