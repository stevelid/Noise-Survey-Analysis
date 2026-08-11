// noise_survey_analysis/static/js/chart-classes.js

/**
 * @fileoverview Defines the object-oriented classes used throughout the Noise Survey application.
 * This includes the base `Chart` class and its specialized subclasses (`TimeSeriesChart`, 
 * `SpectrogramChart`) which encapsulate the logic and state for individual plots. 
 * It also includes the `PositionController` class for managing groups of related charts.
 */
window.NoiseSurveyApp = window.NoiseSurveyApp || {};

(function (app) {
    'use strict';
    function getDebugPosition() {
        try {
            return localStorage.getItem('nsa_debug_position') || '';
        } catch (e) {
            return '';
        }
    }

    const DEFAULT_REGION_COLOR = '#1e88e5';
    const DEFAULT_REGION_FILL_ALPHA = 0.08;
    const SELECTED_REGION_FILL_ALPHA = 0.2;
    const DEFAULT_REGION_LINE_ALPHA = 0.6;
    const DEFAULT_REGION_LINE_WIDTH = 1;
    const SELECTED_REGION_LINE_WIDTH = 3;
    const DEFAULT_MARKER_COLOR = '#fdd835';
    const SELECTED_MARKER_LINE_WIDTH = 3;
    const UNSELECTED_MARKER_LINE_WIDTH = 2;
    const SELECTED_MARKER_LINE_ALPHA = 0.95;
    const UNSELECTED_MARKER_LINE_ALPHA = 0.7;
    const DEFAULT_CLASSIFICATION_FILL_ALPHA = 0.28;
    const SELECTED_CLASSIFICATION_FILL_ALPHA = 0.46;
    const OFF_CLASSIFICATION_FILL_ALPHA = 0.08;
    const CLASSIFICATION_LINE_ALPHA = 0.75;
    const OFF_CLASSIFICATION_LINE_ALPHA = 0.22;
    const SELECTED_CLASSIFICATION_LINE_ALPHA = 1.0;
    const SELECTED_CLASSIFICATION_LINE_WIDTH = 3;
    const DEFAULT_CLASSIFICATION_LINE_WIDTH = 1;
    // High-contrast outline so the selection stays obvious across all three
    // score shades (light/base/dark) of any category hue.
    const SELECTED_CLASSIFICATION_LINE_COLOR = '#ffffff';
    const OFF_CLASSIFICATION_COLOR = '#64748b';
    const FALLBACK_CLASSIFICATION_COLOR = '#2e86ab';
    // Fraction of a lane's height left as padding above each box.
    const CLASSIFICATION_LANE_TOP_PADDING_RATIO = 0.12;
    const CLASSIFICATION_LANE_LABEL_PREFIX = '● ';
    const CLASSIFICATION_LANE_LABEL_FALLBACK_COLOR = '#1f2937';

    function normalizeMarkerColor(color) {
        if (typeof color === 'string') {
            const trimmed = color.trim();
            if (trimmed) {
                return trimmed;
            }
        }
        return DEFAULT_MARKER_COLOR;
    }

    // Removed styleMarkerSpan - markers now use glyph-based rendering

    function _updateBokehImageData(existingImageData, newData) {
        if (!existingImageData || !newData) {
            return false;
        }
        if (existingImageData.length !== newData.length) {
            console.error(`Mismatched image data lengths. Existing: ${existingImageData.length}, New: ${newData.length}. Cannot update.`);
            return false;
        }
        if (typeof existingImageData.set === 'function') {
            existingImageData.set(newData);
            return true;
        }
        return false;
    }

    class Chart {
        constructor(chartModel, sourceModel, labelModel, hoverLineModel, positionId) {
            this.model = chartModel;
            this.source = sourceModel;
            this.labelModel = labelModel;
            this.hoverLineModel = hoverLineModel;
            this.name = chartModel.name;
            this.positionId = positionId; // Store the position ID
            this.regionOverlay = null;
            this.markerOverlay = null; // Glyph-based marker overlay
            this.classificationOverlay = null;
        }

        /**
         * Whether this chart type should draw the right-hand classification
         * lane labels ("● Motorcycle" etc.). Off by default — only the time
         * series carries them, so they are not duplicated on the spectrogram
         * (see classification_review_ui_plan.md, Phase 6).
         */
        get supportsClassificationLaneLabels() {
            return false;
        }

        setVisible(isVisible) {
            if (this.model.visible !== isVisible) {
                this.model.visible = isVisible;
            }
        }

        render() {
            if (this.source && this.source.change && typeof this.source.change.emit === 'function') {
                this.source.change.emit();
            }
        }

        renderLabel(timestamp, text) {
            if (!this.labelModel) return;
            const xRange = this.model.x_range;
            const yRange = this.model.y_range;
            const middleX = xRange.start + (xRange.end - xRange.start) / 2;
            const alignRight = timestamp > middleX;

            this.labelModel.x = alignRight ? timestamp - (xRange.end - xRange.start) * 0.02 : timestamp + (xRange.end - xRange.start) * 0.02;
            this.labelModel.y = yRange.end;
            this.labelModel.text_align = alignRight ? 'right' : 'left';
            this.labelModel.text = text.trimEnd();
            this.labelModel.visible = true;
        }

        hideLabel() {
            if (this.labelModel) this.labelModel.visible = false;
        }

        renderHoverLine(timestamp) {
            if (this.hoverLineModel) {
                this.hoverLineModel.location = timestamp;
                this.hoverLineModel.visible = true;
            } else {
                console.error('Hover line model not initialized');
            }
        }

        hideHoverLine() {
            if (this.hoverLineModel) this.hoverLineModel.visible = false;
        }

        /**
         * Syncs the chart's visible markers to match the global state using Segment glyphs.
         * @param {Array} markers - The global list of marker objects from state.
         * @param {boolean} areMarkersEnabled - The global visibility toggle from state.
         * @param {number} selectedMarkerId - The ID of the currently selected marker.
         */
        syncMarkers(markers, areMarkersEnabled, selectedMarkerId) {
            const overlay = this._ensureMarkerOverlay();
            if (!overlay) {
                console.error('[Chart.syncMarkers] Failed to initialize marker overlay.');
                return;
            }

            const { source, renderer } = overlay;
            const markerList = Array.isArray(markers) ? markers : [];
            const nextData = this._buildMarkerOverlayData(markerList, selectedMarkerId);

            source.data = nextData;
            renderer.visible = areMarkersEnabled && nextData.x0.length > 0;

            if (typeof this.model?.request_render === 'function') {
                this.model.request_render();
            } else if (this.model?.change?.emit) {
                this.model.change.emit();
            }
        }

        _ensureMarkerOverlay() {
            if (this.markerOverlay?.source && this.markerOverlay?.renderer) {
                return this.markerOverlay;
            }

            if (!window.Bokeh || !window.Bokeh.Models) {
                console.error("CRITICAL: window.Bokeh.Models is not available. BokehJS may not be loaded correctly.");
                return null;
            }

            const doc = window.Bokeh?.documents?.[0];
            const ColumnDataSource = Bokeh.Models.get('ColumnDataSource');
            const Segment = Bokeh.Models.get('Segment');
            const GlyphRenderer = Bokeh.Models.get('GlyphRenderer');

            if (!ColumnDataSource || !Segment || !GlyphRenderer) {
                console.error('[Chart._ensureMarkerOverlay] Required Bokeh models (ColumnDataSource, Segment, GlyphRenderer) are not available.');
                return null;
            }

            const initialData = this._emptyMarkerOverlayData();
            let source;
            if (doc && typeof doc.create_model === 'function' && typeof doc.add_model === 'function') {
                source = doc.add_model(doc.create_model('ColumnDataSource', {
                    data: initialData,
                    name: `marker_overlay_source_${this.name}`
                }));
            } else {
                source = new ColumnDataSource({ data: initialData, name: `marker_overlay_source_${this.name}` });
            }

            if (!source.change || typeof source.change.emit !== 'function') {
                source.change = source.change || {};
                source.change.emit = typeof source.change.emit === 'function' ? source.change.emit : function () { };
            }

            const glyphProps = {
                x0: { field: 'x0' },
                y0: { field: 'y0' },
                x1: { field: 'x1' },
                y1: { field: 'y1' },
                line_color: { field: 'line_color' },
                line_alpha: { field: 'line_alpha' },
                line_width: { field: 'line_width' }
            };
            const glyph = doc && typeof doc.create_model === 'function'
                ? doc.create_model('Segment', glyphProps)
                : new Segment(glyphProps);

            const rendererProps = {
                data_source: source,
                glyph,
                level: 'underlay',
                visible: false,
                name: `marker_overlay_renderer_${this.name}`
            };
            const renderer = doc && typeof doc.create_model === 'function' && typeof doc.add_model === 'function'
                ? doc.add_model(doc.create_model('GlyphRenderer', rendererProps))
                : new GlyphRenderer(rendererProps);

            let rendererAdded = false;
            if (typeof this.model?.add_glyph === 'function') {
                try {
                    // add_glyph expects a Glyph object (e.g., Segment), not a GlyphRenderer
                    // It returns a GlyphRenderer which we should use instead of our manually created one
                    const addedRenderer = this.model.add_glyph(glyph, source);
                    if (addedRenderer) {
                        // Use the renderer returned by add_glyph
                        this.markerOverlay = { source, renderer: addedRenderer };
                        return this.markerOverlay;
                    }
                    rendererAdded = true;
                } catch (error) {
                    console.warn('[Chart._ensureMarkerOverlay] add_glyph failed, falling back to manual renderer registration.', error);
                }
            }
            if (!rendererAdded) {
                if (typeof this.model?.add_renderers === 'function') {
                    this.model.add_renderers(renderer);
                    rendererAdded = true;
                } else if (Array.isArray(this.model?.renderers)) {
                    this.model.renderers.push(renderer);
                    rendererAdded = true;
                }
            }

            this.markerOverlay = { source, renderer };
            return this.markerOverlay;
        }

        _emptyMarkerOverlayData() {
            return {
                x0: [],
                y0: [],
                x1: [],
                y1: [],
                line_color: [],
                line_alpha: [],
                line_width: [],
                marker_id: []
            };
        }

        _buildMarkerOverlayData(markerList, selectedMarkerId) {
            const data = this._emptyMarkerOverlayData();
            const yRange = this.model?.y_range;
            const yStart = Number(yRange?.start);
            const yEnd = Number(yRange?.end);
            const hasValidRange = Number.isFinite(yStart) && Number.isFinite(yEnd);
            const y0 = hasValidRange ? Math.min(yStart, yEnd) : 0;
            const y1 = hasValidRange ? Math.max(yStart, yEnd) : 1;

            markerList.forEach(marker => {
                const timestamp = Number(marker?.timestamp);
                if (!Number.isFinite(timestamp)) {
                    return;
                }

                const markerId = marker?.id;
                const markerColor = normalizeMarkerColor(marker?.color);
                const isSelected = Number.isFinite(selectedMarkerId) && markerId === selectedMarkerId;

                data.x0.push(timestamp);
                data.y0.push(y0);
                data.x1.push(timestamp);
                data.y1.push(y1);
                data.line_color.push(markerColor);
                data.line_alpha.push(isSelected ? SELECTED_MARKER_LINE_ALPHA : UNSELECTED_MARKER_LINE_ALPHA);
                data.line_width.push(isSelected ? SELECTED_MARKER_LINE_WIDTH : UNSELECTED_MARKER_LINE_WIDTH);
                data.marker_id.push(markerId);
            });

            return data;
        }

        syncRegions(regionList, selectedId) {
            if (!Array.isArray(regionList)) return;
            const overlay = this._ensureRegionOverlay();
            if (!overlay) {
                return;
            }

            const { source, renderer } = overlay;
            const nextData = this._buildRegionOverlayData(regionList, selectedId);

            source.data = nextData;
            if (source.change && typeof source.change.emit === 'function') {
                source.change.emit();
            }

            renderer.visible = nextData.left.length > 0;

            if (typeof this.model?.request_render === 'function') {
                this.model.request_render();
            } else if (this.model?.change?.emit) {
                this.model.change.emit();
            }
        }

        _ensureRegionOverlay() {
            if (this.regionOverlay?.source && this.regionOverlay?.renderer) {
                return this.regionOverlay;
            }

            if (!window.Bokeh || !window.Bokeh.Models) {
                console.error("CRITICAL: window.Bokeh.Models is not available. BokehJS may not be loaded correctly.");
                return null;
            }

            const doc = window.Bokeh?.documents?.[0];
            const ColumnDataSource = Bokeh.Models.get('ColumnDataSource');
            const Quad = Bokeh.Models.get('Quad');
            const GlyphRenderer = Bokeh.Models.get('GlyphRenderer');

            if (!ColumnDataSource || !Quad || !GlyphRenderer) {
                console.error('[Chart._ensureRegionOverlay] Required Bokeh models (ColumnDataSource, Quad, GlyphRenderer) are not available.');
                return null;
            }

            const initialData = this._emptyRegionOverlayData();
            let source;
            if (doc && typeof doc.create_model === 'function' && typeof doc.add_model === 'function') {
                source = doc.add_model(doc.create_model('ColumnDataSource', {
                    data: initialData,
                    name: `region_overlay_source_${this.name}`
                }));
            } else {
                source = new ColumnDataSource({ data: initialData, name: `region_overlay_source_${this.name}` });
            }

            if (!source.change || typeof source.change.emit !== 'function') {
                source.change = source.change || {};
                source.change.emit = typeof source.change.emit === 'function' ? source.change.emit : function () { };
            }

            const glyphProps = {
                left: { field: 'left' },
                right: { field: 'right' },
                bottom: { field: 'bottom' },
                top: { field: 'top' },
                fill_color: { field: 'fill_color' },
                fill_alpha: { field: 'fill_alpha' },
                line_color: { field: 'line_color' },
                line_alpha: { field: 'line_alpha' },
                line_width: { field: 'line_width' }
            };
            const glyph = doc && typeof doc.create_model === 'function'
                ? doc.create_model('Quad', glyphProps)
                : new Quad(glyphProps);

            const rendererProps = {
                data_source: source,
                glyph,
                level: 'underlay',
                visible: false,
                name: `region_overlay_renderer_${this.name}`
            };
            const renderer = doc && typeof doc.create_model === 'function' && typeof doc.add_model === 'function'
                ? doc.add_model(doc.create_model('GlyphRenderer', rendererProps))
                : new GlyphRenderer(rendererProps);

            let rendererAdded = false;
            if (typeof this.model?.add_glyph === 'function') {
                try {
                    const addedRenderer = this.model.add_glyph(glyph, source);
                    if (addedRenderer) {
                        this.regionOverlay = { source, renderer: addedRenderer };
                        return this.regionOverlay;
                    }
                    rendererAdded = true;
                } catch (error) {
                    console.warn('[Chart._ensureRegionOverlay] add_glyph failed, falling back to manual renderer registration.', error);
                }
            }
            if (!rendererAdded) {
                if (typeof this.model?.add_renderers === 'function') {
                    this.model.add_renderers(renderer);
                    rendererAdded = true;
                } else if (Array.isArray(this.model?.renderers)) {
                    this.model.renderers.push(renderer);
                    rendererAdded = true;
                }
            }

            this.regionOverlay = { source, renderer };
            return this.regionOverlay;
        }

        _emptyRegionOverlayData() {
            return {
                left: [],
                right: [],
                bottom: [],
                top: [],
                fill_color: [],
                fill_alpha: [],
                line_color: [],
                line_alpha: [],
                line_width: [],
                region_id: [],
                area_index: []
            };
        }

        _buildRegionOverlayData(regionList, selectedId) {
            const data = this._emptyRegionOverlayData();
            const yRange = this.model?.y_range;
            const yStart = Number(yRange?.start);
            const yEnd = Number(yRange?.end);
            const hasValidRange = Number.isFinite(yStart) && Number.isFinite(yEnd);
            const bottom = hasValidRange ? Math.min(yStart, yEnd) : 0;
            const top = hasValidRange ? Math.max(yStart, yEnd) : 1;

            regionList.forEach(region => {
                if (!region || region.positionId !== this.positionId) return;
                const areas = Array.isArray(region.areas) && region.areas.length
                    ? region.areas
                    : (Number.isFinite(region.start) && Number.isFinite(region.end)
                        ? [{ start: region.start, end: region.end }]
                        : []);
                if (!areas.length) return;

                const regionColor = typeof region.color === 'string' && region.color.trim()
                    ? region.color.trim()
                    : DEFAULT_REGION_COLOR;
                const isSelected = region.id === selectedId;

                areas.forEach((area, index) => {
                    const start = Number(area?.start);
                    const end = Number(area?.end);
                    if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
                        return;
                    }

                    data.left.push(start);
                    data.right.push(end);
                    data.bottom.push(bottom);
                    data.top.push(top);
                    data.fill_color.push(regionColor);
                    data.fill_alpha.push(isSelected ? SELECTED_REGION_FILL_ALPHA : DEFAULT_REGION_FILL_ALPHA);
                    data.line_color.push(regionColor);
                    data.line_alpha.push(DEFAULT_REGION_LINE_ALPHA);
                    data.line_width.push(isSelected ? SELECTED_REGION_LINE_WIDTH : DEFAULT_REGION_LINE_WIDTH);
                    data.region_id.push(region.id);
                    data.area_index.push(index);
                });
            });

            return data;
        }

        syncClassifications(classificationList, areClassificationsVisible, selectedId) {
            const overlay = this._ensureClassificationOverlay();
            if (!overlay) {
                return;
            }
            const { source, renderer } = overlay;
            const nextData = this._buildClassificationOverlayData(classificationList, selectedId);

            source.__suppressSelectionDispatch = true;
            source.data = nextData;
            if (source.change && typeof source.change.emit === 'function') {
                source.change.emit();
            }
            source.__suppressSelectionDispatch = false;

            renderer.visible = areClassificationsVisible && nextData.left.length > 0;

            // Sync lane labels
            this._syncClassificationLaneLabels(nextData, areClassificationsVisible);

            if (typeof this.model?.request_render === 'function') {
                this.model.request_render();
            } else if (this.model?.change?.emit) {
                this.model.change.emit();
            }
        }

        _ensureClassificationOverlay() {
            if (this.classificationOverlay?.source && this.classificationOverlay?.renderer) {
                return this.classificationOverlay;
            }
            if (!window.Bokeh || !window.Bokeh.Models) {
                return null;
            }

            const ColumnDataSource = Bokeh.Models.get('ColumnDataSource');
            const Quad = Bokeh.Models.get('Quad');
            const GlyphRenderer = Bokeh.Models.get('GlyphRenderer');
            const CustomJS = Bokeh.Models.get('CustomJS');
            const HoverTool = Bokeh.Models.get('HoverTool');
            const LabelSet = Bokeh.Models.get('LabelSet');

            if (!ColumnDataSource || !Quad || !GlyphRenderer) {
                console.error('[Chart._ensureClassificationOverlay] Required Bokeh models are not available.');
                return null;
            }

            // This overlay is entirely client-side (a visual layer plus a JS-only
            // Redux dispatch on tap — no server round-trip needed), so every model
            // below is built via `new Model(...)` rather than `doc.create_model`.
            // `doc.create_model` does NOT run the real Bokeh.js constructor and
            // does not correctly initialise default sub-models — in particular
            // `source.selected` comes back without a working `js_on_change`
            // (confirmed: this was the only place in the file relying on
            // `.selected.js_on_change()` on a `doc.create_model`-built source,
            // which is why the bug wasn't caught by the existing marker/region
            // overlay code that uses the same conditional pattern for other
            // properties). `add_glyph`/`add_tools`/`add_layout` already register
            // whatever model instance they're given with the chart correctly,
            // regardless of how it was constructed.
            const initialData = this._emptyClassificationOverlayData();
            const source = new ColumnDataSource({
                data: initialData,
                name: `classification_overlay_source_${this.name}`,
            });

            // This Selection exists only in the browser. Prevent Bokeh server
            // patches from referring to a child model the Python document does
            // not know about; JS callbacks still run when syncable is false.
            if (source.selected) {
                source.selected.syncable = false;
            }

            const glyphProps = {
                left: { field: 'left' },
                right: { field: 'right' },
                bottom: { field: 'bottom' },
                top: { field: 'top' },
                fill_color: { field: 'fill_color' },
                fill_alpha: { field: 'fill_alpha' },
                line_color: { field: 'line_color' },
                line_alpha: { field: 'line_alpha' },
                line_width: { field: 'line_width' }
            };
            const glyph = new Quad(glyphProps);
            const rendererProps = {
                data_source: source,
                glyph,
                level: 'overlay',
                visible: false,
                name: `classification_overlay_renderer_${this.name}`
            };
            const renderer = new GlyphRenderer(rendererProps);

            let rendererAdded = false;
            if (typeof this.model?.add_glyph === 'function') {
                try {
                    const addedRenderer = this.model.add_glyph(glyph, source);
                    if (addedRenderer) {
                        this.classificationOverlay = { source, renderer: addedRenderer };
                        rendererAdded = true;
                    }
                } catch (error) {
                    console.warn('[Chart._ensureClassificationOverlay] add_glyph failed, falling back.', error);
                }
            }
            if (!rendererAdded) {
                if (typeof this.model?.add_renderers === 'function') {
                    this.model.add_renderers(renderer);
                } else if (Array.isArray(this.model?.renderers)) {
                    this.model.renderers.push(renderer);
                }
                this.classificationOverlay = { source, renderer };
            }

            // The client-created Selection model does not expose Bokeh's
            // CustomJS `js_on_change` helper. Connect directly to its JS
            // signal so programmatic/table selections can still update the
            // Redux selection state. Plot clicks are handled by the shared
            // tap handler, which performs the same quad hit-test before
            // deciding whether a click should seek audio.
            if (source.selected && source.selected.change && typeof source.selected.change.connect === 'function') {
                source.selected.change.connect(() => {
                    if (source.__suppressSelectionDispatch) return;
                    const indices = Array.isArray(source.selected?.indices) ? source.selected.indices : [];
                    if (!indices.length) return;
                    const data = source.data || {};
                    const ids = Array.isArray(data.classification_id) ? data.classification_id : [];
                    const selectedId = Number(ids[indices[0]]);
                    if (!Number.isFinite(selectedId)) return;

                    const noiseSurveyApp = window.NoiseSurveyApp;
                    const selectIntent = noiseSurveyApp?.features?.classifications?.thunks?.selectClassificationIntent;
                    if (typeof selectIntent === 'function' && typeof noiseSurveyApp?.store?.dispatch === 'function') {
                        noiseSurveyApp.store.dispatch(selectIntent(selectedId));
                    }
                });
            } else {
                console.warn('[Chart._ensureClassificationOverlay] source.selected.change.connect '
                    + 'unavailable — chart-click selection will not work for this chart.');
            }

            // Restricted HoverTool
            if (HoverTool && this.model) {
                const hoverProps = {
                    renderers: [this.classificationOverlay.renderer],
                    tooltips: [
                        ['Category', '@label'],
                        ['Start', '@start_str'],
                        ['End', '@end_str'],
                        ['Score', '@score_str'],
                        ['Role', '@role_str'],
                        ['State', '@state'],
                        ['Description', '@description']
                    ],
                    attachment: 'above',
                    show_arrow: false,
                    name: `classification_hover_tool_${this.name}`
                };
                const hoverTool = new HoverTool(hoverProps);
                if (typeof this.model.add_tools === 'function') {
                    this.model.add_tools(hoverTool);
                }
                this.classificationHoverTool = hoverTool;
            }

            // Right-hand lane labels model
            if (LabelSet && this.model && this.supportsClassificationLaneLabels) {
                const labelSource = new ColumnDataSource({
                    data: { x: [], y: [], text: [], text_color: [] },
                    name: `classification_lane_labels_source_${this.name}`,
                });

                const labelSetProps = {
                    x: 'x',
                    y: 'y',
                    text: 'text',
                    text_color: 'text_color',
                    text_font_size: '11px',
                    text_font_style: 'bold',
                    text_align: 'right',
                    text_baseline: 'middle',
                    x_offset: -8,
                    source: labelSource,
                    level: 'annotation',
                    name: `classification_lane_labels_${this.name}`
                };
                const labelSet = new LabelSet(labelSetProps);

                if (typeof this.model.add_layout === 'function') {
                    this.model.add_layout(labelSet);
                }
                this.classificationLabelOverlay = { source: labelSource, labelSet };

                // Re-align labels on x_range changes. Not every chart's x_range is
                // a full Bokeh model with js_on_change (shared/linked ranges can
                // arrive as plainer objects), so check before wiring the callback —
                // without it the labels simply don't re-pin on pan/zoom, which is
                // far better than throwing and killing the whole render pass.
                const xRange = this.model.x_range;
                if (xRange && CustomJS && typeof xRange.js_on_change === 'function') {
                    const rangeCallback = new CustomJS({
                        args: { labelSource, x_range: xRange },
                        code: `
                            const end = x_range?.end;
                            if (!Number.isFinite(end) || !labelSource?.data?.x) return;
                            const len = labelSource.data.x.length;
                            if (!len) return;
                            labelSource.data.x = Array(len).fill(end);
                            if (labelSource.change && typeof labelSource.change.emit === 'function') {
                                labelSource.change.emit();
                            }
                        `
                    });
                    xRange.js_on_change('end', rangeCallback);
                } else if (xRange && CustomJS) {
                    console.warn('[Chart._ensureClassificationOverlay] x_range has no '
                        + 'js_on_change — classification lane labels will not re-align on pan/zoom.');
                }
            }

            return this.classificationOverlay;
        }

        _emptyClassificationOverlayData() {
            return {
                left: [],
                right: [],
                bottom: [],
                top: [],
                fill_color: [],
                fill_alpha: [],
                line_color: [],
                line_alpha: [],
                line_width: [],
                classification_id: [],
                source_id: [],
                label: [],
                start_str: [],
                end_str: [],
                score_str: [],
                role_str: [],
                state: [],
                description: []
            };
        }

        _buildClassificationOverlayData(classificationList, selectedId) {
            const data = this._emptyClassificationOverlayData();
            const entries = (Array.isArray(classificationList) ? classificationList : [])
                .filter(entry => entry && entry.positionId === this.positionId);
            if (!entries.length) {
                return data;
            }

            const yRange = this.model?.y_range;
            const yStart = Number(yRange?.start);
            const yEnd = Number(yRange?.end);
            const hasValidRange = Number.isFinite(yStart) && Number.isFinite(yEnd) && yStart !== yEnd;
            const rangeBottom = hasValidRange ? Math.min(yStart, yEnd) : 0;
            const rangeTop = hasValidRange ? Math.max(yStart, yEnd) : 1;
            const rangeHeight = Math.max(rangeTop - rangeBottom, 1);
            const bandBottom = rangeBottom + rangeHeight * 0.02;
            const bandTop = rangeBottom + rangeHeight * 0.26;
            const sources = Array.from(new Set(entries.map(entry => entry.sourceId || entry.sourceLabel || 'source'))).sort();
            const laneHeight = (bandTop - bandBottom) / Math.max(sources.length, 1);

            const utils = window.NoiseSurveyApp?.features?.classifications?.utils;
            const getShadedColorForScore = utils?.getShadedColorForScore;

            entries.forEach(entry => {
                const start = Number(entry.start);
                const end = Number(entry.end);
                if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end) {
                    return;
                }
                const sourceKey = entry.sourceId || entry.sourceLabel || 'source';
                const laneIndex = Math.max(0, sources.indexOf(sourceKey));
                const lanePadding = laneHeight * CLASSIFICATION_LANE_TOP_PADDING_RATIO;
                const laneBottom = bandBottom + laneIndex * laneHeight + lanePadding;
                const laneTop = bandBottom + (laneIndex + 1) * laneHeight - lanePadding;
                const isSelected = Number.isFinite(selectedId) && entry.id === selectedId;
                const isOff = String(entry.state || '').toLowerCase() === 'off';

                const baseColor = entry.color || FALLBACK_CLASSIFICATION_COLOR;
                const color = isOff
                    ? OFF_CLASSIFICATION_COLOR
                    : (typeof getShadedColorForScore === 'function'
                        ? getShadedColorForScore(baseColor, entry.confidence)
                        : baseColor);

                data.left.push(start);
                data.right.push(end);
                data.bottom.push(laneBottom);
                data.top.push(laneTop);
                data.fill_color.push(color);
                data.fill_alpha.push(isSelected ? SELECTED_CLASSIFICATION_FILL_ALPHA : (isOff ? OFF_CLASSIFICATION_FILL_ALPHA : DEFAULT_CLASSIFICATION_FILL_ALPHA));
                data.line_color.push(isSelected ? SELECTED_CLASSIFICATION_LINE_COLOR : color);
                data.line_alpha.push(isOff
                    ? OFF_CLASSIFICATION_LINE_ALPHA
                    : (isSelected ? SELECTED_CLASSIFICATION_LINE_ALPHA : CLASSIFICATION_LINE_ALPHA));
                data.line_width.push(isSelected ? SELECTED_CLASSIFICATION_LINE_WIDTH : DEFAULT_CLASSIFICATION_LINE_WIDTH);
                data.classification_id.push(entry.id);
                data.source_id.push(sourceKey);
                data.label.push(entry.sourceLabel || sourceKey);
                data.start_str.push(new Date(start).toLocaleTimeString());
                data.end_str.push(new Date(end).toLocaleTimeString());
                data.score_str.push(Number.isFinite(entry.confidence) ? `${Math.round(entry.confidence * 100)}%` : 'N/A');
                data.role_str.push(entry.role === 'supporting' ? 'Supporting' : 'Direct');
                data.state.push(entry.state || 'on');
                data.description.push(entry.description || '');
            });

            // Save computed lane info for right-hand labels
            this._lastComputedLaneInfo = {
                sources,
                bandBottom,
                laneHeight,
                xMax: Number(this.model?.x_range?.end) || 0
            };

            return data;
        }

        _syncClassificationLaneLabels(overlayData, areClassificationsVisible) {
            if (!this.classificationLabelOverlay?.source || !this._lastComputedLaneInfo) {
                return;
            }
            const { source } = this.classificationLabelOverlay;
            if (!areClassificationsVisible || !overlayData || !overlayData.left.length) {
                source.data = { x: [], y: [], text: [], text_color: [] };
                if (source.change?.emit) source.change.emit();
                return;
            }

            const { sources, bandBottom, laneHeight } = this._lastComputedLaneInfo;
            const xMax = Number(this.model?.x_range?.end) || 0;
            const x = [];
            const y = [];
            const text = [];
            const text_color = [];

            // Map each unique source to label text and color
            sources.forEach(sourceKey => {
                const sampleIndex = overlayData.source_id.indexOf(sourceKey);
                if (sampleIndex >= 0) {
                    const laneIndex = sources.indexOf(sourceKey);
                    const laneMidpoint = bandBottom + laneIndex * laneHeight + laneHeight * 0.5;
                    x.push(xMax);
                    y.push(laneMidpoint);
                    text.push(`${CLASSIFICATION_LANE_LABEL_PREFIX}${overlayData.label[sampleIndex]}`);
                    text_color.push(overlayData.fill_color[sampleIndex] || CLASSIFICATION_LANE_LABEL_FALLBACK_COLOR);
                }
            });

            source.data = { x, y, text, text_color };
            if (source.change?.emit) source.change.emit();
        }

        update() {
            throw new Error("Update method must be implemented by subclass.");
        }

        getLabelText() {
            return "Label not implemented";
        }
    }

    class TimeSeriesChart extends Chart {
        constructor(...args) {
            super(...args);
            this.activeData = {};
            this.lastDisplayDetails = { reason: '' };
            this.displayName = this.positionId;
            this._lastDataHash = null; // For change detection
        }

        /** Lane labels live on the time series only — see base class. */
        get supportsClassificationLaneLabels() {
            return true;
        }

        _computeDataHash(data) {
            if (!data || !data.Datetime) return null;
            // Fast hash using first, last, length of Datetime array, and offset
            const dt = data.Datetime;
            const len = dt.length;
            if (len === 0) return 'empty';
            const offset = data._offsetMs ?? 0;
            return `${len}:${dt[0]}:${dt[len - 1]}:${offset}`;
        }

        setDisplayName(name) {
            if (typeof name === 'string' && name.trim()) {
                this.displayName = name.trim();
            } else {
                this.displayName = this.positionId;
            }
        }

        _setOptionalPercentileRenderersVisible(displayType) {
            const renderers = Array.isArray(this.model?.renderers) ? this.model.renderers : [];
            const showOptionalPercentiles = displayType !== 'log';

            renderers.forEach(renderer => {
                const ySpec = renderer?.glyph?.y;
                const fieldName = typeof ySpec === 'string'
                    ? ySpec
                    : (typeof ySpec?.field === 'string' ? ySpec.field : null);
                if (fieldName === 'LAF90' || fieldName === 'LAF10') {
                    renderer.visible = showOptionalPercentiles;
                }
            });
        }

        update(activeLineData, displayDetails) {
            this.lastDisplayDetails = displayDetails || { reason: '' };
            const suffix = this.lastDisplayDetails.reason || '';
            const baseName = this.displayName || this.positionId;
            this.model.title.text = `${baseName} - Time History${suffix}`;
            
            // Force update if switching view types (e.g., from log to overview)
            const newType = displayDetails?.type || 'unknown';
            const oldType = this._lastDisplayType || 'unknown';
            const typeChanged = newType !== oldType;
            this._lastDisplayType = newType;
            this._setOptionalPercentileRenderersVisible(newType);
            
            const newHash = this._computeDataHash(activeLineData);
            if (newHash !== this._lastDataHash || typeChanged) {
                this._lastDataHash = newHash;
                this.activeData = activeLineData;
                // Strip non-array metadata fields before setting Bokeh ColumnDataSource
                // Bokeh requires all values to be arrays of equal length
                const cleanData = {};
                for (const key in activeLineData) {
                    const val = activeLineData[key];
                    // Accept Arrays and TypedArrays (Float64Array, Int32Array, etc.)
                    // but exclude strings and other non-array-like metadata
                    if (Array.isArray(val) || ArrayBuffer.isView(val)) {
                        cleanData[key] = val;
                    }
                }

                // Keep optional percentile fields present in log mode so Bokeh
                // does not warn about missing renderer fields during source swaps.
                if (newType === 'log' && (Array.isArray(cleanData.Datetime) || ArrayBuffer.isView(cleanData.Datetime))) {
                    const n = cleanData.Datetime.length;
                    if (!Object.prototype.hasOwnProperty.call(cleanData, 'LAF90')) {
                        cleanData.LAF90 = new Array(n).fill(NaN);
                    }
                    if (!Object.prototype.hasOwnProperty.call(cleanData, 'LAF10')) {
                        cleanData.LAF10 = new Array(n).fill(NaN);
                    }
                }

                // Only update source if we have actual data columns;
                // prevents emptying the display source when log data hasn't loaded yet
                if (Object.keys(cleanData).length > 0) {
                    this.source.data = cleanData;
                }
                this.render();
            }
        }

        getLabelText(timestamp) {
            if (!this.activeData?.Datetime) return "Data N/A";
            const idx = app.utils.findAssociatedDateIndex(this.activeData, timestamp);
            if (idx === -1) return "No data point";

            const date = new Date(this.activeData.Datetime[idx]);
            let label_text = `Time: ${date.toLocaleString()}\n`;
            for (const key in this.activeData) {
                if (key === 'Datetime' || key === 'index' || key.startsWith('_')) continue;
                const val = this.activeData[key];
                if (!Array.isArray(val) && !ArrayBuffer.isView(val)) continue;
                const value = val[idx];
                const formatted_value = parseFloat(value).toFixed(1);
                const unit = (key.startsWith('L') || key.includes('eq')) ? ' dB' : '';
                label_text += `${key}: ${formatted_value}${unit}\n`;
            }
            return label_text;
        }


    }

    class SpectrogramChart extends Chart {
        constructor(chartModel, labelModel, hoverLineModel, hoverDivModel, positionId) {
            const imageRenderer = chartModel.renderers.find(r => r.glyph?.type === "Image");
            if (!imageRenderer) {
                console.warn('No ImageRenderer found in chartModel');
                // Still call super with undefined source, but it will be handled gracefully.
                super(chartModel, undefined, labelModel, hoverLineModel, positionId);
                return;
            }
            super(chartModel, imageRenderer.data_source, labelModel, hoverLineModel, positionId);
            this.imageRenderer = imageRenderer;
            this.hoverDivModel = hoverDivModel;
            this.lastDisplayDetails = { reason: '' };
            this.displayName = this.positionId;
            this._lastReplacementSignature = null;
        }

        _buildReplacementSignature(replacement, selectedParameter) {
            if (!replacement) return false;
            return [
                selectedParameter,
                replacement._offsetMs ?? 0,
                replacement.x?.[0] ?? 'x',
                replacement.dw?.[0] ?? 'dw',
                replacement.y?.[0] ?? 'y',
                replacement.dh?.[0] ?? 'dh',
                replacement.y_range_start ?? 'ys',
                replacement.y_range_end ?? 'ye',
                replacement.times_ms?.length ?? 0,
                replacement.image?.[0]?.length ?? 0
            ].join('|');
        }

        _hasGlyphChanged(replacement, selectedParameter) {
            const nextSignature = this._buildReplacementSignature(replacement, selectedParameter);
            if (!nextSignature) return false;
            if (nextSignature === this._lastReplacementSignature) {
                return false;
            }
            this._lastReplacementSignature = nextSignature;
            return true;
        }

        setDisplayName(name) {
            if (typeof name === 'string' && name.trim()) {
                this.displayName = name.trim();
            } else {
                this.displayName = this.positionId;
            }
        }

        update(activeSpectralData, displayDetails, selectedParameter) {
            this.lastDisplayDetails = displayDetails || { reason: '' };
            const suffix = this.lastDisplayDetails.reason || '';
            const baseName = this.displayName || this.positionId;
            const displayedParameter = displayDetails?.displayedParameter || activeSpectralData?.displayedParameter || selectedParameter;
            this.model.title.text = `${baseName} - ${displayedParameter} Spectrogram${suffix}`;

            const replacement = activeSpectralData?.source_replacement;
            if (replacement && this.imageRenderer) {
                // Skip expensive updates if glyph position hasn't changed
                if (!this._hasGlyphChanged(replacement, selectedParameter)) {
                    return;
                }

                const glyph = this.imageRenderer.glyph;

                const existingImage = this.source.data.image?.[0];
                const replacementImage = replacement.image?.[0];

                // Validate payload before touching Bokeh's fixed-size image buffer
                if (!replacementImage || typeof replacementImage.length !== 'number' || replacementImage.length === 0) {
                    console.warn('[SpectrogramChart] Invalid or empty replacement image; retaining current image.');
                    return;
                }
                if (Array.isArray(replacementImage)) {
                    const actualRows = replacementImage.length;
                    const actualCols = replacementImage[0]?.length ?? 0;
                    if (actualRows > 0 && actualCols > 0 && existingImage && existingImage.length > 0) {
                        const expectedCells = existingImage.length * (existingImage[0]?.length ?? 0);
                        const actualCells = actualRows * actualCols;
                        if (actualCells !== expectedCells) {
                            console.warn(`[SpectrogramChart] Image size mismatch: expected ${expectedCells} cells, got ${actualCells}. Retaining current image.`);
                            return;
                        }
                    }
                }

                const patchedInPlace = _updateBokehImageData(existingImage, replacementImage);
                if (!patchedInPlace) {
                    console.warn('[SpectrogramChart] Skipping spectrogram update because replacement image shape does not match the initialized glyph buffer.');
                    return;
                }

                // Update the glyph's position and size on the "canvas"
                glyph.x = replacement.x[0];
                glyph.dw = replacement.dw[0];

                // Handle frequency slicing by updating plot range but keeping original glyph positioning
                if (replacement.y_range_start !== undefined && replacement.y_range_end !== undefined) {
                    glyph.y = replacement.y[0];
                    glyph.dh = replacement.dh[0];
                    this.model.y_range.start = replacement.y_range_start;
                    this.model.y_range.end = replacement.y_range_end;
                } else {
                    glyph.y = replacement.y[0];
                    glyph.dh = replacement.dh[0];
                }

                // Update the y-axis ticks to only show labels for the visible range
                if (replacement.visible_freq_indices && replacement.visible_frequency_labels && this.model.yaxis && this.model.yaxis.ticker) {
                    this.model.yaxis.ticker.ticks = replacement.visible_freq_indices;
                    this.model.yaxis.major_label_overrides = {};
                    replacement.visible_freq_indices.forEach((tickIndex, i) => {
                        const labelText = replacement.visible_frequency_labels[i].split(' ')[0];
                        this.model.yaxis.major_label_overrides[tickIndex] = labelText;
                    });
                }

                const debugPos = getDebugPosition();
                if (debugPos && this.positionId === debugPos) {
                    console.log('[SpecDebug] chart-update', {
                        selectedParameter,
                        replacementX: replacement.x?.[0],
                        replacementDw: replacement.dw?.[0],
                        replacementY: replacement.y?.[0],
                        replacementDh: replacement.dh?.[0],
                        replacementTimesFirst: replacement.times_ms?.[0],
                        replacementTimesLast: replacement.times_ms?.[replacement.times_ms?.length - 1],
                        replacementTimesLen: replacement.times_ms?.length,
                        glyphX: glyph.x,
                        glyphDw: glyph.dw,
                        xRangeStart: this.model.x_range?.start,
                        xRangeEnd: this.model.x_range?.end
                    });
                }

                this.render();
            }
            // Visibility is now handled exclusively by the renderPrimaryCharts function.
            // This method is now only responsible for updating the data content.
        }

        getLabelText(timestamp) {
            if (this.timeSeriesCompanion) {
                return this.timeSeriesCompanion.getLabelText(timestamp);
            }
            return `Spectrogram Hover\nTime: ${new Date(timestamp).toLocaleString()}`;
        }

        setTimeSeriesCompanion(chart) {
            this.timeSeriesCompanion = chart;
        }

        renderHoverDetails(hoverState, freqBarData) {
            if (!this.hoverDivModel) return;
            const isRelevant = hoverState.isActive && hoverState.sourceChartName === this.name && freqBarData.setBy === 'hover';
            if (!isRelevant) {
                this.hoverDivModel.text = "Hover over spectrogram for details";
                return;
            }
            const n_freqs = freqBarData.frequency_labels.length;
            const freq_idx = Math.max(0, Math.min(n_freqs - 1, Math.floor(hoverState.spec_y + 0.5)));
            const level = freqBarData.levels[freq_idx];
            const freq_str = freqBarData.frequency_labels[freq_idx];
            const time_str = new Date(hoverState.timestamp).toLocaleString();
            const level_str = (level == null || isNaN(level)) ? "N/A" : level.toFixed(1) + " dB";
            this.hoverDivModel.text = `<b>Time:</b> ${time_str} | <b>Freq:</b> ${freq_str} | <b>Level:</b> ${level_str} (${freqBarData.param})`;
        }


    }

    class PositionController {
        constructor(positionId, models) {
            this.id = positionId;
            this.displayName = positionId;
            this.charts = []; // Initialize as an array
            this.timeSeriesChart = null;
            this.spectrogramChart = null;

            // --- TimeSeries Chart (robustly) ---
            const tsChartModel = models.charts.find(c => c.name === `figure_${this.id}_timeseries`);
            if (tsChartModel) {
                const tsSourceModel = models.chartsSources.find(s => s.name === `source_${this.id}_timeseries`);
                const tsLabelModel = models.labels.find(l => l.name === `label_${this.id}_timeseries`);
                const tsHoverLineModel = models.hoverLines.find(l => l.name === `hoverline_${this.id}_timeseries`);
                this.timeSeriesChart = new TimeSeriesChart(tsChartModel, tsSourceModel, tsLabelModel, tsHoverLineModel, this.id);
                this.timeSeriesChart.setDisplayName(this.displayName);
                this.charts.push(this.timeSeriesChart);
            }

            // --- Spectrogram Chart (robustly) ---
            const specChartModel = models.charts.find(c => c.name === `figure_${this.id}_spectrogram`);
            if (specChartModel) {
                const specLabelModel = models.labels.find(l => l.name === `label_${this.id}_spectrogram`);
                const specHoverLineModel = models.hoverLines.find(l => l.name === `hoverline_${this.id}_spectrogram`);
                const specHoverDivModel = models.hoverDivs.find(d => d.name === `${this.id}_spectrogram_hover_div`);
                try {
                    this.spectrogramChart = new SpectrogramChart(specChartModel, specLabelModel, specHoverLineModel, specHoverDivModel, this.id);
                    this.spectrogramChart.setDisplayName(this.displayName);
                    this.charts.push(this.spectrogramChart);
                }
                catch (e) {
                    console.error(`Could not initialize SpectrogramChart for ${this.id}:`, e);
                }
            }

            // Link the charts for inter-communication
            if (this.timeSeriesChart && this.spectrogramChart) {
                this.spectrogramChart.setTimeSeriesCompanion(this.timeSeriesChart);
            }
        }

        setDisplayName(displayName) {
            const sanitized = typeof displayName === 'string' && displayName.trim()
                ? displayName.trim()
                : this.id;
            if (sanitized === this.displayName) {
                return;
            }
            this.displayName = sanitized;
            if (this.timeSeriesChart) {
                this.timeSeriesChart.setDisplayName(this.displayName);
            }
            if (this.spectrogramChart) {
                this.spectrogramChart.setDisplayName(this.displayName);
            }
        }

        updateAllCharts(state, dataCache, displayDetails = {}) {
            const activeLineData = dataCache.activeLineData[this.id];
            const activeSpecData = dataCache.activeSpectralData[this.id];
            if (this.timeSeriesChart) {
                this.timeSeriesChart.setDisplayName(this.displayName);
                const lineDetails = activeLineData?.displayDetails
                    || displayDetails.line
                    || this.timeSeriesChart.lastDisplayDetails
                    || { reason: '' };
                this.timeSeriesChart.update(activeLineData, lineDetails);
            }
            if (this.spectrogramChart) {
                this.spectrogramChart.setDisplayName(this.displayName);
                const specDetails = activeSpecData?.displayDetails
                    || displayDetails.spec
                    || this.spectrogramChart.lastDisplayDetails
                    || { reason: '' };
                this.spectrogramChart.update(activeSpecData, specDetails, state.view.selectedParameter);
            }
        }

        setVisibility(isVisible) {
            this.charts.forEach(chart => chart.setVisible(isVisible));
        }
    }

    app.classes = {
        Chart: Chart,
        TimeSeriesChart: TimeSeriesChart,
        SpectrogramChart: SpectrogramChart,
        PositionController: PositionController
    };
})(window.NoiseSurveyApp);
