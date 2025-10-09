import { describe, it, expect, vi } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/services/markers/markerPanelRenderer.js';

const { renderMarkerPanel, buildClipboardText } = window.NoiseSurveyApp.services.markerPanelRenderer;

describe('markerPanelRenderer.renderMarkerPanel', () => {
    const createPanelModels = () => {
        const markerSource = {
            data: {},
            change: { emit: vi.fn() },
            properties: {
                data: {
                    change: { emit: vi.fn() }
                }
            },
            selected: {
                indices: [],
                change: { emit: vi.fn() }
            }
        };
        return {
            markerSource,
            markerTable: { __suppressSelectionDispatch: false, disabled: false, visible: true },
            messageDiv: { visible: false, text: '' },
            detail: { visible: false },
            colorPicker: { disabled: true, color: '#ffffff' },
            noteInput: { disabled: true, value: '' },
            metricsDiv: { visible: false, text: '' },
            copyButton: { disabled: true },
            deleteButton: { disabled: true },
            addAtTapButton: { disabled: true },
            visibilityToggle: { active: false }
        };
    };

    it('updates table, details, and controls when markers are present', async () => {
        const panelModels = createPanelModels();
        const timestamp = Date.UTC(2023, 0, 2, 3, 4, 5);
        const longNote = `${'Observation '.repeat(8)}with trailing spaces   `;
        const markersState = {
            allIds: [1],
            byId: {
                1: {
                    id: 1,
                    timestamp,
                    note: longNote,
                    color: '  #abc123  ',
                    metrics: {
                        parameter: 'LZeq',
                        broadband: [
                            { positionId: 'P1', value: 48.45 },
                            { positionId: 'P2' }
                        ],
                        spectral: [
                            { positionId: 'P1', labels: ['63', '125', '250'] }
                        ]
                    }
                }
            },
            selectedId: 1,
            enabled: true
        };
        const interactionState = { tap: { timestamp: 12345 } };
        const viewState = { selectedParameter: 'LAeq' };

        renderMarkerPanel(panelModels, markersState, interactionState, viewState);

        expect(panelModels.markerSource.data.id).toEqual([1]);
        expect(panelModels.markerSource.data.timestamp_display[0]).toBeTruthy();
        expect(panelModels.markerSource.data.note_preview[0].endsWith('…')).toBe(true);
        expect(panelModels.markerSource.data.color[0]).toBe('#abc123');
        expect(panelModels.markerSource.change.emit).toHaveBeenCalledTimes(1);
        expect(panelModels.markerSource.properties.data.change.emit).toHaveBeenCalledTimes(1);
        expect(panelModels.markerSource.selected.indices).toEqual([0]);
        expect(panelModels.markerSource.selected.change.emit).toHaveBeenCalledTimes(1);

        expect(panelModels.markerTable.disabled).toBe(false);
        expect(panelModels.markerTable.visible).toBe(true);
        expect(panelModels.messageDiv.visible).toBe(false);
        expect(panelModels.detail.visible).toBe(true);
        expect(panelModels.metricsDiv.visible).toBe(true);
        expect(panelModels.metricsDiv.text).toContain('Snapshot Metrics');
        expect(panelModels.metricsDiv.text).toContain('Broadband');
        expect(panelModels.metricsDiv.text).toContain('Spectral');
        expect(panelModels.colorPicker.disabled).toBe(false);
        expect(panelModels.colorPicker.color).toBe('#abc123');
        expect(panelModels.noteInput.disabled).toBe(false);
        expect(panelModels.noteInput.value).toBe(longNote);
        expect(panelModels.copyButton.disabled).toBe(false);
        expect(panelModels.deleteButton.disabled).toBe(false);
        expect(panelModels.addAtTapButton.disabled).toBe(false);
        expect(panelModels.visibilityToggle.active).toBe(true);

        expect(panelModels.markerTable.__suppressSelectionDispatch).toBe(true);
        await Promise.resolve();
        expect(panelModels.markerTable.__suppressSelectionDispatch).toBe(false);
    });

    it('shows empty state message when there are no markers', () => {
        const panelModels = createPanelModels();
        const markersState = {
            allIds: [],
            byId: {},
            selectedId: null,
            enabled: false
        };

        renderMarkerPanel(panelModels, markersState, { tap: {} }, { selectedParameter: 'LZeq' });

        expect(panelModels.markerSource.data.id).toEqual([]);
        expect(panelModels.markerSource.change.emit).toHaveBeenCalledTimes(1);
        expect(panelModels.markerSource.properties.data.change.emit).toHaveBeenCalledTimes(1);
        expect(panelModels.markerTable.disabled).toBe(true);
        expect(panelModels.markerTable.visible).toBe(false);
        expect(panelModels.messageDiv.visible).toBe(true);
        expect(panelModels.messageDiv.text).toContain('No markers recorded.');
        expect(panelModels.detail.visible).toBe(false);
        expect(panelModels.metricsDiv.text).toContain('Select a marker to view metrics.');
        expect(panelModels.colorPicker.disabled).toBe(true);
        expect(panelModels.noteInput.disabled).toBe(true);
        expect(panelModels.copyButton.disabled).toBe(true);
        expect(panelModels.deleteButton.disabled).toBe(true);
        expect(panelModels.addAtTapButton.disabled).toBe(true);
        expect(panelModels.visibilityToggle.active).toBe(false);
    });
});

describe('markerPanelRenderer.buildClipboardText', () => {
    it('formats clipboard text with metrics summaries', () => {
        const timestamp = Date.UTC(2024, 4, 6, 7, 8, 9);
        const marker = {
            timestamp,
            note: '  Example note  ',
            metrics: {
                parameter: 'LZeq',
                broadband: [{ positionId: 'P1', value: 45.01 }],
                spectral: [{ positionId: 'P2', labels: ['63', '125'] }]
            }
        };

        const clipboard = buildClipboardText(marker, { view: { selectedParameter: 'LAeq' } });
        const lines = clipboard.split('\n');

        expect(lines[0]).toBe('Marker Details');
        expect(lines).toContain('Parameter: LZeq');
        expect(lines).toContain('Note: Example note');
        expect(lines).toContain('Broadband Values:');
        expect(lines).toContain(' - P1: 45.0 dB');
        expect(lines).toContain('Spectral Snapshots:');
        expect(lines).toContain(' - P2: 2 bands');
    });
});
