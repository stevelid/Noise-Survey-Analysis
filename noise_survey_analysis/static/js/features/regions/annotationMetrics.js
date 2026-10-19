/** Browser metric engine. Mirrors core/annotation_metrics.py; inputs are source-time samples. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    const MS_PER_SECOND = 1000;
    const COVERAGE_TOLERANCE = 1e-6;
    const DEFAULT_BACKGROUND_WINDOW_S = 300;
    const DEFAULT_MIN_CONTEXT_S = 60;
    const finite = value => value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value));
    const number = value => finite(value) ? Number(value) : NaN;
    const geometryCache = new WeakMap();
    const seriesCache = new WeakMap();

    function union(areas) {
        const sorted = (areas || []).map(area => Array.isArray(area)
            ? { start: number(area[0]), end: number(area[1]) } : { start: number(area?.start), end: number(area?.end) })
            .filter(area => Number.isFinite(area.start) && Number.isFinite(area.end) && area.start !== area.end)
            .map(area => ({ start: Math.min(area.start, area.end), end: Math.max(area.start, area.end) }))
            .sort((left, right) => left.start - right.start || left.end - right.end);
        const result = [];
        sorted.forEach(area => {
            const last = result.at(-1);
            if (last && area.start <= last.end) last.end = Math.max(last.end, area.end);
            else result.push({ ...area });
        });
        return result;
    }

    function subtract(areas, exclusions) {
        let result = union(areas);
        union(exclusions).forEach(({ start: low, end: high }) => {
            result = result.flatMap(({ start, end }) => {
                if (high <= start || low >= end) return [{ start, end }];
                return [...(start < low ? [{ start, end: low }] : []), ...(high < end ? [{ start: high, end }] : [])];
            });
        });
        return result;
    }

    function median(values) {
        if (!values.length) return 0;
        const sorted = values.slice().sort((a, b) => a - b);
        const middle = Math.floor(sorted.length / 2);
        return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
    }

    function geometry(timestamps, nominalMs) {
        const cacheable = timestamps && typeof timestamps === 'object';
        const key = `${nominalMs || 0}:${timestamps?.length || 0}:${timestamps?.[0]}:${timestamps?.[timestamps.length - 1]}`;
        const cached = cacheable ? geometryCache.get(timestamps) : null;
        if (cached?.key === key) return cached.value;
        const entries = Array.from(timestamps || [], (value, index) => ({ time: number(value), index }))
            .filter(entry => Number.isFinite(entry.time)).sort((a, b) => a.time - b.time);
        const rows = entries.filter((entry, index) => !index || entry.time !== entries[index - 1].time);
        const differences = rows.slice(1).map((entry, index) => entry.time - rows[index].time).filter(value => value > 0);
        const interval = nominalMs > 0 ? nominalMs : median(differences);
        const value = { rows, interval, ends: rows.map((row, index) => Math.min(rows[index + 1]?.time ?? row.time + interval, row.time + interval)) };
        if (cacheable) geometryCache.set(timestamps, { key, value });
        return value;
    }

    function sliceGeometry(geom, areas) {
        const selected = new Set();
        union(areas).forEach(area => {
            let low = 0, high = geom.rows.length;
            while (low < high) {
                const mid = (low + high) >>> 1;
                if (geom.ends[mid] <= area.start) low = mid + 1;
                else high = mid;
            }
            for (let index = low; index < geom.rows.length && geom.rows[index].time < area.end; index++) selected.add(index);
        });
        const indices = [...selected].sort((a, b) => a - b);
        return { interval: geom.interval, rows: indices.map(index => geom.rows[index]), ends: indices.map(index => geom.ends[index]) };
    }

    function columnSeries(data, name, nominalMs) {
        if (!data?.Datetime || !data?.[name]) return { rows: [], ends: [], interval: 0 };
        let columns = seriesCache.get(data);
        if (!columns) { columns = new Map(); seriesCache.set(data, columns); }
        const previous = columns.get(name);
        if (previous?.times === data.Datetime && previous?.values === data[name] && previous?.nominalMs === nominalMs) return previous.geom;
        const indices = [];
        Array.from(data.Datetime).forEach((time, index) => { if (finite(time) && finite(data[name][index])) indices.push(index); });
        const nativeTimes = indices.map(index => data.Datetime[index]);
        let interval = nominalMs;
        if (!(interval > 0)) {
            const baseInterval = geometry(data.Datetime).interval;
            const inferred = geometry(nativeTimes).interval;
            // Two sparse finite values do not prove a slower native cadence.
            // Require two agreeing intervals before inferring a column period
            // slower than the raw grid; explicit metadata always takes priority.
            const differences = nativeTimes.slice(1).map((time, index) => time - nativeTimes[index]);
            const agreeing = differences.filter(value => Math.abs(value - inferred) <= COVERAGE_TOLERANCE * Math.max(1, inferred)).length;
            const slowerProven = agreeing >= 2 && agreeing >= differences.length / 2;
            interval = baseInterval > 0 && inferred > baseInterval && !slowerProven
                ? baseInterval : inferred || baseInterval;
        }
        const raw = geometry(nativeTimes, interval);
        const geom = { ...raw, rows: raw.rows.map(row => ({ ...row, index: indices[row.index] })) };
        columns.set(name, { times: data.Datetime, values: data[name], nominalMs, geom });
        return geom;
    }

    function intersection(left, right) {
        const a = union(left), b = union(right), result = [];
        let i = 0, j = 0;
        while (i < a.length && j < b.length) {
            const start = Math.max(a[i].start, b[j].start), end = Math.min(a[i].end, b[j].end);
            if (start < end) result.push({ start, end });
            if (a[i].end < b[j].end) i++; else j++;
        }
        return result;
    }

    function weights(sampleGeometry, areas) {
        const intervals = union(areas);
        return sampleGeometry.rows.map((row, index) => intervals.reduce((total, area) =>
            total + Math.max(0, Math.min(sampleGeometry.ends[index], area.end) - Math.max(row.time, area.start)) / MS_PER_SECOND, 0));
    }

    function energy(values, durations) {
        let maximum = -Infinity;
        values.forEach((value, index) => { if (finite(value) && durations[index] > 0) maximum = Math.max(maximum, Number(value)); });
        if (!Number.isFinite(maximum)) return null;
        let sum = 0, duration = 0;
        values.forEach((value, index) => {
            if (finite(value) && durations[index] > 0) {
                sum += 10 ** ((Number(value) - maximum) / 10) * durations[index];
                duration += durations[index];
            }
        });
        return duration ? maximum + 10 * Math.log10(sum / duration) : null;
    }

    function percentile(values, durations, quantile = 0.1) {
        const rows = values.map((value, index) => ({ value: number(value), weight: durations[index] }))
            .filter(row => Number.isFinite(row.value) && row.weight > 0).sort((a, b) => a.value - b.value);
        const threshold = rows.reduce((sum, row) => sum + row.weight, 0) * quantile;
        let cumulative = 0;
        for (const row of rows) { cumulative += row.weight; if (cumulative >= threshold) return row.value; }
        return null;
    }

    function maximum(values, durations) {
        let result = -Infinity;
        values.forEach((value, index) => { if (finite(value) && durations[index] > 0) result = Math.max(result, Number(value)); });
        return Number.isFinite(result) ? result : null;
    }

    function contextAreas(region, regions, meter, windowSeconds = DEFAULT_BACKGROUND_WINDOW_S) {
        const areas = union(region.areas || [region]);
        const width = windowSeconds * MS_PER_SECOND;
        const context = areas.flatMap(area => [{ start: area.start - width, end: area.start }, { start: area.end, end: area.end + width }]);
        const exclusions = regions.filter(item => item.positionId === meter || item.meterStates?.[meter] === 'present')
            .flatMap(item => item.areas || [item]);
        return subtract(context, [...areas, ...exclusions]);
    }

    function computeSamples(data, areas, options = {}) {
        const displayAreas = union(areas);
        const offset = Number(options.chartOffsetMs) || 0;
        const sourceAreas = displayAreas.map(area => ({ start: area.start - offset, end: area.end - offset }));
        const sourceContext = (options.contextAreas || []).map(area => ({ start: area.start - offset, end: area.end - offset }));
        const nominal = Number(options.sampleIntervalS) * MS_PER_SECOND || 0;
        const duration = displayAreas.reduce((total, area) => total + area.end - area.start, 0) / MS_PER_SECOND;
        const series = name => {
            const native = Number(options.columnSampleIntervalsS?.[name]) * MS_PER_SECOND || nominal;
            return sliceGeometry(columnSeries(data, name, native), [...sourceAreas, ...sourceContext]);
        };
        const eq = series('LAeq');
        const max = series('LAFmax');
        const percentileCandidates = ['LAF', 'LAFp', 'LAeq', 'LAF90'];
        const percentileColumn = percentileCandidates.find(name => weights(series(name), sourceAreas).some(value => value > 0))
            || percentileCandidates.find(name => series(name).rows.length);
        const pct = percentileColumn ? series(percentileColumn) : { rows: [], ends: [], interval: 0 };
        const values = (geom, field) => geom.rows.map(row => number(data?.[field]?.[row.index]));
        const eqWeights = weights(eq, sourceAreas);
        const resolution = options.resolution || 'log';
        const indicative = resolution !== 'log' || pct.interval >= MS_PER_SECOND || !['LAF', 'LAFp'].includes(percentileColumn);
        const result = {
            dataResolution: resolution, sampleIntervalS: eq.interval / MS_PER_SECOND || null,
            coverage: duration ? Math.min(1, eqWeights.reduce((a, b) => a + b, 0) / duration) : 0,
            laeq: energy(values(eq, 'LAeq'), eqWeights), lafmax: maximum(values(max, 'LAFmax'), weights(max, sourceAreas)),
            la90: percentileColumn ? percentile(values(pct, percentileColumn), weights(pct, sourceAreas)) : null,
            backgroundLA90: null, backgroundLAeq: null, diffFromBackground: null, contextDurationS: 0,
            percentileMethod: percentileColumn ? `duration-weighted inverse-CDF p10 of ${percentileColumn}${indicative ? '; indicative' : ''}` : 'unavailable',
            missingReasons: [], durationMs: duration * MS_PER_SECOND, chartOffsetMs: offset, sourceAreas,
        };
        result.lafmaxAvailable = result.lafmax !== null;
        result.la90Available = resolution === 'log' && result.la90 !== null;
        if (sourceContext.length && percentileColumn) {
            // Broadband/fast levels can have different cadences. Intersect their
            // usable support first so background LA90 and LAeq describe exactly
            // the same pooled context time, without interpolation across gaps.
            const support = geom => geom.rows.map((row, index) => ({ start: row.time, end: geom.ends[index] }));
            const usable = intersection(sourceContext, intersection(support(eq), support(pct)));
            result.contextDurationS = usable.reduce((sum, area) => sum + (area.end - area.start) / MS_PER_SECOND, 0);
            const minimum = options.minContextS ?? DEFAULT_MIN_CONTEXT_S;
            if (result.contextDurationS + COVERAGE_TOLERANCE >= minimum) {
                result.backgroundLA90 = percentile(values(pct, percentileColumn), weights(pct, usable));
                result.backgroundLAeq = energy(values(eq, 'LAeq'), weights(eq, usable));
            } else result.missingReasons.push(`Background context below ${minimum} usable seconds`);
        }
        if (result.laeq !== null && result.backgroundLA90 !== null) result.diffFromBackground = result.laeq - result.backgroundLA90;
        if (result.laeq === null) result.missingReasons.push('LAeq column unavailable or contains no finite region samples');
        if (result.lafmax === null) result.missingReasons.push('Genuine LAFmax column unavailable');
        if (result.coverage < 1 - COVERAGE_TOLERANCE) result.missingReasons.push('Requested area has incomplete timestamp coverage');
        return result;
    }

    function spectrum(prepared, areas, options = {}) {
        if (!prepared) return { labels: [], values: [] };
        const offset = Number(options.chartOffsetMs) || 0;
        const sourceAreas = union(areas).map(area => ({ start: area.start - offset, end: area.end - offset }));
        const geom = sliceGeometry(geometry(prepared.times_ms, Number(prepared.time_step)), sourceAreas);
        const durations = weights(geom, sourceAreas);
        const labels = Array.from(prepared.frequency_labels || []);
        const parameter = options.parameter || 'LZeq';
        const aggregate = /max/i.test(parameter) ? maximum : /90$/.test(parameter) ? percentile : energy;
        const duration = union(areas).reduce((sum, area) => sum + (area.end - area.start) / MS_PER_SECOND, 0);
        return { labels, sampleIntervalS: geom.interval / MS_PER_SECOND || null,
            coverage: duration ? Math.min(1, durations.reduce((sum, value) => sum + value, 0) / duration) : 0,
            values: labels.map((_, frequency) => aggregate(geom.rows.map(row =>
                number(prepared.levels_flat_transposed?.[frequency * prepared.n_times + row.index])), durations)) };
    }

    function unwrap(value) {
        return Array.isArray(value?.[0]) || ArrayBuffer.isView(value?.[0]) ? value[0] : value;
    }

    function streamedSpectrum(models, meter) {
        const data = models?.spectrogramSources?.[meter]?.log?.data;
        if (!data) return null;
        const times = unwrap(data.times_ms), levels = unwrap(data.levels_flat_transposed);
        const labels = unwrap(data.frequency_labels);
        const nTimes = Number(data.n_times?.[0] ?? times?.length);
        if (!times?.length || !labels?.length || !levels || !nTimes || levels.length < nTimes * labels.length) return null;
        return { parameter: data.parameter?.[0] || data.param?.[0], times_ms: times, levels_flat_transposed: levels,
            n_times: nTimes, n_freqs: labels.length, frequency_labels: labels, time_step: Number(data.time_step?.[0]) || 0 };
    }

    function computeRegion(region, state, models, options = {}) {
        const meter = options.positionId || options.meterId || region.positionId;
        const offset = Number(state?.view?.positionChartOffsets?.[meter]) || 0;
        const areas = union(region.areas || [region]);
        const regions = (state?.regions?.allIds || []).map(id => state.regions.byId[id]).filter(Boolean);
        const backgroundWindow = options.backgroundWindowS ?? state?.annotationPanel?.backgroundWindowS ?? DEFAULT_BACKGROUND_WINDOW_S;
        const context = contextAreas(region, regions, meter, backgroundWindow);
        const requested = options.resolution || 'auto';
        const candidates = requested === 'auto' ? ['log', 'overview'] : [requested];
        let metrics = null, partialLog = null;
        for (const resolution of candidates) {
            const data = models?.timeSeriesSources?.[meter]?.[resolution]?.data;
            if (!data?.Datetime?.length) continue;
            const value = computeSamples(data, areas, { resolution, chartOffsetMs: offset, contextAreas: context,
                minContextS: options.minContextS ?? state?.annotationPanel?.minContextS ?? DEFAULT_MIN_CONTEXT_S,
                sampleIntervalS: options.sampleIntervalS, columnSampleIntervalsS: options.columnSampleIntervalsS });
            const usable = value.laeq !== null || value.lafmax !== null || value.la90 !== null;
            if (requested !== 'auto') { metrics = value; break; }
            if (!usable) continue;
            // Prefer complete log, then overview. Retain usable partial log or
            // maximum/percentile-only data as an explicitly labelled last resort.
            if (resolution === 'log' && (value.laeq === null || value.coverage < 1 - COVERAGE_TOLERANCE)) {
                partialLog = value;
                continue;
            }
            metrics = value; break;
        }
        metrics ||= partialLog;
        if (!metrics) metrics = computeSamples({}, areas, { resolution: requested === 'auto' ? 'none' : requested, chartOffsetMs: offset });
        const streamed = streamedSpectrum(models, meter);
        const preparedByResolution = Object.fromEntries(['log', 'overview'].map(resolution => [resolution,
            models?.preparedGlyphData?.[meter]?.[resolution]?.prepared_params || {}]));
        const names = new Set([...Object.keys(preparedByResolution.log), ...Object.keys(preparedByResolution.overview)]);
        if (streamed?.parameter) names.add(streamed.parameter);
        const requestedParameter = options.parameter || state?.view?.selectedParameter || 'LZeq';
        metrics.spectra = {};
        names.forEach(name => {
            let selected = null, partialLogSpectrum = null;
            const resolutions = requested === 'auto' ? ['log', 'overview'] : [requested];
            for (const resolution of resolutions) {
                const candidates = [resolution === 'log' && streamed?.parameter === name ? streamed : null, preparedByResolution[resolution]?.[name]].filter(Boolean);
                for (const candidate of candidates) {
                    const value = spectrum(candidate, areas, { chartOffsetMs: offset, parameter: name });
                    if (!value.values.some(Number.isFinite)) continue;
                    const result = { ...value, source: resolution,
                        missingReasons: value.coverage < 1 - COVERAGE_TOLERANCE ? ['Spectral area has incomplete timestamp coverage'] : [] };
                    if (requested === 'auto' && resolution === 'log' && value.coverage < 1 - COVERAGE_TOLERANCE) {
                        if (!partialLogSpectrum || result.coverage > partialLogSpectrum.coverage) partialLogSpectrum = result;
                        continue;
                    }
                    selected = result;
                    break;
                }
                if (selected) break;
            }
            if (selected || partialLogSpectrum) metrics.spectra[name] = selected || partialLogSpectrum;
        });
        const parameter = metrics.spectra[requestedParameter] ? requestedParameter : (metrics.spectra.LZeq ? 'LZeq' : requestedParameter);
        metrics.spectrum = metrics.spectra[parameter] || { labels: [], values: [], source: null };
        metrics.parameter = requestedParameter;
        metrics.spectrumParameter = parameter;
        return metrics;
    }

    app.annotationMetrics = { union, subtract, geometry, weights, energy, percentile, maximum,
        contextAreas, computeSamples, spectrum, computeRegion, streamedSpectrum, sliceGeometry, columnSeries, intersection };
})(window.NoiseSurveyApp);
