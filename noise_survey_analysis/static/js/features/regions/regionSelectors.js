// noise_survey_analysis/static/js/features/regions/regionSelectors.js

/**
 * @fileoverview Selectors for region data.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    function selectRegionsState(state) {
        return state?.regions || { byId: {}, allIds: [], selectedId: null, counter: 1 };
    }

    function selectRegionById(state, id) {
        return selectRegionsState(state).byId[id] || null;
    }

    function selectAllRegions(state) {
        const regionsState = selectRegionsState(state);
        return regionsState.allIds.map(id => regionsState.byId[id]).filter(Boolean);
    }

    function selectSelectedRegion(state) {
        const regionsState = selectRegionsState(state);
        return regionsState.selectedId ? regionsState.byId[regionsState.selectedId] || null : null;
    }

    function selectRegionsByPosition(state, positionId) {
        if (!positionId) {
            return [];
        }
        return selectAllRegions(state).filter(region => region.positionId === positionId);
    }

    function selectRegionByTimestamp(state, positionId, timestamp) {
        if (!Number.isFinite(timestamp) || !positionId) {
            return null;
        }
        const regionsState = selectRegionsState(state);
        const { byId, allIds } = regionsState;
        for (let i = allIds.length - 1; i >= 0; i--) {
            const region = byId[allIds[i]];
            if (!region || region.positionId !== positionId) continue;
            if (timestamp >= region.start && timestamp <= region.end) {
                return region;
            }
        }
        return null;
    }

    app.features = app.features || {};
    app.features.regions = app.features.regions || {};
    app.features.regions.selectors = {
        selectRegionsState,
        selectRegionById,
        selectAllRegions,
        selectSelectedRegion,
        selectRegionsByPosition,
        selectRegionByTimestamp
    };
})(window.NoiseSurveyApp);
