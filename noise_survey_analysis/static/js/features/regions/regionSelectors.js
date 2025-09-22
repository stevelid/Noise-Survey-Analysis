// noise_survey_analysis/static/js/features/regions/regionSelectors.js

/**
 * @fileoverview Selectors for region data.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const EMPTY_STATE = {
        byId: {},
        allIds: [],
        selectedId: null,
        counter: 1,
        addAreaTargetId: null,
        panelVisible: true,
        overlaysVisible: true
    };

    function selectRegionsState(state) {
        return state?.regions || EMPTY_STATE;
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

    function getRegionAreas(region) {
        if (!region) {
            return [];
        }
        if (Array.isArray(region.areas) && region.areas.length) {
            return region.areas;
        }
        if (Number.isFinite(region.start) && Number.isFinite(region.end)) {
            return [{ start: region.start, end: region.end }];
        }
        return [];
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
            const areas = getRegionAreas(region);
            for (let j = 0; j < areas.length; j++) {
                const area = areas[j];
                if (timestamp >= area.start && timestamp <= area.end) {
                    return region;
                }
            }
        }
        return null;
    }

    function selectAddAreaTargetId(state) {
        return selectRegionsState(state).addAreaTargetId || null;
    }

    app.features = app.features || {};
    app.features.regions = app.features.regions || {};
    app.features.regions.selectors = {
        selectRegionsState,
        selectRegionById,
        selectAllRegions,
        selectSelectedRegion,
        selectRegionsByPosition,
        selectRegionByTimestamp,
        selectAddAreaTargetId
    };
})(window.NoiseSurveyApp);
