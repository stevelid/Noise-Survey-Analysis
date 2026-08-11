import { describe, it, expect } from 'vitest';

import './loadCoreModules.js';
import '../noise_survey_analysis/static/js/services/classifications/classificationPanelRenderer.js';

const app = window.NoiseSurveyApp;
const { actions, actionTypes } = app;
const reducer = app.features.classifications.classificationsReducer;
const selectors = app.features.classifications.selectors;
const thunks = app.features.classifications.thunks;
const utils = app.features.classifications.utils;

describe('Classification UI Feature Suite', () => {
    it('normalizes role and handles minimum score filter in reducer', () => {
        let state = reducer(undefined, { type: '@@INIT' });
        expect(state.filters).toEqual({
            minimumScore: 0.0,
            enabledSourceIds: null,
            showDirect: true,
            showSupporting: false,
            sourceFilterExpanded: false
        });

        // Add entries with direct and supporting roles
        state = reducer(state, actions.classificationsAdded([
            { id: 1, positionId: 'P1', sourceId: 'motorcycle', start: 10000, end: 20000, confidence: 0.85, role: 'direct' },
            { id: 2, positionId: 'P1', sourceId: 'sup_engine', start: 15000, end: 25000, confidence: 0.15, description: 'supporting engine' },
            { id: 3, positionId: 'P1', sourceId: 'dog', start: 30000, end: 40000, confidence: 0.40 }
        ]));

        expect(state.byId[1].role).toBe('direct');
        expect(state.byId[2].role).toBe('supporting');
        expect(state.byId[3].role).toBe('direct');

        // Set minimum score filter
        state = reducer(state, actions.classificationMinimumScoreSet(0.50));
        expect(state.filters.minimumScore).toBe(0.50);
    });

    it('filters visible classifications correctly via selectors', () => {
        let state = {
            classifications: reducer(undefined, { type: '@@INIT' })
        };

        state.classifications = reducer(state.classifications, actions.classificationsAdded([
            { id: 1, positionId: 'P1', sourceId: 'motorcycle', start: 10000, end: 20000, confidence: 0.85, role: 'direct' },
            { id: 2, positionId: 'P1', sourceId: 'engine', start: 15000, end: 25000, confidence: 0.15, role: 'supporting' },
            { id: 3, positionId: 'P1', sourceId: 'dog', start: 30000, end: 40000, confidence: 0.40, role: 'direct' }
        ]));

        // Default: direct = on, supporting = off, minScore = 0.0 -> entries 1 and 3 visible
        let visible = selectors.selectVisibleClassifications(state);
        expect(visible.map(x => x.id)).toEqual([1, 3]);

        // Enable supporting events
        state.classifications = reducer(state.classifications, actions.classificationRoleVisibilitySet({ showSupporting: true }));
        visible = selectors.selectVisibleClassifications(state);
        expect(visible.map(x => x.id)).toEqual([1, 2, 3]);

        // Set minimum score filter = 0.50
        state.classifications = reducer(state.classifications, actions.classificationMinimumScoreSet(0.50));
        visible = selectors.selectVisibleClassifications(state);
        expect(visible.map(x => x.id)).toEqual([1]);

        // Toggle source visibility
        state.classifications = reducer(state.classifications, actions.classificationMinimumScoreSet(0.0));
        state.classifications = reducer(state.classifications, actions.classificationSourceVisibilitySet('dog', false));
        visible = selectors.selectVisibleClassifications(state);
        expect(visible.map(x => x.id)).toEqual([1, 2]);
    });

    it('stores the source-filter expansion state', () => {
        let state = reducer(undefined, { type: '@@INIT' });
        state = reducer(state, actions.classificationSourceFilterExpandedSet(true));
        expect(state.filters.sourceFilterExpanded).toBe(true);
        state = reducer(state, actions.classificationSourceFilterExpandedSet(false));
        expect(state.filters.sourceFilterExpanded).toBe(false);
    });

    it('calculates classification counts and source summaries', () => {
        let state = {
            classifications: reducer(undefined, { type: '@@INIT' })
        };

        state.classifications = reducer(state.classifications, actions.classificationsAdded([
            { id: 1, positionId: 'P1', sourceId: 'motorcycle', start: 10000, end: 20000, confidence: 0.85, role: 'direct' },
            { id: 2, positionId: 'P1', sourceId: 'engine', start: 15000, end: 25000, confidence: 0.15, role: 'supporting' }
        ]));

        const counts = selectors.selectClassificationCounts(state);
        expect(counts).toEqual({
            total: 2,
            visible: 1,
            directCount: 1,
            supportingCount: 1
        });

        const sources = selectors.selectClassificationSources(state);
        expect(sources).toHaveLength(2);
        expect(sources[0].sourceId).toBe('motorcycle');
    });

    // NOTE: these use the REAL runtime state shapes —
    //   viewport bounds: state.view.viewport.{min,max}  (see viewReducer initialViewState)
    //   audio:           state.audio.isPlaying / .activePositionId  (see audioReducer)
    // Do not "simplify" them to state.view.{min,max} or state.audio.status; those
    // fields do not exist and the thunk silently misbehaves against them.
    function runPreview(stateOverrides) {
        let classificationsState = reducer(undefined, { type: '@@INIT' });
        classificationsState = reducer(classificationsState, actions.classificationsAdded([
            { id: 1, positionId: 'P1', sourceId: 'motorcycle', start: 100000, end: 110000, confidence: 0.85 }
        ]));
        classificationsState = reducer(classificationsState, actions.classificationSelect(1));

        const mockState = { classifications: classificationsState, ...stateOverrides };
        const dispatchedActions = [];
        const dispatch = (action) => {
            if (typeof action === 'function') {
                action(dispatch, () => mockState);
            } else {
                dispatchedActions.push(action);
            }
        };
        thunks.previewSelectedClassificationIntent()(dispatch, () => mockState);
        return dispatchedActions;
    }

    it('preview collapses a wide viewport to the 60s preview window', () => {
        const dispatched = runPreview({
            view: { viewport: { min: 0, max: 300000 } },
            audio: { isPlaying: false }
        });
        const viewportAction = dispatched.find(a => a.type === actionTypes.VIEWPORT_CHANGE);
        expect(viewportAction).toBeDefined();
        // Centred on midpoint 105,000 with 60,000ms width -> [75000, 135000]
        expect(viewportAction.payload.min).toBe(75000);
        expect(viewportAction.payload.max).toBe(135000);
    });

    it('preview preserves a viewport already <= 120s wide', () => {
        const dispatched = runPreview({
            view: { viewport: { min: 60000, max: 150000 } }, // 90s wide
            audio: { isPlaying: false }
        });
        const viewportAction = dispatched.find(a => a.type === actionTypes.VIEWPORT_CHANGE);
        expect(viewportAction.payload.max - viewportAction.payload.min).toBe(90000);
    });

    it('preview seeks one second before the event start', () => {
        const dispatched = runPreview({
            view: { viewport: { min: 0, max: 300000 } },
            audio: { isPlaying: false }
        });
        const tapAction = dispatched.find(a => a.type === actionTypes.TAP);
        expect(tapAction.payload.timestamp).toBe(99000);
        expect(tapAction.payload.position).toBe('P1');
    });

    it('preview starts audio when paused', () => {
        const dispatched = runPreview({
            view: { viewport: { min: 0, max: 300000 } },
            audio: { isPlaying: false }
        });
        const audioAction = dispatched.find(a => a.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE);
        expect(audioAction).toBeDefined();
        expect(audioAction.payload.isActive).toBe(true);
    });

    it('preview does not re-toggle audio already playing the same position', () => {
        const dispatched = runPreview({
            view: { viewport: { min: 0, max: 300000 } },
            audio: { isPlaying: true, activePositionId: 'P1' }
        });
        expect(dispatched.find(a => a.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE)).toBeUndefined();
    });

    it('preview switches audio when another position is playing', () => {
        const dispatched = runPreview({
            view: { viewport: { min: 0, max: 300000 } },
            audio: { isPlaying: true, activePositionId: 'OTHER' }
        });
        const audioAction = dispatched.find(a => a.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE);
        expect(audioAction).toBeDefined();
        expect(audioAction.payload.positionId).toBe('P1');
    });

    it('preview is a no-op when nothing is selected', () => {
        const mockState = {
            classifications: reducer(undefined, { type: '@@INIT' }),
            view: { viewport: { min: 0, max: 300000 } },
            audio: { isPlaying: false }
        };
        const dispatched = [];
        const dispatch = (action) => {
            if (typeof action === 'function') action(dispatch, () => mockState);
            else dispatched.push(action);
        };
        thunks.previewSelectedClassificationIntent()(dispatch, () => mockState);
        expect(dispatched).toHaveLength(0);
    });

    it('exposes selectAreClassificationOverlaysVisible', () => {
        expect(typeof selectors.selectAreClassificationOverlaysVisible).toBe('function');
        expect(selectors.selectAreClassificationOverlaysVisible({ classifications: { overlaysVisible: false } })).toBe(false);
        expect(selectors.selectAreClassificationOverlaysVisible({ classifications: { overlaysVisible: true } })).toBe(true);
    });

    it('rehydrates a legacy workspace that predates the filters field', () => {
        const rootReducer = app.rootReducer;
        const legacy = {
            classifications: {
                byId: {}, allIds: [], selectedId: null, counter: 1,
                panelVisible: true, overlaysVisible: true
                // no `filters` key — saved before Phase 4
            }
        };
        const next = rootReducer(undefined, actions.rehydrateState(legacy));
        expect(next.classifications.filters).toEqual({
            minimumScore: 0.0,
            enabledSourceIds: null,
            showDirect: true,
            showSupporting: false,
            sourceFilterExpanded: false
        });
    });

    it('completes a partial filters object from defaults on rehydrate', () => {
        const rootReducer = app.rootReducer;
        const partial = {
            classifications: {
                byId: {}, allIds: [], selectedId: null, counter: 1,
                panelVisible: true, overlaysVisible: true,
                filters: { minimumScore: 0.42 }
            }
        };
        const next = rootReducer(undefined, actions.rehydrateState(partial));
        expect(next.classifications.filters.minimumScore).toBe(0.42);
        expect(next.classifications.filters.showDirect).toBe(true);
        expect(next.classifications.filters.showSupporting).toBe(false);
        expect(next.classifications.filters.enabledSourceIds).toBeNull();
    });

    it('renders filter controls from store state', () => {
        const renderer = app.services?.classificationPanelRenderer;
        expect(typeof renderer?.renderFilterControls).toBe('function');

        let classificationsState = reducer(undefined, { type: '@@INIT' });
        classificationsState = reducer(classificationsState, actions.classificationsAdded([
            { id: 1, positionId: 'P1', sourceId: 'motorcycle', start: 10000, end: 20000, confidence: 0.85, role: 'direct' },
            { id: 2, positionId: 'P1', sourceId: 'engine', start: 15000, end: 25000, confidence: 0.15, role: 'supporting' },
            { id: 3, positionId: 'P1', sourceId: 'dog', start: 30000, end: 40000, confidence: 0.40, role: 'direct' }
        ]));
        const state = { classifications: classificationsState };
        const counts = selectors.selectClassificationCounts(state);

        const widgets = {
            filterLayout: { visible: false },
            minimumScoreSlider: { value: 0 },
            showingCountDiv: { text: '' },
            sourceFilterToggle: { label: '', active: false },
            sourceFilterLayout: { visible: false },
            sourceCheckboxGroup: { labels: [], active: [] },
            roleFilterLayout: { visible: false },
            roleCheckboxGroup: { labels: ['Direct', 'Supporting'], active: [0] }
        };

        renderer.renderFilterControls(widgets, state, counts, true);

        expect(widgets.sourceCheckboxGroup.labels).toEqual(['motorcycle (1)', 'engine (1)', 'dog (1)']);
        expect(widgets.sourceCheckboxGroup.__sourceIds).toEqual(['motorcycle', 'engine', 'dog']);
        expect(widgets.sourceFilterLayout.visible).toBe(false);
        // supporting hidden by default -> 2 of 3
        expect(widgets.showingCountDiv.text).toBe('Showing 2 of 3');
        // supporting events exist, so the role filter must be shown
        expect(widgets.roleFilterLayout.visible).toBe(true);
        // suppression flags must not be left set, or user clicks stop dispatching
        expect(Boolean(widgets.sourceCheckboxGroup.__suppressDispatch)).toBe(false);
        expect(Boolean(widgets.roleCheckboxGroup.__suppressDispatch)).toBe(false);
    });

    it('hides the role filter when no supporting events are present', () => {
        const renderer = app.services?.classificationPanelRenderer;
        let classificationsState = reducer(undefined, { type: '@@INIT' });
        classificationsState = reducer(classificationsState, actions.classificationsAdded([
            { id: 1, positionId: 'P1', sourceId: 'motorcycle', start: 10000, end: 20000, confidence: 0.85, role: 'direct' }
        ]));
        const state = { classifications: classificationsState };
        const widgets = {
            filterLayout: { visible: false },
            roleFilterLayout: { visible: true },
            roleCheckboxGroup: { labels: ['Direct', 'Supporting'], active: [0] },
            sourceCheckboxGroup: { labels: [], active: [] },
            sourceFilterToggle: { label: '' },
            minimumScoreSlider: { value: 0 },
            showingCountDiv: { text: '' }
        };
        renderer.renderFilterControls(widgets, state, selectors.selectClassificationCounts(state), true);
        expect(widgets.roleFilterLayout.visible).toBe(false);
    });

    it('computes discrete score shading colors', () => {
        const baseColor = '#e4572e';
        const lowShade = utils.getShadedColorForScore(baseColor, 0.10);
        const midShade = utils.getShadedColorForScore(baseColor, 0.35);
        const highShade = utils.getShadedColorForScore(baseColor, 0.90);

        expect(midShade).toBe(baseColor);
        expect(lowShade).not.toBe(baseColor);
        expect(highShade).not.toBe(baseColor);
    });
});
