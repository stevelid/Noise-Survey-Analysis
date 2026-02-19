import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/features/view/viewThunks.js';

const app = window.NoiseSurveyApp;
const originalRegionThunks = app.features.regions.thunks;

describe('View thunks', () => {
    beforeEach(() => {
        app.features.regions.thunks = { ...originalRegionThunks };
        app.registry = app.registry || {};
        app.registry.models = {
            config: { server_mode: false, log_view_max_viewport_seconds: 86400 },
            positionHasLogData: { P1: true },
            timeSeriesSources: {
                P1: {
                    overview: { data: { Datetime: [0, 60000, 120000] } },
                    log: { data: { Datetime: [0, 1000, 2000, 3000] } }
                }
            }
        };
    });

    afterEach(() => {
        app.features.regions.thunks = originalRegionThunks;
    });

    it('gracefully returns when dispatch or getState are missing', () => {
        const dispatch = vi.fn();
        const getState = vi.fn();
        const thunk = app.features.view.thunks.handleTabSwitchIntent({ newIndex: 1 });
        thunk();
        expect(dispatch).not.toHaveBeenCalled();
        expect(getState).not.toHaveBeenCalled();
    });

    it('dispatches enter comparison mode when switching to the comparison tab', () => {
        const dispatched = vi.fn();
        const enterThunk = vi.fn();
        app.features.regions.thunks.enterComparisonModeIntent = vi.fn(() => enterThunk);

        const thunk = app.features.view.thunks.handleTabSwitchIntent({ newIndex: 1 });
        thunk(dispatched, () => ({ view: { mode: 'analysis' } }));

        expect(app.features.regions.thunks.enterComparisonModeIntent).toHaveBeenCalledTimes(1);
        expect(dispatched).toHaveBeenCalledTimes(1);
        expect(dispatched).toHaveBeenCalledWith(enterThunk);
    });

    it('dispatches exit comparison mode when leaving the comparison tab', () => {
        const dispatched = vi.fn();
        const exitThunk = vi.fn();
        app.features.regions.thunks.exitComparisonModeIntent = vi.fn(() => exitThunk);

        const thunk = app.features.view.thunks.handleTabSwitchIntent({ newIndex: 0 });
        thunk(dispatched, () => ({ view: { mode: 'comparison' } }));

        expect(app.features.regions.thunks.exitComparisonModeIntent).toHaveBeenCalledTimes(1);
        expect(dispatched).toHaveBeenCalledTimes(1);
        expect(dispatched).toHaveBeenCalledWith(exitThunk);
    });

    it('toggles to overview when viewport exceeds resolved threshold', () => {
        const dispatch = vi.fn();
        const getState = () => ({
            view: {
                availablePositions: ['P1'],
                globalViewType: 'log',
                logViewThreshold: { mode: 'manual', seconds: 30 }
            }
        });

        const thunk = app.features.view.thunks.handleViewportChangeIntent({ min: 0, max: 120000 });
        thunk(dispatch, getState);

        expect(dispatch).toHaveBeenNthCalledWith(1, app.actions.viewportChange(0, 120000));
        expect(dispatch).toHaveBeenNthCalledWith(2, app.actions.viewToggle('overview'));
    });

    it('toggles to log when viewport is within resolved threshold', () => {
        const dispatch = vi.fn();
        const getState = () => ({
            view: {
                availablePositions: ['P1'],
                globalViewType: 'overview',
                logViewThreshold: { mode: 'manual', seconds: 300 }
            }
        });

        const thunk = app.features.view.thunks.handleViewportChangeIntent({ min: 0, max: 60000 });
        thunk(dispatch, getState);

        expect(dispatch).toHaveBeenNthCalledWith(1, app.actions.viewportChange(0, 60000));
        expect(dispatch).toHaveBeenNthCalledWith(2, app.actions.viewToggle('log'));
    });
});
