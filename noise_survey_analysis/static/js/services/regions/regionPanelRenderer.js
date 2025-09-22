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
            .region-spectrum { display: flex; align-items: flex-end; gap: 2px; margin-top: 8px; min-height: 60px; border: 1px solid #eee; padding: 4px; }
            .region-spectrum .bar { width: 6px; background: #64b5f6; transition: opacity 0.2s; }
            .region-spectrum .bar:hover { opacity: 0.7; }
            .region-spectrum .bar-empty { background: #cfd8dc; }
            .region-segments { margin: 8px 0; padding-left: 18px; font-size: 12px; }
            .region-segments li { margin-bottom: 2px; }
        </style>
    `;

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

    function formatTime(timestamp) {
        if (!Number.isFinite(timestamp)) return 'N/A';
        const date = new Date(timestamp);
        return date.toLocaleTimeString([], { hour12: false });
    }
    
    function formatSegmentRange(area) {
        if (!area) return 'N/A';
        return `${formatTime(area.start)} – ${formatTime(area.end)}`;
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
            return `<div class="bar" style="height:${height}%;" title="${escapeHtml(String(label))}: ${value.toFixed(1)} dB"></div>`;
        }).join('');
        return `${PANEL_STYLE}<div class="region-spectrum">${bars}</div>`;
    }

    function buildMetricsHtml(region) {
        if (!region) {
            return `${PANEL_STYLE}<p class="region-panel-placeholder">Select a region to view metrics.</p>`;
        }
        const metrics = region.metrics || {};
        const areas = getRegionAreas(region);
        
        const laeq = Number.isFinite(metrics.laeq) ? `${metrics.laeq.toFixed(1)} dB` : 'N/A';
        const lafmax = Number.isFinite(metrics.lafmax) ? `${metrics.lafmax.toFixed(1)} dB` : 'N/A';
        const la90 = metrics.la90Available && Number.isFinite(metrics.la90)
            ? `${metrics.la90.toFixed(1)} dB`
            : 'N/A';
        const la90Class = metrics.la90Available && Number.isFinite(metrics.la90) ? '' : 'metric-disabled';

        const totalDuration = formatDuration(metrics.durationMs ?? sumAreaDurations(areas));
        const dataSourceLabel = metrics.dataResolution === 'log' ? 'Log data'
            : metrics.dataResolution === 'overview' ? 'Overview data' : 'No data';
        
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
        const positionLabel = region?.positionId ? escapeHtml(String(region.positionId)) : '';
        const areaCount = getRegionAreas(region).length;
        const areaLabel = areaCount > 1 ? ` (${areaCount} areas)` : '';
        const addingLabel = region.id === addAreaTargetId ? ' (Adding area...)' : '';
        return `Region ${region.id} – ${positionLabel}${areaLabel}${addingLabel}`;
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

    function updateSelect(select, regionList, selectedId, state) {
        if (!select) {
            return { selectedRegion: null, selectedValue: '' };
        }

        const options = regionList.map(region => [String(region.id), buildRegionLabel(region, state)]);
        if (!ensureArrayEquals(select.options || [], options)) {
            select.options = options;
        }

        const stringSelectedId = Number.isFinite(selectedId) ? String(selectedId) : '';
        const newValue = stringSelectedId || (options[0]?.[0] ?? '');
        if (select.value !== newValue) {
            select.value = newValue;
        }

        select.disabled = options.length === 0;
        const region = regionList.find(entry => String(entry.id) === select.value) || null;
        return { selectedRegion: region, selectedValue: select.value };
    }

    function updateMessage(messageDiv, detailLayout, hasRegions) {
        if (!messageDiv || !detailLayout) return;
        messageDiv.visible = !hasRegions;
        detailLayout.visible = hasRegions;
        if (!hasRegions) {
            const text = `${PANEL_STYLE}<div class='region-panel-empty'>No regions defined.</div>`;
            if (messageDiv.text !== text) {
                messageDiv.text = text;
            }
        }
    }

    function updateButtons(models, hasSelection, selectedRegion, state) {
        const { copyButton, deleteButton, addAreaButton, mergeButton } = models;
        const addAreaTargetId = state?.regions?.addAreaTargetId ?? null;
        const hasOtherRegions = state?.regions?.allIds.length > 1;

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
            mergeButton.disabled = !(hasSelection && hasOtherRegions);
        }
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

    function updateDetailWidgets(panelModels, region) {
        const { metricsDiv, spectrumDiv } = panelModels;
        const metricsHtml = buildMetricsHtml(region);
        if (metricsDiv && metricsDiv.text !== metricsHtml) {
            metricsDiv.text = metricsHtml;
        }
        const spectrumHtml = buildSpectrumHtml(region?.metrics?.spectrum);
        if (spectrumDiv) {
            spectrumDiv.visible = !!region;
            if (spectrumDiv.text !== spectrumHtml) {
                spectrumDiv.text = spectrumHtml;
            }
        }
        if (metricsDiv) {
            metricsDiv.visible = !!region;
        }
    }

    function renderRegionPanel(panelModels, regionList, selectedId, state) {
        if (!panelModels) return;

        const { select, messageDiv, detail, noteInput, metricsDiv, spectrumDiv } = panelModels;

        const { selectedRegion } = updateSelect(select, regionList, selectedId, state);
        const hasRegions = regionList.length > 0;
        const hasSelection = Boolean(selectedRegion);

        updateMessage(messageDiv, detail, hasRegions);
        updateButtons(panelModels, hasSelection, selectedRegion, state);
        updateNoteInput(noteInput, selectedRegion);
        updateDetailWidgets({ metricsDiv, spectrumDiv }, selectedRegion);
    }
    
    app.services = app.services || {};
    app.services.regionPanelRenderer = {
        renderRegionPanel,
    };
})(window.NoiseSurveyApp);