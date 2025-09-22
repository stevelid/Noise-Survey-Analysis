// noise_survey_analysis/static/js/features/regions/regionReducer.js

/**
 * @fileoverview Reducer for region entities supporting multi-area regions.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const DEFAULT_REGION_COLOR = '#1e88e5';

    const initialRegionsState = {
        byId: {},
        allIds: [],
        selectedId: null,
        counter: 1,
        addAreaTargetId: null,
        isMergeModeActive: false,
        panelVisible: true,
        overlaysVisible: true
    };

    function normalizeColor(color, fallback = DEFAULT_REGION_COLOR) {
        if (typeof color === 'string') {
            const trimmed = color.trim();
            if (trimmed) {
                return trimmed;
            }
        }
        return fallback;
    }

    function normalizeRegionBounds(start, end) {
        if (!Number.isFinite(start) || !Number.isFinite(end)) {
            return null;
        }
        if (start === end) {
            return null;
        }
        const normalizedStart = Math.min(start, end);
        const normalizedEnd = Math.max(start, end);
        return { start: normalizedStart, end: normalizedEnd };
    }

    function normalizeArea(areaOrStart, maybeEnd) {
        if (areaOrStart == null) {
            return null;
        }
        if (typeof areaOrStart === 'object') {
            return normalizeRegionBounds(areaOrStart.start, areaOrStart.end);
        }
        return normalizeRegionBounds(areaOrStart, maybeEnd);
    }

    function cloneAreas(areas) {
        if (!Array.isArray(areas)) {
            return [];
        }
        return areas.map(area => ({ start: area.start, end: area.end }));
    }

    function normalizeAreaList(list) {
        const normalized = [];
        if (Array.isArray(list)) {
            list.forEach(item => {
                const area = normalizeArea(item);
                if (area) {
                    normalized.push(area);
                }
            });
        }
        if (!normalized.length) {
            return [];
        }
        normalized.sort((a, b) => {
            if (a.start === b.start) {
                return a.end - b.end;
            }
            return a.start - b.start;
        });
        const merged = [Object.assign({}, normalized[0])];
        for (let i = 1; i < normalized.length; i++) {
            const current = normalized[i];
            const last = merged[merged.length - 1];
            if (current.start <= last.end) {
                if (current.end > last.end) {
                    last.end = current.end;
                }
            } else {
                merged.push(Object.assign({}, current));
            }
        }
        return merged;
    }

    function summarizeAreas(areas) {
        if (!Array.isArray(areas) || !areas.length) {
            return { start: null, end: null };
        }
        return {
            start: areas[0].start,
            end: areas[areas.length - 1].end
        };
    }

    function ensureRegionAreas(region) {
        if (Array.isArray(region.areas) && region.areas.length) {
            const normalized = normalizeAreaList(region.areas);
            if (normalized.length) {
                return normalized;
            }
        }
        const fallback = normalizeRegionBounds(region.start, region.end);
        return fallback ? [fallback] : [];
    }

    function addSingleRegion(state, payload) {
        const { positionId, start, end } = payload || {};
        if (!positionId) {
            return state;
        }
        const area = normalizeRegionBounds(start, end);
        if (!area) {
            return state;
        }
        const id = state.counter;
        const areas = [area];
        const summary = summarizeAreas(areas);
        const newRegion = {
            id,
            positionId,
            areas,
            start: summary.start,
            end: summary.end,
            note: '',
            metrics: null,
            color: DEFAULT_REGION_COLOR
        };
        return {
            ...state,
            byId: { ...state.byId, [id]: newRegion },
            allIds: [...state.allIds, id],
            selectedId: id,
            counter: id + 1
        };
    }

    function updateRegion(state, id, changes) {
        const existing = state.byId[id];
        if (!existing) {
            return state;
        }

        const baseAreas = ensureRegionAreas(existing);
        let nextAreas = cloneAreas(baseAreas);
        let areasMutated = false;

        const sanitizedChanges = { ...changes };

        if (Object.prototype.hasOwnProperty.call(changes, 'areas')) {
            const normalized = normalizeAreaList(changes.areas);
            if (!normalized.length) {
                return state;
            }
            nextAreas = normalized;
            areasMutated = true;
        }

        if (Object.prototype.hasOwnProperty.call(changes, 'start')) {
            const newStart = Number(changes.start);
            if (!Number.isFinite(newStart)) {
                return state;
            }
            const first = nextAreas[0];
            if (!first || newStart >= first.end) {
                return state;
            }
            nextAreas = normalizeAreaList([{ start: newStart, end: first.end }, ...nextAreas.slice(1)]);
            areasMutated = true;
        }

        if (Object.prototype.hasOwnProperty.call(changes, 'end')) {
            const newEnd = Number(changes.end);
            if (!Number.isFinite(newEnd)) {
                return state;
            }
            const lastIndex = nextAreas.length - 1;
            const last = nextAreas[lastIndex];
            if (!last || newEnd <= last.start) {
                return state;
            }
            nextAreas = normalizeAreaList([...nextAreas.slice(0, lastIndex), { start: last.start, end: newEnd }]);
            areasMutated = true;
        }

        if (Object.prototype.hasOwnProperty.call(changes, 'color')) {
            sanitizedChanges.color = normalizeColor(changes.color, existing.color || DEFAULT_REGION_COLOR);
        }

        const summary = summarizeAreas(nextAreas);
        const updated = {
            ...existing,
            ...sanitizedChanges,
            areas: nextAreas,
            start: summary.start,
            end: summary.end
        };

        if (areasMutated) {
            updated.metrics = null;
        } else if (Object.prototype.hasOwnProperty.call(sanitizedChanges, 'metrics')) {
            updated.metrics = sanitizedChanges.metrics || null;
        }

        if (Object.prototype.hasOwnProperty.call(sanitizedChanges, 'note')) {
            updated.note = typeof sanitizedChanges.note === 'string' ? sanitizedChanges.note : '';
        }

        if (!updated.color) {
            updated.color = DEFAULT_REGION_COLOR;
        }

        return {
            ...state,
            byId: { ...state.byId, [id]: updated }
        };
    }

    function removeRegion(state, id) {
        if (!Number.isFinite(id) || !state.byId[id]) {
            return state;
        }
        const newById = { ...state.byId };
        delete newById[id];
        const newAllIds = state.allIds.filter(regionId => regionId !== id);
        const newSelectedId = state.selectedId === id ? null : state.selectedId;
        const newAddAreaTargetId = state.addAreaTargetId === id ? null : state.addAreaTargetId;
        const shouldKeepMergeMode = state.isMergeModeActive
            && newAllIds.length > 1
            && Number.isFinite(newSelectedId)
            && !!newById[newSelectedId];
        return {
            ...state,
            byId: newById,
            allIds: newAllIds,
            selectedId: newSelectedId,
            addAreaTargetId: newAddAreaTargetId,
            isMergeModeActive: shouldKeepMergeMode
        };
    }

    function addMultipleRegions(state, regions) {
        if (!Array.isArray(regions) || !regions.length) {
            return state;
        }
        const newById = { ...state.byId };
        const newAllIds = [...state.allIds];
        let nextCounter = state.counter;
        let selectedId = state.selectedId;

        regions.forEach(region => {
            if (!region) return;
            const positionId = region.positionId;
            if (!positionId) return;
            const areas = normalizeAreaList(region.areas && region.areas.length ? region.areas : [region]);
            if (!areas.length) return;

            let candidateId = Number.isFinite(region.id) ? region.id : null;
            if (candidateId === null || Object.prototype.hasOwnProperty.call(newById, candidateId)) {
                candidateId = nextCounter;
                while (Object.prototype.hasOwnProperty.call(newById, candidateId)) {
                    candidateId += 1;
                }
            }
            nextCounter = Math.max(nextCounter, candidateId + 1);

            const summary = summarizeAreas(areas);
            newById[candidateId] = {
                id: candidateId,
                positionId,
                areas,
                start: summary.start,
                end: summary.end,
                note: typeof region.note === 'string' ? region.note : '',
                metrics: region.metrics || null,
                color: normalizeColor(region.color)
            };
            newAllIds.push(candidateId);
            selectedId = candidateId;
        });

        return {
            ...state,
            byId: newById,
            allIds: newAllIds,
            selectedId,
            counter: Math.max(nextCounter, state.counter)
        };
    }

    function replaceRegions(state, incoming) {
        if (!Array.isArray(incoming)) {
            return {
                byId: {},
                allIds: [],
                selectedId: null,
                counter: 1,
                addAreaTargetId: null,
                isMergeModeActive: false,
                panelVisible: state.panelVisible,
                overlaysVisible: state.overlaysVisible
            };
        }

        const byId = {};
        const allIds = [];
        let maxId = 0;

        incoming.forEach(region => {
            if (!region) return;
            const positionId = region.positionId;
            if (!positionId) return;
            const areas = normalizeAreaList(region.areas && region.areas.length ? region.areas : [region]);
            if (!areas.length) return;
            let candidateId = Number.isFinite(region.id) ? region.id : undefined;
            if (candidateId === undefined || Object.prototype.hasOwnProperty.call(byId, candidateId)) {
                candidateId = ++maxId;
                while (Object.prototype.hasOwnProperty.call(byId, candidateId)) {
                    candidateId = ++maxId;
                }
            }
            maxId = Math.max(maxId, candidateId);
            const summary = summarizeAreas(areas);
            byId[candidateId] = {
                id: candidateId,
                positionId,
                areas,
                start: summary.start,
                end: summary.end,
                note: typeof region.note === 'string' ? region.note : '',
                metrics: region.metrics || null,
                color: normalizeColor(region.color)
            };
            allIds.push(candidateId);
        });

        const selectedId = byId[state.selectedId] ? state.selectedId : (allIds[0] ?? null);

        return {
            byId,
            allIds,
            selectedId,
            counter: Math.max(maxId + 1, state.counter, 1),
            addAreaTargetId: null,
            isMergeModeActive: false,
            panelVisible: state.panelVisible,
            overlaysVisible: state.overlaysVisible
        };
    }

    function regionsReducer(state = initialRegionsState, action) {
        switch (action.type) {
            case actionTypes.REGION_ADDED:
                return addSingleRegion(state, action.payload);

            case actionTypes.REGIONS_ADDED:
                return addMultipleRegions(state, action.payload?.regions);

            case actionTypes.REGION_UPDATED: {
                const { id, changes } = action.payload || {};
                if (!Number.isFinite(id) || !changes) {
                    return state;
                }
                return updateRegion(state, id, changes);
            }

            case actionTypes.REGION_REMOVED:
                return removeRegion(state, action.payload?.id);

            case actionTypes.REGION_SELECTED: {
                const { id } = action.payload || {};
                const nextSelected = Number.isFinite(id) && state.byId[id] ? id : null;
                if (state.selectedId === nextSelected) {
                    return state;
                }
                const shouldKeepMergeMode = nextSelected !== null
                    && state.isMergeModeActive
                    && state.allIds.length > 1;
                return {
                    ...state,
                    selectedId: nextSelected,
                    isMergeModeActive: shouldKeepMergeMode
                };
            }

            case actionTypes.REGION_SELECTION_CLEARED:
                if (state.selectedId === null) {
                    return state;
                }
                return {
                    ...state,
                    selectedId: null,
                    isMergeModeActive: false
                };

            case actionTypes.REGION_NOTE_SET: {
                const { id, note } = action.payload || {};
                if (!Number.isFinite(id)) {
                    return state;
                }
                return updateRegion(state, id, { note });
            }

            case actionTypes.REGION_METRICS_SET: {
                const { id, metrics } = action.payload || {};
                if (!Number.isFinite(id)) {
                    return state;
                }
                return updateRegion(state, id, { metrics });
            }

            case actionTypes.REGION_COLOR_SET: {
                const { id, color } = action.payload || {};
                if (!Number.isFinite(id)) {
                    return state;
                }
                return updateRegion(state, id, { color });
            }

            case actionTypes.REGION_VISIBILITY_SET: {
                const rawPanelVisible = action.payload?.showPanel;
                const rawOverlaysVisible = action.payload?.showOverlays;
                const nextPanelVisible = typeof rawPanelVisible === 'boolean'
                    ? rawPanelVisible
                    : state.panelVisible;
                const nextOverlaysVisible = typeof rawOverlaysVisible === 'boolean'
                    ? rawOverlaysVisible
                    : state.overlaysVisible;
                if (nextPanelVisible === state.panelVisible && nextOverlaysVisible === state.overlaysVisible) {
                    return state;
                }
                return {
                    ...state,
                    panelVisible: nextPanelVisible,
                    overlaysVisible: nextOverlaysVisible
                };
            }

            case actionTypes.REGIONS_REPLACED:
                return replaceRegions(state, action.payload?.regions);

            case actionTypes.REGION_ADD_AREA_MODE_SET: {
                const { regionId } = action.payload || {};
                const normalizedId = Number.isFinite(regionId) && state.byId[regionId] ? regionId : null;
                if (state.addAreaTargetId === normalizedId) {
                    return state;
                }
                return {
                    ...state,
                    addAreaTargetId: normalizedId
                };
            }

            case actionTypes.REGION_MERGE_MODE_SET: {
                const { isActive } = action.payload || {};
                const requested = Boolean(isActive);
                const canActivate = requested
                    && state.allIds.length > 1
                    && Number.isFinite(state.selectedId)
                    && !!state.byId[state.selectedId];
                const nextValue = requested && canActivate;
                if (state.isMergeModeActive === nextValue) {
                    return state;
                }
                return {
                    ...state,
                    isMergeModeActive: nextValue
                };
            }

            default:
                return state;
        }
    }

    app.features = app.features || {};
    app.features.regions = app.features.regions || {};
    app.features.regions.initialState = initialRegionsState;
    app.features.regions.regionsReducer = regionsReducer;
    app.features.regions.normalizeRegionBounds = normalizeRegionBounds;
})(window.NoiseSurveyApp);