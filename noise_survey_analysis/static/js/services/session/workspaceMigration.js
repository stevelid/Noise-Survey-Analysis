/** Explicit workspace upgrades. Never merge an unknown file version into live state. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const WORKSPACE_VERSION = 2;
    const clone = value => JSON.parse(JSON.stringify(value));

    function regionList(slice) {
        if (Array.isArray(slice)) return slice;
        const ids = Array.isArray(slice?.allIds) ? slice.allIds : Object.keys(slice?.byId || {});
        return ids.map(id => slice.byId?.[id]).filter(Boolean);
    }

    function positionIds(payload) {
        const state = payload?.appState || {};
        const positions = new Set(state.view?.availablePositions || []);
        (payload?.sourceConfigs || []).forEach(source => {
            const id = source.position_name || source.position || source.positionId;
            if (id) positions.add(id);
        });
        regionList(state.regions).forEach(region => {
            if (region.positionId) positions.add(region.positionId);
            Object.keys(region.meterStates || {}).forEach(id => positions.add(id));
        });
        return [...positions];
    }

    function normalizeRegions(slice, positions, consolidate = false) {
        const model = app.annotationModel;
        if (!model) throw new Error('Annotation model is not loaded.');
        const incoming = regionList(slice);
        const result = consolidate
            ? model.consolidateLegacyRegions(incoming, positions)
            : { regions: incoming, mergedCount: 0 };
        const byId = {};
        const allIds = [];
        let counter = 1;
        result.regions.forEach(raw => {
            const normalized = model.normalizeRegion(raw, positions);
            if (!normalized) return;
            let id = Number(raw.id);
            if (!Number.isFinite(id) || id < 1 || byId[id]) id = counter;
            while (byId[id]) id += 1;
            byId[id] = { ...normalized, id };
            allIds.push(id);
            counter = Math.max(counter, id + 1);
        });
        const selectedId = byId[slice?.selectedId] ? Number(slice.selectedId) : (allIds[0] ?? null);
        return {
            regions: {
                ...(Array.isArray(slice) ? {} : slice), byId, allIds, counter,
                selectedId, addAreaTargetId: null, isMergeModeActive: false,
                categories: model.normalizeCatalog(slice?.categories),
                ghostMode: ['off', 'selected', 'all'].includes(slice?.ghostMode) ? slice.ghostMode : 'selected',
            },
            mergedCount: result.mergedCount,
        };
    }

    function migrateWorkspace(payload) {
        if (!payload || typeof payload !== 'object' || !payload.appState || typeof payload.appState !== 'object') {
            throw new Error('Workspace must contain an appState object.');
        }
        const version = payload.version === undefined ? 1 : Number(payload.version);
        if (version !== 1 && version !== WORKSPACE_VERSION) {
            throw new Error(`Unsupported workspace version: ${payload.version}`);
        }
        const migrated = clone(payload);
        const normalized = normalizeRegions(migrated.appState.regions, positionIds(migrated), version === 1);
        migrated.version = WORKSPACE_VERSION;
        migrated.appState.regions = normalized.regions;
        return { payload: migrated, mergedCount: normalized.mergedCount };
    }

    app.workspaceMigration = { WORKSPACE_VERSION, migrateWorkspace, normalizeRegions, positionIds };
})(window.NoiseSurveyApp);
