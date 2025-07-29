console.log("[DEBUG] app.js: Script loading started");

window.NoiseSurveyApp = (function () {
    'use strict';

    console.log("[DEBUG] NoiseSurveyApp: IIFE called");

    // =======================================================================================
    //           CONSTANTS
    // =======================================================================================

    const MAX_LINE_POINTS_TO_RENDER = 5000;
    const MAX_SPECTRAL_POINTS_TO_RENDER = 5000;

    // =======================================================================================
    //           CLASSES - Encapsulating Logic and Data
    // =======================================================================================

    class Chart {
        constructor(chartModel, sourceModel, labelModel, hoverLineModel, positionId) {
            this.model = chartModel;
            this.source = sourceModel;
            this.labelModel = labelModel;
            this.hoverLineModel = hoverLineModel;
            this.name = chartModel.name;
            this.positionId = positionId; // Store the position ID
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

        // Marker methods
        renderMarkers(timestamps) {
            if (!_state.markers.enabled) {
                this.hideAllMarkers();
                return;
            }
            
            // Get the marker_lines array from the Python component
            const markerLines = this.getMarkerLines();
            if (!markerLines) return;
            
            // Hide all existing markers first
            markerLines.forEach(marker => marker.visible = false);
            
            // Show markers for each timestamp
            timestamps.forEach((timestamp, index) => {
                if (index < markerLines.length) {
                    markerLines[index].location = timestamp;
                    markerLines[index].visible = true;
                } else {
                    // Create new marker if needed (dynamically)
                    this.createMarker(timestamp);
                }
            });
        }
        
        hideAllMarkers() {
            const markerLines = this.getMarkerLines();
            if (markerLines) {
                markerLines.forEach(marker => marker.visible = false);
            }
        }
        
        getMarkerLines() {
            // This will be overridden to access the Python component's marker_lines
            return null;
        }
        
        createMarker(timestamp) {
            // This will be overridden to create new markers dynamically
            console.warn('createMarker not implemented for this chart type');
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
            const idx = _findAssociatedDateIndex(this.activeData, timestamp);
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
        
        getMarkerLines() {
            // Access the marker_lines array from the Python TimeSeriesComponent
            const componentName = `${this.positionId}_timeseries`;
            const component = _models.components?.[componentName];
            return component?.marker_lines || null;
        }
        
        createMarker(timestamp) {
            // Create a new marker Span dynamically
            const componentName = `${this.positionId}_timeseries`;
            const component = _models.components?.[componentName];
            if (!component) return;
            
            // Create new Span for marker (orange, slightly transparent, behind other lines)
            const newMarker = new Bokeh.models.Span({
                location: timestamp,
                dimension: 'height',
                line_color: 'orange',
                line_width: 2,
                line_alpha: 0.7,
                level: 'underlay', // Behind other elements
                visible: true,
                name: `marker_${this.name}_${Date.now()}`
            });
            
            // Add to the figure and track it
            this.model.add_layout(newMarker);
            if (!component.marker_lines) component.marker_lines = [];
            component.marker_lines.push(newMarker);
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

                updateBokehImageData(this.source.data.image[0], replacement.image[0]);

                glyph.x = replacement.x[0];
                glyph.y = replacement.y[0];
                glyph.dw = replacement.dw[0];
                glyph.dh = replacement.dh[0];
                this.render();
                this.setVisible(true);
            }
            else {
                this.setVisible(false);
            }
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
        
        getMarkerLines() {
            // Access the marker_lines array from the Python SpectrogramComponent
            const componentName = `${this.positionId}_spectrogram`;
            const component = _models.components?.[componentName];
            return component?.marker_lines || null;
        }
        
        createMarker(timestamp) {
            // Create a new marker Span dynamically
            const componentName = `${this.positionId}_spectrogram`;
            const component = _models.components?.[componentName];
            if (!component) return;
            
            // Create new Span for marker (orange, slightly transparent, behind other lines)
            const newMarker = new Bokeh.models.Span({
                location: timestamp,
                dimension: 'height',
                line_color: 'orange',
                line_width: 2,
                line_alpha: 0.7,
                level: 'underlay', // Behind other elements
                visible: true,
                name: `marker_${this.name}_${Date.now()}`
            });
            
            // Add to the figure and track it
            this.model.add_layout(newMarker);
            if (!component.marker_lines) component.marker_lines = [];
            component.marker_lines.push(newMarker);
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

        updateAllCharts(state) {
            const activeLineData = state.data.activeLineData[this.id];
            const activeSpecData = state.data.activeSpectralData[this.id];
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

    // =======================================================================================
    //           PRIVATE MODELS & STATES
    // =======================================================================================

    let _models = {};
    let _state = {
        data: {
            activeLineData: {},
            activeSpectralData: {},
            activeFreqBarData: {},
        },
        view: {
            availablePositions: [],
            globalViewType: 'log',
            selectedParameter: 'LZeq',
            viewport: { min: null, max: null },
            chartVisibility: {},
            displayDetails: {},
            hoverEnabled: true,
        },
        interaction: {
            tap: { isActive: false, timestamp: null, position: null, sourceChartName: null },
            hover: { isActive: false, timestamp: null, position: null, sourceChartName: null, spec_y: null },
            keyboard: { enabled: false, stepSizeMs: 300000 },
        },
        markers: {
            timestamps: [],  // Array of marker timestamps
            enabled: true    // Global toggle for marker visibility
        },
        audio: {
            isPlaying: false,
            activePositionId: null,
            currentTime: 0,
            playbackRate: 1.0,
            volumeBoost: false,
        },
    };
    let _controllers = {
        positions: {},
        chartsByName: new Map(),
    };

    // =======================================================================================
    //           UTILITY FUNCTIONS
    // =======================================================================================

    /**
     * Calculates an appropriate keyboard navigation step size based on the total
     * time duration of the currently active dataset for the position with focus.
     * The position with focus is determined by checking audio state first, then tap state.
     */
    function calculateStepSize() {

        const positionId = _state.audio.activePositionId || _state.interaction.tap.position;

        if (!positionId) {
            //console.log("[DEBUG] Cannot calculate step size: No active position from audio or tap. State is:", _state);
            return; // Exit if no position has focus
        }

        const activeData = _state.data.activeLineData[positionId];
        if (!activeData || !activeData.Datetime || activeData.Datetime.length < 2) {
            // Can't calculate if there's no data, so leave the step size as it is.
            return;
        }

        const dataDuration = activeData.Datetime[activeData.Datetime.length - 1] - activeData.Datetime[0];

        let newStep = (activeData.Datetime[10] - activeData.Datetime[5]) / 5;

        const oneSecond = 1000;
        const oneHour = 3600000;
        newStep = Math.max(oneSecond, Math.min(newStep, oneHour));

        _state.interaction.keyboard.stepSizeMs = newStep;
        //console.log(`[DEBUG] Step size updated for '${positionId}' to ${Math.round(newStep / 1000)}s`);
    }

    /**
    * Safely updates the data of an existing Bokeh image data array in place.
    * This preserves the array's type and reference, ensuring Bokeh detects the change.
    * @param {TypedArray} existingImageData - The array from the Bokeh data source (e.g., source.data.image[0]).
    * @param {TypedArray} newData - The new data chunk to copy into the existing array.
    */
    function updateBokehImageData(existingImageData, newData) {
        if (existingImageData.length !== newData.length) {
            console.error(`Mismatched image data lengths. Existing: ${existingImageData.length}, New: ${newData.length}. Cannot update.`);
            return;
        }
        // This element-by-element copy mutates the original array, which is what Bokeh needs.
        for (let i = 0; i < newData.length; i++) {
            existingImageData[i] = newData[i];
        }
    }

    function _extractTimeChunkFromFlatData(flatData, n_freqs, n_times_total, start_time_idx, chunk_time_length) {
        const typedFlatData = (flatData instanceof Float32Array) ? flatData : new Float32Array(flatData);
        const chunk_data = new Float32Array(n_freqs * chunk_time_length);
        const end_time_idx = Math.min(start_time_idx + chunk_time_length, n_times_total);
        const actual_slice_width = end_time_idx - start_time_idx;
        for (let i = 0; i < n_freqs; i++) {
            const row_offset = i * n_times_total;
            const slice_start_in_flat_array = row_offset + start_time_idx;
            const row_slice = typedFlatData.subarray(slice_start_in_flat_array, slice_start_in_flat_array + actual_slice_width);
            chunk_data.set(row_slice, i * chunk_time_length);
        }
        return chunk_data;
    }

    function _getChartPositionByName(chartName) {
        if (!chartName) return null;
        const parts = chartName.split('_');
        if (parts.length >= 2) {
            // Simply return the parsed position name, e.g., 'East' or 'West'
            return parts[1];
        }
        return null;
    }

    function _findAssociatedDateIndex(activeData, timestamp) {
        for (let i = activeData.Datetime.length - 1; i >= 0; i--) {
            if (activeData.Datetime[i] <= timestamp) return i;
        }
        return -1;
    }

    function seek(time) {
        if (!_models.audio_control_source) {
            console.warn("Audio controls are disabled in static mode.");
            return;
        }
        if (_state.audio.activePositionId === null || _state.audio.activePositionId === undefined) return;
        _models.audio_control_source.data = { command: ['seek'], position_id: [_state.audio.activePositionId], value: [time] };
        _models.audio_control_source.change.emit();
    }

    function debounce(func, wait) {
        let timeout;
        return (...args) => {
            clearTimeout(timeout);
            timeout = setTimeout(() => func(...args), wait);
        };
    }

    // =======================================================================================
    //           EVENT CONTROLLERS
    // =======================================================================================

    function handleTap(cb_obj) {
        const chartName = cb_obj.origin.name;
        if (chartName === 'frequency_bar') return;
        
        // Check if Ctrl key is pressed for marker removal
        if (cb_obj.event && cb_obj.event.ctrlKey) {
            removeMarkerNear(cb_obj.x);
            return;
        }
        
        _dispatchAction({
            type: 'TAP',
            payload: {
                timestamp: cb_obj.x,
                position: _getChartPositionByName(chartName),
                sourceChartName: chartName
            }
        });
    }

    function handleChartHover(cb_data, chartName) {
        const geometry = cb_data.geometry;
        const isActive = geometry && Number.isFinite(geometry.x);
        if (isActive) {
            _dispatchAction({
                type: 'HOVER',
                payload: {
                    isActive: true,
                    sourceChartName: chartName,
                    timestamp: geometry.x,
                    spec_y: geometry.y,
                    position: _getChartPositionByName(chartName),
                }
            });
        }
        else {
            _dispatchAction({ type: 'HOVER', payload: { isActive: false } });
        }
    }

    const debouncedRangeUpdate = debounce((cb_obj) => {
        _dispatchAction({
            type: 'VIEWPORT_CHANGE',
            payload: {
                min: cb_obj.start,
                max: cb_obj.end
            }
        });
    }, 200); // Debounce by 200ms

    function handleRangeUpdate(cb_obj) {
        debouncedRangeUpdate(cb_obj);
    }

    function handleDoubleClick(cb_obj) {
        const chartName = cb_obj.origin.name;
        if (chartName === 'frequency_bar') return;
        
        const timestamp = cb_obj.x;
        addMarker(timestamp);
    }
    
    function handleRightClick(cb_obj) {
        const chartName = cb_obj.origin.name;
        if (chartName === 'frequency_bar') return;
        
        const timestamp = cb_obj.x;
        removeMarkerNear(timestamp);
    }
    
    function addMarker(timestamp) {
        // Add marker to global state
        if (!_state.markers.timestamps.includes(timestamp)) {
            _state.markers.timestamps.push(timestamp);
            _state.markers.timestamps.sort((a, b) => a - b); // Keep sorted
            
            // Create marker on all charts
            _controllers.chartsByName.forEach(chart => {
                chart.createMarker(timestamp);
            });
            
            console.log(`[Marker] Added marker at ${new Date(timestamp).toLocaleString()}`);
        }
    }
    
    function removeMarkerNear(timestamp) {
        // Find the closest marker within a reasonable threshold
        const threshold = 60000; // 1 minute threshold
        let closestIndex = -1;
        let closestDistance = Infinity;
        
        _state.markers.timestamps.forEach((markerTime, index) => {
            const distance = Math.abs(markerTime - timestamp);
            if (distance < threshold && distance < closestDistance) {
                closestDistance = distance;
                closestIndex = index;
            }
        });
        
        if (closestIndex !== -1) {
            const removedTimestamp = _state.markers.timestamps[closestIndex];
            _state.markers.timestamps.splice(closestIndex, 1);
            
            // Remove marker from all charts
            _controllers.chartsByName.forEach(chart => {
                const markerLines = chart.getMarkerLines();
                if (markerLines) {
                    const markerToRemove = markerLines.find(marker => 
                        Math.abs(marker.location - removedTimestamp) < threshold
                    );
                    if (markerToRemove) {
                        markerToRemove.visible = false;
                    }
                }
            });
            
            console.log(`[Marker] Removed marker at ${new Date(removedTimestamp).toLocaleString()}`);
        }
    }
    
    function clearAllMarkers() {
        // Clear all markers from global state
        const markerCount = _state.markers.timestamps.length;
        _state.markers.timestamps = [];
        
        // Hide all markers on all charts
        _controllers.chartsByName.forEach(chart => {
            chart.hideAllMarkers();
        });
        
        console.log(`[Marker] Cleared ${markerCount} markers`);
    }

    function handleParameterChange(value) {
        _dispatchAction({
            type: 'PARAM_CHANGE',
            payload: {
                parameter: value
            }
        });
    }

    function handleViewToggle(isActive, toggleWidget) {
        const newViewType = isActive ? 'log' : 'overview';
        _dispatchAction({
            type: 'VIEW_TOGGLE',
            payload: {
                newViewType: newViewType
            }
        });
        if (toggleWidget) {
            toggleWidget.label = isActive ? "Log View Enabled" : "Log View Disabled";
        }
    }

    function handleHoverToggle(isActive, toggleWidget) {
        _state.view.hoverEnabled = isActive;
        if (toggleWidget) {
            toggleWidget.label = isActive ? "Hover Enabled" : "Hover Disabled";
        }
        // If hover is disabled, immediately hide all hover effects
        if (!isActive) {
            _controllers.chartsByName.forEach(chart => {
                chart.hideHoverLine();
                chart.hideLabel();
            });
        }
    }

    function handleVisibilityChange(cb_obj, chartName) {
        const isVisible = Array.isArray(cb_obj.active) ? cb_obj.active.includes(0) : Boolean(cb_obj.active);
        _dispatchAction({ type: 'VISIBILITY_CHANGE', payload: { chartName: chartName, isVisible: isVisible } });
    }

    function handleAudioStatusUpdate() {
        const status = _models.audio_status_source.data;
        _dispatchAction({ type: 'AUDIO_UPDATE', payload: { status: status } });
    }

    function togglePlayPause(positionId) {
        if (!_models.audio_control_source) {
            console.warn("Audio controls are disabled in static mode.");
            return;
        }
        console.log("Toggle play/pause for position: " + positionId);
        const command = _state.audio.isPlaying && _state.audio.activePositionId === positionId ? 'pause' : 'play';
        _models.audio_control_source.data = { command: [command], position_id: [positionId], value: [_state.interaction.tap.timestamp] };
        _models.audio_control_source.change.emit();
    }

    function handleKeyPress(e) {
        const targetTagName = e.target.tagName.toLowerCase();
        if (targetTagName === 'input' || targetTagName === 'textarea' || targetTagName === 'select') return;

        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            e.preventDefault();
            let currentX = _state.interaction.tap.timestamp || _state.view.viewport.min || 0;
            const step = _state.interaction.keyboard.stepSizeMs || 300000;
            let newX = e.key === 'ArrowLeft' ? currentX - step : currentX + step;
            newX = Math.max(_state.view.viewport.min, Math.min(_state.view.viewport.max, newX));

            _dispatchAction({
                type: 'KEY_NAV',
                payload: {
                    newTimestamp: newX
                }
            });
        }
    }


    function setupKeyboardNavigation() {
        if (!_state.interaction.keyboard.enabled) {
            document.addEventListener('keydown', handleKeyPress);
            _state.interaction.keyboard.enabled = true;
        }
    }


    // =======================================================================================
    //           STATE MANAGEMENT & RENDERING ORCHESTRATION
    // =======================================================================================

    /**
     * Executes the "heavy" update path. This involves re-calculating the data
     * to display and re-rendering the primary chart content. It should be called
     * for actions that change the fundamental view of the data (zoom, parameter change, etc.).
     */
    function _performHeavyUpdate() {
        //console.log("[DEBUG] Executing HEAVY update path.");
        _updateActiveData();      // 1. Re-process data based on new state (e.g., viewport)
        _renderPrimaryCharts();   // 2. Push new data to the main chart models
        calculateStepSize();      // 3. Recalculate step size as data context might have changed
        _renderOverlays();        // 4. Update interactive lines and labels
        renderFrequencyBar();     // 5. Update the frequency bar with the new data context
    }

    /**
     * Executes the "light" update path. This only updates overlays, labels, and
     * the frequency bar based on user interaction (tap, hover, audio playback).
     * It avoids the costly data recalculation and primary chart rendering.
     */
    function _performLightUpdate() {
        //console.log("[DEBUG] Executing LIGHT update path.");
        calculateStepSize(); // Recalculate step size as tap/key_nav can change the focused position

        _updateActiveFreqBarData(); // Update the frequency bar data with the new interaction context

        _renderOverlays();    // Update interactive lines and labels
        renderFrequencyBar(); // re-render the frequency bar with the new interaction context
    }


    /**
     * The central dispatcher for all application actions.
     * It orchestrates state updates, data processing, and UI rendering.
     * @param {object} action - An object describing the action (e.g., { type: 'TAP', payload: { ... } })
     */
    function _dispatchAction(action) {
        //console.log(`[DEBUG] Dispatching action: ${action.type}`, action.payload);

        // --- Step 1: Update the _state object based on the action (This is the "Reducer") ---
        switch (action.type) {
            case 'TAP':
                _state.interaction.tap = {
                    isActive: true,
                    timestamp: action.payload.timestamp,
                    position: action.payload.position,
                    sourceChartName: action.payload.sourceChartName
                };
                // Clear hover state on tap to prevent conflicting overlays
                _state.interaction.hover.isActive = false;
                break;
            case 'HOVER':
                _state.interaction.hover = action.payload;
                break;
            case 'VIEWPORT_CHANGE':
                _state.view.viewport = action.payload;
                break;
            case 'PARAM_CHANGE':
                _state.view.selectedParameter = action.payload.parameter;
                break;
            case 'VIEW_TOGGLE':
                _state.view.globalViewType = action.payload.newViewType;
                break;
            case 'VISIBILITY_CHANGE':
                _state.view.chartVisibility[action.payload.chartName] = action.payload.isVisible;
                // If a chart is hidden, ensure its hover div is also hidden
                const chart = _controllers.chartsByName.get(action.payload.chartName);
                if (chart instanceof SpectrogramChart && !action.payload.isVisible) {
                    chart.hoverDivModel.visible = false;
                }
                break;
            case 'AUDIO_UPDATE':
                _state.audio.isPlaying = action.payload.status.is_playing[0];
                _state.audio.activePositionId = action.payload.status.active_position_id[0];
                _state.audio.currentTime = action.payload.status.current_time[0];
                _state.audio.playbackRate = action.payload.status.playback_rate[0];
                _state.audio.volumeBoost = action.payload.status.volume_boost[0];

                // If audio is playing, sync the tap/cursor position to the audio time
                if (_state.audio.isPlaying) {
                    _state.interaction.tap.timestamp = _state.audio.currentTime;
                    _state.interaction.tap.isActive = true;
                    _state.interaction.tap.position = _state.audio.activePositionId;
                }
                break;
            case 'KEY_NAV':
                _state.interaction.tap.timestamp = action.payload.newTimestamp;
                _state.interaction.tap.isActive = true;
                // If no position is active, infer from the first available position
                if (!_state.interaction.tap.position && _state.view.availablePositions.length > 0) {
                    _state.interaction.tap.position = _state.view.availablePositions[0];
                }
                break;
            case 'INITIAL_LOAD':
                // No specific state change needed; its purpose is to trigger a heavy update.
                break;
            default:
                console.warn(`[DEBUG] Unknown action type: ${action.type}`);
                return;
        }

        // --- Step 2: Decide which rendering path to take and execute it ---
        const isHeavyUpdate = ['VIEWPORT_CHANGE', 'PARAM_CHANGE', 'VIEW_TOGGLE', 'INITIAL_LOAD', 'VISIBILITY_CHANGE'].includes(action.type);

        if (isHeavyUpdate) {
            _performHeavyUpdate();
        }
        else {
            // If it's not a heavy update, it's a light one (e.g., TAP, HOVER, AUDIO_UPDATE, KEY_NAV).
            _performLightUpdate();
        }

        // --- Step 3: Handle specific side effects that occur after rendering ---
        if (action.type === 'TAP' || action.type === 'KEY_NAV') {
            const seekTime = action.payload.newTimestamp || action.payload.timestamp;
            seek(seekTime);
        }
        if (action.type === 'AUDIO_UPDATE') {
            renderaudio_controls(); // This only needs to run when audio status itself changes.
        }
    }

        /**
         * _updateActiveData()
         * 
         * Updates the active data for all visible charts. This involves:
         * 
         * 1. Updating the active line chart data for each visible chart.
         * 2. Updating the active spectrogram data for each visible chart.
         * 3. Determining the context (position and timestamp) for the frequency bar
         *    from the currently active interaction (hover or tap), and calling
         *    _updateActiveFreqBarData() to update the bar chart's data.
         */
    function _updateActiveData() {
        _state.view.availablePositions.forEach(position => {
            const tsChartName = `figure_${position}_timeseries`;
            const specChartName = `figure_${position}_spectrogram`;

            // Only process data for charts that are currently visible
            if (_state.view.chartVisibility[tsChartName] || _state.view.chartVisibility[specChartName]) {
                _updateActiveLineChartData(position, _state.view.globalViewType);
                _updateActiveSpectralData(position, _state.view.globalViewType, _state.view.selectedParameter);
            }
        });

        // If neither is active, timestamp will be null and the function will handle it.
        _updateActiveFreqBarData();
    }

    /**
     * Updates the active line chart data for a given position based on the view type.
     * 
     * This function determines whether to use 'overview' or 'log' data for the line chart 
     * based on the provided viewType and the current viewport. It updates the activeLineData 
     * in the state with the selected data and sets the display details for the position.
     * 
     * @param {string} position - The position identifier for which the line chart data is updated.
     * @param {string} viewType - The type of view ('overview' or 'log') to determine data selection.
     */
    function _updateActiveLineChartData(position, viewType) {
        const sourceData = _models.timeSeriesSources[position];
        const overviewData = sourceData?.overview?.data;
        const logData = sourceData?.log?.data;
        const hasLogData = logData && logData.Datetime && logData.Datetime.length > 0;

        let displayDetails = { type: 'overview', reason: ' (Overview)' }; // Default reason

        if (viewType === 'log') {
            if (hasLogData) {
                const { min, max } = _state.view.viewport;
                const startIndex = logData.Datetime.findIndex(t => t >= min);
                const endIndex = logData.Datetime.findLastIndex(t => t <= max);
                const pointsInView = (startIndex !== -1 && endIndex !== -1) ? endIndex - startIndex : 0;

                if (pointsInView > MAX_LINE_POINTS_TO_RENDER) {
                    // Log view is active, but user is too zoomed out
                    _state.data.activeLineData[position] = overviewData || {};
                    displayDetails = { type: 'overview', reason: ' - Zoom in for Log Data' };
                } else {
                    // Happy path: Show a chunk of log data
                    const buffer = Math.floor(pointsInView * 0.5);
                    const sliceStart = Math.max(0, startIndex - buffer);
                    const sliceEnd = Math.min(logData.Datetime.length, endIndex + buffer + 1);
                    const chunk = {};
                    for (const key in logData) {
                        chunk[key] = logData[key].slice(sliceStart, sliceEnd);
                    }
                    _state.data.activeLineData[position] = chunk;
                    displayDetails = { type: 'log', reason: ' (Log Data)' };
                }
            } else {
                // Log view is active, but no log data exists for this position
                _state.data.activeLineData[position] = overviewData || {}; // Show overview as a fallback
                displayDetails = { type: 'overview', reason: ' (No Log Data Available)' };
            }
        } else {
            // Overview view is explicitly active
            _state.data.activeLineData[position] = overviewData || {};
            displayDetails = { type: 'overview', reason: ' (Overview)' };
        }

        _state.view.displayDetails[position].line = displayDetails;
    }

    /**
     * Updates the active spectrogram data for a given position based on the view type and parameter.
     * 
     * This function determines whether to use 'overview' or 'log' data for the spectrogram based on 
     * the provided viewType and the current viewport. It updates the activeSpectralData in the state 
     * with the selected data and sets the display details for the position.
     * 
     * @param {string} position - The position identifier for which the spectrogram data is updated.
     * @param {string} viewType - The type of view ('overview' or 'log') to determine data selection.
     * @param {string} parameter - The parameter to be displayed in the spectrogram.
     */
    function _updateActiveSpectralData(position, viewType, parameter) {
        const positionGlyphData = _models.preparedGlyphData[position];
        const overviewData = positionGlyphData?.overview?.prepared_params?.[parameter];
        const logData = positionGlyphData?.log?.prepared_params?.[parameter];
        const hasLogData = logData && logData.times_ms && logData.times_ms.length > 0;

        let finalDataToUse, finalGlyphData, displayReason;

        if (viewType === 'log') {
            if (hasLogData) {
                const pointsInView = Math.floor((_state.view.viewport.max - _state.view.viewport.min) / logData.time_step);

                if (pointsInView <= MAX_SPECTRAL_POINTS_TO_RENDER) {
                    // Happy Path: Show chunked LOG data
                    finalDataToUse = logData;
                    displayReason = ' (Log Data)'; // Explicitly label the log view

                    const { n_times, chunk_time_length, times_ms, time_step, levels_flat_transposed, n_freqs } = finalDataToUse;
                    const { min, max } = _state.view.viewport;
                    const targetChunkStartTimeStamp = (max + min) / 2 - (chunk_time_length * time_step / 2);
                    
                    // A more robust way to find the index, defaulting to 0 if the view is before the data starts.
                    let chunkStartTimeIdx = times_ms.findIndex(t => t >= targetChunkStartTimeStamp);
                    if (chunkStartTimeIdx === -1) {
                         // If the view is past the end of the data, show the last possible chunk.
                        chunkStartTimeIdx = Math.max(0, n_times - chunk_time_length);
                    }

                    const chunk_image = _extractTimeChunkFromFlatData(levels_flat_transposed, n_freqs, n_times, chunkStartTimeIdx, chunk_time_length);

                    finalGlyphData = {
                        ...finalDataToUse.initial_glyph_data,
                        image: [chunk_image],
                        x: [times_ms[chunkStartTimeIdx]],
                        dw: [chunk_time_length * time_step],
                        times_ms: times_ms.slice(chunkStartTimeIdx, chunkStartTimeIdx + chunk_time_length),
                    };
                } else {
                    // Log view active, but too zoomed out
                    finalDataToUse = overviewData;
                    displayReason = ' - Zoom in for Log Data';
                    finalGlyphData = finalDataToUse ? { ...finalDataToUse.initial_glyph_data, times_ms: finalDataToUse.times_ms } : null;
                }
            } else {
                // Log view active, but no log data exists
                finalDataToUse = overviewData;
                displayReason = ' (No Log Data Available)';
                finalGlyphData = finalDataToUse ? { ...finalDataToUse.initial_glyph_data, times_ms: finalDataToUse.times_ms } : null;
            }
        } else {
            // Overview view is explicitly active
            finalDataToUse = overviewData;
            displayReason = ' (Overview)';
            finalGlyphData = finalDataToUse ? { ...finalDataToUse.initial_glyph_data, times_ms: finalDataToUse.times_ms } : null;
        }

        // --- Final state update ---
        if (finalGlyphData && finalDataToUse) {
            _state.data.activeSpectralData[position] = { ...finalDataToUse, source_replacement: finalGlyphData };
        } else {
            // This case handles when overviewData was also null in one of the fallback paths.
            _state.data.activeSpectralData[position] = { source_replacement: null, reason: 'No Data Available' };
            // If we ended up with no data, this reason overrides any previous one.
            displayReason = ' (No Data Available)';
        }
        _state.view.displayDetails[position].spec = { reason: displayReason };
    }


    /**
     * Updates the active frequency bar data based on the current interaction context.
     * 
     * This function determines the context (position and timestamp) for the frequency bar
     * from the currently active interaction (hover or tap), and calls _updateActiveFreqBarData()
     * to update the bar chart's data.
     */
    function _updateActiveFreqBarData() {
        const blankData = { levels: [], frequency_labels: [], sourceposition: '', timestamp: null, setBy: null, param: null };

        // --- Step 1: Determine the context and priority from the global state ---
        let position, timestamp, setBy;

        if (_state.interaction.hover.isActive) {
            // Priority 1: Active hover
            position = _state.interaction.hover.position;
            timestamp = _state.interaction.hover.timestamp;
            setBy = 'hover';
        }
        else if (_state.interaction.tap.isActive) {
            // Priority 2: Active tap (which may be driven by audio)
            position = _state.interaction.tap.position;
            timestamp = _state.interaction.tap.timestamp;
            setBy = _state.audio.isPlaying && _state.audio.activePositionId === position ? 'audio' : 'tap';
        }
        else {
            // No active interaction, so set to blank and exit
            _state.data.activeFreqBarData = blankData;
            return;
        }

        // If there's no valid context, exit
        if (!timestamp || !position) {
            _state.data.activeFreqBarData = blankData;
            return;
        }

        // --- Step 2: Fetch and process data based on the determined context ---
        const activeSpectralData = _state.data.activeSpectralData[position];
        if (!activeSpectralData?.times_ms?.length) {
            _state.data.activeFreqBarData = blankData;
            return;
        }

        const closestTimeIdx = activeSpectralData.times_ms.findLastIndex(time => time <= timestamp);
        if (closestTimeIdx === -1) {
            _state.data.activeFreqBarData = blankData;
            return;
        }

        const freqDataSlice = new Float32Array(activeSpectralData.n_freqs);
        for (let i = 0; i < activeSpectralData.n_freqs; i++) {
            // This logic for accessing the transposed flat array remains the same
            freqDataSlice[i] = activeSpectralData.levels_flat_transposed[i * activeSpectralData.n_times + closestTimeIdx];
        }

        _state.data.activeFreqBarData = {
            levels: Array.from(freqDataSlice).map(l => (l === null || isNaN(l)) ? 0 : l),
            frequency_labels: activeSpectralData.frequency_labels,
            sourceposition: position,
            timestamp: timestamp,
            setBy: setBy,
            param: _state.view.selectedParameter,
            dataViewType: _state.view.displayDetails[position]?.spec?.type || 'None'
        };
    }



    // =======================================================================================
    //           RENDERERS
    // =======================================================================================

    /**
     * Updates the primary data sources of the main charts.
     * This is a HEAVY operation and should only be called when the underlying
     * data view (zoom level, parameter, log/overview) changes.
     */
    function _renderPrimaryCharts() {
        for (const posId in _controllers.positions) {
            // Only update charts that are currently visible
            const tsChartName = `figure_${posId}_timeseries`;
            const specChartName = `figure_${posId}_spectrogram`;

            if (_state.view.chartVisibility[tsChartName] || _state.view.chartVisibility[specChartName]) {
                _controllers.positions[posId].updateAllCharts(_state);
            }
            else {
                // Ensure charts are hidden if not visible
                _controllers.positions[posId].charts.forEach(chart => {
                    chart.setVisible(false);
                    if (chart instanceof SpectrogramChart) {
                        chart.hoverDivModel.visible = false; // Also hide hover div
                    }
                });
            }
        }
    }

    /**
     * Updates lightweight UI overlays like lines and labels.
     * This is a LIGHT operation and can be called frequently.
     */
    function _renderOverlays() {
        renderTapLines();
        renderLabels();
        renderHoverEffects();
        renderMarkers();
    }

    // =======================================================================================
    //           RENDERERS
    // =======================================================================================

    function renderAllVisuals() {
        // This function is now deprecated. All rendering should go through _dispatchAction.
        // It's kept for backward compatibility during refactoring, but will be removed.
        console.warn("[DEBUG] renderAllVisuals() called. This function is deprecated. Use _dispatchAction instead.");
        _renderPrimaryCharts();
        _renderOverlays();
        renderFrequencyBar();
    }

    function renderHoverEffects() {
        const hoverState = _state.interaction.hover;

        // Update data for the bar chart based on hover
        _updateActiveFreqBarData(hoverState.position, hoverState.timestamp, 'hover');
        renderFrequencyBar();

        // Only render hover effects if hover is enabled
        if (_state.view.hoverEnabled) {
            _controllers.chartsByName.forEach(chart => {
                if (hoverState.isActive) {
                    chart.renderHoverLine(hoverState.timestamp);
                }
                else {
                    chart.hideHoverLine();
                }

                if (chart instanceof SpectrogramChart) {
                    chart.renderHoverDetails(hoverState, _state.data.activeFreqBarData);
                }
            });
        } else {
            // If hover is disabled, hide all hover lines
            _controllers.chartsByName.forEach(chart => {
                chart.hideHoverLine();
            });
        }

        // After updating hover effects, re-render the labels with the new context
        renderLabels();
    }

    function renderTapLines() {
        const { isActive, timestamp } = _state.interaction.tap;
        _models.clickLines.forEach(line => {
            if (line) {
                line.location = timestamp;
                line.visible = isActive;
            }
        });
    }

    function renderLabels() {
        const hoverState = _state.interaction.hover;
        const tapState = _state.interaction.tap;

        // If no interaction is active, hide all labels and exit.
        if (!hoverState.isActive && !tapState.isActive) {
            _controllers.chartsByName.forEach(chart => chart.hideLabel());
            return;
        }

        _controllers.chartsByName.forEach(chart => {
            // For the chart being hovered, its label is tied to the hover line (only if hover is enabled).
            if (hoverState.isActive && chart.name === hoverState.sourceChartName && _state.view.hoverEnabled) {
                const text = chart.getLabelText(hoverState.timestamp);
                chart.renderLabel(hoverState.timestamp, text);
            }
            // For all other charts, their labels are tied to the tap line, if it's active.
            else if (tapState.isActive) {
                const text = chart.getLabelText(tapState.timestamp);
                chart.renderLabel(tapState.timestamp, text);
            }
            // If a chart isn't being hovered and there's no active tap, hide its label.
            else {
                chart.hideLabel();
            }
        });
    }

    function renderMarkers() {
        // Render markers across all charts
        _controllers.chartsByName.forEach(chart => {
            chart.renderMarkers(_state.markers.timestamps);
        });
    }

    function _renderFrequencyTable() {
        const freqData = _state.data.activeFreqBarData;
        const tableDiv = _models.freqTableDiv;

        if (!tableDiv) {
            console.error("Frequency table div model not found.");
            return;
        }

        // Determine the labels to use for the header. Fallback to the bar chart's current labels if none in active data.
        const labels = (freqData && freqData.frequency_labels && freqData.frequency_labels.length > 0)
            ? freqData.frequency_labels
            : _models.barSource.data.frequency_labels;

        // Determine the levels to display. Use an empty array if no data.
        const levels = (freqData && freqData.levels) ? freqData.levels : [];

        if (!labels || labels.length === 0) {
            // If there are absolutely no labels to draw, show a simple message.
            tableDiv.text = "<p>Frequency bands not available.</p>";
            return;
        }

        let tableHtml = `
        <style>
            .freq-html-table { border-collapse: collapse; width: 100%; font-size: 0.9em; table-layout: fixed; }
            .freq-html-table th, .freq-html-table td { border: 1px solid #ddd; padding: 6px; text-align: center; white-space: nowrap; }
            .freq-html-table th { background-color: #f2f2f2; font-weight: bold; }
        </style>
        <table class="freq-html-table">
            <tr>`;

        labels.forEach(label => {
            tableHtml += `<th title=\"${label}\">${label}</th>`;
        });

        tableHtml += `</tr><tr>`;

        // If there are levels, display them. Otherwise, display blank cells.
        if (levels.length > 0) {
            levels.forEach(level => {
                const levelNum = (level === null || isNaN(level)) ? NaN : parseFloat(level);
                const levelText = isNaN(levelNum) ? 'N/A' : levelNum.toFixed(1);
                tableHtml += `<td>${levelText}</td>`;
            });
        } else {
            // Create blank cells matching the number of labels
            labels.forEach(() => {
                tableHtml += `<td>-</td>`;
            });
        }

        tableHtml += `</tr></table>`;
        tableDiv.text = tableHtml;
    }

    function renderFrequencyBar() {
        const freqData = _state.data.activeFreqBarData;
        _models.barSource.data = {
            'levels': freqData.levels,
            'frequency_labels': freqData.frequency_labels
        };
        _models.barChart.x_range.factors = freqData.frequency_labels;
        _models.barChart.title.text = `Slice: ${freqData.sourceposition} | ${freqData.param} @ ${new Date(freqData.timestamp).toLocaleTimeString()} | by ${freqData.setBy}`;
        _models.barSource.change.emit();

        // Also update the HTML table
        _renderFrequencyTable();
    }

    function renderaudio_controls() {
        const { isPlaying, activePositionId } = _state.audio;
        _state.view.availablePositions.forEach(pos => {
            const controls = _models.audio_controls[pos];
            if (controls) {
                controls.playToggle.active = isPlaying && activePositionId === pos;
                controls.playToggle.label = isPlaying && activePositionId === pos ? "Pause" : "Play";
            }
        });
    }

    // =======================================================================================
    //           PUBLIC API
    // =======================================================================================

    function initializeApp(models, options) {
        try {
            console.info('[NoiseSurveyApp]', 'Initializing...');
            console.log("[DEBUG] models: ", models); //DEBUG
            _models = models;

            // Correctly populate availablePositions first
            _state.view.availablePositions = Array.from(new Set(models.charts.map(c => {
                const parts = c.name.split('_');
                return parts.length >= 2 ? parts[1] : null;
            }).filter(Boolean)));

            _state.view.selectedParameter = models.paramSelect?.value || 'LZeq';
            _state.view.viewport = { min: models.charts[0].x_range.start, max: models.charts[0].x_range.end };

            _state.view.availablePositions.forEach(pos => {
                _state.view.displayDetails[pos] = { line: { type: 'overview' }, spec: { type: 'overview' } };
                const posController = new PositionController(pos, _models);
                _controllers.positions[pos] = posController;
                posController.charts.forEach(chart => {
                    _controllers.chartsByName.set(chart.name, chart);
                    const checkbox = _models.visibilityCheckBoxes.find(cb => cb.name === `visibility_${chart.name}`);
                    _state.view.chartVisibility[chart.name] = checkbox ? checkbox.active.includes(0) : true;
                });
            });



            if (options?.enableKeyboardNavigation) {
                setupKeyboardNavigation();
            }

            _dispatchAction({ type: 'INITIAL_LOAD' });
            console.info('[NoiseSurveyApp]', 'App initialized successfully.');


            console.log("[DEBUG] Attempting to initialize audio");
            if (_models.audio_status_source) {
                _models.audio_status_source.patching.connect(handleAudioStatusUpdate);
            }
            if (_models.audio_controls) {
                Object.keys(_models.audio_controls).forEach(pos => {
                    if (_models.audio_controls[pos] && _models.audio_controls[pos].playToggle) {
                        _models.audio_controls[pos].playToggle.on_change('active', () => togglePlayPause(pos));
                    }
                });
            }

            return true;
        }
        catch (error) {
            console.error('[NoiseSurveyApp]', 'Error initializing app:', error);
            return false;
        }
    }

    return {
        init: initializeApp,
        getState: () => JSON.parse(JSON.stringify(_state)),
        interactions: {
            onTap: cb_obj => handleTap(cb_obj),
            onHover: (cb_data, chartName) => handleChartHover(cb_data, chartName),
            onSpectrogramHover: (cb_data, position_name) => { /* Placeholder */ },
            onRangeUpdate: cb_obj => handleRangeUpdate(cb_obj),
            onVisibilityChange: (cb_obj, chartName) => handleVisibilityChange(cb_obj, chartName),
            onDoubleClick: cb_obj => handleDoubleClick(cb_obj),
            onRightClick: cb_obj => handleRightClick(cb_obj),
        },
        handleParameterChange: value => handleParameterChange(value),
        handleViewToggle: (active, widget) => handleViewToggle(active, widget),
        handleHoverToggle: (active, widget) => handleHoverToggle(active, widget),
        clearAllMarkers: () => clearAllMarkers(),
        controls: {
            togglePlayPause: togglePlayPause
        }
    };

})();

console.log("[DEBUG] app.js loaded and NoiseSurveyApp object created.");