// noise_survey_analysis/static/js/features/classifications/classificationReducer.js

/**
 * @fileoverview Reducer for imported audio-classification interval annotations.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const DEFAULT_CLASSIFICATION_COLORS = [
        '#e4572e',
        '#2e86ab',
        '#7a5c99',
        '#3f7d20',
        '#c47f00',
        '#c2185b',
        '#00897b',
        '#5e6ad2',
    ];

    const initialClassificationsState = {
        byId: {},
        allIds: [],
        selectedId: null,
        counter: 1,
        panelVisible: true,
        overlaysVisible: true,
        filters: {
            minimumScore: 0.0,
            enabledSourceIds: null, // null means all available sources enabled
            showDirect: true,
            showSupporting: false,
            sourceFilterExpanded: false
        }
    };

    function stableColorForSource(sourceId) {
        const key = typeof sourceId === 'string' && sourceId.trim() ? sourceId.trim() : 'source';
        let hash = 0;
        for (let i = 0; i < key.length; i += 1) {
            hash = ((hash << 5) - hash) + key.charCodeAt(i);
            hash |= 0;
        }
        const index = Math.abs(hash) % DEFAULT_CLASSIFICATION_COLORS.length;
        return DEFAULT_CLASSIFICATION_COLORS[index];
    }

    function normalizeText(value, fallback = '') {
        if (value === null || value === undefined) {
            return fallback;
        }
        const text = String(value).trim();
        return text || fallback;
    }

    function normalizeStateValue(value) {
        const text = normalizeText(value, 'on').toLowerCase();
        if (text === 'off' || text === 'inactive') return 'off';
        if (text === 'uncertain' || text === 'maybe' || text === 'unknown') return 'uncertain';
        return 'on';
    }

    function normalizeConfidence(value) {
        if (value === null || value === undefined || value === '') {
            return null;
        }
        const numeric = Number(value);
        if (!Number.isFinite(numeric)) {
            return null;
        }
        if (numeric > 1 && numeric <= 100) {
            return Math.max(0, Math.min(1, numeric / 100));
        }
        return Math.max(0, Math.min(1, numeric));
    }

    function normalizeInterval(start, end) {
        const startMs = Number(start);
        const endMs = Number(end);
        if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || startMs === endMs) {
            return null;
        }
        return {
            start: Math.min(startMs, endMs),
            end: Math.max(startMs, endMs)
        };
    }

    function normalizeClassification(entry, fallbackId) {
        if (!entry || typeof entry !== 'object') {
            return null;
        }
        const positionId = normalizeText(entry.positionId ?? entry.position_id ?? entry.position);
        if (!positionId) {
            return null;
        }
        const interval = normalizeInterval(entry.start ?? entry.startMs ?? entry.start_ms, entry.end ?? entry.endMs ?? entry.end_ms);
        if (!interval) {
            return null;
        }

        const sourceId = normalizeText(entry.sourceId ?? entry.source_id ?? entry.source, 'source');
        const sourceLabel = normalizeText(entry.sourceLabel ?? entry.source_label ?? entry.label, sourceId);
        const idCandidate = Number(entry.id);
        const id = Number.isFinite(idCandidate) && idCandidate > 0 ? idCandidate : fallbackId;
        const color = normalizeText(entry.color, stableColorForSource(sourceId));

        let role = normalizeText(entry.role).toLowerCase();
        if (role !== 'direct' && role !== 'supporting') {
            const descLower = normalizeText(entry.description ?? entry.note).toLowerCase();
            const sourceLower = sourceId.toLowerCase();
            if (descLower.includes('supporting') || sourceLower.includes('supporting') || sourceLower.startsWith('sup_')) {
                role = 'supporting';
            } else {
                role = 'direct';
            }
        }

        return {
            id,
            positionId,
            sourceId,
            sourceLabel,
            start: interval.start,
            end: interval.end,
            state: normalizeStateValue(entry.state),
            confidence: normalizeConfidence(entry.confidence),
            description: normalizeText(entry.description ?? entry.note),
            audioFile: normalizeText(entry.audioFile ?? entry.audio_file ?? entry.file),
            color,
            role,
            elevatedRegionId: Number.isFinite(Number(entry.elevatedRegionId))
                ? Number(entry.elevatedRegionId)
                : null
        };
    }

    function addClassifications(state, incoming, replace = false) {
        const byId = replace ? {} : { ...state.byId };
        const allIds = replace ? [] : [...state.allIds];
        let nextCounter = replace ? 1 : state.counter;
        let selectedId = replace ? null : state.selectedId;

        if (!Array.isArray(incoming)) {
            return replace
                ? { ...initialClassificationsState, panelVisible: state.panelVisible, overlaysVisible: state.overlaysVisible, filters: { ...state.filters } }
                : state;
        }

        incoming.forEach(entry => {
            let candidateId = Number.isFinite(Number(entry?.id)) && Number(entry.id) > 0 ? Number(entry.id) : nextCounter;
            while (Object.prototype.hasOwnProperty.call(byId, candidateId)) {
                candidateId += 1;
            }
            const classification = normalizeClassification(entry, candidateId);
            if (!classification) {
                return;
            }
            classification.id = candidateId;
            byId[candidateId] = classification;
            allIds.push(candidateId);
            nextCounter = Math.max(nextCounter, candidateId + 1);
            selectedId = candidateId;
        });

        return {
            ...state,
            byId,
            allIds,
            selectedId,
            counter: Math.max(nextCounter, 1)
        };
    }

    function updateClassification(state, id, changes) {
        if (!Number.isFinite(id) || !state.byId[id] || !changes || typeof changes !== 'object') {
            return state;
        }
        const existing = state.byId[id];
        const next = {
            ...existing,
            ...changes
        };
        const normalized = normalizeClassification(next, id);
        if (!normalized) {
            return state;
        }
        normalized.id = id;
        return {
            ...state,
            byId: {
                ...state.byId,
                [id]: normalized
            }
        };
    }

    function removeClassification(state, id) {
        if (!Number.isFinite(id) || !state.byId[id]) {
            return state;
        }
        const byId = { ...state.byId };
        delete byId[id];
        const allIds = state.allIds.filter(existingId => existingId !== id);
        return {
            ...state,
            byId,
            allIds,
            selectedId: state.selectedId === id ? null : state.selectedId
        };
    }

    function classificationsReducer(state = initialClassificationsState, action) {
        const currentFilters = state.filters || initialClassificationsState.filters;

        switch (action.type) {
            case actionTypes.CLASSIFICATIONS_ADDED:
                return addClassifications(state, action.payload?.classifications, false);

            case actionTypes.CLASSIFICATIONS_REPLACED:
                return addClassifications(state, action.payload?.classifications, true);

            case actionTypes.CLASSIFICATION_UPDATED:
                return updateClassification(state, Number(action.payload?.id), action.payload?.changes);

            case actionTypes.CLASSIFICATION_REMOVED:
                return removeClassification(state, Number(action.payload?.id));

            case actionTypes.CLASSIFICATION_SELECTED: {
                const id = Number(action.payload?.id);
                const selectedId = Number.isFinite(id) && state.byId[id] ? id : null;
                if (state.selectedId === selectedId) {
                    return state;
                }
                return { ...state, selectedId };
            }

            case actionTypes.CLASSIFICATION_SELECTION_CLEARED:
                return state.selectedId === null ? state : { ...state, selectedId: null };

            case actionTypes.CLASSIFICATION_VISIBILITY_SET: {
                const rawPanelVisible = action.payload?.showPanel;
                const rawOverlaysVisible = action.payload?.showOverlays;
                const panelVisible = typeof rawPanelVisible === 'boolean' ? rawPanelVisible : state.panelVisible;
                const overlaysVisible = typeof rawOverlaysVisible === 'boolean' ? rawOverlaysVisible : state.overlaysVisible;
                if (panelVisible === state.panelVisible && overlaysVisible === state.overlaysVisible) {
                    return state;
                }
                return { ...state, panelVisible, overlaysVisible };
            }

            case actionTypes.CLASSIFICATION_MINIMUM_SCORE_SET: {
                const minimumScore = Number.isFinite(action.payload?.minimumScore)
                    ? Math.max(0, Math.min(1, action.payload.minimumScore))
                    : 0.0;
                if (currentFilters.minimumScore === minimumScore) return state;
                return {
                    ...state,
                    filters: { ...currentFilters, minimumScore }
                };
            }

            case actionTypes.CLASSIFICATION_SOURCE_VISIBILITY_SET: {
                const { sourceId, visible } = action.payload || {};
                if (!sourceId) return state;

                // Collect all known sources if enabledSourceIds is currently null
                let enabledSourceIds = currentFilters.enabledSourceIds;
                if (!Array.isArray(enabledSourceIds)) {
                    enabledSourceIds = Array.from(new Set(state.allIds.map(id => state.byId[id]?.sourceId).filter(Boolean)));
                }

                if (visible) {
                    if (!enabledSourceIds.includes(sourceId)) {
                        enabledSourceIds = [...enabledSourceIds, sourceId];
                    }
                } else {
                    enabledSourceIds = enabledSourceIds.filter(id => id !== sourceId);
                }

                return {
                    ...state,
                    filters: { ...currentFilters, enabledSourceIds }
                };
            }

            case actionTypes.CLASSIFICATION_ALL_SOURCES_VISIBILITY_SET: {
                const visible = action.payload?.visible;
                const enabledSourceIds = visible ? null : [];
                return {
                    ...state,
                    filters: { ...currentFilters, enabledSourceIds }
                };
            }

            case actionTypes.CLASSIFICATION_ROLE_VISIBILITY_SET: {
                const showDirect = typeof action.payload?.showDirect === 'boolean' ? action.payload.showDirect : currentFilters.showDirect;
                const showSupporting = typeof action.payload?.showSupporting === 'boolean' ? action.payload.showSupporting : currentFilters.showSupporting;
                if (showDirect === currentFilters.showDirect && showSupporting === currentFilters.showSupporting) return state;
                return {
                    ...state,
                    filters: { ...currentFilters, showDirect, showSupporting }
                };
            }

            case actionTypes.CLASSIFICATION_SOURCE_FILTER_EXPANDED_SET: {
                const sourceFilterExpanded = Boolean(action.payload?.expanded);
                if (sourceFilterExpanded === Boolean(currentFilters.sourceFilterExpanded)) return state;
                return {
                    ...state,
                    filters: { ...currentFilters, sourceFilterExpanded }
                };
            }

            default:
                return state;
        }
    }

    app.features = app.features || {};
    app.features.classifications = app.features.classifications || {};
    app.features.classifications.initialState = initialClassificationsState;
    app.features.classifications.classificationsReducer = classificationsReducer;
    app.features.classifications.normalizeClassification = normalizeClassification;
    app.features.classifications.stableColorForSource = stableColorForSource;
})(window.NoiseSurveyApp);
