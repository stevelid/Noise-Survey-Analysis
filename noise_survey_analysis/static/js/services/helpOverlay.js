// noise_survey_analysis/static/js/services/helpOverlay.js

/**
 * @fileoverview "?" help overlay. The keyboard table is generated from
 * app.keymap.getKeyBindingsForHelp(), so keys registered by any module (A / D, { } ...) appear
 * without edits here. Esc, a click outside, or "?" closes it.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const MOUSE_ROWS = [
        ['Wheel over a chart', 'Zoom when the page does not scroll, or with Ctrl held, or with wheel lock (W); otherwise scroll the page'],
        ['Shift + wheel', 'Pan the time axis'],
        ['Ctrl + wheel', 'Always zoom (the browser page zoom is not triggered)'],
        ['Drag', 'Pan; hold Shift to drag a selection box'],
        ['Click / double-click', 'Move the tap line / add a marker'],
        ['Header buttons', 'Offsets, move position up / down, collapse the spectrogram to a strip']
    ];

    let overlayEl = null;

    function escapeHtml(text) {
        return String(text ?? '').replace(/[&<>"']/g, ch => (
            { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
    }

    function groupRows(rows) {
        const groups = new Map();
        rows.forEach(row => {
            if (!groups.has(row.group)) groups.set(row.group, []);
            groups.get(row.group).push(row);
        });
        return groups;
    }

    function buildHtml() {
        const rows = app.keymap?.getKeyBindingsForHelp?.() || [];
        const sections = [];
        groupRows(rows).forEach((items, group) => {
            const body = items.map(item =>
                `<tr><td class="k"><kbd>${escapeHtml(item.keys)}</kbd></td><td>${escapeHtml(item.description)}</td></tr>`
            ).join('');
            sections.push(`<section><h3>${escapeHtml(group)}</h3><table>${body}</table></section>`);
        });
        const mouse = MOUSE_ROWS.map(([k, d]) =>
            `<tr><td class="k"><kbd>${escapeHtml(k)}</kbd></td><td>${escapeHtml(d)}</td></tr>`).join('');
        sections.push(`<section><h3>Mouse</h3><table>${mouse}</table></section>`);
        return `<div class="nsa-help-card" role="dialog" aria-label="Keyboard shortcuts">
            <header><b>Keyboard and mouse</b><button type="button" data-close aria-label="Close">&times;</button></header>
            <div class="nsa-help-grid">${sections.join('')}</div>
            <footer>Esc or ? closes this help</footer></div>`;
    }

    const STYLE = `
        .nsa-help-overlay { position: fixed; inset: 0; z-index: 100000; background: rgba(15, 23, 42, 0.45);
            display: flex; align-items: center; justify-content: center; font-family: 'Segoe UI', system-ui, sans-serif; }
        .nsa-help-card { background: #fff; color: #0f172a; border-radius: 10px; box-shadow: 0 12px 40px rgba(15,23,42,.35);
            max-width: min(1100px, 94vw); max-height: 90vh; display: flex; flex-direction: column; }
        .nsa-help-card header { display: flex; justify-content: space-between; align-items: center; padding: 10px 16px;
            border-bottom: 1px solid #e2e8f0; font-size: 15px; }
        .nsa-help-card header button { border: 0; background: transparent; font-size: 22px; cursor: pointer; color: #64748b; }
        .nsa-help-grid { overflow: auto; padding: 8px 16px; columns: 3 300px; column-gap: 24px; }
        .nsa-help-grid section { break-inside: avoid; margin-bottom: 12px; }
        .nsa-help-grid h3 { margin: 6px 0 4px; font-size: 12px; text-transform: uppercase; letter-spacing: .05em; color: #2563eb; }
        .nsa-help-grid table { border-collapse: collapse; width: 100%; font-size: 12px; }
        .nsa-help-grid td { padding: 2px 4px; vertical-align: top; }
        .nsa-help-grid td.k { white-space: nowrap; width: 1%; padding-right: 10px; }
        .nsa-help-grid kbd { background: #f1f5f9; border: 1px solid #cbd5e1; border-bottom-width: 2px; border-radius: 4px;
            padding: 0 5px; font-size: 11px; font-family: inherit; }
        .nsa-help-card footer { padding: 6px 16px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #64748b; }
    `;

    function onKeyDown(event) {
        if (event.key === 'Escape' || event.key === '?') {
            event.preventDefault();
            event.stopImmediatePropagation();
            close();
        } else {
            // Nothing behind the overlay may react: swallow the key for the app (not for the browser,
            // so F5, Ctrl+R and the like still work). Tab must not move focus to hidden controls.
            if (event.key === 'Tab') event.preventDefault();
            event.stopImmediatePropagation();
        }
    }

    function open() {
        if (overlayEl || typeof document === 'undefined') return;
        overlayEl = document.createElement('div');
        overlayEl.className = 'nsa-help-overlay';
        overlayEl.innerHTML = `<style>${STYLE}</style>${buildHtml()}`;
        overlayEl.addEventListener('click', (event) => {
            if (event.target === overlayEl || event.target?.hasAttribute?.('data-close')) close();
        });
        document.body.appendChild(overlayEl);
        // Capture so Esc closes the help before the region-cancel shortcut sees it.
        document.addEventListener('keydown', onKeyDown, true);
    }

    function close() {
        if (!overlayEl) return;
        document.removeEventListener('keydown', onKeyDown, true);
        overlayEl.remove();
        overlayEl = null;
    }

    function toggle() {
        if (overlayEl) close(); else open();
    }

    app.services = app.services || {};
    app.services.helpOverlay = { open, close, toggle, isOpen: () => Boolean(overlayEl), buildHtml };
})(window.NoiseSurveyApp);
