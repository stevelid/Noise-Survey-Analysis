/** Pure selectors and transient, serializable review controls for the HTML panel. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    const PANEL_CHANGED = 'annotationPanel/settingsChanged';
    const DEFAULT_BACKGROUND_WINDOW_SECONDS = 300;
    const DEFAULT_MIN_CONTEXT_SECONDS = 60;
    const DEFAULT_METRICS_VISIBLE = false;
    const DEFAULT_SPECTRUM_VISIBLE = false;
    const initialState = {
        filters: { categoryId: '', presentAt: '', onlyOneMeter: false, hasUnchecked: false },
        classificationSort: 'start', metricsVisible: DEFAULT_METRICS_VISIBLE,
        spectrumVisible: DEFAULT_SPECTRUM_VISIBLE, clearMarkersPending: false,
        backgroundWindowS: DEFAULT_BACKGROUND_WINDOW_SECONDS,
        minContextS: DEFAULT_MIN_CONTEXT_SECONDS,
        includeAllResolutions: false,
    };
    function reducer(state = initialState, action) {
        if (action.type !== PANEL_CHANGED) return state;
        const changes = action.payload || {};
        return { ...state, ...changes, filters: { ...state.filters, ...(changes.filters || {}) } };
    }
    function selectPanelState(state) {
        const panel = state?.annotationPanel || {};
        return { ...initialState, ...panel, filters: { ...initialState.filters, ...panel.filters } };
    }
    function selectPositions(state) {
        return (state?.view?.availablePositions || []).filter(id => typeof id === 'string');
    }
    function selectMeterTitle(state, id) { return state?.view?.positionDisplayTitles?.[id] || id; }
    function selectPanelData(state) {
        const regionSelectors = app.features.regions.selectors;
        const classificationSelectors = app.features.classifications.selectors;
        const ui = selectPanelState(state);
        const sorters = {
            start: (a, b) => a.start - b.start,
            score: (a, b) => (Number.isFinite(b.confidence) ? b.confidence : -1) - (Number.isFinite(a.confidence) ? a.confidence : -1),
            source: (a, b) => String(a.sourceLabel || a.sourceId).localeCompare(String(b.sourceLabel || b.sourceId)),
            state: (a, b) => String(a.state || '').localeCompare(String(b.state || '')),
            meter: (a, b) => selectMeterTitle(state, a.positionId).localeCompare(selectMeterTitle(state, b.positionId))
        };
        return {
            ui, positions: selectPositions(state),
            regions: regionSelectors.selectFilteredRegions(state, ui.filters),
            allRegions: regionSelectors.selectAllRegions(state),
            region: regionSelectors.selectSelectedRegion(state),
            categories: regionSelectors.selectCategoryCatalog(state),
            markers: app.features.markers.selectors.selectAllMarkers(state),
            marker: app.features.markers.selectors.selectSelectedMarker(state),
            classifications: classificationSelectors.selectVisibleClassifications(state).slice().sort(sorters[ui.classificationSort] || sorters.start),
            classification: classificationSelectors.selectSelectedClassification(state),
            classificationSources: classificationSelectors.selectClassificationSources(state),
            classificationCounts: classificationSelectors.selectClassificationCounts(state),
            classificationFilters: classificationSelectors.selectClassificationFilters(state)
        };
    }
    app.features = app.features || {};
    app.features.annotationPanel = {
        initialState, reducer,
        actions: { panelSettingsChanged: changes => ({ type: PANEL_CHANGED, payload: changes }) },
        selectors: { selectPanelState, selectPositions, selectMeterTitle, selectPanelData }
    };
})(window.NoiseSurveyApp);
