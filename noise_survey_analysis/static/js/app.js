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
        constructor(chartModel, sourceModel, labelModel, hoverLineModel) {
            this.model = chartModel;
            this.source = sourceModel;
            this.labelModel = labelModel;
            this.hoverLineModel = hoverLineModel;
            this.name = chartModel.name;
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
            this.model.title.text = `Time History - ${displayDetails.reason}`;
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
    }

    class SpectrogramChart extends Chart {
        constructor(chartModel, labelModel, hoverLineModel, hoverDivModel) {
            const imageRenderer = chartModel.renderers.find(r => r.glyph?.type === "Image");
            if (!imageRenderer) {
                console.warn('No ImageRenderer found in chartModel');
                return;
            }
            super(chartModel, imageRenderer.data_source, labelModel, hoverLineModel);
            this.imageRenderer = imageRenderer;
            this.hoverDivModel = hoverDivModel;
        }

        update(activeSpectralData, displayDetails, selectedParameter) {
            const reason = displayDetails.reason || 'Overview';
            this.model.title.text = `Spectrogram | ${selectedParameter} (${reason})`;

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
            } else {
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
                this.timeSeriesChart = new TimeSeriesChart(tsChartModel, tsSourceModel, tsLabelModel, tsHoverLineModel);
                this.charts.push(this.timeSeriesChart);
            }

            // --- Spectrogram Chart (robustly) ---
            const specChartModel = models.charts.find(c => c.name === `figure_${this.id}_spectrogram`);
            if (specChartModel) {
                const specLabelModel = models.labels.find(l => l.name === `label_${this.id}_spectrogram`);
                const specHoverLineModel = models.hoverLines.find(l => l.name === `hoverline_${this.id}_spectrogram`);
                const specHoverDivModel = models.hoverDivs.find(d => d.name === `${this.id}_spectrogram_hover_div`);
                // The Spectrogram constructor is also robust in case imageRenderer is not found
                try {
                    this.spectrogramChart = new SpectrogramChart(specChartModel, specLabelModel, specHoverLineModel, specHoverDivModel);
                    this.charts.push(this.spectrogramChart);
                } catch (e) {
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
            globalViewType: 'overview',
            selectedParameter: 'LZeq',
            viewport: { min: null, max: null },
            chartVisibility: {},
            displayDetails: {},
        },
        interaction: {
            tap: { isActive: false, timestamp: null, position: null, sourceChartName: null },
            hover: { isActive: false, timestamp: null, position: null, sourceChartName: null, spec_y: null },
            keyboard: { enabled: false, stepSizeMs: 300000 },
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
            console.log("[DEBUG] Cannot calculate step size: No active position from audio or tap.");
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
        console.log(`[DEBUG] Step size updated for '${positionId}' to ${Math.round(newStep / 1000)}s`);
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
        if (_state.audio.activePositionId === null || _state.audio.activePositionId === undefined) return;
        _models.audioControlSource.data = { command: ['seek'], position_id: [_state.audio.activePositionId], value: [time] };
        _models.audioControlSource.change.emit();
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
        _state.interaction.tap = {
            isActive: true,
            timestamp: cb_obj.x,
            position: _getChartPositionByName(chartName),
            sourceChartName: chartName
        };
        _updateActiveData();
        calculateStepSize();
        renderAllVisuals();
        seek(cb_obj.x);
    }

    function handleChartHover(cb_data, chartName) {
        const geometry = cb_data.geometry;
        const isActive = geometry && Number.isFinite(geometry.x);
        if (isActive) {
            _state.interaction.hover = {
                isActive: true,
                sourceChartName: chartName,
                timestamp: geometry.x,
                spec_y: geometry.y,
                position: _getChartPositionByName(chartName),
            };
        } else {
            _state.interaction.hover.isActive = false;
        }
        renderHoverEffects();
    }

    function handleRangeUpdate(cb_obj) {
        //TODO: set a threshold for the range update before data is updated and visuals are rendered. should be done in _updateActiveData()?
        _state.view.viewport = { min: cb_obj.start, max: cb_obj.end };
        _updateActiveData();
        renderAllVisuals();
    }

    function handleParameterChange(value) {
        _state.view.selectedParameter = value;
        _updateActiveData();
        calculateStepSize();
        renderAllVisuals();
    }

    function handleViewToggle(isActive, toggleWidget) {
        const newViewType = isActive ? 'log' : 'overview';
        _state.view.globalViewType = newViewType;
        _updateActiveData();
        calculateStepSize();
        renderAllVisuals();
        if (toggleWidget) {
            toggleWidget.label = `Switch to ${newViewType === 'overview' ? 'Log' : 'Overview'}`;
        }
    }

    function handleVisibilityChange(cb_obj, chartName) {
        const isVisible = Array.isArray(cb_obj.active) ? cb_obj.active.includes(0) : Boolean(cb_obj.active);
        _state.view.chartVisibility[chartName] = isVisible;
        const chart = _controllers.chartsByName.get(chartName);
        if (chart) {
            chart.setVisible(isVisible);
            if (chart instanceof SpectrogramChart && !isVisible) {
                chart.hoverDivModel.visible = false;
            }
        }
    }

    function handleAudioStatusUpdate() {
        const status = _models.audioStatusSource.data;
        _state.audio.isPlaying = status.is_playing[0];
        _state.audio.activePositionId = status.active_position_id[0];
        _state.audio.currentTime = status.current_time[0];

        if (_state.audio.isPlaying) {
            _state.interaction.tap.timestamp = _state.audio.currentTime;
            _state.interaction.tap.isActive = true;
        }

        renderAudioControls();
        calculateStepSize();
        renderTapLines();
        renderLabels();
        _updateActiveFreqBarData(_state.interaction.tap.position, _state.interaction.tap.timestamp, 'tap');
        renderFrequencyBar();
    }

    function togglePlayPause(positionId) {
        const command = _state.audio.isPlaying && _state.audio.activePositionId === positionId ? 'pause' : 'play';
        _models.audioControlSource.data = { command: [command], position_id: [positionId], value: [_state.interaction.tap.timestamp] };
        _models.audioControlSource.change.emit();
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

            _state.interaction.tap.timestamp = newX;
            _state.interaction.tap.isActive = true;

            _updateActiveData();
            renderTapLines();
            renderLabels();
            renderFrequencyBar();
        }
    }

    function setupKeyboardNavigation() {
        if (!_state.interaction.keyboard.enabled) {
            document.addEventListener('keydown', handleKeyPress);
            _state.interaction.keyboard.enabled = true;
        }
    }

    // =======================================================================================
    //           STATE MANAGEMENT
    // =======================================================================================

    function _updateActiveData() {
        _state.view.availablePositions.forEach(position => {
            _updateActiveLineChartData(position, _state.view.globalViewType);
            _updateActiveSpectralData(position, _state.view.globalViewType, _state.view.selectedParameter);
        });

        // Determine context for the frequency bar with clear precedence
        let contextSource = _state.interaction.hover.isActive ? _state.interaction.hover : _state.interaction.tap;
        let setBy = _state.interaction.hover.isActive ? 'hover' : 'tap';

        // If neither is active, timestamp will be null and the function will handle it.
        _updateActiveFreqBarData(contextSource.position, contextSource.timestamp, setBy);
    }

    function _updateActiveLineChartData(position, viewType) {
        const sourceData = _models.timeSeriesSources[position];
        const overviewData = sourceData?.overview?.data;
        const logData = sourceData?.log?.data;
        let displayDetails = { type: 'overview', reason: 'Overview' };

        if (viewType === 'overview' || !logData || logData.Datetime.length === 0) {
            _state.data.activeLineData[position] = overviewData || {};
        } else {
            const { min, max } = _state.view.viewport;
            const startIndex = logData.Datetime.findIndex(t => t >= min);
            const endIndex = logData.Datetime.findLastIndex(t => t <= max);
            const pointsInView = (startIndex !== -1 && endIndex !== -1) ? endIndex - startIndex : 0;

            if (pointsInView > MAX_LINE_POINTS_TO_RENDER) {
                _state.data.activeLineData[position] = overviewData || {};
                displayDetails.reason = 'Zoom in for Log Data';
            } else {
                const buffer = Math.floor(pointsInView * 0.5);
                const sliceStart = Math.max(0, startIndex - buffer);
                const sliceEnd = Math.min(logData.Datetime.length, endIndex + buffer + 1);
                const chunk = {};
                for (const key in logData) {
                    chunk[key] = logData[key].slice(sliceStart, sliceEnd);
                }
                _state.data.activeLineData[position] = chunk;
                displayDetails = { type: 'log', reason: 'Log Data (Chunked)' };
            }
        }
        _state.view.displayDetails[position].line = displayDetails;
    }

    // noise_survey_analysis/static/js/app.js

    function _updateActiveSpectralData(position, viewType, parameter) {
        const positionGlyphData = _models.preparedGlyphData[position];
        const overviewData = positionGlyphData?.overview?.prepared_params?.[parameter];
        const logData = positionGlyphData?.log?.prepared_params?.[parameter];

        let finalDataToUse, finalGlyphData, displayReason;

        // Determine if we want to and can show log data
        const wantsLogView = viewType === 'log' && logData;
        const pointsInView = wantsLogView ? Math.floor((_state.view.viewport.max - _state.view.viewport.min) / logData.time_step) : Infinity;

        // --- LOGIC PATH 1: Show chunked LOG data ---
        // This is the "happy path" for log view: user wants it, it exists, and they are zoomed in enough.
        if (wantsLogView && pointsInView <= MAX_SPECTRAL_POINTS_TO_RENDER) {

            finalDataToUse = logData;
            displayReason = 'Log Data (Chunked)';

            const { n_times, chunk_time_length, times_ms, time_step, levels_flat_transposed, n_freqs } = finalDataToUse;

            const { min, max } = _state.view.viewport;
            const targetChunkStartTimeStamp = (max + min) / 2 - (chunk_time_length * time_step / 2);

            let chunkStartTimeIdx;
            const foundIndex = times_ms.findIndex(t => t >= targetChunkStartTimeStamp);

            if (foundIndex !== -1) {
                // Normal case: The target time is somewhere within the data range.
                chunkStartTimeIdx = foundIndex;
            } else {
                // Out-of-bounds case: The target time is either before the start or after the end.
                if (targetChunkStartTimeStamp > times_ms[times_ms.length - 1]) {
                    // The view is PAST the end of the data. Show the last possible full chunk.
                    chunkStartTimeIdx = Math.max(0, n_times - chunk_time_length);
                } else {
                    // The view is BEFORE the start of the data. Show the first chunk.
                    chunkStartTimeIdx = 0;
                }
            }

            const actualPointsInThisChunk = chunk_time_length; //Math.min(chunk_time_length, n_real_times - chunkStartTimeIdx); was here if the last chunk was not full. not sure that would work for a glyph. 
            const chunk_specific_dw = actualPointsInThisChunk * time_step;
            const chunk_image = _extractTimeChunkFromFlatData(levels_flat_transposed, n_freqs, n_times, chunkStartTimeIdx, chunk_time_length);

            finalGlyphData = {
                ...finalDataToUse.initial_glyph_data,
                image: [chunk_image],
                x: [times_ms[chunkStartTimeIdx]],
                dw: [chunk_specific_dw],
                times_ms: times_ms.slice(chunkStartTimeIdx, chunkStartTimeIdx + chunk_time_length),
            };

            // --- LOGIC PATH 2: Show full OVERVIEW data ---
            // This is the fallback path used if:
            //  a) The user selected 'overview' view.
            //  b) The user selected 'log' view, but no log data exists.
            //  c) The user selected 'log' view, but is zoomed out too far.
        } else {
            finalDataToUse = overviewData;
            // The reason depends on why we're in this fallback path
            displayReason = wantsLogView ? 'Zoom in for Log Data' : 'Overview (Full)';

            if (finalDataToUse) {
                // IMPORTANT: Use the initial_glyph_data directly, which represents the full, un-chunked overview data.
                finalGlyphData = { ...finalDataToUse.initial_glyph_data, times_ms: finalDataToUse.times_ms };
            } else {
                finalGlyphData = null; // No overview data exists either
                displayReason = 'No Data Available';
            }
        }

        // --- Final state update ---
        if (finalGlyphData && finalDataToUse) {
            _state.data.activeSpectralData[position] = { ...finalDataToUse, source_replacement: finalGlyphData };
        } else {
            _state.data.activeSpectralData[position] = { source_replacement: null, reason: 'No Data Available' };
        }
        _state.view.displayDetails[position].spec = { reason: displayReason };
    }
    function _updateActiveFreqBarData(position, timestamp, setBy) {
        const blankData = { levels: [], frequency_labels: [], sourceposition: '', timestamp: null, setBy: null, param: null };
        if (!timestamp || !position) {
            _state.data.activeFreqBarData = blankData;
            return;
        }
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

    function renderAllVisuals() {
        for (const posId in _controllers.positions) {
            _controllers.positions[posId].updateAllCharts(_state);
        }
        renderTapLines();
        renderLabels();
        renderFrequencyBar();
    }

    function renderHoverEffects() {
        const hoverState = _state.interaction.hover;

        // Update data for the bar chart based on hover
        _updateActiveFreqBarData(hoverState.position, hoverState.timestamp, 'hover');
        renderFrequencyBar();

        _controllers.chartsByName.forEach(chart => {
            if (hoverState.isActive) {
                chart.renderHoverLine(hoverState.timestamp);
            } else {
                chart.hideHoverLine();
            }

            if (chart instanceof SpectrogramChart) {
                chart.renderHoverDetails(hoverState, _state.data.activeFreqBarData);
            }
        });

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
            // For the chart being hovered, its label is tied to the hover line.
            if (hoverState.isActive && chart.name === hoverState.sourceChartName) {
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

    function renderFrequencyBar() {
        const freqData = _state.data.activeFreqBarData;
        _models.barSource.data = {
            'levels': freqData.levels,
            'frequency_labels': freqData.frequency_labels
        };
        _models.barChart.title.text = `Slice: ${freqData.sourceposition} | ${freqData.param} @ ${new Date(freqData.timestamp).toLocaleTimeString()} | by ${freqData.setBy}`;
        _models.barSource.change.emit();
    }

    function renderAudioControls() {
        const { isPlaying, activePositionId } = _state.audio;
        _state.view.availablePositions.forEach(pos => {
            const controls = _models.audio_controls[pos];
            if (controls) {
                controls.play_toggle.active = isPlaying && activePositionId === pos;
                controls.play_toggle.label = isPlaying && activePositionId === pos ? "Pause" : "Play";
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

            if (_models.audio_status_source) {
                _models.audio_status_source.on_change('data', handleAudioStatusUpdate);
            }
            if (_models.audio_controls) {
                Object.keys(_models.audio_controls).forEach(pos => {
                    _models.audio_controls[pos].play_toggle.on_change('active', (active) => togglePlayPause(pos));
                });
            }

            if (options?.enableKeyboardNavigation) {
                setupKeyboardNavigation();
            }

            _updateActiveData();
            renderAllVisuals();
            console.info('[NoiseSurveyApp]', 'App initialized successfully.');
            return true;
        } catch (error) {
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
        },
        handleParameterChange: value => handleParameterChange(value),
        handleViewToggle: (active, widget) => handleViewToggle(active, widget),
    };

})();

console.log("[DEBUG] app.js loaded and NoiseSurveyApp object created.");