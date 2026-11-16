// noise_survey_analysis/static/js/features/regions/suggestionModel.js

/**
 * @fileoverview Agent suggestions: regions and markers an automated reviewer has proposed.
 *
 * A suggestion is an ordinary region or marker with extra optional fields:
 *   source ('user' | 'agent'), status ('proposed' | 'accepted' | 'rejected'), rationale (read-only text),
 *   confidence (0-1 or null), agent {name, runId}, createdAt, reviewedAt (ISO-8601).
 * Items without these fields are ordinary user annotations (treated as source 'user', status 'accepted').
 *
 * Every state change goes through `regionUpdate` / `markerUpdate` (or one batch replace) so Ctrl+Z works.
 * Accepting or rejecting is a deliberate review act: editing bounds, note or category never changes the status.
 */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const STATUS_PROPOSED = 'proposed';
    const STATUS_ACCEPTED = 'accepted';
    const STATUS_REJECTED = 'rejected';
    const STATUSES = Object.freeze([STATUS_PROPOSED, STATUS_ACCEPTED, STATUS_REJECTED]);
    const SOURCES = Object.freeze(['user', 'agent']);
    const MAX_RATIONALE_CHARS = 2000;
    const MAX_TEXT_CHARS = 200;
    const REVIEW_FILTERS = Object.freeze(['all', 'review', 'mine']);
    const META_KEYS = Object.freeze(['source', 'status', 'rationale', 'confidence', 'agent', 'createdAt', 'reviewedAt']);

    // ---- pure helpers ----------------------------------------------------------------------------

    const isProposed = item => item?.status === STATUS_PROPOSED;
    const isRejected = item => item?.status === STATUS_REJECTED;
    const isAgent = item => item?.source === 'agent';
    const statusOf = item => (STATUSES.includes(item?.status) ? item.status : STATUS_ACCEPTED);
    const sourceOf = item => (item?.source === 'agent' ? 'agent' : 'user');

    // Provenance validation lives in annotationModel.js so the reducers (loaded earlier) can use it too.
    const sanitizeAgent = value => app.annotationModel.sanitizeAgent(value);
    const pickMeta = value => app.annotationModel.pickReviewMeta(value);

    function formatConfidence(value) {
        return Number.isFinite(value) ? value.toFixed(2) : '';
    }

    /** "AI 0.82" for an agent item, "AI" when it has no score, '' for a user item. */
    function badgeText(item) {
        if (!isAgent(item) && !item?.status) return '';
        const score = formatConfidence(item.confidence);
        return score ? `AI ${score}` : 'AI';
    }

    function byTime(left, right) {
        return (Number(left.start ?? left.timestamp) - Number(right.start ?? right.timestamp)) || (left.id - right.id);
    }

    function filterByReview(items, filter) {
        if (filter === 'review') return items.filter(isProposed);
        if (filter === 'mine') return items.filter(item => !isAgent(item));
        return items;
    }

    // ---- selectors -------------------------------------------------------------------------------

    function allRegions(state) {
        const slice = state?.regions;
        return (slice?.allIds || []).map(id => slice.byId[id]).filter(Boolean);
    }

    function allMarkers(state) {
        const slice = state?.markers;
        return (slice?.allIds || []).map(id => slice.byId[id]).filter(Boolean);
    }

    const selectProposedRegions = state => allRegions(state).filter(isProposed).sort(byTime);
    const selectRejectedRegions = state => allRegions(state).filter(isRejected).sort(byTime);
    const selectProposedMarkers = state => allMarkers(state).filter(isProposed).sort(byTime);
    const selectRejectedMarkers = state => allMarkers(state).filter(isRejected).sort(byTime);

    function selectReviewFilter(state) {
        const value = state?.annotationPanel?.reviewFilter;
        return REVIEW_FILTERS.includes(value) ? value : 'all';
    }

    /** Counts for the filter chips (rejected items are never in the main list). */
    function selectReviewCounts(state) {
        const live = allRegions(state).filter(item => !isRejected(item));
        return {
            all: live.length,
            review: live.filter(isProposed).length,
            mine: live.filter(item => !isAgent(item)).length,
            rejected: allRegions(state).length - live.length,
            markersReview: allMarkers(state).filter(isProposed).length
        };
    }

    /**
     * The list the Regions tab shows: the panel's existing filters, then the review chip.
     * `shown` excludes rejected regions; `rejected` is the collapsed group beneath it.
     */
    function selectReviewList(state) {
        const regionSelectors = app.features.regions.selectors;
        const panelSelectors = app.features.annotationPanel?.selectors;
        const ui = panelSelectors ? panelSelectors.selectPanelState(state) : { filters: {} };
        const filtered = regionSelectors.selectFilteredRegions(state, ui.filters || {});
        const filter = selectReviewFilter(state);
        return {
            filter,
            counts: selectReviewCounts(state),
            shown: filterByReview(filtered.filter(item => !isRejected(item)), filter),
            rejected: allRegions(state).filter(isRejected).sort(byTime)
        };
    }

    /**
     * Next (direction 1) or previous (-1) proposed item after `current` in time order, wrapping.
     * Returns null when nothing is proposed.
     */
    function pickNeighbour(items, current, direction) {
        if (!items.length) return null;
        if (!current) return direction < 0 ? items[items.length - 1] : items[0];
        const index = items.findIndex(item => item.id === current.id);
        if (index >= 0) {
            if (items.length === 1) return null;
            return items[(index + direction + items.length) % items.length];
        }
        // `current` is not itself proposed (just reviewed, or a user region): the nearest in time.
        const key = Number(current.start ?? current.timestamp);
        if (direction < 0) {
            const before = items.filter(item => Number(item.start ?? item.timestamp) < key);
            return before.length ? before[before.length - 1] : items[items.length - 1];
        }
        const after = items.find(item => Number(item.start ?? item.timestamp) > key);
        return after || items[0];
    }

    // ---- thunks ----------------------------------------------------------------------------------

    const nowIso = () => new Date().toISOString();

    function invalidateMetrics() {
        app.regions?.invalidateMetricsCache?.();
    }

    /** Select a proposed region, bring it into view and open the Regions tab. */
    function focusRegion(dispatch, regionId) {
        const thunks = app.features.regions.thunks;
        dispatch(thunks.selectRegionIntent(regionId));
        dispatch(thunks.centerViewportOnSelectedRegionIntent());
    }

    function focusMarker(dispatch, markerId, timestamp) {
        dispatch(app.features.markers.thunks.selectMarkerIntent(markerId));
        const viewport = app.store?.getState?.()?.view?.viewport;
        const width = Number(viewport?.max) - Number(viewport?.min);
        if (Number.isFinite(width) && width > 0 && Number.isFinite(timestamp)) {
            const half = Math.max(width, 1000) / 2;
            dispatch(app.actions.regionViewportCentered(timestamp - half, timestamp + half));
        }
    }

    function setRegionStatus(dispatch, getState, id, status) {
        const region = getState().regions.byId[id];
        if (!region || statusOf(region) === status || (!region.status && status === STATUS_ACCEPTED)) return false;
        dispatch(app.actions.regionUpdate(id, { status, reviewedAt: nowIso() }));
        invalidateMetrics();
        return true;
    }

    function setMarkerStatus(dispatch, getState, id, status) {
        const marker = getState().markers.byId[id];
        if (!marker || statusOf(marker) === status || (!marker.status && status === STATUS_ACCEPTED)) return false;
        dispatch(app.actions.markerUpdate(id, { status, reviewedAt: nowIso() }));
        return true;
    }

    /** Move on to the next suggestion after one is reviewed (regions first, then markers). */
    function advance(dispatch, getState, from) {
        const state = getState();
        // The reviewed item is no longer proposed, so pickNeighbour finds the nearest later one (wrapping).
        const regionCandidate = pickNeighbour(selectProposedRegions(state), from.kind === 'region' ? from.item : null, 1);
        if (regionCandidate) { focusRegion(dispatch, regionCandidate.id); return regionCandidate; }
        const marker = pickNeighbour(selectProposedMarkers(state), from.kind === 'marker' ? from.item : null, 1);
        if (marker) { focusMarker(dispatch, marker.id, marker.timestamp); return marker; }
        return null;
    }

    /** What A / D act on: the selected suggestion, else the region under the tap line. */
    function resolveTarget(state) {
        const region = state.regions?.byId?.[state.regions.selectedId];
        if (region && (isProposed(region) || isRejected(region))) return { kind: 'region', item: region };
        const marker = state.markers?.byId?.[state.markers.selectedId];
        if (marker && (isProposed(marker) || isRejected(marker))) return { kind: 'marker', item: marker };
        const tap = state.interaction?.tap;
        const underTap = tap?.isActive
            ? app.features.regions.selectors.selectRegionByTimestamp(state, tap.position, tap.timestamp) : null;
        if (underTap && (isProposed(underTap) || isRejected(underTap))) return { kind: 'region', item: underTap };
        return null;
    }

    function reviewIntent(status) {
        return function (dispatch, getState) {
            const target = resolveTarget(getState());
            if (!target) {
                dispatch(app.actions.noticeShown('Select a suggestion first. Press } to step through suggestions.'));
                return false;
            }
            return dispatch(reviewItemIntent(target.kind, target.item.id, status));
        };
    }

    /** Accept, reject or restore one region or marker; A / D then move to the next suggestion. */
    function reviewItemIntent(kind, id, status, options = {}) {
        return function (dispatch, getState) {
            const numeric = Number(id);
            const changed = kind === 'marker'
                ? setMarkerStatus(dispatch, getState, numeric, status)
                : setRegionStatus(dispatch, getState, numeric, status);
            if (!changed) return false;
            if (options.advance !== false && status !== STATUS_PROPOSED) {
                const item = kind === 'marker' ? getState().markers.byId[numeric] : getState().regions.byId[numeric];
                const next = advance(dispatch, getState, { kind, item });
                if (!next) {
                    dispatch(app.actions.noticeShown(status === STATUS_ACCEPTED
                        ? 'Accepted. No more suggestions to review.' : 'Rejected. No more suggestions to review.'));
                }
            }
            return true;
        };
    }

    const acceptSelectedIntent = () => reviewIntent(STATUS_ACCEPTED);
    const rejectSelectedIntent = () => reviewIntent(STATUS_REJECTED);

    /** One undo step for the whole batch: replace the region list with the same regions, new status. */
    function replaceRegionsIntent(mutate, successMessage) {
        return function (dispatch, getState) {
            const state = getState();
            const before = allRegions(state);
            const after = mutate(before);
            if (after.length === before.length && after.every((item, index) => item === before[index])) return 0;
            const selectedId = state.regions.selectedId;
            dispatch(app.actions.regionReplaceAll(after));
            if (Number.isFinite(selectedId)) {
                dispatch(app.actions.regionSelect(selectedId));
            }
            invalidateMetrics();
            if (successMessage) dispatch(app.actions.noticeShown(successMessage(before, after)));
            return Math.abs(before.length - after.length) || after.filter((item, index) => item !== before[index]).length;
        };
    }

    /** "Accept all shown": every proposed region in the current list, as one undo step. */
    function acceptAllShownIntent() {
        return function (dispatch, getState) {
            const ids = new Set(selectReviewList(getState()).shown.filter(isProposed).map(item => item.id));
            if (!ids.size) return 0;
            const stamp = nowIso();
            return dispatch(replaceRegionsIntent(
                regions => regions.map(item => (ids.has(item.id) ? { ...item, status: STATUS_ACCEPTED, reviewedAt: stamp } : item)),
                () => `Accepted ${ids.size} suggestion${ids.size === 1 ? '' : 's'}.`
            ));
        };
    }

    /** Delete rejected regions for good (Ctrl+Z restores them). */
    function purgeRejectedIntent() {
        return function (dispatch, getState) {
            const rejected = allRegions(getState()).filter(isRejected);
            if (!rejected.length) return 0;
            return dispatch(replaceRegionsIntent(
                regions => regions.filter(item => !isRejected(item)),
                () => `Deleted ${rejected.length} rejected suggestion${rejected.length === 1 ? '' : 's'}. Ctrl+Z restores them.`
            ));
        };
    }

    /** `{` / `}`: select the previous / next proposed region and scroll the chart to it. */
    function stepProposedRegionIntent(direction) {
        return function (dispatch, getState) {
            const state = getState();
            const proposed = selectProposedRegions(state);
            if (!proposed.length) {
                const markers = selectProposedMarkers(state);
                if (markers.length) {
                    const current = state.markers.byId[state.markers.selectedId] || null;
                    const marker = pickNeighbour(markers, current, direction < 0 ? -1 : 1);
                    if (marker) { focusMarker(dispatch, marker.id, marker.timestamp); return marker; }
                }
                dispatch(app.actions.noticeShown('No suggestions to review.'));
                return null;
            }
            const current = state.regions.byId[state.regions.selectedId] || null;
            const next = pickNeighbour(proposed, current, direction < 0 ? -1 : 1);
            if (!next) {
                focusRegion(dispatch, proposed[0].id);
                return proposed[0];
            }
            focusRegion(dispatch, next.id);
            return next;
        };
    }

    function setReviewFilterIntent(filter) {
        return function (dispatch) {
            if (!REVIEW_FILTERS.includes(filter)) return;
            dispatch(app.features.annotationPanel.actions.panelSettingsChanged({ reviewFilter: filter }));
        };
    }

    const PANEL_COMMANDS = Object.freeze([
        'suggestion-filter', 'suggestion-accept', 'suggestion-reject', 'suggestion-restore',
        'suggestion-accept-all', 'suggestion-purge', 'promote-classifications'
    ]);

    /** Panel buttons for the review UI (routed here by htmlPanelEvents, ahead of the generic panel command). */
    function panelSuggestionIntent(command, payload = {}) {
        return function (dispatch, getState) {
            const kind = payload.kind === 'marker' ? 'marker' : 'region';
            switch (command) {
                case 'suggestion-filter': return dispatch(setReviewFilterIntent(payload.value));
                case 'suggestion-accept': return dispatch(reviewItemIntent(kind, payload.id, STATUS_ACCEPTED));
                case 'suggestion-reject': return dispatch(reviewItemIntent(kind, payload.id, STATUS_REJECTED));
                case 'suggestion-restore': return dispatch(reviewItemIntent(kind, payload.id, STATUS_PROPOSED, { advance: false }));
                case 'suggestion-accept-all': return dispatch(acceptAllShownIntent());
                case 'suggestion-purge': return dispatch(purgeRejectedIntent());
                case 'promote-classifications':
                    return dispatch(app.features.classifications.thunks.promoteShownToSuggestionsIntent());
                default: return undefined;
            }
        };
    }

    app.features = app.features || {};
    app.features.review = {
        PANEL_COMMANDS,
        STATUS_PROPOSED, STATUS_ACCEPTED, STATUS_REJECTED, STATUSES, REVIEW_FILTERS, META_KEYS,
        helpers: { isProposed, isRejected, isAgent, statusOf, sourceOf, pickMeta, sanitizeAgent, badgeText, formatConfidence, filterByReview, pickNeighbour },
        selectors: {
            selectAllRegionsSorted: state => allRegions(state).sort(byTime),
            selectAllMarkersSorted: state => allMarkers(state).sort(byTime),
            selectProposedRegions, selectRejectedRegions, selectProposedMarkers, selectRejectedMarkers,
            selectReviewFilter, selectReviewCounts, selectReviewList, resolveTarget
        },
        thunks: {
            acceptSelectedIntent, rejectSelectedIntent, reviewItemIntent, acceptAllShownIntent,
            purgeRejectedIntent, stepProposedRegionIntent, setReviewFilterIntent, replaceRegionsIntent,
            panelSuggestionIntent
        }
    };
})(window.NoiseSurveyApp);
