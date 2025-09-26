import { describe, it, expect, beforeEach, vi } from 'vitest';

import './loadCoreModules.js';

const { createStore, actions, rootReducer, thunks } = window.NoiseSurveyApp;

describe('NoiseSurveyApp thunks', () => {
    let store;
    beforeEach(() => {
        store = createStore(rootReducer);
        window.NoiseSurveyApp.store = store;
    });

    it('handleTapIntent clears selection and taps when no region hit', () => {
        store.dispatch(actions.regionAdd('P1', 1000, 2000));
        const thunk = thunks.handleTapIntent({
            timestamp: 5000,
            positionId: 'P1',
            chartName: 'figure_P1_timeseries',
            modifiers: {}
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.regions.selectedId).toBeNull();
        expect(state.interaction.tap.timestamp).toBe(5000);
        expect(state.interaction.tap.position).toBe('P1');
    });

    it('handleTapIntent selects region when hit', () => {
        store.dispatch(actions.regionAdd('P1', 1000, 2000));
        const thunk = thunks.handleTapIntent({
            timestamp: 1500,
            positionId: 'P1',
            chartName: 'figure_P1_timeseries',
            modifiers: {}
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.regions.selectedId).toBe(1);
        expect(state.interaction.tap.timestamp).toBe(1500);
        expect(state.regions.byId[1]).toBeTruthy();
    });

    it('handleTapIntent removes region on ctrl click', () => {
        store.dispatch(actions.regionAdd('P1', 1000, 2000));
        const thunk = thunks.handleTapIntent({
            timestamp: 1500,
            positionId: 'P1',
            chartName: 'figure_P1_timeseries',
            modifiers: { ctrl: true }
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.regions.allIds).toHaveLength(0);
        expect(state.regions.counter).toBe(2);
    });

    it('handleTapIntent removes only the targeted area on ctrl click when multiple areas exist', () => {
        store.dispatch(actions.regionAdd('P1', 1000, 2000));
        store.dispatch(actions.regionUpdate(1, { areas: [
            { start: 1000, end: 2000 },
            { start: 3000, end: 4000 }
        ] }));

        const thunk = thunks.handleTapIntent({
            timestamp: 3500,
            positionId: 'P1',
            chartName: 'figure_P1_timeseries',
            modifiers: { ctrl: true }
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.regions.allIds).toHaveLength(1);
        expect(state.regions.byId[1].areas).toEqual([{ start: 1000, end: 2000 }]);
    });

    it('handleTapIntent selects a nearby marker before regions', () => {
        store.dispatch(actions.viewportChange(0, 10000));
        store.dispatch(actions.markerAdd(1200, { positionId: 'P1' }));
        const thunk = thunks.handleTapIntent({
            timestamp: 1210,
            positionId: 'P1',
            chartName: 'figure_P1_timeseries',
            modifiers: {}
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.markers.selectedId).toBe(1);
        expect(state.interaction.tap.timestamp).toBe(1200);
    });

    it('createRegionIntent adds region when bounds valid', () => {
        const thunk = thunks.createRegionIntent({
            positionId: 'P1',
            start: 1000,
            end: 2000
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.regions.allIds).toHaveLength(1);
        expect(state.regions.byId[1].start).toBe(1000);
        expect(state.regions.byId[1].end).toBe(2000);
        expect(state.regions.selectedId).toBe(1);
    });

    it('createRegionIntent ignores creation requests during comparison mode', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        const thunk = thunks.createRegionIntent({
            positionId: 'P1',
            start: 1000,
            end: 2000
        });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.regions.allIds).toHaveLength(0);
    });

    it('resizeSelectedRegionIntent nudges end when alt held', () => {
        store.dispatch(actions.viewportChange(0, 10000));
        store.dispatch(actions.stepSizeCalculated(1000));
        store.dispatch(actions.regionAdd('P1', 1000, 5000));
        const thunk = thunks.resizeSelectedRegionIntent({ key: 'ArrowRight', modifiers: { alt: true } });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.regions.byId[1].end).toBe(6000);
    });

    it('resizeSelectedRegionIntent nudges start when ctrl held', () => {
        store.dispatch(actions.viewportChange(0, 10000));
        store.dispatch(actions.stepSizeCalculated(1000));
        store.dispatch(actions.regionAdd('P1', 1000, 5000));
        const thunk = thunks.resizeSelectedRegionIntent({ key: 'ArrowLeft', modifiers: { ctrl: true } });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.regions.byId[1].start).toBe(0);
    });

    it('nudgeTapLineIntent dispatches key nav', () => {
        store.dispatch(actions.viewportChange(0, 10000));
        store.dispatch(actions.stepSizeCalculated(1000));
        store.dispatch(actions.tap(5000, 'P1', 'figure_P1_timeseries'));
        const thunk = thunks.nudgeTapLineIntent({ key: 'ArrowLeft' });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.interaction.tap.timestamp).toBe(4000);
    });

    it('addMarkerAtTapIntent adds a marker at the tap timestamp', () => {
        store.dispatch(actions.tap(2500, 'P2', 'figure_P2_timeseries'));
        const thunk = thunks.addMarkerAtTapIntent();
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.markers.allIds).toHaveLength(1);
        expect(state.markers.byId[1]).toMatchObject({ timestamp: 2500, positionId: 'P2' });
    });

    it('nudgeSelectedMarkerIntent shifts the marker timestamp', () => {
        store.dispatch(actions.viewportChange(0, 10000));
        store.dispatch(actions.stepSizeCalculated(500));
        store.dispatch(actions.markerAdd(3000, { positionId: 'P1' }));
        store.dispatch(actions.markerSelect(1));
        const thunk = thunks.nudgeSelectedMarkerIntent({ key: 'ArrowRight' });
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.markers.byId[1].timestamp).toBe(3500);
    });

    it('toggleRegionCreationIntent stores a pending start when idle', () => {
        store.dispatch(actions.tap(4000, 'P3', 'figure_P3_timeseries'));
        const thunk = thunks.toggleRegionCreationIntent();
        thunk(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.interaction.pendingRegionStart).toEqual({ timestamp: 4000, positionId: 'P3' });
    });

    it('toggleRegionCreationIntent creates a region and clears pending state', () => {
        store.dispatch(actions.tap(5000, 'P4', 'figure_P4_timeseries'));
        thunks.toggleRegionCreationIntent()(store.dispatch, store.getState);
        store.dispatch(actions.tap(5400, 'P4', 'figure_P4_timeseries'));
        thunks.toggleRegionCreationIntent()(store.dispatch, store.getState);
        const state = store.getState();
        expect(state.regions.allIds).toHaveLength(1);
        const region = state.regions.byId[1];
        expect(region).toMatchObject({ positionId: 'P4', start: 5000, end: 5400 });
        expect(state.interaction.pendingRegionStart).toBeNull();
    });

    it('enterComparisonModeIntent enables comparison mode', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1', 'P2'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        const state = store.getState();
        expect(state.view.mode).toBe('comparison');
        expect(state.view.comparison.includedPositions).toEqual(['P1', 'P2']);
    });

    it('exitComparisonModeIntent returns to normal mode', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.exitComparisonModeIntent());
        const state = store.getState();
        expect(state.view.mode).toBe('normal');
        expect(state.view.comparison.isActive).toBe(false);
    });

    it('updateIncludedPositionsIntent updates included positions', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1', 'P2'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.updateIncludedPositionsIntent({ includedPositions: ['P2'] }));
        const state = store.getState();
        expect(state.view.comparison.includedPositions).toEqual(['P2']);
    });

    it('updateComparisonSliceIntent records normalized bounds when active', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.updateComparisonSliceIntent({ start: 4000, end: 2000 }));
        const state = store.getState();
        expect(state.view.comparison.start).toBe(2000);
        expect(state.view.comparison.end).toBe(4000);
    });

    it('updateComparisonSliceIntent clears slice when bounds collapse', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.updateComparisonSliceIntent({ start: 4000, end: 2000 }));
        store.dispatch(thunks.updateComparisonSliceIntent({ start: 2500, end: 2500 }));
        const state = store.getState();
        expect(state.view.comparison.start).toBeNull();
        expect(state.view.comparison.end).toBeNull();
    });

    it('createRegionsFromComparisonIntent creates regions and exits comparison mode', () => {
        store.dispatch(actions.initializeState({
            availablePositions: ['P1', 'P2'],
            selectedParameter: 'LZeq',
            viewport: { min: 0, max: 1000 },
            chartVisibility: {}
        }));
        store.dispatch(thunks.enterComparisonModeIntent());
        store.dispatch(thunks.updateComparisonSliceIntent({ start: 1000, end: 3000 }));
        store.dispatch(thunks.createRegionsFromComparisonIntent());
        const state = store.getState();
        expect(state.view.mode).toBe('normal');
        expect(state.regions.allIds).toEqual([1, 2]);
        expect(state.regions.byId[1].positionId).toBe('P1');
        expect(state.regions.byId[2].positionId).toBe('P2');
    });

    it('createAutoRegionsIntent builds daytime and nighttime regions with colours', () => {
        const times = [
            Date.UTC(2024, 0, 1, 6, 0, 0),
            Date.UTC(2024, 0, 1, 8, 0, 0),
            Date.UTC(2024, 0, 1, 22, 0, 0),
            Date.UTC(2024, 0, 1, 23, 30, 0),
            Date.UTC(2024, 0, 2, 1, 0, 0),
            Date.UTC(2024, 0, 2, 6, 30, 0),
            Date.UTC(2024, 0, 2, 8, 0, 0),
            Date.UTC(2024, 0, 2, 22, 0, 0),
            Date.UTC(2024, 0, 2, 23, 30, 0),
            Date.UTC(2024, 0, 3, 6, 30, 0)
        ];

        window.NoiseSurveyApp.registry.models = window.NoiseSurveyApp.registry.models || {};
        const originalSources = window.NoiseSurveyApp.registry.models.timeSeriesSources;
        window.NoiseSurveyApp.registry.models.timeSeriesSources = {
            P1: {
                overview: { data: { Datetime: times } },
                log: { data: { Datetime: [] } },
            }
        };

        store.dispatch(actions.initializeState({
            availablePositions: ['P1'],
            selectedParameter: 'LZeq',
            viewport: { min: times[0], max: times[times.length - 1] },
            chartVisibility: {}
        }));

        const thunk = thunks.createAutoRegionsIntent();
        thunk(store.dispatch, store.getState);

        const state = store.getState();
        expect(state.regions.allIds.length).toBe(4);
        const regions = state.regions.allIds.map(id => state.regions.byId[id]);
        const daytimeRegions = regions.filter(region => region.color === '#4caf50');
        const nighttimeRegions = regions.filter(region => region.color === '#7e57c2');
        expect(daytimeRegions.length).toBe(2);
        expect(nighttimeRegions.length).toBe(2);
        daytimeRegions.forEach(region => {
            expect(new Date(region.start).getUTCHours()).toBe(7);
        });
        nighttimeRegions.forEach(region => {
            expect(new Date(region.start).getUTCHours()).toBe(23);
        });

        window.NoiseSurveyApp.registry.models.timeSeriesSources = originalSources;
    });

    it('createAutoRegionsIntent respects explicit mode filters', () => {
        const times = [
            Date.UTC(2024, 0, 1, 20, 0, 0),
            Date.UTC(2024, 0, 1, 23, 30, 0),
            Date.UTC(2024, 0, 2, 3, 0, 0),
            Date.UTC(2024, 0, 2, 6, 30, 0),
            Date.UTC(2024, 0, 2, 10, 0, 0)
        ];

        const previousSources = window.NoiseSurveyApp.registry.models.timeSeriesSources;
        window.NoiseSurveyApp.registry.models.timeSeriesSources = {
            P1: {
                overview: { data: { Datetime: times } },
                log: { data: { Datetime: [] } },
            }
        };

        store.dispatch(actions.regionReplaceAll([]));

        const thunk = thunks.createAutoRegionsIntent({ mode: 'nighttime' });
        thunk(store.dispatch, store.getState);

        const state = store.getState();
        expect(state.regions.allIds.length).toBe(1);
        const region = state.regions.byId[state.regions.allIds[0]];
        expect(region.color).toBe('#7e57c2');
        expect(new Date(region.start).getUTCHours()).toBe(23);

        window.NoiseSurveyApp.registry.models.timeSeriesSources = previousSources;
    });

    describe('audio control intents', () => {
        it('togglePlayPauseIntent ignores redundant play requests', () => {
            store.dispatch(actions.audioPlayPauseToggle('P1', true));
            const thunk = thunks.togglePlayPauseIntent({ positionId: 'P1', isActive: true });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).not.toHaveBeenCalled();
        });

        it('togglePlayPauseIntent dispatches when switching positions', () => {
            store.dispatch(actions.audioPlayPauseToggle('P1', true));
            const thunk = thunks.togglePlayPauseIntent({ positionId: 'P2', isActive: true });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).toHaveBeenCalledWith(actions.audioPlayPauseToggle('P2', true));
        });

        it('togglePlayPauseIntent dispatches pause when active', () => {
            store.dispatch(actions.audioPlayPauseToggle('P1', true));
            const thunk = thunks.togglePlayPauseIntent({ positionId: 'P1', isActive: false });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).toHaveBeenCalledWith(actions.audioPlayPauseToggle('P1', false));
        });

        it('togglePlayPauseIntent ignores redundant pause', () => {
            const thunk = thunks.togglePlayPauseIntent({ positionId: 'P1', isActive: false });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).not.toHaveBeenCalled();
        });

        it('changePlaybackRateIntent ignores inactive positions', () => {
            store.dispatch(actions.audioPlayPauseToggle('P1', true));
            const thunk = thunks.changePlaybackRateIntent({ positionId: 'P2', playbackRate: 1.5 });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).not.toHaveBeenCalled();
        });

        it('changePlaybackRateIntent ignores redundant rate request when provided', () => {
            store.dispatch(actions.audioPlayPauseToggle('P1', true));
            const thunk = thunks.changePlaybackRateIntent({ positionId: 'P1', playbackRate: 1.0 });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).not.toHaveBeenCalled();
        });

        it('changePlaybackRateIntent dispatches when rate differs', () => {
            store.dispatch(actions.audioPlayPauseToggle('P1', true));
            const thunk = thunks.changePlaybackRateIntent({ positionId: 'P1', playbackRate: 1.5 });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).toHaveBeenCalledWith(actions.audioRateChangeRequest('P1'));
        });

        it('toggleVolumeBoostIntent ignores inactive positions', () => {
            store.dispatch(actions.audioPlayPauseToggle('P1', true));
            const thunk = thunks.toggleVolumeBoostIntent({ positionId: 'P2', isBoostActive: true });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).not.toHaveBeenCalled();
        });

        it('toggleVolumeBoostIntent ignores redundant boost state', () => {
            store.dispatch(actions.audioPlayPauseToggle('P1', true));
            const status = {
                is_playing: [true],
                active_position_id: ['P1'],
                playback_rate: [1.0],
                volume_boost: [true],
                current_time: [0]
            };
            store.dispatch(actions.audioStatusUpdate(status));
            const thunk = thunks.toggleVolumeBoostIntent({ positionId: 'P1', isBoostActive: true });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).not.toHaveBeenCalled();
        });

        it('toggleVolumeBoostIntent dispatches when toggling boost', () => {
            store.dispatch(actions.audioPlayPauseToggle('P1', true));
            const thunk = thunks.toggleVolumeBoostIntent({ positionId: 'P1', isBoostActive: true });
            const dispatchSpy = vi.fn();
            thunk(dispatchSpy, store.getState);
            expect(dispatchSpy).toHaveBeenCalledWith(actions.audioBoostToggleRequest('P1', true));
        });

        describe('Marker keyboard workflows', () => {
            it('createMarkerFromKeyboardIntent adds marker at tap and computes metrics', () => {
                window.NoiseSurveyApp.dataCache = {
                    activeLineData: {
                        P1: {
                            Datetime: [1000, 1500, 2000],
                            LZeq: [40, 45, 50]
                        }
                    },
                    activeSpectralData: {
                        P1: {
                            frequency_labels: ['63', '125'],
                            n_freqs: 2,
                            n_times: 3,
                            levels_flat_transposed: [1, 2, 3, 4, 5, 6],
                            times_ms: [1000, 1500, 2000]
                        }
                    }
                };

                store.dispatch(actions.initializeState({
                    availablePositions: ['P1'],
                    selectedParameter: 'LZeq',
                    viewport: { min: 0, max: 3000 },
                    chartVisibility: {}
                }));
                store.dispatch(actions.tap(1500, 'P1', 'figure_P1_timeseries'));

                const thunk = thunks.createMarkerFromKeyboardIntent();
                thunk(store.dispatch, store.getState);

                const state = store.getState();
                expect(state.markers.allIds).toEqual([1]);
                expect(state.markers.byId[1].timestamp).toBe(1500);
                expect(state.markers.byId[1].metrics?.broadband?.[0]?.value).toBe(45);
                expect(state.markers.byId[1].metrics?.spectral?.[0]?.values).toEqual([2, 5]);
            });

            it('createRegionFromMarkersIntent builds a region from the last two markers', () => {
                store.dispatch(actions.initializeState({
                    availablePositions: ['P1'],
                    selectedParameter: 'LZeq',
                    viewport: { min: 0, max: 4000 },
                    chartVisibility: {}
                }));
                store.dispatch(actions.markersReplace([
                    { id: 1, timestamp: 1000 },
                    { id: 2, timestamp: 2500 }
                ]));

                const thunk = thunks.createRegionFromMarkersIntent();
                thunk(store.dispatch, store.getState);

                const state = store.getState();
                expect(state.regions.allIds).toHaveLength(1);
                const region = state.regions.byId[state.regions.allIds[0]];
                expect(region.start).toBe(1000);
                expect(region.end).toBe(2500);
                expect(region.positionId).toBe('P1');
            });
        });
});
});
