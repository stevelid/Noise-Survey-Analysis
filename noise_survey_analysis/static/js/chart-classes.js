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
            this.regionAnnotations = new Map();
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
        syncMarkers(masterTimestampList, areMarkersEnabled) {
            // First, handle the global visibility toggle
            if (!areMarkersEnabled) {
                this.markerModels.forEach(marker => marker.visible = false);
                return; // Stop here if markers are globally disabled
            }

            const existingTimestamps = this.markerModels.map(m => m.location);
            const timestampsToAdd = masterTimestampList.filter(t => !existingTimestamps.includes(t));
            const markersToRemove = this.markerModels.filter(m => !masterTimestampList.includes(m.location));

            // Add new markers using Bokeh document API
            timestampsToAdd.forEach(timestamp => {
                const doc = Bokeh.documents[0];
                if (!doc) {
                    console.error("Bokeh document not available for creating Span markers");
                    return;
                }
                
                const newMarker = doc.add_model(
                    doc.create_model('Span', {
                        location: timestamp,
                        dimension: 'height',
                        line_color: 'orange',
                        line_width: 2,
                        line_alpha: 0.7,
                        level: 'underlay',
                        visible: true,
                        name: `marker_${this.name}_${timestamp}`
                    })
                );
                this.model.add_layout(newMarker);
                this.markerModels.push(newMarker);
            });

            // Remove old markers and update the internal list
            markersToRemove.forEach(markerModel => this.model.remove_layout(markerModel));
            this.markerModels = this.markerModels.filter(m => !markersToRemove.includes(m));

            // Ensure all remaining markers are visible
            this.markerModels.forEach(marker => marker.visible = true);

            const hasChanges = timestampsToAdd.length > 0 || markersToRemove.length > 0;
            if (hasChanges && this.source) {
                this.render();
            }
        }

        syncRegions(regionList, selectedId) {
            if (!Array.isArray(regionList)) return;
            const doc = window.Bokeh?.documents?.[0];
            if (!doc) return;

            const seen = new Set();
            regionList.forEach(region => {
                if (!region || region.positionId !== this.positionId) return;
                seen.add(region.id);
                let annotation = this.regionAnnotations.get(region.id);
                if (!annotation) {
                    annotation = doc.add_model(doc.create_model('BoxAnnotation', {
                        left: region.start,
                        right: region.end,
                        fill_alpha: 0.1,
                        fill_color: '#1e88e5',
                        line_color: '#1e88e5',
                        line_alpha: 0.6,
                        line_width: 1,
                        level: 'underlay',
                        name: `region_${this.name}_${region.id}`
                    }));
                    this.model.add_layout(annotation);
                    this.regionAnnotations.set(region.id, annotation);
                }

                annotation.left = region.start;
                annotation.right = region.end;
                annotation.fill_alpha = region.id === selectedId ? 0.2 : 0.08;
                annotation.line_width = region.id === selectedId ? 3 : 1;
                annotation.visible = true;
            });

            this.regionAnnotations.forEach((annotation, id) => {
                if (!seen.has(id)) {
                    this.model.remove_layout(annotation);
                    this.regionAnnotations.delete(id);
                }
            });
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
        }

        update(activeLineData, displayDetails) {
            this.activeData = activeLineData;
            this.source.data = activeLineData;
            // The 'reason' now contains the full suffix, including leading spaces/parentheses
            this.model.title.text = `${this.positionId} - Time History${displayDetails.reason}`;
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
        }

        update(activeSpectralData, displayDetails, selectedParameter) {
            // The 'reason' now contains the full suffix, including leading spaces/parentheses
            this.model.title.text = `${this.positionId} - ${selectedParameter} Spectrogram${displayDetails.reason}`;

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

        updateAllCharts(state, dataCache) {
            const activeLineData = dataCache.activeLineData[this.id];
            const activeSpecData = dataCache.activeSpectralData[this.id];
            if (this.timeSeriesChart) {
                this.timeSeriesChart.update(activeLineData, state.view.displayDetails[this.id].line);
            }
            if (this.spectrogramChart) {
                this.spectrogramChart.update(activeSpecData, state.view.displayDetails[this.id].spec, state.view.selectedParameter);
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


