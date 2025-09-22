// noise_survey_analysis/static/js/services/renderers.js

/**
 * @fileoverview Contains all rendering functions that update the UI of the Noise Survey app.
 * These functions take the fully processed application state as input and are responsible
 * for updating the properties of the Bokeh models (e.g., chart data sources, line visibility,
 * label text). They are "presentational" and should contain minimal logic, focusing
 * only on translating the state into visuals.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    // Dependencies are accessed dynamically within each function (e.g., `app.registry.models`)
    // to ensure they are not stale, especially in test environments.
    function escapeHtml(value) {
        if (typeof value !== 'string') return '';
        return value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function formatDuration(ms) {
        if (!Number.isFinite(ms) || ms <= 0) return '0s';
        const totalSeconds = Math.floor(ms / 1000);
        const minutes = Math.floor(totalSeconds / 60);
        const seconds = totalSeconds % 60;
        const parts = [];
        if (minutes) parts.push(`${minutes}m`);
        parts.push(`${seconds}s`);
        return parts.join('');
    }

    function formatDateTime(timestamp) {
        if (!Number.isFinite(timestamp)) {
            return 'N/A';
        }
        const date = new Date(timestamp);
        return date.toLocaleString([], {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
    }

    const COMPARISON_METRICS_STYLE = `
        <style>
            .comparison-metrics-table { width: 100%; border-collapse: collapse; font-size: 12px; }
            .comparison-metrics-table th, .comparison-metrics-table td {
                border: 1px solid #ddd;
                padding: 4px 6px;
                text-align: center;
            }
            .comparison-metrics-table th {
                background-color: #f5f5f5;
                font-weight: 600;
            }
            .comparison-metrics-table__placeholder {
                font-style: italic;
                color: #666;
            }
        </style>
    `;

    const COMPARISON_METRICS_EMPTY_HTML = `${COMPARISON_METRICS_STYLE}
        <table class="comparison-metrics-table">
            <thead>
                <tr>
                    <th>Position</th>
                    <th>Duration</th>
                    <th>LAeq</th>
                    <th>LAFmax</th>
                    <th>LA90</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td class="comparison-metrics-table__placeholder" colspan="5">Select a time slice to populate metrics.</td>
                </tr>
            </tbody>
        </table>`;

    const COMPARISON_SPECTRUM_EMPTY_HTML = `
        <table class="comparison-frequency-table" style="width:100%; border-collapse: collapse; font-size:12px;">
            <thead>
                <tr>
                    <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Position</th>
                    <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Dataset</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td colspan="2" style="border:1px solid #ddd; padding:6px; text-align:center; font-style:italic; color:#666;">
                        Select a time slice to view averaged spectra.
                    </td>
                </tr>
            </tbody>
        </table>
    `;

    const DEFAULT_COMPARISON_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf'];

    function buildComparisonMetricsTable(rows) {
        if (!Array.isArray(rows) || !rows.length) {
            return COMPARISON_METRICS_EMPTY_HTML;
        }
        const bodyHtml = rows.map(row => {
            const positionCell = escapeHtml(String(row.positionId || '—'));
            const durationCell = formatDuration(row.durationMs);
            const laeqCell = Number.isFinite(row.laeq) ? row.laeq.toFixed(1) : 'N/A';
            const lafmaxCell = Number.isFinite(row.lafmax) ? row.lafmax.toFixed(1) : 'N/A';
            const la90Cell = row.la90Available && Number.isFinite(row.la90)
                ? row.la90.toFixed(1)
                : 'N/A';
            return `<tr><td>${positionCell}</td><td>${durationCell}</td><td>${laeqCell}</td><td>${lafmaxCell}</td><td>${la90Cell}</td></tr>`;
        }).join('');
        return `${COMPARISON_METRICS_STYLE}
            <table class="comparison-metrics-table">
                <thead>
                    <tr>
                        <th>Position</th>
                        <th>Duration</th>
                        <th>LAeq</th>
                        <th>LAFmax</th>
                        <th>LA90</th>
                    </tr>
                </thead>
                <tbody>${bodyHtml}</tbody>
            </table>`;
    }

    function buildComparisonSpectrumTable(series) {
        if (!Array.isArray(series) || !series.length) {
            return COMPARISON_SPECTRUM_EMPTY_HTML;
        }
        const rowsHtml = series.map(entry => {
            const positionCell = escapeHtml(String(entry?.positionId || '—'));
            const datasetLabel = entry?.dataset === 'log'
                ? 'Log'
                : entry?.dataset === 'overview'
                    ? 'Overview'
                    : 'No Data';
            return `<tr><td style="border:1px solid #ddd; padding:4px;">${positionCell}</td><td style="border:1px solid #ddd; padding:4px;">${datasetLabel}</td></tr>`;
        }).join('');
        return `
            <table class="comparison-frequency-table" style="width:100%; border-collapse: collapse; font-size:12px;">
                <thead>
                    <tr>
                        <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Position</th>
                        <th style="border:1px solid #ddd; padding:4px; background:#f5f5f5;">Dataset</th>
                    </tr>
                </thead>
                <tbody>${rowsHtml}</tbody>
            </table>
        `;
    }

    const COMPARISON_SLICE_COLOR = '#d32f2f';
    const COMPARISON_SLICE_FILL_ALPHA = 0.12;
    const COMPARISON_SLICE_LINE_ALPHA = 0.9;

    function ensureComparisonSliceSpans(chart) {
        if (!chart || !chart.model) return null;
        if (chart._comparisonSliceSpans) {
            return chart._comparisonSliceSpans;
        }
        const doc = window.Bokeh?.documents?.[0];
        if (!doc || typeof doc.create_model !== 'function' || typeof doc.add_model !== 'function') {
            return null;
        }
        try {
            const startSpan = doc.add_model(doc.create_model('Span', {
                location: 0,
                dimension: 'height',
                line_color: COMPARISON_SLICE_COLOR,
                line_width: 2,
                line_alpha: COMPARISON_SLICE_LINE_ALPHA,
                level: 'overlay',
                visible: false,
                name: `comparison_slice_start_${chart.name}`
            }));
            const endSpan = doc.add_model(doc.create_model('Span', {
                location: 0,
                dimension: 'height',
                line_color: COMPARISON_SLICE_COLOR,
                line_width: 2,
                line_alpha: COMPARISON_SLICE_LINE_ALPHA,
                level: 'overlay',
                visible: false,
                name: `comparison_slice_end_${chart.name}`
            }));
            chart.model.add_layout(startSpan);
            chart.model.add_layout(endSpan);
            chart._comparisonSliceSpans = { start: startSpan, end: endSpan };
            return chart._comparisonSliceSpans;
        } catch (error) {
            console.error('[Renderers] Failed to initialize comparison slice spans:', error);
            return null;
        }
    }

    function ensureComparisonSliceBox(chart) {
        if (!chart || !chart.model) return null;
        if (chart._comparisonSliceBox) {
            return chart._comparisonSliceBox;
        }
        const doc = window.Bokeh?.documents?.[0];
        if (!doc || typeof doc.create_model !== 'function' || typeof doc.add_model !== 'function') {
            return null;
        }
        try {
            const box = doc.add_model(doc.create_model('BoxAnnotation', {
                left: 0,
                right: 0,
                top: null,
                bottom: null,
                fill_alpha: COMPARISON_SLICE_FILL_ALPHA,
                fill_color: COMPARISON_SLICE_COLOR,
                line_color: COMPARISON_SLICE_COLOR,
                line_alpha: COMPARISON_SLICE_LINE_ALPHA,
                line_width: 2,
                level: 'overlay',
                visible: false,
                name: `comparison_slice_box_${chart.name}`
            }));
            chart.model.add_layout(box);
            chart._comparisonSliceBox = box;
            return box;
        } catch (error) {
            console.error('[Renderers] Failed to initialize comparison slice box:', error);
            return null;
        }
    }

    function setComparisonSliceVisibility(chart, isVisible, start, end) {
        const spans = ensureComparisonSliceSpans(chart);
        const box = ensureComparisonSliceBox(chart);
        if (!spans && !box) return;
        if (isVisible && Number.isFinite(start) && Number.isFinite(end)) {
            spans.start.location = start;
            spans.end.location = end;
            spans.start.visible = true;
            spans.end.visible = true;
            if (box) {
                box.left = start;
                box.right = end;
                box.visible = true;
            }
        } else {
            if (spans) {
                spans.start.visible = false;
                spans.end.visible = false;
            }
            if (box) {
                box.visible = false;
            }
        }
    }

    function updateComparisonSliceLines(controllersByPosition, isActive, start, end) {
        Object.keys(controllersByPosition || {}).forEach(positionId => {
            const controller = controllersByPosition[positionId];
            if (!controller) return;
            setComparisonSliceVisibility(controller.timeSeriesChart, isActive, start, end);
            setComparisonSliceVisibility(controller.spectrogramChart, isActive, start, end);
        });
    }

    function updateComparisonFrequencyVisualization(models, spectrum) {
        const source = models.comparisonFrequencySource;
        const figure = models.comparisonFrequencyFigure;
        const tableDiv = models.comparisonFrequencyTable;
        const labels = Array.isArray(spectrum?.labels) ? spectrum.labels : [];
        const series = Array.isArray(spectrum?.series) ? spectrum.series : [];
        const palette = Array.isArray(models.comparisonFrequencyPalette) && models.comparisonFrequencyPalette.length
            ? models.comparisonFrequencyPalette
            : DEFAULT_COMPARISON_COLORS;

        if (!source) {
            return;
        }

        if (!labels.length || !series.length) {
            source.data = { x: [], level: [], position: [], color: [] };
            if (figure?.x_range) {
                figure.x_range.factors = [];
            }
            if (tableDiv) {
                tableDiv.text = COMPARISON_SPECTRUM_EMPTY_HTML;
            }
            return;
        }

        const xValues = [];
        const levels = [];
        const positions = [];
        const colors = [];
        const factors = [];

        series.forEach((entry, index) => {
            const positionId = entry?.positionId || `Series ${index + 1}`;
            const color = palette[index % palette.length];
            const values = Array.isArray(entry?.values) ? entry.values : [];
            labels.forEach((label, labelIndex) => {
                const tuple = [String(label ?? `Band ${labelIndex + 1}`), positionId];
                factors.push(tuple);
                xValues.push(tuple);
                const numericValue = Number(values[labelIndex]);
                levels.push(Number.isFinite(numericValue) ? numericValue : null);
                positions.push(positionId);
                colors.push(color);
            });
        });

        source.data = {
            x: xValues,
            level: levels,
            position: positions,
            color: colors
        };
        if (figure?.x_range) {
            figure.x_range.factors = factors;
        }
        if (tableDiv) {
            tableDiv.text = buildComparisonSpectrumTable(series);
        }
    }

    /**
         * Updates the primary data sources of the main charts.
         * This is a HEAVY operation and should only be called when the underlying
         * data view (zoom level, parameter, log/overview) changes.
         */
    function renderPrimaryCharts(state, dataCache) {
        const { controllers } = app.registry;
        if (!controllers?.positions) return;

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
            controller.updateAllCharts(state, dataCache);
        }
    }

    /**
     * Updates lightweight UI overlays like lines and labels.
     * This is a LIGHT operation and can be called frequently.
     */
    function renderOverlays(state, dataCache) {
        renderTapLines(state);
        renderLabels(state);
        renderHoverEffects(state, dataCache);
        renderSummaryTable(state, dataCache);
    }

    function renderAllVisuals(state, dataCache) {
        // This function is now deprecated. All rendering should go through _dispatchAction.
        // It's kept for backward compatibility during refactoring, but will be removed.
        console.warn("[DEBUG] renderAllVisuals() called. This function is deprecated. Use app.state.dispatchAction instead.");
        renderPrimaryCharts(state, dataCache);
        renderOverlays(state, dataCache);
        renderFrequencyBar(state, dataCache);
    }

    function renderHoverEffects(state, dataCache) {
        const { controllers } = app.registry;
        const SpectrogramChart = app.classes.SpectrogramChart;
        if (!controllers || !SpectrogramChart) return;

        const hoverState = state.interaction.hover;

        // The data processing is now handled in onStateChange, so we just need to render.
        renderFrequencyBar(state, dataCache);

        // Only render hover effects if hover is enabled
        if (state.view.hoverEnabled) {
            controllers.chartsByName.forEach(chart => {
                if (hoverState.isActive) {
                    chart.renderHoverLine(hoverState.timestamp);
                }
                else {
                    chart.hideHoverLine();
                }

                if (chart instanceof SpectrogramChart) {
                    chart.renderHoverDetails(hoverState, dataCache.activeFreqBarData);
                }
            });
        } else {
            // If hover is disabled, hide all hover lines
            controllers.chartsByName.forEach(chart => {
                chart.hideHoverLine();
            });
        }

        // After updating hover effects, re-render the labels with the new context
        renderLabels(state);
    }

    function renderTapLines(state) {
        const { models } = app.registry;
        if (!models?.clickLines) return;

        const { isActive, timestamp } = state.interaction.tap;
        models.clickLines.forEach(line => {
            if (line) {
                line.location = timestamp;
                line.visible = isActive;
            }
        });
    }

    function renderLabels(state) {
        const { controllers } = app.registry;
        if (!controllers?.chartsByName) return;

        const hoverState = state.interaction.hover;
        const tapState = state.interaction.tap;

        // If no interaction is active, hide all labels and exit.
        if (!hoverState.isActive && !tapState.isActive) {
            controllers.chartsByName.forEach(chart => chart.hideLabel());
            return;
        }

        controllers.chartsByName.forEach(chart => {
            // For the chart being hovered, its label is tied to the hover line (only if hover is enabled).
            if (hoverState.isActive && chart.name === hoverState.sourceChartName && state.view.hoverEnabled) {
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
    function renderMarkers(state) {
        const { controllers } = app.registry;
        if (!controllers?.chartsByName) return;

        controllers.chartsByName.forEach(chart => {
            chart.syncMarkers(state.markers.timestamps, state.markers.enabled);
        });
    }

    function renderRegions(state, dataCache) {
        const { controllers, models } = app.registry;
        const regionsState = state?.regions;
        if (!regionsState) return;
        const regionList = regionsState.allIds.map(id => regionsState.byId[id]).filter(Boolean);
        const panelVisible = regionsState.panelVisible !== false;
        const overlaysVisible = regionsState.overlaysVisible !== false;
        const regionsForCharts = overlaysVisible ? regionList : [];

        if (controllers?.chartsByName) {
            controllers.chartsByName.forEach(chart => {
                if (typeof chart.syncRegions === 'function') {
                    const selectedId = overlaysVisible ? regionsState.selectedId : null;
                    chart.syncRegions(regionsForCharts, selectedId);
                }
            });
        }

        const regionPanelRenderer = app.services?.regionPanelRenderer;
        if (regionPanelRenderer && typeof regionPanelRenderer.renderRegionPanel === 'function') {
            const panelModels = {
                select: models?.regionPanelSelect,
                messageDiv: models?.regionPanelMessageDiv,
                detail: models?.regionPanelDetail,
                copyButton: models?.regionPanelCopyButton,
                deleteButton: models?.regionPanelDeleteButton,
                addAreaButton: models?.regionPanelAddAreaButton,
                mergeButton: models?.regionPanelMergeButton,
                mergeSelect: models?.regionPanelMergeSelect,
                colorPicker: models?.regionPanelColorPicker,
                noteInput: models?.regionPanelNoteInput,
                metricsDiv: models?.regionPanelMetricsDiv,
                frequencyCopyButton: models?.regionPanelFrequencyCopyButton,
                frequencyTableDiv: models?.regionPanelFrequencyTableDiv,
                spectrumDiv: models?.regionPanelSpectrumDiv,
                visibilityToggle: models?.regionVisibilityToggle,
                autoDayButton: models?.regionAutoDayButton,
                autoNightButton: models?.regionAutoNightButton,
            };
            const availablePositions = Array.isArray(state?.view?.availablePositions)
                ? state.view.availablePositions
                : [];
            const fallbackPositions = models?.timeSeriesSources
                ? Object.keys(models.timeSeriesSources)
                : [];
            const positionCount = availablePositions.length ? availablePositions.length : fallbackPositions.length;

            regionPanelRenderer.renderRegionPanel(
                panelModels,
                regionList,
                regionsState.selectedId,
                state,
                {
                    panelVisible,
                    overlaysVisible,
                    positionCount
                }
            );
        }
    }

    function renderFrequencyTable(state, dataCache) {
        const { models } = app.registry;
        if (!models) return;

        const tableDiv = models.freqTableDiv;

        if (!tableDiv) {
            console.error("Frequency table div model not found.");
            return;
        }

        // Get tap context for independent table data processing
        const { isActive, timestamp, position } = state.interaction.tap;

        if (!isActive || !timestamp || !position) {
            tableDiv.text = "<p>Tap on a time series chart to populate this table.</p>";
            return;
        }

        // Get the full spectral data for the tapped position and timestamp
        const activeSpectralData = dataCache.activeSpectralData[position];
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

    function renderFrequencyBar(state, dataCache) {
        const { models } = app.registry;
        if (!models) return;

        const freqData = dataCache.activeFreqBarData;
        models.barSource.data = {
            'levels': freqData.levels,
            'frequency_labels': freqData.frequency_labels
        };
        models.barChart.x_range.factors = freqData.frequency_labels;
        models.barChart.title.text = `Slice: ${freqData.sourceposition} | ${freqData.param} @ ${new Date(freqData.timestamp).toLocaleTimeString()} | by ${freqData.setBy}`;
        models.barSource.change.emit();

        // Also update the HTML table
        renderFrequencyTable(state, dataCache);
    }

    const PLAYING_BACKGROUND_COLOR = '#e6f0ff'; // A light blue to highlight the active chart
    const DEFAULT_BACKGROUND_COLOR = '#ffffff'; // Standard white background

    function renderControlWidgets(state) {
        const { models, controllers } = app.registry;
        if (!models || !controllers) return;

        const { isPlaying, activePositionId, playbackRate, volumeBoost } = state.audio;
        const chartVisibility = state?.view?.chartVisibility || {};
        const isChartVisible = chartName => {
            if (!chartName) {
                return true;
            }
            if (Object.prototype.hasOwnProperty.call(chartVisibility, chartName)) {
                return Boolean(chartVisibility[chartName]);
            }
            return true;
        };

        state.view.availablePositions.forEach(pos => {
            const controller = controllers.positions[pos];
            const controls = models.audio_controls[pos];
            const isThisPositionActive = isPlaying && activePositionId === pos;
            const timeSeriesChartName = `figure_${pos}_timeseries`;
            const spectrogramChartName = `figure_${pos}_spectrogram`;
            const shouldShowControls = isChartVisible(timeSeriesChartName) || isChartVisible(spectrogramChartName);

            if (controls?.layout && controls.layout.visible !== shouldShowControls) {
                controls.layout.visible = shouldShowControls;
            }

            // --- Update Chart Visuals (Title and Background) ---
            if (controller && controller.timeSeriesChart) {
                const tsChart = controller.timeSeriesChart;
                // Base title comes from the state's displayDetails
                const baseTitle = `${pos} - Time History${state.view.displayDetails[pos].line.reason}`;
                tsChart.model.title.text = isThisPositionActive ? `${baseTitle} (▶ PLAYING)` : baseTitle;
                tsChart.model.background_fill_color = isThisPositionActive ? PLAYING_BACKGROUND_COLOR : DEFAULT_BACKGROUND_COLOR;
            }
            if (controller && controller.spectrogramChart) {
                const specChart = controller.spectrogramChart;
                const baseTitle = `${pos} - ${state.view.selectedParameter} Spectrogram${state.view.displayDetails[pos].spec.reason}`;
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

    function mapComparisonMetricValue(paramLabel, metricsRow) {
        if (!metricsRow) return null;
        const normalized = typeof paramLabel === 'string'
            ? paramLabel.replace(/\s+/g, '').toUpperCase()
            : '';
        switch (normalized) {
            case 'LAEQ':
            case 'LZEQ':
                return metricsRow.laeq;
            case 'LAFMAX':
            case 'LAMAX':
                return metricsRow.lafmax;
            case 'LAF90':
            case 'LA90':
                return metricsRow.la90;
            default:
                return null;
        }
    }

    function renderSummaryTable(state, dataCache) {
        const { models } = app.registry;
        if (!models) return;

        const tableDiv = models.summaryTableDiv;
        if (!tableDiv) {
            console.error("Summary table div model not found.");
            return;
        }

        const { isActive, timestamp } = state.interaction.tap;
        const viewState = state?.view || {};
        const comparisonState = viewState.comparison || {};
        const isComparisonMode = viewState.mode === 'comparison' && comparisonState.isActive;
        const hasComparisonSlice = isComparisonMode
            && Number.isFinite(comparisonState.start)
            && Number.isFinite(comparisonState.end)
            && comparisonState.start !== comparisonState.end;
        const includedPositions = Array.isArray(comparisonState.includedPositions)
            ? comparisonState.includedPositions
            : [];

        const initialDoc = new DOMParser().parseFromString(tableDiv.text, 'text/html');
        const headerCells = initialDoc.querySelectorAll("thead th:not(.position-header)");
        const parameters = Array.from(headerCells).map(th => th.textContent.trim());

        let tableBodyHtml = '';

        if (isComparisonMode) {
            if (!hasComparisonSlice || !includedPositions.length) {
                tableBodyHtml = `<tr><td class='placeholder' colspan='${parameters.length + 1}'>Select a comparison region to populate this table.</td></tr>`;
            } else {
                const processor = app.comparisonMetrics?.processComparisonSliceMetrics;
                if (typeof processor === 'function') {
                    const metricsResult = processor({
                        start: comparisonState.start,
                        end: comparisonState.end,
                        positionIds: includedPositions,
                        timeSeriesSources: models.timeSeriesSources,
                        preparedGlyphData: models.preparedGlyphData,
                        selectedParameter: viewState.selectedParameter
                    }) || {};
                    const metricsRows = Array.isArray(metricsResult.metricsRows) ? metricsResult.metricsRows : [];
                    if (metricsRows.length) {
                        const startTs = Number(metricsResult.start);
                        const endTs = Number(metricsResult.end);
                        const durationMs = Number.isFinite(metricsRows[0]?.durationMs)
                            ? metricsRows[0].durationMs
                            : (Number.isFinite(startTs) && Number.isFinite(endTs) ? Math.max(0, endTs - startTs) : null);
                        const parts = [];
                        if (Number.isFinite(startTs) && Number.isFinite(endTs)) {
                            const startStr = new Date(startTs).toLocaleString();
                            const endStr = new Date(endTs).toLocaleString();
                            parts.push(`Region: ${startStr} – ${endStr}`);
                        }
                        if (Number.isFinite(durationMs)) {
                            parts.push(`Duration: ${formatDuration(durationMs)}`);
                        }
                        if (parts.length) {
                            tableBodyHtml += `<tr><td class='timestamp-info' colspan='${parameters.length + 1}'>${parts.join(' | ')}</td></tr>`;
                        }

                        metricsRows.forEach(row => {
                            const positionLabel = escapeHtml(String(row.positionId || '—'));
                            let rowHtml = `<tr><td class="position-header">${positionLabel}</td>`;
                            parameters.forEach(param => {
                                const metricValue = mapComparisonMetricValue(param, row);
                                const formattedValue = Number.isFinite(metricValue)
                                    ? metricValue.toFixed(1)
                                    : 'N/A';
                                rowHtml += `<td>${formattedValue}</td>`;
                            });
                            rowHtml += `</tr>`;
                            tableBodyHtml += rowHtml;
                        });
                    } else {
                        tableBodyHtml = `<tr><td class='placeholder' colspan='${parameters.length + 1}'>No data available for the selected comparison region.</td></tr>`;
                    }
                } else {
                    tableBodyHtml = `<tr><td class='placeholder' colspan='${parameters.length + 1}'>Comparison metrics are unavailable.</td></tr>`;
                }
            }
        } else if (!isActive || !timestamp) {
            tableBodyHtml = `<tr><td class='placeholder' colspan='${parameters.length + 1}'>Tap on a time series chart to populate this table.</td></tr>`;
        } else {
            // Add timestamp info row
            const timestampStr = new Date(timestamp).toLocaleString();
            tableBodyHtml += `<tr><td class='timestamp-info' colspan='${parameters.length + 1}'>Values at: ${timestampStr}</td></tr>`;

            state.view.availablePositions.forEach(pos => {
                let rowHtml = `<tr><td class="position-header">${pos}</td>`;
                const activeLineData = dataCache.activeLineData[pos];

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

    function renderComparisonMode(state) {
        const { models, controllers } = app.registry;
        if (!models) return;

        const viewState = state?.view || {};
        const comparisonState = viewState.comparison || {};
        const isComparisonActive = viewState.mode === 'comparison';

        if (models.regionPanelLayout) {
            models.regionPanelLayout.visible = !isComparisonActive;
        }
        if (models.comparisonPanelLayout) {
            models.comparisonPanelLayout.visible = isComparisonActive;
        }
        if (models.sidePanelTabs) {
            models.sidePanelTabs.active = isComparisonActive ? 1 : 0;
        }
        if (models.frequencyBarLayout) {
            models.frequencyBarLayout.visible = !isComparisonActive;
        }
        if (models.comparisonFrequencyLayout) {
            models.comparisonFrequencyLayout.visible = isComparisonActive;
        }

        if (models.startComparisonButton) {
            models.startComparisonButton.disabled = isComparisonActive;
        }
        if (models.comparisonFinishButton) {
            models.comparisonFinishButton.disabled = !isComparisonActive;
        }
        const hasSlice = Number.isFinite(comparisonState.start) && Number.isFinite(comparisonState.end);
        if (models.comparisonMakeRegionsButton) {
            models.comparisonMakeRegionsButton.disabled = !(isComparisonActive && hasSlice);
        }

        const sliceInfoDiv = models.comparisonSliceInfoDiv;
        if (sliceInfoDiv) {
            sliceInfoDiv.visible = isComparisonActive;
            let infoHtml;
            if (!isComparisonActive || !hasSlice) {
                infoHtml = "<div class='comparison-slice-info'><em>Select a time slice to view details.</em></div>";
            } else {
                const startText = escapeHtml(formatDateTime(comparisonState.start));
                const endText = escapeHtml(formatDateTime(comparisonState.end));
                infoHtml = "<div class=\"comparison-slice-info\"><strong>Selected Slice</strong><div>Start: "
                    + `${startText}</div><div>End: ${endText}</div></div>`;
            }
            if (sliceInfoDiv.text !== infoHtml) {
                sliceInfoDiv.text = infoHtml;
            }
        }

        const selector = models.comparisonPositionSelector;
        if (selector) {
            selector.disabled = !isComparisonActive;
            const orderedPositions = Array.isArray(models.comparisonPositionIds)
                ? models.comparisonPositionIds
                : [];
            const includedPositions = Array.isArray(comparisonState.includedPositions)
                ? comparisonState.includedPositions
                : [];
            const desiredActive = includedPositions
                .map(positionId => orderedPositions.indexOf(positionId))
                .filter(index => index >= 0)
                .sort((a, b) => a - b);

            const isDifferentLength = selector.active.length !== desiredActive.length;
            const hasDifferentValues = !isDifferentLength && selector.active.some((value, idx) => value !== desiredActive[idx]);
            if (isDifferentLength || hasDifferentValues) {
                selector.active = desiredActive;
            }
        }

        const includedPositions = Array.isArray(comparisonState.includedPositions)
            ? comparisonState.includedPositions
            : [];
        const includedSet = new Set(includedPositions);
        const controllersByPosition = controllers?.positions || {};
        const chartVisibility = viewState.chartVisibility || {};

        Object.keys(controllersByPosition).forEach(positionId => {
            const controller = controllersByPosition[positionId];
            if (!controller || !controller.timeSeriesChart) {
                return;
            }
            const chartName = `figure_${positionId}_timeseries`;
            const baseVisible = Object.prototype.hasOwnProperty.call(chartVisibility, chartName)
                ? Boolean(chartVisibility[chartName])
                : true;
            const shouldBeVisible = !isComparisonActive || includedSet.has(positionId);
            controller.timeSeriesChart.setVisible(baseVisible && shouldBeVisible);
        });

        updateComparisonSliceLines(controllersByPosition, isComparisonActive && hasSlice, comparisonState.start, comparisonState.end);

        if (!isComparisonActive || !hasSlice || !includedPositions.length) {
            if (models.comparisonMetricsDiv) {
                models.comparisonMetricsDiv.text = COMPARISON_METRICS_EMPTY_HTML;
            }
            updateComparisonFrequencyVisualization(models, null);
            return;
        }

        const processor = app.comparisonMetrics?.processComparisonSliceMetrics;
        if (typeof processor !== 'function') {
            return;
        }

        const metricsResult = processor({
            start: comparisonState.start,
            end: comparisonState.end,
            positionIds: includedPositions,
            timeSeriesSources: models.timeSeriesSources,
            preparedGlyphData: models.preparedGlyphData,
            selectedParameter: viewState.selectedParameter
        }) || {};

        if (models.comparisonMetricsDiv) {
            models.comparisonMetricsDiv.text = buildComparisonMetricsTable(metricsResult.metricsRows || []);
        }

        updateComparisonFrequencyVisualization(models, metricsResult.spectrum);
    }

    function renderActiveTool(state, models) {
        const desired = state?.interaction?.activeDragTool === 'box_select' ? 'box_select' : 'pan';
        const charts = Array.isArray(models?.charts) ? models.charts : [];

        charts.forEach(chart => {
            if (!chart?.toolbar) {
                return;
            }

            const tools = Array.isArray(chart.toolbar.tools) ? chart.toolbar.tools : [];
            let panTool = null;
            let boxSelectTool = null;

            tools.forEach(tool => {
                if (!tool) {
                    return;
                }
                const typeName = typeof tool.type === 'string' ? tool.type.toLowerCase() : '';
                const ctorName = typeof tool.constructor?.name === 'string' ? tool.constructor.name.toLowerCase() : '';
                const toolName = typeof tool.tool_name === 'string' ? tool.tool_name.toLowerCase() : '';

                if (!panTool && (typeName === 'pantool' || ctorName === 'pantool' || toolName === 'pan')) {
                    panTool = tool;
                    return;
                }

                const isBoxSelectName = toolName.includes('box select');
                const isBoxSelectType = typeName === 'boxselecttool' || ctorName === 'boxselecttool' || typeName.includes('boxselect') || ctorName.includes('boxselect');
                if (!boxSelectTool && (isBoxSelectName || isBoxSelectType)) {
                    boxSelectTool = tool;
                }
            });

            let targetTool = null;
            if (desired === 'box_select') {
                targetTool = boxSelectTool || panTool || null;
            } else {
                targetTool = panTool || boxSelectTool || null;
            }

            if (targetTool && chart.toolbar.active_drag !== targetTool) {
                chart.toolbar.active_drag = targetTool;
            }
        });
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
        renderRegions: renderRegions,
        renderFrequencyTable: renderFrequencyTable,
        renderFrequencyBar: renderFrequencyBar,
        renderControlWidgets: renderControlWidgets,
        renderSummaryTable: renderSummaryTable,
        renderComparisonMode: renderComparisonMode,
        renderActiveTool: renderActiveTool,
        //formatTime: formatTime
    };
})(window.NoiseSurveyApp);
