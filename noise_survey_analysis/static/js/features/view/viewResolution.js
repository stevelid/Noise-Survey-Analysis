// noise_survey_analysis/static/js/features/view/viewResolution.js

/**
 * @fileoverview Shared utilities for viewport resolution and log threshold behavior.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const DEFAULT_SERVER_LIMIT_SECONDS = 86400;
    const DEFAULT_AUTO_THRESHOLD_SECONDS = 3600;
    const DEFAULT_OVERVIEW_STEPS = 10;
    const DEFAULT_LOG_STEPS = 360;

    function computeMedianPositiveStepMs(values, maxPairs = 4000) {
        if (!values || typeof values.length !== 'number' || values.length < 2) {
            return null;
        }

        const diffs = [];
        const pairCount = Math.min(values.length - 1, Math.max(1, Math.floor(maxPairs)));
        for (let i = 0; i < pairCount; i++) {
            const a = Number(values[i]);
            const b = Number(values[i + 1]);
            const diff = b - a;
            if (Number.isFinite(diff) && diff > 0) {
                diffs.push(diff);
            }
        }

        if (!diffs.length) {
            return null;
        }

        diffs.sort((x, y) => x - y);
        return diffs[Math.floor(diffs.length / 2)];
    }

    function getServerLogViewportLimitSeconds(models) {
        const raw = Number(models?.config?.log_view_max_viewport_seconds);
        return (Number.isFinite(raw) && raw > 0) ? raw : DEFAULT_SERVER_LIMIT_SECONDS;
    }

    function secondsToMinutes(seconds) {
        const numeric = Number(seconds);
        return (Number.isFinite(numeric) && numeric > 0) ? numeric / 60 : null;
    }

    function minutesToSeconds(minutes) {
        const numeric = Number(minutes);
        return (Number.isFinite(numeric) && numeric > 0) ? numeric * 60 : null;
    }

    function clampNumber(value, min, max) {
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) {
            return null;
        }
        const minBound = Number.isFinite(min) ? min : numeric;
        const maxBound = Number.isFinite(max) ? max : numeric;
        return Math.min(maxBound, Math.max(minBound, numeric));
    }

    function normalizeLogThreshold(input) {
        if (typeof input === 'number' || typeof input === 'string') {
            const seconds = Number(input);
            return {
                mode: (Number.isFinite(seconds) && seconds > 0) ? 'manual' : 'auto',
                seconds: (Number.isFinite(seconds) && seconds > 0) ? seconds : null
            };
        }

        const rawMode = typeof input?.mode === 'string' ? input.mode.toLowerCase() : 'auto';
        const mode = rawMode === 'manual' ? 'manual' : 'auto';
        const rawSeconds = Number(input?.seconds);
        const hasManualSeconds = mode === 'manual' && Number.isFinite(rawSeconds) && rawSeconds > 0;
        const seconds = hasManualSeconds
            ? rawSeconds
            : null;
        if (mode === 'manual' && !hasManualSeconds) {
            return { mode: 'auto', seconds: null };
        }

        return { mode, seconds };
    }

    function selectLogThresholdConfig(viewState) {
        return normalizeLogThreshold(viewState?.logViewThreshold);
    }

    function calculatePositionAutoLogThresholdSeconds(models, positionId) {
        const overviewTimes = models?.timeSeriesSources?.[positionId]?.overview?.data?.Datetime;
        const logTimes = models?.timeSeriesSources?.[positionId]?.log?.data?.Datetime;
        const overviewStepMs = computeMedianPositiveStepMs(overviewTimes);
        const logStepMs = computeMedianPositiveStepMs(logTimes);

        const candidates = [DEFAULT_AUTO_THRESHOLD_SECONDS];
        if (Number.isFinite(overviewStepMs) && overviewStepMs > 0) {
            candidates.push((overviewStepMs / 1000) * DEFAULT_OVERVIEW_STEPS);
        }
        if (Number.isFinite(logStepMs) && logStepMs > 0) {
            candidates.push((logStepMs / 1000) * DEFAULT_LOG_STEPS);
        }

        const threshold = Math.min(...candidates);
        return (Number.isFinite(threshold) && threshold > 0) ? threshold : DEFAULT_AUTO_THRESHOLD_SECONDS;
    }

    function calculateGlobalAutoLogThresholdSeconds(models, positions) {
        if (!Array.isArray(positions) || !positions.length) {
            return Math.min(DEFAULT_AUTO_THRESHOLD_SECONDS, getServerLogViewportLimitSeconds(models));
        }

        let minThreshold = Infinity;
        positions.forEach(positionId => {
            const value = calculatePositionAutoLogThresholdSeconds(models, positionId);
            if (Number.isFinite(value) && value > 0) {
                minThreshold = Math.min(minThreshold, value);
            }
        });

        const fallback = (Number.isFinite(minThreshold) && minThreshold > 0)
            ? minThreshold
            : DEFAULT_AUTO_THRESHOLD_SECONDS;

        return Math.min(fallback, getServerLogViewportLimitSeconds(models));
    }

    function resolveLogThresholdSeconds(models, viewState, positionId = null) {
        const serverLimit = getServerLogViewportLimitSeconds(models);
        const config = selectLogThresholdConfig(viewState);

        if (config.mode === 'manual' && Number.isFinite(config.seconds) && config.seconds > 0) {
            return Math.min(config.seconds, serverLimit);
        }

        const positions = Array.isArray(viewState?.availablePositions) ? viewState.availablePositions : [];
        if (typeof positionId === 'string' && positionId.length) {
            return Math.min(calculatePositionAutoLogThresholdSeconds(models, positionId), serverLimit);
        }
        return calculateGlobalAutoLogThresholdSeconds(models, positions);
    }

    function getViewportSpanSeconds(viewport) {
        const min = Number(viewport?.min);
        const max = Number(viewport?.max);
        if (!Number.isFinite(min) || !Number.isFinite(max)) {
            return null;
        }
        return Math.abs(max - min) / 1000;
    }

    function determineViewportViewType(models, viewState, viewport, options = {}) {
        const spanSeconds = getViewportSpanSeconds(viewport);
        if (!Number.isFinite(spanSeconds)) {
            return null;
        }
        const thresholdSeconds = resolveLogThresholdSeconds(models, viewState, options.positionId || null);
        return spanSeconds <= thresholdSeconds ? 'log' : 'overview';
    }

    app.features = app.features || {};
    app.features.view = app.features.view || {};
    app.features.view.resolution = {
        DEFAULT_AUTO_THRESHOLD_SECONDS,
        DEFAULT_SERVER_LIMIT_SECONDS,
        computeMedianPositiveStepMs,
        getServerLogViewportLimitSeconds,
        secondsToMinutes,
        minutesToSeconds,
        clampNumber,
        normalizeLogThreshold,
        selectLogThresholdConfig,
        calculatePositionAutoLogThresholdSeconds,
        calculateGlobalAutoLogThresholdSeconds,
        resolveLogThresholdSeconds,
        getViewportSpanSeconds,
        determineViewportViewType
    };
})(window.NoiseSurveyApp);
