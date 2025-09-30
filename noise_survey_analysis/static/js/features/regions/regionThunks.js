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

    const markerSelectors = app.features?.markers?.selectors || {};
    const constants = app.constants || {};
    const sidePanelTabs = constants.sidePanelTabs || {};
    const SIDE_PANEL_TAB_REGIONS = Number.isFinite(sidePanelTabs.regions)
        ? sidePanelTabs.regions
        : 0;


    function collectTimestampsFromSource(source) {
        const data = source?.data;
        if (!data || !data.Datetime) {
            return [];
        }
        const raw = data.Datetime;
        const timestamps = [];
        const rawArray = Array.from(raw);
        for (let index = 0; index < rawArray.length; index++) {
            const value = Number(rawArray[index]);
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
        const sources = registry?.models?.timeSeriesSources?.[positionId];
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
        const rawBuffer = Math.ceil(timestamps.length * 0.002);
        const maxBuffer = Math.floor((timestamps.length - 1) / 2);
        const startAndEndBuffer = Math.min(Math.max(rawBuffer, 0), maxBuffer);
        const minIndex = Math.min(startAndEndBuffer, timestamps.length - 1);
        const maxIndex = Math.max(timestamps.length - 1 - startAndEndBuffer, minIndex);
        const minTimestamp = timestamps[minIndex]; // skip the first 0.2% of timestamps when possible
        const maxTimestamp = timestamps[maxIndex]; // skip the last 0.2% of timestamps when possible
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
                const extendedMax = Math.max(maxTimestamp, rawEnd);
                const effectiveMin = Math.min(minTimestamp, rawStart);
                const interval = clampInterval(rawStart, rawEnd, effectiveMin, extendedMax);
                if (interval) {
                    intervals.push(interval);
                }
            } else {
                const rawStart = day + DAYTIME_START_HOUR * HOUR_MS;
                const rawEnd = day + DAYTIME_END_HOUR * HOUR_MS;
                const extendedMax = Math.max(maxTimestamp, rawEnd);
                const effectiveMin = Math.min(minTimestamp, rawStart);
                const interval = clampInterval(rawStart, rawEnd, effectiveMin, extendedMax);
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
            console.log('[RegionThunk] dispatching setActiveSidePanelTab'); // DEBUG
            dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_REGIONS));
        };
    }


    /**
     * Selects a region by ID.
     *
     * @param {number} regionId - The ID of the region to select.
     * @returns {Function} Thunk function for dispatch.
     */
    function selectRegionIntent(regionId) {
        return function (dispatch) {
            if (!actions || typeof dispatch !== 'function') {
                return;
            }

            const normalizedId = Number(regionId);
            if (!Number.isFinite(normalizedId)) {
                dispatch(actions.regionClearSelection());
                return;
            }

            dispatch(actions.regionSelect(normalizedId));
            if (typeof actions.markerSelect === 'function') {
                console.log('[RegionThunk] dispatching markerSelect(null)'); // DEBUG
                dispatch(actions.markerSelect(null));
            }
            if (typeof actions.setActiveSidePanelTab === 'function') {
                console.log('[RegionThunk] dispatching setActiveSidePanelTab'); // DEBUG
                dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_REGIONS));
            }
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
            const regionsState = state.regions;
            const targetId = regionsState.addAreaTargetId;
            const targetRegion = Number.isFinite(targetId) ? regionsState.byId[targetId] : null;

            if (targetRegion && targetRegion.positionId === positionId) {
                const existingAreas = getRegionAreas(targetRegion);
                const nextAreas = [...existingAreas, { start, end }];
                dispatch(actions.regionUpdate(targetRegion.id, { areas: nextAreas }));
                if (regionsState?.selectedId !== targetRegion.id) {
                    dispatch(selectRegionIntent(targetRegion.id));
                }
                return;
            }

            if (targetId !== null && actions.regionSetAddAreaMode) {
                dispatch(actions.regionSetAddAreaMode(null));
            }

            const nextRegionId = Number.isFinite(regionsState?.counter)
                ? regionsState.counter
                : null;

            console.log('[regionAdd] Adding region:', { positionId, start, end });
            dispatch(actions.regionAdd(positionId, start, end));

            const newState = getState();
            const newRegionId = newState.regions.selectedId; // The reducer sets the new region as selected

            // Orchestrate post-creation side effects by calling the canonical selection thunk
            if (Number.isFinite(newRegionId)) {
                dispatch(selectRegionIntent(newRegionId));
            }
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
            const shouldAggregate = requestedModes.length === 1;

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
                    
                    if (intervals.length > 0) {
                        const baseTitle = `${modeName.charAt(0).toUpperCase() + modeName.slice(1)} - ${positionId}`;
                        if (shouldAggregate) {
                            generated.push({
                                positionId,
                                start: intervals[0].start,
                                end: intervals[intervals.length - 1].end,
                                areas: intervals,
                                color: config.color,
                                note: baseTitle
                            });
                        } else {
                            intervals.forEach((interval, index) => {
                                const titleSuffix = intervals.length > 1 ? ` (${index + 1})` : '';
                                generated.push({
                                    positionId,
                                    start: interval.start,
                                    end: interval.end,
                                    areas: [interval],
                                    color: config.color,
                                    note: `${baseTitle}${titleSuffix}`
                                });
                            });
                        }
                    }
                });
            });

            if (!generated.length) {
                return;
            }

            dispatch(actions.regionsAdded(generated));
        };
    }


     /**
     * A stateful thunk that manages the two-step region creation process via keyboard.
     * First press pins the start, second press finalizes and creates the region.
     */
     function toggleRegionCreationIntent() {
        return function (dispatch, getState) {
            if (!actions || !getState || !dispatch) return;

            const state = getState();
            const tapState = state.interaction.tap;
            if (!tapState?.isActive || !Number.isFinite(tapState.timestamp) || !tapState.position) {
                return;
            }

            const pending = state.interaction.pendingRegionStart;

            if (!pending || pending.positionId !== tapState.position) {
                // --- First 'R' press: Start the creation process ---
                dispatch(actions.regionCreationStarted({
                    timestamp: tapState.timestamp,
                    positionId: tapState.position
                }));
                return;
            }

            // --- Second 'R' press: Finalize the region ---
            const start = Number(pending.timestamp);
            const end = Number(tapState.timestamp);

            // Cancel the pending state regardless of what happens next
            dispatch(actions.regionCreationCancelled());
            
            // Validate the region before creation
            if (!Number.isFinite(start) || !Number.isFinite(end) || start === end) {
                return;
            }
            const normalizedStart = Math.min(start, end);
            const normalizedEnd = Math.max(start, end);
            if (Math.abs(normalizedEnd - normalizedStart) < MIN_REGION_WIDTH_MS) {
                return;
            }

            // Delegate the actual creation and all its side effects to the canonical thunk
            dispatch(createRegionIntent({
                positionId: pending.positionId,
                start: normalizedStart,
                end: normalizedEnd
            }));
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

            const areas = getRegionAreas(region);
            if (!areas.length) {
                return;
            }

            const stepSize = Number.isFinite(state?.interaction?.keyboard?.stepSizeMs)
                ? state.interaction.keyboard.stepSizeMs
                : 1000;
            const delta = direction * stepSize;
            const viewport = viewSelectors.selectViewport ? viewSelectors.selectViewport(state) : state?.view?.viewport || {};
            const viewportMin = Number.isFinite(viewport.min) ? viewport.min : -Infinity;
            const viewportMax = Number.isFinite(viewport.max) ? viewport.max : Infinity;

            const hoverState = state?.interaction?.hover;
            const hoverTimestamp = hoverState?.isActive
                && hoverState?.position === region.positionId
                && Number.isFinite(hoverState?.timestamp)
                ? hoverState.timestamp
                : null;
            const tapState = state?.interaction?.tap;
            const tapTimestamp = tapState?.isActive
                && tapState?.position === region.positionId
                && Number.isFinite(tapState?.timestamp)
                ? tapState.timestamp
                : null;
            const pointerTimestamp = hoverTimestamp != null ? hoverTimestamp : tapTimestamp;

            const nextAreas = areas.map(area => ({ start: area.start, end: area.end }));

            let targetAreaIndex = -1;
            if (Number.isFinite(pointerTimestamp)) {
                targetAreaIndex = nextAreas.findIndex(area => pointerTimestamp >= area.start && pointerTimestamp <= area.end);
            }

            if (adjustStart) {
                const index = targetAreaIndex !== -1 ? targetAreaIndex : 0;
                const area = nextAreas[index];
                const previousEnd = index > 0 ? nextAreas[index - 1].end : -Infinity;
                const lowerBound = Math.max(viewportMin, previousEnd);
                const upperBound = area.end - MIN_REGION_WIDTH_MS;
                const rawStart = area.start + delta;
                const clampedStart = Math.max(Math.min(rawStart, upperBound), lowerBound);
                if (clampedStart !== area.start) {
                    area.start = clampedStart;
                }
            }

            if (adjustEnd) {
                const index = targetAreaIndex !== -1 ? targetAreaIndex : nextAreas.length - 1;
                const area = nextAreas[index];
                const nextStart = index < nextAreas.length - 1 ? nextAreas[index + 1].start : Infinity;
                const upperBound = Math.min(viewportMax, nextStart);
                const lowerBound = area.start + MIN_REGION_WIDTH_MS;
                const rawEnd = area.end + delta;
                const clampedEnd = Math.min(Math.max(rawEnd, lowerBound), upperBound);
                if (clampedEnd !== area.end) {
                    area.end = clampedEnd;
                }
            }

            let mutated = false;
            for (let i = 0; i < nextAreas.length; i++) {
                if (nextAreas[i].start !== areas[i].start || nextAreas[i].end !== areas[i].end) {
                    mutated = true;
                    break;
                }
            }

            if (mutated) {
                dispatch(actions.regionUpdate(region.id, { areas: nextAreas }));
            }
        };
    }

    function splitSelectedRegionIntent() {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') return;
            const state = getState();
            const regionsState = regionSelectors.selectRegionsState
                ? regionSelectors.selectRegionsState(state)
                : state?.regions;
            const selectedId = regionsState?.selectedId;
            if (!Number.isFinite(selectedId)) {
                return;
            }

            const region = regionsState.byId[selectedId];
            if (!region) {
                return;
            }

            const areas = getRegionAreas(region);
            if (areas.length <= 1) {
                return;
            }

            const newRegions = areas.map(area => ({
                positionId: region.positionId,
                areas: [{ start: area.start, end: area.end }],
                note: region.note,
                color: region.color
            }));

            dispatch(actions.regionRemove(region.id));
            if (regionsState?.addAreaTargetId === region.id && actions.regionSetAddAreaMode) {
                dispatch(actions.regionSetAddAreaMode(null));
            }
            dispatch(actions.regionsAdded(newRegions));
        };
    }

    app.features = app.features || {};
    app.features.regions = app.features.regions || {};
    app.features.regions.thunks = {
        selectRegionIntent,
        enterComparisonModeIntent,
        exitComparisonModeIntent,
        updateIncludedPositionsIntent,
        updateComparisonSliceIntent,
        createRegionsFromComparisonIntent,
        createRegionIntent,
        createAutoRegionsIntent,
        mergeRegionIntoSelectedIntent,
        resizeSelectedRegionIntent,
        splitSelectedRegionIntent,
        toggleRegionCreationIntent
    };
})(window.NoiseSurveyApp);




