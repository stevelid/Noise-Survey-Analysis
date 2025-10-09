import { describe, it, expect, beforeEach, vi } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/services/regions/regionPanelRenderer.js';

const { renderRegionPanel } = window.NoiseSurveyApp.services.regionPanelRenderer;

function createPanelModels() {
    return {
        regionSource: {
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
        },
        regionTable: { __suppressSelectionDispatch: false, disabled: false, visible: true },
        messageDiv: { visible: false, text: '' },
        creationIndicatorDiv: { visible: false, text: '' },
        detail: { visible: false },
        noteInput: { disabled: true, value: '' },
        metricsDiv: { visible: false, text: '' },
        spectrumDiv: { visible: false, text: '' },
        mergeSelect: { options: [], value: '', disabled: true, visible: false },
        colorPicker: { disabled: true, color: '#1e88e5' },
        frequencyTableDiv: { visible: false, text: '' },
        frequencyCopyButton: { visible: false, disabled: true },
        visibilityToggle: { label: 'Regions', active: false, button_type: 'default' },
        autoDayNightButton: { disabled: true, button_type: 'light', visible: true },
        splitButton: { disabled: true, visible: true },
        copyButton: { disabled: true },
        deleteButton: { disabled: true },
        addAreaButton: { disabled: true, label: 'Add Area', button_type: 'default' },
        mergeButton: { disabled: true, label: 'Merge Regions', button_type: 'default' }
    };
}

describe('regionPanelRenderer.renderRegionPanel', () => {
    beforeEach(() => {
        window.NoiseSurveyApp.regions = window.NoiseSurveyApp.regions || {};
        window.NoiseSurveyApp.regions.getRegionMetrics = vi.fn().mockReturnValue(null);
        window.NoiseSurveyApp.dataCache = {};
        window.NoiseSurveyApp.registry = window.NoiseSurveyApp.registry || {};
        window.NoiseSurveyApp.registry.models = window.NoiseSurveyApp.registry.models || {};
    });

    it('repopulates the region table after clearing all regions', () => {
        const panelModels = createPanelModels();

        const baseState = {
            regions: {
                byId: {
                    1: { id: 1, positionId: 'P1', areas: [{ start: 0, end: 1000 }], start: 0, end: 1000, note: '', color: '#1e88e5' }
                },
                allIds: [1],
                selectedId: 1,
                addAreaTargetId: null,
                isMergeModeActive: false,
                panelVisible: true,
                overlaysVisible: true
            },
            interaction: {},
            view: { availablePositions: ['P1'] }
        };

        renderRegionPanel(panelModels, [baseState.regions.byId[1]], 1, baseState, { panelVisible: true, overlaysVisible: true, positionCount: 1 });

        expect(panelModels.regionSource.data.id).toEqual([1]);
        expect(panelModels.regionTable.visible).toBe(true);
        expect(panelModels.regionSource.change.emit).toHaveBeenCalledTimes(1);
        expect(panelModels.regionSource.properties.data.change.emit).toHaveBeenCalledTimes(1);

        const clearedState = {
            ...baseState,
            regions: {
                ...baseState.regions,
                byId: {},
                allIds: [],
                selectedId: null
            }
        };

        renderRegionPanel(panelModels, [], null, clearedState, { panelVisible: true, overlaysVisible: true, positionCount: 1 });

        expect(panelModels.regionSource.data.id).toEqual([]);
        expect(panelModels.regionTable.visible).toBe(false);
        expect(panelModels.regionSource.change.emit).toHaveBeenCalledTimes(2);
        expect(panelModels.regionSource.properties.data.change.emit).toHaveBeenCalledTimes(2);

        const newState = {
            ...baseState,
            regions: {
                ...baseState.regions,
                byId: {
                    10: { id: 10, positionId: 'P1', areas: [{ start: 2000, end: 3000 }], start: 2000, end: 3000, note: '', color: '#1e88e5' },
                    11: { id: 11, positionId: 'P1', areas: [{ start: 4000, end: 4500 }], start: 4000, end: 4500, note: '', color: '#1e88e5' }
                },
                allIds: [10, 11],
                selectedId: 11
            }
        };

        renderRegionPanel(panelModels, [newState.regions.byId[10], newState.regions.byId[11]], 11, newState, { panelVisible: true, overlaysVisible: true, positionCount: 1 });

        expect(panelModels.regionSource.data.id).toEqual([10, 11]);
        expect(panelModels.regionSource.data.title.length).toBe(2);
        expect(panelModels.regionTable.visible).toBe(true);
        expect(panelModels.regionSource.selected.indices).toEqual([1]);
        expect(panelModels.regionSource.change.emit).toHaveBeenCalledTimes(3);
        expect(panelModels.regionSource.properties.data.change.emit).toHaveBeenCalledTimes(3);
    });
});
