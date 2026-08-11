// noise_survey_analysis/static/js/services/classifications/classificationPanelRenderer.js

/**
 * @fileoverview Panel rendering helpers for imported audio classifications.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const PANEL_STYLE = `
        <style>
            .classification-panel-empty { font-style: italic; color: #666; margin: 0; }
            .classification-detail { font-family: 'Segoe UI', sans-serif; font-size: 12px; line-height: 1.45; }
            .classification-detail__title { font-weight: 600; margin-bottom: 4px; }
            .classification-detail__meta { color: #4b5563; margin-bottom: 6px; }
            .classification-detail table { width: 100%; border-collapse: collapse; margin-top: 6px; }
            .classification-detail th, .classification-detail td { text-align: left; padding: 4px; border-bottom: 1px solid #e5e7eb; }
            .classification-detail__description { margin-top: 6px; }
        </style>
    `;

    function escapeHtml(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function ensureArrayEquals(a, b) {
        if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
            return false;
        }
        for (let i = 0; i < a.length; i += 1) {
            if (a[i] !== b[i]) {
                return false;
            }
        }
        return true;
    }

    function emitColumnDataChange(source) {
        if (!source) return;
        if (source.change && typeof source.change.emit === 'function') {
            source.change.emit();
        }
        const dataChangeSignal = source.properties?.data?.change;
        if (dataChangeSignal && typeof dataChangeSignal.emit === 'function') {
            dataChangeSignal.emit();
        }
    }

    function formatTimestamp(timestamp) {
        if (!Number.isFinite(timestamp)) {
            return 'N/A';
        }
        return new Date(timestamp).toLocaleString([], {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

    /**
     * Time-of-day string for the table's Start column, in the SAME browser-local
     * timezone as formatTimestamp() uses for the detail panel. The column sorts
     * on the numeric start_ms field and only renders this text, so the two views
     * can never disagree about what time an event happened.
     */
    function formatTimeOfDay(timestamp) {
        const numeric = Number(timestamp);
        if (!Number.isFinite(numeric)) {
            return '';
        }
        return new Date(numeric).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

    function formatDuration(ms) {
        if (!Number.isFinite(ms) || ms <= 0) return '0s';
        const totalSeconds = Math.floor(ms / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        const parts = [];
        if (hours) parts.push(`${hours}h`);
        if (minutes) parts.push(`${minutes}m`);
        if (seconds || !parts.length) parts.push(`${seconds}s`);
        return parts.join(' ');
    }

    function formatConfidence(value) {
        if (!Number.isFinite(value)) {
            return 'N/A';
        }
        return `${Math.round(value * 100)}%`;
    }

    function buildTimeSpan(entry) {
        if (!entry) return '';
        return `${formatTimestamp(entry.start)} - ${formatTimestamp(entry.end)}`;
    }

    function buildDetailHtml(entry, isSelectedHidden = false) {
        if (isSelectedHidden) {
            return `${PANEL_STYLE}<p class="classification-panel-empty" style="color:#c53030;">Selected classification is hidden by current filters.</p>`;
        }
        if (!entry) {
            return `${PANEL_STYLE}<p class="classification-panel-empty">Select a classification to view details.</p>`;
        }
        const duration = formatDuration(Number(entry.end) - Number(entry.start));
        const scoreStr = formatConfidence(entry.confidence);
        const roleStr = entry.role === 'supporting' ? 'Supporting' : 'Direct';
        const elevated = Number.isFinite(entry.elevatedRegionId)
            ? `Region ${entry.elevatedRegionId}`
            : 'No';
        const description = entry.description
            ? `<div class="classification-detail__description">${escapeHtml(entry.description)}</div>`
            : '';
        return `${PANEL_STYLE}
            <div class="classification-detail">
                <div class="classification-detail__title">${escapeHtml(entry.sourceLabel || entry.sourceId)}</div>
                <div class="classification-detail__meta">${escapeHtml(entry.positionId)} | ${escapeHtml(roleStr)} | ${escapeHtml(entry.state || 'on')} | ${duration}</div>
                <table>
                    <tr><th>Start</th><td>${escapeHtml(formatTimestamp(entry.start))}</td></tr>
                    <tr><th>End</th><td>${escapeHtml(formatTimestamp(entry.end))}</td></tr>
                    <tr><th>Score</th><td>${escapeHtml(scoreStr)}</td></tr>
                    <tr><th>Audio</th><td>${escapeHtml(entry.audioFile || 'N/A')}</td></tr>
                    <tr><th>Elevated</th><td>${escapeHtml(elevated)}</td></tr>
                </table>
                ${description}
            </div>`;
    }

    function updateTable(source, table, classificationList, selectedId) {
        if (!source) {
            return { selectedClassification: null };
        }
        const data = {
            id: classificationList.map(entry => entry.id ?? null),
            source: classificationList.map(entry => entry.sourceLabel || entry.sourceId || ''),
            position: classificationList.map(entry => entry.positionId || ''),
            time_span: classificationList.map(entry => buildTimeSpan(entry)),
            confidence: classificationList.map(entry => formatConfidence(entry.confidence)),
            // null (not -1) for unscored entries: the Score column uses a
            // NumberFormatter, which would render a sentinel -1 as a misleading
            // "-1.00" rather than leaving the cell blank.
            score_value: classificationList.map(entry => Number.isFinite(entry.confidence) ? entry.confidence : null),
            start_ms: classificationList.map(entry => Number(entry.start) || 0),
            start_display: classificationList.map(entry => formatTimeOfDay(entry.start)),
            state: classificationList.map(entry => entry.state || 'on'),
            color: classificationList.map(entry => entry.color || ''),
            role: classificationList.map(entry => entry.role || 'direct'),
        };

        const currentData = source.data || {};
        const keys = Object.keys(data);
        let changed = keys.length !== Object.keys(currentData).length;
        if (!changed) {
            changed = keys.some(key => !ensureArrayEquals(currentData[key] || [], data[key]));
        }
        if (changed) {
            const staleSelection = source.selected;
            const nextLength = data.id.length;
            if (staleSelection && Array.isArray(staleSelection.indices)
                && staleSelection.indices.some(index => index >= nextLength)) {
                if (table) {
                    table.__suppressSelectionDispatch = true;
                    const release = () => { table.__suppressSelectionDispatch = false; };
                    if (typeof queueMicrotask === 'function') queueMicrotask(release);
                    else Promise.resolve().then(release);
                }
                staleSelection.indices = [];
            }
            source.data = data;
            emitColumnDataChange(source);
        }

        const selectedIndex = Number.isFinite(selectedId)
            ? classificationList.findIndex(entry => entry.id === selectedId)
            : -1;
        const desiredSelection = selectedIndex >= 0 ? [selectedIndex] : [];
        const selection = source.selected;
        if (selection) {
            const currentSelection = Array.isArray(selection.indices) ? selection.indices : [];
            if (!ensureArrayEquals(currentSelection, desiredSelection)) {
                if (table) table.__suppressSelectionDispatch = true;
                selection.indices = desiredSelection;
                if (selection.change && typeof selection.change.emit === 'function') {
                    selection.change.emit();
                }
                if (table) {
                    const release = () => { table.__suppressSelectionDispatch = false; };
                    if (typeof queueMicrotask === 'function') queueMicrotask(release);
                    else Promise.resolve().then(release);
                }
            }
        }

        if (table) {
            table.disabled = classificationList.length === 0;
            table.visible = classificationList.length > 0;
        }

        return {
            selectedClassification: selectedIndex >= 0 ? classificationList[selectedIndex] : null
        };
    }

    function renderClassificationPanel(panelModels, classificationsState, fullState = null) {
        if (!panelModels || !classificationsState) {
            return;
        }

        const selectors = app.features?.classifications?.selectors || {};
        const visibleList = fullState && selectors.selectVisibleClassifications
            ? selectors.selectVisibleClassifications(fullState)
            : (Array.isArray(classificationsState.allIds)
                ? classificationsState.allIds.map(id => classificationsState.byId?.[id]).filter(Boolean)
                : []);

        const counts = fullState && selectors.selectClassificationCounts
            ? selectors.selectClassificationCounts(fullState)
            : { total: classificationsState.allIds?.length || 0, visible: visibleList.length };

        const selectedId = Number.isFinite(classificationsState.selectedId)
            ? classificationsState.selectedId
            : null;
        const selectedObjectInState = selectedId !== null ? classificationsState.byId?.[selectedId] : null;

        const panelVisible = classificationsState.panelVisible !== false;
        const overlaysVisible = classificationsState.overlaysVisible !== false;

        const { selectedClassification } = updateTable(
            panelModels.classificationSource,
            panelModels.classificationTable,
            visibleList,
            selectedId
        );

        const isSelectedHidden = selectedObjectInState && !selectedClassification;

        if (panelModels.visibilityToggle) {
            const countLabel = counts.total > 0
                ? (counts.visible < counts.total ? `Classifications (${counts.visible}/${counts.total})` : `Classifications (${counts.total})`)
                : 'Classifications';
            if (panelModels.visibilityToggle.label !== countLabel) {
                panelModels.visibilityToggle.label = countLabel;
            }
            if (panelModels.visibilityToggle.active !== panelVisible) {
                panelModels.visibilityToggle.active = panelVisible;
            }
            const buttonType = panelVisible && overlaysVisible ? 'primary' : 'default';
            if (panelModels.visibilityToggle.button_type !== buttonType) {
                panelModels.visibilityToggle.button_type = buttonType;
            }
        }

        const hasClassifications = visibleList.length > 0;
        if (panelModels.messageDiv) {
            panelModels.messageDiv.visible = panelVisible && !hasClassifications;
            const emptyHtml = `${PANEL_STYLE}<p class="classification-panel-empty">${counts.total > 0 ? 'No classifications match current filters.' : 'No classifications imported.'}</p>`;
            if (panelModels.messageDiv.text !== emptyHtml) {
                panelModels.messageDiv.text = emptyHtml;
            }
        }
        if (panelModels.detail) {
            panelModels.detail.visible = panelVisible && (hasClassifications || isSelectedHidden);
        }
        if (panelModels.detailDiv) {
            const html = buildDetailHtml(selectedClassification || selectedObjectInState, isSelectedHidden);
            if (panelModels.detailDiv.text !== html) {
                panelModels.detailDiv.text = html;
            }
        }
        if (panelModels.elevateButton) {
            panelModels.elevateButton.disabled = !selectedClassification && !selectedObjectInState;
        }
        if (panelModels.deleteButton) {
            panelModels.deleteButton.disabled = !selectedClassification && !selectedObjectInState;
        }
        if (panelModels.exportButton) {
            panelModels.exportButton.disabled = counts.total === 0;
        }
        if (panelModels.previewButton) {
            // Preview needs a selection that is actually visible — previewing a
            // filtered-out event would jump to something the user cannot see.
            panelModels.previewButton.disabled = !selectedClassification;
        }

        renderFilterControls(panelModels, fullState, counts, panelVisible);
    }

    /**
     * Drives the Phase 4 filter widgets (minimum-score slider, collapsible
     * source list, direct/supporting role toggles, "Showing N of M" caption).
     *
     * Widget -> store dispatch is wired in components.py via CustomJS; this
     * function is the store -> widget direction. Writes that would re-enter
     * those callbacks are guarded with `__suppressDispatch`.
     */
    function renderFilterControls(panelModels, fullState, counts, panelVisible) {
        const selectors = app.features?.classifications?.selectors || {};
        if (!fullState || typeof selectors.selectClassificationFilters !== 'function') {
            return;
        }
        const filters = selectors.selectClassificationFilters(fullState);
        const hasAny = counts.total > 0;

        if (panelModels.filterLayout) {
            panelModels.filterLayout.visible = panelVisible && hasAny;
        }

        if (panelModels.minimumScoreSlider) {
            const value = Number.isFinite(filters.minimumScore) ? filters.minimumScore : 0;
            if (panelModels.minimumScoreSlider.value !== value) {
                panelModels.minimumScoreSlider.value = value;
            }
        }

        if (panelModels.showingCountDiv) {
            const text = hasAny ? `Showing ${counts.visible} of ${counts.total}` : '';
            if (panelModels.showingCountDiv.text !== text) {
                panelModels.showingCountDiv.text = text;
            }
        }

        // Source checkbox list
        const sources = typeof selectors.selectClassificationSources === 'function'
            ? selectors.selectClassificationSources(fullState)
            : [];
        if (panelModels.sourceCheckboxGroup) {
            const group = panelModels.sourceCheckboxGroup;
            const labels = sources.map(s => `${s.sourceLabel} (${s.count})`);
            const active = [];
            sources.forEach((s, index) => {
                if (s.visible) active.push(index);
            });

            const labelsChanged = JSON.stringify(group.labels || []) !== JSON.stringify(labels);
            const activeChanged = JSON.stringify(group.active || []) !== JSON.stringify(active);

            if (labelsChanged || activeChanged) {
                group.__suppressDispatch = true;
                if (labelsChanged) group.labels = labels;
                if (activeChanged) group.active = active;
                group.__suppressDispatch = false;
            }
            // Index -> sourceId map consumed by the CustomJS change handler.
            group.__sourceIds = sources.map(s => s.sourceId);
        }

        if (panelModels.sourceFilterToggle) {
            const expanded = Boolean(filters.sourceFilterExpanded);
            if (panelModels.sourceFilterToggle.active !== expanded) {
                panelModels.sourceFilterToggle.__suppressDispatch = true;
                panelModels.sourceFilterToggle.active = expanded;
                panelModels.sourceFilterToggle.__suppressDispatch = false;
            }
            const label = sources.length
                ? `Sources (${sources.filter(s => s.visible).length}/${sources.length})`
                : 'Sources';
            if (panelModels.sourceFilterToggle.label !== label) {
                panelModels.sourceFilterToggle.label = label;
            }
        }
        if (panelModels.sourceFilterLayout) {
            panelModels.sourceFilterLayout.visible = panelVisible
                && hasAny
                && Boolean(filters.sourceFilterExpanded);
        }

        // Role filter — hidden entirely when nothing supporting was imported,
        // per the plan (supporting events are a diagnostic import, not normal).
        const hasSupporting = counts.supportingCount > 0;
        if (panelModels.roleFilterLayout) {
            panelModels.roleFilterLayout.visible = panelVisible && hasSupporting;
        }
        if (panelModels.roleCheckboxGroup && hasSupporting) {
            const group = panelModels.roleCheckboxGroup;
            const active = [];
            if (filters.showDirect !== false) active.push(0);
            if (filters.showSupporting) active.push(1);
            if (JSON.stringify(group.active || []) !== JSON.stringify(active)) {
                group.__suppressDispatch = true;
                group.active = active;
                group.__suppressDispatch = false;
            }
        }
    }

    app.services = app.services || {};
    app.services.classificationPanelRenderer = {
        renderClassificationPanel,
        renderFilterControls,
        buildDetailHtml
    };
})(window.NoiseSurveyApp);
