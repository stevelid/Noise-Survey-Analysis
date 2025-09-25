// noise_survey_analysis/static/js/features/markers/markersReducer.js

/**
 * @fileoverview Reducer responsible for marker entity state management.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const DEFAULT_MARKER_COLOR = '#fdd835';

    const initialMarkersState = {
        byId: {},
        allIds: [],
        selectedId: null,
        counter: 1,
        enabled: true
    };

    function normalizeColor(color, fallback = DEFAULT_MARKER_COLOR) {
        if (typeof color === 'string') {
            const trimmed = color.trim();
            if (trimmed) {
                return trimmed;
            }
        }
        return fallback;
    }

    function normalizeNote(note) {
        return typeof note === 'string' ? note : '';
    }

    function cloneMetrics(metrics) {
        if (!metrics || typeof metrics !== 'object') {
            return null;
        }
        try {
            return JSON.parse(JSON.stringify(metrics));
        } catch (error) {
            console.error('[Markers] Failed to clone marker metrics payload:', error);
            return null;
        }
    }

    function sortIdsByTimestamp(byId, ids) {
        return ids.slice().sort((a, b) => {
            const markerA = byId[a];
            const markerB = byId[b];
            const aTimestamp = Number(markerA?.timestamp);
            const bTimestamp = Number(markerB?.timestamp);
            if (aTimestamp === bTimestamp) {
                return (markerA?.id || 0) - (markerB?.id || 0);
            }
            return aTimestamp - bTimestamp;
        });
    }

    function hasDuplicateTimestamp(state, timestamp, excludeId) {
        return state.allIds.some(id => {
            if (id === excludeId) {
                return false;
            }
            const marker = state.byId[id];
            return Number(marker?.timestamp) === timestamp;
        });
    }

    function normalizePositionId(positionId) {
        if (typeof positionId === 'string') {
            const trimmed = positionId.trim();
            if (trimmed) {
                return trimmed;
            }
        }
        return null;
    }

    function addMarker(state, payload) {
        const timestamp = Number(payload?.timestamp);
        if (!Number.isFinite(timestamp)) {
            return state;
        }
        if (hasDuplicateTimestamp(state, timestamp)) {
            return state;
        }

        const id = state.counter;
        const marker = {
            id,
            timestamp,
            note: normalizeNote(payload?.note),
            color: normalizeColor(payload?.color),
            metrics: cloneMetrics(payload?.metrics),
            positionId: normalizePositionId(payload?.positionId)
        };

        const nextById = { ...state.byId, [id]: marker };
        const nextAllIds = sortIdsByTimestamp(nextById, [...state.allIds, id]);

        return {
            ...state,
            byId: nextById,
            allIds: nextAllIds,
            selectedId: id,
            counter: id + 1
        };
    }

    function removeMarker(state, id) {
        const markerId = Number(id);
        if (!Number.isFinite(markerId) || !state.byId[markerId]) {
            return state;
        }

        const nextById = { ...state.byId };
        delete nextById[markerId];

        const nextAllIds = state.allIds.filter(existingId => existingId !== markerId);
        const nextSelectedId = state.selectedId === markerId ? null : state.selectedId;

        return {
            ...state,
            byId: nextById,
            allIds: nextAllIds,
            selectedId: nextSelectedId
        };
    }

    function updateMarker(state, id, changes) {
        const markerId = Number(id);
        if (!Number.isFinite(markerId)) {
            return state;
        }
        const existing = state.byId[markerId];
        if (!existing) {
            return state;
        }
        const updates = changes && typeof changes === 'object' ? { ...changes } : {};
        const nextMarker = { ...existing };
        let mutated = false;
        let timestampChanged = false;

        if (Object.prototype.hasOwnProperty.call(updates, 'timestamp')) {
            const timestamp = Number(updates.timestamp);
            if (!Number.isFinite(timestamp) || hasDuplicateTimestamp(state, timestamp, markerId)) {
                return state;
            }
            if (timestamp !== existing.timestamp) {
                nextMarker.timestamp = timestamp;
                mutated = true;
                timestampChanged = true;
            }
            delete updates.timestamp;
        }

        if (Object.prototype.hasOwnProperty.call(updates, 'note')) {
            const note = normalizeNote(updates.note);
            if (note !== existing.note) {
                nextMarker.note = note;
                mutated = true;
            }
            delete updates.note;
        }

        if (Object.prototype.hasOwnProperty.call(updates, 'color')) {
            const color = normalizeColor(updates.color, existing.color || DEFAULT_MARKER_COLOR);
            if (color !== existing.color) {
                nextMarker.color = color;
                mutated = true;
            }
            delete updates.color;
        }

        if (Object.prototype.hasOwnProperty.call(updates, 'positionId')) {
            const positionId = normalizePositionId(updates.positionId);
            if (positionId !== existing.positionId) {
                nextMarker.positionId = positionId;
                mutated = true;
            }
            delete updates.positionId;
        }

        if (Object.prototype.hasOwnProperty.call(updates, 'metrics')) {
            const metrics = cloneMetrics(updates.metrics);
            const existingMetrics = existing.metrics;
            const metricsChanged = JSON.stringify(metrics) !== JSON.stringify(existingMetrics);
            if (metricsChanged) {
                nextMarker.metrics = metrics;
                mutated = true;
            }
            delete updates.metrics;
        }

        const remainingKeys = Object.keys(updates);
        remainingKeys.forEach(key => {
            nextMarker[key] = updates[key];
            mutated = true;
        });

        if (!mutated) {
            return state;
        }

        const nextById = { ...state.byId, [markerId]: nextMarker };
        const nextAllIds = timestampChanged ? sortIdsByTimestamp(nextById, state.allIds) : state.allIds;

        return {
            ...state,
            byId: nextById,
            allIds: nextAllIds
        };
    }

    function selectMarker(state, id) {
        if (id === null || id === undefined) {
            if (state.selectedId === null) {
                return state;
            }
            return { ...state, selectedId: null };
        }
        const markerId = Number(id);
        if (!Number.isFinite(markerId) || !state.byId[markerId]) {
            return state;
        }
        if (state.selectedId === markerId) {
            return state;
        }
        return { ...state, selectedId: markerId };
    }

    function setMarkerNote(state, id, note) {
        return updateMarker(state, id, { note });
    }

    function setMarkerColor(state, id, color) {
        return updateMarker(state, id, { color });
    }

    function setMarkerMetrics(state, id, metrics) {
        return updateMarker(state, id, { metrics });
    }

    function replaceMarkers(state, payload) {
        const markers = Array.isArray(payload?.markers) ? payload.markers : [];
        const nextById = {};
        const nextAllIds = [];
        let nextCounter = 1;
        let nextSelectedId = null;

        markers.forEach(rawMarker => {
            const timestamp = Number(rawMarker?.timestamp);
            if (!Number.isFinite(timestamp) || hasDuplicateTimestamp({ byId: nextById, allIds: nextAllIds }, timestamp)) {
                return;
            }
            const providedId = Number(rawMarker?.id);
            const id = Number.isFinite(providedId) && providedId > 0 ? providedId : nextCounter;
            nextCounter = Math.max(nextCounter, id + 1);
            const marker = {
                id,
                timestamp,
                note: normalizeNote(rawMarker?.note),
                color: normalizeColor(rawMarker?.color),
                metrics: cloneMetrics(rawMarker?.metrics),
                positionId: normalizePositionId(rawMarker?.positionId)
            };
            nextById[id] = marker;
            nextAllIds.push(id);
        });

        const sortedIds = sortIdsByTimestamp(nextById, nextAllIds);
        const requestedSelectedId = Number(payload?.selectedId);
        if (Number.isFinite(requestedSelectedId) && nextById[requestedSelectedId]) {
            nextSelectedId = requestedSelectedId;
        }

        const nextEnabled = typeof payload?.enabled === 'boolean' ? payload.enabled : state.enabled;

        return {
            ...state,
            byId: nextById,
            allIds: sortedIds,
            selectedId: nextSelectedId,
            counter: Math.max(nextCounter, sortedIds.length ? Math.max(...sortedIds) + 1 : 1),
            enabled: nextEnabled
        };
    }

    function markersReducer(state = initialMarkersState, action) {
        switch (action.type) {
            case actionTypes.MARKER_ADDED:
                return addMarker(state, action.payload);

            case actionTypes.MARKER_REMOVED:
                return removeMarker(state, action.payload?.id);

            case actionTypes.MARKER_UPDATED:
                return updateMarker(state, action.payload?.id, action.payload?.changes);

            case actionTypes.MARKER_SELECTED:
                return selectMarker(state, action.payload?.id);

            case actionTypes.MARKER_NOTE_SET:
                return setMarkerNote(state, action.payload?.id, action.payload?.note);

            case actionTypes.MARKER_COLOR_SET:
                return setMarkerColor(state, action.payload?.id, action.payload?.color);

            case actionTypes.MARKER_METRICS_SET:
                return setMarkerMetrics(state, action.payload?.id, action.payload?.metrics);

            case actionTypes.MARKERS_REPLACED:
                return replaceMarkers(state, action.payload);

            case actionTypes.MARKERS_VISIBILITY_SET: {
                const enabledFlag = action.payload?.enabled;
                const nextEnabled = typeof enabledFlag === 'boolean'
                    ? enabledFlag
                    : Boolean(enabledFlag);
                return { ...state, enabled: nextEnabled };
            }

            default:
                return state;
        }
    }

    app.features = app.features || {};
    app.features.markers = app.features.markers || {};
    app.features.markers.initialState = initialMarkersState;
    app.features.markers.markersReducer = markersReducer;
})(window.NoiseSurveyApp);
