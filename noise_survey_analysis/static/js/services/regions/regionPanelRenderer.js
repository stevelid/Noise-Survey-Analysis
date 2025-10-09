// noise_survey_analysis/static/js/services/regions/regionPanelRenderer.js

/**
 * @fileoverview Region panel rendering helpers.
 * These functions update the dedicated Bokeh widgets that compose the region
 * management sidebar. The module remains presentation-only and communicates with
 * the rest of the application through the global NoiseSurveyApp namespace.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const PANEL_STYLE = `
        <style>
            .region-panel-placeholder { font-style: italic; color: #666; margin: 0; }
            .region-metrics { font-family: 'Segoe UI', sans-serif; font-size: 12px; }
            .region-metrics table { width: 100%; border-collapse: collapse; margin-top: 6px; }
            .region-metrics th, .region-metrics td { text-align: left; padding: 4px; border-bottom: 1px solid #eee; }
            .region-detail__header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; margin-bottom: 4px; }
            .region-detail__meta { color: #555; font-size: 11px; margin-bottom: 6px; }
            .metric-disabled { color: #999; }
            .region-frequency { font-family: 'Segoe UI', sans-serif; font-size: 12px; margin-top: 8px; }
            .region-frequency__header { display: flex; justify-content: space-between; align-items: center; font-weight: 600; margin-bottom: 4px; }
            .region-frequency__source { font-size: 11px; color: #555; }
            .region-frequency__table { width: 100%; border-collapse: collapse; }
            .region-frequency__table th, .region-frequency__table td { text-align: left; padding: 4px; border-bottom: 1px solid #eee; }
            .region-frequency__value { font-variant-numeric: tabular-nums; transition: background-color 0.2s ease; }
            .region-frequency__value--empty { color: #999; background: #eceff1; }
            .region-spectrum { display: flex; align-items: flex-end; gap: 2px; margin-top: 8px; min-height: 60px; border: 1px solid #eee; padding: 4px; }
            .region-spectrum .bar { width: 6px; background: #64b5f6; transition: opacity 0.2s; }
            .region-spectrum .bar:hover { opacity: 0.7; }
            .region-spectrum .bar-empty { background: #cfd8dc; }
            .region-segments { margin: 8px 0; padding-left: 18px; font-size: 12px; }
            .region-segments li { margin-bottom: 2px; }
            .region-panel-pending { background: #fff3cd; border-left: 4px solid #ffa000; padding: 6px 8px; margin: 0 0 8px 0; color: #5f4200; font-size: 12px; line-height: 1.4; border-radius: 4px; }
            .region-panel-pending strong { font-weight: 600; }
            .region-panel-pending kbd { display: inline-block; padding: 1px 4px; border-radius: 3px; border: 1px solid #d7ccc8; background: #fff; font-size: 11px; font-family: 'Segoe UI', sans-serif; box-shadow: inset 0 -1px 0 rgba(0,0,0,0.1); }
            .region-panel-mode { background: #eff6ff; border-left: 4px solid #2563eb; border-radius: 6px; color: #1d4ed8; font-size: 12px; line-height: 1.45; margin: 0 0 8px 0; padding: 8px 10px; box-shadow: inset 0 1px 0 rgba(59, 130, 246, 0.1); }
            .region-panel-mode__title { font-weight: 600; margin: 0 0 4px 0; font-size: 12px; color: #1e3a8a; }
            .region-panel-mode p { margin: 4px 0 0 0; color: inherit; }
            .region-panel-mode kbd { display: inline-block; padding: 1px 4px; border-radius: 3px; border: 1px solid rgba(37, 99, 235, 0.35); background: #fff; font-size: 11px; font-family: 'Segoe UI', sans-serif; box-shadow: inset 0 -1px 0 rgba(37, 99, 235, 0.15); color: inherit; }
            .region-panel-info { background: #f8fafc; border-radius: 6px; border-left: 4px solid #3b82f6; color: #1f2937; font-size: 12px; line-height: 1.45; margin: 0 0 8px 0; padding: 8px 10px; }
            .region-panel-info--pending { background: #fff7ed; border-color: #fb923c; color: #5f3700; }
            .region-panel-info__title { font-weight: 600; margin: 0 0 4px 0; font-size: 12px; }
            .region-panel-info p { margin: 4px 0; }
            .region-panel-hints { margin: 6px 0 0 18px; padding: 0; color: inherit; }
            .region-panel-hints li { margin-bottom: 4px; }
            .region-panel-hints kbd, .region-panel-info kbd { display: inline-block; padding: 1px 4px; border-radius: 3px; border: 1px solid #d7ccc8; background: #fff; font-size: 11px; font-family: 'Segoe UI', sans-serif; box-shadow: inset 0 -1px 0 rgba(0,0,0,0.1); color: inherit; }
        </style>
    `;

    const DEFAULT_REGION_COLOR = '#1e88e5';
    const NOTE_PREVIEW_MAX_LENGTH = 40;

    const REGION_TIPS_HTML = `
        <ul class="region-panel-hints">
            <li>Click and drag on a chart to draw a new region instantly.</li>
            <li>Press <kbd>R</kbd> while a tap line is active to toggle make region mode; <kbd>Esc</kbd> cancels it.</li>
            <li>Hold <kbd>Shift</kbd> and click to span a region between the previous tap and your new click.</li>
            <li>Use <kbd>Ctrl</kbd> + click inside a region to remove it, or <kbd>Ctrl</kbd>/<kbd>Alt</kbd> + <kbd>←</kbd>/<kbd>→</kbd> to resize the selected region's edges.</li>
        </ul>
    `;

    const CREATION_MODE_HTML = `${PANEL_STYLE}
        <div class="region-panel-mode">
            <div class="region-panel-mode__title">Create Region mode active</div>
            <p>Press <kbd>R</kbd> again to complete the region at the current cursor position or <kbd>Esc</kbd> to cancel.</p>
        </div>`;

    function normalizeColor(color) {
        if (typeof color === 'string') {
            const trimmed = color.trim();
            if (trimmed) {
                return trimmed;
            }
        }
        return DEFAULT_REGION_COLOR;
    }

    function escapeHtml(value) {
        if (typeof value !== 'string') return '';
        return value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
    
    function getRegionAreas(region) {
        if (!region) return [];
        if (Array.isArray(region.areas) && region.areas.length) {
            return region.areas;
        }
        if (Number.isFinite(region.start) && Number.isFinite(region.end)) {
            return [{ start: region.start, end: region.end }];
        }
        return [];
    }

    function sumAreaDurations(areas) {
        if (!Array.isArray(areas) || !areas.length) return 0;
        return areas.reduce((total, area) => {
            const start = Number(area?.start);
            const end = Number(area?.end);
            if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
                return total;
            }
            return total + (end - start);
        }, 0);
    }

    function formatDateTime(timestamp) {
        if (!Number.isFinite(timestamp)) return 'N/A';
        const date = new Date(timestamp);
        return date.toLocaleString([], {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

    function formatSegmentRange(area) {
        if (!area) return 'N/A';
        return `${formatDateTime(area.start)} – ${formatDateTime(area.end)}`;
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

    function normaliseSpectrum(spectrum) {
        if (!spectrum || typeof spectrum !== 'object') {
            return { labels: [], values: [] };
        }
        const labels = Array.isArray(spectrum.labels)
            ? spectrum.labels
            : Array.isArray(spectrum.bands)
                ? spectrum.bands
                : [];
        const values = Array.isArray(spectrum.values) ? spectrum.values : [];
        return { labels, values };
    }

    function buildSpectrumHtml(spectrum) {
        const { labels, values } = normaliseSpectrum(spectrum);
        if (!labels.length || !values.length) {
            return `${PANEL_STYLE}<p class="region-panel-placeholder">No spectrum data.</p>`;
        }
        const numericValues = values.filter(value => Number.isFinite(value));
        if (!numericValues.length) {
            return `${PANEL_STYLE}<p class="region-panel-placeholder">No spectrum data.</p>`;
        }
        const minVal = Math.min(...numericValues);
        const maxVal = Math.max(...numericValues);
        const range = Math.max(maxVal - minVal, 1);
        const bars = labels.map((label, index) => {
            const value = values[index];
            if (!Number.isFinite(value)) {
                return `<div class="bar bar-empty" title="${escapeHtml(String(label))}: N/A"></div>`;
            }
            const height = Math.max(4, ((value - minVal) / range) * 100);
            const normalized = Math.min(Math.max((value - minVal) / range, 0), 1);
            const color = getHeatColor(normalized);
            return `<div class="bar" style="height:${height}%; background:${color};" title="${escapeHtml(String(label))}: ${value.toFixed(1)} dB"></div>`;
        }).join('');
        return `${PANEL_STYLE}<div class="region-spectrum">${bars}</div>`;
    }

    function getHeatColor(normalized) {
        const clamped = Math.min(Math.max(normalized, 0), 1);
        const hue = 210 - clamped * 160;
        const saturation = 75;
        const lightness = 65 - clamped * 20;
        return `hsl(${hue}, ${saturation}%, ${lightness}%)`;
    }

    function getSpectrumSourceLabel(source) {
        if (source === 'log') return 'Log data';
        if (source === 'overview') return 'Overview data';
        return 'No spectral data';
    }

    function hasSpectrumValues(spectrum) {
        const { values } = normaliseSpectrum(spectrum);
        return values.some(value => Number.isFinite(value));
    }

    function buildFrequencyTableHtml(metrics) {
        const spectrum = metrics?.spectrum || {};
        const { labels, values } = normaliseSpectrum(spectrum);
        const finiteValues = values.filter(value => Number.isFinite(value));
        const sourceLabel = getSpectrumSourceLabel(spectrum?.source);
        if (!labels.length || !finiteValues.length) {
            return `${PANEL_STYLE}<div class="region-frequency"><div class="region-frequency__header"><span>Frequency Bands</span><span class="region-frequency__source">${escapeHtml(sourceLabel)}</span></div><p class='region-panel-placeholder'>No frequency data available.</p></div>`;
        }
        const minVal = Math.min(...finiteValues);
        const maxVal = Math.max(...finiteValues);
        const range = Math.max(maxVal - minVal, 1);
        const rows = labels.map((label, index) => {
            const value = values[index];
            const safeLabel = escapeHtml(String(label));
            if (!Number.isFinite(value)) {
                return `<tr><td>${safeLabel}</td><td class="region-frequency__value region-frequency__value--empty">N/A</td></tr>`;
            }
            const normalized = Math.min(Math.max((value - minVal) / range, 0), 1);
            const color = getHeatColor(normalized);
            return `<tr><td>${safeLabel}</td><td class="region-frequency__value" style="background:${color};">${value.toFixed(1)} dB</td></tr>`;
        }).join('');
        return `${PANEL_STYLE}<div class="region-frequency"><div class="region-frequency__header"><span>Frequency Bands</span><span class="region-frequency__source">${escapeHtml(sourceLabel)}</span></div><table class="region-frequency__table"><tr><th>Band</th><th>LAeq</th></tr>${rows}</table></div>`;
    }

    function buildMetricsHtml(region, metrics) {
        if (!region) {
            return `${PANEL_STYLE}<p class="region-panel-placeholder">Select a region to view metrics.</p>`;
        }
        const safeMetrics = metrics || {};
        const areas = getRegionAreas(region);

        const laeq = Number.isFinite(safeMetrics.laeq) ? `${safeMetrics.laeq.toFixed(1)} dB` : 'N/A';
        const lafmax = Number.isFinite(safeMetrics.lafmax) ? `${safeMetrics.lafmax.toFixed(1)} dB` : 'N/A';
        const la90 = safeMetrics.la90Available && Number.isFinite(safeMetrics.la90)
            ? `${safeMetrics.la90.toFixed(1)} dB`
            : 'N/A';
        const la90Class = safeMetrics.la90Available && Number.isFinite(safeMetrics.la90) ? '' : 'metric-disabled';

        const totalDuration = formatDuration(safeMetrics.durationMs ?? sumAreaDurations(areas));
        const dataSourceLabel = safeMetrics.dataResolution === 'log' ? 'Log data'
            : safeMetrics.dataResolution === 'overview' ? 'Overview data' : 'No data';
        
        const segmentItems = areas.map((area, idx) => {
            const spanMs = Math.max(0, Number(area?.end) - Number(area?.start));
            return `<li>Segment ${idx + 1}: ${formatSegmentRange(area)} (${formatDuration(spanMs)})</li>`;
        }).join('');
        const segmentListHtml = segmentItems ? `<ul class="region-segments">${segmentItems}</ul>` : '';

        return `
            ${PANEL_STYLE}
            <div class="region-metrics">
                <div class="region-detail__meta">Segments: ${areas.length} &bull; Total Duration: ${totalDuration} &bull; Source: ${dataSourceLabel}</div>
                ${segmentListHtml}
                <table>
                    <tr><th>Metric</th><th>Value</th></tr>
                    <tr><td>LAeq</td><td>${laeq}</td></tr>
                    <tr><td>LAFmax</td><td>${lafmax}</td></tr>
                    <tr><td class="${la90Class}">LA90</td><td class="${la90Class}">${la90}</td></tr>
                </table>
            </div>
        `;
    }

    function buildRegionLabel(region, state) {
        const addAreaTargetId = state?.regions?.addAreaTargetId ?? null;
        const rawNote = typeof region?.note === 'string' ? region.note : '';
        const normalizedNote = rawNote.replace(/\s+/g, ' ').trim();
        const hasNote = normalizedNote.length > 0;
        const addingLabel = region?.id === addAreaTargetId ? ' (Adding area...)' : '';

        if (hasNote) {
            const truncated = normalizedNote.length > NOTE_PREVIEW_MAX_LENGTH
                ? `${normalizedNote.slice(0, NOTE_PREVIEW_MAX_LENGTH).trimEnd()}…`
                : normalizedNote;
            return `${escapeHtml(truncated)}${addingLabel}`;
        }

        const positionLabel = region?.positionId ? escapeHtml(String(region.positionId)) : '';
        const areaCount = getRegionAreas(region).length;
        const areaLabel = areaCount > 1 ? ` (${areaCount} areas)` : '';
        return `Region ${region.id} – ${positionLabel}${areaLabel}${addingLabel}`;
    }

    function buildRegionSubtitle(region) {
        if (!region) return '';
        const position = region?.positionId ? `Position ${escapeHtml(String(region.positionId))}` : 'Position N/A';
        const areas = getRegionAreas(region);
        const segmentLabel = areas.length === 1 ? '1 segment' : `${areas.length} segments`;
        const duration = formatDuration(sumAreaDurations(areas));
        return `${position} • ${segmentLabel} • ${duration}`;
    }

    function ensureArrayEquals(a, b) {
        if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) {
            return false;
        }
        for (let i = 0; i < a.length; i++) {
            const left = a[i];
            const right = b[i];
            if (Array.isArray(left) && Array.isArray(right)) {
                if (!ensureArrayEquals(left, right)) return false;
            } else if (left !== right) {
                return false;
            }
        }
        return true;
    }

    function emitColumnDataChange(source) {
        if (!source) {
            return;
        }
        const changeSignal = source.change;
        if (changeSignal && typeof changeSignal.emit === 'function') {
            changeSignal.emit();
        }
        const dataChangeSignal = source.properties?.data?.change;
        if (dataChangeSignal && typeof dataChangeSignal.emit === 'function') {
            dataChangeSignal.emit();
        }
    }

    function shallowEqualObjects(a, b) {
        const left = a || {};
        const right = b || {};
        const leftKeys = Object.keys(left);
        const rightKeys = Object.keys(right);
        if (leftKeys.length !== rightKeys.length) {
            return false;
        }
        for (let i = 0; i < leftKeys.length; i++) {
            const key = leftKeys[i];
            if (left[key] !== right[key]) {
                return false;
            }
        }
        return true;
    }

    function updateRegionTable(regionSource, regionTable, regionList, selectedId, state) {
        if (!regionSource) {
            return { selectedRegion: null, resolvedSelectedId: null };
        }

        const nextData = {
            id: regionList.map(region => region.id ?? null),
            title: regionList.map(region => buildRegionLabel(region, state)),
            subtitle: regionList.map(region => buildRegionSubtitle(region)),
            color: regionList.map(region => normalizeColor(region.color)),
        };

        const currentData = regionSource.data || {};
        const dataKeys = Object.keys(nextData);
        let dataChanged = dataKeys.length !== Object.keys(currentData).length;
        if (!dataChanged) {
            dataChanged = dataKeys.some(key => !ensureArrayEquals(currentData[key] || [], nextData[key]));
        }

        if (dataChanged) {
            regionSource.data = nextData;
            emitColumnDataChange(regionSource);
        }

        const desiredIndex = (() => {
            if (!regionList.length) return -1;
            if (Number.isFinite(selectedId)) {
                const explicitIndex = regionList.findIndex(entry => entry.id === selectedId);
                if (explicitIndex >= 0) return explicitIndex;
            }
            return 0;
        })();

        const desiredSelection = desiredIndex >= 0 ? [desiredIndex] : [];
        const selection = regionSource.selected;
        if (selection) {
            const currentSelection = Array.isArray(selection.indices) ? selection.indices : [];
            if (!ensureArrayEquals(currentSelection, desiredSelection)) {
                if (regionTable) {
                    regionTable.__suppressSelectionDispatch = true;
                }
                selection.indices = desiredSelection;
                if (selection.change && typeof selection.change.emit === 'function') {
                    selection.change.emit();
                }
                if (regionTable) {
                    const releaseGuard = () => { regionTable.__suppressSelectionDispatch = false; };
                    if (typeof queueMicrotask === 'function') {
                        queueMicrotask(releaseGuard);
                    } else {
                        Promise.resolve().then(releaseGuard);
                    }
                }
            }
        }

        if (regionTable) {
            regionTable.disabled = regionList.length === 0;
            regionTable.visible = regionList.length > 0;
        }

        const selectedRegion = desiredIndex >= 0 ? regionList[desiredIndex] : null;
        return {
            selectedRegion,
            resolvedSelectedId: selectedRegion ? selectedRegion.id : null,
        };
    }

    function updateCreationIndicator(indicatorDiv, panelVisible, pendingRegionStart) {
        
        if (!indicatorDiv) {
            return;
        }

        const hasPending = Number.isFinite(pendingRegionStart?.timestamp)
            && typeof pendingRegionStart?.positionId === 'string';
        const shouldShow = panelVisible && hasPending;
        if (indicatorDiv.visible !== shouldShow) {
            indicatorDiv.visible = shouldShow;
        }

        if (!shouldShow) {
            if (indicatorDiv.text !== '') {
                indicatorDiv.text = '';
            }
            return;
        }

        if (indicatorDiv.text !== CREATION_MODE_HTML) {
            indicatorDiv.text = CREATION_MODE_HTML;
        }
    }

    function updateMessage(messageDiv, detailLayout, hasRegions, panelVisible, pendingRegionStart) {
        if (!messageDiv || !detailLayout) return;
        const hasPending = Number.isFinite(pendingRegionStart?.timestamp) && typeof pendingRegionStart?.positionId === 'string';
        const shouldShowMessage = panelVisible;
        const shouldShowDetail = panelVisible && hasRegions;
        messageDiv.visible = shouldShowMessage;
        detailLayout.visible = shouldShowDetail;
        if (!shouldShowMessage) {
            return;
        }

        if (hasPending) {
            const formattedTimestamp = formatDateTime(pendingRegionStart.timestamp);
            const positionLabel = pendingRegionStart.positionId
                ? ` for <strong>${escapeHtml(String(pendingRegionStart.positionId))}</strong>`
                : '';
            const pendingText = `${PANEL_STYLE}
                <div class="region-panel-info region-panel-info--pending">
                    <div class="region-panel-info__title">Make Region mode active</div>
                    <p>Region start pinned at <strong>${formattedTimestamp}</strong>${positionLabel}. Press <kbd>R</kbd> again to set the end point or <kbd>Esc</kbd> to cancel.</p>
                    <p>You can nudge the tap line with the arrow keys before finishing the region.</p>
                    ${REGION_TIPS_HTML}
                </div>`;
            if (messageDiv.text !== pendingText) {
                messageDiv.text = pendingText;
            }
            return;
        }

        if (!hasRegions) {
            const emptyText = `${PANEL_STYLE}
                <div class="region-panel-info">
                    <div class="region-panel-info__title">No regions yet</div>
                    <p>Click on a chart to place the tap line, then press <kbd>R</kbd> to pin the start time. Press <kbd>R</kbd> again at the end time or drag to draw a region.</p>
                    ${REGION_TIPS_HTML}
                </div>`;
            if (messageDiv.text !== emptyText) {
                messageDiv.text = emptyText;
            }
            return;
        }

        const infoText = `${PANEL_STYLE}
            <div class="region-panel-info">
                <div class="region-panel-info__title">Region tips</div>
                <p>Use these shortcuts to refine the selected region.</p>
                ${REGION_TIPS_HTML}
            </div>`;
        if (messageDiv.text !== infoText) {
            messageDiv.text = infoText;
        }
    }

    function updateVisibilityToggle(toggle, regionCount, panelVisible, overlaysVisible) {
        if (!toggle) {
            return;
        }
        const baseLabel = regionCount > 0 ? `Regions (${regionCount})` : 'Regions';
        if (toggle.label !== baseLabel) {
            toggle.label = baseLabel;
        }
        const desiredActive = Boolean(panelVisible);
        if (toggle.active !== desiredActive) {
            toggle.active = desiredActive;
        }
        const desiredType = panelVisible && overlaysVisible ? 'primary' : 'default';
        if (toggle.button_type !== desiredType) {
            toggle.button_type = desiredType;
        }
    }

    function updateAutoButton(autoButton, hasPositions, panelVisible) {
        if (!autoButton) {
            return;
        }
        const disabled = !hasPositions;
        autoButton.disabled = disabled;
        const desiredType = disabled ? 'light' : 'primary';
        if (autoButton.button_type !== desiredType) {
            autoButton.button_type = desiredType;
        }
        autoButton.visible = panelVisible;
    }

    function updateButtons(models, hasSelection, selectedRegion, state, isMergeModeActive, panelVisible) {
        const { copyButton, deleteButton, addAreaButton, mergeButton, mergeSelect, splitButton } = models;
        const addAreaTargetId = state?.regions?.addAreaTargetId ?? null;
        const hasOtherRegions = state?.regions?.allIds.length > 1;
        const mergeOptionsAvailable = Array.isArray(mergeSelect?.options) && mergeSelect.options.length > 0;

        if (copyButton) copyButton.disabled = !hasSelection;
        if (deleteButton) deleteButton.disabled = !hasSelection;
        if (addAreaButton) {
            addAreaButton.disabled = !hasSelection;
            if (selectedRegion) {
                const isActive = addAreaTargetId === selectedRegion.id;
                addAreaButton.label = isActive ? 'Cancel Add Area' : 'Add Area';
                addAreaButton.button_type = isActive ? 'warning' : 'default';
            }
        }
        if (mergeButton) {
            const canStartMerge = hasSelection && hasOtherRegions;
            const canConfirmMerge = hasSelection && hasOtherRegions && mergeOptionsAvailable;
            mergeButton.disabled = isMergeModeActive ? !canConfirmMerge : !canStartMerge;
            const desiredLabel = isMergeModeActive ? 'Confirm Merge' : 'Merge Regions';
            if (mergeButton.label !== desiredLabel) {
                mergeButton.label = desiredLabel;
            }
            const desiredType = isMergeModeActive ? 'primary' : 'default';
            if (mergeButton.button_type !== desiredType) {
                mergeButton.button_type = desiredType;
            }
        }
        if (mergeSelect) {
            const shouldShow = isMergeModeActive && hasSelection && hasOtherRegions;
            mergeSelect.visible = shouldShow;
            mergeSelect.disabled = !(hasSelection && hasOtherRegions && mergeOptionsAvailable);
        }
        if (splitButton) {
            const areaCount = Array.isArray(selectedRegion?.areas) ? selectedRegion.areas.length : 0;
            splitButton.disabled = !(hasSelection && areaCount > 1);
            splitButton.visible = panelVisible;
        }
    }

    function updateMergeSelect(mergeSelect, regionList, selectedId, state, isMergeModeActive) {
        if (!mergeSelect) {
            return { selectedSourceId: null };
        }

        const options = regionList
            .filter(region => region.id !== selectedId)
            .map(region => [String(region.id), buildRegionLabel(region, state)]);

        if (!ensureArrayEquals(mergeSelect.options || [], options)) {
            mergeSelect.options = options;
        }

        if (!options.length || !isMergeModeActive) {
            if (mergeSelect.value !== '') {
                mergeSelect.value = '';
            }
            mergeSelect.disabled = true;
            return { selectedSourceId: null };
        }

        const optionValues = options.map(option => option[0]);
        const nextValue = optionValues.includes(mergeSelect.value) ? mergeSelect.value : options[0][0];
        if (mergeSelect.value !== nextValue) {
            mergeSelect.value = nextValue;
        }

        return { selectedSourceId: Number(mergeSelect.value) || null };
    }

    function updateNoteInput(noteInput, region) {
        if (!noteInput) return;
        if (!region) {
            noteInput.disabled = true;
            if (noteInput.value !== '') noteInput.value = '';
            return;
        }
        noteInput.disabled = false;
        const note = typeof region.note === 'string' ? region.note : '';
        if (noteInput.value !== note) {
            noteInput.value = note;
        }
    }

    function updateColorPicker(colorPicker, region) {
        if (!colorPicker) return;
        if (!region) {
            colorPicker.disabled = true;
            const fallback = DEFAULT_REGION_COLOR;
            if (colorPicker.color !== fallback) {
                colorPicker.color = fallback;
            }
            return;
        }
        colorPicker.disabled = false;
        const color = normalizeColor(region.color);
        if (colorPicker.color !== color) {
            colorPicker.color = color;
        }
    }

    function updateDetailWidgets(panelModels, region, metrics) {
        const { metricsDiv, spectrumDiv, frequencyTableDiv, frequencyCopyButton } = panelModels;
        const metricsHtml = buildMetricsHtml(region, metrics);
        if (metricsDiv && metricsDiv.text !== metricsHtml) {
            metricsDiv.text = metricsHtml;
        }
        const spectrumHtml = buildSpectrumHtml(metrics?.spectrum);
        if (spectrumDiv) {
            spectrumDiv.visible = !!region;
            if (spectrumDiv.text !== spectrumHtml) {
                spectrumDiv.text = spectrumHtml;
            }
        }
        if (metricsDiv) {
            metricsDiv.visible = !!region;
        }
        if (frequencyTableDiv) {
            const frequencyHtml = buildFrequencyTableHtml(metrics);
            frequencyTableDiv.visible = !!region;
            if (frequencyTableDiv.text !== frequencyHtml) {
                frequencyTableDiv.text = frequencyHtml;
            }
        }
        if (frequencyCopyButton) {
            const hasValues = !!region && hasSpectrumValues(metrics?.spectrum);
            frequencyCopyButton.visible = !!region;
            frequencyCopyButton.disabled = !hasValues;
        }
    }

    function renderRegionPanel(panelModels, regionList, selectedId, state, visibilityState = {}) {
        if (!panelModels) return;

        const {
            regionSource,
            regionTable,
            messageDiv,
            creationIndicatorDiv,
            detail,
            noteInput,
            metricsDiv,
            spectrumDiv,
            mergeSelect,
            colorPicker,
            frequencyTableDiv,
            frequencyCopyButton,
            visibilityToggle,

            autoDayNightButton,
            splitButton


        } = panelModels;

        const regionsState = state?.regions || {};
        const isMergeModeActive = !!regionsState.isMergeModeActive;
        const panelVisible = visibilityState.panelVisible !== false;
        const overlaysVisible = visibilityState.overlaysVisible !== false;
        const hasPositions = Number.isFinite(visibilityState.positionCount)
            ? visibilityState.positionCount > 0
            : true;

        const { selectedRegion, resolvedSelectedId } = updateRegionTable(regionSource, regionTable, regionList, selectedId, state);
        updateMergeSelect(mergeSelect, regionList, resolvedSelectedId, state, isMergeModeActive);
        const hasRegions = regionList.length > 0;
        const hasSelection = Boolean(selectedRegion);

        const pendingRegionStart = state?.interaction?.pendingRegionStart || null;

        updateVisibilityToggle(visibilityToggle, regionList.length, panelVisible, overlaysVisible);
        updateAutoButton(autoDayNightButton, hasPositions, panelVisible);
        updateCreationIndicator(creationIndicatorDiv, panelVisible, pendingRegionStart);
        updateMessage(messageDiv, detail, hasRegions, panelVisible, pendingRegionStart);
        updateButtons(panelModels, hasSelection, selectedRegion, state, isMergeModeActive, panelVisible);
        updateNoteInput(noteInput, selectedRegion);

        updateColorPicker(colorPicker, selectedRegion);
        const metrics = selectedRegion && app.regions?.getRegionMetrics
            ? app.regions.getRegionMetrics(selectedRegion, state, app.dataCache, app.registry?.models)
            : null;
        updateDetailWidgets({ metricsDiv, spectrumDiv, frequencyTableDiv, frequencyCopyButton }, selectedRegion, metrics);
    }
    
    app.services = app.services || {};
    app.services.regionPanelRenderer = {
        renderRegionPanel,
    };
})(window.NoiseSurveyApp);
