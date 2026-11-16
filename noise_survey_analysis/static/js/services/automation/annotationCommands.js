// noise_survey_analysis/static/js/services/automation/annotationCommands.js

/**
 * @fileoverview Browser side of the annotation control API (see CONTROL_API.md).
 *
 * Python validates every payload first (control/annotation_validation.py); these handlers re-check the parts
 * only the browser knows (positions, existing ids, categories) and apply the change through the normal actions
 * so undo, autosave and rendering behave exactly as for edits made by hand.
 *
 * Times in a payload are "source" time by default (`time_basis: "source"`): the true UTC instant of the data, as
 * read from the survey files. The browser adds the position's chart offset to get display time (the chart axis,
 * which is what regions and markers are stored in). `time_basis: "display"` takes the times as display time
 * already. Records returned carry both (`start`/`end` display, `source_start`/`source_end`).
 * Handlers return `{success, message, data}`; throwing is a failure.
 */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const MAX_ITEMS = 500;
    const SHOW_PAD_FRACTION = 0.2;
    const MIN_SHOW_WIDTH_MS = 1000;

    const review = () => app.features.review;
    const isoOf = ms => (Number.isFinite(ms) ? new Date(ms).toISOString() : null);
    const nowIso = () => new Date().toISOString();

    function fail(message) { throw new Error(message); }

    // One command is one undo step, even when it creates categories and then adds items.
    const batched = fn => (app.history && typeof app.history.batch === 'function' ? app.history.batch(fn) : fn());

    const basisOf = payload => (payload?.time_basis === 'display' ? 'display' : 'source');
    function offsetOf(state, position) {
        const value = Number(state.view?.positionChartOffsets?.[position]);
        return Number.isFinite(value) ? value : 0;
    }
    /** Payload time -> display time for `position` (a no-op when the payload is already display time). */
    const toDisplay = (time, state, position, basis) => (basis === 'display' ? time : time + offsetOf(state, position));

    function positionsOf(state) {
        return (state.view?.availablePositions || []).filter(id => typeof id === 'string');
    }

    function requirePosition(state, position, label) {
        const known = positionsOf(state);
        if (typeof position !== 'string' || !position) fail(`${label}: position is required`);
        if (known.length && !known.includes(position)) fail(`${label}: unknown position '${position}' (known: ${known.join(', ')})`);
        return position;
    }

    function agentOf(payload) {
        const agent = review().helpers.sanitizeAgent(payload?.agent);
        if (!agent) fail('agent.name is required');
        return agent;
    }

    function limit(list, name) {
        if (!Array.isArray(list) || !list.length) fail(`${name} must be a non-empty list`);
        if (list.length > MAX_ITEMS) fail(`${name} has ${list.length} items; the limit is ${MAX_ITEMS}`);
        return list;
    }

    // ---- shapes returned to the caller -----------------------------------------------------------

    function regionToApi(region, state) {
        const catalog = state.regions?.categories?.byId || {};
        const categoryIds = region.categoryIds || (region.categoryId ? [region.categoryId] : ['other']);
        const areas = (region.areas && region.areas.length ? region.areas : [{ start: region.start, end: region.end }])
            .map(area => ({ start: area.start, end: area.end }));
        const helpers = review().helpers;
        const offset = offsetOf(state, region.positionId);
        return {
            id: region.id,
            position: region.positionId,
            start: region.start, end: region.end,
            start_iso: isoOf(region.start), end_iso: isoOf(region.end),
            source_start: region.start - offset, source_end: region.end - offset,
            source_start_iso: isoOf(region.start - offset), source_end_iso: isoOf(region.end - offset),
            areas,
            source_areas: areas.map(area => ({ start: area.start - offset, end: area.end - offset })),
            note: region.note || '',
            category: categoryIds[0],
            category_label: catalog[categoryIds[0]]?.label || categoryIds[0],
            categories: categoryIds,
            meter_states: region.meterStates || {},
            color: region.color || null,
            source: helpers.sourceOf(region),
            status: helpers.statusOf(region),
            rationale: region.rationale ?? null,
            confidence: Number.isFinite(region.confidence) ? region.confidence : null,
            agent: region.agent ? { name: region.agent.name, run_id: region.agent.runId ?? null } : null,
            created_at: region.createdAt ?? null,
            reviewed_at: region.reviewedAt ?? null,
            selected: state.regions?.selectedId === region.id
        };
    }

    function markerToApi(marker, state) {
        const helpers = review().helpers;
        const sourceTimestamp = marker.timestamp - offsetOf(state, marker.positionId);
        return {
            id: marker.id,
            position: marker.positionId ?? null,
            timestamp: marker.timestamp, timestamp_iso: isoOf(marker.timestamp),
            source_timestamp: sourceTimestamp, source_timestamp_iso: isoOf(sourceTimestamp),
            note: marker.note || '',
            color: marker.color || null,
            source: helpers.sourceOf(marker),
            status: helpers.statusOf(marker),
            rationale: marker.rationale ?? null,
            confidence: Number.isFinite(marker.confidence) ? marker.confidence : null,
            agent: marker.agent ? { name: marker.agent.name, run_id: marker.agent.runId ?? null } : null,
            created_at: marker.createdAt ?? null,
            reviewed_at: marker.reviewedAt ?? null,
            selected: state.markers?.selectedId === marker.id
        };
    }

    // ---- list ------------------------------------------------------------------------------------

    function listAnnotations(payload, { getState }) {
        const state = getState();
        const { kind, status, source, start, end } = payload || {};
        const keep = record => (!status || record.status === status) && (!source || record.source === source);
        const prefix = basisOf(payload) === 'display' ? '' : 'source_';
        const inWindow = (low, high) => (!Number.isFinite(start) || high >= start) && (!Number.isFinite(end) || low <= end);
        const regions = kind === 'marker' ? [] : review().selectors.selectAllRegionsSorted(state)
            .map(region => regionToApi(region, state))
            .filter(record => keep(record) && inWindow(record[`${prefix}start`], record[`${prefix}end`]));
        const markers = kind === 'region' ? [] : review().selectors.selectAllMarkersSorted(state)
            .map(marker => markerToApi(marker, state))
            .filter(record => keep(record) && inWindow(record[`${prefix}timestamp`], record[`${prefix}timestamp`]));
        const viewport = state.view?.viewport;
        return {
            success: true,
            message: `${regions.length} region(s), ${markers.length} marker(s)`,
            data: {
                positions: positionsOf(state),
                position_titles: state.view?.positionDisplayTitles || {},
                position_chart_offsets: state.view?.positionChartOffsets || {},
                timezone: app.registry?.models?.config?.timezone || null,
                viewport: viewport && Number.isFinite(viewport.min) ? { start: viewport.min, end: viewport.max } : null,
                categories: state.regions?.categories?.allIds?.map(id => ({
                    id, label: state.regions.categories.byId[id].label
                })) || [],
                regions, markers
            }
        };
    }

    // ---- regions ---------------------------------------------------------------------------------

    function resolveCategory(dispatch, getState, name, created) {
        const catalog = getState().regions.categories;
        if (catalog?.byId?.[name]) return name;
        const lower = name.toLowerCase();
        const match = catalog?.allIds?.find(id => catalog.byId[id].label.toLowerCase() === lower || id.toLowerCase() === lower);
        if (match) return match;
        const id = dispatch(app.features.regions.thunks.createCategoryIntent({ label: name }));
        if (id) created.push(name);
        return id || 'other';
    }

    function meterStatesFor(state, position, given) {
        const positions = positionsOf(state);
        const requested = {};
        Object.entries(given || {}).forEach(([key, value]) => {
            if (!positions.length || positions.includes(key)) requested[key] = value;
        });
        return app.annotationModel.normalizeMeterStates({ positionId: position, meterStates: requested }, positions);
    }

    function addRegions(payload, { dispatch, getState }) {
        const items = limit(payload?.regions, 'regions');
        const agent = agentOf(payload);
        const state = getState();
        const created = [];
        const stamp = nowIso();
        // Check every item before changing anything, so a bad item leaves the dashboard untouched.
        items.forEach((item, index) => {
            const label = `regions[${index}]`;
            requirePosition(state, item.position, label);
            const areas = Array.isArray(item.areas) ? item.areas : [];
            if (!areas.length || !areas.every(a => Number.isFinite(a?.start) && Number.isFinite(a?.end) && a.start < a.end)) {
                fail(`${label}: needs finite start < end`);
            }
        });
        const basis = basisOf(payload);
        const regions = items.map(item => {
            const areas = item.areas.map(a => ({
                start: toDisplay(a.start, state, item.position, basis), end: toDisplay(a.end, state, item.position, basis)
            }));
            const categoryId = item.category ? resolveCategory(dispatch, getState, item.category, created) : 'other';
            return {
                positionId: item.position,
                start: areas[0].start, end: areas[areas.length - 1].end, areas,
                note: item.note || '',
                categoryId, categoryIds: [categoryId],
                color: item.color || null,
                meterStates: meterStatesFor(state, item.position, item.meter_states),
                ...review().helpers.pickMeta({
                    source: 'agent', status: item.status || 'proposed', rationale: item.rationale,
                    confidence: item.confidence, agent, createdAt: stamp
                })
            };
        });
        const before = getState().regions;
        dispatch(app.actions.regionsAdded(regions));
        const after = getState().regions;
        // regionsAdded selects the last new region; leave the user's own selection alone.
        if (before.selectedId !== after.selectedId) {
            dispatch(before.selectedId && after.byId[before.selectedId]
                ? app.actions.regionSelect(before.selectedId) : app.actions.regionClearSelection());
        }
        const known = new Set(before.allIds);
        const ids = after.allIds.filter(id => !known.has(id));
        app.regions?.invalidateMetricsCache?.();
        const byClientRef = {};
        items.forEach((item, index) => { if (item.client_ref && ids[index] !== undefined) byClientRef[item.client_ref] = ids[index]; });
        if (ids.length !== items.length) fail(`only ${ids.length} of ${items.length} regions were added (ids ${ids.join(', ')})`);
        return {
            success: true,
            message: `Added ${ids.length} region(s) from ${agent.name}.`,
            data: { ids, by_client_ref: byClientRef, categories_created: created }
        };
    }

    function updateRegion(payload, { dispatch, getState }) {
        const id = Number(payload?.id);
        const state = getState();
        const region = state.regions.byId[id];
        if (!region) fail(`region ${payload?.id} not found`);
        const changes = payload.changes || {};
        const patch = {};
        const created = [];
        const basis = basisOf(payload);
        const shift = time => toDisplay(time, state, region.positionId, basis);
        if (changes.areas) patch.areas = changes.areas.map(a => ({ start: shift(a.start), end: shift(a.end) }));
        if (Number.isFinite(changes.start)) patch.start = shift(changes.start);
        if (Number.isFinite(changes.end)) patch.end = shift(changes.end);
        if (typeof changes.note === 'string') patch.note = changes.note;
        if (typeof changes.color === 'string') patch.color = changes.color;
        if (changes.category) {
            const categoryId = resolveCategory(dispatch, getState, changes.category, created);
            patch.categoryId = categoryId; patch.categoryIds = [categoryId];
        }
        if (changes.meter_states) {
            patch.meterStates = meterStatesFor(state, region.positionId, { ...region.meterStates, ...changes.meter_states });
        }
        const meta = review().helpers.pickMeta(changes);
        delete meta.source; delete meta.agent; delete meta.createdAt; delete meta.reviewedAt;
        Object.assign(patch, meta);
        if (meta.status && meta.status !== review().helpers.statusOf(region)) patch.reviewedAt = nowIso();
        if (!Object.keys(patch).length) fail('no valid changes given');
        dispatch(app.actions.regionUpdate(id, patch));
        const updated = getState().regions.byId[id];
        if (updated === region) fail('the region was not changed (check start < end)');
        app.regions?.invalidateRegionMetrics?.(id);
        app.regions?.invalidateMetricsCache?.();
        return { success: true, message: `Updated region ${id}.`, data: { region: regionToApi(updated, getState()), categories_created: created } };
    }

    function deleteRegions(payload, { dispatch, getState }) {
        const state = getState();
        const wanted = limit(payload?.ids, 'ids').map(Number);
        const present = wanted.filter(id => state.regions.byId[id]);
        const missing = wanted.filter(id => !state.regions.byId[id]);
        const refused = present.filter(id => review().helpers.sourceOf(state.regions.byId[id]) !== 'agent');
        if (refused.length && !payload.force) {
            fail(`refusing to delete user region(s) ${refused.join(', ')} without force`);
        }
        if (present.length) {
            const drop = new Set(present);
            dispatch(review().thunks.replaceRegionsIntent(regions => regions.filter(r => !drop.has(r.id))));
        }
        return { success: true, message: `Deleted ${present.length} region(s).`, data: { deleted: present, missing } };
    }

    // ---- markers ---------------------------------------------------------------------------------

    function addMarkers(payload, { dispatch, getState }) {
        const items = limit(payload?.markers, 'markers');
        const agent = agentOf(payload);
        const state = getState();
        const stamp = nowIso();
        items.forEach((item, index) => {
            if (!Number.isFinite(item.timestamp)) fail(`markers[${index}]: timestamp is required`);
            if (item.position != null) requirePosition(state, item.position, `markers[${index}]`);
        });
        const ids = [];
        const skipped = [];
        const byClientRef = {};
        const basis = basisOf(payload);
        items.forEach((item, index) => {
            const counter = getState().markers.counter;
            dispatch({
                type: app.actionTypes.MARKER_ADDED,
                payload: {
                    timestamp: toDisplay(item.timestamp, state, item.position, basis),
                    note: item.note || '',
                    color: item.color || undefined,
                    positionId: item.position || undefined,
                    ...review().helpers.pickMeta({
                        source: 'agent', status: item.status || 'proposed', rationale: item.rationale,
                        confidence: item.confidence, agent, createdAt: stamp
                    })
                }
            });
            const after = getState().markers;
            if (after.counter === counter) { skipped.push({ index, reason: 'a marker already exists at this time' }); return; }
            ids.push(counter);
            if (item.client_ref) byClientRef[item.client_ref] = counter;
        });
        // markerAdded selects the new marker; clear it so a batch does not steal the user's selection.
        if (ids.length && getState().markers.selectedId !== state.markers.selectedId) {
            dispatch(app.actions.markerSelect(state.markers.byId[state.markers.selectedId] ? state.markers.selectedId : null));
        }
        return { success: true, message: `Added ${ids.length} marker(s) from ${agent.name}.`, data: { ids, by_client_ref: byClientRef, skipped } };
    }

    function updateMarker(payload, { dispatch, getState }) {
        const id = Number(payload?.id);
        const state = getState();
        const marker = state.markers.byId[id];
        if (!marker) fail(`marker ${payload?.id} not found`);
        const changes = payload.changes || {};
        const patch = {};
        if (Number.isFinite(changes.timestamp)) {
            const position = Object.prototype.hasOwnProperty.call(changes, 'position') ? changes.position : marker.positionId;
            patch.timestamp = toDisplay(changes.timestamp, state, position, basisOf(payload));
        }
        if (typeof changes.note === 'string') patch.note = changes.note;
        if (typeof changes.color === 'string') patch.color = changes.color;
        if (Object.prototype.hasOwnProperty.call(changes, 'position')) {
            if (changes.position !== null) requirePosition(state, changes.position, 'changes');
            patch.positionId = changes.position;
        }
        const meta = review().helpers.pickMeta(changes);
        delete meta.source; delete meta.agent; delete meta.createdAt; delete meta.reviewedAt;
        Object.assign(patch, meta);
        if (meta.status && meta.status !== review().helpers.statusOf(marker)) patch.reviewedAt = nowIso();
        if (!Object.keys(patch).length) fail('no valid changes given');
        dispatch(app.actions.markerUpdate(id, patch));
        const updated = getState().markers.byId[id];
        if (updated === marker) fail('the marker was not changed (another marker may already be at that time)');
        return { success: true, message: `Updated marker ${id}.`, data: { marker: markerToApi(updated, getState()) } };
    }

    function deleteMarkers(payload, { dispatch, getState }) {
        const state = getState();
        const wanted = limit(payload?.ids, 'ids').map(Number);
        const present = wanted.filter(id => state.markers.byId[id]);
        const missing = wanted.filter(id => !state.markers.byId[id]);
        const refused = present.filter(id => review().helpers.sourceOf(state.markers.byId[id]) !== 'agent');
        if (refused.length && !payload.force) fail(`refusing to delete user marker(s) ${refused.join(', ')} without force`);
        if (present.length) {
            const drop = new Set(present);
            const keep = state.markers.allIds.filter(id => !drop.has(id)).map(id => state.markers.byId[id]);
            dispatch(app.actions.markersReplace(keep, { selectedId: state.markers.selectedId }));
        }
        return { success: true, message: `Deleted ${present.length} marker(s).`, data: { deleted: present, missing } };
    }

    // ---- show ------------------------------------------------------------------------------------

    /** Scroll the page so a position's chart is visible (best effort; Bokeh view lookup varies by version). */
    function scrollToPosition(positionId) {
        try {
            const charts = app.registry?.controllers?.chartsByName;
            let model = null;
            charts?.forEach?.(chart => { if (!model && chart.positionId === positionId) model = chart.model; });
            const index = window.Bokeh?.index;
            const view = model && index
                ? (index.get_by_id?.(model.id) || index.find_one?.(model) || index.get_one?.(model)
                    || Object.values(index.roots ? Object.fromEntries(index.roots.entries?.() || []) : index)
                        .map(root => root?.child_views?.get?.(model) || root?.find_one?.(model)).find(Boolean))
                : null;
            const element = view?.el || view?.canvas_view?.el;
            if (element?.scrollIntoView) { element.scrollIntoView({ block: 'center', behavior: 'smooth' }); return true; }
        } catch (error) {
            console.warn('[show] could not scroll to position', error);
        }
        return false;
    }

    function show(payload, { dispatch, getState }) {
        const state = getState();
        let start; let end; let position = payload?.position || null;
        const select = payload?.select !== false;
        if (payload?.region_id != null) {
            const region = state.regions.byId[Number(payload.region_id)];
            if (!region) fail(`region ${payload.region_id} not found`);
            start = region.start; end = region.end; position = position || region.positionId;
            if (select) dispatch(app.features.regions.thunks.selectRegionIntent(region.id));
        } else if (payload?.marker_id != null) {
            const marker = state.markers.byId[Number(payload.marker_id)];
            if (!marker) fail(`marker ${payload.marker_id} not found`);
            const width = Number(state.view?.viewport?.max) - Number(state.view?.viewport?.min);
            const half = Math.max(Number.isFinite(width) ? width : 60000, MIN_SHOW_WIDTH_MS * 10) / 2 / (1 + 2 * SHOW_PAD_FRACTION);
            start = marker.timestamp - half; end = marker.timestamp + half; position = position || marker.positionId;
            if (select) dispatch(app.features.markers.thunks.selectMarkerIntent(marker.id));
        } else {
            if (position) requirePosition(state, position, 'show');
            const basis = basisOf(payload);
            start = Number.isFinite(payload?.start) ? toDisplay(payload.start, state, position, basis) : payload?.start;
            end = Number.isFinite(payload?.end) ? toDisplay(payload.end, state, position, basis) : payload?.end;
        }
        if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) fail('show needs a valid time window');
        const pad = Math.max(end - start, MIN_SHOW_WIDTH_MS) * SHOW_PAD_FRACTION;
        const viewport = { start: start - pad, end: end + pad };
        dispatch(app.actions.regionViewportCentered(viewport.start, viewport.end));
        if (payload?.parameter) {
            const change = app.services?.eventHandlers?.view?.handleParameterChange;
            if (typeof change === 'function') change(payload.parameter);
        }
        const scrolled = position ? scrollToPosition(position) : false;
        if (typeof payload?.message === 'string' && payload.message) dispatch(app.actions.noticeShown(payload.message));
        return { success: true, message: 'Showing the requested window.', data: { viewport, scrolled } };
    }

    // ---- registration ----------------------------------------------------------------------------

    const undoable = handler => (payload, context) => batched(() => handler(payload, context));
    const handlers = {
        list_annotations: listAnnotations, add_regions: undoable(addRegions), update_region: undoable(updateRegion),
        delete_regions: undoable(deleteRegions), add_markers: undoable(addMarkers), update_marker: undoable(updateMarker),
        delete_markers: undoable(deleteMarkers), show
    };
    if (app.session && typeof app.session.registerAutomationCommand === 'function') {
        Object.entries(handlers).forEach(([name, handler]) => app.session.registerAutomationCommand(name, handler));
    }
    app.services = app.services || {};
    app.services.annotationCommands = { handlers, regionToApi, markerToApi };
})(window.NoiseSurveyApp);
