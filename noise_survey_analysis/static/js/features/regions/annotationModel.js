/** Pure annotation normalization shared by creation, imports and migrations. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const METER_PRESENT = 'present';
    const METER_ABSENT = 'absent';
    const METER_UNCHECKED = 'unchecked';
    const DEFAULT_CATEGORY_ID = 'other';
    const DEFAULT_REGION_COLOR = '#1e88e5';
    const LEGACY_AREA_TOLERANCE_MS = 1;
    const DEFAULT_CATEGORIES = Object.freeze([
        Object.freeze({ id: 'dog-bark', label: 'Dog bark', color: '#e65100' }),
        Object.freeze({ id: 'traffic', label: 'Traffic', color: '#1976d2' }),
        Object.freeze({ id: 'plant', label: 'Plant', color: '#388e3c' }),
        Object.freeze({ id: 'speech', label: 'Speech', color: '#7b1fa2' }),
        Object.freeze({ id: DEFAULT_CATEGORY_ID, label: 'Other', color: DEFAULT_REGION_COLOR })
    ]);

    function normalizeColor(value, fallback = null) {
        const text = typeof value === 'string' ? value.trim() : '';
        // Colour values reach both Bokeh and HTML style attributes. Restrict
        // them to hex colours or simple CSS names, never arbitrary CSS text.
        return /^(?:#[\da-f]{3}|#[\da-f]{4}|#[\da-f]{6}|#[\da-f]{8}|[a-z]+)$/i.test(text)
            ? text : fallback;
    }

    function normalizeCatalog(catalog) {
        let incoming;
        if (Array.isArray(catalog)) incoming = catalog;
        else if (catalog?.byId && typeof catalog.byId === 'object') {
            const ids = Array.isArray(catalog.allIds) ? catalog.allIds : Object.keys(catalog.byId);
            incoming = ids.map(id => catalog.byId[id]);
        } else incoming = DEFAULT_CATEGORIES;
        const byId = {};
        const allIds = [];
        incoming.forEach(item => {
            if (!item || typeof item.id !== 'string' || !item.id.trim()) return;
            const id = item.id.trim();
            // Avoid prototype-bearing keys in user-editable/imported catalogs.
            if (['__proto__', 'constructor', 'prototype'].includes(id) || Object.hasOwn(byId, id)) return;
            const label = typeof item.label === 'string' && item.label.trim()
                ? item.label.trim() : (typeof item.name === 'string' && item.name.trim() ? item.name.trim() : id);
            byId[id] = { id, label, color: normalizeColor(item.color, DEFAULT_REGION_COLOR) };
            allIds.push(id);
        });
        if (!Object.hasOwn(byId, DEFAULT_CATEGORY_ID)) {
            byId[DEFAULT_CATEGORY_ID] = { ...DEFAULT_CATEGORIES[DEFAULT_CATEGORIES.length - 1] };
            allIds.push(DEFAULT_CATEGORY_ID);
        }
        return { byId, allIds };
    }

    function positionIds(positions) {
        return [...new Set((Array.isArray(positions) ? positions : []).map(position => {
            if (typeof position === 'string') return position;
            return position?.id || position?.positionId || '';
        }).filter(id => typeof id === 'string' && id && !['__proto__', 'constructor', 'prototype'].includes(id)))];
    }

    function normalizeState(value) {
        return value === METER_PRESENT || value === METER_ABSENT ? value : METER_UNCHECKED;
    }

    function normalizeMeterStates(region, positions = []) {
        const source = region?.meterStates || (region?.positionId ? {} : region) || {};
        const origin = typeof region?.positionId === 'string' ? region.positionId : null;
        const keys = positionIds([...positionIds(positions), ...Object.keys(source), ...(origin ? [origin] : [])]);
        const states = {};
        keys.forEach(id => { states[id] = normalizeState(source[id]); });
        if (origin) states[origin] = METER_PRESENT;
        return states;
    }

    function normalizeAreas(region) {
        const raw = Array.isArray(region?.areas) && region.areas.length ? region.areas : [region];
        const sorted = raw.filter(area => area && area.start != null && area.end != null && Number.isFinite(Number(area.start))
            && Number.isFinite(Number(area.end)) && Number(area.start) !== Number(area.end))
            .map(area => ({ start: Math.min(Number(area.start), Number(area.end)), end: Math.max(Number(area.start), Number(area.end)) }))
            .sort((left, right) => left.start - right.start || left.end - right.end);
        const areas = [];
        sorted.forEach(area => {
            const last = areas[areas.length - 1];
            if (last && area.start <= last.end) last.end = Math.max(last.end, area.end);
            else areas.push({ ...area });
        });
        return areas;
    }

    function normalizeRegion(region, positions = []) {
        if (!region || typeof region.positionId !== 'string' || !region.positionId) return null;
        const areas = normalizeAreas(region);
        if (!areas.length) return null;
        return {
            ...region,
            areas,
            start: areas[0].start,
            end: areas[areas.length - 1].end,
            note: typeof region.note === 'string' ? region.note : '',
            categoryId: typeof region.categoryId === 'string' && region.categoryId ? region.categoryId : DEFAULT_CATEGORY_ID,
            color: normalizeColor(region.color),
            meterStates: normalizeMeterStates(region, positions)
        };
    }

    function effectiveColor(region, catalog) {
        return normalizeColor(region?.color)
            || normalizeColor(catalog?.byId?.[region?.categoryId]?.color)
            || DEFAULT_REGION_COLOR;
    }

    function mergeMeterStates(left, right, positions = []) {
        const first = left?.meterStates || left || {};
        const second = right?.meterStates || right || {};
        const keys = positionIds([...positionIds(positions), ...Object.keys(first), ...Object.keys(second)]);
        const states = {};
        const conflicts = [];
        keys.forEach(id => {
            const a = normalizeState(first[id]);
            const b = normalizeState(second[id]);
            if (a === METER_UNCHECKED) states[id] = b;
            else if (b === METER_UNCHECKED || a === b) states[id] = a;
            else {
                states[id] = METER_UNCHECKED;
                conflicts.push(id);
            }
        });
        return { states, conflicts };
    }

    function consolidateLegacyRegions(regions, positions = []) {
        const groups = [];
        let mergedCount = 0;
        (Array.isArray(regions) ? regions : []).forEach(raw => {
            const region = normalizeRegion(raw, positions);
            if (!region) return;
            // Compare every candidate to the fixed representative, so a series
            // of near-matches cannot drift beyond the 1 ms endpoint tolerance.
            const group = groups.find(candidate => {
                const reference = candidate.reference;
                return !candidate.origins.has(region.positionId)
                    && reference.areas.length === region.areas.length
                    && reference.areas.every((area, index) => Math.abs(area.start - region.areas[index].start) <= LEGACY_AREA_TOLERANCE_MS
                        && Math.abs(area.end - region.areas[index].end) <= LEGACY_AREA_TOLERANCE_MS)
                    && (Boolean(reference.note.trim() && reference.note.trim().replace(/\s+/g, ' ') === region.note.trim().replace(/\s+/g, ' '))
                        || Boolean(reference.color && reference.color.toLowerCase() === region.color?.toLowerCase()));
            });
            if (!group) {
                groups.push({ reference: region, region, origins: new Set([region.positionId]) });
                return;
            }
            group.origins.add(region.positionId);
            const note = [group.region.note, region.note].filter(Boolean).filter((text, index, values) => values.indexOf(text) === index).join('\n');
            group.region = { ...group.region, note, meterStates: { ...group.region.meterStates, [region.positionId]: METER_PRESENT } };
            mergedCount++;
        });
        return { regions: groups.map(group => group.region), mergedCount };
    }

    app.annotationModel = {
        METER_PRESENT, METER_ABSENT, METER_UNCHECKED,
        DEFAULT_CATEGORY_ID, DEFAULT_REGION_COLOR, DEFAULT_CATEGORIES,
        LEGACY_AREA_TOLERANCE_MS, normalizeColor, normalizeCatalog,
        normalizeMeterStates, normalizeAreas, normalizeRegion, effectiveColor,
        mergeMeterStates, consolidateLegacyRegions
    };
})(window.NoiseSurveyApp);
