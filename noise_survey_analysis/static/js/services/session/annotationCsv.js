/** Sectioned annotation CSV. Read only REGIONS/MARKERS, never analysis rows. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    const REGION_FIELDS = ['id', 'category', 'category_label', 'note', 'colour', 'start', 'end', 'duration_s', 'origin_meter', 'areas'];
    const PROVENANCE_FIELDS = ['chart_offset_ms', 'source_start', 'source_end', 'source_areas', 'data_resolution', 'sample_interval_s', 'coverage', 'LAeq_dB', 'LAFmax_dB'];
    const OVERALL_FIELDS = ['region_id', 'category', 'meter', 'state', 'data_resolution', 'sample_interval_s', 'coverage',
        'LAeq_dB', 'LAFmax_dB', 'LAF90_dB', 'background_dB', 'background_LA90_dB', 'background_LAeq_dB',
        'diff_from_background_dB', 'context_duration_s', 'percentile_method', 'missing_reasons'];
    const SPECTRAL_FIELDS = ['region_id', 'category', 'meter', 'state', 'parameter', 'data_resolution', 'sample_interval_s', 'coverage', 'missing_reasons'];
    const MARKER_FIELDS = ['id', 'timestamp', 'note', 'colour', 'metrics'];
    const escape = value => {
        const text = value === null || value === undefined ? '' : String(value);
        return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
    };
    const timestamp = value => Number.isFinite(Number(value)) && value != null
        ? new Date(Number(value)).toISOString().replace('T', ' ').replace('Z', '') : '';

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
        const models = options.models || app.registry?.models || {};
        const engine = app.annotationMetrics;
        if (!engine) throw new Error('The annotation metrics engine is not loaded.');
        const positions = [...new Set([...(state.view?.availablePositions || []), ...Object.keys(models.timeSeriesSources || {}),
            ...regions.flatMap(region => [region.positionId, ...Object.keys(region.meterStates || {})])])].filter(Boolean);
        const categories = app.annotationModel.normalizeCatalog(state.regions?.categories);
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
            chart_offsets_ms: state.view?.positionChartOffsets || {}
        };
        const lines = [[`NSA annotations export`, 'format=2', `exported=${exported}`, 'resolution=best-available'].map(escape).join(','),
            ['metadata', JSON.stringify(metadata)].map(escape).join(','), ''];
        const section = (name, fields, records) => {
            lines.push(`[${name}]`, fields.map(escape).join(','));
            records.forEach(record => lines.push(fields.map(field => escape(record[field])).join(',')));
            lines.push('');
        };
        const annotationRows = [], overallRows = [], spectralRows = [];
        const bands = new Set();
        const parameters = new Set();
        positions.forEach(meter => {
            ['log', 'overview'].forEach(resolution => Object.keys(models.preparedGlyphData?.[meter]?.[resolution]?.prepared_params || {}).forEach(name => parameters.add(name)));
            const streamed = models.spectrogramSources?.[meter]?.log?.data;
            const param = streamed?.parameter?.[0] || streamed?.param?.[0];
            if (param) parameters.add(param);
        });
        regions.forEach(region => {
            const origin = engine.computeRegion(region, state, models, { ...metricsOptions, resolution: 'auto' });
            const normalized = app.annotationModel.normalizeRegion(region, positions);
            if (!normalized) return;
            const category = categories.byId[normalized.categoryId];
            annotationRows.push({
                id: normalized.id, category: normalized.categoryId, category_label: category?.label || normalized.categoryId,
                note: normalized.note, colour: normalized.color, start: timestamp(normalized.start), end: timestamp(normalized.end),
                duration_s: origin.durationMs / 1000, origin_meter: normalized.positionId, areas: JSON.stringify(normalized.areas),
                ...normalized.meterStates, chart_offset_ms: origin.chartOffsetMs,
                source_start: timestamp(origin.sourceAreas[0]?.start), source_end: timestamp(origin.sourceAreas.at(-1)?.end),
                source_areas: JSON.stringify(origin.sourceAreas), data_resolution: origin.dataResolution,
                sample_interval_s: origin.sampleIntervalS, coverage: origin.coverage, LAeq_dB: origin.laeq, LAFmax_dB: origin.lafmax
            });
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
        section('OVERALL', OVERALL_FIELDS, overallRows);
        section('SPECTRAL', [...SPECTRAL_FIELDS, ...[...bands].sort((a, b) => frequency(a) - frequency(b))], spectralRows);
        section('MARKERS', MARKER_FIELDS, markers.map(marker => ({ id: marker.id, timestamp: timestamp(marker.timestamp), note: marker.note,
            colour: marker.color, metrics: JSON.stringify(marker.metrics || marker.metricsSnapshot || {}) })));
        section('NOTES', ['key', 'value'], Object.entries({
            exported, time_zone: 'UTC', source_files: JSON.stringify(metadata.sourceConfigs), chart_offsets_ms: JSON.stringify(metadata.chart_offsets_ms),
            resolution_policy: allResolutions ? 'Separate log and overview rows where available' : 'Best available resolution per region and meter; log requires complete area coverage, otherwise overview',
            background_method: `LA90 (duration-weighted inverse-CDF p10) of pooled context before/after each area; LAeq of the same samples also reported; exclude all present regions; window=${metricsOptions.backgroundWindowS ?? 300}s; minimum=${metricsOptions.minContextS ?? 60}s`,
            caveats: 'LAF90 derived from overview or 1 s data is indicative. Missing genuine LAFmax remains blank. Browser export can only use available embedded/streamed data.'
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
                meterStates: Object.fromEntries(positions.map(id => [id, record[id] || 'unchecked'])) }, positions);
        }).filter(Boolean);
        const markers = readSection(rows, 'MARKERS').map(record => ({ id: Number(record.id), timestamp: parseTimestamp(record.timestamp),
            note: record.note || '', color: record.colour || '#fdd835', metrics: JSON.parse(record.metrics || record.metrics_json || '{}') }))
            .filter(marker => Number.isFinite(marker.timestamp));
        const categories = app.annotationModel.normalizeCatalog(metadata.categories || [
            ...app.annotationModel.DEFAULT_CATEGORIES,
            ...records.map(record => ({ id: record.category, label: record.category_label || record.category, color: '#1e88e5' }))
        ]);
        return { regions, markers, categories, metadata, mergedCount: 0 };
    }

    app.annotationCsv = { buildAnnotationsCsv, parseAnnotationsCsv, parseCsvRows, readSection,
        REGION_FIELDS, PROVENANCE_FIELDS, OVERALL_FIELDS, SPECTRAL_FIELDS, MARKER_FIELDS };
})(window.NoiseSurveyApp);
