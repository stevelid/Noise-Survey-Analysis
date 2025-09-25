// noise_survey_analysis/static/js/services/markers/markerPanelRenderer.js

/**
 * @fileoverview Marker panel rendering helpers.
 * These functions keep the marker management widgets in sync with the current
 * application state. All logic here is presentational only.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const DEFAULT_MARKER_COLOR = '#43a047';
    const NOTE_PREVIEW_MAX_LENGTH = 60;
    const PANEL_STYLE = `
        <style>
            .marker-panel-empty { font-style: italic; color: #666; margin: 0; }
            .marker-metrics { font-family: 'Segoe UI', sans-serif; font-size: 12px; margin-top: 6px; }
            .marker-metrics__header { font-weight: 600; margin-bottom: 4px; display: flex; justify-content: space-between; }
            .marker-metrics__section { margin-top: 6px; }
            .marker-metrics__table { width: 100%; border-collapse: collapse; }
            .marker-metrics__table th, .marker-metrics__table td { text-align: left; padding: 4px; border-bottom: 1px solid #e5e7eb; }
            .marker-metrics__placeholder { color: #9ca3af; font-style: italic; }
            .marker-metrics__spectral { margin: 0; padding-left: 18px; }
        </style>
    `;

    function normalizeColor(color) {
        if (typeof color === 'string') {
            const trimmed = color.trim();
            if (trimmed) {
                return trimmed;
            }
        }
        return DEFAULT_MARKER_COLOR;
    }

    function escapeHtml(value) {
        if (typeof value !== 'string') {
            return '';
        }
        return value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function ensureArrayEquals(a, b) {
        if (!Array.isArray(a) || !Array.isArray(b)) {
            return false;
        }
        if (a.length !== b.length) {
            return false;
        }
        for (let i = 0; i < a.length; i += 1) {
            if (a[i] !== b[i]) {
                return false;
            }
        }
        return true;
    }

    function formatTimestamp(timestamp) {
        if (!Number.isFinite(timestamp)) {
            return '—';
        }
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

    function buildNotePreview(note) {
        if (typeof note !== 'string' || !note) {
            return '—';
        }
        const trimmed = note.trim();
        if (trimmed.length <= NOTE_PREVIEW_MAX_LENGTH) {
            return trimmed;
        }
        return `${trimmed.slice(0, NOTE_PREVIEW_MAX_LENGTH - 1)}…`;
    }

    function buildClipboardText(marker, state) {
        if (!marker) {
            return '';
        }
        const timestampText = formatTimestamp(marker.timestamp);
        const noteText = typeof marker.note === 'string' && marker.note.trim()
            ? marker.note.trim()
            : 'None';
        const metrics = marker.metrics || {};
        const parameter = metrics.parameter || state?.view?.selectedParameter || '—';

        const broadbandEntries = Array.isArray(metrics.broadband)
            ? metrics.broadband
            : [];
        const broadbandLines = broadbandEntries.length
            ? broadbandEntries.map(entry => {
                const value = Number.isFinite(entry?.value)
                    ? `${entry.value.toFixed(1)} dB`
                    : 'N/A';
                return ` - ${entry?.positionId ?? 'Unknown'}: ${value}`;
            }).join('\n')
            : ' - No broadband values';

        const spectralEntries = Array.isArray(metrics.spectral)
            ? metrics.spectral
            : [];
        const spectralLines = spectralEntries.length
            ? spectralEntries.map(entry => {
                const bandCount = Array.isArray(entry?.labels) ? entry.labels.length : 0;
                return ` - ${entry?.positionId ?? 'Unknown'}: ${bandCount} bands`;
            }).join('\n')
            : ' - No spectral snapshots';

        return [
            'Marker Details',
            `Timestamp: ${timestampText}`,
            `Parameter: ${parameter}`,
            `Note: ${noteText}`,
            'Broadband Values:',
            broadbandLines,
            'Spectral Snapshots:',
            spectralLines
        ].join('\n');
    }

    function updateMarkerTable(markerSource, markerTable, markers, selectedId) {
        if (!markerSource) {
            return { selectedMarker: null };
        }

        const data = {
            id: markers.map(marker => marker.id ?? null),
            timestamp: markers.map(marker => marker.timestamp ?? null),
            timestamp_display: markers.map(marker => formatTimestamp(marker.timestamp)),
            note_preview: markers.map(marker => buildNotePreview(marker.note)),
            color: markers.map(marker => normalizeColor(marker.color))
        };

        const currentData = markerSource.data || {};
        const keys = Object.keys(data);
        let changed = keys.length !== Object.keys(currentData).length;
        if (!changed) {
            changed = keys.some(key => !ensureArrayEquals(currentData[key] || [], data[key]));
        }

        if (changed) {
            markerSource.data = data;
            if (markerSource.change && typeof markerSource.change.emit === 'function') {
                markerSource.change.emit();
            }
        }

        const selection = markerSource.selected;
        const selectedIndex = Number.isFinite(selectedId)
            ? markers.findIndex(marker => marker.id === selectedId)
            : -1;
        const selectionIndices = selectedIndex >= 0 ? [selectedIndex] : [];

        if (selection) {
            const currentSelection = Array.isArray(selection.indices) ? selection.indices : [];
            if (!ensureArrayEquals(currentSelection, selectionIndices)) {
                if (markerTable) {
                    markerTable.__suppressSelectionDispatch = true;
                }
                selection.indices = selectionIndices;
                if (selection.change && typeof selection.change.emit === 'function') {
                    selection.change.emit();
                }
                if (markerTable) {
                    const release = () => { markerTable.__suppressSelectionDispatch = false; };
                    if (typeof queueMicrotask === 'function') {
                        queueMicrotask(release);
                    } else {
                        Promise.resolve().then(release);
                    }
                }
            }
        }

        if (markerTable) {
            markerTable.disabled = markers.length === 0;
            markerTable.visible = markers.length > 0;
        }

        const resolvedMarker = selectedIndex >= 0 ? markers[selectedIndex] : null;
        return { selectedMarker: resolvedMarker };
    }

    function updateMessage(messageDiv, detailLayout, hasMarkers) {
        if (!messageDiv || !detailLayout) {
            return;
        }
        if (hasMarkers) {
            messageDiv.visible = false;
            detailLayout.visible = true;
        } else {
            messageDiv.visible = true;
            detailLayout.visible = false;
            const emptyHtml = `${PANEL_STYLE}<p class="marker-panel-empty">No markers recorded.</p>`;
            if (messageDiv.text !== emptyHtml) {
                messageDiv.text = emptyHtml;
            }
        }
    }

    function formatBroadbandTable(entries) {
        if (!Array.isArray(entries) || !entries.length) {
            return '<p class="marker-metrics__placeholder">No broadband values calculated.</p>';
        }
        const rows = entries.map(entry => {
            const position = escapeHtml(String(entry?.positionId ?? '—'));
            const value = Number.isFinite(entry?.value)
                ? `${entry.value.toFixed(1)} dB`
                : 'N/A';
            return `<tr><td>${position}</td><td>${value}</td></tr>`;
        }).join('');
        return `
            <table class="marker-metrics__table">
                <thead><tr><th>Position</th><th>Value</th></tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    }

    function formatSpectralSummary(entries) {
        if (!Array.isArray(entries) || !entries.length) {
            return '<p class="marker-metrics__placeholder">No spectral snapshots.</p>';
        }
        const items = entries.map(entry => {
            const position = escapeHtml(String(entry?.positionId ?? '—'));
            const count = Array.isArray(entry?.labels) ? entry.labels.length : 0;
            return `<li><strong>${position}</strong>: ${count} bands sampled</li>`;
        }).join('');
        return `<ul class="marker-metrics__spectral">${items}</ul>`;
    }

    function buildMetricsHtml(marker, viewState) {
        if (!marker) {
            return `${PANEL_STYLE}<p class="marker-panel-empty">Select a marker to view metrics.</p>`;
        }
        const metrics = marker.metrics || {};
        const timestampText = formatTimestamp(marker.timestamp);
        const parameter = escapeHtml(String(metrics.parameter || viewState?.selectedParameter || '—'));
        const broadbandHtml = formatBroadbandTable(metrics.broadband);
        const spectralHtml = formatSpectralSummary(metrics.spectral);
        return `${PANEL_STYLE}
            <div class="marker-metrics">
                <div class="marker-metrics__header">
                    <span>Snapshot Metrics</span>
                    <span>${escapeHtml(timestampText)}</span>
                </div>
                <div class="marker-metrics__section"><strong>Parameter:</strong> ${parameter}</div>
                <div class="marker-metrics__section">
                    <strong>Broadband</strong>
                    ${broadbandHtml}
                </div>
                <div class="marker-metrics__section">
                    <strong>Spectral</strong>
                    ${spectralHtml}
                </div>
            </div>
        `;
    }

    function updateDetail(panelModels, marker, options) {
        const {
            colorPicker,
            noteInput,
            metricsDiv,
            copyButton,
            deleteButton,
            addAtTapButton
        } = panelModels;
        const hasMarker = Boolean(marker);

        if (colorPicker) {
            colorPicker.disabled = !hasMarker;
            if (hasMarker) {
                const desiredColor = normalizeColor(marker.color);
                if (colorPicker.color !== desiredColor) {
                    colorPicker.color = desiredColor;
                }
            }
        }

        if (noteInput) {
            noteInput.disabled = !hasMarker;
            const noteValue = hasMarker && typeof marker.note === 'string' ? marker.note : '';
            if (noteInput.value !== noteValue) {
                noteInput.value = noteValue;
            }
        }

        if (metricsDiv) {
            metricsDiv.visible = true;
            const html = buildMetricsHtml(marker, options.viewState);
            if (metricsDiv.text !== html) {
                metricsDiv.text = html;
            }
        }

        if (copyButton) {
            copyButton.disabled = !hasMarker;
        }
        if (deleteButton) {
            deleteButton.disabled = !hasMarker;
        }
        if (addAtTapButton) {
            const tapState = options.interactionState?.tap || {};
            const hasTap = Number.isFinite(tapState.timestamp);
            addAtTapButton.disabled = !hasTap;
        }
    }

    function renderMarkerPanel(panelModels, markersState, interactionState, viewState) {
        if (!panelModels || !markersState) {
            return;
        }

        const markers = Array.isArray(markersState.allIds)
            ? markersState.allIds.map(id => markersState.byId?.[id]).filter(Boolean)
            : [];
        const selectedId = Number.isFinite(markersState.selectedId)
            ? markersState.selectedId
            : null;

        const { selectedMarker } = updateMarkerTable(
            panelModels.markerSource,
            panelModels.markerTable,
            markers,
            selectedId
        );

        updateMessage(panelModels.messageDiv, panelModels.detail, markers.length > 0);
        updateDetail(panelModels, selectedMarker, {
            interactionState,
            viewState
        });

        if (panelModels.visibilityToggle) {
            const shouldEnable = Boolean(markersState.enabled !== false);
            if (panelModels.visibilityToggle.active !== shouldEnable) {
                panelModels.visibilityToggle.active = shouldEnable;
            }
        }
    }

    app.services = app.services || {};
    app.services.markerPanelRenderer = {
        renderMarkerPanel,
        buildClipboardText
    };
})(window.NoiseSurveyApp);
