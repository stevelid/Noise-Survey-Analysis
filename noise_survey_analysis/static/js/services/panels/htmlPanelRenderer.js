/** Store-to-HTML rendering only. Event binding and restoration live separately. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    const STATE_SYMBOLS = { present: '●', absent: '✕', unchecked: '○' };
    const TAB_LABELS = ['Regions', 'Markers', 'Classifications'];
    const HELP = {
        'select-region': 'Open this region for notes, category and measurements.',
        'check-region': 'Tick two or more regions from the same origin meter to merge them.',
        'merge-checked': 'Combine the ticked regions. Their original notes, categories and meter checks are kept for Unmerge.',
        'clear-region-checks': 'Clear the merge selection without changing any regions.',
        'play-region': 'Start audio at the beginning of the selected region on its origin meter.',
        'centre-region': 'Bring the selected region into view on the charts.',
        'back': 'Return to the previous chart view.',
        'region-category': 'Add or remove this category from the selected region. Other clears the other categories.',
        'add-area': 'Add another time interval to the selected region.',
        'split-region': 'Make a separate region for each area. This does not restore records from a merge.',
        'recalculate': 'Refresh the selected region’s calculated measurements.',
        'copy-summary': 'Copy the selected region’s summary to the clipboard.',
        'copy-spectrum': 'Copy the selected region’s origin-meter spectrum to the clipboard.',
        'unmerge-region': 'Restore the original regions saved at merge time. Later edits to the merged region will be replaced.',
        'delete-region': 'Delete the selected region. Undo can restore it.',
        'region-color': 'Set a colour for this region only, overriding its category colour.',
        'auto-periods': 'Create day and night regions automatically.',
        'select-marker': 'Open this marker to edit its note and view the measurements saved when it was made.',
        'copy-marker': 'Copy the selected marker’s saved measurements to the clipboard.',
        'delete-marker': 'Delete the selected marker. Undo can restore it.',
        'clear-markers': 'Remove every marker after confirmation. Undo can restore them.',
        'suggestion-accept': 'Accept this suggestion so it becomes an ordinary annotation (key A).',
        'suggestion-reject': 'Reject this suggestion. It stays under Rejected so it is not proposed again (key D).',
        'suggestion-restore': 'Move this rejected suggestion back to the review queue.',
        'suggestion-accept-all': 'Accept every proposed region in the list below. One Ctrl+Z reverses it.',
        'suggestion-purge': 'Delete all rejected suggestions for good. Ctrl+Z restores them.',
        'suggestion-filter': 'Choose which regions the list shows.',
        'promote-classifications': 'Turn the classification bands currently shown into proposed regions to review.',
    };
    const review = () => app.features.review;
    const AI_TITLE = 'Suggested by an automated reviewer. Accept or reject it; editing it does not accept it.';
    function aiBadge(item) {
        const text = review().helpers.badgeText(item);
        return text ? `<span class="nsa-ai-badge" title="${e(AI_TITLE)}">${e(text)}</span>` : '';
    }
    function suggestionCard(item, kind) {
        if (!review().helpers.isAgent(item) && !item.status) return '';
        const status = review().helpers.statusOf(item);
        const agent = item.agent?.name ? ` · ${e(item.agent.name)}` : '';
        const actions = status === 'proposed'
            ? `${button('suggestion-accept', 'Accept (A)', `data-kind="${kind}" data-id="${e(item.id)}"`)}${button('suggestion-reject', 'Reject (D)', `data-kind="${kind}" data-id="${e(item.id)}"`)}`
            : status === 'rejected' ? button('suggestion-restore', 'Restore to review', `data-kind="${kind}" data-id="${e(item.id)}"`) : '';
        return `<div class="nsa-suggestion-card nsa-suggestion--${status}" data-key="suggestion-card:${kind}:${e(item.id)}">
            <p class="nsa-suggestion-head">${aiBadge(item) || '<span class="nsa-ai-badge">AI</span>'} <strong>${e(status)}</strong>${agent}</p>
            ${item.rationale ? `<p class="nsa-rationale" title="Read-only. Edit the note below instead.">${e(item.rationale)}</p>` : ''}
            ${actions ? `<div class="nsa-buttons">${actions}</div>` : ''}</div>`;
    }
    const e = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
    const checked = value => value ? ' checked' : '';
    const disabled = value => value ? ' disabled' : '';
    const selected = (a, b) => a === b ? ' selected' : '';
    const color = value => app.annotationModel.normalizeColor(value, '#1e88e5');
    function pickerColor(value) {
        const normalized = color(value);
        if (/^#[\da-f]{3,4}$/i.test(normalized)) return '#' + [...normalized.slice(1, 4)].map(part => part + part).join('');
        return /^#[\da-f]{6}(?:[\da-f]{2})?$/i.test(normalized) ? normalized.slice(0, 7) : '#1e88e5';
    }
    const level = value => Number.isFinite(value) ? value.toFixed(1) : '—';
    const timestamp = value => Number.isFinite(value) ? new Date(value).toLocaleString([], { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }) : '—';

    function duration(region) {
        const seconds = Math.round(app.annotationModel.normalizeAreas(region).reduce((sum, area) => sum + area.end - area.start, 0) / 1000);
        return seconds >= 3600 ? `${Math.floor(seconds / 3600)}h ${Math.floor(seconds % 3600 / 60)}m` : `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
    }

    function option(value, label, current) { return `<option value="${e(value)}"${selected(value, current)}>${e(label)}</option>`; }

    function button(action, text, attrs = '') {
        const help = HELP[action];
        return `<button type="button" data-action="${action}" ${attrs}${help ? `${/\btitle\s*=/.test(attrs) ? '' : ` title="${e(help)}"`} aria-description="${e(help)}"` : ''}>${e(text)}</button>`;
    }
    // Meter buttons share stable annotation/meter keys for delegated events.

    function meterStrip(region, data, state) {
        const selectors = app.features.regions.selectors;
        return `<div class="nsa-meter-strip" aria-label="Meter states">${data.positions.map(meter => {
            const status = selectors.selectRegionMeterState(state, region, meter);
            const title = app.features.annotationPanel.selectors.selectMeterTitle(state, meter);
            const explanation = meter === region.positionId
                ? `${title} is the origin meter, so this region is always marked present here.`
                : `${title}: ${status}. Click to cycle between unchecked, present and absent.`;
            return `<button type="button" data-action="cycle-meter" class="nsa-meter nsa-meter--${status}" data-id="${e(region.id)}" data-meter="${e(meter)}" title="${e(explanation)}" aria-label="${e(title)}: ${status}" aria-description="${e(explanation)}"${disabled(meter === region.positionId)}><span>${e(title)}</span><span class="nsa-meter-symbol" aria-hidden="true">${STATE_SYMBOLS[status]}</span></button>`;
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
            <summary title="Add, rename or recolour categories shared by all regions.">Manage categories</summary>
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
            <summary title="Set how much surrounding sound is used to calculate background levels in analysis exports.">Analysis export: background comparison</summary>
            <label title="Look this many seconds before and after each region area for background sound.">Context either side of each area (seconds)
                <input type="number" min="0" step="60" data-key="background-window" data-action="export-setting" data-field="backgroundWindowS" value="${Number(data.ui.backgroundWindowS)}">
            </label>
            <label title="Require this much usable surrounding sound before reporting a background result.">Minimum usable context (seconds)
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
        const meterTitle = id => app.features.annotationPanel.selectors.selectMeterTitle(state, id);
        const label = item => item.name?.trim() || item.note?.trim() || `${timestamp(item.start)} · ${duration(item)}`;
        const checkedIds = data.checkedRegions.map(item => item.id);
        const canMerge = checkedIds.length > 1 && data.checkedRegions.every(item => item.positionId === data.checkedRegions[0].positionId);
        const reviewList = review().selectors.selectReviewList(state);
        const rowHtml = (item, rejected = false) => {
            const categoryIds = item.categoryIds || [item.categoryId];
            const categoryBadges = categoryIds.slice(0, 2).map(id => {
                const category = data.categories.byId[id];
                return `<span class="nsa-category-badge" title="Category: ${e(category?.label || id)}" style="border-color:${e(color(category?.color))}"><span class="nsa-category-dot" style="background:${e(color(category?.color))}"></span>${e(category?.label || id)}</span>`;
            }).join('');
            const proposed = review().helpers.isProposed(item);
            return `<article class="nsa-region-row${region?.id === item.id ? ' is-selected' : ''}${proposed ? ' is-suggestion' : ''}${rejected ? ' is-rejected' : ''}" data-status="${e(review().helpers.statusOf(item))}">
                <input type="checkbox" data-key="check-region:${e(item.id)}" data-action="check-region" data-id="${e(item.id)}" aria-label="Select ${e(label(item))} for merge" title="${e(HELP['check-region'])}" aria-description="${e(HELP['check-region'])}"${checked(checkedIds.includes(item.id))}>
                ${button('select-region', label(item), `data-id="${e(item.id)}" class="nsa-row-button" title="${e(label(item))} · ${e(timestamp(item.start))} · ${e(duration(item))}" aria-pressed="${region?.id === item.id}"`)}
                ${aiBadge(item)}<span class="nsa-origin-badge" title="Origin meter: ${e(meterTitle(item.positionId))}">${e(meterTitle(item.positionId))}</span>
                ${categoryBadges}${categoryIds.length > 2 ? `<span title="${e(categoryIds.map(id => data.categories.byId[id]?.label || id).join(', '))}">+${categoryIds.length - 2}</span>` : ''}
                ${rejected ? button('suggestion-restore', 'Restore', `data-kind="region" data-id="${e(item.id)}"`) : ''}
            </article>`;
        };
        const list = reviewList.shown.map(item => rowHtml(item)).join('');
        const counts = reviewList.counts;
        const chip = (value, text, count) => button('suggestion-filter', `${text} (${count})`, `data-value="${value}" aria-pressed="${reviewList.filter === value}"`);
        const proposedShown = reviewList.shown.filter(review().helpers.isProposed).length;
        const reviewBar = (counts.review || counts.rejected || reviewList.filter !== 'all') ? `<div class="nsa-review-bar" role="group" aria-label="Review filter">
            ${chip('all', 'All', counts.all)}${chip('review', 'To review', counts.review)}${chip('mine', 'Mine', counts.mine)}
            ${proposedShown ? button('suggestion-accept-all', `Accept all shown (${proposedShown})`) : ''}</div>` : '';
        const rejectedGroup = reviewList.rejected.length ? `<details class="nsa-rejected" data-key="rejected-regions"><summary title="Kept so an agent does not propose them again.">Rejected (${reviewList.rejected.length})</summary>
            <div class="nsa-annotation-list" data-scroll-key="rejected-list">${reviewList.rejected.map(item => rowHtml(item, true)).join('')}</div>
            ${button('suggestion-purge', `Delete ${reviewList.rejected.length} rejected`, 'class="nsa-danger"')}</details>` : '';
        const filters = data.ui.filters;
        const listSection = `<section class="nsa-region-list-section"><h3>Regions <small>${reviewList.shown.length} / ${data.allRegions.length - reviewList.rejected.length}</small></h3>${reviewBar}
            <details class="nsa-region-filters" data-key="region-filters"><summary>Filters${Object.values(filters).some(Boolean) ? ' · active' : ''}</summary><div class="nsa-filters">
            <label>Category<select data-key="filter-category" data-action="filter" data-field="categoryId">${option('', 'All categories', filters.categoryId)}${data.categories.allIds.map(id => option(id, data.categories.byId[id].label, filters.categoryId)).join('')}</select></label>
            <label>Present at<select data-key="filter-meter" data-action="filter" data-field="presentAt">${option('', 'Any meter', filters.presentAt)}${data.positions.map(id => option(id, meterTitle(id), filters.presentAt)).join('')}</select></label>
            <label class="nsa-check"><input type="checkbox" data-action="filter" data-field="onlyOneMeter"${checked(filters.onlyOneMeter)}>Present at one meter only</label>
            <label class="nsa-check"><input type="checkbox" data-action="filter" data-field="hasUnchecked"${checked(filters.hasUnchecked)}>Has unchecked meters</label>
            </div></details>
            <div class="nsa-annotation-list" data-scroll-key="region-list">${list || '<p class="nsa-help">No regions match these filters.</p>'}</div>${rejectedGroup}
            ${checkedIds.length ? `<div class="nsa-buttons">${button('merge-checked', `Merge selected (${checkedIds.length})`, disabled(!canMerge))}${button('clear-region-checks', 'Clear selection')}</div><p class="nsa-help">${canMerge ? 'Keeps the active region’s category; combines notes. Originals are retained for Unmerge.' : 'Choose at least two regions from the same origin meter.'} ${checkedIds.length - data.regions.filter(item => checkedIds.includes(item.id)).length ? 'Selection includes regions hidden by filters.' : ''}</p>` : ''}</section>`;
        let selectedHtml = '<p class="nsa-help">Select a region from the list or a chart. Shift+drag creates a region; R twice marks its bounds.</p>';
        if (region) {
            const metrics = data.ui.metricsVisible ? metricsTable(region, data, state, models, cache) : null;
            let originMetrics = metrics?.byMeter?.[region.positionId];
            if (data.ui.spectrumVisible && !originMetrics) {
                try { originMetrics = app.regions.getRegionMetrics(region, state, cache, models, { positionId: region.positionId }); }
                catch (_) { originMetrics = null; }
            }
            selectedHtml = `<section class="nsa-selected" data-key="selected-region:${e(region.id)}">
                <h3>Selected region <span class="nsa-origin-badge">${e(meterTitle(region.positionId))}</span></h3>
                <p class="nsa-help">${e(timestamp(region.start))} · ${e(duration(region))}${region.areas.length > 1 ? ` · ${region.areas.length} areas` : ''}</p>
                ${suggestionCard(region, 'region')}
                <label>Notes<textarea rows="2" data-key="region-note:${e(region.id)}" data-action="region-note" data-id="${e(region.id)}" placeholder="What can you hear?">${e(region.note)}</textarea></label>
                <p class="nsa-help">Save on leaving the field or Ctrl+Enter; Esc cancels.</p>
                <div class="nsa-category-chips" role="group" aria-label="Categories for selected region">${data.categories.allIds.map(id => button('region-category', data.categories.byId[id].label, `data-id="${e(region.id)}" data-key="category-chip:${e(id)}" data-value="${e(id)}" aria-pressed="${(region.categoryIds || [region.categoryId]).includes(id)}" style="--category-color:${e(color(data.categories.byId[id].color))}"`)).join('')}</div>
                <details data-key="inline-category"><summary title="Create a reusable category and assign it to this region.">+ New category</summary><form data-action="create-region-category" class="nsa-inline-category"><input name="label" data-key="inline-category-label" aria-label="New category name" required maxlength="100" placeholder="Category name"><input name="color" type="color" value="#1e88e5" aria-label="New category colour"><button type="submit" title="Save this category and apply it to the selected region.">Add & apply</button></form></details>
                <div class="nsa-buttons">${button('play-region', 'Play from start')}${button('centre-region', 'Show on chart')}${button('back', 'Back (B)')}</div>
                <details data-key="meter-checks:${e(region.id)}"><summary title="Mark whether this event is present, absent or still unchecked at each other meter.">Check other meters</summary>${meterStrip(region, data, state)}<p class="nsa-help">● Present · ✕ Absent · ○ Unchecked. Click to cycle; the origin is always present.</p></details>
                <details data-key="region-measurements" data-action="metrics-visible" data-open-state="${Boolean(data.ui.metricsVisible)}"${data.ui.metricsVisible ? ' open' : ''}><summary aria-expanded="${Boolean(data.ui.metricsVisible)}" title="Show LAeq, LAFmax and LAF90 for this region at each meter.">Measurements</summary><div id="nsa-region-metrics">${metrics?.html || ''}</div></details>
                <details data-key="region-spectrum" data-action="spectrum-visible" data-open-state="${Boolean(data.ui.spectrumVisible)}"${data.ui.spectrumVisible ? ' open' : ''}><summary title="Show the average spectrum for this region at its origin meter.">Average spectrum · ${e(meterTitle(region.positionId))}</summary>${data.ui.spectrumVisible ? spectrumTable(originMetrics) : ''}${button('copy-spectrum', 'Copy spectrum')}</details>
                <details data-key="selected-actions"><summary title="Add or split areas, recalculate, copy or delete the selected region.">More region actions</summary><div class="nsa-buttons">${button('add-area', state.regions.addAreaTargetId ? 'Finish adding areas' : 'Add area')}${button('split-region', 'Split areas', disabled(region.areas.length < 2))}${button('recalculate', 'Recalculate')}${button('copy-summary', 'Copy summary')}${button('delete-region', 'Delete region', 'class="nsa-danger"')}</div>
                ${region.mergeSources?.length ? `<div class="nsa-confirm"><p>Unmerge restores the ${region.mergeSources.length} original records, including notes, categories and meter checks. Edits made since this merge will be replaced. Undo can reverse this.</p>${button('unmerge-region', 'Restore originals (Unmerge)')}</div>` : ''}
                <label>Colour override<input type="color" data-key="region-color:${e(region.id)}" data-action="region-color" data-id="${e(region.id)}" value="${e(pickerColor(app.annotationModel.effectiveColor(region, data.categories)))}" data-picker-colour="true" style="color:${e(color(app.annotationModel.effectiveColor(region, data.categories)))}" aria-label="Region colour override"></label><small>${region.color ? 'Override set' : 'Using category colour'}</small>${button('region-color', 'Use category', `data-id="${e(region.id)}" data-value=""`)}</details>
            </section>`;
        }
        return `${creationStatus(state)}${listSection}${selectedHtml}
            <details data-key="region-secondary" class="nsa-global-settings"><summary title="Settings that apply across the region list, including categories and export.">Global region settings</summary><div class="nsa-global-settings-content">
                ${categoryEditor(data)}
                <details data-key="region-display"><summary title="Control which annotation highlights appear on the charts.">Display options</summary><label>Show unchecked regions on other meters<select data-key="ghost-mode" data-action="ghost-mode" title="Choose whether faint time bands appear for unchecked meters on the selected region, all regions or neither.">${[['off', 'Off'], ['selected', 'Selected region only'], ['all', 'All regions']].map(([value, label]) => option(value, label, state.regions.ghostMode || 'selected')).join('')}</select></label><p class="nsa-help">Faint time bands mark events not yet checked at that meter. This changes display only.</p></details>
                ${exportSettings(data)}${button('auto-periods', 'Auto Day & Night')}</div>
            </details>`;
    }
    // Marker snapshots stay separate from live region calculations.

    function markerPanel(data, state) {
        const marker = data.marker;
        const rows = marker?.metrics?.broadband || [];
        const spectral = marker?.metrics?.spectral || [];
        const liveMarkers = data.markers.filter(item => !review().helpers.isRejected(item));
        const rejectedMarkers = data.markers.filter(review().helpers.isRejected);
        const markerRow = (item, rejected = false) => `<article class="nsa-marker-row${item.id === marker?.id ? ' is-selected' : ''}${review().helpers.isProposed(item) ? ' is-suggestion' : ''}${rejected ? ' is-rejected' : ''}">
            <span class="nsa-swatch" style="background:${e(color(item.color))}" aria-hidden="true"></span>
            <span class="nsa-marker-time">${e(timestamp(item.timestamp))}</span>${aiBadge(item)}
            ${button('select-marker', item.note?.trim() || 'Marker', `data-id="${e(item.id)}" class="nsa-row-button" title="${e(timestamp(item.timestamp))} · ${e(item.note?.trim() || 'Marker')}" aria-pressed="${item.id === marker?.id}"`)}${rejected ? button('suggestion-restore', 'Restore', `data-kind="marker" data-id="${e(item.id)}"`) : ''}</article>`;
        const list = `<section class="nsa-marker-list-section"><h3>Markers <small>${liveMarkers.length}</small></h3>
            <div class="nsa-annotation-list" data-scroll-key="marker-list">${liveMarkers.map(item => markerRow(item)).join('') || '<p class="nsa-help">No markers yet.</p>'}</div>${rejectedMarkers.length ? `<details class="nsa-rejected" data-key="rejected-markers"><summary>Rejected (${rejectedMarkers.length})</summary><div class="nsa-annotation-list" data-scroll-key="rejected-marker-list">${rejectedMarkers.map(item => markerRow(item, true)).join('')}</div></details>` : ''}</section>`;
        const detail = marker ? `<section class="nsa-selected nsa-selected-marker" data-key="selected-marker:${e(marker.id)}">
            <h3>Selected marker</h3>
            <p class="nsa-help">${e(timestamp(marker.timestamp))}</p>
            ${suggestionCard(marker, 'marker')}
            <label>Notes<textarea rows="2" data-action="marker-note" data-id="${e(marker.id)}" data-key="marker-note:${e(marker.id)}" placeholder="What can you hear?">${e(marker.note)}</textarea>
            </label>
            <p class="nsa-help">Save on leaving the field or Ctrl+Enter; Esc cancels.</p>
            <div class="nsa-buttons">${button('copy-marker', 'Copy snapshot')}</div>
            <details data-key="marker-measurements:${e(marker.id)}"><summary title="Measurements saved when this marker was created; they do not change with the current chart view.">Saved measurements</summary>
            <div class="nsa-table-wrap"><table>
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
            </table></div>${spectral.map(row => `<details data-key="marker-spectrum:${e(row.positionId)}">
            <summary>${e(app.features.annotationPanel.selectors.selectMeterTitle(state, row.positionId))} spectrum</summary>${spectrumTable({ spectrum: row, parameter: marker.metrics.parameter })}</details>`).join('')}</details>
            <details data-key="marker-actions:${e(marker.id)}"><summary>More marker actions</summary>
            <label>Colour<input type="color" data-picker-colour="true" style="color:${e(color(marker.color))}" data-action="marker-color" data-id="${e(marker.id)}" data-key="marker-color:${e(marker.id)}" value="${e(pickerColor(marker.color))}"></label>
            ${button('delete-marker', 'Delete marker', `data-id="${e(marker.id)}" class="nsa-danger"`)}</details></section>` : '<p class="nsa-help">M or double-click adds a marker on every chart. Select one to edit its note and view its saved measurements.</p>';
        return `${list}${detail}<details data-key="marker-list-actions"><summary>Marker list actions</summary>${data.ui.clearMarkersPending ? `<div class="nsa-confirm" role="alert">Clear all ${data.markers.length} markers? Notes and snapshots will be removed.<div class="nsa-buttons">${button('confirm-clear-markers', 'Clear all markers', 'class="nsa-danger"')}
                ${button('cancel-clear-markers', 'Cancel')}</div>
            </div>` : button('clear-markers', 'Clear all markers…', disabled(!data.markers.length))}</details>`;
    }
    // Passive selection and explicit preview remain separate controls.

    function classificationPanel(data, state) {
        const entry = data.classification;
        const visible = entry && data.classifications.some(item => item.id === entry.id);
        const filters = data.classificationFilters;
        // Classifications are stored in source time; the charts (and regions) use display time.
        const offsetOf = positionId => Number(state.view?.positionChartOffsets?.[positionId]) || 0;
        const detail = entry ? `<section>
            <h3>${e(entry.sourceLabel || entry.sourceId)}</h3>
            <p>${e(timestamp(entry.start + offsetOf(entry.positionId)))} – ${e(timestamp(entry.end + offsetOf(entry.positionId)))}</p>
            <p>${e(app.features.annotationPanel.selectors.selectMeterTitle(state, entry.positionId))} · Score ${Number.isFinite(entry.confidence) ? entry.confidence.toFixed(2) : 'unscored'} · ${e(entry.state || '')}</p>
            <p>${e(entry.description)}</p>${!visible ? '<p role="status">Selected classification is hidden by current filters.</p>' : ''}<div class="nsa-buttons">${button('preview-classification', 'Preview (P)')}
                ${button('elevate-classification', 'Elevate to Region')}</div>
            </section>` : '<p class="nsa-help">Selecting a classification leaves the cursor, viewport and audio unchanged. P explicitly previews it.</p>';
        return `${detail}<h3>Classifications <small>Showing ${data.classifications.length} of ${data.classificationCounts.total}</small>
            </h3>
            <div class="nsa-buttons">${button('promote-classifications', `Promote shown to suggestions (${data.classifications.length})`, disabled(!data.classifications.length))}</div>
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
            <span class="nsa-swatch" style="background:${e(color(item.color))}"></span>${button('select-classification', `${item.sourceLabel || item.sourceId} · ${timestamp(item.start + offsetOf(item.positionId))} · ${Number.isFinite(item.confidence) ? item.confidence.toFixed(2) : 'unscored'} · ${item.state || ''}`, `data-id="${e(item.id)}" class="nsa-row-button"`)}</article>`).join('') || '<p class="nsa-help">No classifications match these filters.</p>'}</div>`;
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
    function keyboardHelp() {
        // Generated from the live keymap so the list cannot drift from the shortcuts that actually work.
        const rows = app.keymap?.getKeyBindingsForHelp?.() || [];
        const grouped = new Map();
        rows.forEach(row => {
            if (!grouped.has(row.group)) grouped.set(row.group, []);
            grouped.get(row.group).push([row.keys, row.description]);
        });
        // Typing-field keys are handled by the note editor, not the keymap.
        grouped.set('Editing a note', [['Ctrl + Enter', 'Save a note'], ['Esc', 'Cancel a note draft']]);
        const groups = [...grouped.entries()];
        return `<details class="nsa-keyboard-help" data-key="keyboard-help"><summary title="Show keyboard controls for charts and annotations.">Keyboard shortcuts</summary>
            <p class="nsa-help">Use these when you are not typing in a field.</p>
            ${groups.map(([heading, items]) => `<div class="nsa-shortcut-group"><h4>${e(heading)}</h4><dl>${items.map(([keys, description]) => `<div><dt><kbd>${e(keys)}</kbd></dt><dd>${e(description)}</dd></div>`).join('')}</dl></div>`).join('')}
            </details>`;
    }
    // Rendering produces markup only; event binding lives in htmlPanelEvents.

    function buildHtml(state, models, cache) {
        const data = app.features.annotationPanel.selectors.selectPanelData(state);
        const tab = Math.max(0, Math.min(2, Number(state.view?.activeSidePanelTab) || 0));
        const comparison = state.view?.mode === 'comparison';
        const content = comparison ? comparisonPanel(data, state, models, cache) : tab === 1 ? markerPanel(data, state) : tab === 2 ? classificationPanel(data, state) : regionPanel(data, state, models, cache);
        return `<div class="nsa-annotation-panel" data-nsa-panel="annotations" data-nsa-model="${e(models?.htmlSidePanel?.id || '')}">
            <header class="nsa-panel-header"><nav role="tablist" aria-label="Annotations">${TAB_LABELS.map((label, index) => button('tab', label, `role="tab" data-value="${index}" data-key="tab:${index}" aria-selected="${!comparison && tab === index}"${disabled(comparison)}`)).join('')}</nav>${button('sidebar-toggle', '›', 'class="nsa-panel-collapse" aria-label="Hide annotations panel" title="Hide panel"')}</header>
            <div class="nsa-panel-scroll" data-scroll-key="panel">
            ${keyboardHelp()}
            <div role="tabpanel" class="${!comparison && tab === 0 ? 'nsa-region-view' : 'nsa-other-view'}" aria-label="${comparison ? 'Comparison' : TAB_LABELS[tab]}">${content}
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
