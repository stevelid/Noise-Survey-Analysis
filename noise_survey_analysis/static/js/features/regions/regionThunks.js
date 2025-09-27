// noise_survey_analysis/static/js/features/regions/regionThunks.js

/**
 * @fileoverview Thunks handling region and comparison workflows.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;
    app.registry = app.registry || {};
    const registry = app.registry;
    const MIN_REGION_WIDTH_MS = 1;
    const HOUR_MS = 60 * 60 * 1000;
    const DAY_MS = 24 * HOUR_MS;
    const DAYTIME_START_HOUR = 7;
    const DAYTIME_END_HOUR = 23;
    const AUTO_REGION_MODES = {
        daytime: { color: '#4caf50' },
        nighttime: { color: '#7e57c2' }
    };

    function getRegionAreas(region) {
        if (!region) return [];
        if (Array.isArray(region.areas) && region.areas.length) {
            return region.areas;
        }
        if (Number.isFinite(region.start) && Number.isFinite(region.end)) {
            return [{ start: region.start, end: region.end }];
        }
        return [];
    }

    const viewSelectors = app.features?.view?.selectors || {};
    const regionSelectors = app.features?.regions?.selectors || {};

    function collectTimestampsFromSource(source) {
        const data = source?.data;
        if (!data || !data.Datetime) {
            return [];
        }
        const raw = data.Datetime;
        const timestamps = [];
        for (let index = 0; index < raw.length; index++) {
            const value = Number(raw[index]);
            if (Number.isFinite(value)) {
                timestamps.push(value);
            }
        }
        return timestamps;
    }

    function collectPositionTimestamps(positionId) {
        if (!positionId) {
            return [];
        }
        const sources = registry.models?.timeSeriesSources?.[positionId];
        if (!sources) {
            return [];
        }
        const overviewTimes = collectTimestampsFromSource(sources.overview);
        const logTimes = collectTimestampsFromSource(sources.log);
        if (!overviewTimes.length && !logTimes.length) {
            return [];
        }
        const combined = [...overviewTimes, ...logTimes];
        combined.sort((a, b) => a - b);
        const deduped = [];
        let previous = null;
        combined.forEach(timestamp => {
            if (timestamp !== previous) {
                deduped.push(timestamp);
                previous = timestamp;
            }
        });
        return deduped;
    }

    function clampInterval(start, end, min, max) {
        if (!Number.isFinite(start) || !Number.isFinite(end)) {
            return null;
        }
        const clampedStart = Math.max(start, min);
        const clampedEnd = Math.min(end, max);
        if (clampedStart >= clampedEnd) {
            return null;
        }
        return { start: clampedStart, end: clampedEnd };
    }

    function buildDailyIntervals(timestamps, mode) {
        if (!Array.isArray(timestamps) || !timestamps.length) {
            return [];
        }
        const minTimestamp = timestamps[0];
        const maxTimestamp = timestamps[timestamps.length - 1];
        if (!Number.isFinite(minTimestamp) || !Number.isFinite(maxTimestamp)) {
            return [];
        }

        const startDate = new Date(minTimestamp);
        startDate.setHours(0, 0, 0, 0);
        const endDate = new Date(maxTimestamp);
        endDate.setHours(0, 0, 0, 0);

        const intervals = [];
        for (let day = startDate.getTime(); day <= endDate.getTime(); day += DAY_MS) {
            if (mode === 'nighttime') {
                const rawStart = day + DAYTIME_END_HOUR * HOUR_MS;
                const rawEnd = day + DAY_MS + DAYTIME_START_HOUR * HOUR_MS;
                const interval = clampInterval(rawStart, rawEnd, minTimestamp, maxTimestamp);
                if (interval) {
                    intervals.push(interval);
                }
            } else {
                const rawStart = day + DAYTIME_START_HOUR * HOUR_MS;
                const rawEnd = day + DAYTIME_END_HOUR * HOUR_MS;
                const interval = clampInterval(rawStart, rawEnd, minTimestamp, maxTimestamp);
                if (interval) {
                    intervals.push(interval);
                }
            }
        }
        return intervals;
    }

    function enterComparisonModeIntent() {
        return function (dispatch) {
            if (!actions) return;
            dispatch(actions.comparisonModeEntered());
        };
    }

    function exitComparisonModeIntent() {
        return function (dispatch) {
            if (!actions) return;
            dispatch(actions.comparisonModeExited());
        };
    }

    function updateIncludedPositionsIntent(payload) {
        return function (dispatch) {
            if (!actions) return;
            const includedPositions = Array.isArray(payload?.includedPositions)
                ? payload.includedPositions
                : [];
            dispatch(actions.comparisonPositionsUpdated(includedPositions));
        };
    }

    function updateComparisonSliceIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') return;

            const state = getState();
            const viewState = viewSelectors.selectViewState ? viewSelectors.selectViewState(state) : state?.view;
            if (!viewState || viewState.mode !== 'comparison') {
                return;
            }

            const rawStart = Number(payload?.start);
            const rawEnd = Number(payload?.end);
            const hasBounds = Number.isFinite(rawStart) && Number.isFinite(rawEnd) && rawStart !== rawEnd;

            const nextStart = hasBounds ? Math.min(rawStart, rawEnd) : null;
            const nextEnd = hasBounds ? Math.max(rawStart, rawEnd) : null;

            const currentComparison = viewSelectors.selectComparisonState
                ? viewSelectors.selectComparisonState(state)
                : viewState.comparison || {};

            if (currentComparison.start === nextStart && currentComparison.end === nextEnd) {
                return;
            }

            dispatch(actions.comparisonSliceUpdated(nextStart, nextEnd));
        };
    }

    function createRegionsFromComparisonIntent() {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') return;

            const state = getState();
            const viewState = viewSelectors.selectViewState ? viewSelectors.selectViewState(state) : state?.view || {};
            const comparisonState = viewSelectors.selectComparisonState ? viewSelectors.selectComparisonState(state) : viewState.comparison || {};

            if (viewState.mode !== 'comparison' || !comparisonState.isActive) {
                return;
            }

            const rawStart = Number(comparisonState.start);
            const rawEnd = Number(comparisonState.end);
            if (!Number.isFinite(rawStart) || !Number.isFinite(rawEnd) || rawStart === rawEnd) {
                return;
            }

            const start = Math.min(rawStart, rawEnd);
            const end = Math.max(rawStart, rawEnd);

            const includedPositions = Array.isArray(comparisonState.includedPositions)
                ? comparisonState.includedPositions
                : [];

            if (!includedPositions.length) {
                return;
            }

            const regions = includedPositions
                .filter(positionId => typeof positionId === 'string' && positionId)
                .map(positionId => ({ positionId, start, end }));

            if (!regions.length) {
                return;
            }

            dispatch(actions.regionsAdded(regions));
            dispatch(actions.comparisonModeExited());
        };
    }

    function createRegionIntent(payload) {
        return function (dispatch, getState) {
            if (!actions) return;
            const { positionId, start, end } = payload || {};
            if (!positionId || !Number.isFinite(start) || !Number.isFinite(end)) return;
            if (Math.abs(end - start) < MIN_REGION_WIDTH_MS) return;

            const state = typeof getState === 'function' ? getState() : null;
            const viewState = viewSelectors.selectViewState
                ? viewSelectors.selectViewState(state)
                : state?.view;
            if (viewState?.mode === 'comparison') {
                return;
            }
            const regionsState = state?.regions;
            const rawTargetId = regionsState?.addAreaTargetId;
            const targetId = Number.isFinite(rawTargetId) ? rawTargetId : null;
            const targetRegion = targetId !== null ? regionsState?.byId?.[targetId] : null;

            if (targetRegion && targetRegion.positionId === positionId) {
                const existingAreas = getRegionAreas(targetRegion);
                const nextAreas = [...existingAreas, { start, end }];
                dispatch(actions.regionUpdate(targetRegion.id, { areas: nextAreas }));
                if (regionsState?.selectedId !== targetRegion.id) {
                    dispatch(actions.regionSelect(targetRegion.id));
                }
                return;
            }

            if (targetId !== null && actions.regionSetAddAreaMode) {
                dispatch(actions.regionSetAddAreaMode(null));
            }

            dispatch(actions.regionAdd(positionId, start, end));
        };
    }


    function createAutoRegionsIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function') {
                return;
            }
            const state = typeof getState === 'function' ? getState() : null;
            const availablePositions = Array.isArray(state?.view?.availablePositions)
                ? state.view.availablePositions
                : [];
            const fallbackPositions = registry.models?.timeSeriesSources
                ? Object.keys(registry.models.timeSeriesSources)
                : [];
            const positions = availablePositions.length ? availablePositions : fallbackPositions;
            if (!positions.length) {
                return;
            }

            const requestedModes = (() => {
                const primary = typeof payload?.mode === 'string' ? payload.mode : null;
                const modeList = Array.isArray(payload?.modes) ? payload.modes : null;
                const raw = modeList && modeList.length ? modeList : (primary ? [primary] : null);
                const result = [];
                const candidates = raw && raw.length ? raw : Object.keys(AUTO_REGION_MODES);
                candidates.forEach(candidate => {
                    const normalized = candidate === 'nighttime' ? 'nighttime' : candidate === 'daytime' ? 'daytime' : null;
                    if (normalized && !result.includes(normalized)) {
                        result.push(normalized);
                    }
                });
                return result.length ? result : Object.keys(AUTO_REGION_MODES);
            })();

            const generated = [];
            positions.forEach(positionId => {
                if (!positionId) {
                    return;
                }
                const timestamps = collectPositionTimestamps(positionId);
                if (!timestamps.length) {
                    return;
                }
                requestedModes.forEach(modeName => {
                    const config = AUTO_REGION_MODES[modeName];
                    if (!config) {
                        return;
                    }
                    const intervals = buildDailyIntervals(timestamps, modeName);
                    intervals.forEach(interval => {
                        generated.push({
                            positionId,
                            start: interval.start,
                            end: interval.end,
                            color: config.color
                        });
                    });
                });
            });

            if (!generated.length) {
                return;
            }

            dispatch(actions.regionsAdded(generated));
        };
    }


    function mergeRegionIntoSelectedIntent(sourceId) {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') return;
            const state = getState();
            const regionsState = state?.regions;
            const targetId = regionsState?.selectedId;
            const sourceNumericId = Number(sourceId);
            if (!Number.isFinite(targetId) || !Number.isFinite(sourceNumericId) || targetId === sourceNumericId) {
                return;
            }
            const targetRegion = regionsState?.byId?.[targetId];
            const sourceRegion = regionsState?.byId?.[sourceNumericId];
            if (!targetRegion || !sourceRegion) {
                return;
            }
            if (targetRegion.positionId !== sourceRegion.positionId) {
                console.warn('[Regions] Cannot merge regions from different positions.');
                return;
            }
            const combinedAreas = [...getRegionAreas(targetRegion), ...getRegionAreas(sourceRegion)];
            dispatch(actions.regionUpdate(targetId, { areas: combinedAreas }));
            dispatch(actions.regionRemove(sourceNumericId));
            if (regionsState?.addAreaTargetId === sourceNumericId) {
                dispatch(actions.regionSetAddAreaMode(null));
            }
        };
    }

    function toggleRegionCreationIntent() {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') {
                return;
            }

            const state = getState();
            const tapState = state?.interaction?.tap;
            if (!tapState?.isActive || !Number.isFinite(tapState.timestamp) || !tapState.position) {
                return;
            }

            const pending = state?.interaction?.pendingRegionStart;
            if (!pending || pending.positionId !== tapState.position) {
                dispatch(actions.regionCreationStarted({
                    timestamp: tapState.timestamp,
                    positionId: tapState.position
                }));
                return;
            }

            const start = Number(pending.timestamp);
            const end = Number(tapState.timestamp);
            if (!Number.isFinite(start) || !Number.isFinite(end) || start === end) {
                dispatch(actions.regionCreationCancelled());
                return;
            }

            const normalizedStart = Math.min(start, end);
            const normalizedEnd = Math.max(start, end);
            if (Math.abs(normalizedEnd - normalizedStart) < MIN_REGION_WIDTH_MS) {
                dispatch(actions.regionCreationCancelled());
                return;
            }

            dispatch(actions.regionAdd(pending.positionId, normalizedStart, normalizedEnd));
            dispatch(actions.regionCreationCancelled());
        };
    }

    function resizeSelectedRegionIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') return;
            const { key, modifiers = {} } = payload || {};
            const direction = key === 'ArrowRight' ? 1 : key === 'ArrowLeft' ? -1 : 0;
            if (!direction) return;

            const state = getState();
            const regionsState = regionSelectors.selectRegionsState
                ? regionSelectors.selectRegionsState(state)
                : state?.regions;
            const selectedId = regionsState?.selectedId;
            if (!selectedId) return;
            const region = regionsState.byId[selectedId];
            if (!region) return;

            const adjustStart = Boolean(modifiers.ctrl);
            const adjustEnd = Boolean(modifiers.alt);
            if (!adjustStart && !adjustEnd) {
                return;
            }

            const stepSize = Number.isFinite(state?.interaction?.keyboard?.stepSizeMs)
                ? state.interaction.keyboard.stepSizeMs
                : 1000;
            const delta = direction * stepSize;
            const viewport = viewSelectors.selectViewport ? viewSelectors.selectViewport(state) : state?.view?.viewport || {};
            const viewportMin = Number.isFinite(viewport.min) ? viewport.min : -Infinity;
            const viewportMax = Number.isFinite(viewport.max) ? viewport.max : Infinity;

            let nextStart = region.start;
            let nextEnd = region.end;

            if (adjustStart) { //todo: move key modifiers to config
                const rawStart = region.start + delta;
                const maxStart = region.end - MIN_REGION_WIDTH_MS;
                const clampedStart = Math.max(Math.min(maxStart, rawStart), viewportMin);
                if (clampedStart !== region.start) {
                    nextStart = clampedStart;
                }
            }

            if (adjustEnd) { //todo: move key modifiers to config
                const rawEnd = region.end + delta;
                const minEnd = nextStart + MIN_REGION_WIDTH_MS;
                const clampedEnd = Math.min(Math.max(minEnd, rawEnd), viewportMax);
                if (clampedEnd !== region.end) {
                    nextEnd = clampedEnd;
                }
            }

            const changes = {};
            if (nextStart !== region.start) {
                changes.start = nextStart;
            }
            if (nextEnd !== region.end) {
                changes.end = nextEnd;
            }

            if (Object.keys(changes).length) {
                dispatch(actions.regionUpdate(region.id, changes));
            }
        };
    }

    app.features = app.features || {};
    app.features.regions = app.features.regions || {};
    app.features.regions.thunks = {
        enterComparisonModeIntent,
        exitComparisonModeIntent,
        updateIncludedPositionsIntent,
        updateComparisonSliceIntent,
        createRegionsFromComparisonIntent,
        createRegionIntent,
        createAutoRegionsIntent,
        mergeRegionIntoSelectedIntent,
        resizeSelectedRegionIntent,
        toggleRegionCreationIntent
    };
})(window.NoiseSurveyApp);




