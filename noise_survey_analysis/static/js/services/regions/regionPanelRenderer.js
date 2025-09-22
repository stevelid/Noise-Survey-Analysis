// noise_survey_analysis/static/js/services/regions/regionPanelRenderer.js

/**
 * @fileoverview Region panel rendering helpers extracted from services/renderers.js.
 * These functions focus on building DOM markup and wiring listeners for the region
 * management sidebar. They remain presentation-only and interact with the rest of the
 * application through the global NoiseSurveyApp namespace.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

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

    const regionPanelObservers = new WeakMap();
    const regionListObservers = new WeakMap();

    function debounce(fn, delay = 200) {
        let timerId;
        return function (...args) {
            clearTimeout(timerId);
            timerId = setTimeout(() => fn.apply(this, args), delay);
        };
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

    function buildRegionListHtml(regionList, selectedId) {
        if (!Array.isArray(regionList) || !regionList.length) {
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
        const dataSourceLabel = metrics.dataResolution === 'log' ? 'Log data'
            : (metrics.dataResolution === 'overview' ? 'Overview data' : 'No data');
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
        const selectedRegion = Array.isArray(regionList)
            ? regionList.find(region => region.id === selectedId) || regionList[0] || null
            : null;
        const detailHtml = buildRegionDetailHtml(selectedRegion, state);
        return `${REGION_PANEL_STYLE}<div class="region-panel-root"><div class="region-list">${listHtml}</div><div class="region-detail">${detailHtml}</div></div>`;
    }

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

        const directPanelRoot = document.querySelector('.region-panel-root');
        if (directPanelRoot) {
            candidates.push(directPanelRoot);
            const rootNode = directPanelRoot.getRootNode?.();
            if (rootNode && rootNode !== directPanelRoot) {
                candidates.push(rootNode);
            }
        }

        const directRegionList = document.querySelector('.region-list');
        if (directRegionList) {
            const panelRoot = directRegionList.closest?.('.region-panel-root');
            if (panelRoot) {
                candidates.push(panelRoot);
            }
            const rootNode = directRegionList.getRootNode?.();
            if (rootNode && rootNode !== directRegionList) {
                candidates.push(rootNode);
            }
        }

        const potentialHosts = document.querySelectorAll?.('.bk-Column') || [];
        potentialHosts.forEach(host => {
            if (host?.shadowRoot) {
                candidates.push(host.shadowRoot);
            }
            candidates.push(host);
        });

        const ShadowRootCtor = window.ShadowRoot;

        for (const candidate of candidates) {
            if (!candidate) continue;
            if (typeof Node !== 'undefined' && candidate.nodeType === Node.DOCUMENT_NODE) {
                continue;
            }
            if (ShadowRootCtor && candidate instanceof ShadowRootCtor) {
                return candidate;
            }
            if (ShadowRootCtor && candidate.shadowRoot instanceof ShadowRootCtor) {
                return candidate.shadowRoot;
            }
            if (typeof candidate.querySelector === 'function') {
                const panelRoot = candidate.classList?.contains('region-panel-root')
                    ? candidate
                    : candidate.querySelector('.region-panel-root');
                if (panelRoot) {
                    return panelRoot;
                }
            }
        }

        return null;
    }

    function observeRegionListMutations(root) {
        if (!root || typeof root.querySelector !== 'function') {
            return;
        }
        if (typeof window.MutationObserver !== 'function') {
            return;
        }

        const regionList = root.querySelector('.region-list');
        if (!regionList || regionListObservers.has(regionList)) {
            return;
        }

        const observer = new window.MutationObserver(() => {
            bindRegionPanelListeners(root);
        });

        regionListObservers.set(regionList, observer);
        observer.observe(regionList, { childList: true, subtree: true });
    }

    function handleCopyRegion(id) {
        const regionsModule = app.regions;
        if (!regionsModule?.formatRegionSummary) return;
        const state = app.store?.getState ? app.store.getState() : null;
        const region = state?.regions?.byId?.[id];
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
            observeRegionListMutations(root);
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
            observeRegionListMutations(resolvedRoot);
        });

        const target = document.body || document.documentElement;
        if (!target) {
            return;
        }

        regionPanelObservers.set(panelDiv, observer);
        observer.observe(target, { childList: true, subtree: true });
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

    app.services = app.services || {};
    app.services.regionPanelRenderer = {
        buildRegionListHtml,
        buildRegionDetailHtml,
        buildRegionPanelHtml,
        buildSpectrumHtml,
        bindRegionPanelListeners,
        observeRegionListMutations,
        attachRegionPanelListeners,
        handleCopyRegion,
        getPanelRoot,
        renderRegionPanel,
    };
})(window.NoiseSurveyApp);
