/** Business intents shared by delegated HTML controls; no DOM access. */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';
    const feature = app.features.annotationPanel;
    function flushNoteDraft(dispatch, getState, draft) {
        if (!draft || typeof draft.value !== 'string') return;
        const id = Number(draft.id);
        if (!Number.isFinite(id)) return;
        const state = getState();
        if (draft.command === 'region-note') {
            const region = state.regions.byId[id];
            if (region && (region.note || '') !== draft.value) {
                dispatch(app.features.regions.thunks.saveRegionNoteIntent(id, draft.value));
            }
        } else if (draft.command === 'marker-note') {
            const marker = state.markers.byId[id];
            if (marker && (marker.note || '') !== draft.value) dispatch(app.actions.markerSetNote(id, draft.value));
        }
    }
    function panelCommandIntent(command, payload = {}) {
        return function (dispatch, getState) {
            // Resolve the click against fresh state after saving the previous
            // annotation, including commands that merge or delete that record.
            flushNoteDraft(dispatch, getState, payload.draft);
            const state = getState();
            const actions = app.actions;
            const regionThunks = app.features.regions.thunks;
            const markerThunks = app.features.markers.thunks;
            const classificationThunks = app.features.classifications.thunks;
            const selectors = feature.selectors;
            const region = app.features.regions.selectors.selectSelectedRegion(state);
            const id = Number(payload.id);
            const setPanel = changes => dispatch(feature.actions.panelSettingsChanged(changes));
            switch (command) {
                case 'commit-note-draft': break; // The validated draft was saved above.
                case 'tab': dispatch(actions.setActiveSidePanelTab(Number(payload.value))); break;
                case 'filter': {
                    const allowed = ['categoryId', 'presentAt', 'onlyOneMeter', 'hasUnchecked'];
                    if (allowed.includes(payload.field)) setPanel({ filters: { [payload.field]: payload.value } });
                    break;
                }
                case 'select-region': dispatch(regionThunks.selectRegionIntent(id)); break;
                case 'cycle-meter': dispatch(regionThunks.cycleRegionMeterStateIntent(id, payload.meter)); break;
                case 'region-category': dispatch(regionThunks.setRegionCategoryIntent(id, payload.value)); break;
                case 'region-note': dispatch(regionThunks.saveRegionNoteIntent(id, payload.value)); break;
                case 'region-color': dispatch(actions.regionSetColor(id, app.annotationModel.normalizeColor(payload.value))); break;
                case 'delete-region': if (region) dispatch(actions.regionRemove(region.id)); break;
                case 'centre-region': dispatch(regionThunks.centerViewportOnSelectedRegionIntent()); break;
                case 'back': dispatch(regionThunks.returnToPreviousRegionViewIntent()); break;
                case 'add-area': dispatch(actions.regionSetAddAreaMode(state.regions.addAreaTargetId ? null : region?.id)); break;
                case 'merge-region': if (Number.isFinite(id)) dispatch(regionThunks.mergeRegionIntoSelectedIntent(id)); break;
                case 'split-region': dispatch(regionThunks.splitSelectedRegionIntent()); break;
                case 'auto-periods': dispatch(regionThunks.createAutoRegionsIntent()); break;
                case 'ghost-mode': dispatch(regionThunks.setRegionGhostModeIntent(payload.value)); break;
                case 'annotation-visibility':
                    if (payload.field === 'regions') dispatch(actions.regionVisibilitySet({ showOverlays: Boolean(payload.value) }));
                    else if (payload.field === 'markers') dispatch(actions.markersVisibilitySet(Boolean(payload.value)));
                    else if (payload.field === 'classifications') dispatch(actions.classificationVisibilitySet({ showOverlays: Boolean(payload.value) }));
                    break;
                case 'metrics-visible': setPanel({ metricsVisible: !selectors.selectPanelState(state).metricsVisible }); break;
                case 'export-setting':
                    if (payload.field === 'includeAllResolutions') setPanel({ includeAllResolutions: Boolean(payload.value) });
                    else if (['backgroundWindowS', 'minContextS'].includes(payload.field)) {
                        const seconds = Number(payload.value);
                        if (Number.isFinite(seconds) && seconds >= 0) setPanel({ [payload.field]: seconds });
                    }
                    break;
                case 'recalculate': dispatch(regionThunks.recalculateSelectedRegionIntent()); break;
                case 'create-category': dispatch(regionThunks.createCategoryIntent({ label: payload.label, color: payload.color })); break;
                case 'update-category': dispatch(regionThunks.updateCategoryIntent({ id: payload.category, [payload.field]: payload.value })); break;
                case 'delete-category':
                    dispatch(regionThunks.deleteCategoryIntent(payload.category));
                    if (!app.features.regions.selectors.selectCategoryCatalog(getState()).byId[payload.category]
                        && selectors.selectPanelState(state).filters.categoryId === payload.category) setPanel({ filters: { categoryId: '' } });
                    break;
                case 'select-marker': dispatch(markerThunks.selectMarkerIntent(id)); break;
                case 'marker-note': dispatch(actions.markerSetNote(id, payload.value)); break;
                case 'marker-color': dispatch(actions.markerSetColor(id, app.annotationModel.normalizeColor(payload.value, '#fdd835'))); break;
                case 'delete-marker': dispatch(actions.markerRemove(id)); break;
                case 'clear-markers': setPanel({ clearMarkersPending: true }); break;
                case 'cancel-clear-markers': setPanel({ clearMarkersPending: false }); break;
                case 'confirm-clear-markers':
                    if (selectors.selectPanelState(state).clearMarkersPending) dispatch(actions.markersReplace([]));
                    setPanel({ clearMarkersPending: false }); break;
                case 'select-classification': dispatch(classificationThunks.selectClassificationIntent(id)); break;
                case 'preview-classification': dispatch(classificationThunks.previewSelectedClassificationIntent()); break;
                case 'elevate-classification': dispatch(classificationThunks.elevateClassificationToRegionIntent()); break;
                case 'classification-score': dispatch(actions.classificationMinimumScoreSet(Number(payload.value))); break;
                case 'classification-source': dispatch(actions.classificationSourceVisibilitySet(payload.source, Boolean(payload.value))); break;
                case 'classification-sources-all': dispatch(actions.classificationAllSourcesVisibilitySet(Boolean(payload.value))); break;
                case 'classification-role': dispatch(actions.classificationRoleVisibilitySet({ [payload.field]: Boolean(payload.value) })); break;
                case 'classification-sort': if (['start', 'score', 'source', 'state', 'meter'].includes(payload.value)) setPanel({ classificationSort: payload.value }); break;
                case 'comparison-meter': {
                    const included = state.view.comparison?.includedPositions || [];
                    const next = payload.value ? [...new Set([...included, payload.meter])] : included.filter(meter => meter !== payload.meter);
                    dispatch(regionThunks.updateIncludedPositionsIntent({ includedPositions: next })); break;
                }
                case 'comparison-finish': dispatch(regionThunks.exitComparisonModeIntent()); break;
                case 'comparison-create': dispatch(regionThunks.createRegionsFromComparisonIntent()); break;
                case 'copy-summary':
                case 'copy-spectrum':
                case 'copy-marker': {
                    let text = '';
                    if (command === 'copy-marker') {
                        const marker = app.features.markers.selectors.selectSelectedMarker(state);
                        if (marker) text = [new Date(marker.timestamp).toISOString(), marker.note || '', JSON.stringify(marker.metrics || {}, null, 2)].join('\n');
                    } else if (region) {
                        const metrics = app.regions.getRegionMetrics(region, state, app.dataCache, app.registry?.models);
                        text = command === 'copy-spectrum' ? app.regions.formatSpectrumClipboardText(metrics.spectrum)
                            : app.regions.formatRegionSummary(region, metrics, selectors.selectMeterTitle(state, region.positionId));
                    }
                    if (text && globalThis.navigator?.clipboard?.writeText) {
                        return navigator.clipboard.writeText(text).then(() => dispatch(actions.noticeShown('Copied to clipboard.')),
                            () => dispatch(actions.noticeShown('Clipboard access was blocked by the browser.', 'warning')));
                    }
                    dispatch(actions.noticeShown('Clipboard access is unavailable in this browser.', 'warning')); break;
                }
                default: break;
            }
        };
    }
    feature.thunks = { panelCommandIntent };
})(window.NoiseSurveyApp);
