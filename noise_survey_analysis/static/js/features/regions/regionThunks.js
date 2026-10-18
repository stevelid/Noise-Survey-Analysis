// noise_survey_analysis/static/js/features/regions/regionThunks.js

/**
 * @fileoverview Thunks handling region and comparison workflows.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const METER_PRESENT = 'present';
    const METER_ABSENT = 'absent';
    const METER_UNCHECKED = 'unchecked';

    const { actions } = app;

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

    function getAvailablePositions(state) {
        const positions = state?.view?.availablePositions;
        return Array.isArray(positions) && positions.length
            ? positions : Object.keys(app.registry?.models?.timeSeriesSources || {});
    }

    function getMeterStates(region, positions) {
        if (app.annotationModel?.normalizeMeterStates) return app.annotationModel.normalizeMeterStates(region, positions);
        const states = { ...(region.meterStates || {}) };
        positions.forEach(id => { if (!states[id]) states[id] = METER_UNCHECKED; });
        states[region.positionId] = METER_PRESENT;
        return states;
    }


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

    function isDebugEnabled() {
        try {
            return localStorage.getItem('nsa_debug') === '1';
        } catch (e) {
            return false;
        }
    }

    // Module-private cache for collectPositionTimestampStats.
    // Keyed by positionId → { overviewSource, logSource, stats }.
    // Invalidated when source object identity changes (Bokeh replaces sources on rebuild).
    const _timestampStatsCache = new Map();

    function _resetTimestampStatsCache() {
        _timestampStatsCache.clear();
    }

    /**
     * Collects timestamp statistics for a position using a single O(n) linear scan.
     * Results are cached by source object identity; repeated calls with unchanged
     * sources return the same result object without rescanning.
     */
    function collectPositionTimestampStats(positionId) {
        if (!positionId) {
            return null;
        }
        const registryModels = app.registry?.models || {};
        const sources = registryModels.timeSeriesSources?.[positionId];
        if (!sources) {
            return null;
        }

        const cached = _timestampStatsCache.get(positionId);
        if (cached &&
            cached.overviewSource === sources.overview &&
            cached.logSource === sources.log) {
            return cached.stats;
        }

        let min = Infinity;
        let max = -Infinity;
        let count = 0;

        function scanSource(source) {
            const data = source?.data;
            if (!data || !data.Datetime) {
                return;
            }
            const raw = data.Datetime;
            for (let i = 0; i < raw.length; i++) {
                const value = Number(raw[i]);
                if (Number.isFinite(value)) {
                    if (value < min) min = value;
                    if (value > max) max = value;
                    count++;
                }
            }
        }

        scanSource(sources.overview);
        scanSource(sources.log);

        const stats = count ? { min, max, count } : null;
        _timestampStatsCache.set(positionId, {
            overviewSource: sources.overview,
            logSource: sources.log,
            stats
        });
        return stats;
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

    function buildDailyIntervals(timestampStats, mode, timezone = 'Europe/London') {
        if (!timestampStats || !timestampStats.count) {
            return [];
        }

        const minTimestamp = timestampStats.min;
        const maxTimestamp = timestampStats.max;

        if (!Number.isFinite(minTimestamp) || !Number.isFinite(maxTimestamp)) {
            return [];
        }

        const formatter = new Intl.DateTimeFormat('en-GB', {
            timeZone: timezone, year: 'numeric', month: '2-digit', day: '2-digit',
            hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23'
        });
        function parts(timestamp) {
            return Object.fromEntries(formatter.formatToParts(timestamp)
                .filter(part => part.type !== 'literal').map(part => [part.type, Number(part.value)]));
        }
        function civilToUtc(day, hour) {
            const date = new Date(day);
            const desired = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), hour);
            let guess = desired;
            for (let iteration = 0; iteration < 3; iteration++) {
                const local = parts(guess);
                const represented = Date.UTC(local.year, local.month - 1, local.day, local.hour, local.minute, local.second);
                guess += desired - represented;
            }
            return guess;
        }
        const first = parts(minTimestamp);
        const last = parts(maxTimestamp);
        // Iterate civil dates, not 24-hour epoch jumps: night periods crossing
        // the spring/autumn clock change then retain their correct duration.
        const firstDay = Date.UTC(first.year, first.month - 1, first.day) - DAY_MS;
        const lastDay = Date.UTC(last.year, last.month - 1, last.day);
        const intervals = [];
        for (let day = firstDay; day <= lastDay; day += DAY_MS) {
            if (mode === 'nighttime') {
                const rawStart = civilToUtc(day, DAYTIME_END_HOUR);
                const rawEnd = civilToUtc(day + DAY_MS, DAYTIME_START_HOUR);
                const interval = clampInterval(rawStart, rawEnd, minTimestamp, maxTimestamp);
                if (interval) {
                    intervals.push(interval);
                }
            } else {
                const rawStart = civilToUtc(day, DAYTIME_START_HOUR);
                const rawEnd = civilToUtc(day, DAYTIME_END_HOUR);
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

            const available = getAvailablePositions(state);
            const included = (available.length ? available : includedPositions)
                .filter(positionId => typeof positionId === 'string' && includedPositions.includes(positionId));
            const positionId = included[0];
            const meterStates = positionId ? getMeterStates({ positionId }, available) : {};
            included.forEach(id => { meterStates[id] = METER_PRESENT; });
            const regions = positionId ? [{ positionId, start, end, meterStates }] : [];

            if (!regions.length) {
                return;
            }

            dispatch(actions.regionsAdded(regions));
            app.regions?.invalidateMetricsCache?.();
            dispatch(actions.comparisonModeExited());
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
                dispatch(actions.markerSelect(null));
            }
            if (typeof actions.setActiveSidePanelTab === 'function') {
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
                app.regions?.invalidateRegionMetrics?.(targetRegion.id);
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

            dispatch(actions.regionAdd(positionId, start, end, {
                categoryId: payload.categoryId || 'other',
                color: payload.color ?? null,
                note: payload.note || '',
                meterStates: getMeterStates({ positionId, meterStates: payload.meterStates }, getAvailablePositions(state))
            }));

            // Invalidate metrics cache for the newly created region
            app.regions?.invalidateMetricsCache?.();

            // The reducer will use `nextRegionId` and then select it.
            // We still dispatch selectRegionIntent to handle side-effects like switching panels.

            if (Number.isFinite(nextRegionId)) {

                dispatch(selectRegionIntent(nextRegionId));
            }
        };
    }

    function createAutoRegionsIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function') return;
            const state = typeof getState === 'function' ? getState() : app.store?.getState?.();
            const positions = getAvailablePositions(state);
            if (!positions.length) return;
            let min = Infinity;
            let max = -Infinity;
            positions.forEach(positionId => {
                const stats = collectPositionTimestampStats(positionId);
                if (!stats) return;
                const offset = Number(state?.view?.positionChartOffsets?.[positionId]) || 0;
                min = Math.min(min, stats.min + offset);
                max = Math.max(max, stats.max + offset);
            });
            if (!Number.isFinite(min) || !Number.isFinite(max) || min >= max) return;
            const requested = Array.isArray(payload?.modes) ? payload.modes
                : (payload?.mode ? [payload.mode] : Object.keys(AUTO_REGION_MODES));
            const modes = [...new Set(requested)].filter(mode => Object.hasOwn(AUTO_REGION_MODES, mode));
            const timezone = app.registry?.models?.config?.timezone || 'Europe/London';
            const generated = [];
            modes.forEach(mode => {
                buildDailyIntervals({ min, max, count: 1 }, mode, timezone).forEach(interval => {
                    generated.push({
                        positionId: positions[0],
                        ...interval,
                        areas: [interval],
                        meterStates: Object.fromEntries(positions.map(id => [id, METER_PRESENT])),
                        categoryId: 'other',
                        color: AUTO_REGION_MODES[mode].color,
                        note: mode === 'daytime' ? 'Daytime' : 'Nighttime'
                    });
                });
            });
            if (!generated.length) return;
            generated.sort((left, right) => left.start - right.start);
            dispatch(actions.regionsAdded(generated));
            dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_REGIONS));
            app.regions?.invalidateMetricsCache?.();
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
                //set region to be displayed in the UI
                dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_REGIONS));
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
            const regionsState = regionSelectors.selectRegionsState?.(state) || state?.regions;
            const targetId = regionsState?.selectedId;
            const sourceNumericId = Number(sourceId);
            if (!Number.isFinite(targetId) || !Number.isFinite(sourceNumericId) || targetId === sourceNumericId) return;
            const target = regionsState.byId[targetId];
            const source = regionsState.byId[sourceNumericId];
            if (!target || !source || target.positionId !== source.positionId) return;
            const positions = getAvailablePositions(state);
            const left = getMeterStates(target, positions);
            const right = getMeterStates(source, positions);
            let merged;
            if (app.annotationModel?.mergeMeterStates) merged = app.annotationModel.mergeMeterStates(left, right, positions);
            else {
                const states = {};
                const conflicts = [];
                [...new Set([...positions, ...Object.keys(left), ...Object.keys(right)])].forEach(id => {
                    const a = left[id] || METER_UNCHECKED;
                    const b = right[id] || METER_UNCHECKED;
                    states[id] = a === METER_UNCHECKED ? b : (b === METER_UNCHECKED || a === b ? a : METER_UNCHECKED);
                    if (a !== METER_UNCHECKED && b !== METER_UNCHECKED && a !== b) conflicts.push(id);
                });
                merged = { states, conflicts };
            }
            const note = [...new Set([target.note, source.note].filter(Boolean))].join('\n');
            const region = {
                ...target,
                areas: [...getRegionAreas(target), ...getRegionAreas(source)],
                meterStates: merged.states,
                note
            };
            app.regions?.invalidateRegionMetrics?.(targetId);
            app.regions?.invalidateRegionMetrics?.(sourceNumericId);
            // One semantic action makes replacing the target and removing the
            // source a single undoable transition, with no half-merged state.
            dispatch(actions.regionMerged(targetId, sourceNumericId, region));
            const names = merged.conflicts.map(id => state?.view?.positionDisplayTitles?.[id] || id);
            dispatch(actions.noticeShown(names.length
                ? `Regions merged. Re-check required: ${names.join(', ')}.` : 'Regions merged.',
            names.length ? 'warning' : 'info'));
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
                app.regions?.invalidateRegionMetrics?.(region.id);
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
                ...region,
                id: undefined,
                start: area.start,
                end: area.end,
                areas: [{ start: area.start, end: area.end }],
                meterStates: { ...getMeterStates(region, getAvailablePositions(state)) }
            }));

            app.regions?.invalidateRegionMetrics?.(region.id);
            dispatch(actions.regionSplit(region.id, newRegions));
            app.regions?.invalidateMetricsCache?.();
        };
    }

    function copySelectedRegionToPositionsIntent(requestedPositionIds = null) {
        return function (dispatch, getState) {
            if (!actions || typeof getState !== 'function') return;
            const state = getState();
            const regionsState = regionSelectors.selectRegionsState
                ? regionSelectors.selectRegionsState(state) : state?.regions;
            const selectedId = regionsState?.selectedId;
            if (!Number.isFinite(selectedId)) return;

            const sourceRegion = regionsState.byId[selectedId];
            if (!sourceRegion) return;

            const sourceAreas = getRegionAreas(sourceRegion);
            if (!sourceAreas.length) return;

            const availablePositions = Array.isArray(state?.view?.availablePositions)
                ? state.view.availablePositions : [];
            const sourcePositionKey = String(sourceRegion.positionId);
            const requestedKeys = Array.isArray(requestedPositionIds)
                ? new Set(requestedPositionIds.map(positionId => String(positionId)))
                : null;
            const targets = availablePositions.filter(positionId => {
                const positionKey = String(positionId);
                return positionKey !== sourcePositionKey
                    && (requestedKeys === null || requestedKeys.has(positionKey));
            });
            if (!targets.length) return;

            const meterStates = getMeterStates(sourceRegion, availablePositions);
            targets.forEach(positionId => { meterStates[positionId] = METER_PRESENT; });
            dispatch(actions.regionMeterStatesSet(sourceRegion.id, meterStates));
            app.regions?.invalidateMetricsCache?.();
            dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_REGIONS));
        };
    }

    /**
     * Marks the selected sound present at all other meters. The legacy
     * command name remains available until its old controls are retired.
     */
    function copyRegionToAllPositionsIntent() {
        return copySelectedRegionToPositionsIntent(null);
    }

    /** Copy the currently selected region to one validated target position. */
    function copyRegionToPositionIntent(targetPositionId) {
        return copySelectedRegionToPositionsIntent([targetPositionId]);
    }

    function setRegionMeterStateIntent(regionId, positionId, meterState) {
        return function (dispatch, getState) {
            const payload = typeof regionId === 'object' ? regionId : { id: regionId, positionId, state: meterState };
            const state = getState();
            const id = Number(payload.id ?? payload.regionId ?? state?.regions?.selectedId);
            const region = state?.regions?.byId?.[id];
            const meter = payload.positionId || payload.meterId;
            const requested = payload.state ?? payload.meterState;
            if (!region || !getAvailablePositions(state).includes(meter)
                || ![METER_PRESENT, METER_ABSENT, METER_UNCHECKED].includes(requested)) return;
            const meterStates = getMeterStates(region, getAvailablePositions(state));
            if (meter === region.positionId || meterStates[meter] === requested) return;
            meterStates[meter] = requested;
            dispatch(actions.regionMeterStatesSet(id, meterStates));
        };
    }

    function cycleRegionMeterStateIntent(regionId, positionId) {
        return function (dispatch, getState) {
            const payload = typeof regionId === 'object' ? regionId : { id: regionId, positionId };
            const state = getState();
            const id = Number(payload.id ?? payload.regionId ?? state?.regions?.selectedId);
            const region = state?.regions?.byId?.[id];
            const meter = payload.positionId || payload.meterId;
            if (!region || meter === region.positionId) return;
            const current = getMeterStates(region, getAvailablePositions(state))[meter];
            const next = current === METER_PRESENT ? METER_ABSENT : current === METER_ABSENT ? METER_UNCHECKED : METER_PRESENT;
            dispatch(setRegionMeterStateIntent(id, meter, next));
        };
    }

    function setRegionCategoryIntent(regionId, categoryId) {
        return function (dispatch, getState) {
            const payload = typeof regionId === 'object' ? regionId : { id: regionId, categoryId };
            const state = getState();
            const id = Number(payload.id ?? payload.regionId ?? state?.regions?.selectedId);
            if (!state?.regions?.byId?.[id] || !state.regions.categories?.byId?.[payload.categoryId]) return;
            dispatch(actions.regionCategorySet(id, payload.categoryId));
        };
    }

    function createCategoryIntent(payload) {
        return function (dispatch, getState) {
            const model = app.annotationModel;
            if (!model) return null;
            const label = typeof payload?.label === 'string' ? payload.label.trim() : '';
            if (!label) return null;
            const catalog = model.normalizeCatalog(getState()?.regions?.categories);
            const existing = catalog.allIds.find(id => catalog.byId[id].label.toLowerCase() === label.toLowerCase());
            if (existing) return existing;
            const stem = label.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'category';
            let id = stem;
            let suffix = 2;
            while (Object.hasOwn(catalog.byId, id) || ['__proto__', 'constructor', 'prototype'].includes(id)) id = `${stem}-${suffix++}`;
            const category = { id, label, color: model.normalizeColor(payload?.color, model.DEFAULT_REGION_COLOR) };
            dispatch(actions.regionCategoryCatalogSet({
                byId: { ...catalog.byId, [id]: category }, allIds: [...catalog.allIds, id]
            }));
            return id;
        };
    }

    function updateCategoryIntent(payload) {
        return function (dispatch, getState) {
            const model = app.annotationModel;
            if (!model) return;
            const catalog = model.normalizeCatalog(getState()?.regions?.categories);
            const existing = catalog.byId[payload?.id];
            if (!existing) return;
            const label = typeof payload.label === 'string' && payload.label.trim() ? payload.label.trim() : existing.label;
            const color = Object.hasOwn(payload, 'color') ? model.normalizeColor(payload.color, existing.color) : existing.color;
            dispatch(actions.regionCategoryCatalogSet({
                ...catalog, byId: { ...catalog.byId, [existing.id]: { ...existing, label, color } }
            }));
        };
    }

    function deleteCategoryIntent(categoryId) {
        return function (dispatch, getState) {
            const model = app.annotationModel;
            if (!model || categoryId === model.DEFAULT_CATEGORY_ID) return;
            const state = getState();
            const catalog = model.normalizeCatalog(state?.regions?.categories);
            if (!catalog.byId[categoryId]) return;
            const byId = { ...catalog.byId };
            delete byId[categoryId];
            const reassignedById = {};
            Object.values(state.regions.byId).forEach(region => {
                if (region.categoryId === categoryId) reassignedById[region.id] = model.DEFAULT_CATEGORY_ID;
            });
            // Catalog removal and reassignment share one history checkpoint.
            dispatch(actions.regionCategoryCatalogSet({ byId, allIds: catalog.allIds.filter(id => id !== categoryId) }, reassignedById));
        };
    }

    // When a region fills less than this share of the view, centring also zooms
    // in, so a short event is not left as a sliver on a multi-day overview.
    const ZOOM_TO_FIT_THRESHOLD = 0.1;
    // Zoomed-in view width as a multiple of the region span (one span of
    // context either side of the region).
    const ZOOM_TO_FIT_SPAN_FACTOR = 3;
    const MIN_VIEWPORT_WIDTH_MS = 1000;

    /**
     * Width of the view to use when centring a region.
     * - Region small relative to the view: zoom in to fit it with context.
     * - Otherwise: keep the current width, widening only if the region
     *   (plus 10% padding either side) would not fit.
     */
    function computeRegionViewportWidth(regionSpan, currentWidth) {
        const paddedRegionWidth = Math.max(MIN_VIEWPORT_WIDTH_MS, regionSpan * 1.2);
        if (currentWidth > 0 && regionSpan < currentWidth * ZOOM_TO_FIT_THRESHOLD) {
            return Math.max(MIN_VIEWPORT_WIDTH_MS, regionSpan * ZOOM_TO_FIT_SPAN_FACTOR);
        }
        return Math.max(currentWidth, paddedRegionWidth);
    }

    /** Centre the viewport on the selected region, zooming in or widening as needed. */
    function centerViewportOnSelectedRegionIntent() {
        return function (dispatch, getState) {
            if (!actions?.regionViewportCentered || typeof getState !== 'function') return;
            const state = getState();
            const regionsState = regionSelectors.selectRegionsState
                ? regionSelectors.selectRegionsState(state) : state?.regions;
            const selectedId = regionsState?.selectedId;
            const region = Number.isFinite(selectedId) ? regionsState?.byId?.[selectedId] : null;
            const areas = getRegionAreas(region);
            if (!areas.length) return;

            const regionStart = Math.min(...areas.map(area => Number(area.start)).filter(Number.isFinite));
            const regionEnd = Math.max(...areas.map(area => Number(area.end)).filter(Number.isFinite));
            if (!Number.isFinite(regionStart) || !Number.isFinite(regionEnd) || regionStart >= regionEnd) return;

            const viewportMin = Number(state?.view?.viewport?.min);
            const viewportMax = Number(state?.view?.viewport?.max);
            const currentWidth = Number.isFinite(viewportMin) && Number.isFinite(viewportMax) && viewportMax > viewportMin
                ? viewportMax - viewportMin
                : 0;
            const viewportWidth = computeRegionViewportWidth(regionEnd - regionStart, currentWidth);
            const centre = (regionStart + regionEnd) / 2;
            dispatch(actions.regionViewportCentered(centre - viewportWidth / 2, centre + viewportWidth / 2));
        };
    }

    /** Select a region from the list and centre the viewport on it. */
    function centerViewportOnRegionIntent(regionId) {
        return function (dispatch, getState) {
            const id = Number(regionId);
            if (!Number.isFinite(id) || typeof getState !== 'function') return;
            const state = getState();
            const region = regionSelectors.selectRegionById
                ? regionSelectors.selectRegionById(state, id)
                : state?.regions?.byId?.[id];
            if (!region) return;
            if (state?.regions?.selectedId !== id) {
                dispatch(actions.regionSelect(id));
            }
            dispatch(centerViewportOnSelectedRegionIntent());
        };
    }

    /**
     * Select the previous (-1) or next (+1) region in panel list order and
     * centre it. With nothing selected, ] starts at the first region and
     * [ at the last.
     */
    function stepRegionSelectionIntent(direction) {
        return function (dispatch, getState) {
            if (typeof getState !== 'function') return;
            const step = direction < 0 ? -1 : 1;
            const state = getState();
            const regions = regionSelectors.selectAllRegions
                ? regionSelectors.selectAllRegions(state) : [];
            if (!regions.length) {
                dispatch(actions.noticeShown('No regions yet. Drag on a chart to draw one.'));
                return;
            }

            const selectedId = state?.regions?.selectedId;
            const currentIndex = regions.findIndex(region => region.id === selectedId);
            let nextIndex;
            if (currentIndex < 0) {
                nextIndex = step > 0 ? 0 : regions.length - 1;
            } else {
                nextIndex = currentIndex + step;
            }
            if (nextIndex < 0 || nextIndex >= regions.length) {
                dispatch(actions.noticeShown(step > 0
                    ? 'This is the last region.'
                    : 'This is the first region.'));
                return;
            }

            dispatch(selectRegionIntent(regions[nextIndex].id));
            dispatch(centerViewportOnSelectedRegionIntent());
        };
    }

    function returnToPreviousRegionViewIntent() {
        return function (dispatch, getState) {
            const history = getState()?.view?.regionJumpHistory;
            if (!Array.isArray(history) || !history.length) {
                dispatch(actions.noticeShown('No previous view to return to.'));
                return;
            }
            if (actions?.regionViewportRestored) {
                dispatch(actions.regionViewportRestored());
            }
        };
    }

    /**
     * Open the selected region's note for editing. With nothing selected, the
     * region under the active tap line is selected first; otherwise the user
     * is told what to do.
     */
    function focusSelectedRegionNoteIntent() {
        return function (dispatch, getState) {
            let state = getState();
            if (!regionSelectors.selectSelectedRegion?.(state)) {
                const tap = state?.interaction?.tap;
                const regionUnderTap = tap?.isActive && regionSelectors.selectRegionByTimestamp
                    ? regionSelectors.selectRegionByTimestamp(state, tap.position, tap.timestamp)
                    : null;
                if (!regionUnderTap) {
                    dispatch(actions.noticeShown(
                        'Select a region first (click it, or press ] to step through regions), then press N.'
                    ));
                    return;
                }
                dispatch(selectRegionIntent(regionUnderTap.id));
                state = getState();
            }
            if (state.regions.panelVisible === false) {
                dispatch(actions.regionVisibilitySet({ showPanel: true }));
            }
            if (state.view.activeSidePanelTab !== SIDE_PANEL_TAB_REGIONS) {
                dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_REGIONS));
            }
            dispatch(actions.regionNoteFocusRequested());
        };
    }

    /** Track whether the note being typed differs from the stored note. */
    function updateRegionNoteDraftIntent(regionId, text) {
        return function (dispatch, getState) {
            const region = regionSelectors.selectRegionById?.(getState(), Number(regionId));
            if (!region) return;
            const stored = typeof region.note === 'string' ? region.note : '';
            const draft = typeof text === 'string' ? text : '';
            dispatch(actions.regionNoteStatusSet(draft === stored ? 'idle' : 'unsaved'));
        };
    }

    /**
     * Store a committed note. The note widget also reports a commit when the
     * panel loads a different region's note, so unchanged text is ignored.
     */
    function saveRegionNoteIntent(regionId, note) {
        return function (dispatch, getState) {
            const id = Number(regionId);
            const state = getState();
            const region = regionSelectors.selectRegionById?.(state, id);
            if (!region) return;
            const stored = typeof region.note === 'string' ? region.note : '';
            const next = typeof note === 'string' ? note : '';
            if (next === stored) {
                if (state?.view?.regionNoteStatus === 'unsaved') {
                    dispatch(actions.regionNoteStatusSet('idle'));
                }
                return;
            }
            dispatch(actions.regionSetNote(id, next));
            dispatch(actions.regionNoteStatusSet('saved'));
        };
    }

    /** Recalculate the selected region from the resolution currently displayed on its chart. */
    function recalculateSelectedRegionIntent() {
        return function (dispatch, getState) {
            if (typeof getState !== 'function') return;
            const state = getState();
            const regionsState = regionSelectors.selectRegionsState
                ? regionSelectors.selectRegionsState(state) : state?.regions;
            const selectedId = regionsState?.selectedId;
            const region = Number.isFinite(selectedId) ? regionsState?.byId?.[selectedId] : null;
            if (!region || !app.regions?.getRegionMetrics) return;

            const activeResolution = app.dataCache?.activeLineData?.[region.positionId]?.dataViewType;
            const resolution = activeResolution === 'log' || activeResolution === 'overview'
                ? activeResolution
                : (state?.view?.globalViewType === 'overview' ? 'overview' : 'auto');

            app.regions.invalidateRegionMetrics?.(region.id);
            app.regions.getRegionMetrics(
                region,
                state,
                app.dataCache,
                app.registry?.models,
                { resolution, force: true }
            );
            if (actions?.regionMetricsRecalculated) {
                dispatch(actions.regionMetricsRecalculated(region.id, resolution));
            }
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
        toggleRegionCreationIntent,
        copyRegionToAllPositionsIntent,
        copyRegionToPositionIntent,
        setRegionMeterStateIntent,
        cycleRegionMeterStateIntent,
        setRegionCategoryIntent,
        createCategoryIntent,
        updateCategoryIntent,
        deleteCategoryIntent,
        centerViewportOnSelectedRegionIntent,
        centerViewportOnRegionIntent,
        stepRegionSelectionIntent,
        returnToPreviousRegionViewIntent,
        focusSelectedRegionNoteIntent,
        updateRegionNoteDraftIntent,
        saveRegionNoteIntent,
        recalculateSelectedRegionIntent
    };
    app.features.regions.__test__ = app.features.regions.__test__ || {};
    app.features.regions.__test__.collectPositionTimestampStats = collectPositionTimestampStats;
    app.features.regions.__test__._resetTimestampStatsCache = _resetTimestampStatsCache;
    app.features.regions.__test__.buildDailyIntervals = buildDailyIntervals;
})(window.NoiseSurveyApp);




