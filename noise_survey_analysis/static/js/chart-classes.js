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

    function normalizeMarkerColor(color) {
        if (typeof color === 'string') {
            const trimmed = color.trim();
            if (trimmed) {
                return trimmed;
            }
        }
        return DEFAULT_MARKER_COLOR;
    }

    function styleMarkerSpan(span, color, isSelected) {
        if (!span) {
            return;
        }
        const desiredColor = normalizeMarkerColor(color);
        const desiredWidth = isSelected ? SELECTED_MARKER_LINE_WIDTH : UNSELECTED_MARKER_LINE_WIDTH;
        const desiredAlpha = isSelected ? SELECTED_MARKER_LINE_ALPHA : UNSELECTED_MARKER_LINE_ALPHA;

        if (span.line_color !== desiredColor) {
            span.line_color = desiredColor;
        }
        if (span.line_width !== desiredWidth) {
            span.line_width = desiredWidth;
        }
        if (span.line_alpha !== desiredAlpha) {
            span.line_alpha = desiredAlpha;
        }
    }

    function _updateBokehImageData(existingImageData, newData) {
        if (existingImageData.length !== newData.length) {
            console.error(`Mismatched image data lengths. Existing: ${existingImageData.length}, New: ${newData.length}. Cannot update.`);
            return;
        }
        existingImageData.set(newData);
    }

    class Chart {
        constructor(chartModel, sourceModel, labelModel, hoverLineModel, positionId) {
            this.model = chartModel;
            this.source = sourceModel;
            this.labelModel = labelModel;
            this.hoverLineModel = hoverLineModel;
            this.name = chartModel.name;
            this.positionId = positionId; // Store the position ID
            this.markerModels = []; // Each chart instance manages its own marker models.
            this.regionOverlay = null;
        }

        setVisible(isVisible) {
            if (this.model.visible !== isVisible) {
                this.model.visible = isVisible;
            }
        }

        render() {
            this.source.change.emit();
        }

        renderLabel(timestamp, text) {
            if (!this.labelModel) return;
            const xRange = this.model.x_range;
            const yRange = this.model.y_range;
            const middleX = xRange.start + (xRange.end - xRange.start) / 2;
            const alignRight = timestamp > middleX;

            this.labelModel.x = alignRight ? timestamp - (xRange.end - xRange.start) * 0.02 : timestamp + (xRange.end - xRange.start) * 0.02;
            this.labelModel.y = yRange.end - (yRange.end - yRange.start) / 5;
            this.labelModel.text_align = alignRight ? 'right' : 'left';
            this.labelModel.text = text;
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
         * The "main" marker method. It syncs the chart's visible markers
         * to match the global state. This is a declarative approach.
         * @param {number[]} masterTimestampList - The global list of marker timestamps from _state.
         * @param {boolean} areMarkersEnabled - The global visibility toggle from _state.
         */
        syncMarkers(markers, areMarkersEnabled, selectedMarkerId) {
            // First, handle the global visibility toggle
            if (!areMarkersEnabled) {
                this.markerModels.forEach(marker => marker.visible = false);
                return; // Stop here if markers are globally disabled
            }

            if (!window.Bokeh || !window.Bokeh.Models) {
                console.error("CRITICAL: window.Bokeh.Models is not available. BokehJS may not be loaded correctly.");
                return;
            }

            const existingMarkersById = new Map();
            this.markerModels.forEach(marker => {
                if (Number.isFinite(marker.__markerId)) {
                    existingMarkersById.set(marker.__markerId, marker);
                } else {
                    existingMarkersById.set(marker.location, marker);
                }
                marker.visible = false;
            });

            const nextMarkers = [];
            const markerList = Array.isArray(markers) ? markers : [];
            markerList.forEach(markerState => {
                const timestamp = Number(markerState?.timestamp);
                if (!Number.isFinite(timestamp)) {
                    return;
                }

                const markerId = Number(markerState?.id);
                const markerColor = markerState?.color;
                const isSelected = Number.isFinite(selectedMarkerId) && markerId === selectedMarkerId;

                let marker = Number.isFinite(markerId)
                    ? existingMarkersById.get(markerId)
                    : existingMarkersById.get(timestamp);
                if (!marker) {
                    const doc = Bokeh.documents[0];
                    if (!doc) {
                        console.error("[Chart.syncMarkers] Bokeh document not available for creating Span markers");
                        return;
                    }

                    const Span = Bokeh.Models.get("Span");
                    if (!Span) {
                        console.error("[Chart.syncMarkers] Could not retrieve Span model constructor from Bokeh.Models.");
                        return;
                    }

                    try {
                        marker = new Span({
                            location: timestamp,
                            dimension: 'height',
                            line_color: normalizeMarkerColor(markerColor),
                            line_width: UNSELECTED_MARKER_LINE_WIDTH,
                            line_alpha: UNSELECTED_MARKER_LINE_ALPHA,
                            level: 'underlay',
                            visible: true,
                            name: `marker_${this.name}_${timestamp}`
                        });
                        
                        
                        // Add to chart layout first
                        this.model.add_layout(marker);

                        try {
                            doc.add_root(marker);
                            console.log("[Chart.syncMarkers] Added marker to document root"); // DEBUG
                        } catch (error) {
                            console.error("[Chart.syncMarkers] Failed to add marker to document root:", error);
                            // Then add to document root if in live mode
                            // This is needed for Bokeh's view system to work properly
                            if (doc.session) {
                                console.log("[Chart.syncMarkers] Adding marker to document root"); // DEBUG
                                doc.add_root(marker);
                            } else {
                                console.log("[Chart.syncMarkers] Document session not available, skipping document root addition"); // DEBUG
                            }
                        }
                    } catch (error) {
                        console.error(`[Chart.syncMarkers] Failed to create/add marker for chart ${this.name}:`, error);
                        console.error('[Chart.syncMarkers] Stack trace:', error.stack);
                        return;
                    }
                } else {
                    marker.location = timestamp;
                    marker.visible = true;
                }

                marker.__markerId = Number.isFinite(markerId) ? markerId : null;
                styleMarkerSpan(marker, markerColor, isSelected);
                nextMarkers.push(marker);
            });

            // Remove markers that are no longer in state
            const doc = Bokeh.documents[0];
            this.markerModels.forEach(marker => {
                if (!nextMarkers.includes(marker)) {
                    try {
                        if (this.model && typeof this.model.remove_layout === 'function') {
                            this.model.remove_layout(marker);
                        }
                        if (doc && doc.session && typeof doc.remove_root === 'function') {
                            doc.remove_root(marker);
                        }
                    } catch (error) {
                        console.warn(`[Chart.syncMarkers] Failed to remove marker from chart ${this.name}:`, error);
                    }
                }
            });

            this.markerModels = nextMarkers;

            if (this.model && typeof this.model.request_render === 'function') {
                this.model.request_render();
            }

            if (this.source && this.source.change && typeof this.source.change.emit === 'function') {
                this.source.change.emit();
            }
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
                    this.model.add_glyph(renderer);
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
        }

        setDisplayName(name) {
            if (typeof name === 'string' && name.trim()) {
                this.displayName = name.trim();
            } else {
                this.displayName = this.positionId;
            }
        }

        update(activeLineData, displayDetails) {
            this.activeData = activeLineData;
            this.source.data = activeLineData;
            this.lastDisplayDetails = displayDetails || { reason: '' };
            // The 'reason' now contains the full suffix, including leading spaces/parentheses
            const suffix = this.lastDisplayDetails.reason || '';
            const baseName = this.displayName || this.positionId;
            this.model.title.text = `${baseName} - Time History${suffix}`;
            this.render();
        }

        getLabelText(timestamp) {
            if (!this.activeData?.Datetime) return "Data N/A";
            const idx = app.utils.findAssociatedDateIndex(this.activeData, timestamp);
            if (idx === -1) return "No data point";

            const date = new Date(this.activeData.Datetime[idx]);
            let label_text = `Time: ${date.toLocaleString()}\n`;
            for (const key in this.activeData) {
                if (key !== 'Datetime' && key !== 'index') {
                    const value = this.activeData[key][idx];
                    const formatted_value = parseFloat(value).toFixed(1);
                    const unit = (key.startsWith('L') || key.includes('eq')) ? ' dB' : '';
                    label_text += `${key}: ${formatted_value}${unit}\n`;
                }
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
            // The 'reason' now contains the full suffix, including leading spaces/parentheses
            const suffix = this.lastDisplayDetails.reason || '';
            const baseName = this.displayName || this.positionId;
            this.model.title.text = `${baseName} - ${selectedParameter} Spectrogram${suffix}`;

            const replacement = activeSpectralData?.source_replacement;
            if (replacement && this.imageRenderer) {
                const glyph = this.imageRenderer.glyph;

                // The image data MUST be updated first, using our special function.
                _updateBokehImageData(this.source.data.image[0], replacement.image[0]);

                // Update the glyph's position and size on the "canvas"
                glyph.x = replacement.x[0];
                glyph.dw = replacement.dw[0];

                // Handle frequency slicing by updating plot range but keeping original glyph positioning
                if (replacement.y_range_start !== undefined && replacement.y_range_end !== undefined) {

                    // CRITICAL: Keep original glyph positioning to match image data layout
                    glyph.y = replacement.y[0];  // Original image position (matches data layout)
                    glyph.dh = replacement.dh[0]; // Original image height (matches data layout)

                    // Let the plot range crop the view to show only visible frequencies
                    this.model.y_range.start = replacement.y_range_start;
                    this.model.y_range.end = replacement.y_range_end;
                } else {
                    // Fallback to original glyph positioning if no frequency slicing
                    glyph.y = replacement.y[0];
                    glyph.dh = replacement.dh[0];
                }

                // Update the y-axis ticks to only show labels for the visible range (if frequency slicing was applied)
                if (replacement.visible_freq_indices && replacement.visible_frequency_labels && this.model.yaxis && this.model.yaxis.ticker) {
                    this.model.yaxis.ticker.ticks = replacement.visible_freq_indices;
                    this.model.yaxis.major_label_overrides = {}; // Clear old labels first
                    replacement.visible_freq_indices.forEach((tickIndex, i) => {
                        // Recreate label from label string (e.g., "5000 Hz" -> "5000")
                        const labelText = replacement.visible_frequency_labels[i].split(' ')[0];
                        this.model.yaxis.major_label_overrides[tickIndex] = labelText;
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
                const lineDetails = displayDetails.line || this.timeSeriesChart.lastDisplayDetails || { reason: '' };
                this.timeSeriesChart.update(activeLineData, lineDetails);
            }
            if (this.spectrogramChart) {
                this.spectrogramChart.setDisplayName(this.displayName);
                const specDetails = displayDetails.spec || this.spectrogramChart.lastDisplayDetails || { reason: '' };
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