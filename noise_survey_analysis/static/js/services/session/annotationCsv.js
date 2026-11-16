/** Sectioned annotation CSV. Read only REGIONS/MARKERS, never analysis rows. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    const EXPORT_MODE_ANNOTATIONS = 'annotations';
    const EXPORT_MODE_FULL = 'full';
    const REGION_FIELDS = ['id', 'category', 'category_label', 'category_ids', 'note', 'colour', 'start', 'end', 'duration_s', 'origin_meter', 'areas', 'merge_sources', 'merge_categories'];
    const PROVENANCE_FIELDS = ['chart_offset_ms', 'source_start', 'source_end', 'source_areas', 'data_resolution', 'sample_interval_s', 'coverage', 'LAeq_dB', 'LAFmax_dB',
        'start_local', 'end_local', 'source_start_local', 'source_end_local', 'start_utc', 'end_utc', 'timezone',
        'source', 'status', 'confidence', 'rationale', 'agent', 'agent_run_id'];
    const DEFAULT_TIMEZONE = 'Europe/London';
    const OVERALL_FIELDS = ['region_id', 'category', 'meter', 'state', 'data_resolution', 'sample_interval_s', 'coverage',
        'LAeq_dB', 'LAFmax_dB', 'LAF90_dB', 'background_dB', 'background_LA90_dB', 'background_LAeq_dB',
        'diff_from_background_dB', 'context_duration_s', 'percentile_method', 'missing_reasons'];
    const SPECTRAL_FIELDS = ['region_id', 'category', 'meter', 'state', 'parameter', 'data_resolution', 'sample_interval_s', 'coverage', 'missing_reasons'];
    const MARKER_FIELDS = ['id', 'timestamp', 'note', 'colour', 'metrics', 'timestamp_utc', 'timezone', 'position',
        'source', 'status', 'confidence', 'rationale', 'agent', 'agent_run_id'];
    /** Suggestion provenance as CSV cells; blank for ordinary user annotations. */
    const provenanceCells = item => ({
        source: item?.source || '', status: item?.status || '', confidence: item?.confidence ?? '', rationale: item?.rationale || '',
        agent: item?.agent?.name || '', agent_run_id: item?.agent?.runId || ''
    });
    /** Inverse of provenanceCells for imported rows; pickReviewMeta drops anything invalid. */
    const provenanceFromCells = record => app.annotationModel.pickReviewMeta({
        source: record.source || undefined, status: record.status || undefined, rationale: record.rationale || undefined,
        confidence: record.confidence !== undefined && record.confidence !== '' && Number.isFinite(Number(record.confidence)) ? Number(record.confidence) : undefined,
        agent: record.agent ? { name: record.agent, runId: record.agent_run_id || null } : undefined
    });
    /** Proposed and rejected suggestions are not real events: leave them out unless includeProposed (rejected are always left out). */
    const isExported = (item, includeProposed) => item?.status !== 'rejected' && (item?.status !== 'proposed' || includeProposed);
    const escape = value => {
        const text = value === null || value === undefined ? '' : String(value);
        return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    const timestamp = value => Number.isFinite(Number(value)) && value != null
        ? new Date(Number(value)).toISOString().replace('T', ' ').replace('Z', '') : '';
    /** True UTC instant as ISO-8601 with a Z suffix, matching the Python exporter's *_utc columns. */
    const utcIso = value => Number.isFinite(Number(value)) && value != null
        ? new Date(Number(value)).toISOString() : '';

    /** Naive wall-clock time in `zone` (what Svantek/NTi logs record), same text format as `timestamp`. */
    function localTimestamp(value, zone) {
        if (!Number.isFinite(Number(value)) || value == null) return '';
        const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: zone || DEFAULT_TIMEZONE, hourCycle: 'h23',
            year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
            .formatToParts(new Date(Number(value))).map(part => [part.type, part.value]));
        const millis = String(((Number(value) % 1000) + 1000) % 1000).padStart(3, '0');
        return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}.${millis}`;
    }

    function parseCsvRows(text) {
        const rows = [], row = [];
        let value = '', quoted = false;
        const input = String(text || '').replace(/^\ufeff/, '');
        for (let index = 0; index < input.length; index++) {
            const char = input[index];
            if (char === '"') {
                if (quoted && input[index + 1] === '"') { value += '"'; index++; }
                else quoted = !quoted;
            } else if (!quoted && char === ',') { row.push(value); value = ''; }
            else if (!quoted && (char === '\n' || char === '\r')) {
                row.push(value); rows.push(row.splice(0)); value = '';
                if (char === '\r' && input[index + 1] === '\n') index++;
            } else value += char;
        }
        if (value || row.length) { row.push(value); rows.push(row); }
        if (quoted) throw new Error('Annotation CSV contains an unterminated quoted field.');
        return rows;
    }

    function readSection(rows, name) {
        const marker = rows.findIndex(row => row[0]?.trim() === `[${name}]`);
        if (marker < 0) return [];
        const header = rows[marker + 1] || [];
        const records = [];
        for (let index = marker + 2; index < rows.length; index++) {
            const row = rows[index];
            if (!row.some(value => value.trim()) || /^\[[A-Z_]+\]$/.test(row[0]?.trim())) break;
            records.push(Object.fromEntries(header.map((field, column) => [field, row[column] ?? ''])));
        }
        return records;
    }

    function frequency(label) {
        const match = String(label).toLowerCase().replace(/\s*hz$/, '').match(/([\d.]+)\s*(k)?/);
        return match ? Number(match[1]) * (match[2] ? 1000 : 1) : Infinity;
    }

    function buildAnnotationsCsv(markers = [], regions = [], state = {}, options = {}) {
        state = state || {};
        // Quick exports carry annotations without touching survey arrays or metrics.
        const mode = options.mode ?? EXPORT_MODE_ANNOTATIONS;
        if (![EXPORT_MODE_ANNOTATIONS, EXPORT_MODE_FULL].includes(mode)) throw new Error(`Unknown annotation export mode: ${mode}`);
        const includeAnalysis = mode === EXPORT_MODE_FULL;
        const includeProposed = !!(options.include_proposed ?? options.includeProposed);
        markers = (markers || []).filter(marker => isExported(marker, includeProposed));
        regions = (regions || []).filter(region => isExported(region, includeProposed));
        const models = options.models || app.registry?.models || {};
        const engine = app.annotationMetrics;
        if (includeAnalysis && !engine) throw new Error('The annotation metrics engine is not loaded.');
        const positions = [...new Set([...(state.view?.availablePositions || []), ...Object.keys(models.timeSeriesSources || {}),
            ...regions.flatMap(region => [region.positionId, ...Object.keys(region.meterStates || {})])])].filter(Boolean);
        const categories = app.annotationModel.normalizeCatalog(state.regions?.categories);
        const zone = options.timezone || models.config?.timezone || DEFAULT_TIMEZONE;
        const exported = options.exportedAt || new Date().toISOString();
        const allResolutions = options.include_all_resolutions ?? options.includeAllResolutions ?? state.annotationPanel?.includeAllResolutions ?? false;
        const metricsOptions = {
            backgroundWindowS: options.background_window_s ?? options.backgroundWindowS ?? state.annotationPanel?.backgroundWindowS,
            minContextS: options.min_context_s ?? options.minContextS ?? state.annotationPanel?.minContextS
        };
        const metadata = {
            version: 2, categories,
            meters: positions.map(id => ({ id, title: state.view?.positionDisplayTitles?.[id] || id })),
            sourceConfigs: options.sourceConfigs || models.sourceConfigs || [],
            chart_offsets_ms: state.view?.positionChartOffsets || {},
            local_time_zone: zone
        };
        const lines = [[`NSA annotations export`, 'format=2', `exported=${exported}`, `resolution=${includeAnalysis ? 'best-available' : 'not-calculated'}`].map(escape).join(','),
            ['metadata', JSON.stringify(metadata)].map(escape).join(','), ''];
        const section = (name, fields, records) => {
            lines.push(`[${name}]`, fields.map(escape).join(','));
            records.forEach(record => lines.push(fields.map(field => escape(record[field])).join(',')));
            lines.push('');
        };
        const annotationRows = [], overallRows = [], spectralRows = [];
        const bands = new Set();
        const parameters = new Set();
        if (includeAnalysis) positions.forEach(meter => {
            ['log', 'overview'].forEach(resolution => Object.keys(models.preparedGlyphData?.[meter]?.[resolution]?.prepared_params || {}).forEach(name => parameters.add(name)));
            const streamed = models.spectrogramSources?.[meter]?.log?.data;
            const param = streamed?.parameter?.[0] || streamed?.param?.[0];
            if (param) parameters.add(param);
        });
        regions.forEach(region => {
            const normalized = app.annotationModel.normalizeRegion(region, positions);
            if (!normalized) return;
            const chartOffsetMs = Number(state.view?.positionChartOffsets?.[normalized.positionId]) || 0;
            const sourceAreas = normalized.areas.map(area => ({ start: area.start - chartOffsetMs, end: area.end - chartOffsetMs }));
            const origin = includeAnalysis
                ? engine.computeRegion(normalized, state, models, { ...metricsOptions, resolution: 'auto' })
                : { durationMs: normalized.areas.reduce((total, area) => total + area.end - area.start, 0), chartOffsetMs, sourceAreas };
            const category = categories.byId[normalized.categoryId];
            annotationRows.push({
                id: normalized.id, category: normalized.categoryId, category_label: category?.label || normalized.categoryId,
                category_ids: JSON.stringify(normalized.categoryIds),
                note: normalized.note, colour: normalized.color, start: timestamp(normalized.start), end: timestamp(normalized.end),
                duration_s: origin.durationMs / 1000, origin_meter: normalized.positionId, areas: JSON.stringify(normalized.areas),
                merge_sources: normalized.mergeSources ? JSON.stringify(normalized.mergeSources) : '',
                merge_categories: normalized.mergeCategories ? JSON.stringify(normalized.mergeCategories) : '',
                ...normalized.meterStates, chart_offset_ms: origin.chartOffsetMs,
                source_start: timestamp(origin.sourceAreas[0]?.start), source_end: timestamp(origin.sourceAreas.at(-1)?.end),
                source_areas: JSON.stringify(origin.sourceAreas), data_resolution: origin.dataResolution,
                sample_interval_s: origin.sampleIntervalS, coverage: origin.coverage, LAeq_dB: origin.laeq, LAFmax_dB: origin.lafmax,
                start_local: localTimestamp(normalized.start, zone), end_local: localTimestamp(normalized.end, zone),
                source_start_local: localTimestamp(origin.sourceAreas[0]?.start, zone), source_end_local: localTimestamp(origin.sourceAreas.at(-1)?.end, zone),
                start_utc: utcIso(normalized.start), end_utc: utcIso(normalized.end), timezone: zone,
                ...provenanceCells(normalized)
            });
            if (!includeAnalysis) return;
            positions.forEach(meter => {
                const resolutions = allResolutions ? ['log', 'overview'].filter(resolution =>
                    models.timeSeriesSources?.[meter]?.[resolution]?.data?.Datetime?.length
                    || Object.keys(models.preparedGlyphData?.[meter]?.[resolution]?.prepared_params || {}).length
                    || (resolution === 'log' && models.spectrogramSources?.[meter]?.log?.data?.times_ms?.length)) : ['auto'];
                (resolutions.length ? resolutions : ['auto']).forEach(resolution => {
                    const metrics = engine.computeRegion(region, state, models, { ...metricsOptions, positionId: meter, resolution });
                    const identity = { region_id: region.id, category: normalized.categoryId, meter, state: normalized.meterStates[meter], data_resolution: metrics.dataResolution };
                    overallRows.push({ ...identity, sample_interval_s: metrics.sampleIntervalS, coverage: metrics.coverage,
                        LAeq_dB: metrics.laeq, LAFmax_dB: metrics.lafmax, LAF90_dB: metrics.la90,
                        background_dB: metrics.backgroundLA90, background_LA90_dB: metrics.backgroundLA90, background_LAeq_dB: metrics.backgroundLAeq,
                        diff_from_background_dB: metrics.diffFromBackground, context_duration_s: metrics.contextDurationS,
                        percentile_method: metrics.percentileMethod, missing_reasons: metrics.missingReasons.join('; ') });
                    parameters.forEach(parameter => {
                        const spectrum = metrics.spectra[parameter];
                        const record = { ...identity, parameter, data_resolution: spectrum?.source || metrics.dataResolution,
                            sample_interval_s: spectrum?.sampleIntervalS, coverage: spectrum?.coverage,
                            missing_reasons: spectrum ? (spectrum.missingReasons || []).join('; ') : 'Spectral parameter unavailable at this meter/resolution' };
                        spectrum?.labels.forEach((label, index) => {
                            const hz = frequency(label);
                            const field = Number.isFinite(hz) ? `${hz}Hz` : label;
                            bands.add(field); record[field] = spectrum.values[index];
                        });
                        spectralRows.push(record);
                    });
                });
            });
        });
        section('REGIONS', [...REGION_FIELDS, ...positions, ...PROVENANCE_FIELDS], annotationRows);
        if (includeAnalysis) {
            section('OVERALL', OVERALL_FIELDS, overallRows);
            section('SPECTRAL', [...SPECTRAL_FIELDS, ...[...bands].sort((a, b) => frequency(a) - frequency(b))], spectralRows);
        }
        section('MARKERS', MARKER_FIELDS, markers.map(marker => ({ id: marker.id, timestamp: timestamp(marker.timestamp), note: marker.note,
            colour: marker.color, metrics: JSON.stringify(marker.metrics || marker.metricsSnapshot || {}),
            timestamp_utc: utcIso(marker.timestamp), timezone: zone, position: marker.positionId || '', ...provenanceCells(marker) })));
        section('NOTES', ['key', 'value'], Object.entries({
            exported, export_mode: mode, time_zone: 'UTC', local_time_zone: zone,
            time_basis: `start/end/source_start/source_end are true UTC. start_local/end_local/source_start_local/source_end_local are naive ${zone} wall-clock time (BST in summer) and match the instrument _log.csv/_summary.csv time basis; use source_*_local to look up rows in the survey files (the source_* columns remove any chart alignment offset). All metrics are calculated for the UTC instants; data_resolution gives the resolution they came from (log or overview).`,
            source_files: JSON.stringify(metadata.sourceConfigs), chart_offsets_ms: JSON.stringify(metadata.chart_offsets_ms),
            resolution_policy: includeAnalysis
                ? (allResolutions ? 'Separate log and overview rows where available' : 'Best available resolution per region and meter; complete log preferred, otherwise overview, otherwise partial log with coverage recorded')
                : 'Annotations only; survey metrics are not calculated and headline metric columns are blank. Marker snapshots are preserved unchanged.',
            background_method: includeAnalysis
                ? `LA90 (duration-weighted inverse-CDF p10) of pooled context before/after each area; LAeq of the same samples also reported; exclude all present regions; window=${metricsOptions.backgroundWindowS ?? 300}s; minimum=${metricsOptions.minContextS ?? 60}s`
                : 'Not calculated in annotations-only export',
            caveats: includeAnalysis
                ? 'LAF90 derived from overview or 1 s data is indicative. Missing genuine LAFmax remains blank. Browser export can only use available embedded/streamed data.'
                : 'This file carries annotation geometry, states, categories and existing marker snapshots; use the browser analysis export or server full-resolution export for calculated region metrics.'
        }).map(([key, value]) => ({ key, value })));
        return lines.join('\r\n');
    }

    function parseTimestamp(value) {
        if (/^-?\d+(?:\.\d+)?$/.test(String(value).trim())) return Number(value);
        const normalized = String(value).trim().replace(' ', 'T');
        return Date.parse(/[zZ]$|[+-]\d\d:\d\d$/.test(normalized) ? normalized : `${normalized}Z`);
    }

    function parseAnnotationsCsv(text) {
        const rows = parseCsvRows(text);
        const metadataRow = rows.find(row => row[0]?.trim() === 'metadata');
        const metadata = metadataRow ? JSON.parse(metadataRow[1]) : {};
        const records = readSection(rows, 'REGIONS');
        const positions = (metadata.meters || []).map(meter => meter.id);
        const known = new Set([...REGION_FIELDS, ...PROVENANCE_FIELDS]);
        if (!positions.length && records.length) Object.keys(records[0]).filter(key => !known.has(key)
            && records.some(row => ['present', 'absent', 'unchecked'].includes(row[key]))).forEach(key => positions.push(key));
        const regions = records.map(record => {
            const areas = record.areas ? JSON.parse(record.areas) : [{ start: parseTimestamp(record.start), end: parseTimestamp(record.end) }];
            return app.annotationModel.normalizeRegion({ id: Number(record.id), positionId: record.origin_meter,
                areas, note: record.note, color: record.colour || null, categoryId: record.category || 'other',
                categoryIds: record.category_ids ? JSON.parse(record.category_ids) : undefined,
                mergeSources: record.merge_sources ? JSON.parse(record.merge_sources) : undefined,
                mergeCategories: record.merge_categories ? JSON.parse(record.merge_categories) : undefined,
                meterStates: Object.fromEntries(positions.map(id => [id, record[id] || 'unchecked'])),
                ...provenanceFromCells(record) }, positions);
        }).filter(Boolean);
        const markers = readSection(rows, 'MARKERS').map(record => ({ id: Number(record.id), timestamp: parseTimestamp(record.timestamp),
            note: record.note || '', color: record.colour || '#fdd835', metrics: JSON.parse(record.metrics || record.metrics_json || '{}'),
            ...(record.position ? { positionId: record.position } : {}), ...provenanceFromCells(record) }))
            .filter(marker => Number.isFinite(marker.timestamp));
        const categories = app.annotationModel.normalizeCatalog(metadata.categories || [
            ...app.annotationModel.DEFAULT_CATEGORIES,
            ...records.map(record => ({ id: record.category, label: record.category_label || record.category, color: '#1e88e5' }))
        ]);
        return { regions, markers, categories, metadata, mergedCount: 0 };
    }

    app.annotationCsv = { buildAnnotationsCsv, parseAnnotationsCsv, parseCsvRows, readSection,
        EXPORT_MODE_ANNOTATIONS, EXPORT_MODE_FULL, REGION_FIELDS, PROVENANCE_FIELDS, OVERALL_FIELDS, SPECTRAL_FIELDS, MARKER_FIELDS };
})(window.NoiseSurveyApp);
