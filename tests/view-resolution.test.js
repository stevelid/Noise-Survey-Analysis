import { describe, it, expect } from 'vitest';

import './loadCoreModules.js';

const resolution = window.NoiseSurveyApp.features.view.resolution;

describe('view resolution utilities', () => {
    it('uses the server viewport cap as the auto threshold default when no spectral log threshold exists', () => {
        const models = {
            config: { log_view_max_viewport_seconds: 86400 },
            positionHasLogData: { P1: true },
            positionHasLogSpectral: { P1: false },
            positionLogSpectralThresholdSeconds: { P1: null }
        };
        const threshold = resolution.calculatePositionAutoLogThresholdSeconds(models, 'P1');
        expect(threshold).toBe(86400);
    });

    it('uses the smallest spectral log threshold as the shared auto threshold', () => {
        const models = {
            config: { log_view_max_viewport_seconds: 86400 },
            positionHasLogData: { P1: true, P2: true, P3: false },
            positionHasLogSpectral: { P1: true, P2: false, P3: false },
            positionLogSpectralThresholdSeconds: { P1: 900, P2: null, P3: null }
        };
        const threshold = resolution.calculateGlobalAutoLogThresholdSeconds(models, ['P1', 'P2', 'P3']);
        expect(threshold).toBe(900);
    });

    it('reuses the shared threshold for log-only positions without spectral data', () => {
        const models = {
            config: { log_view_max_viewport_seconds: 86400 },
            positionHasLogData: { P1: true, P2: true },
            positionHasLogSpectral: { P1: true, P2: false },
            positionLogSpectralThresholdSeconds: { P1: 900, P2: null }
        };
        const threshold = resolution.calculatePositionAutoLogThresholdSeconds(models, 'P2');
        expect(threshold).toBe(900);
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
