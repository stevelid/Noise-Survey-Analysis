console.log("[DEBUG] app.js: Script loading started");

window.NoiseSurveyApp = (function () {
    'use strict';

    console.log("[DEBUG] NoiseSurveyApp: IIFE called");

    // =======================================================================================
    //           PRIVATE MODELS & STATES
    // =======================================================================================
    let _models = { // Populated by initializeApp
        charts: [],
        chartsSources: {},
        timeSeriesSources: {}, // Overview/log raw data sources (_models.sources[pos_overview_raw_data], _models.sources[pos_log_raw_data])
        preparedGlyphData: {}, // Master store: { pos: { spectral: { prepared_data: {param: {times_ms, levels_matrix,...}}}, spectral_log: {...} }}
        clickLines: [],
        labels: [], // Labels for tap lines
        hoverLines: [], // Added for managing hover lines if needed centrally
        visibilityCheckBoxes: [],
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
        seekCommandSource: null,
        playRequestSource: null,
        // UI elements that might need direct access for specific updates (e.g., hover divs for spectrograms)
        uiPositionElements: {}, // e.g., { SW: { spectrogram_hover_div: model } }
    };


    let _state = {
        // Core state
        selectedParameter: 'LZeq',  // Currently selected spectral parameter
        viewType: 'overview',       // 'overview' | 'log' - Current view for line and spectral charts
        activeLineChartData: {},    // { position: { Datetime: [], LAeq: [], ... } } - Data currently active for line chart
        activeSpectralData: {},     // { position: { times_ms:[], min_val:X, max_val:Y, ... } } - Data for spec
        displayedDataTypes: {},     // { position: { line: 'overview' | 'log', spec: 'overview' | 'log' } } - Data types currently displayed for each position TODO: incorporate this with the data in one state object. 
        activeFreqBarData: {        //??? this should not be touched by the action controllers, it is updated by the state controller. Should is be here or in another formate? 
            levels: [],
            labels: [],
            sourceposition: '',     //position of the data
            sourceType: '',         //type of the data 'timeseries' | 'spectrogram'
            timestamp: null,        //ms timestamp of the frequ data
            setBy: null,            //'tap' | 'playback' | 'hover', data was selected by
            param: null,
            dataViewType: 'overview'    //'overview' | 'log'
        },          // Data currently active for frequency bar

        // Interaction state
        verticalLinePosition: null, // ms timestamp of the red tap line
        lastHoverX: null,           // Last hovered X position on any chart
        chartVisibility: {},        // { chartName: true | false } - Visibility state for each chart

        keyboardNavigationEnabled: false,
        stepSize: 300000,           // ms for keyboard nav

        // Playback state (mostly driven by playbackStatusSource from Python)
        isPlaying: false,
        activeAudioPosition: null,  // Position name ('SW', 'N', etc.) being played

        // Configuration / Initialization
        availablePositions: [],     // Populated from _models.spectralParamCharts keys

        tapContext: {
            isActive: false,      // true if any chart is currently being hovered
            sourceChartId: null,  // The ID of the chart currently being hovered (e.g., 'figure_SW_timeseries')
            sourceChartName: null, // The name of the chart currently being hovered
            position: null,       // The position associated with the hovered chart ('SW', 'N', etc.)
            timestamp: null,      // Timestamp of the hover event
            setBy: null,          // The type of the source ('tap' or 'playback')
        },
        hoverContext: {
            isActive: false,      // true if any chart is currently being hovered
            sourceChartId: null,  // The ID of the chart currently being hovered (e.g., 'figure_SW_timeseries')
            sourceChartName: null, // The name of the chart currently being hovered
            position: null,       // The position associated with the hovered chart ('SW', 'N', etc.)
            timestamp: null,      // Timestamp of the hover event
            spec_y: null,           // Y coordinate of the hover event in the spectrogram
            sourceType: null,     // The type of the source ('timeseries' or 'spectrogram')
        },
    };


    // =======================================================================================
    //           UTILITY FUNCTIONS
    // =======================================================================================
    function _getChartModel(nameOrId, isId = false) {
        // A single helper to abstract chart model retrieval
        if (_models.chartsById && isId) {
            return _models.chartsById.get(nameOrId);
        }
        return _models.charts.find(chart => (isId ? chart?.id === nameOrId : chart?.name === nameOrId));
    }


    function _getChartPositionByName(chartName) {
        try {
            //console.log("[DEBUG] _getChartPositionByName: Function called");
            if (!chartName) return null;
            // Extracts position like 'SW' from 'figure_SW_timeseries' or 'figure_SW_spectrogram'
            const parts = chartName.split('_');
            if (parts.length >= 2 && _state.availablePositions.includes(parts[1])) {
                return parts[1];
            } else {
                //fallback approach
                return chartName.replace('figure_', '').replace('_timeseries', '').replace('_spectrogram', '');
            }
        } catch (error) {
            console.error("Error in _getChartPositionByName:", error);
            return null;
        }
    }

    function findClosestDateIndex(dates, x) {
        try {
            //console.log("[DEBUG] findClosestDateIndex: Function called");
            // Add checks for robustness
            if (dates === null || dates === undefined || typeof dates.length !== 'number' || dates.length === 0) {
                console.error('[findClosestDateIndex]', 'Invalid dates array:', dates);
                return -1;
            }
            if (typeof x !== 'number' || isNaN(x)) {
                console.error('[findClosestDateIndex]', 'Invalid x value:', x);
                return -1;
            }

            let low = 0;
            let high = dates.length - 1;
            let closest_idx = 0;
            let min_diff = Infinity;

            // Handle edge cases: x before start or after end
            if (x <= dates[0]) { return 0; }
            if (x >= dates[high]) { return high; }

            // Linear scan approach (robust for potentially unsorted/gappy data):
            min_diff = Math.abs(dates[0] - x); // Initialize difference
            for (let j = 1; j < dates.length; j++) {
                let diff = Math.abs(dates[j] - x);
                if (diff < min_diff) {
                    min_diff = diff;
                    closest_idx = j;
                }
            }
            return closest_idx;
        } catch (error) {
            console.error("Error in findClosestDateIndex:", error);
            return -1;
        }
    }

    function _findAssociatedDateIndex(activeData, timestamp) {
        //the datapoint in activedata which is applicable to timestamp is the last Datetime value less than or equal to timestamp
        try {
            for (let i = activeData.Datetime.length - 1; i >= 0; i--) {
                if (activeData.Datetime[i] <= timestamp) {
                    return i;
                }
            }
            return -1;
        } catch (error) {
            console.error("Error in _findAssociatedDateIndex:", error);
            return -1;
        }
    }


    function _createLabelTextFromActiveChartData(labelModel, timestamp) {
        try {

            if (!labelModel) { console.error("Error in _createLabelTextFromActiveChartData: Invalid label data"); return "Error: Invalid data for label"; }

            const position = labelModel.name.replace('label_', '').replace('_timeseries', ''); // Assuming label names are like 'label_SW' //TODO: a better way of dealing with names
            const activeData = _state.activeLineChartData[position];

            if (!activeData || !activeData.Datetime || activeData.Datetime.length === 0) {
                console.warn('[Renderer:_createLabelTextFromActiveChartData]', `No active data for label position: ${position}`);
                return "Data N/A";
            }

            const latest_idx = _findAssociatedDateIndex(activeData, timestamp);
            if (latest_idx === -1) {
                console.warn('[Renderer:_createLabelTextFromActiveChartData]', `No suitable data point for timestamp ${timestamp} in position ${position}`);
                return "No data point";
            }

            const date = new Date(activeData.Datetime[latest_idx]);
            let label_text = `Time: ${date.toLocaleString()}\n`;
            for (const key in activeData) {
                if (activeData.hasOwnProperty(key) && key !== 'Datetime' && key !== 'index') {
                    const value = activeData[key][latest_idx];
                    if (value !== undefined && value !== null && !isNaN(value)) {
                        const formatted_value = parseFloat(value).toFixed(1);
                        const unit = (key.startsWith('L') || key.includes('eq') || key.includes('max') || key.includes('min')) ? ' dB' : '';
                        label_text += `${key}: ${formatted_value}${unit}\n`;
                    }
                }
            }

            return label_text;

        } catch (error) {
            console.error("Error in createLabelText:", error);
            return "Error: Could not create label";
        }
    }
    function _positionLabel(labelModel, x) {
        try {
            //console.log("[DEBUG] positionLabel: Function called with label", labelModel, "and x", x);

            if (!labelModel) { console.error('[Renderer:positionLabel]', 'Label model not found.'); return; }

            const associatedChartName = `figure_${labelModel.name.replace('label_', '')}`;
            const chart = _getChartModel(associatedChartName);


            if (!chart || !chart.x_range || !chart.y_range) { console.error('[Renderer:positionLabel]', 'Chart ranges not found.'); return; }
            const xStart = chart.x_range.start ?? 0; // Use nullish coalescing for defaults
            const xEnd = chart.x_range.end ?? 0;
            const yStart = chart.y_range.start ?? 0;
            const yEnd = chart.y_range.end ?? 0;

            if (xStart === xEnd || yStart === yEnd) { console.error('[Renderer:positionLabel]', 'Chart ranges are invalid.'); return; }

            const middleX = xStart + (xEnd - xStart) / 2;
            const topY = yEnd - (yEnd - yStart) / 5; // Position near top of chart

            // Position label to avoid overlapping the vertical line (x)
            if (x <= middleX) {
                labelModel.x = x + (xEnd - xStart) * 0.02; // Offset slightly right
                labelModel.text_align = 'left';
            } else {
                labelModel.x = x - (xEnd - xStart) * 0.02; // Offset slightly left
                labelModel.text_align = 'right';
            }
            labelModel.y = topY;
            labelModel.text_baseline = 'middle';
        } catch (error) {
            console.error("Error in positionLabel:", error);
        }
    }


    function calculateStepSize(sourceData) {
        try {
            //console.log("[DEBUG] calculateStepSize: Function called");
            const DEFAULT_STEP_SIZE = 300000;
            if (!sourceData?.Datetime || sourceData.Datetime.length < 2) {
                return DEFAULT_STEP_SIZE;
            }
            const times = sourceData.Datetime;
            const interval = times[1] - times[0]; // Simple interval
            return Math.max(1000, Math.min(3600000, Math.round(interval || DEFAULT_STEP_SIZE)));
        } catch (error) {
            console.error("Error in calculateStepSize:", error);
            return 300000; // Return default on error
        }
    }

    /**
     * Matrix utility functions for spectrogram processing
     */
    const MatrixUtils = {
        /**
         * Transposes a 2D matrix (rows become columns, columns become rows)
         * @param {number[][]} matrix - The input matrix to transpose
         * @returns {number[][]} The transposed matrix
         */
        transpose(matrix) {
            if (!matrix || matrix.length === 0 || matrix[0].length === 0) {
                return [];
            }
            const rows = matrix.length;
            const cols = matrix[0].length;
            const transposed = Array(cols).fill(0).map(() => Array(rows).fill(0));

            for (let i = 0; i < rows; i++) {
                for (let j = 0; j < cols; j++) {
                    transposed[j][i] = matrix[i][j];
                }
            }
            return transposed;
        },

        /**
         * Updates existing Bokeh image data in place with new matrix data
         * @param {Float32Array} existingImageData - The existing Bokeh image data
         * @param {number[][]} newMatrix2D - The new matrix data to apply
         */
        updateBokehImageData(existingImageData, newMatrix2D) {
            if (!newMatrix2D || newMatrix2D.length === 0) {
                console.warn('[MatrixUtils] Cannot update with empty matrix data');
                return;
            }

            const height = newMatrix2D.length;
            const width = newMatrix2D[0] ? newMatrix2D[0].length : 0;
            const flattenedData = newMatrix2D.flat();

            // Verify data compatibility
            if (flattenedData.length !== existingImageData.length) {
                console.warn('[MatrixUtils] Matrix size mismatch:', {
                    expected: existingImageData.length,
                    received: flattenedData.length
                });
            }

            // Copy new data to existing structure
            for (let i = 0; i < Math.min(flattenedData.length, existingImageData.length); i++) {
                existingImageData[i] = flattenedData[i];
            }

            // Update dimensions
            existingImageData.width = width;
            existingImageData.height = height;
        }
    };

    /**
     * Creates a debounced version of a function that delays execution until after a wait period.
     * @param {Function} func - The function to debounce.
     * @param {number} wait - The number of milliseconds to wait before executing the function.
     * @returns {Function} The debounced function.
     */
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
        try {
            //console.log("[DEBUG] handleTap: Function called");
            const chartModel = _getChartModel(cb_obj.origin.id, true);
            if (!chartModel || chartModel.name === 'frequency_bar') {
                console.log('[Controller:handleTap]', 'Tap on frequency_bar or unknown chart, ignoring.');
                return;
            }

            const raw_x = cb_obj.x;
            if (raw_x === undefined || raw_x === null || isNaN(raw_x)) {
                console.warn("[Controller:handleTap]", "Invalid x coordinate from tap event:", raw_x);
                return;
            }

            const position = _getChartPositionByName(chartModel.name);
            let snapped_x = raw_x;

            // Snap to actual data points for better accuracy
            if (position && chartModel.name.includes('_timeseries') && _state.activeLineChartData[position]) {
                const activeData = _state.activeLineChartData[position];
                const closest_idx = findClosestDateIndex(activeData.Datetime, raw_x);
                if (closest_idx !== -1) {
                    snapped_x = activeData.Datetime[closest_idx];
                }
            } else if (position && chartModel.name.includes('_spectrogram') && _state.activeSpectralData[position]) {
                const activeData = _state.activeSpectralData[position];
                const closest_idx = findClosestDateIndex(activeData.Datetime, raw_x);
                if (closest_idx !== -1) {
                    snapped_x = activeData.Datetime[closest_idx];
                }
            }

            // --- Update State ---
            _state.verticalLinePosition = snapped_x;

            _state.tapContext = {
                isActive: true,
                timestamp: snapped_x,
                position: position,
                sourceChartName: chartModel.name
            };

            _updateActiveData();

            // --- Call Renderers ---
            renderTapLines(snapped_x);
            renderFrequencyBar();
            renderLabels();

            // --- Trigger Backend Action ---
            // _sendSeekCommand(snapped_x); // This function is not defined in the provided code
        } catch (error) {
            console.error("Error in handleTap:", error);
        }
    }

    /**
    * Handles the click of a toggle button for a position.
    * Switches between 'overview' and 'log' views for both line and spectral charts.
    */
    function handleViewToggle(isActive, toggleWidget) { // toggleWidget passed to update its label
        try {
            console.log("[DEBUG] handleViewToggle: Function called");
            const newViewType = isActive ? 'log' : 'overview';

            _state.viewType = newViewType;
            _updateActiveData(_state.viewType, _state.selectedParameter);
            renderLineCharts();
            renderSpectrograms();
            renderTapLines(_state.verticalLinePosition); // Re-render tap lines as labels might change
            renderFrequencyBar();
            renderLabels();

            // Update the toggle button's label
            if (toggleWidget) {
                toggleWidget.label = `Switch to ${newViewType === 'overview' ? 'Log' : 'Overview'}`;
            }
        } catch (error) {
            console.error("Error in handleViewToggle:", error);
        }
    }

    function handleParameterChange(value, selectWidget) {
        try {
            console.log("[DEBUG] handleParameterChange: Function called");
            console.log('[Controller:handleParameterChange]', { value });

            if (!value) { console.warn('[Controller:handleParameterChange]', 'Null/undefined parameter received.'); return; }

            _state.selectedParameter = value;
            _updateActiveData();
            renderLineCharts();
            renderSpectrograms();
            renderTapLines(); // Re-render tap lines as labels might change
            renderFrequencyBar();
            renderLabels();
        } catch (error) {
            console.error("Error in handleParameterChange:", error);
        }
    }

    /**
     * Handles hover events on line charts.
     */
    function handleChartHover(cb_data, chartName) {
        try {
            //if (!cb_data.geometry) { return; }
            let isActive = true;
            let sourceType = null;

            //check if on a chart
            const geometry = cb_data.geometry;
            if (!geometry || !Number.isFinite(geometry.x)) {
                isActive = false;
            }

            //check for chart type
            if (chartName.includes('_timeseries')) {
                sourceType = 'timeseries';
            } else if (chartName.includes('_spectrogram')) {
                sourceType = 'spectrogram';
            }

            if (isActive) {
                _state.hoverContext = {
                    isActive: true,      // true if any chart is currently being hovered
                    sourceChartName: chartName, // The name of the chart currently being hovered
                    timestamp: geometry.x,      // Timestamp of the hover event
                    spec_y: geometry.y,
                    sourceType: sourceType,
                    position: _getChartPositionByName(chartName),
                }
            } else {
                _state.hoverContext.isActive = false;
            }

            _updateActiveData();
            renderHoverLines();
            renderLabels();
            renderFrequencyBar();
            renderSpectrogramHoverDiv();


            // Optional: Update frequency bar on line chart hover if desired
            // const position = _getChartPositionByName(chartModel.name);
            // if (position) {
            //   _state.hoverContext = {
            //      isActive: true,
            //      source: 'line_chart', // Special marker
            //      position: position,
            //      timestamp: hoveredX,
            //      dataForBar: _state.activeSpectralData[position] // Use the globally selected param/view
            //   };
            //   renderFrequencyBar(hoveredX);
            // }
        } catch (error) {
            console.error("Error in handleChartHover:", error);
        }
    }
    // Debounced version of handleChartHover
    const debouncedHandleChartHover = debounce(handleChartHover, 500);

    // This function was not provided in the original code, adding a placeholder for it
    function handleSpectrogramHover(cb_data, position_name) {
        try {
            console.log("[DEBUG] handleSpectrogramHover: Function called with data:", cb_data, "for position:", position_name);
            // Implement spectrogram hover logic here if needed
        } catch (error) {
            console.error("Error in handleSpectrogramHover:", error);
        }
    }

    /**
     * Handles the change in visibility for a specific chart.
     * @param {object} cb_obj - The Bokeh callback object from the checkbox.
     * @param {string} chartName - The name of the chart to toggle (e.g., 'figure_SW_timeseries').
     */
    function handleVisibilityChange(cb_obj, chartName) {
        try {
            //console.log(`[DEBUG] handleVisibilityChange: Called for ${chartName} with:`, cb_obj);
            if (!chartName) {
                console.warn('[Controller:handleVisibilityChange]', 'No chartName provided.');
                return;
            }

            const isVisible = Array.isArray(cb_obj.active) ? cb_obj.active.includes(0) : Boolean(cb_obj.active);


            // --- Update State ---
            if (_state.chartVisibility.hasOwnProperty(chartName)) {
                _state.chartVisibility[chartName] = isVisible;
            } else {
                console.warn(`[Controller:handleVisibilityChange] Chart name ${chartName} not found in _state.chartVisibility, adding it.`);
                _state.chartVisibility[chartName] = isVisible;
            }

            // --- Call Renderer ---
            renderSingleChartVisibility(chartName);


        } catch (error) {
            console.error("Error in handleVisibilityChange for " + chartName + ":", error);
        }
    }

    //===============================================================================================
    //           STATE MANAGEMENT
    //===============================================================================================

    /**
 * Updates active data for all positions based on view type and parameter
 * Orchestrates both line chart and spectral data updates
 * @param {string} viewType - The view type ('log' or 'overview')
 * @param {string} parameter - The parameter to display
 */
    function _updateActiveData(viewType = _state.viewType, parameter = _state.selectedParameter) {
        try {
            //console.log("[DEBUG] _updateActiveData: Function called");

            _state.availablePositions.forEach(position => {
                if (!_state.availablePositions.includes(position)) {
                    console.warn('[_updateActiveData]', `Position ${position} not found in available positions.`);
                    return;
                }

                // 1. Update Active Line Chart Data
                _updateActiveLineChartData(position, viewType);

                // 2. Update Active Spectral Data
                _updateActiveSpectralData(position, viewType, parameter);
            });

            // 3. Update (global) Active Frequency Bar Data. Use hoverContext if active, else use tapLine context, else no data
            let timestamp = null;
            let setBy = null;
            let position = null;
            if (_state.hoverContext.isActive) {
                timestamp = _state.hoverContext.timestamp;
                setBy = 'hover';
                position = _state.hoverContext.position;
            } else if (_state.tapContext.isActive) {
                timestamp = _state.tapContext.timestamp;
                setBy = 'tap';
                position = _state.tapContext.position;
            }

            _updateActiveFreqBarData(position, timestamp, setBy);

        } catch (error) {
            console.error("Error in _updateActiveData:", error);
        }
    }

    /**
     * Updates active line chart data for a specific position
     * @param {string} position - The position identifier
     * @param {string} viewType - The view type ('log' or 'overview')
     * @private
     */
    function _updateActiveLineChartData(position, viewType) {
        try {
            if (!_state.availablePositions.includes(position)) {
                console.warn('[_updateActiveLineChartData]', `Position ${position} not found in available positions.`);
                return;
            }

            const sourceData = _models.timeSeriesSources[position];
            const fallbackViewType = viewType === 'overview' ? 'log' : 'overview';
            const requestedSource = sourceData ? sourceData[viewType] : null;
            const fallbackSource = sourceData ? sourceData[fallbackViewType] : null;

            if (requestedSource?.data?.Datetime?.length > 0) {
                _state.activeLineChartData[position] = requestedSource.data;
                _state.displayedDataTypes[position].line = viewType;
            } else if (fallbackSource?.data?.Datetime?.length > 0) {
                _state.activeLineChartData[position] = fallbackSource.data;
                _state.displayedDataTypes[position].line = fallbackViewType; // Track that we're showing the fallback
            } else {
                _state.activeLineChartData[position] = { Datetime: [], LAeq: [], LAFmax: [], LAF10: [], LAF90: [] }; // Empty default
                _state.displayedDataTypes[position].line = 'None'; // Track that we're showing the fallback
                console.warn('[_updateActiveLineChartData]', `No line chart data found for ${position}.`);
            }
        } catch (error) {
            console.error("Error in _updateActiveLineChartData:", error);
        }
    }

    /**
     * Updates active spectral data for a specific position
     * @param {string} position - The position identifier
     * @param {string} viewType - The view type ('log' or 'overview')
     * @param {string} parameter - The parameter to display
     * @private
     */
    function _updateActiveSpectralData(position, viewType, parameter) {
        try {
            const positionGlyphData = _models.preparedGlyphData[position];
            const fallbackViewType = viewType === 'overview' ? 'log' : 'overview';

            if (positionGlyphData?.[viewType]?.prepared_params?.[parameter]?.levels_matrix?.length > 0) {

                // Set the active spectral data
                _state.activeSpectralData[position] = positionGlyphData[viewType].prepared_params[parameter];

                // Transpose the matrix for the spectrogram using utility function
                _state.activeSpectralData[position].levels_matrix_transposed =
                    MatrixUtils.transpose(_state.activeSpectralData[position].levels_matrix);

                _state.displayedDataTypes[position].spec = viewType;

            } else if (positionGlyphData?.[fallbackViewType]?.prepared_params?.[parameter]?.levels_matrix?.length > 0) {
                _state.activeSpectralData[position] = positionGlyphData[fallbackViewType].prepared_params[parameter];
                // Transpose the matrix for the spectrogram using utility function
                _state.activeSpectralData[position].levels_matrix_transposed =
                    MatrixUtils.transpose(_state.activeSpectralData[position].levels_matrix);

                _state.displayedDataTypes[position].spec = fallbackViewType;
                console.warn('[_updateActiveSpectralData]', `Data for view '${viewType}' not found for ${position}. Using fallback '${fallbackViewType}'.`);
            } else {
                _state.activeSpectralData[position] = {
                    levels_matrix_transposed: null, // Explicitly null
                    x_coord: 0, y_coord: 0, dw_val: 1, dh_val: 1, // Minimal valid dimensions
                    min_val: 0, max_val: 1, // Default color range
                    frequency_labels: [], n_freqs: 0,
                    times_ms: [], n_times: 0, freq_indices: []
                };
                _state.displayedDataTypes[position].spec = 'None'; // Track that we're showing the fallback
                console.warn('[_updateActiveSpectralData]', `Prepared spectral data for ${position}/${viewType}/${parameter} not found. Using placeholder.`);
            }
        } catch (error) {
            console.error("Error in _updateActiveSpectralData:", error);
        }
    }

    function _updateActiveFreqBarData(position, timestamp, setBy) {
        try {

            //helper to create blank data
            const blankData = { levels: [], frequency_labels: [], sourceposition: '', timestamp: null, setBy: null, param: null };

            if (!timestamp) {
                _state.activeFreqBarData = blankData;
                return;
            }

            if (!position || !_state.availablePositions.includes(position)) {
                console.warn('[Manager:_updateActiveFreqBarData]', `Invalid or no position provided: ${position}. Using blank data.`);
                _state.activeFreqBarData = blankData;
                return;
            }

            const activeSpectralData = _state.activeSpectralData[position];
            if (!activeSpectralData || !activeSpectralData.times_ms || !Array.isArray(activeSpectralData.times_ms) || !activeSpectralData.levels_matrix) {
                console.warn('[Manager:_updateActiveFreqBarData]', `No or incomplete active spectral data for position ${position}.`);
                _state.activeFreqBarData = blankData;
                return;
            }

            const closestTimeIdx = activeSpectralData.times_ms.findLastIndex(time => time <= timestamp); //find the index of the 1st time <= timestamp
            if (closestTimeIdx === -1) {
                console.warn('[Manager:_updateActiveFreqBarData]', `No closest time index for ${timestamp}.`);
                _state.activeFreqBarData = blankData;
                return;
            }

            const freqDataSlice = activeSpectralData.levels_matrix[closestTimeIdx];
            if (!freqDataSlice || freqDataSlice.length !== activeSpectralData.n_freqs) {
                console.warn('[Manager:_updateActiveFreqBarData]', `Frequency data slice invalid or wrong length for ${position} at index ${closestTimeIdx}.`);
                _state.activeFreqBarData = blankData;
                return;
            }

            let sourcetype = '';
            if (setBy === 'tap' && _state.tapContext.sourceChartName) {
                sourcetype = _state.tapContext.sourceChartName.includes('spectrogram') ? 'spectrogram' : 'timeseries';
            } else if (setBy === 'hover' && _state.hoverContext.sourceChartName) {
                sourcetype = _state.hoverContext.sourceChartName.includes('spectrogram') ? 'spectrogram' : 'timeseries';
            } else {
                sourcetype = '';
            }

            const cleanedLevels = freqDataSlice.map(level => (level === null || level === undefined || Number.isNaN(level)) ? 0 : level);

            const dataViewTypeForSpec = _state.displayedDataTypes[position]?.spec || 'None';

            _state.activeFreqBarData = {
                levels: cleanedLevels,
                frequency_labels: activeSpectralData.frequency_labels,
                sourceposition: position,
                sourceType: sourcetype,
                timestamp: timestamp,
                setBy: setBy,
                param: _state.selectedParameter,
                dataViewType: dataViewTypeForSpec //data view actually used on chart (rather than global request)
            };

        } catch (error) {
            console.error("Error in _updateActiveFreqBarData:", error);
            _state.activeFreqBarData = { levels: [], frequency_labels: [], sourceposition: '', timestamp: null, setBy: null, param: null, dataViewType: 'None' };
        }

    }


    //===============================================================================================
    //           RENDERERS
    //===============================================================================================

    function renderLineCharts() {
        try {
            //console.log("[DEBUG] renderLineCharts: Function called");
            _state.availablePositions.forEach(position => {
                const chartSource = _models.chartsSources.find(s => s.name === `source_${position}_timeseries`);
                const chartModel = _models.charts.find(c => c.name === `figure_${position}_timeseries`);
                const activeData = _state.activeLineChartData[position];

                if (!chartSource || !activeData) {
                    console.warn('[Render:renderLineChart]', `No chart model or active data for ${position}.`);
                    return;
                }

                chartSource.data = activeData;

                const requestedViewType = _state.viewType;
                const displayedViewType = _state.displayedDataTypes[position];
                const newTitleType = displayedViewType === 'log' ? "Log Data" : "Overview Data";
                let titletext = `Time History ${position} (${newTitleType})`;
                if (requestedViewType !== displayedViewType) {
                    titletext = `${titletext} (${requestedViewType} data not available)`;
                }
                chartModel.title.text = titletext;

                // Recalculate step size for keyboard navigation based on the new active data 
                //TODO: this shouldnt be here???. Renderers are meant to be dumb. step size will be based on the position with focus
                if (_state.activeFreqBarData.sourceposition === position) {
                    _state.stepSize = calculateStepSize(activeData);
                    console.log('[Render:renderLineChart]', `Step size recalculated to ${_state.stepSize}ms for ${position}`);
                }

                chartSource.change.emit();

            });
        } catch (error) {
            console.error("Error in renderLineCharts:", error);
        }
    }

    /**
     * Renders spectrograms for all available positions
     * Called by controllers after state updates
     */
    function renderSpectrograms() {
        try {
            _state.availablePositions.forEach(position => {
                const chartModel = _models.charts.find(c => c.name === `figure_${position}_spectrogram`);
                const activeData = _state.activeSpectralData[position];

                if (!chartModel) {
                    console.warn('[Render:renderSpectrogram] No spectrogram model found for:', position);
                    return;
                }

                const requestedViewType = _state.viewType;
                const displayedSpecViewType = _state.displayedDataTypes[position]?.spec || 'None'; // Safe access
                const currentParameter = _state.selectedParameter;

                let titleText = `Spectrogram ${position} | ${currentParameter}`;

                if (displayedSpecViewType !== 'None') {
                    const viewTypeLabel = displayedSpecViewType === 'log' ? "Log Data" : "Overview Data";
                    titleText += ` (${viewTypeLabel})`;
                    if (requestedViewType !== displayedSpecViewType) {
                        titleText += ` (${requestedViewType} data not available)`;
                    }
                } else {
                    titleText += ` (No data available)`;
                }
                chartModel.title.text = titleText;

                const imageRenderer = chartModel.renderers.find(r => r.glyph?.type === "Image");
                if (!imageRenderer) {
                    console.warn('[Render:renderSpectrogram] No Image renderer found for spectrogram:', position);
                }

                if (activeData?.levels_matrix_transposed) {
                    _renderSingleSpectrogram(imageRenderer, activeData, chartModel, position);
                    chartModel.visible = true; // Ensure visible if data is rendered
                } else {
                    //chartModel.visible = false;
                    if (imageRenderer?.data_source?.data?.image?.[0]) {
                        imageRenderer.data_source.data.image[0] = new Float32Array();
                        imageRenderer.data_source.change.emit();
                    }
                }
            });

        } catch (error) {
            console.error("Error in renderSpectrograms:", error);
            console.error("Stack trace:", error.stack);
        }
    }

    /**
     * Renders a single spectrogram with new data
     * @param {Object} imageRenderer - The Bokeh image renderer
     * @param {Object} activeData - The active spectral data
     * @param {Object} chartModel - The chart model (used for visibility and potentially other properties)
     * @param {string} position - The position identifier
     * @private
     */
    function _renderSingleSpectrogram(imageRenderer, activeData, chartModel, position) {
        try {
            if (!imageRenderer) {
                console.warn(`[Render:_renderSingleSpectrogram] imageRenderer not provided for ${position}. Cannot render.`);
                if (chartModel) chartModel.visible = false; // Hide chart if no renderer
                return;
            }

            const source = imageRenderer.data_source;
            const glyph = imageRenderer.glyph;
            const colorMapper = imageRenderer.color_mapper;

            if (!activeData ||
                activeData.levels_matrix_transposed === null ||
                !Array.isArray(activeData.levels_matrix_transposed) ||
                typeof activeData.x_coord === 'undefined' ||
                typeof activeData.dw_val === 'undefined' || activeData.dw_val <= 0 ||
                typeof activeData.dh_val === 'undefined' || activeData.dh_val <= 0) {

                if (source?.data?.image?.[0]?.length > 0) { // Check if image exists and has data
                    source.data.image[0] = new Float32Array(); // Clear to empty typed array
                    source.change.emit();
                }
                console.warn(`[Render:_renderSingleSpectrogram] Insufficient/invalid data for spectrogram ${position}. Clearing image.`);
                return;
            }

            glyph.x = activeData.x_coord;
            glyph.y = activeData.y_coord;
            glyph.dw = activeData.dw_val;
            glyph.dh = activeData.dh_val;

            if (colorMapper) {
                colorMapper.low = activeData.min_val;
                colorMapper.high = activeData.max_val;
            }

            //if (!source.data.image || !source.data.image[0] || !(source.data.image[0] instanceof Float32Array)) {
            //    const flattenedData = activeData.levels_matrix_transposed.flat();
            //    source.data.image = [new Float32Array(flattenedData.length)];
            //}
            MatrixUtils.updateBokehImageData(source.data.image[0], activeData.levels_matrix_transposed);

            source.change.emit();
        } catch (error) {
            console.error("Error in _renderSingleSpectrogram:", error);
        }
    }

    /**
     * Renders the Frequency Bar Chart and Data Table based on _state.freqBarFocus and the given timestamp.
     */
    function renderFrequencyBar() {
        try {
            //console.log('[Render:renderFrequencyBar]', `Rendering frequency bar`);

            _models.barSource.data = { 'levels': _state.activeFreqBarData.levels, 'frequency_labels': _state.activeFreqBarData.frequency_labels };
            // _models.barXRange.factors = _state.freqBarFocus.labels;

            _models.barChart.title.text =
                `Frequency Slice: ${_state.activeFreqBarData.sourceposition} (${_state.activeFreqBarData.dataViewType})` +
                ` | ${_state.selectedParameter}  | ${new Date(_state.activeFreqBarData.timestamp).toLocaleString()}` +
                ` | ${_state.activeFreqBarData.setBy}`;

            _models.barSource.change.emit();
            //_updateFrequencyTable(_state.freqBarFocus.levels, _state.freqBarFocus.labels); 

        } catch (error) {
            console.error("Error in renderFrequencyBar:", error);
        }
    }


    function renderTapLines(timestamp = _state.verticalLinePosition) {
        try {
            //console.log("[DEBUG] renderTapLines: Function called");
            //console.log('[Renderer:renderTapLines]', `Updating tap lines at x=${timestamp}`);

            if (!_models.clickLines) { console.error('[Renderer:renderTapLines]', 'Click lines not found.'); return; }

            timestamp = timestamp || _state.verticalLinePosition; //if no timestamp is provided, get from state
            if (timestamp === null || timestamp === undefined || timestamp === -1) {
                console.log('[Renderer:renderTapLines]', 'No timestamp provided or invalid timestamp.');
                _models.clickLines.forEach(line => { if (line) line.visible = false; });
                return;
            }

            _models.clickLines.forEach(line => {
                if (line) {
                    console.log('[Renderer:renderTapLines]', `Updating tap line for ${line.name}`);
                    line.location = timestamp;
                    line.visible = true;
                }
            });
        } catch (error) {
            console.error("Error in renderTapLines:", error);
        }
    }

    function renderLabels() {
        //render labels for all charts. if hover is active, we use the hover timestamp for the active chart only. 
        // if tap is active, we use the tap timestamp for all charts. 
        // if playback is active, we use the playback timestamp for all charts.
        // if none are active, we dont show labels.

        try {
            //console.log("[DEBUG] renderLabels: Function called");
            //console.log('[Renderer:renderLabels]', `Updating labels at x=${timestamp}`);

            if (!_models.labels) { console.error('[Renderer:renderLabels]', 'Labels not found.'); return; }

            _models.labels.forEach(label => {

                let labelActive = false;
                let timestamp = null;

                const labelMatchesHoverSourceChart = _state.hoverContext.sourceChartName ?
                    label.name.replace('label_', '') === _state.hoverContext.sourceChartName.replace('figure_', '') :
                    false;

                if (_state.hoverContext.isActive && labelMatchesHoverSourceChart) {
                    timestamp = _state.hoverContext.timestamp;
                    labelActive = true;
                } else if (_state.tapContext.isActive) {
                    timestamp = _state.tapContext.timestamp;
                    labelActive = true;
                } else {
                    labelActive = false;
                }

                if (labelActive) {
                    label.text = _createLabelTextFromActiveChartData(label, timestamp);
                    _positionLabel(label, timestamp);
                    label.visible = true;
                } else {
                    label.visible = false;
                }
            });
        } catch (error) {
            console.error("Error in renderLabels:", error);
        }
    }

    function renderHoverLines() {
        try {
            //console.log("[DEBUG] renderHoverLine: Function called");

            const timestamp = _state.hoverContext.timestamp;
            if (!timestamp) {
                console.log('[Render:renderHoverLine]', 'No valid timestamp.');
                _state.hoverContext.isActive = false;
            }

            // Update all grey hover lines
            if (_state.hoverContext.isActive) {
                _models.hoverLines.forEach(line => {
                    if (line) {
                        line.location = timestamp;
                        line.visible = true;
                    }
                });
            } else {
                _models.hoverLines.forEach(line => { if (line) line.visible = false; });
            }

        } catch (error) {
            console.error("Error in renderHoverLine:", error);
        }
    }

    function renderSpectrogramHoverDiv() {
        try {
            //console.log("[DEBUG] renderSpectrogramHoverDiv: Function called");

            //get the hover div for the active position
            if (!_state.hoverContext.position) { console.error('[Renderer:renderSpectrogramHoverDiv]', 'No hover div found.'); return; }
            const hover_div = _models.hoverDivs.find(div => div.name === `${_state.hoverContext.position}_spectrogram_hover_div`);

            //only update if hover context is active and frequency data set up associated hover
            if (!_state.hoverContext.isActive ||
                _state.activeFreqBarData.setBy !== 'hover' ||
                _state.activeFreqBarData.sourceposition !== _state.hoverContext.position ||
                _state.activeFreqBarData.sourceType !== 'spectrogram') {
                hover_div.text = "Hover over spectrogram to view details";
                return;
            }

            const freqLevels = _state.activeFreqBarData.levels;
            const freqLabels = _state.activeFreqBarData.frequency_labels;
            if (!freqLevels || !freqLabels) {
                hover_div.text = "Hover over spectrogram (data not loaded)";
                return;
            }

            const n_freqs = freqLevels.length;
            const spec_y = _state.hoverContext.spec_y;
            const freq_idx = Math.max(0, Math.min(n_freqs - 1, Math.floor(spec_y + 0.5)));
            const level_val_hover = freqLevels[freq_idx];
            const freq_str = freqLabels[freq_idx];
            const time_str = new Date(_state.activeFreqBarData.timestamp).toLocaleString();

            let level_str_hover = (level_val_hover == null || isNaN(level_val_hover)) ? "N/A" : level_val_hover.toFixed(1) + " dB";
            hover_div.text = `<b>Time:</b> ${time_str} | <b>Freq:</b> ${freq_str} | <b>Level:</b> ${level_str_hover} (${_state.activeFreqBarData.param})`;


            hover_div.visible = true;
        } catch (error) {
            console.error("Error in renderSpectrogramHoverDiv:", error);
        }
    }


    function renderAllVisuals() {
        try {
            console.log("[DEBUG] renderAllVisuals: Function called");
            renderLineCharts();
            renderSpectrograms();
            renderTapLines();
            renderLabels();
            // This causes infinite loop if renderFrequencyBar() calls _updateFrequencyTable() which then causes an issue.
            // It's likely intended to be called with a specific timestamp or state that prevents loop.
            // For now, removing this direct call here.
            // renderFrequencyBar();
        } catch (error) {
            console.error("Error in renderAllVisuals:", error);
        }
    }

    /**
     * Updates the visibility of a single chart based on the _state.
     * @param {string} chartName - The name of the chart to update.
     */
    function renderSingleChartVisibility(chartName) {
        try {
            const chartModel = _getChartModel(chartName);
            const isVisible = _state.chartVisibility[chartName];

            if (chartModel) {
                if (typeof isVisible === 'boolean') {
                    if (chartModel.visible !== isVisible) {
                        chartModel.visible = isVisible;
                        console.log(`[Render:renderSingleChartVisibility] Set ${chartName} visibility to ${isVisible}`);
                    }
                } else {
                    console.warn(`[Render:renderSingleChartVisibility] Visibility state for ${chartName} is not a boolean:`, isVisible);
                }
            } else {
                console.warn(`[Render:renderSingleChartVisibility] Chart model not found for ${chartName}.`);
            }
        } catch (error) {
            console.error(`Error in renderSingleChartVisibility for ${chartName}:`, error);
        }
    }

    /**
     * Renders the visibility for all charts.
     * Called on initialization or if a full visibility refresh is needed.
     */
    function renderChartVisibility() {
        try {
            console.log("[DEBUG] renderChartVisibility: Function called");
            for (const chartName in _state.chartVisibility) {
                if (_state.chartVisibility.hasOwnProperty(chartName)) {
                    renderSingleChartVisibility(chartName);
                }
            }
        } catch (error) {
            console.error("Error in renderChartVisibility:", error);
        }
    }

    //===============================================================================================
    //           PUBLIC API
    //===============================================================================================

    function initializeApp(models, options) {
        try {
            console.log("[DEBUG] initializeApp: Function called");
            console.info('[NoiseSurveyApp]', 'Initializing...');

            _models = models; // Store all Bokeh models passed from Python

            // Populate _state.availablePositions
            const positions = new Set();
            _models.charts.forEach(chartObject => {
                const pos = _getChartPositionByName(chartObject.name);
                if (pos) positions.add(pos);
                _state.chartVisibility[chartObject.name] = true;
            });
            _state.availablePositions = Array.from(positions);
            if (_state.availablePositions.length === 0) {
                console.error('[NoiseSurveyApp] No positions found. Cannot initialize properly.');
                return false;
            }

            _state.selectedParameter = _models.paramSelect?.value || _models.selectedParamHolder?.text || 'LZeq';

            // Store UI elements that need direct access
            _state.availablePositions.forEach(pos => {
                if (!_models.uiPositionElements[pos]) _models.uiPositionElements[pos] = {};
                _state.displayedDataTypes[pos] = {};
            });
            _state.viewType = 'overview'; // Default to overview
            _state.verticalLinePosition = -1;
            _state.activeFreqBarData.timestamp = -1;

            //initialize visibility checkboxes
            if (_models.charts && _models.visibilityCheckBoxes) {
                _models.charts.forEach(chart => {
                    if (chart && chart.name) {
                        const checkboxWidget = _models.visibilityCheckBoxes.find(
                            cb => cb.name === `${chart.name.replace("figure_", "checkbox_")}`
                        );
                        if (checkboxWidget) {
                            _state.chartVisibility[chart.name] = checkboxWidget.active;
                        } else {
                            console.warn(`[Init] No visibility checkbox found for chart: ${chart.name}. Defaulting to true.`);
                            _state.chartVisibility[chart.name] = true; // Default if no checkbox found
                        }
                    }
                });
            } else {
                // Fallback: if no checkboxes passed, assume all charts are initially visible
                _models.charts.forEach(chart => {
                    if (chart && chart.name) _state.chartVisibility[chart.name] = true;
                });
            }

            //initialize data and render charts
            _updateActiveData(_state.viewType, _state.selectedParameter);
            renderAllVisuals();
            return true; // Indicate successful initialization
        } catch (error) {
            console.error("Error in initializeApp:", error);
            return false; // Indicate failed initialization
        }
    }
    return {
        init: initializeApp,
        // State Access (for debugging or specific needs)
        getState: function () {
            try {
                console.log("[DEBUG] getState: Function called");
                return JSON.parse(JSON.stringify(_state));
            } catch (error) {
                console.error("Error in getState:", error);
                return {};
            }
        },
        // Direct event handlers that are called from Bokeh CustomJS
        // These are now thin wrappers that call the new controller functions.
        interactions: {
            onTap: function (cb_obj) {
                try {
                    //console.log("[DEBUG] interactions.onTap: Function called");
                    handleTap(cb_obj);
                } catch (error) {
                    console.error("Error in interactions.onTap:", error);
                }
            },
            onHover: function (cb_data, chartName) {
                try {
                    //console.log("[DEBUG] interactions.onHover: Function called");
                    debouncedHandleChartHover(cb_data, chartName);
                    //handleChartHover(cb_data, chartName);
                } catch (error) {
                    console.error("Error in interactions.onHover:", error);
                }
            },
            onSpectrogramHover: function (cb_data, position_name) {
                try {
                    //console.log("[DEBUG] interactions.onSpectrogramHover: Function called");
                    handleSpectrogramHover(cb_data, position_name);
                } catch (error) {
                    console.error("Error in interactions.onSpectrogramHover:", error);
                }
            },
            onZoom: function (cb_obj) {
                try {
                    //console.log("[DEBUG] interactions.onZoom: Function called");
                    /* Optional: handle zoom if needed */
                } catch (error) {
                    console.error("Error in interactions.onZoom:", error);
                }
            },
            onVisibilityChange: function (cb_obj, chartName) {
                try {
                    //console.log("[DEBUG] interactions.onVisibilityChange: Function called");
                    handleVisibilityChange(cb_obj, chartName);
                } catch (error) {
                    console.error("Error in interactions.onVisibilityChange:", error);
                }
            }
        },
        handleParameterChange: function (value, select_widget) {
            try {
                console.log("[DEBUG] handleParameterChange: Function called");
                handleParameterChange(value, select_widget);
            } catch (error) {
                console.error("Error in handleParameterChange:", error);
            }
        },
        handleViewToggle: function (active, toggle_widget) {
            try {
                console.log("[DEBUG] handleViewToggle: Function called");
                handleViewToggle(active, toggle_widget);
            } catch (error) {
                console.error("Error in handleViewToggle:", error);
            }
        },
    }
})();


console.log("[DEBUG] app.js loaded and NoiseSurveyApp object created.");