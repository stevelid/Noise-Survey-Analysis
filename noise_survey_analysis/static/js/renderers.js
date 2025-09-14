// noise_survey_analysis/static/js/renderers.js

/**
 * @fileoverview Contains all rendering functions that update the UI of the Noise Survey app.
 * These functions take the fully processed application state as input and are responsible
 * for updating the properties of the Bokeh models (e.g., chart data sources, line visibility,
 * label text). They are "presentational" and should contain minimal logic, focusing
 * only on translating the state into visuals.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function(app) {
    'use strict';

    let models = app.models;
    let controllers = app.controllers;
    let SpectrogramChart = app.classes.SpectrogramChart;

/**
     * Updates the primary data sources of the main charts.
     * This is a HEAVY operation and should only be called when the underlying
     * data view (zoom level, parameter, log/overview) changes.
     */
function renderPrimaryCharts(state) {
    for (const posId in controllers.positions) {        
        const controller = controllers.positions[posId];
        const tsChartName = `figure_${posId}_timeseries`;
        const specChartName = `figure_${posId}_spectrogram`;

        // Explicitly set visibility for each chart based on the state
        if (controller.timeSeriesChart) {
            controller.timeSeriesChart.setVisible(state.view.chartVisibility[tsChartName]);
        }
        if (controller.spectrogramChart) {
            const isSpecVisible = state.view.chartVisibility[specChartName];
            controller.spectrogramChart.setVisible(isSpecVisible);
            if (controller.spectrogramChart.hoverDivModel) {
                controller.spectrogramChart.hoverDivModel.visible = isSpecVisible;
            }
        }
        // Update the data for the controller if any of its charts are visible
        controller.updateAllCharts(state);
    }
}

    /**
     * Updates lightweight UI overlays like lines and labels.
     * This is a LIGHT operation and can be called frequently.
     */
    function renderOverlays() {
        renderTapLines();
        renderLabels();
        renderHoverEffects();
        renderSummaryTable();
    }

    function renderAllVisuals(state) {
        // This function is now deprecated. All rendering should go through _dispatchAction.
        // It's kept for backward compatibility during refactoring, but will be removed.
        console.warn("[DEBUG] renderAllVisuals() called. This function is deprecated. Use _dispatchAction instead.");
        renderPrimaryCharts(state);
        renderOverlays();
        renderFrequencyBar();
    }

    function renderHoverEffects() {
        const _state = app.state.getState();
        const hoverState = _state.interaction.hover;

        // Update data for the bar chart based on hover
        app.data_processors.updateActiveFreqBarData(hoverState.position, hoverState.timestamp, 'hover'); //TODO: ??this is impure. Should be moved outside this function. 
        renderFrequencyBar();

        // Only render hover effects if hover is enabled
        if (_state.view.hoverEnabled) {
            controllers.chartsByName.forEach(chart => {
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
            controllers.chartsByName.forEach(chart => {
                chart.hideHoverLine();
            });
        }

        // After updating hover effects, re-render the labels with the new context
        renderLabels();
    }

    function renderTapLines() {
        const _state = app.state.getState();
        const { isActive, timestamp } = _state.interaction.tap;
        models.clickLines.forEach(line => {
            if (line) {
                line.location = timestamp;
                line.visible = isActive;
            }
        });
    }

    function renderLabels() {
        const _state = app.state.getState();
        const hoverState = _state.interaction.hover;
        const tapState = _state.interaction.tap;

        // If no interaction is active, hide all labels and exit.
        if (!hoverState.isActive && !tapState.isActive) {
            controllers.chartsByName.forEach(chart => chart.hideLabel());
            return;
        }

        controllers.chartsByName.forEach(chart => {
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

    /**
    * Iterates through all charts and tells them to synchronize their
    * marker visuals with the central state.
    */
    function renderMarkers() {
        const _state = app.state.getState();
        controllers.chartsByName.forEach(chart => {
            chart.syncMarkers(_state.markers.timestamps, _state.markers.enabled);
        });
    }

    function renderFrequencyTable() {
        const _state = app.state.getState();
        const tableDiv = models.freqTableDiv;

        if (!tableDiv) {
            console.error("Frequency table div model not found.");
            return;
        }

        // Get tap context for independent table data processing
        const { isActive, timestamp, position } = _state.interaction.tap;
        
        if (!isActive || !timestamp || !position) {
            tableDiv.text = "<p>Tap on a time series chart to populate this table.</p>";
            return;
        }

        // Get the full spectral data for the tapped position and timestamp
        const activeSpectralData = _state.data.activeSpectralData[position];
        if (!activeSpectralData?.times_ms?.length || !activeSpectralData.frequencies_hz) {
            tableDiv.text = "<p>No frequency data available for selected position.</p>";
            return;
        }

        const closestTimeIdx = activeSpectralData.times_ms.findLastIndex(time => time <= timestamp);
        if (closestTimeIdx === -1) {
            tableDiv.text = "<p>No data available at selected time.</p>";
            return;
        }

        // Apply independent frequency slicing for table's specific range
        const tableFreqRange = models?.config?.freq_table_freq_range_hz;
        let labels, levels;
        
        if (tableFreqRange && activeSpectralData.frequencies_hz) {
            const [tableMinHz, tableMaxHz] = tableFreqRange;
            const table_start_idx = activeSpectralData.frequencies_hz.findIndex(f => f >= tableMinHz);
            const table_end_idx = activeSpectralData.frequencies_hz.findLastIndex(f => f <= tableMaxHz);
            
            if (table_start_idx !== -1 && table_end_idx !== -1) {
                // Extract data for the table's frequency range
                const tableFreqCount = (table_end_idx - table_start_idx) + 1;
                labels = activeSpectralData.frequency_labels.slice(table_start_idx, table_end_idx + 1);
                
                const tableLevelsSlice = new Float32Array(tableFreqCount);
                for (let i = 0; i < tableFreqCount; i++) {
                    const globalFreqIdx = table_start_idx + i;
                    tableLevelsSlice[i] = activeSpectralData.levels_flat_transposed[globalFreqIdx * activeSpectralData.n_times + closestTimeIdx];
                }
                levels = Array.from(tableLevelsSlice);
            } else {
                // Fallback if no frequencies found in table range
                labels = activeSpectralData.frequency_labels;
                const freqDataSlice = new Float32Array(activeSpectralData.n_freqs);
                for (let i = 0; i < activeSpectralData.n_freqs; i++) {
                    freqDataSlice[i] = activeSpectralData.levels_flat_transposed[i * activeSpectralData.n_times + closestTimeIdx];
                }
                levels = Array.from(freqDataSlice);
            }
        } else {
            // Fallback if config is missing - use full range
            labels = activeSpectralData.frequency_labels;
            const freqDataSlice = new Float32Array(activeSpectralData.n_freqs);
            for (let i = 0; i < activeSpectralData.n_freqs; i++) {
                freqDataSlice[i] = activeSpectralData.levels_flat_transposed[i * activeSpectralData.n_times + closestTimeIdx];
            }
            levels = Array.from(freqDataSlice);
        }

        if (!labels || labels.length === 0) {
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

        // Display the levels data
        levels.forEach(level => {
            const levelNum = (level === null || isNaN(level)) ? NaN : parseFloat(level);
            const levelText = isNaN(levelNum) ? 'N/A' : levelNum.toFixed(1);
            tableHtml += `<td>${levelText}</td>`;
        });

        tableHtml += `</tr></table>`;
        tableDiv.text = tableHtml;
    }

    function renderFrequencyBar() {
        const _state = app.state.getState();

        const freqData = _state.data.activeFreqBarData;
        models.barSource.data = {
            'levels': freqData.levels,
            'frequency_labels': freqData.frequency_labels
        };
        models.barChart.x_range.factors = freqData.frequency_labels;
        models.barChart.title.text = `Slice: ${freqData.sourceposition} | ${freqData.param} @ ${new Date(freqData.timestamp).toLocaleTimeString()} | by ${freqData.setBy}`;
        models.barSource.change.emit();

        // Also update the HTML table
        renderFrequencyTable();
    }

    const PLAYING_BACKGROUND_COLOR = '#e6f0ff'; // A light blue to highlight the active chart
    const DEFAULT_BACKGROUND_COLOR = '#ffffff'; // Standard white background

    function renderAudioControls() {
        const _state = app.state.getState();
        const { isPlaying, activePositionId, playbackRate, volumeBoost } = _state.audio;

        _state.view.availablePositions.forEach(pos => {
            const controller = controllers.positions[pos];
            const controls = models.audio_controls[pos];
            const isThisPositionActive = isPlaying && activePositionId === pos;

            // --- Update Chart Visuals (Title and Background) ---
            if (controller && controller.timeSeriesChart) {
                const tsChart = controller.timeSeriesChart;
                // Base title comes from the state's displayDetails
                const baseTitle = `${pos} - Time History${_state.view.displayDetails[pos].line.reason}`;
                tsChart.model.title.text = isThisPositionActive ? `${baseTitle} (▶ PLAYING)` : baseTitle;
                tsChart.model.background_fill_color = isThisPositionActive ? PLAYING_BACKGROUND_COLOR : DEFAULT_BACKGROUND_COLOR;
            }
            if (controller && controller.spectrogramChart) {
                const specChart = controller.spectrogramChart;
                const baseTitle = `${pos} - ${_state.view.selectedParameter} Spectrogram${_state.view.displayDetails[pos].spec.reason}`;
                specChart.model.title.text = isThisPositionActive ? `${baseTitle} (▶ PLAYING)` : baseTitle;
                specChart.model.background_fill_color = isThisPositionActive ? PLAYING_BACKGROUND_COLOR : DEFAULT_BACKGROUND_COLOR;
            }

            // --- Update Control Widget Visuals ---
            if (controls) {                
                // Update Play/Pause button state, label, and color
                if (controls.playToggle.active !== isThisPositionActive) {
                    controls.playToggle.active = isThisPositionActive;
                }
                controls.playToggle.label = isThisPositionActive ? "Pause" : "Play";
                controls.playToggle.button_type = isThisPositionActive ? 'primary' : 'success'; // Blue when playing, green when ready

                // Update playback rate button label (always reflects current rate)
                controls.playbackRateButton.label = `${playbackRate.toFixed(1)}x`;

                // Update volume boost toggle and color
                const isBoostActiveForThisPos = isThisPositionActive && volumeBoost;
                controls.volumeBoostButton.active = isBoostActiveForThisPos;
                controls.volumeBoostButton.button_type = isBoostActiveForThisPos ? 'warning' : 'light'; // 'warning' (orange) when active, 'light' (grey) otherwise
            }
        });
    }

    function renderSummaryTable() {
        const _state = app.state.getState();
        const tableDiv = models.summaryTableDiv;
        if (!tableDiv) {
            console.error("Summary table div model not found.");
            return;
        }

        const { isActive, timestamp } = _state.interaction.tap;

        const initialDoc = new DOMParser().parseFromString(tableDiv.text, 'text/html');
        const headerCells = initialDoc.querySelectorAll("thead th:not(.position-header)");
        const parameters = Array.from(headerCells).map(th => th.textContent.trim());

        let tableBodyHtml = '';
        
        if (!isActive || !timestamp) {
            tableBodyHtml = `<tr><td class='placeholder' colspan='${parameters.length + 1}'>Tap on a time series chart to populate this table.</td></tr>`;
        } else {
            // Add timestamp info row
            const timestampStr = new Date(timestamp).toLocaleString();
            tableBodyHtml += `<tr><td class='timestamp-info' colspan='${parameters.length + 1}'>Values at: ${timestampStr}</td></tr>`;
            
            _state.view.availablePositions.forEach(pos => {
                let rowHtml = `<tr><td class="position-header">${pos}</td>`;
                const activeLineData = _state.data.activeLineData[pos];
                
                if (activeLineData && activeLineData.Datetime && activeLineData.Datetime.length > 0) {
                    const idx = app.utils.findAssociatedDateIndex(activeLineData, timestamp);

                    if (idx !== -1) {
                        parameters.forEach(param => {
                            const value = activeLineData[param]?.[idx];
                            const formattedValue = (value === null || value === undefined || isNaN(value))
                                ? 'N/A'
                                : parseFloat(value).toFixed(1);
                            rowHtml += `<td>${formattedValue}</td>`;
                        });
                    } else {
                         // Data exists for position, but not at this timestamp
                        parameters.forEach(() => rowHtml += `<td>N/A</td>`);
                    }
                } else {
                    // No data loaded for this position
                    parameters.forEach(() => rowHtml += `<td>No Data</td>`);
                }
                rowHtml += `</tr>`;
                tableBodyHtml += rowHtml;
            });
        }
        
        // Use regex to replace only the content of the <tbody> tag, preserving the header and style
        const newTableHtml = tableDiv.text.replace(/<tbody>[\s\S]*<\/tbody>/, `<tbody>${tableBodyHtml}</tbody>`);
        tableDiv.text = newTableHtml;
    }





    // Attach the public functions to the global object
    app.renderers = {
        renderPrimaryCharts: renderPrimaryCharts,
        renderOverlays: renderOverlays,
        renderAllVisuals: renderAllVisuals,
        renderHoverEffects: renderHoverEffects,
        renderTapLines: renderTapLines,
        renderLabels: renderLabels,
        renderMarkers: renderMarkers,
        renderFrequencyTable: renderFrequencyTable,
        renderFrequencyBar: renderFrequencyBar,
        renderAudioControls: renderAudioControls,
        renderSummaryTable: renderSummaryTable,
        //formatTime: formatTime
    };
})(window.NoiseSurveyApp);
