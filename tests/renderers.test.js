import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Import source files for side effects to enable coverage tracking.
import '../noise_survey_analysis/static/js/chart-classes.js';
import '../noise_survey_analysis/static/js/features/regions/regionUtils.js';
import '../noise_survey_analysis/static/js/comparison-metrics.js';
import '../noise_survey_analysis/static/js/services/regions/regionPanelRenderer.js';
import '../noise_survey_analysis/static/js/services/renderers.js';
import '../noise_survey_analysis/static/js/features/markers/markersSelectors.js';

describe('NoiseSurveyApp.renderers', () => {
    let renderers;
    let mockUpdateAllCharts;
    let mockSetVisible;
    let mockHideHoverLine;
    let mockHideLabel;
    let mockSyncMarkers;
    let mockGetLabelText;
    let mockRenderLabel;
    let mockRenderHoverLine;
    let mockRenderHoverDetails;

    let mockDispatchAction;
    let panelElement;
    let mockSyncRegions;
    let mockStoreDispatch;
    let mockGetState;
    let mockRegionSelect;
    let mockRegionRemove;
    let mockRegionSetNote;
    let mockRegionSetColor;

    beforeEach(() => {
        vi.useFakeTimers(); // Use fake timers for debounce testing
        vi.restoreAllMocks(); // Ensure any spies from previous tests are reset
        vi.clearAllMocks();
        mockDispatchAction = vi.fn();
        mockStoreDispatch = vi.fn();
        mockGetState = vi.fn(() => ({ regions: { byId: {}, allIds: [], selectedId: null, counter: 1, panelVisible: true, overlaysVisible: true } }));

        mockUpdateAllCharts = vi.fn();
        mockSetVisible = vi.fn();
        mockHideHoverLine = vi.fn();
        mockHideLabel = vi.fn();
        mockSyncMarkers = vi.fn();
        mockSyncRegions = vi.fn();
        mockGetLabelText = vi.fn();
        mockRenderLabel = vi.fn();
        mockRenderHoverLine = vi.fn();
        mockRenderHoverDetails = vi.fn();

        mockRegionSelect = vi.fn(id => ({ type: 'regions/select', payload: id }));
        mockRegionRemove = vi.fn(id => ({ type: 'regions/remove', payload: id }));
        mockRegionSetNote = vi.fn((id, value) => ({ type: 'regions/setNote', payload: { id, value } }));
        mockRegionSetColor = vi.fn((id, color) => ({ type: 'regions/setColor', payload: { id, color } }));

        Object.assign(window.NoiseSurveyApp, {
            state: {
                dispatchAction: vi.fn()
            },
            store: {
                dispatch: mockStoreDispatch,
                getState: mockGetState
            },
            actions: {
                regionSelect: mockRegionSelect,
                regionRemove: mockRegionRemove,
                regionSetNote: mockRegionSetNote,
                regionSetColor: mockRegionSetColor
            },
            registry: {
                controllers: {
                    positions: {
                        P1: {
                            updateAllCharts: mockUpdateAllCharts,
                            timeSeriesChart: { setVisible: mockSetVisible, model: { title: { text: '' }, background_fill_color: '' } },
                            spectrogramChart: { setVisible: mockSetVisible, hoverDivModel: { visible: true }, model: { title: { text: '' }, background_fill_color: '' } }
                        }
                    },
                    chartsByName: new Map([
                        ['figure_P1_timeseries', {
                            name: 'figure_P1_timeseries',
                            hideHoverLine: mockHideHoverLine,
                            hideLabel: mockHideLabel,
                            syncMarkers: mockSyncMarkers,
                            syncRegions: mockSyncRegions,
                            getLabelText: mockGetLabelText,
                            renderLabel: mockRenderLabel,
                            renderHoverLine: mockRenderHoverLine,
                            renderHoverDetails: mockRenderHoverDetails,
                            model: { title: { text: '' }, background_fill_color: '' }
                        }],
                        ['figure_P1_spectrogram', {
                            name: 'figure_P1_spectrogram',
                            hideHoverLine: mockHideHoverLine,
                            hideLabel: mockHideLabel,
                            syncMarkers: mockSyncMarkers,
                            syncRegions: mockSyncRegions,
                            getLabelText: mockGetLabelText,
                            renderLabel: mockRenderLabel,
                            renderHoverLine: mockRenderHoverLine,
                            renderHoverDetails: mockRenderHoverDetails,
                            model: { title: { text: '' }, background_fill_color: '' }
                        }]
                    ])
                },
                models: {
                    clickLines: [{ location: null, visible: false }],
                    freqTableDiv: { text: '' },
                    regionPanelDiv: null,
                    summaryTableDiv: { text: '<thead><tr><th>Position</th><th class="position-header">LAeq</th><th class="position-header">LCeq</th></tr></thead><tbody></tbody>' },
                    barSource: { data: {}, change: { emit: vi.fn() } },
                    barChart: { x_range: { factors: [] }, title: { text: '' } },
                    audio_controls: {
                        P1: {
                            playToggle: { active: false, label: '', button_type: '' },
                            playbackRateButton: { label: '' },
                            volumeBoostButton: { active: false, button_type: '' },
                            layout: { visible: true }
                        }
                    },
                    config: { // Add config mock
                        freq_table_freq_range_hz: [200, 300]
                    }
                }
            },
            data_processors: {
                updateActiveFreqBarData: vi.fn()
            },
            utils: {
                findAssociatedDateIndex: vi.fn()
            }
        });
        renderers = window.NoiseSurveyApp.renderers;

        panelElement = document.createElement('div');
        panelElement.id = 'region-panel';
        document.body.appendChild(panelElement);

        const regionPanelMocks = {
            source: {
                data: { id: [], title: [], subtitle: [], color: [] },
                selected: { indices: [], change: { emit: vi.fn() } },
                change: { emit: vi.fn() }
            },
            table: { disabled: true, visible: false },
            source: {
                data: { id: [], title: [], subtitle: [], color: [] },
                selected: { indices: [], change: { emit: vi.fn() } },
                change: { emit: vi.fn() }
            },
            table: { disabled: true, visible: false },
            messageDiv: { text: '', visible: true },
            detail: { visible: false },
            copyButton: { disabled: true },
            deleteButton: { disabled: true },
            addAreaButton: { disabled: true, label: 'Add Area', button_type: 'default' },
            mergeButton: { disabled: true },
            mergeSelect: { options: [], value: '', disabled: true },
            noteInput: { value: '', disabled: true },
            colorPicker: { color: '#1e88e5', disabled: true },
            metricsDiv: { text: '', visible: false },
            frequencyCopyButton: { disabled: true, visible: false },
            frequencyTableDiv: { text: '', visible: false },
            spectrumDiv: { text: '', visible: false },
            visibilityToggle: { label: 'Regions', active: true, button_type: 'primary' },
            autoDayButton: { disabled: false, button_type: 'default', visible: true },
            autoNightButton: { disabled: false, button_type: 'default', visible: true },
        };

        Object.assign(window.NoiseSurveyApp.registry.models, {
            regionPanelSource: regionPanelMocks.source,
            regionPanelTable: regionPanelMocks.table,
            regionPanelMessageDiv: regionPanelMocks.messageDiv,
            regionPanelDetail: regionPanelMocks.detail,
            regionPanelCopyButton: regionPanelMocks.copyButton,
            regionPanelDeleteButton: regionPanelMocks.deleteButton,
            regionPanelAddAreaButton: regionPanelMocks.addAreaButton,
            regionPanelMergeButton: regionPanelMocks.mergeButton,
            regionPanelMergeSelect: regionPanelMocks.mergeSelect,
            regionPanelNoteInput: regionPanelMocks.noteInput,
            regionPanelColorPicker: regionPanelMocks.colorPicker,
            regionPanelMetricsDiv: regionPanelMocks.metricsDiv,
            regionPanelFrequencyCopyButton: regionPanelMocks.frequencyCopyButton,
            regionPanelFrequencyTableDiv: regionPanelMocks.frequencyTableDiv,
            regionPanelSpectrumDiv: regionPanelMocks.spectrumDiv,
            regionVisibilityToggle: regionPanelMocks.visibilityToggle,
            regionAutoDayButton: regionPanelMocks.autoDayButton,
            regionAutoNightButton: regionPanelMocks.autoNightButton,
        });

    });

        it('respects panel visibility toggles and updates labels', () => {
            const models = window.NoiseSurveyApp.registry.models;
            mockSyncRegions.mockClear();

            const hiddenState = {
                view: { availablePositions: ['P1'] },
                regions: {
                    byId: {
                        1: {
                            id: 1,
                            positionId: 'P1',
                            start: 0,
                            end: 3000,
                            note: '',
                            color: '#607d8b',
                            metrics: null,
                        }
                    },
                    allIds: [1],
                    selectedId: 1,
                    counter: 2,
                    panelVisible: false,
                    overlaysVisible: false,
                }
            };

            renderers.renderRegions(hiddenState, {});

            expect(models.regionPanelDetail.visible).toBe(false);
            expect(models.regionPanelMessageDiv.visible).toBe(false);
            expect(models.regionVisibilityToggle.active).toBe(false);
            expect(models.regionVisibilityToggle.label).toBe('Regions (1)');
            expect(models.regionVisibilityToggle.button_type).toBe('default');
            expect(models.regionAutoDayButton.visible).toBe(false);
            expect(models.regionAutoNightButton.visible).toBe(false);

            const hiddenCall = mockSyncRegions.mock.calls.at(-1);
            expect(hiddenCall[0]).toEqual([]);
            expect(hiddenCall[1]).toBeNull();

            mockSyncRegions.mockClear();

            const visibleState = {
                view: { availablePositions: ['P1'] },
                regions: {
                    byId: {
                        1: hiddenState.regions.byId[1],
                        2: {
                            id: 2,
                            positionId: 'P1',
                            start: 4000,
                            end: 8000,
                            note: '',
                            color: '#c2185b',
                            metrics: null,
                        }
                    },
                    allIds: [1, 2],
                    selectedId: 2,
                    counter: 3,
                    panelVisible: true,
                    overlaysVisible: true,
                }
            };

            renderers.renderRegions(visibleState, {});

            expect(models.regionPanelDetail.visible).toBe(true);
            expect(models.regionVisibilityToggle.active).toBe(true);
            expect(models.regionVisibilityToggle.label).toBe('Regions (2)');
            expect(models.regionVisibilityToggle.button_type).toBe('primary');
            expect(models.regionAutoDayButton.visible).toBe(true);
            expect(models.regionAutoNightButton.visible).toBe(true);

            const visibleCall = mockSyncRegions.mock.calls.at(-1);
            expect(Array.isArray(visibleCall[0])).toBe(true);
            expect(visibleCall[0].length).toBe(2);
            expect(visibleCall[1]).toBe(2);
        });

    afterEach(() => {
        vi.useRealTimers(); // Restore real timers
        if (panelElement && panelElement.parentNode) {
            panelElement.parentNode.removeChild(panelElement);
        }
        delete window.Bokeh;
    });

    describe('renderPrimaryCharts', () => {
        it('should update chart visibility and data', () => {
            const mockState = {
                view: {
                    chartVisibility: {
                        figure_P1_timeseries: true,
                        figure_P1_spectrogram: false
                    }
                }
            };
            const mockDataCache = {}; // Not used by this renderer directly, but passed down
            renderers.renderPrimaryCharts(mockState, mockDataCache);
            expect(mockSetVisible).toHaveBeenCalledWith(true);
            expect(mockSetVisible).toHaveBeenCalledWith(false);
            expect(mockUpdateAllCharts).toHaveBeenCalledWith(mockState, mockDataCache);
            expect(window.NoiseSurveyApp.registry.controllers.positions.P1.spectrogramChart.hoverDivModel.visible).toBe(false);
        });
    });

    describe('renderOverlays', () => {
        it('should perform overlay updates (tap lines, labels, hover effects, summary)', () => {
            // Arrange a state that triggers visible side-effects
            const mockState = {
                interaction: {
                    tap: { isActive: true, timestamp: 12345, position: 'P1' },
                    hover: { isActive: false, timestamp: null, position: null, spec_y: null }
                },
                view: { hoverEnabled: true, availablePositions: [] },
                markers: { timestamps: [], enabled: true },
                audio: { isPlaying: false }
            };
            // Provide minimal bar data to avoid errors in renderFrequencyBar (called inside hover effects)
            const mockDataCache = { 
                activeFreqBarData: {
                    levels: [1],
                    frequency_labels: ['A'],
                    sourceposition: 'P1',
                    param: 'LAeq',
                    timestamp: 12345,
                    setBy: 'test'
                },
                activeSpectralData: {
                    P1: {
                        times_ms: [10000, 13000],
                        frequencies_hz: [100],
                        frequency_labels: ['100Hz'],
                        levels_flat_transposed: [10, 20],
                        n_times: 2,
                        n_freqs: 1
                    }
                }
            };
            mockGetLabelText.mockReturnValue('Label');

            // Act
            renderers.renderOverlays(mockState, mockDataCache);

            // Assert observable side-effects from each inner renderer
            // Tap lines
            expect(window.NoiseSurveyApp.registry.models.clickLines[0].location).toBe(12345);
            expect(window.NoiseSurveyApp.registry.models.clickLines[0].visible).toBe(true);
            // Labels should have been rendered at least once
            expect(mockRenderLabel).toHaveBeenCalled();
            // Hover effects should hide hover lines when inactive
            expect(mockHideHoverLine).toHaveBeenCalled();
            // Frequency bar should have been updated (emit called)
            expect(window.NoiseSurveyApp.registry.models.barSource.change.emit).toHaveBeenCalled();
            // Note: We do not assert internal calls to summary renderer here because
            // it is a local function inside the module. We verify observable effects instead.
        });
    });

    describe('renderRegions', () => {
        it('should refresh region metrics in the side panel for the selected region', () => {
            const stateWithMetrics = {
                view: { availablePositions: ['P1'] },
                regions: {
                    byId: {
                        1: {
                            id: 1,
                            positionId: 'P1',
                            start: 0,
                            end: 60000,
                            note: '',
                            color: '#ff5722',
                            metrics: {
                                laeq: 50.12,
                                lafmax: 65.5,
                                la90: null,
                                la90Available: false,
                                durationMs: 60000,
                                dataResolution: 'log',
                                spectrum: { bands: ['63 Hz'], values: [40] }
                            }
                        }
                    },
                    allIds: [1],
                    selectedId: 1,
                    counter: 2,
                    panelVisible: true,
                    overlaysVisible: true
                }
            };

            renderers.renderRegions(stateWithMetrics, {});

            const models = window.NoiseSurveyApp.registry.models;
            expect(models.regionPanelMetricsDiv.text).toContain('50.1 dB');
            expect(models.regionPanelMetricsDiv.text).toContain('65.5 dB');
            expect(models.regionPanelFrequencyTableDiv.text).toContain('63 Hz');
            expect(models.regionPanelFrequencyTableDiv.text).toContain('40.0 dB');
            expect(models.regionPanelFrequencyCopyButton.disabled).toBe(false);
            expect(models.regionPanelFrequencyCopyButton.visible).toBe(true);
            expect(models.regionPanelSource.data.id).toEqual([1]);
            expect(models.regionPanelSource.selected.indices).toEqual([0]);
            expect(models.regionPanelTable.disabled).toBe(false);
            expect(models.regionPanelNoteInput.disabled).toBe(false);
            expect(models.regionPanelMergeSelect.disabled).toBe(true);
            expect(models.regionPanelColorPicker.disabled).toBe(false);
            expect(models.regionPanelColorPicker.color).toBe('#ff5722');

            const updatedState = {
                view: { availablePositions: ['P1'] },
                regions: {
                    byId: {
                        1: {
                            id: 1,
                            positionId: 'P1',
                            start: 0,
                            end: 62000,
                            note: '',
                            color: '#4caf50',
                            metrics: {
                                laeq: 55.44,
                                lafmax: 70.2,
                                la90: 45.3,
                                la90Available: true,
                                durationMs: 62000,
                                dataResolution: 'log',
                                spectrum: { bands: ['63 Hz'], values: [45] }
                            }
                        }
                    },
                    allIds: [1],
                    selectedId: 1,
                    counter: 2,
                    panelVisible: true,
                    overlaysVisible: true
                }
            };

            renderers.renderRegions(updatedState, {});
            expect(models.regionPanelMetricsDiv.text).toContain('55.4 dB');
            expect(models.regionPanelMetricsDiv.text).toContain('70.2 dB');
            expect(models.regionPanelMetricsDiv.text).toContain('45.3 dB');
            expect(models.regionPanelFrequencyTableDiv.text).toContain('45.0 dB');
            expect(models.regionPanelSpectrumDiv.text).toContain('63 Hz');
            expect(models.regionPanelColorPicker.color).toBe('#4caf50');

            const lastCall = mockSyncRegions.mock.calls.at(-1);
            const syncedRegions = lastCall[0];
            expect(Array.isArray(syncedRegions)).toBe(true);
            expect(syncedRegions[0].metrics.laeq).toBeCloseTo(55.44);
        });
    });

    describe('region panel widgets', () => {
        it('toggles widget visibility and disabled states based on region availability', () => {
            const models = window.NoiseSurveyApp.registry.models;

            const emptyState = {
                view: { availablePositions: [] },
                regions: {
                    byId: {},
                    allIds: [],
                    selectedId: null,
                    counter: 0,
                    panelVisible: true,
                    overlaysVisible: true,
                }
            };

            renderers.renderRegions(emptyState, {});
            expect(models.regionPanelMessageDiv.visible).toBe(true);
            expect(models.regionPanelDetail.visible).toBe(false);
            expect(models.regionPanelTable.disabled).toBe(true);
            expect(models.regionPanelCopyButton.disabled).toBe(true);
            expect(models.regionPanelDeleteButton.disabled).toBe(true);
            expect(models.regionPanelAddAreaButton.disabled).toBe(true);
            expect(models.regionPanelMergeButton.disabled).toBe(true);
            expect(models.regionPanelMergeSelect.disabled).toBe(true);
            expect(models.regionPanelNoteInput.disabled).toBe(true);

            expect(models.regionPanelColorPicker.disabled).toBe(true);

            expect(models.regionPanelFrequencyCopyButton.disabled).toBe(true);
            expect(models.regionPanelFrequencyCopyButton.visible).toBe(false);
            expect(models.regionPanelFrequencyTableDiv.visible).toBe(false);
            expect(models.regionAutoDayButton.disabled).toBe(true);
            expect(models.regionAutoNightButton.disabled).toBe(true);


            const populatedState = {
                view: { availablePositions: ['P9'] },
                regions: {
                    byId: {
                        5: {
                            id: 5,
                            positionId: 'P9',
                            start: 1000,
                            end: 4000,
                            note: 'hello',
                            color: '#2196f3',
                            metrics: {
                                laeq: 52,
                                lafmax: 60,
                                la90: null,
                                la90Available: false,
                                durationMs: 3000,
                                dataResolution: 'overview',
                                spectrum: { labels: [], values: [] },
                            }
                        }
                    },
                    allIds: [5],
                    selectedId: 5,
                    counter: 6,
                    panelVisible: true,
                    overlaysVisible: true,
                }
            };

            renderers.renderRegions(populatedState, {});
            expect(models.regionPanelMessageDiv.visible).toBe(false);
            expect(models.regionPanelDetail.visible).toBe(true);
            expect(models.regionPanelTable.disabled).toBe(false);
            expect(models.regionPanelSource.data.title[0]).toBe('hello');
            expect(models.regionPanelCopyButton.disabled).toBe(false);
            expect(models.regionPanelDeleteButton.disabled).toBe(false);
            expect(models.regionPanelAddAreaButton.disabled).toBe(false);
            expect(models.regionPanelMergeButton.disabled).toBe(true);
            expect(models.regionPanelMergeSelect.disabled).toBe(true);
            expect(models.regionPanelNoteInput.disabled).toBe(false);
            expect(models.regionPanelNoteInput.value).toBe('hello');

            expect(models.regionPanelColorPicker.disabled).toBe(false);
            expect(models.regionPanelColorPicker.color).toBe('#2196f3');

            expect(models.regionPanelFrequencyCopyButton.disabled).toBe(true);
            expect(models.regionPanelFrequencyCopyButton.visible).toBe(true);
            expect(models.regionPanelFrequencyTableDiv.visible).toBe(true);
            expect(models.regionPanelFrequencyTableDiv.text).toContain('No frequency data available');
            expect(models.regionAutoDayButton.disabled).toBe(false);
            expect(models.regionAutoNightButton.disabled).toBe(false);


            const multiRegionState = {
                view: { availablePositions: ['P9'] },
                regions: {
                    byId: {
                        5: populatedState.regions.byId[5],
                        6: {
                            id: 6,
                            positionId: 'P9',
                            start: 2000,
                            end: 6000,
                            note: '',
                            color: '#e91e63',
                            metrics: null,
                        }
                    },
                    allIds: [5, 6],
                    selectedId: 5,
                    counter: 7,
                    addAreaTargetId: null,
                    panelVisible: true,
                    overlaysVisible: true,
                }
            };

            renderers.renderRegions(multiRegionState, {});
            expect(models.regionPanelMergeSelect.disabled).toBe(false);
            expect(models.regionPanelMergeButton.disabled).toBe(false);
            expect(models.regionPanelMergeSelect.options).toEqual([
                ['6', expect.stringContaining('Region 6')]
            ]);
            expect(models.regionPanelMergeSelect.visible).toBe(false);
            expect(models.regionPanelMergeSelect.value).toBe('');
        });

        it('uses note previews when building region labels', () => {
            const models = window.NoiseSurveyApp.registry.models;
            const longNote = '  This is a deliberately long note value that should be trimmed when displayed.  ';
            const state = {
                view: { availablePositions: ['A1'] },
                regions: {
                    byId: {
                        7: {
                            id: 7,
                            positionId: 'A1',
                            start: 0,
                            end: 1000,
                            note: longNote,
                            color: '#123456',
                            metrics: null,
                        }
                    },
                    allIds: [7],
                    selectedId: 7,
                    counter: 8,
                    panelVisible: true,
                    overlaysVisible: true,
                }
            };

            renderers.renderRegions(state, {});
            const label = models.regionPanelSource.data.title[0];
            const normalized = longNote.replace(/\s+/g, ' ').trim();
            const expected = `${normalized.slice(0, 40).trimEnd()}…`;
            expect(label).toBe(expected);
        });
    });

    describe('renderTapLines', () => {
        it('should set line location and visibility based on tap state', () => {
            const mockState = { interaction: { tap: { isActive: true, timestamp: 12345 } } };
            renderers.renderTapLines(mockState);
            expect(window.NoiseSurveyApp.registry.models.clickLines[0].location).toBe(12345);
            expect(window.NoiseSurveyApp.registry.models.clickLines[0].visible).toBe(true);
        });

        it('should hide line if tap is not active', () => {
            const mockState = { interaction: { tap: { isActive: false, timestamp: null } } };
            renderers.renderTapLines(mockState);
            expect(window.NoiseSurveyApp.registry.models.clickLines[0].visible).toBe(false);
        });
    });

    describe('renderLabels', () => {
        it('should hide labels if no interaction is active', () => {
            const mockState = { interaction: { hover: { isActive: false }, tap: { isActive: false } } };
            renderers.renderLabels(mockState);
            expect(mockHideLabel).toHaveBeenCalledTimes(2);
        });

        it('should render hover label if hover is active and enabled', () => {
            const mockState = {
                interaction: {
                    hover: { isActive: true, sourceChartName: 'figure_P1_timeseries', timestamp: 100 },
                    tap: { isActive: false }
                },
                view: { hoverEnabled: true }
            };
            mockGetLabelText.mockReturnValue('Hover Text');
            renderers.renderLabels(mockState);
            expect(mockRenderLabel).toHaveBeenCalledWith(100, 'Hover Text');
            expect(mockHideLabel).toHaveBeenCalledWith();
        });

        it('should render tap label if tap is active', () => {
            const mockState = {
                interaction: {
                    hover: { isActive: false },
                    tap: { isActive: true, timestamp: 200 }
                },
                view: { hoverEnabled: true }
            };
            mockGetLabelText.mockReturnValue('Tap Text');
            renderers.renderLabels(mockState);
            expect(mockRenderLabel).toHaveBeenCalledWith(200, 'Tap Text');
            expect(mockRenderLabel).toHaveBeenCalledTimes(2);
        });
    });

    describe('renderMarkers', () => {
        it('should sync markers for all charts', () => {
            const mockState = {
                markers: {
                    byId: {
                        1: { id: 1, timestamp: 100 },
                        2: { id: 2, timestamp: 200 }
                    },
                    allIds: [1, 2],
                    selectedId: null,
                    counter: 3,
                    enabled: true
                }
            };
            renderers.renderMarkers(mockState);
            expect(mockSyncMarkers).toHaveBeenCalledWith([100, 200], true);
            expect(mockSyncMarkers).toHaveBeenCalledTimes(2);
        });
    });

    describe('renderFrequencyTable', () => {
        it('should display placeholder if no tap interaction', () => {
            const mockState = { interaction: { tap: { isActive: false } } };
            const mockDataCache = {};
            renderers.renderFrequencyTable(mockState, mockDataCache);
            expect(window.NoiseSurveyApp.registry.models.freqTableDiv.text).toContain('Tap on a time series chart to populate this table.');
        });

        it('should display no frequency data message if spectral data is missing', () => {
            const mockState = { interaction: { tap: { isActive: true, timestamp: 100, position: 'P1' } } };
            const mockDataCache = { activeSpectralData: {} };
            renderers.renderFrequencyTable(mockState, mockDataCache);
            expect(window.NoiseSurveyApp.registry.models.freqTableDiv.text).toContain('No frequency data available for selected position.');
        });

        it('should display no data at selected time if closestTimeIdx is -1', () => {
            const mockState = { interaction: { tap: { isActive: true, timestamp: 100, position: 'P1' } } };
            const mockDataCache = {
                activeSpectralData: {
                    P1: { times_ms: [200, 300], frequencies_hz: [1000] }
                }
            };
            renderers.renderFrequencyTable(mockState, mockDataCache);
            expect(window.NoiseSurveyApp.registry.models.freqTableDiv.text).toContain('No data available at selected time.');
        });

        it('should render table with sliced frequency data', () => {
            const mockState = { interaction: { tap: { isActive: true, timestamp: 150, position: 'P1' } } };
            const mockDataCache = {
                activeSpectralData: {
                    P1: {
                        times_ms: [100, 200],
                        frequencies_hz: [100, 200, 300, 400],
                        frequency_labels: ['100Hz', '200Hz', '300Hz', '400Hz'],
                        levels_flat_transposed: [10, 20, 30, 40, 50, 60, 70, 80],
                        n_times: 2,
                        n_freqs: 4
                    }
                }
            };
            window.NoiseSurveyApp.registry.models.config = {
                freq_table_freq_range_hz: [200, 300]
            };

            renderers.renderFrequencyTable(mockState, mockDataCache);
            const expectedHtml = `\n        <style>\n            .freq-html-table { border-collapse: collapse; width: 100%; font-size: 0.9em; table-layout: fixed; }\n            .freq-html-table th, .freq-html-table td { border: 1px solid #ddd; padding: 6px; text-align: center; white-space: nowrap; }\n            .freq-html-table th { background-color: #f2f2f2; font-weight: bold; }\n        </style>\n        <table class="freq-html-table">\n            <tr><th title="200Hz">200Hz</th><th title="300Hz">300Hz</th></tr><tr><td>30.0</td><td>50.0</td></tr></table>`;
            expect(window.NoiseSurveyApp.registry.models.freqTableDiv.text).toBe(expectedHtml);
        });

        it('should render table with full frequency data if config is missing', () => {
            const mockState = { interaction: { tap: { isActive: true, timestamp: 150, position: 'P1' } } };
            const mockDataCache = {
                activeSpectralData: {
                    P1: {
                        times_ms: [100, 200],
                        frequencies_hz: [100, 200],
                        frequency_labels: ['100Hz', '200Hz'],
                        levels_flat_transposed: [10, 20, 30, 40],
                        n_times: 2,
                        n_freqs: 2
                    }
                }
            };
            window.NoiseSurveyApp.registry.models.config = {}; // Missing config
            renderers.renderFrequencyTable(mockState, mockDataCache);
            const expectedHtml = `\n        <style>\n            .freq-html-table { border-collapse: collapse; width: 100%; font-size: 0.9em; table-layout: fixed; }\n            .freq-html-table th, .freq-html-table td { border: 1px solid #ddd; padding: 6px; text-align: center; white-space: nowrap; }\n            .freq-html-table th { background-color: #f2f2f2; font-weight: bold; }\n        </style>\n        <table class="freq-html-table">\n            <tr><th title="100Hz">100Hz</th><th title="200Hz">200Hz</th></tr><tr><td>10.0</td><td>30.0</td></tr></table>`;
            expect(window.NoiseSurveyApp.registry.models.freqTableDiv.text).toBe(expectedHtml);
        });
    });

    describe('renderFrequencyBar', () => {
        it('should update bar source data and chart properties', () => {
            const mockState = { interaction: { tap: { isActive: false } } }; // Minimal state
            const mockDataCache = {
                activeFreqBarData: {
                    levels: [1, 2, 3],
                    frequency_labels: ['A', 'B', 'C'],
                    sourceposition: 'P1',
                    param: 'LAeq',
                    timestamp: 12345,
                    setBy: 'test'
                }
            };
            renderers.renderFrequencyBar(mockState, mockDataCache);

            expect(window.NoiseSurveyApp.registry.models.barSource.data.levels).toEqual([1, 2, 3]);
            expect(window.NoiseSurveyApp.registry.models.barSource.data.frequency_labels).toEqual(['A', 'B', 'C']);
            expect(window.NoiseSurveyApp.registry.models.barChart.x_range.factors).toEqual(['A', 'B', 'C']);
            expect(window.NoiseSurveyApp.registry.models.barChart.title.text).toContain('Slice: P1 | LAeq @');
            expect(window.NoiseSurveyApp.registry.models.barSource.change.emit).toHaveBeenCalled();
        });
    });

    describe('renderControlWidgets', () => {
        it('should update chart titles and background colors based on audio state', () => {
            const mockState = {
                audio: { isPlaying: true, activePositionId: 'P1', playbackRate: 1.0, volumeBoost: false },
                view: { availablePositions: ['P1'], selectedParameter: 'LAeq', displayDetails: { P1: { line: { reason: '' }, spec: { reason: '' } } } }
            };
            renderers.renderControlWidgets(mockState);
            expect(window.NoiseSurveyApp.registry.controllers.positions.P1.timeSeriesChart.model.title.text).toContain('(▶ PLAYING)');
            expect(window.NoiseSurveyApp.registry.controllers.positions.P1.timeSeriesChart.model.background_fill_color).toBe('#e6f0ff');
            expect(window.NoiseSurveyApp.registry.controllers.positions.P1.spectrogramChart.model.title.text).toContain('(▶ PLAYING)');
            expect(window.NoiseSurveyApp.registry.controllers.positions.P1.spectrogramChart.model.background_fill_color).toBe('#e6f0ff');
        });

        it('should update control widget visuals', () => {
            const mockState = {
                audio: { isPlaying: true, activePositionId: 'P1', playbackRate: 1.5, volumeBoost: true },
                view: { availablePositions: ['P1'], selectedParameter: 'LAeq', displayDetails: { P1: { line: { reason: '' }, spec: { reason: '' } } } }
            };
            renderers.renderControlWidgets(mockState);
            const controls = window.NoiseSurveyApp.registry.models.audio_controls.P1;
            expect(controls.playToggle.active).toBe(true);
            expect(controls.playToggle.label).toBe('Pause');
            expect(controls.playToggle.button_type).toBe('primary');
            expect(controls.playbackRateButton.label).toBe('1.5x');
            expect(controls.volumeBoostButton.active).toBe(true);
            expect(controls.volumeBoostButton.button_type).toBe('warning');
        });

        it('should hide audio controls when all charts for a position are hidden', () => {
            const baseState = {
                audio: { isPlaying: false, activePositionId: null, playbackRate: 1.0, volumeBoost: false },
                view: {
                    availablePositions: ['P1'],
                    selectedParameter: 'LAeq',
                    displayDetails: { P1: { line: { reason: '' }, spec: { reason: '' } } }
                }
            };

            renderers.renderControlWidgets({
                ...baseState,
                view: {
                    ...baseState.view,
                    chartVisibility: {
                        figure_P1_timeseries: false,
                        figure_P1_spectrogram: false
                    }
                }
            });

            const controls = window.NoiseSurveyApp.registry.models.audio_controls.P1;
            expect(controls.layout.visible).toBe(false);

            renderers.renderControlWidgets({
                ...baseState,
                view: {
                    ...baseState.view,
                    chartVisibility: {
                        figure_P1_timeseries: true,
                        figure_P1_spectrogram: false
                    }
                }
            });

            expect(controls.layout.visible).toBe(true);
        });
    });

    describe('renderSummaryTable', () => {
        it('should display placeholder if no tap interaction', () => {
            const mockState = { interaction: { tap: { isActive: false } } };
            const mockDataCache = {};
            renderers.renderSummaryTable(mockState, mockDataCache);
            expect(window.NoiseSurveyApp.registry.models.summaryTableDiv.text).toContain('Tap on a time series chart to populate this table.');
        });

        it('should display timestamp info and data for active position', () => {
            const mockState = {
                interaction: { tap: { isActive: true, timestamp: 100, position: 'P1' } },
                view: { availablePositions: ['P1'] }
            };
            const mockDataCache = {
                activeLineData: {
                    P1: {
                        Datetime: [100],
                        LAeq: [70],
                        LCeq: [80]
                    }
                }
            };
            window.NoiseSurveyApp.registry.models.summaryTableDiv.text = '<table><thead><tr><th class="position-header">Position</th><th>LAeq</th><th>LCeq</th></tr></thead><tbody></tbody></table>';
            window.NoiseSurveyApp.utils.findAssociatedDateIndex.mockReturnValue(0);
            renderers.renderSummaryTable(mockState, mockDataCache);
            const actual = window.NoiseSurveyApp.registry.models.summaryTableDiv.text;
            const tsStr = new Date(100).toLocaleString();
            expect(actual).toContain(`<thead><tr><th class="position-header">Position</th><th>LAeq</th><th>LCeq</th></tr></thead>`);
            expect(actual).toContain(`Values at: ${tsStr}`);
            expect(actual).toContain(`<td class="position-header">P1</td>`);
            expect(actual).toContain(`<td>70.0</td>`);
            expect(actual).toContain(`<td>80.0</td>`);
        });
    });
});