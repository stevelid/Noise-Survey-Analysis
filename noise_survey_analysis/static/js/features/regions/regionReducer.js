// noise_survey_analysis/static/js/features/regions/regionReducer.js

/**
 * @fileoverview Reducer for region entities.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const initialRegionsState = {
        byId: {},
        allIds: [],
        selectedId: null,
        counter: 1
    };

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

    function addSingleRegion(state, payload) {
        const { positionId, start, end } = payload || {};
        if (!positionId) {
            return state;
        }
        const bounds = normalizeRegionBounds(start, end);
        if (!bounds) {
            return state;
        }
        const id = state.counter;
        const newRegion = {
            id,
            positionId,
            start: bounds.start,
            end: bounds.end,
            note: '',
            metrics: null
        };
        return {
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
        let updated = { ...existing, ...changes };
        if (Object.prototype.hasOwnProperty.call(changes, 'start') || Object.prototype.hasOwnProperty.call(changes, 'end')) {
            const candidateBounds = normalizeRegionBounds(
                Object.prototype.hasOwnProperty.call(changes, 'start') ? changes.start : existing.start,
                Object.prototype.hasOwnProperty.call(changes, 'end') ? changes.end : existing.end
            );
            if (!candidateBounds) {
                return state;
            }
            updated.start = candidateBounds.start;
            updated.end = candidateBounds.end;
            updated.metrics = null;
        }
        return {
            ...state,
            byId: { ...state.byId, [id]: updated }
        };
    }

    function removeRegion(state, id) {
        if (!id || !state.byId[id]) {
            return state;
        }
        const newById = { ...state.byId };
        delete newById[id];
        const newAllIds = state.allIds.filter(regionId => regionId !== id);
        const newSelectedId = state.selectedId === id ? null : state.selectedId;
        return {
            ...state,
            byId: newById,
            allIds: newAllIds,
            selectedId: newSelectedId
        };
    }

    function addMultipleRegions(state, regions) {
        if (!Array.isArray(regions) || !regions.length) {
            return state;
        }
        const newById = { ...state.byId };
        const newAllIds = [...state.allIds];
        let nextCounter = state.counter;
        let createdAny = false;
        let fallbackSelectedId = null;

        regions.forEach(region => {
            if (!region) return;
            const bounds = normalizeRegionBounds(region.start, region.end);
            if (!bounds) return;
            const positionId = region.positionId;
            if (!positionId) return;

            let candidateId = Number.isFinite(region.id) ? region.id : null;
            if (candidateId === null || Object.prototype.hasOwnProperty.call(newById, candidateId)) {
                candidateId = nextCounter;
                while (Object.prototype.hasOwnProperty.call(newById, candidateId)) {
                    candidateId += 1;
                }
            }

            nextCounter = Math.max(nextCounter, candidateId + 1);

            newById[candidateId] = {
                id: candidateId,
                positionId,
                start: bounds.start,
                end: bounds.end,
                note: typeof region.note === 'string' ? region.note : '',
                metrics: region.metrics || null
            };

            if (!newAllIds.includes(candidateId)) {
                newAllIds.push(candidateId);
            }

            if (fallbackSelectedId === null) {
                fallbackSelectedId = candidateId;
            }

            createdAny = true;
        });

        if (!createdAny) {
            return state;
        }

        const nextSelectedId = state.byId[state.selectedId]
            ? state.selectedId
            : (fallbackSelectedId !== null ? fallbackSelectedId : (newAllIds[0] ?? null));

        return {
            byId: newById,
            allIds: newAllIds,
            selectedId: nextSelectedId,
            counter: Math.max(nextCounter, 1)
        };
    }

    function replaceRegions(state, regions) {
        const incoming = Array.isArray(regions) ? regions : [];
        if (!incoming.length) {
            return {
                byId: {},
                allIds: [],
                selectedId: null,
                counter: 1
            };
        }

        const byId = {};
        const allIds = [];
        let maxId = 0;
        let nextGeneratedId = state.counter;

        incoming.forEach(region => {
            if (!region) return;
            const bounds = normalizeRegionBounds(region.start, region.end);
            if (!bounds) return;
            const positionId = region.positionId;
            if (!positionId) return;

            let candidateId = Number.isFinite(region.id) ? region.id : nextGeneratedId++;
            while (Object.prototype.hasOwnProperty.call(byId, candidateId)) {
                candidateId = nextGeneratedId++;
            }
            maxId = Math.max(maxId, candidateId);

            byId[candidateId] = {
                id: candidateId,
                positionId,
                start: bounds.start,
                end: bounds.end,
                note: typeof region.note === 'string' ? region.note : '',
                metrics: region.metrics || null
            };
            allIds.push(candidateId);
        });

        const selectedId = byId[state.selectedId] ? state.selectedId : (allIds[0] ?? null);

        return {
            byId,
            allIds,
            selectedId,
            counter: Math.max(maxId + 1, state.counter, 1)
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
                if (!id || !changes) {
                    return state;
                }
                return updateRegion(state, id, changes);
            }

            case actionTypes.REGION_REMOVED:
                return removeRegion(state, action.payload?.id);

            case actionTypes.REGION_SELECTED: {
                const { id } = action.payload || {};
                const nextSelected = id && state.byId[id] ? id : null;
                if (state.selectedId === nextSelected) {
                    return state;
                }
                return {
                    ...state,
                    selectedId: nextSelected
                };
            }

            case actionTypes.REGION_SELECTION_CLEARED:
                if (state.selectedId === null) {
                    return state;
                }
                return {
                    ...state,
                    selectedId: null
                };

            case actionTypes.REGION_NOTE_SET: {
                const { id, note } = action.payload || {};
                const region = state.byId[id];
                if (!region || region.note === note) {
                    return state;
                }
                return {
                    ...state,
                    byId: {
                        ...state.byId,
                        [id]: { ...region, note: typeof note === 'string' ? note : '' }
                    }
                };
            }

            case actionTypes.REGION_METRICS_SET: {
                const { id, metrics } = action.payload || {};
                const region = state.byId[id];
                if (!region) {
                    return state;
                }
                return {
                    ...state,
                    byId: {
                        ...state.byId,
                        [id]: { ...region, metrics: metrics || null }
                    }
                };
            }

            case actionTypes.REGIONS_REPLACED:
                return replaceRegions(state, action.payload?.regions);

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
