// noise_survey_analysis/static/js/features/classifications/classificationThunks.js

/**
 * @fileoverview Thunks for selecting and elevating classifier intervals.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;

    const classificationSelectors = app.features?.classifications?.selectors || {};
    const constants = app.constants || {};
    const sidePanelTabs = constants.sidePanelTabs || {};
    const SIDE_PANEL_TAB_CLASSIFICATIONS = Number.isFinite(sidePanelTabs.classifications)
        ? sidePanelTabs.classifications
        : 2;
    const SIDE_PANEL_TAB_REGIONS = Number.isFinite(sidePanelTabs.regions)
        ? sidePanelTabs.regions
        : 0;

    const MAX_PROMOTED_BANDS = 500;

    function getChartOffsetMs(state, positionId) {
        const raw = Number(state?.view?.positionChartOffsets?.[positionId]);
        return Number.isFinite(raw) ? raw : 0;
    }

    function selectClassificationIntent(classificationId) {
        return function (dispatch) {
            if (!actions || typeof dispatch !== 'function') {
                return;
            }
            const id = Number(classificationId);
            if (!Number.isFinite(id)) {
                dispatch(actions.classificationClearSelection());
                return;
            }
            dispatch(actions.classificationSelect(id));
            if (typeof actions.regionClearSelection === 'function') {
                dispatch(actions.regionClearSelection());
            }
            if (typeof actions.markerSelect === 'function') {
                dispatch(actions.markerSelect(null));
            }
            if (typeof actions.setActiveSidePanelTab === 'function') {
                dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_CLASSIFICATIONS));
            }
        };
    }

    function buildRegionNoteFromClassification(classification) {
        if (!classification) {
            return '';
        }
        const parts = [];
        const label = classification.sourceLabel || classification.sourceId || 'Classification';
        parts.push(label);
        if (classification.state && classification.state !== 'on') {
            parts.push(`state: ${classification.state}`);
        }
        if (Number.isFinite(classification.confidence)) {
            parts.push(`confidence: ${Math.round(classification.confidence * 100)}%`);
        }
        if (classification.description) {
            parts.push(classification.description);
        }
        if (classification.audioFile) {
            parts.push(`audio: ${classification.audioFile}`);
        }
        return parts.join(' | ');
    }

    function elevateClassificationToRegionIntent(classificationId = null) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') {
                return;
            }
            const state = getState();
            const classification = classificationId !== null && Number.isFinite(Number(classificationId))
                ? classificationSelectors.selectClassificationById?.(state, Number(classificationId))
                : classificationSelectors.selectSelectedClassification?.(state);
            if (!classification) {
                return;
            }
            if (!classification.positionId || !Number.isFinite(classification.start) || !Number.isFinite(classification.end)) {
                return;
            }
            // Regions store display time (what the chart shows), i.e. source time plus
            // the position's chart offset - the same shift the classification bands get.
            const chartOffsetMs = getChartOffsetMs(state, classification.positionId);
            const displayStart = classification.start + chartOffsetMs;
            const displayEnd = classification.end + chartOffsetMs;
            const nextRegionId = Number.isFinite(state?.regions?.counter) ? state.regions.counter : null;
            const label = classification.sourceLabel || classification.sourceId || 'Classification';
            const catalog = state?.regions?.categories;
            let categoryId = catalog?.allIds?.find(id => catalog.byId[id]?.label?.toLowerCase() === label.toLowerCase());
            if (!categoryId && app.features?.regions?.thunks?.createCategoryIntent) {
                categoryId = dispatch(app.features.regions.thunks.createCategoryIntent({ label, color: classification.color }));
            }
            const meterStates = app.annotationModel?.normalizeMeterStates(
                { positionId: classification.positionId }, state?.view?.availablePositions || []
            ) || { [classification.positionId]: 'present' };
            const region = {
                positionId: classification.positionId,
                start: displayStart,
                end: displayEnd,
                areas: [{ start: displayStart, end: displayEnd }],
                note: buildRegionNoteFromClassification(classification),
                categoryId: categoryId || 'other',
                color: categoryId ? null : classification.color,
                meterStates
            };
            dispatch(actions.regionsAdded([region]));
            if (Number.isFinite(nextRegionId)) {
                dispatch(actions.classificationUpdate(classification.id, { elevatedRegionId: nextRegionId }));
                const selectRegion = app.features?.regions?.thunks?.selectRegionIntent;
                if (typeof selectRegion === 'function') {
                    dispatch(selectRegion(nextRegionId));
                } else {
                    dispatch(actions.regionSelect(nextRegionId));
                    dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_REGIONS));
                }
            } else if (typeof actions.setActiveSidePanelTab === 'function') {
                dispatch(actions.setActiveSidePanelTab(SIDE_PANEL_TAB_REGIONS));
            }
            app.regions?.invalidateMetricsCache?.();
        };
    }

    const CLASSIFICATION_PRE_ROLL_MS = 1000;
    const CLASSIFICATION_PREVIEW_MAX_PRESERVE_MS = 120000;
    const CLASSIFICATION_PREVIEW_WINDOW_MS = 60000;

    function previewSelectedClassificationIntent() {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') {
                return;
            }
            const state = getState();
            const selectors = app.features?.classifications?.selectors || classificationSelectors;
            const selected = selectors.selectSelectedClassification?.(state);
            if (!selected) {
                return;
            }

            // Work in display time: the viewport and tap cursor are in display time, and
            // the audio side effect converts the tap back to the true audio time by
            // removing the position's effective offset.
            const chartOffsetMs = getChartOffsetMs(state, selected.positionId);
            const startMs = Number(selected.start) + chartOffsetMs;
            const endMs = Number(selected.end) + chartOffsetMs;
            if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) {
                return;
            }

            // 1. Calculate seek target timestamp (1.0s pre-roll)
            const seekTimestamp = Math.max(0, startMs - CLASSIFICATION_PRE_ROLL_MS);

            // 2. Viewport calculation
            // Viewport bounds live at state.view.viewport.{min,max} (see viewReducer's
            // initialViewState) — not state.view.{min,max}.
            const midpoint = (startMs + endMs) / 2;
            const currentViewMin = Number(state?.view?.viewport?.min);
            const currentViewMax = Number(state?.view?.viewport?.max);
            let windowWidth = CLASSIFICATION_PREVIEW_WINDOW_MS;

            if (Number.isFinite(currentViewMin) && Number.isFinite(currentViewMax) && currentViewMax > currentViewMin) {
                const currentWidth = currentViewMax - currentViewMin;
                if (currentWidth <= CLASSIFICATION_PREVIEW_MAX_PRESERVE_MS) {
                    windowWidth = currentWidth;
                }
            }

            const halfWidth = windowWidth / 2;
            const newMin = Math.max(0, midpoint - halfWidth);
            const newMax = newMin + windowWidth;

            // 3. Dispatch viewport change if needed
            if (typeof actions.viewportChange === 'function') {
                dispatch(actions.viewportChange(newMin, newMax));
            }

            // 4. Dispatch tap to seek
            if (typeof actions.tap === 'function') {
                dispatch(actions.tap(seekTimestamp, selected.positionId, 'classification_preview'));
            }

            // 5. Start audio playback.
            // Audio state exposes `isPlaying` (boolean) and `activePositionId` —
            // there is no `status` string. Only dispatch a toggle when it will
            // actually change something: either audio is stopped, or it is playing
            // a different position and needs to switch. Re-toggling audio that is
            // already playing this position would restart/interrupt it.
            const isPlaying = Boolean(state?.audio?.isPlaying);
            const activePositionId = state?.audio?.activePositionId ?? null;
            const needsAudioChange = !isPlaying || activePositionId !== selected.positionId;
            if (needsAudioChange && typeof actions.audioPlayPauseToggle === 'function') {
                dispatch(actions.audioPlayPauseToggle(selected.positionId, true));
            }
        };
    }

    /**
     * Turn the classification bands currently shown (after the score/source/role filters) into proposed
     * regions for review, in one undo step. Times become display time (source time plus the chart offset);
     * the detector score becomes the confidence. Bands already promoted (same meter and times) are skipped,
     * as are "off" intervals. Returns the number of regions added.
     * At most MAX_PROMOTED_BANDS are promoted per call (a toast says so; run it again for the rest).
     */
    function promoteShownToSuggestionsIntent() {
        // Category creation plus the region batch is one undo step.
        return function (dispatch, getState) {
            return app.history?.batch ? app.history.batch(() => promoteShown(dispatch, getState)) : promoteShown(dispatch, getState);
        };
    }

    function promoteShown(dispatch, getState) {
        {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') return 0;
            const state = getState();
            const shown = (classificationSelectors.selectVisibleClassifications?.(state) || [])
                .filter(entry => entry.positionId && Number.isFinite(entry.start) && Number.isFinite(entry.end)
                    && entry.start < entry.end && String(entry.state || 'on').toLowerCase() !== 'off');
            // Dedupe on source time (display time minus the chart offset) so a later offset change cannot duplicate a band.
            const existing = new Set(Object.values(state.regions.byId)
                .filter(region => region.source === 'agent')
                .map(region => {
                    const shift = getChartOffsetMs(state, region.positionId);
                    return `${region.positionId}|${region.start - shift}|${region.end - shift}`;
                }));
            const positions = state?.view?.availablePositions || [];
            const stamp = new Date().toISOString();
            const regions = [];
            let capped = false;
            shown.forEach(entry => {
                const offset = getChartOffsetMs(state, entry.positionId);
                const start = entry.start + offset;
                const end = entry.end + offset;
                const key = `${entry.positionId}|${entry.start}|${entry.end}`;
                if (existing.has(key)) return;
                if (regions.length >= MAX_PROMOTED_BANDS) { capped = true; return; }
                existing.add(key);
                const label = entry.sourceLabel || entry.sourceId || 'Classification';
                const catalog = getState().regions.categories;
                let categoryId = catalog?.allIds?.find(id => catalog.byId[id]?.label?.toLowerCase() === label.toLowerCase());
                if (!categoryId && app.features?.regions?.thunks?.createCategoryIntent) {
                    categoryId = dispatch(app.features.regions.thunks.createCategoryIntent({ label, color: entry.color }));
                }
                const score = Number.isFinite(entry.confidence) ? entry.confidence : null;
                regions.push({
                    positionId: entry.positionId, start, end, areas: [{ start, end }],
                    note: buildRegionNoteFromClassification(entry),
                    categoryId: categoryId || 'other', categoryIds: [categoryId || 'other'],
                    meterStates: app.annotationModel.normalizeMeterStates({ positionId: entry.positionId }, positions),
                    ...app.annotationModel.pickReviewMeta({
                        source: 'agent', status: 'proposed', agent: { name: 'yamnet', runId: null }, createdAt: stamp,
                        confidence: score,
                        rationale: `Detector band "${label}"${score === null ? '' : ` scored ${score.toFixed(2)}`}${entry.description ? `: ${entry.description}` : ''}`
                    })
                });
            });
            if (!regions.length) {
                dispatch(actions.noticeShown('No new classification bands to promote.'));
                return 0;
            }
            const before = getState().regions;
            dispatch(actions.regionsAdded(regions));
            // Adding selects the last region; leave the user's selection as it was.
            if (before.selectedId !== getState().regions.selectedId) {
                dispatch(before.byId[before.selectedId] ? actions.regionSelect(before.selectedId) : actions.regionClearSelection());
            }
            app.regions?.invalidateMetricsCache?.();
            dispatch(actions.noticeShown(`Promoted ${regions.length} classification band${regions.length === 1 ? '' : 's'} to suggestions. Review them in the Regions tab.${capped ? ` Limited to ${MAX_PROMOTED_BANDS} at a time; promote again for the rest.` : ''}`));
            return regions.length;
        }
    }

    app.features = app.features || {};
    app.features.classifications = app.features.classifications || {};
    app.features.classifications.thunks = {
        promoteShownToSuggestionsIntent,
        selectClassificationIntent,
        elevateClassificationToRegionIntent,
        previewSelectedClassificationIntent,
        buildRegionNoteFromClassification,
        CLASSIFICATION_PRE_ROLL_MS,
        CLASSIFICATION_PREVIEW_MAX_PRESERVE_MS,
        CLASSIFICATION_PREVIEW_WINDOW_MS
    };
})(window.NoiseSurveyApp);
