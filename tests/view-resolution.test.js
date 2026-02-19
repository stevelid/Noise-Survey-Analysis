import { describe, it, expect } from 'vitest';

import './loadCoreModules.js';

const resolution = window.NoiseSurveyApp.features.view.resolution;

describe('view resolution utilities', () => {
    it('computes auto threshold as min(1h, 10 overview steps, 360 log steps)', () => {
        const models = {
            config: { log_view_max_viewport_seconds: 86400 },
            timeSeriesSources: {
                P1: {
                    overview: { data: { Datetime: [0, 10000, 20000] } }, // 10s step -> 100s
                    log: { data: { Datetime: [0, 1000, 2000, 3000] } }   // 1s step -> 360s
                }
            }
        };
        const threshold = resolution.calculatePositionAutoLogThresholdSeconds(models, 'P1');
        expect(threshold).toBe(100);
    });

    it('resolves manual threshold and caps to server max', () => {
        const models = { config: { log_view_max_viewport_seconds: 300 } };
        const viewState = { logViewThreshold: { mode: 'manual', seconds: 900 }, availablePositions: ['P1'] };
        const threshold = resolution.resolveLogThresholdSeconds(models, viewState, 'P1');
        expect(threshold).toBe(300);
    });

    it('determines log/overview view type from viewport span', () => {
        const models = { config: { log_view_max_viewport_seconds: 86400 } };
        const viewState = { logViewThreshold: { mode: 'manual', seconds: 60 }, availablePositions: ['P1'] };
        expect(resolution.determineViewportViewType(models, viewState, { min: 0, max: 59000 })).toBe('log');
        expect(resolution.determineViewportViewType(models, viewState, { min: 0, max: 61000 })).toBe('overview');
    });
});
