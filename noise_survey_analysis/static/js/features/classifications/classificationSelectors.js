// noise_survey_analysis/static/js/features/classifications/classificationSelectors.js

/**
 * @fileoverview Selectors for imported audio classifications.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const EMPTY_STATE = {
        byId: {},
        allIds: [],
        selectedId: null,
        counter: 1,
        panelVisible: true,
        overlaysVisible: true
    };

    function selectClassificationsState(state) {
        return state?.classifications || EMPTY_STATE;
    }

    function selectAllClassifications(state) {
        const classificationsState = selectClassificationsState(state);
        return classificationsState.allIds
            .map(id => classificationsState.byId[id])
            .filter(Boolean);
    }

    function selectClassificationById(state, id) {
        return selectClassificationsState(state).byId[id] || null;
    }

    function selectSelectedClassification(state) {
        const classificationsState = selectClassificationsState(state);
        const selectedId = classificationsState.selectedId;
        return Number.isFinite(selectedId) ? classificationsState.byId[selectedId] || null : null;
    }

    function selectClassificationsByPosition(state, positionId) {
        if (!positionId) {
            return [];
        }
        return selectAllClassifications(state).filter(entry => entry.positionId === positionId);
    }

    function selectAreClassificationOverlaysVisible(state) {
        return selectClassificationsState(state).overlaysVisible !== false;
    }

    const DEFAULT_FILTERS = {
        minimumScore: 0.0,
        enabledSourceIds: null,
        showDirect: true,
        showSupporting: false,
        sourceFilterExpanded: false
    };

    function selectClassificationFilters(state) {
        return selectClassificationsState(state).filters || DEFAULT_FILTERS;
    }

    function selectVisibleClassifications(state) {
        const all = selectAllClassifications(state);
        const filters = selectClassificationFilters(state);
        const minScore = Number.isFinite(filters.minimumScore) ? filters.minimumScore : 0.0;
        const enabledSources = Array.isArray(filters.enabledSourceIds) ? filters.enabledSourceIds : null;
        const showDirect = filters.showDirect !== false;
        const showSupporting = Boolean(filters.showSupporting);

        return all.filter(entry => {
            // Source ID check
            if (enabledSources !== null && !enabledSources.includes(entry.sourceId)) {
                return false;
            }

            // Role check
            const role = entry.role || 'direct';
            if (role === 'direct' && !showDirect) {
                return false;
            }
            if (role === 'supporting' && !showSupporting) {
                return false;
            }

            // Minimum score check (unscored entries with null confidence remain visible)
            if (Number.isFinite(entry.confidence) && entry.confidence < minScore) {
                return false;
            }

            return true;
        });
    }

    function selectClassificationSources(state) {
        const all = selectAllClassifications(state);
        const filters = selectClassificationFilters(state);
        const enabledSources = Array.isArray(filters.enabledSourceIds) ? filters.enabledSourceIds : null;

        const sourceMap = new Map();
        all.forEach(entry => {
            if (!entry.sourceId) return;
            if (!sourceMap.has(entry.sourceId)) {
                sourceMap.set(entry.sourceId, {
                    sourceId: entry.sourceId,
                    sourceLabel: entry.sourceLabel || entry.sourceId,
                    color: entry.color,
                    count: 0,
                    visible: enabledSources === null || enabledSources.includes(entry.sourceId)
                });
            }
            const info = sourceMap.get(entry.sourceId);
            info.count += 1;
        });

        return Array.from(sourceMap.values());
    }

    function selectClassificationCounts(state) {
        const all = selectAllClassifications(state);
        const visible = selectVisibleClassifications(state);
        let directCount = 0;
        let supportingCount = 0;

        all.forEach(entry => {
            if (entry.role === 'supporting') {
                supportingCount += 1;
            } else {
                directCount += 1;
            }
        });

        return {
            total: all.length,
            visible: visible.length,
            directCount,
            supportingCount
        };
    }

    function selectIsSelectedClassificationVisible(state) {
        const selectedId = selectClassificationsState(state).selectedId;
        if (!Number.isFinite(selectedId)) return false;
        const visible = selectVisibleClassifications(state);
        return visible.some(entry => entry.id === selectedId);
    }

    app.features = app.features || {};
    app.features.classifications = app.features.classifications || {};
    app.features.classifications.selectors = {
        selectClassificationsState,
        selectAllClassifications,
        selectClassificationById,
        selectSelectedClassification,
        selectClassificationsByPosition,
        selectAreClassificationOverlaysVisible,
        selectClassificationFilters,
        selectVisibleClassifications,
        selectClassificationSources,
        selectClassificationCounts,
        selectIsSelectedClassificationVisible
    };
})(window.NoiseSurveyApp);
