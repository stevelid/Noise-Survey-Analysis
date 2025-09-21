import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

// Import source files for side effects to enable coverage tracking.
import '../noise_survey_analysis/static/js/chart-classes.js';
import '../noise_survey_analysis/static/js/calcMetrics.js';
import '../noise_survey_analysis/static/js/comparison-metrics.js';
import '../noise_survey_analysis/static/js/renderers.js';

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

    beforeEach(() => {
        vi.useFakeTimers(); // Use fake timers for debounce testing
        vi.restoreAllMocks(); // Ensure any spies from previous tests are reset
        vi.clearAllMocks();
        mockDispatchAction = vi.fn();
        mockStoreDispatch = vi.fn();
        mockGetState = vi.fn(() => ({ markers: { regions: { byId: {} } } }));

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
                regionSetNote: mockRegionSetNote
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
        window.NoiseSurveyApp.registry.models.regionPanelDiv = {
            id: 'region-panel',
            _text: '',
            get text() {
                return this._text;
            },
            set text(value) {
                this._text = value;
                const el = document.getElementById(this.id);
                if (el) {
                    el.innerHTML = value;
                }
            }
        };
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
                markers: {
                    regions: {
                        byId: {
                            1: {
                                id: 1,
                                positionId: 'P1',
                                start: 0,
                                end: 60000,
                                note: '',
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
                        counter: 2
                    }
                }
            };

            renderers.renderRegions(stateWithMetrics, {});

            let panelHtml = document.getElementById('region-panel').innerHTML;
            expect(panelHtml).toContain('50.1 dB');
            expect(panelHtml).toContain('65.5 dB');

            const updatedState = {
                markers: {
                    regions: {
                        byId: {
                            1: {
                                id: 1,
                                positionId: 'P1',
                                start: 0,
                                end: 62000,
                                note: '',
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
                        counter: 2
                    }
                }
            };

            renderers.renderRegions(updatedState, {});

            panelHtml = document.getElementById('region-panel').innerHTML;
            expect(panelHtml).toContain('55.4 dB');
            expect(panelHtml).toContain('70.2 dB');
            expect(panelHtml).toContain('45.3 dB');

            const lastCall = mockSyncRegions.mock.calls.at(-1);
            const syncedRegions = lastCall[0];
            expect(Array.isArray(syncedRegions)).toBe(true);
            expect(syncedRegions[0].metrics.laeq).toBeCloseTo(55.44);
        });
    });

    describe('region panel listeners', () => {
        it('attaches listeners when the panel root appears via MutationObserver', () => {
            const originalMutationObserver = window.MutationObserver;
            const observers = [];
            class MockMutationObserver {
                constructor(callback) {
                    this.callback = callback;
                    observers.push(this);
                }

                observe(target, options) {
                    this.target = target;
                    this.options = options;
                }
                disconnect() {}
            }
            window.MutationObserver = MockMutationObserver;

            const panelId = 'region-panel-shadow';
            const viewHost = document.createElement('div');
            let shadowRoot = null;

            const bokehView = { shadow_el: null };
            window.Bokeh = { index: { [panelId]: bokehView } };

            const panelDiv = {
                id: panelId,
                _text: '',
                get text() {
                    return this._text;
                },
                set text(value) {
                    this._text = value;

                    if (shadowRoot) {
                        shadowRoot.innerHTML = value;

                    }
                }
            };

            window.NoiseSurveyApp.registry.models.regionPanelDiv = panelDiv;

            const regionState = {
                byId: {
                    1: {
                        id: 1,
                        positionId: 'P1',
                        start: 0,
                        end: 1000,
                        note: '',
                        metrics: {
                            laeq: 40,
                            lafmax: 45,
                            la90: null,
                            la90Available: false,
                            durationMs: 1000,
                            dataResolution: 'log',
                            spectrum: { bands: [], values: [] }
                        }
                    }
                },
                allIds: [1],
                selectedId: 1,
                counter: 2
            };

            try {
                renderers.renderRegions({ markers: { regions: regionState } }, {});
                vi.runAllTimers();

                expect(observers.length).toBeGreaterThan(0);
                expect(mockStoreDispatch).not.toHaveBeenCalled();

                shadowRoot = viewHost;
                bokehView.shadow_el = shadowRoot;
                document.body.appendChild(viewHost);
                shadowRoot.innerHTML = panelDiv.text;

                const docObserver = observers.find(observer => {
                    return observer.target === document.body || observer.target === document.documentElement;
                });
                expect(docObserver).toBeDefined();
                docObserver.callback([], docObserver);

                const entry = viewHost.querySelector('[data-region-entry="1"]');
                expect(entry).not.toBeNull();

                const regionList = viewHost.querySelector('.region-list');
                expect(regionList).not.toBeNull();

                const regionListObserver = observers.find(observer => observer.target === regionList);
                expect(regionListObserver).toBeDefined();

                entry.click();
                expect(mockRegionSelect).toHaveBeenCalledWith(1);
                expect(mockStoreDispatch).toHaveBeenCalledWith({ type: 'regions/select', payload: 1 });

                const deleteButton = viewHost.querySelector('[data-region-delete="1"]');
                expect(deleteButton).not.toBeNull();
                deleteButton.dispatchEvent(new Event('click', { bubbles: true }));
                expect(mockRegionRemove).toHaveBeenCalledWith(1);
                expect(mockStoreDispatch).toHaveBeenCalledWith({ type: 'regions/remove', payload: 1 });

                const noteField = viewHost.querySelector('[data-region-note="1"]');
                expect(noteField).not.toBeNull();
                noteField.value = 'Updated note';
                noteField.dispatchEvent(new Event('input', { bubbles: true }));
                vi.advanceTimersByTime(300);
                expect(mockRegionSetNote).toHaveBeenCalledWith(1, 'Updated note');
                expect(mockStoreDispatch).toHaveBeenLastCalledWith({ type: 'regions/setNote', payload: { id: 1, value: 'Updated note' } });
            } finally {
                window.MutationObserver = originalMutationObserver;
                if (viewHost.parentNode) {
                    viewHost.parentNode.removeChild(viewHost);
                }
            }
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
                markers: { timestamps: [100, 200], enabled: true }
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