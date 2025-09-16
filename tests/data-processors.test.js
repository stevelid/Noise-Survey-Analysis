import { describe, it, expect, beforeEach, vi } from 'vitest';

// Import source files for side effects to enable coverage tracking.
import '../noise_survey_analysis/static/js/data-processors.js';

describe('NoiseSurveyApp.data_processors', () => {
    let dataProcessors;

    beforeEach(() => {
        vi.clearAllMocks();
        dataProcessors = window.NoiseSurveyApp.data_processors;

        // Mock dependencies that the data processors might need.
        window.NoiseSurveyApp.models = {};
    });

    describe('calculateStepSize', () => {
        it('should calculate step size correctly from active line data', () => {
            const mockState = {
                interaction: {
                    tap: { position: 'P1' }
                }
            };
            const mockDataCache = {
                activeLineData: {
                    P1: {
                        Datetime: [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]
                    }
                }
            };
            
            const stepSize = dataProcessors.calculateStepSize(mockState, mockDataCache);
            expect(stepSize).toBe(1000);
        });

        it('should return undefined if no active position', () => {
            const mockState = {
                interaction: {
                    tap: { position: null }
                },
                audio: { activePositionId: null }
            };
            const mockDataCache = { activeLineData: {} };
            const stepSize = dataProcessors.calculateStepSize(mockState, mockDataCache);
            expect(stepSize).toBeUndefined();
        });

        it('should return undefined if not enough data points', () => {
            const mockState = {
                interaction: {
                    tap: { position: 'P1' }
                },
                audio: {}
            };
            const mockDataCache = {
                activeLineData: {
                    P1: {
                        Datetime: [0, 1000, 2000]
                    }
                }
            };
            const stepSize = dataProcessors.calculateStepSize(mockState, mockDataCache);
            expect(stepSize).toBeUndefined();
        });
    });

    describe('updateActiveFreqBarData', () => {
        it('should set blank data if no interaction', () => {
            const mockState = {
                interaction: {
                    hover: { isActive: false },
                    tap: { isActive: false }
                },
                audio: { isPlaying: false }
            };
            const mockDataCache = { activeFreqBarData: {} };
            window.NoiseSurveyApp.registry = { models: {} }; // Ensure registry exists

            dataProcessors.updateActiveFreqBarData(mockState, mockDataCache);
            expect(mockDataCache.activeFreqBarData).toEqual({ levels: [], frequency_labels: [], sourceposition: '', timestamp: null, setBy: null, param: null });
        });

        it('should update from hover when hover is active', () => {
            const mockState = {
                interaction: {
                    hover: { isActive: true, position: 'P1', timestamp: 12345 },
                    tap: { isActive: false }
                },
                audio: { isPlaying: false },
                view: {
                    selectedParameter: 'LAeq',
                    displayDetails: { P1: { spec: { type: 'None' } } }
                }
            };
            const mockDataCache = {
                activeFreqBarData: {},
                activeSpectralData: {
                    P1: {
                        times_ms: [12000, 13000],
                        n_times: 2,
                        n_freqs: 2,
                        levels_flat_transposed: [1, 2, 3, 4],
                        frequency_labels: ['1k', '2k']
                    }
                }
            };
            window.NoiseSurveyApp.registry = { models: {} };

            dataProcessors.updateActiveFreqBarData(mockState, mockDataCache);
            expect(mockDataCache.activeFreqBarData.setBy).toBe('hover');
            expect(mockDataCache.activeFreqBarData.timestamp).toBe(12345);
        });

        it('should update from tap when tap is active and hover is not', () => {
            const mockState = {
                interaction: {
                    hover: { isActive: false },
                    tap: { isActive: true, position: 'P1', timestamp: 54321 }
                },
                audio: { isPlaying: false },
                view: {
                    selectedParameter: 'LAeq',
                    displayDetails: { P1: { spec: { type: 'None' } } }
                }
            };
            const mockDataCache = {
                activeFreqBarData: {},
                activeSpectralData: {
                    P1: {
                        times_ms: [54000, 55000],
                        n_times: 2,
                        n_freqs: 2,
                        levels_flat_transposed: [1, 2, 3, 4],
                        frequency_labels: ['1k', '2k']
                    }
                }
            };
            window.NoiseSurveyApp.registry = { models: {} };

            dataProcessors.updateActiveFreqBarData(mockState, mockDataCache);
            expect(mockDataCache.activeFreqBarData.setBy).toBe('tap');
            expect(mockDataCache.activeFreqBarData.timestamp).toBe(54321);
        });

        it('should set blank data if no spectral data for position', () => {
            const mockState = {
                interaction: {
                    hover: { isActive: true, position: 'P1', timestamp: 12345 },
                    tap: { isActive: false }
                },
                audio: { isPlaying: false },
                view: { selectedParameter: 'LAeq' }
            };
            const mockDataCache = {
                activeFreqBarData: {},
                activeSpectralData: {} // No data for P1
            };
            window.NoiseSurveyApp.registry = { models: {} };

            dataProcessors.updateActiveFreqBarData(mockState, mockDataCache);
            expect(mockDataCache.activeFreqBarData).toEqual({ levels: [], frequency_labels: [], sourceposition: '', timestamp: null, setBy: null, param: null });
        });

        it('should update from audio when audio is playing', () => {
            const mockState = {
                interaction: {
                    hover: { isActive: false },
                    tap: { isActive: true, position: 'P1', timestamp: 54321 }
                },
                audio: { isPlaying: true, activePositionId: 'P1' },
                view: {
                    selectedParameter: 'LAeq',
                    displayDetails: { P1: { spec: { type: 'None' } } }
                }
            };
            const mockDataCache = {
                activeFreqBarData: {},
                activeSpectralData: {
                    P1: {
                        times_ms: [54000, 55000],
                        n_times: 2,
                        n_freqs: 2,
                        levels_flat_transposed: [1, 2, 3, 4],
                        frequency_labels: ['1k', '2k']
                    }
                }
            };
            window.NoiseSurveyApp.registry = { models: {} };

            dataProcessors.updateActiveFreqBarData(mockState, mockDataCache);
            expect(mockDataCache.activeFreqBarData.setBy).toBe('audio');
        });

        it('should apply frequency slicing for bar chart', () => {
            const mockState = {
                interaction: {
                    hover: { isActive: true, position: 'P1', timestamp: 12345 },
                    tap: { isActive: false }
                },
                audio: { isPlaying: false },
                view: {
                    selectedParameter: 'LAeq',
                    displayDetails: { P1: { spec: { type: 'None' } } }
                }
            };
            const mockDataCache = {
                activeFreqBarData: {},
                activeSpectralData: {
                    P1: {
                        times_ms: [12000, 13000],
                        n_times: 2,
                        n_freqs: 4,
                        levels_flat_transposed: [1, 2, 3, 4, 5, 6, 7, 8],
                        frequencies_hz: [500, 1000, 2000, 4000],
                        frequency_labels: ['500', '1k', '2k', '4k']
                    }
                }
            };
            window.NoiseSurveyApp.registry = {
                models: {
                    config: {
                        freq_bar_freq_range_hz: [1000, 2000]
                    }
                }
            };

            dataProcessors.updateActiveFreqBarData(mockState, mockDataCache);
            expect(mockDataCache.activeFreqBarData.frequency_labels).toEqual(['1k', '2k']);
            expect(mockDataCache.activeFreqBarData.levels).toEqual([3, 5]);
        });
    });

    describe('updateActiveLineChartData', () => {
        it('should show log data when in log view and zoomed in', () => {
            const viewState = {
                globalViewType: 'log',
                viewport: { min: 1000, max: 2000 },
                displayDetails: {}
            };
            const mockDataCache = { activeLineData: {} };
            const models = {
                timeSeriesSources: {
                    P1: {
                        log: {
                            data: {
                                Datetime: [0, 1200, 1800, 3000],
                                LAeq: [50, 60, 70, 80]
                            }
                        }
                    }
                }
            };

            dataProcessors.updateActiveLineChartData('P1', viewState, mockDataCache, models);

            expect(mockDataCache.activeLineData.P1.LAeq).toEqual([60, 70]);
            expect(viewState.displayDetails.P1.line.type).toBe('log');
        });

        it('should show overview data when in log view but zoomed out', () => {
            const viewState = {
                globalViewType: 'log',
                viewport: { min: 0, max: 5001000 }, // Large range
                displayDetails: {}
            };
            const dataCache = { activeLineData: {} };
            const models = {
                timeSeriesSources: {
                    P1: {
                        overview: {
                            data: {
                                Datetime: [0, 10000],
                                LAeq: [55, 65]
                            }
                        },
                        log: {
                            data: {
                                Datetime: Array.from({length: 6000}, (_, i) => i * 1000),
                                LAeq: Array.from({length: 6000}, (_, i) => i)
                            }
                        }
                    }
                }
            };

            dataProcessors.updateActiveLineChartData('P1', viewState, dataCache, models);

            expect(dataCache.activeLineData.P1.LAeq).toEqual([55, 65]);
            expect(viewState.displayDetails.P1.line.type).toBe('overview');
        });

        it('should use overview data when log data is not available', () => {
            const viewState = {
                globalViewType: 'log',
                viewport: { min: 1000, max: 2000 },
                displayDetails: {}
            };
            const dataCache = { activeLineData: {} };
            const models = {
                timeSeriesSources: {
                    P1: {
                        overview: {
                            data: {
                                Datetime: [0, 10000],
                                LAeq: [55, 65]
                            }
                        }
                    }
                }
            };

            dataProcessors.updateActiveLineChartData('P1', viewState, dataCache, models);

            expect(dataCache.activeLineData.P1.LAeq).toEqual([55, 65]);
            expect(viewState.displayDetails.P1.line.type).toBe('overview');
        });

        it('should use overview data when globalViewType is overview', () => {
            const viewState = {
                globalViewType: 'overview',
                viewport: { min: 1000, max: 2000 },
                displayDetails: {}
            };
            const dataCache = { activeLineData: {} };
            const models = {
                timeSeriesSources: {
                    P1: {
                        overview: {
                            data: {
                                Datetime: [0, 10000],
                                LAeq: [55, 65]
                            }
                        },
                        log: {
                            data: {
                                Datetime: [0, 1200, 1800, 3000],
                                LAeq: [50, 60, 70, 80]
                            }
                        }
                    }
                }
            };

            dataProcessors.updateActiveLineChartData('P1', viewState, dataCache, models);

            expect(dataCache.activeLineData.P1.LAeq).toEqual([55, 65]);
            expect(viewState.displayDetails.P1.line.type).toBe('overview');
        });
    });
});
