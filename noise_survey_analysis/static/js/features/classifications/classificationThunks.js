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
            const classification = Number.isFinite(Number(classificationId))
                ? classificationSelectors.selectClassificationById?.(state, Number(classificationId))
                : classificationSelectors.selectSelectedClassification?.(state);
            if (!classification) {
                return;
            }
            if (!classification.positionId || !Number.isFinite(classification.start) || !Number.isFinite(classification.end)) {
                return;
            }
            const nextRegionId = Number.isFinite(state?.regions?.counter) ? state.regions.counter : null;
            const region = {
                positionId: classification.positionId,
                start: classification.start,
                end: classification.end,
                areas: [{ start: classification.start, end: classification.end }],
                note: buildRegionNoteFromClassification(classification),
                color: classification.color
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

            const startMs = Number(selected.start);
            const endMs = Number(selected.end);
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

    app.features = app.features || {};
    app.features.classifications = app.features.classifications || {};
    app.features.classifications.thunks = {
        selectClassificationIntent,
        elevateClassificationToRegionIntent,
        previewSelectedClassificationIntent,
        buildRegionNoteFromClassification,
        CLASSIFICATION_PRE_ROLL_MS,
        CLASSIFICATION_PREVIEW_MAX_PRESERVE_MS,
        CLASSIFICATION_PREVIEW_WINDOW_MS
    };
})(window.NoiseSurveyApp);
