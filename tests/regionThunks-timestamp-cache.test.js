import { describe, it, beforeEach, expect } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/init.js';

const app = window.NoiseSurveyApp;

if (!app) {
    throw new Error('NoiseSurveyApp namespace is not available.');
}

function makeSource(datetimes) {
    return { data: { Datetime: datetimes } };
}

describe('collectPositionTimestampStats cache', () => {
    let collectPositionTimestampStats;
    let resetCache;

    beforeEach(() => {
        const testNs = app.features?.regions?.__test__;
        if (!testNs) {
            throw new Error('app.features.regions.__test__ not available.');
        }
        collectPositionTimestampStats = testNs.collectPositionTimestampStats;
        resetCache = testNs._resetTimestampStatsCache;

        resetCache();

        app.registry = app.registry || {};
        app.registry.models = app.registry.models || {};
        app.registry.models.timeSeriesSources = {};
    });

    it('caches stats for unchanged sources — second call returns same object reference', () => {
        const overview = makeSource([1000, 2000, 3000]);
        const log = makeSource([1500, 2500]);
        app.registry.models.timeSeriesSources.P1 = { overview, log };

        const first = collectPositionTimestampStats('P1');
        const second = collectPositionTimestampStats('P1');

        expect(first).not.toBeNull();
        expect(second).toBe(first);
    });

    it('invalidates when overview source identity changes', () => {
        const originalOverview = makeSource([1000, 2000]);
        const log = makeSource([1500]);
        app.registry.models.timeSeriesSources.P1 = { overview: originalOverview, log };

        const first = collectPositionTimestampStats('P1');

        // Replace overview with a new object containing different data
        const newOverview = makeSource([5000, 6000, 7000]);
        app.registry.models.timeSeriesSources.P1 = { overview: newOverview, log };

        const second = collectPositionTimestampStats('P1');

        expect(first).not.toBeNull();
        expect(second).not.toBeNull();
        expect(second.min).toBe(1500); // from log (unchanged)
        expect(second.max).toBe(7000); // from new overview
        expect(second).not.toBe(first);
    });

    it('invalidates when log source identity changes', () => {
        const overview = makeSource([1000, 2000]);
        const originalLog = makeSource([1500]);
        app.registry.models.timeSeriesSources.P1 = { overview, log: originalLog };

        const first = collectPositionTimestampStats('P1');

        const newLog = makeSource([9000, 10000]);
        app.registry.models.timeSeriesSources.P1 = { overview, log: newLog };

        const second = collectPositionTimestampStats('P1');

        expect(first).not.toBeNull();
        expect(second).not.toBeNull();
        expect(second.max).toBe(10000);
        expect(second).not.toBe(first);
    });

    it('returns null when no sources registered for position', () => {
        const result = collectPositionTimestampStats('NONEXISTENT');
        expect(result).toBeNull();
    });

    it('returns null when sources exist but contain no finite values', () => {
        const emptyOverview = { data: { Datetime: [] } };
        const emptyLog = { data: { Datetime: [] } };
        app.registry.models.timeSeriesSources.P2 = { overview: emptyOverview, log: emptyLog };

        const result = collectPositionTimestampStats('P2');
        expect(result).toBeNull();
    });
});
