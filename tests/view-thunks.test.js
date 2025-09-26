import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/features/view/viewThunks.js';

const app = window.NoiseSurveyApp;
const originalRegionThunks = app.features.regions.thunks;

describe('View thunks', () => {
    beforeEach(() => {
        app.features.regions.thunks = { ...originalRegionThunks };
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
});
