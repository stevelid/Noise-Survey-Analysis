/* DEBUG START */
console.log("[DEBUG] app.js: Script loading started (State-Driven Refactor).");
/* DEBUG END */
window.NoiseSurveyApp = (function () {
    'use strict';

    // --- Private State & Models ---
    let _models = { // Populated by initializeApp
        charts: [],
        allTimeSeriesSources: {}, // Overview/log raw data sources (_models.sources[pos_overview_raw_data], _models.sources[pos_log_raw_data])
        clickLines: [],
        labels: [], // Labels for tap lines
        hoverLines: [], // Added for managing hover lines if needed centrally
        hoverLabels: [], // Added for managing hover labels if needed centrally
        playbackSource: null,
        playbackStatusSource: null,
        playButton: null,
        pauseButton: null,
        positionPlayButtons: {},
        barSource: null,
        barXRange: null,
        barChart: null,
        freqTableDiv: null,
        paramSelect: null,
        selectedParamHolder: null,
        allSpectralData: {}, // Master store: { pos: { spectral: { prepared_data: {param: {times_ms, levels_matrix,...}}}, spectral_log: {...} }}
        seekCommandSource: null,
        playRequestSource: null,
        // UI elements that might need direct access for specific updates (e.g., hover divs for spectrograms)
        uiPositionElements: {}, // e.g., { SW: { spectrogram_hover_div: model } }
    };

    let _state = {
        // Core state
        selectedParameter: 'LZeq',  // Currently selected spectral parameter
        viewType: {},               // { position: 'overview' | 'log' } - Current view for line and spectral charts
        activeLineChartData: {},    // { position: { Datetime: [], LAeq: [], ... } } - Data currently active for line chart
        activeSpectralData: {},     // { position: { times_ms:[], levels_matrix_transposed:[], min_val:X, max_val:Y, ... } } - Data for spec
        
        // Interaction state
        verticalLinePosition: null, // ms timestamp of the red tap line
        lastHoverX: null,           // Last hovered X position on any chart
        keyboardNavigationEnabled: false,
        stepSize: 300000,           // ms for keyboard nav

        // Playback state (mostly driven by playbackStatusSource from Python)
        isPlaying: false,
        activeAudioPosition: null,  // Position name ('SW', 'N', etc.) being played

        // Configuration / Initialization
        availablePositions: [],     // Populated from _models.spectralParamCharts keys

        // Frequency Bar Focus
        // Determines which data the frequency bar should display
        // type: 'tap', 'playback', 'hover'
        // position: The position name relevant to the focus
        // (parameter and viewType for freq bar are derived from global _state.selectedParameter
        // and _state.viewType[focusedPosition] unless hover overrides)
        freqBarFocus: {
            type: 'tap', // Default to tap
            position: null,
            timestamp: null, // Timestamp for the slice
            // Optional: for hover on spectrogram, if it needs to show a different param/view than global state
            // hoverOverride: { parameter: null, viewType: null } 
        },
        // Temporary state for hover interactions that update the frequency bar
        hoverContext: { // Used if _handleSpectrogramHover needs to feed specific data to renderFreqBar
            isActive: false,
            position: null,
            timestamp: null,
            dataForBar: null // Actual prepared_data slice for the hovered parameter/view
        }
    };

    // Debugging access
    window.__debugNoiseSurveyModels = _models;
    window.__debugNoiseSurveyState = _state;

    // --- Private Utility Functions (largely unchanged, ensure they use _state if needed) ---
    function findClosestDateIndex(dates, x) { /* ... unchanged ... */ 
        if (!dates || dates.length === 0) return -1;
        // Simplified for brevity, original robust checks should be kept
        let min_diff = Infinity;
        let closest_idx = 0;
        for (let j = 0; j < dates.length; j++) {
            let diff = Math.abs(dates[j] - x);
            if (diff < min_diff) {
                min_diff = diff;
                closest_idx = j;
            }
        }
        return closest_idx;
    }
    function findClosestIndex(array, target) { /* ... unchanged ... */ 
        if (!array || array.length === 0) return -1;
        let minDiff = Infinity;
        let closestIndex = -1;
        for (let i = 0; i < array.length; i++) {
            let diff = Math.abs(array[i] - target);
            if (diff < minDiff) {
                minDiff = diff;
                closestIndex = i;
            }
        }
        return closestIndex;
    }
    function createLabelText(sourceData, closest_idx) { // Modified to take data object
        if (!sourceData || !sourceData.Datetime || closest_idx < 0 || closest_idx >= sourceData.Datetime.length) {
            return "Error: Invalid data for label";
        }
        let date = new Date(sourceData.Datetime[closest_idx]);
        let formatted_date = date.toLocaleString();
        let label_text = 'Time: ' + formatted_date + '\n';
        for (let key in sourceData) {
            if (key !== 'Datetime' && key !== 'index' && sourceData.hasOwnProperty(key) && sourceData[key]?.length > closest_idx) {
                let value = sourceData[key][closest_idx];
                if (value !== undefined && value !== null && !isNaN(value)) {
                    let formatted_value = parseFloat(value).toFixed(1);
                    let unit = (key.startsWith('L') || key.includes('eq') || key.includes('max') || key.includes('min')) ? ' dB' : '';
                    label_text += key + ': ' + formatted_value + unit + '\n';
                }
            }
        }
        return label_text;
    }
    function positionLabel(x, chart, labelModel) { /* ... unchanged ... */ }
    function calculateStepSize(sourceData) { // Modified to take data object
        const DEFAULT_STEP_SIZE = 300000;
        if (!sourceData?.Datetime || sourceData.Datetime.length < 2) {
            return DEFAULT_STEP_SIZE;
        }
        const times = sourceData.Datetime;
        const interval = times[1] - times[0]; // Simple interval
        return Math.max(1000, Math.min(3600000, Math.round(interval || DEFAULT_STEP_SIZE)));
    }
    function _getActiveChartModelById(id) {
        return _models.charts.find(chart => chart?.id === id);
    }
    function _getChartPositionByName(chartName) {
        if (!chartName) return null;
        // Extracts position like 'SW' from 'SW_combined_time_series' or 'SW_combined_spectrogram'
        const parts = chartName.split('_');
        if (parts.length > 0 && _state.availablePositions.includes(parts[0])) {
            return parts[0];
        }
        // Fallback for simple names if needed, or other chart naming conventions
        for (const pos of _state.availablePositions) {
            if (chartName.startsWith(pos)) return pos;
        }
        return null;
    }

    // --- Group A: State Management ---
    /**
     * Updates the active data slices in _state for a given position, viewType, and parameter.
     * This is the single source of truth for what data is considered "active" for rendering.
     */
    function _updateActiveData(position, viewType, parameter) {
        console.log('[_updateActiveData]', `Updating for ${position}/${viewType}/${parameter}`);
        if (!_state.availablePositions.includes(position)) {
            console.warn('[_updateActiveData]', `Position ${position} not found in available positions.`);
            return;
        }

        // 1. Update Active Line Chart Data
        const lineChartDataKey = viewType === 'log' ? `${position}_log_raw_data` : `${position}_overview_raw_data`;
        if (_models.allTimeSeriesSources[lineChartDataKey]) {
            _state.activeLineChartData[position] = _models.allTimeSeriesSources[lineChartDataKey];
            console.log('[_updateActiveData]', `Line chart data for ${position} (${viewType}) set.`);
        } else {
            _state.activeLineChartData[position] = { Datetime: [], LAeq: [] }; // Empty default
            console.warn('[_updateActiveData]', `Raw line chart data for ${lineChartDataKey} not found.`);
        }

        // 2. Update Active Spectral Data
        const spectralKey = viewType === 'log' ? 'spectral_log' : 'spectral';
        const positionSpectralData = _models.allSpectralData[position];

        if (positionSpectralData && positionSpectralData[spectralKey] &&
            positionSpectralData[spectralKey].prepared_data &&
            positionSpectralData[spectralKey].prepared_data[parameter]) {
            _state.activeSpectralData[position] = positionSpectralData[spectralKey].prepared_data[parameter];
            console.log('[_updateActiveData]', `Spectral data for ${position} (${spectralKey}, ${parameter}) set.`);
        } else {
            _state.activeSpectralData[position] = null; // Or a default empty spectral data structure
            console.warn('[_updateActiveData]', `Prepared spectral data for ${position}/${spectralKey}/${parameter} not found.`);
        }
    }

    // --- Group B: UI Updaters (Renderers) ---

    /**
     * Renders the line chart for the given position based on _state.activeLineChartData.
     */
    function renderLineChart(position) {
        console.log('[Render:renderLineChart]', `Rendering line chart for ${position}`);
        const chartModel = _models.charts.find(c => c.name === `${position}_combined_time_series`);
        const activeData = _state.activeLineChartData[position];

        if (!chartModel || !activeData) {
            console.warn('[Render:renderLineChart]', `No chart model or active data for ${position}.`);
            return;
        }

        chartModel.source.data = activeData;
        const newTitleType = _state.viewType[position] === 'log' ? "Log Data" : "Overview Data";
        chartModel.title.text = `${position} - ${newTitleType}`;
        
        // Recalculate step size for keyboard navigation based on the new active data
        _state.stepSize = calculateStepSize(activeData);
        console.log('[Render:renderLineChart]', `Step size recalculated to ${_state.stepSize}ms for ${position}`);
        
        chartModel.source.change.emit();
        console.log('[Render:renderLineChart]', `Line chart for ${position} updated. Title: "${chartModel.title.text}"`);
    }

    /**
     * Renders the spectrogram for the given position based on _state.activeSpectralData.
     */
    function renderSpectrogram(position) {
        console.log('[Render:renderSpectrogram]', `Rendering spectrogram for ${position}`);
        const chartModel = _models.charts.find(c => c.name === `${position}_combined_spectrogram`);
        const activeData = _state.activeSpectralData[position]; // This IS the prepared_data[param] object

        if (!chartModel) {
            console.warn('[Render:renderSpectrogram]', `No spectrogram model found for ${position}.`);
            return;
        }

        const imageRenderer = chartModel.renderers.find(r => r.glyph?.type === "Image");
        if (!imageRenderer) {
            console.warn('[Render:renderSpectrogram]', `No Image renderer found for spectrogram ${position}.`);
            return;
        }

        if (activeData) {
            const source = imageRenderer.data_source;
            const glyph = imageRenderer.glyph;
            const colorMapper = glyph.color_mapper;

            glyph.x = activeData.x;
            glyph.y = activeData.y;
            glyph.dw = activeData.dw;
            glyph.dh = activeData.dh;
            source.data = { 'image': [activeData.levels_matrix_transposed] };

            if (colorMapper) {
                colorMapper.low = activeData.min_val;
                colorMapper.high = activeData.max_val;
            }

            const newTitleSuffix = _state.viewType[position] === 'log' ? "Spectral Log" : "Spectral Overview";
            chartModel.title.text = `${position} - ${_state.selectedParameter} (${newTitleSuffix})`;
            chartModel.visible = true;
            source.change.emit();
            console.log('[Render:renderSpectrogram]', `Spectrogram for ${position} updated and visible. Title: "${chartModel.title.text}"`);
        } else {
            chartModel.visible = false;
            console.log('[Render:renderSpectrogram]', `No active spectral data for ${position}. Hiding spectrogram.`);
        }
    }
    
    /**
     * Renders the Frequency Bar Chart and Data Table based on _state.freqBarFocus and the given timestamp.
     */
    function renderFrequencyBar(timestamp) {
        console.log('[Render:renderFrequencyBar]', `Rendering for time ${timestamp}, focus:`, _state.freqBarFocus);

        if (timestamp === null || timestamp === undefined) {
            console.warn('[Render:renderFrequencyBar]', 'Timestamp is null/undefined. Clearing bar chart.');
            _models.barSource.data = { 'levels': [], 'frequency_labels': [] };
            _models.barXRange.factors = [];
            _models.barChart.title.text = "Frequency Slice: N/A";
            _models.barSource.change.emit();
            _updateFrequencyTable([], []);
            return;
        }

        let dataForBar;
        let positionToUse = _state.freqBarFocus.position;
        let paramToUse = _state.selectedParameter;
        let viewTypeToUse = _state.viewType[positionToUse] || 'overview'; // Default if not set

        if (_state.hoverContext.isActive && _state.hoverContext.position && _state.hoverContext.dataForBar) {
            // Priority to hover context if active
            positionToUse = _state.hoverContext.position;
            dataForBar = _state.hoverContext.dataForBar; // This is already the specific prepared_data[param] for hover
            paramToUse = dataForBar.parameterName || paramToUse; // Assuming dataForBar is tagged with its param
            viewTypeToUse = dataForBar.viewType || viewTypeToUse; // Assuming dataForBar is tagged with its viewType
            console.log('[Render:renderFrequencyBar]', `Using hover context for position ${positionToUse}`);
        } else if (positionToUse) {
            // Use focus position and global state for param/viewType
            const spectralKey = viewTypeToUse === 'log' ? 'spectral_log' : 'spectral';
            if (_models.allSpectralData[positionToUse] &&
                _models.allSpectralData[positionToUse][spectralKey] &&
                _models.allSpectralData[positionToUse][spectralKey].prepared_data) {
                dataForBar = _models.allSpectralData[positionToUse][spectralKey].prepared_data[paramToUse];
            }
            console.log('[Render:renderFrequencyBar]', `Using focus type: ${_state.freqBarFocus.type} for position ${positionToUse}`);
        }

        if (!dataForBar) {
            console.warn('[Render:renderFrequencyBar]', `No spectral data found for position '${positionToUse}', param '${paramToUse}', view '${viewTypeToUse}'. Resetting bar chart.`);
            _models.barChart.title.text = `Frequency Slice: ${positionToUse || 'N/A'} | ${paramToUse} (Data N/A)`;
            _models.barSource.data = { 'levels': [], 'frequency_labels': [] };
            _models.barXRange.factors = [];
            _models.barSource.change.emit();
            _updateFrequencyTable([], []);
            return;
        }

        const { times_ms, levels_matrix, frequency_labels, n_freqs } = dataForBar;
        if (!times_ms || !levels_matrix || !frequency_labels || n_freqs === 0) {
            console.warn('[Render:renderFrequencyBar]', `Incomplete data in dataForBar object for ${positionToUse}.`);
            return;
        }
        
        const closestTimeIdx = findClosestDateIndex(times_ms, timestamp);
        if (closestTimeIdx === -1) {
            console.warn('[Render:renderFrequencyBar]', `No closest time index for ${timestamp}.`);
            return;
        }

        let freqDataSlice;
        // Assuming levels_matrix is 2D: (n_times, n_freqs) as per prepare_spectral_image_data output
        if (closestTimeIdx < levels_matrix.length) {
            freqDataSlice = levels_matrix[closestTimeIdx];
        }

        if (!freqDataSlice || freqDataSlice.length !== n_freqs) {
            console.warn('[Render:renderFrequencyBar]', `Frequency data slice invalid or wrong length for ${positionToUse} at index ${closestTimeIdx}.`);
            return;
        }

        const cleanedLevels = freqDataSlice.map(level => (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);
        _models.barSource.data = { 'levels': cleanedLevels, 'frequency_labels': frequency_labels };
        _models.barXRange.factors = frequency_labels;
        
        const spectralTypeDisplay = viewTypeToUse.replace('_', ' ');
        let titleSuffix = `(${spectralTypeDisplay}) | ${paramToUse}`;
        if (_state.hoverContext.isActive) titleSuffix += ` | ${new Date(timestamp).toLocaleTimeString()} (Hover)`;
        else titleSuffix += ` | ${new Date(timestamp).toLocaleString()}`;

        _models.barChart.title.text = `Frequency Slice: ${positionToUse} ${titleSuffix}`;
        _models.barSource.change.emit();
        _updateFrequencyTable(cleanedLevels, frequency_labels);
        console.log('[Render:renderFrequencyBar]', `Bar chart updated for ${positionToUse} at ${timestamp}.`);
    }

    /**
     * Renders all tap lines and their associated labels.
     */
    function renderTapLines(timestamp) {
        console.log('[Render:renderTapLines]', `Updating tap lines to ${timestamp}`);
        if (timestamp === null || timestamp === undefined) {
            _models.clickLines.forEach(line => { if(line) line.visible = false; });
            _models.labels.forEach(label => { if(label) label.visible = false; });
            return;
        }

        _state.verticalLinePosition = timestamp; // Ensure state is authoritative

        _models.charts.forEach((chart, i) => {
            if (!chart || chart.name === 'frequency_bar' || !chart.name) return;

            const clickLineModel = _models.clickLines[i];
            const labelModel = _models.labels[i];

            if (!clickLineModel || !labelModel) return;

            clickLineModel.location = timestamp;
            clickLineModel.visible = true;

            // For labels, only update for combined_time_series charts
            if (chart.name.includes('_combined_time_series')) {
                const position = _getChartPositionByName(chart.name);
                if (position && _state.activeLineChartData[position]) {
                    const activeData = _state.activeLineChartData[position];
                    const closest_idx = findClosestDateIndex(activeData.Datetime, timestamp);
                    if (closest_idx !== -1) {
                        labelModel.text = createLabelText(activeData, closest_idx);
                        positionLabel(timestamp, chart, labelModel);
                        labelModel.visible = true;
                    } else {
                        labelModel.visible = false;
                    }
                } else {
                    labelModel.visible = false;
                }
            } else { // Hide labels for other chart types like spectrograms
                labelModel.visible = false;
            }
        });
        console.log('[Render:renderTapLines]', 'Tap lines and labels updated.');
    }
    
    /**
     * Renders hover lines and labels for a specific chart.
     */
    function renderHoverEffects(chartModel, timestamp, chartIndex) {
        // console.log('[Render:renderHoverEffects]', `Updating for chart ${chartModel?.name} at ${timestamp}`); // Can be too verbose
        
        // Update all grey hover lines
        _models.hoverLines.forEach(line => {
            if (line) {
                line.location = timestamp;
                line.visible = true;
            }
        });
    
        // Update label only for the currently hovered chart (if it's a line chart)
        _models.hoverLabels.forEach((labelModel, i) => {
            if (!labelModel) return;
            if (i === chartIndex && chartModel && chartModel.name.includes('_combined_time_series')) {
                const position = _getChartPositionByName(chartModel.name);
                if (position && _state.activeLineChartData[position]) {
                    const activeData = _state.activeLineChartData[position];
                    const closest_idx = findClosestDateIndex(activeData.Datetime, timestamp);
                    if (closest_idx !== -1) {
                        labelModel.text = createLabelText(activeData, closest_idx);
                        positionLabel(timestamp, chartModel, labelModel); // Use chartModel here
                        labelModel.visible = true;
                    } else {
                        labelModel.visible = false;
                    }
                } else {
                    labelModel.visible = false;
                }
            } else {
                labelModel.visible = false; // Hide labels for other charts or non-hovered charts
            }
        });
    }

    function clearHoverEffects() {
        // console.log('[Render:clearHoverEffects]', 'Clearing hover effects'); // Can be too verbose
        _models.hoverLines.forEach(line => { if (line) line.visible = false; });
        _models.hoverLabels.forEach(label => { if (label) label.visible = false; });
        _state.lastHoverX = null; // Reset last hover X
    }

    /**
     * Renders all visual components based on the current _state.
     */
    function renderAllVisuals() {
        console.log('[Render:renderAllVisuals]', 'Rendering all visuals.');
        _state.availablePositions.forEach(pos => {
            renderLineChart(pos);
            renderSpectrogram(pos);
        });
        renderTapLines(_state.verticalLinePosition); // Update tap lines and their labels
        
        // Determine correct timestamp for freq bar (hover might have its own)
        let freqBarTimestamp = _state.verticalLinePosition;
        if (_state.hoverContext.isActive && _state.hoverContext.timestamp !== null) {
            freqBarTimestamp = _state.hoverContext.timestamp;
        } else if (_state.freqBarFocus.timestamp !== null) {
            freqBarTimestamp = _state.freqBarFocus.timestamp;
        }
        renderFrequencyBar(freqBarTimestamp);
        
        _updatePlayButtonsState(_state.isPlaying); // Ensure buttons are correct
    }


    // --- Group C: Event Controllers ---

    /**
     * Handles the click of a toggle button for a position.
     * Switches between 'overview' and 'log' views for both line and spectral charts.
     */
    function handleToggleClick(isActive, position, toggleWidget) { // toggleWidget passed to update its label
        const newViewType = isActive ? 'log' : 'overview';
        console.log('[Controller:handleToggleClick]', { position, newViewType });

        _state.viewType[position] = newViewType;
        _updateActiveData(position, newViewType, _state.selectedParameter);

        renderLineChart(position);
        renderSpectrogram(position);
        renderTapLines(_state.verticalLinePosition); // Re-render tap lines as labels might change
        
        // Update frequency bar if the focus was on this position
        if (_state.freqBarFocus.position === position && !_state.hoverContext.isActive) {
            renderFrequencyBar(_state.verticalLinePosition);
        }

        // Update the toggle button's label
        if (toggleWidget) {
            toggleWidget.label = `Switch to ${newViewType === 'overview' ? 'Log' : 'Overview'}`;
        }
    }

    /**
     * Handles change in the parameter selection dropdown.
     */
    function handleParameterChange(new_param) {
        console.log('[Controller:handleParameterChange]', { new_param });
        if (!new_param) {
            console.warn('[Controller:handleParameterChange]', 'Null/undefined parameter received.');
            return;
        }
        _state.selectedParameter = new_param;
        if (_models.selectedParamHolder) { // Update Python-visible holder
            _models.selectedParamHolder.text = new_param;
        }

        _state.availablePositions.forEach(pos => {
            _updateActiveData(pos, _state.viewType[pos], _state.selectedParameter);
        });

        // Re-render all spectrograms as they depend on the parameter
        _state.availablePositions.forEach(pos => {
            renderSpectrogram(pos);
        });
        
        // Re-render frequency bar as its data depends on the selected parameter
        // (unless hover is active and providing its own parameter)
        if (!_state.hoverContext.isActive) {
            renderFrequencyBar(_state.verticalLinePosition);
        }
        console.log('[Controller:handleParameterChange]', 'Parameter change processed.');
    }

    /**
     * Handles tap events on charts.
     */
    function handleTap(cb_obj) {
        const chartModel = _getActiveChartModelById(cb_obj.origin.id);
        if (!chartModel || chartModel.name === 'frequency_bar') {
            console.log('[Controller:handleTap]', 'Tap on frequency_bar or unknown chart, ignoring.');
            return;
        }

        const raw_x = cb_obj.x;
        if (raw_x === undefined || raw_x === null || isNaN(raw_x)) {
            console.warn("[Controller:handleTap]", "Invalid x coordinate:", raw_x);
            return;
        }

        const position = _getChartPositionByName(chartModel.name);
        let snapped_x = raw_x;

        if (position && chartModel.name.includes('_combined_time_series') && _state.activeLineChartData[position]) {
            const activeData = _state.activeLineChartData[position];
            const closest_idx = findClosestDateIndex(activeData.Datetime, raw_x);
            if (closest_idx !== -1) {
                snapped_x = activeData.Datetime[closest_idx];
            }
        } else if (position && chartModel.name.includes('_combined_spectrogram') && _state.activeSpectralData[position]) {
            const activeData = _state.activeSpectralData[position];
            const closest_idx = findClosestDateIndex(activeData.times_ms, raw_x);
            if (closest_idx !== -1) {
                snapped_x = activeData.times_ms[closest_idx];
            }
        }
        
        console.log('[Controller:handleTap]', `Chart: ${chartModel.name}, Position: ${position}, X: ${snapped_x}`);

        _state.verticalLinePosition = snapped_x;
        if (position) { // Only update focus if tap is on a known position's chart
             _state.freqBarFocus = { type: 'tap', position: position, timestamp: snapped_x };
        }
       
        renderTapLines(snapped_x); // Update all tap lines and their labels

        if (!_state.hoverContext.isActive) { // Don't let tap override active hover for freq bar
            renderFrequencyBar(snapped_x);
        }
        
        _sendSeekCommand(snapped_x);

        // Update step size based on the specific chart tapped
        if (position && chartModel.name.includes('_combined_time_series') && _state.activeLineChartData[position]) {
            _state.stepSize = calculateStepSize(_state.activeLineChartData[position]);
        }
        // If spectral chart tapped, step size might not be relevant or use a default.
    }
    
    /**
     * Handles hover events on line charts.
     */
    function handleLineChartHover(cb_data, chartIndex) {
        const chartModel = _models.charts[chartIndex]; // Assumes chartIndex is valid for _models.charts
        if (!chartModel || !chartModel.name.includes('_combined_time_series')) {
            // console.log('[Controller:handleLineChartHover]', 'Hover not on a line chart.');
            return; // Only for line charts for now
        }

        const geometry = cb_data.geometry;
        if (!geometry || !Number.isFinite(geometry.x)) {
            clearHoverEffects();
            // If mouse leaves, restore frequency bar to tap/playback state
            if (_state.hoverContext.isActive && _state.hoverContext.source === 'line_chart') {
                _state.hoverContext.isActive = false; // Deactivate line chart hover for freq bar
                renderFrequencyBar(_state.verticalLinePosition); // Re-render based on main state
            }
            return;
        }

        const hoveredX = geometry.x;
        if (_state.lastHoverX === hoveredX) return; // Debounce
        _state.lastHoverX = hoveredX;

        renderHoverEffects(chartModel, hoveredX, chartIndex);

        // Optional: Update frequency bar on line chart hover if desired
        // const position = _getChartPositionByName(chartModel.name);
        // if (position) {
        //     _state.hoverContext = {
        //         isActive: true,
        //         source: 'line_chart', // Special marker
        //         position: position,
        //         timestamp: hoveredX,
        //         dataForBar: _state.activeSpectralData[position] // Use the globally selected param/view
        //     };
        //     renderFrequencyBar(hoveredX);
        // }
    }

    /**
     * Handles hover events on spectrograms.
     */
    function handleSpectrogramHover(cb_data, position_name) {
        const chartModel = _models.charts.find(c => c.name === `${position_name}_combined_spectrogram`);
        const hover_div = _models.uiPositionElements[position_name]?.spectrogram_hover_div;

        if (!chartModel || !hover_div) {
            console.warn(`[Controller:handleSpectrogramHover] Missing chart or hover_div for ${position_name}`);
            return;
        }
        
        const preparedData = _state.activeSpectralData[position_name]; // Data for current global param/view
        if (!preparedData) {
            hover_div.text = "Hover over spectrogram (data not loaded)";
            return;
        }

        const { times_ms, frequency_labels, levels_matrix, n_freqs } = preparedData;
        const { x: gx, y: gy } = cb_data.geometry;
        const fig_x_range = chartModel.x_range; // Spectrogram's own x_range
        
        // Basic check against figure x_range and y index range
        const is_inside = !(gx < fig_x_range.start || gx > fig_x_range.end || gy < -0.5 || gy > n_freqs - 0.5);

        if (is_inside) {
            const time_idx = findClosestDateIndex(times_ms, gx);
            if (time_idx === -1) return;
            
            const freq_idx = Math.max(0, Math.min(n_freqs - 1, Math.floor(gy + 0.5)));
            const time_val_ms = times_ms[time_idx];
            
            if (time_idx >= levels_matrix.length || freq_idx >= levels_matrix[time_idx].length) {
                hover_div.text = "Data Error";
                return;
            }
            const level_val_hover = levels_matrix[time_idx][freq_idx]; // levels_matrix is (n_times, n_freqs)
            const time_str = new Date(time_val_ms).toLocaleString();
            const freq_str = frequency_labels[freq_idx];
            let level_str_hover = (level_val_hover == null || isNaN(level_val_hover)) ? "N/A" : level_val_hover.toFixed(1) + " dB";
            hover_div.text = `<b>Time:</b> ${time_str} | <b>Freq:</b> ${freq_str} | <b>Level:</b> ${level_str_hover} (${_state.selectedParameter})`;

            // Update frequency bar based on this hover
            // For spectrogram hover, we use the *active* spectral data for that spectrogram (which respects global param/view)
            _state.hoverContext = {
                isActive: true,
                source: 'spectrogram',
                position: position_name,
                timestamp: time_val_ms,
                dataForBar: preparedData // Pass the already selected data
            };
            renderFrequencyBar(time_val_ms);

        } else {
            hover_div.text = "Hover over spectrogram to view details";
            if (_state.hoverContext.isActive && _state.hoverContext.source === 'spectrogram') {
                _state.hoverContext.isActive = false;
                // Restore frequency bar to main state (tap or playback)
                renderFrequencyBar(_state.freqBarFocus.timestamp || _state.verticalLinePosition);
            }
        }
    }


    // --- Audio Button State Management ---
    function _updatePlayButtonsState(isPlaying) { /* ... unchanged, but ensure it reads _state.isPlaying & _state.activeAudioPosition ... */ }

    // --- Other Interaction Functions (largely unchanged) ---
    function _sendSeekCommand(x) { /* ... unchanged ... */ }
    function _updateFrequencyTable(levels, labels) { /* ... unchanged ... */ }


    // --- Public API - Initialize App ---
    function initializeApp(models, options) {
        console.info('[NoiseSurveyApp]', 'Initializing...');
        _models = models; // Store all Bokeh models passed from Python

        // Populate _state.availablePositions
        if (_models.allSpectralData) {
            _state.availablePositions = Object.keys(_models.allSpectralData);
        } else if (_models.allTimeSeriesSources) { // Fallback if no spectral data
            const positions = new Set();
            Object.keys(_models.allTimeSeriesSources).forEach(key => {
                const pos = key.split('_')[0];
                if (pos) positions.add(pos);
            });
            _state.availablePositions = Array.from(positions);
        }
        if (_state.availablePositions.length === 0) {
            console.error('[NoiseSurveyApp] No positions found. Cannot initialize properly.');
            return false;
        }
        console.log('[NoiseSurveyApp]', 'Available positions:', _state.availablePositions);
        _state.freqBarFocus.position = _state.availablePositions[0]; // Default focus to first position

        // Initialize state for each position
        _state.selectedParameter = _models.paramSelect?.value || _models.selectedParamHolder?.text || 'LZeq';
        _state.availablePositions.forEach(pos => {
            _state.viewType[pos] = 'overview'; // Default to overview
            _updateActiveData(pos, 'overview', _state.selectedParameter);
        });
        
        // Initial tap line position (e.g., start of first chart)
        if (_models.charts.length > 0 && _models.charts[0]?.x_range?.start !== undefined) {
            _state.verticalLinePosition = _models.charts[0].x_range.start;
        } else {
            _state.verticalLinePosition = 0;
        }
        _state.freqBarFocus.timestamp = _state.verticalLinePosition;


        // Store UI elements that need direct access
        _state.availablePositions.forEach(pos => {
            if (!_models.uiPositionElements[pos]) _models.uiPositionElements[pos] = {};
            // Example: find hover div for this position's spectrogram
             const specChart = _models.charts.find(c => c.name === `${pos}_combined_spectrogram`);
             if (specChart) { // This relies on the hover div being passed in the initial `models` struct
                 // We need to ensure Python passes these correctly, or find them via Bokeh structure.
                 // Assuming models.ui_elements = { SW_spectrogram_hover_div: DivModel, ... }
                 // This part needs careful alignment with how Python provides these specific Divs.
                 // For now, let's assume `_models.uiPositionElements[pos].spectrogram_hover_div` will be populated
                 // if Python sends a `hover_divs_by_position` dict in `models`.
             }
        });


        // Setup playback status listener (from Python to JS)
        if (_models.playbackStatusSource) {
            _models.playbackStatusSource.on_change('data', () => {
                const statusData = _models.playbackStatusSource.data;
                const pyIsPlaying = statusData.is_playing[0];
                const pyActivePosition = statusData.active_position[0];
                
                console.log('[NoiseSurveyApp_playbackStatus]', `Python state: playing=${pyIsPlaying}, pos=${pyActivePosition}`);

                _state.isPlaying = pyIsPlaying;
                _state.activeAudioPosition = pyActivePosition;
                _updatePlayButtonsState(_state.isPlaying); // Update button visuals

                if (_state.isPlaying && _state.activeAudioPosition) {
                    _state.freqBarFocus = { type: 'playback', position: _state.activeAudioPosition, timestamp: _state.verticalLinePosition };
                    // If playback starts/changes, freq bar should follow. Timestamp is updated by synchronizePlaybackPosition.
                } else if (!_state.isPlaying && _state.freqBarFocus.type === 'playback') {
                    // Playback stopped, revert focus to tap (or last known good state)
                    const lastTappedPosition = _state.availablePositions[0]; // Simplified, ideally track last tap
                     _state.freqBarFocus = { type: 'tap', position: lastTappedPosition, timestamp: _state.verticalLinePosition };
                }
                // Potentially call renderFrequencyBar here if playback state change implies focus change for it
                // renderFrequencyBar(_state.verticalLinePosition); // Timestamp might be slightly out of sync here
            });
        }
        
        // Setup keyboard navigation
        const kbNavEnabled = options?.enableKeyboardNavigation ?? false;
        if (kbNavEnabled) { setupKeyboardNavigation(); }

        // Initial render of everything
        renderAllVisuals();
        
        console.info('[NoiseSurveyApp]', 'Initialization complete.');
        return true;
    }


    // --- Audio Player Integration ---
    function synchronizePlaybackPosition(ms) { // Called by Python timer
        console.log('[NoiseSurveyApp_sync]', `Syncing to ${ms}`);
        _state.verticalLinePosition = ms;

        if (_state.isPlaying && _state.activeAudioPosition) {
            _state.freqBarFocus = { type: 'playback', position: _state.activeAudioPosition, timestamp: ms };
        }
        
        renderTapLines(ms);
        renderFrequencyBar(ms); // Uses _state.freqBarFocus which was just updated
        return true;
    }

    function notifyPlaybackStopped() { // Called by Python on EOF/error
        console.log("[NoiseSurveyApp_playbackStop]", "Playback stopped notification.");
        // Python's playbackStatusSource should already update _state.isPlaying
        // This function is more of a backup or for actions needed beyond state update
        if (_state.isPlaying) { // If JS thought it was playing, but Python says stop
            _state.isPlaying = false;
            // activeAudioPosition might be cleared by playbackStatusSource or kept for context
            _updatePlayButtonsState(false);
        }
         // Revert freq bar focus if it was on playback
        if (_state.freqBarFocus.type === 'playback') {
            const fallbackPos = _state.freqBarFocus.position || _state.availablePositions[0];
            _state.freqBarFocus = { type: 'tap', position: fallbackPos, timestamp: _state.verticalLinePosition };
            renderFrequencyBar(_state.verticalLinePosition);
        }
    }

    // --- Keyboard Navigation ---
    function handleKeyPress(e) {
        // ... (check for input fields, etc.)
        const targetTagName = e.target.tagName.toLowerCase();
        if (targetTagName === 'input' || targetTagName === 'textarea' || targetTagName === 'select') return;

        let currentX = _state.verticalLinePosition;
        // ... (fallback for currentX if null) ...
        if (currentX === null || currentX === undefined) { currentX = 0; }


        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            e.preventDefault();
            let newX = e.key === 'ArrowLeft' ? currentX - _state.stepSize : currentX + _state.stepSize;
            // ... (clamp newX to chart ranges) ...
            const firstChart = _models.charts.find(c => c.name && c.name.includes('_combined_time_series'));
            if (firstChart && firstChart.x_range) {
                newX = Math.max(firstChart.x_range.start, Math.min(firstChart.x_range.end, newX));
            }

            _state.verticalLinePosition = newX;
            _state.freqBarFocus.timestamp = newX; // Assume tap-like focus for keyboard nav
            // If navigating, ensure focus position is set, e.g., to the first one or last tapped.
            if (!_state.freqBarFocus.position && _state.availablePositions.length > 0) {
                 _state.freqBarFocus.position = _state.availablePositions[0];
                 _state.freqBarFocus.type = 'tap'; // Or 'keyboard'
            }


            renderTapLines(newX);
            _sendSeekCommand(newX);
            if (!_state.hoverContext.isActive) { // Don't override hover
                renderFrequencyBar(newX);
            }

        } else if (e.key === ' ' || e.code === 'Space') {
            e.preventDefault();
            togglePlayPause();
        }
    }
    function setupKeyboardNavigation() { /* ... unchanged, calls enableKeyboardNavigation ... */ }
    function enableKeyboardNavigation() { /* ... unchanged ... */ }
    function disableKeyboardNavigation() { /* ... unchanged ... */ }

    // --- Audio Control Wrappers (JS -> Python via model changes) ---
    // These functions (_updatePlayButtonsState, startAudioPlayback, pauseAudioPlayback,
    // handlePositionPlayClick, togglePlayPause) remain largely the same in terms of
    // how they interact with Bokeh models to signal Python.
    // Python side is responsible for updating _models.playbackStatusSource.
    // _updatePlayButtonsState will be called by the listener on playbackStatusSource.
    // Example:
    function togglePlayPause() {
        console.log("[Controller:togglePlayPause]");
        // Logic to determine if playing or paused (can use _state.isPlaying or button disabled state)
        // and call appropriate Python-triggering function.
        // For example, if trying to play:
        if (!_state.isPlaying) {
            if (!_state.activeAudioPosition && _state.availablePositions.length > 0) {
                // Auto-select first position if none is active (for main play button)
                const targetPos = _state.availablePositions[0];
                 console.log(`[Controller:togglePlayPause] No active audio position, attempting to play default: ${targetPos}`);
                _models.playRequestSource.data = { 'position': [targetPos], 'time': [_state.verticalLinePosition] };
                _models.playRequestSource.change.emit();
            } else if (_state.activeAudioPosition) {
                 console.log(`[Controller:togglePlayPause] Attempting to resume/play current: ${_state.activeAudioPosition}`);
                _models.playRequestSource.data = { 'position': [_state.activeAudioPosition], 'time': [_state.verticalLinePosition] };
                _models.playRequestSource.change.emit();
            } else {
                 console.warn("[Controller:togglePlayPause] Cannot play: No positions available.");
            }
        } else { // Is playing, so pause
             console.log("[Controller:togglePlayPause] Attempting to pause.");
            _models.playRequestSource.data = { 'position': ['pause_request'], 'time': [_state.verticalLinePosition] };
            _models.playRequestSource.change.emit();
        }
    }
    // Other audio control functions like startAudioPlayback, pauseAudioPlayback, handlePositionPlayClick
    // will similarly update _models.playRequestSource or _models.playButton.clicks / _models.pauseButton.clicks
    // and Python will react, then update _models.playbackStatusSource.
    // The main change is that JS-side state updates for isPlaying/activeAudioPosition
    // are now primarily driven by the playbackStatusSource callback.


    // --- Module Exports ---
    return {
        init: initializeApp,
        // State Access (for debugging or specific needs)
        getState: function () { return JSON.parse(JSON.stringify(_state)); },
        // Direct event handlers that are called from Bokeh CustomJS
        // These are now thin wrappers that call the new controller functions.
        interactions: {
            onTap: function(cb_obj) { // cb_obj passed from Bokeh
                handleTap(cb_obj);
            },
            onHover: function(hoverLines, hoverLabels, cb_data, chart_index) { // Bokeh passes these from CustomJS
                // Note: The new architecture makes hoverLines and hoverLabels arguments less relevant
                // as renderHoverEffects will use _models.hoverLines etc.
                // This is called for LINE CHART hover.
                handleLineChartHover(cb_data, chart_index);
            },
            onSpectrogramHover: function(cb_data, position_name) { // CustomJS for spectrogram hover
                handleSpectrogramHover(cb_data, position_name);
            },
            onZoom: function(cb_obj) { /* Optional: handle zoom if needed */ }
        },
        // Parameter change still directly called
        handleParameterChange: handleParameterChange,
        // Toggle click needs to be exposed if called from CustomJS directly
        handleToggleClick: handleToggleClick,
        // Audio sync and notifications from Python
        synchronizePlaybackPosition: synchronizePlaybackPosition,
        notifyPlaybackStopped: notifyPlaybackStopped,
        // Audio controls called from Python-generated buttons (if any still do that) or other JS
        togglePlayPause: togglePlayPause, // Example if main toggle button calls this
        handlePositionPlayClick: function(positionName) { // Exposed for position play buttons
            console.log(`[NoiseSurveyApp] Position play click for: ${positionName}`);
            _models.playRequestSource.data = { 'position': [positionName], 'time': [_state.verticalLinePosition] };
            _models.playRequestSource.change.emit();
        }
        // Old functions like updateFrequencyBar, showTapLines, hideTapLines, updateTapLinePosition
        // are now replaced by the render* functions and direct state manipulation.
    };
})();

// --- Global Exposure for Bokeh CustomJS Callbacks ---
// Ensure these point to the new interaction handlers within NoiseSurveyApp
window.handleTap = function (cb_obj) { // cb_obj is from Bokeh
    if (window.NoiseSurveyApp && window.NoiseSurveyApp.interactions && window.NoiseSurveyApp.interactions.onTap) {
        window.NoiseSurveyApp.interactions.onTap(cb_obj);
    } else { console.error("NoiseSurveyApp.interactions.onTap not found"); }
};

window.handleHover = function (hoverLines, hoverLabelsModels, cb_data, chart_index) { // For line charts
    // hoverLines, hoverLabelsModels are legacy, chart_index and cb_data are key
    if (window.NoiseSurveyApp && window.NoiseSurveyApp.interactions && window.NoiseSurveyApp.interactions.onHover) {
        window.NoiseSurveyApp.interactions.onHover(null, null, cb_data, chart_index); // Pass null for old args
    } else { console.error("NoiseSurveyApp.interactions.onHover not found"); }
};

window.handleSpectrogramHover = function (cb_data, hover_div_model, bar_source_model, bar_x_range_model, position_name, fig_x_range_model) {
    // hover_div_model, bar_source_model, bar_x_range_model, fig_x_range_model are models Bokeh passes.
    // The new JS handleSpectrogramHover inside NoiseSurveyApp will use _models and _state.
    // position_name and cb_data are the most important.
    if (window.NoiseSurveyApp && window.NoiseSurveyApp.interactions && window.NoiseSurveyApp.interactions.onSpectrogramHover) {
        window.NoiseSurveyApp.interactions.onSpectrogramHover(cb_data, position_name);
    } else { console.error("NoiseSurveyApp.interactions.onSpectrogramHover not found"); }
};

window.handleParameterChange = function (param_value) {
    if (window.NoiseSurveyApp && window.NoiseSurveyApp.handleParameterChange) {
        window.NoiseSurveyApp.handleParameterChange(param_value);
    } else { console.error("NoiseSurveyApp.handleParameterChange not found"); }
};

window.handlePositionPlayClick = function (positionName) {
    if (window.NoiseSurveyApp && window.NoiseSurveyApp.handlePositionPlayClick) {
        window.NoiseSurveyApp.handlePositionPlayClick(positionName);
    } else { console.error("NoiseSurveyApp.handlePositionPlayClick not found"); }
};

window.handleCombinedChartToggle = function(is_active, position, toggle_widget_model) {
    // is_active, position, toggle_widget_model are passed by Bokeh CustomJS
    if (window.NoiseSurveyApp && window.NoiseSurveyApp.handleToggleClick) {
        window.NoiseSurveyApp.handleToggleClick(is_active, position, toggle_widget_model);
    } else { console.error("NoiseSurveyApp.handleToggleClick not found"); }
};

// Global functions called by Python
window.synchronizePlaybackPosition = function (ms) {
    if (window.NoiseSurveyApp && window.NoiseSurveyApp.synchronizePlaybackPosition) {
        return window.NoiseSurveyApp.synchronizePlaybackPosition(ms);
    } else { console.error("NoiseSurveyApp.synchronizePlaybackPosition not found"); return false; }
};
window.notifyPlaybackStopped = function () {
    if (window.NoiseSurveyApp && window.NoiseSurveyApp.notifyPlaybackStopped) {
        return window.NoiseSurveyApp.notifyPlaybackStopped();
    } else { console.error("NoiseSurveyApp.notifyPlaybackStopped not found"); return false; }
};

console.log("[DEBUG] app.js loaded and NoiseSurveyApp object created (State-Driven Refactor).");