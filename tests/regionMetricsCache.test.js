import { describe, it, beforeEach, expect, vi } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/init.js';
import '../noise_survey_analysis/static/js/services/session/sessionManager.js';

const app = window.NoiseSurveyApp;

if (!app) {
    throw new Error('NoiseSurveyApp namespace is not available.');
}

describe('Region metrics cache invalidation', () => {
    beforeEach(() => {
        vi.restoreAllMocks();
        if (app.init?.reInitializeStore) {
            app.init.reInitializeStore();
        }
        if (typeof app.regions?.__ensureMetricsSubscription === 'function') {
            app.regions.__ensureMetricsSubscription();
        }
    });

    it('invalidates cached metrics when region boundaries change', () => {
        const { store, actions } = app;
        if (!store || !actions) {
            throw new Error('Store or actions are not available for the test.');
        }

        store.dispatch(actions.regionAdd('P1', 0, 1000));
        const state = store.getState();
        const regionId = state?.regions?.allIds?.[0];
        expect(Number.isFinite(regionId)).toBe(true);

        const invalidateSpy = vi.spyOn(app.regions, 'invalidateRegionMetrics');

        store.dispatch(actions.regionUpdate(regionId, { areas: [{ start: 0, end: 1500 }] }));

        expect(invalidateSpy).toHaveBeenCalledWith(regionId);
        invalidateSpy.mockRestore();
    });

    it('clears the metrics cache when applying a saved workspace', () => {
        const { session, regions, createInitialState } = app;
        if (!session || !regions || typeof session.applyWorkspaceState !== 'function') {
            throw new Error('Session helpers are not available for the test.');
        }

        const invalidateSpy = vi.spyOn(regions, 'invalidateMetricsCache');
        const payload = {
            appState: createInitialState(),
            sourceConfigs: []
        };

        const applied = session.applyWorkspaceState(payload);
        expect(applied).toBe(true);
        expect(invalidateSpy).toHaveBeenCalled();
        invalidateSpy.mockRestore();
    });
});
