/** Comparison adapter: all acoustic calculations use annotationMetrics. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    function processComparisonSliceMetrics(options = {}) {
        const start = Number(options.start), end = Number(options.end);
        const positions = Array.isArray(options.positionIds) ? options.positionIds : [];
        if (!Number.isFinite(start) || !Number.isFinite(end) || start === end || !positions.length) {
            return { start: null, end: null, metricsRows: [], spectrum: { labels: [], series: [] }, hasData: false };
        }
        const bounds = { start: Math.min(start, end), end: Math.max(start, end) };
        const engine = app.annotationMetrics;
        if (!engine) throw new Error('Annotation metrics engine is not loaded.');
        const state = options.state || { view: { selectedParameter: options.selectedParameter,
            positionChartOffsets: options.positionChartOffsets || {} } };
        const models = options.models || { timeSeriesSources: options.timeSeriesSources || {},
            preparedGlyphData: options.preparedGlyphData || {}, spectrogramSources: options.spectrogramSources || {} };
        const selectedParameter = options.selectedParameter || state.view?.selectedParameter || 'LAeq';
        const metricsRows = [], spectra = [];
        let hasData = false;
        positions.forEach(positionId => {
            const region = { positionId, areas: [bounds] };
            const metrics = engine.computeRegion(region, state, models, { parameter: selectedParameter, resolution: 'auto' });
            let dataset = metrics.dataResolution;
            let data = models.timeSeriesSources?.[positionId]?.[dataset]?.data;
            // Generic line-only sources still have a meaningful selected value,
            // even when standard acoustic LAeq/LAFmax metrics are unavailable.
            if (!data) {
                dataset = ['log', 'overview'].find(name => {
                    const source = models.timeSeriesSources?.[positionId]?.[name]?.data;
                    const geom = engine.columnSeries(source, selectedParameter, 0);
                    const durations = engine.weights(geom, metrics.sourceAreas);
                    const coverage = durations.reduce((sum, value) => sum + value, 0) * 1000 / metrics.durationMs;
                    return geom.rows.length && (name !== 'log' || coverage >= 1 - 1e-6);
                }) || 'none';
                data = models.timeSeriesSources?.[positionId]?.[dataset]?.data;
            }
            const broadbandParam = data?.[selectedParameter] ? selectedParameter : 'LAeq';
            const geom = engine.sliceGeometry(engine.columnSeries(data, broadbandParam, 0), metrics.sourceAreas);
            const durations = engine.weights(geom, metrics.sourceAreas);
            const values = geom.rows.map(row => data[broadbandParam][row.index]);
            const aggregate = /max/i.test(broadbandParam) ? engine.maximum : /90$/.test(broadbandParam) ? engine.percentile : engine.energy;
            const broadbandValue = aggregate(values, durations);
            const spectrum = metrics.spectrum;
            spectra.push({ positionId, dataset: spectrum.source || dataset, labels: spectrum.labels, values: spectrum.values });
            metricsRows.push({ ...metrics, positionId, dataset, broadbandValue, broadbandParam });
            hasData ||= metrics.laeq !== null || metrics.lafmax !== null || broadbandValue !== null || spectrum.values.some(Number.isFinite);
        });
        const labels = [...new Set(spectra.flatMap(item => item.labels))];
        const series = spectra.map(item => ({ positionId: item.positionId, dataset: item.dataset,
            values: labels.map(label => item.labels.includes(label) ? item.values[item.labels.indexOf(label)] : null) }));
        return { ...bounds, metricsRows, spectrum: { labels, series }, hasData };
    }

    app.comparisonMetrics = { processComparisonSliceMetrics };
})(window.NoiseSurveyApp);
