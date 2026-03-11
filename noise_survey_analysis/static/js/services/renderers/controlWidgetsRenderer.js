// noise_survey_analysis/static/js/services/renderers/controlWidgetsRenderer.js

/**
 * @fileoverview Renderer module dedicated to control widgets and per-position controls.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const PLAYING_BACKGROUND_COLOR = '#e6f0ff';
    const DEFAULT_BACKGROUND_COLOR = '#ffffff';

    function isChartVisibleFactory(chartVisibility) {
        return function isChartVisible(chartName) {
            if (!chartName) {
                return true;
            }
            if (Object.prototype.hasOwnProperty.call(chartVisibility, chartName)) {
                return Boolean(chartVisibility[chartName]);
            }
            return true;
        };
    }

    function syncLogThresholdSpinner(viewState, spinner) {
        if (!spinner) {
            return;
        }
        const resolution = app.features?.view?.resolution;
        const thresholdSeconds = resolution?.resolveLogThresholdSeconds
            ? resolution.resolveLogThresholdSeconds(app.registry?.models || {}, viewState)
            : null;
        if (!Number.isFinite(thresholdSeconds) || thresholdSeconds <= 0) {
            return;
        }

        const minutes = resolution?.secondsToMinutes
            ? resolution.secondsToMinutes(thresholdSeconds)
            : (thresholdSeconds / 60);
        if (!Number.isFinite(minutes) || minutes <= 0) {
            return;
        }

        const low = Number(spinner.low);
        const high = Number(spinner.high);
        const clamped = resolution?.clampNumber
            ? resolution.clampNumber(minutes, low, high)
            : Math.min(Number.isFinite(high) ? high : minutes, Math.max(Number.isFinite(low) ? low : minutes, minutes));
        const current = Number(spinner.value);
        if (!Number.isFinite(current) || Math.abs(current - clamped) > 0.0001) {
            spinner.value = clamped;
        }
    }

    function renderControlWidgets(state, displayDetailsByPosition = null) {
        const { models, controllers } = app.registry || {};
        if (!models || !controllers) return;

        const { isPlaying, activePositionId, playbackRate, volumeBoost } = state.audio;
        const viewState = state?.view || {};

        const chartVisibility = viewState.chartVisibility || {};
        const availablePositions = Array.isArray(viewState.availablePositions)
            ? viewState.availablePositions
            : [];
        const selectedParameter = viewState.selectedParameter;
        const positionChartOffsets = viewState.positionChartOffsets || {};
        const positionAudioOffsets = viewState.positionAudioOffsets || {};
        const positionEffectiveOffsets = viewState.positionEffectiveOffsets || {};
        const displayTitles = viewState.positionDisplayTitles || {};
        const isServerMode = models?.config?.server_mode !== false;

        const viewToggleModel = models.viewToggle;
        if (viewToggleModel) {
            const isLogActive = viewState.globalViewType === 'log';
            if (viewToggleModel.active !== isLogActive) {
                viewToggleModel.active = isLogActive;
            }
            viewToggleModel.label = isLogActive ? 'Log View Enabled' : 'Log View Disabled';
        }

        const hoverToggleModel = models.hoverToggle;
        if (hoverToggleModel) {
            const isHoverActive = Boolean(viewState.hoverEnabled);
            if (hoverToggleModel.active !== isHoverActive) {
                hoverToggleModel.active = isHoverActive;
            }
            hoverToggleModel.label = isHoverActive ? 'Hover Enabled' : 'Hover Disabled';
        }

        syncLogThresholdSpinner(viewState, models.logThresholdSpinner);

        const thresholdSeconds = app.features?.view?.resolution?.resolveLogThresholdSeconds
            ? app.features.view.resolution.resolveLogThresholdSeconds(models, viewState)
            : null;
        const streamingReasons = [];
        const detailEntries = displayDetailsByPosition ? Object.values(displayDetailsByPosition) : [];
        detailEntries.forEach(details => {
            const lineReason = details?.line?.reason;
            const specReason = details?.spec?.reason || details?.spectrogram?.reason;
            if (typeof lineReason === 'string' && lineReason.includes('Streaming Log Data')) {
                streamingReasons.push(lineReason);
            }
            if (typeof specReason === 'string' && specReason.includes('Streaming Log Data')) {
                streamingReasons.push(specReason);
            }
        });
        const isStreamingInBackground = streamingReasons.length > 0;
        if (models.viewStatusChip) {
            const mode = viewState.globalViewType === 'log' ? 'Log' : 'Overview';
            const thresholdText = Number.isFinite(thresholdSeconds) ? `${Math.round(thresholdSeconds / 60)}m` : '--';
            const streamingSuffix = isStreamingInBackground
                ? ` <span style='color:#9a3412;'>| Streaming log data...</span>`
                : '';
            models.viewStatusChip.text = `<span style='font-size:11px;color:#0f172a;'>View: ${mode} | ${thresholdText}${streamingSuffix}</span>`;
        }
        if (models.focusStatusChip) {
            const activeLabel = (isPlaying && activePositionId)
                ? (displayTitles[activePositionId] || activePositionId)
                : 'none';
            models.focusStatusChip.text = `<span style='font-size:11px;color:#0f172a;'>Focus: ${activeLabel}</span>`;
        }

        const globalAudioControls = models.globalAudioControls;
        if (globalAudioControls) {
            if (globalAudioControls.layout) {
                globalAudioControls.layout.visible = isServerMode;
            }
            if (isServerMode) {
                if (globalAudioControls.play_toggle) {
                    if (globalAudioControls.play_toggle.active !== isPlaying) {
                        globalAudioControls.play_toggle.active = isPlaying;
                    }
                    globalAudioControls.play_toggle.label = isPlaying ? "Pause" : "Play";
                    globalAudioControls.play_toggle.button_type = isPlaying ? 'primary' : 'success';
                }

                if (globalAudioControls.playback_rate_button) {
                    globalAudioControls.playback_rate_button.label = `${playbackRate.toFixed(1)}x`;
                }

                if (globalAudioControls.volume_boost_button) {
                    const isBoostActive = isPlaying && volumeBoost;
                    if (globalAudioControls.volume_boost_button.active !== isBoostActive) {
                        globalAudioControls.volume_boost_button.active = isBoostActive;
                    }
                    globalAudioControls.volume_boost_button.button_type = isBoostActive ? 'warning' : 'light';
                }

                if (globalAudioControls.active_position_display) {
                    let displayText = "<span style='font-size: 11px; color: #666;'>No audio</span>";
                    if (isPlaying && activePositionId) {
                        const displayName = typeof displayTitles[activePositionId] === 'string' && displayTitles[activePositionId].trim()
                            ? displayTitles[activePositionId]
                            : activePositionId;
                        displayText = `<span style='font-size: 11px; color: #2c7bb6; font-weight: 600;'>&#9654; ${displayName}</span>`;
                    }
                    if (globalAudioControls.active_position_display.text !== displayText) {
                        globalAudioControls.active_position_display.text = displayText;
                    }
                }

                if (globalAudioControls.audio_file_info_display) {
                    let fileInfoText = "";
                    if (isPlaying && state.audio.currentFileName) {
                        const fileName = state.audio.currentFileName;
                        const currentTimeMs = state.audio.currentTime || 0;
                        const fileStartTimeMs = state.audio.currentFileStartTime || 0;
                        const positionInFileSec = Math.max(0, (currentTimeMs - fileStartTimeMs) / 1000);
                        const posHours = Math.floor(positionInFileSec / 3600);
                        const posMinutes = Math.floor((positionInFileSec % 3600) / 60);
                        const posSeconds = Math.floor(positionInFileSec % 60);
                        const positionFormatted = `${String(posHours).padStart(2, '0')}:${String(posMinutes).padStart(2, '0')}:${String(posSeconds).padStart(2, '0')}`;

                        const fileStartDate = new Date(fileStartTimeMs);
                        const startHours = String(fileStartDate.getHours()).padStart(2, '0');
                        const startMinutes = String(fileStartDate.getMinutes()).padStart(2, '0');
                        const startSeconds = String(fileStartDate.getSeconds()).padStart(2, '0');
                        const startDay = String(fileStartDate.getDate()).padStart(2, '0');
                        const startMonth = String(fileStartDate.getMonth() + 1).padStart(2, '0');
                        const startYear = String(fileStartDate.getFullYear()).slice(-2);
                        const startTimeFormatted = `${startHours}:${startMinutes}:${startSeconds} ${startDay}/${startMonth}/${startYear}`;

                        fileInfoText = `<span style='font-size: 10px; color: #555;'>` +
                            `<b>${fileName}</b> | ` +
                            `${positionFormatted} | ` +
                            `Start: ${startTimeFormatted}` +
                            `</span>`;
                    }
                    if (globalAudioControls.audio_file_info_display.text !== fileInfoText) {
                        globalAudioControls.audio_file_info_display.text = fileInfoText;
                    }
                }
            }
        }

        const isChartVisible = isChartVisibleFactory(chartVisibility);
        const jobNumber = models.jobNumber;

        availablePositions.forEach(pos => {
            const controller = controllers.positions[pos];
            const positionControls = models.positionControls?.[pos];
            const isThisPositionActive = isPlaying && activePositionId === pos;
            const timeSeriesChartName = `figure_${pos}_timeseries`;
            const spectrogramChartName = `figure_${pos}_spectrogram`;
            const shouldShowControls = isChartVisible(timeSeriesChartName) || isChartVisible(spectrogramChartName);
            const rawDisplayName = typeof displayTitles[pos] === 'string' && displayTitles[pos].trim()
                ? displayTitles[pos]
                : pos;
            const displayName = jobNumber ? `${jobNumber} | ${rawDisplayName}` : rawDisplayName;

            if (positionControls?.layout) {
                positionControls.layout.visible = shouldShowControls;
            }

            if (controller) {
                if (typeof controller.setDisplayName === 'function') {
                    controller.setDisplayName(displayName);
                }
                const tsChart = controller.timeSeriesChart;
                const specChart = controller.spectrogramChart;
                if (tsChart?.model) {
                    const tsDetails = displayDetailsByPosition?.[pos]?.line?.reason
                        || tsChart?.lastDisplayDetails?.reason
                        || '';
                    tsChart.model.title.text = `${displayName} - Time Series${tsDetails}`;
                    tsChart.model.background_fill_color = isThisPositionActive ? PLAYING_BACKGROUND_COLOR : DEFAULT_BACKGROUND_COLOR;
                    if (displayDetailsByPosition?.[pos]?.line?.reason) {
                        tsChart.lastDisplayDetails = displayDetailsByPosition[pos].line;
                    }
                }
                if (specChart?.model) {
                    const specDetails = displayDetailsByPosition?.[pos]?.spec?.reason
                        || displayDetailsByPosition?.[pos]?.spectrogram?.reason
                        || specChart?.lastDisplayDetails?.reason
                        || '';
                    specChart.model.title.text = `${displayName} - Spectrogram${specDetails}`;
                    specChart.model.background_fill_color = isThisPositionActive ? PLAYING_BACKGROUND_COLOR : DEFAULT_BACKGROUND_COLOR;
                    if (displayDetailsByPosition?.[pos]?.spec?.reason) {
                        specChart.lastDisplayDetails = displayDetailsByPosition[pos].spec;
                    } else if (displayDetailsByPosition?.[pos]?.spectrogram?.reason) {
                        specChart.lastDisplayDetails = displayDetailsByPosition[pos].spectrogram;
                    }
                }
            }

            if (!positionControls) {
                return;
            }

            if (positionControls.chart_offset_spinner) {
                const offsetSeconds = (Number(positionChartOffsets[pos]) || 0) / 1000;
                if (typeof positionControls.chart_offset_spinner.value !== 'number'
                    || Math.abs(positionControls.chart_offset_spinner.value - offsetSeconds) > 0.0001) {
                    positionControls.chart_offset_spinner.value = offsetSeconds;
                }
            }

            if (positionControls.audio_offset_spinner) {
                const offsetSeconds = (Number(positionAudioOffsets[pos]) || 0) / 1000;
                if (typeof positionControls.audio_offset_spinner.value !== 'number'
                    || Math.abs(positionControls.audio_offset_spinner.value - offsetSeconds) > 0.0001) {
                    positionControls.audio_offset_spinner.value = offsetSeconds;
                }
            }

            if (positionControls.effective_offset_display) {
                const effectiveSeconds = (Number(positionEffectiveOffsets[pos]) || 0) / 1000;
                const sign = effectiveSeconds >= 0 ? '+' : '-';
                positionControls.effective_offset_display.text = `Effective offset: ${sign}${Math.abs(effectiveSeconds).toFixed(2)} s`;
            }

            if (positionControls.display_title_div) {
                const title = typeof displayTitles[pos] === 'string' && displayTitles[pos].trim()
                    ? displayTitles[pos]
                    : pos;
                const html = `<b style="font-size:11px;">${title}</b>`;
                if (positionControls.display_title_div.text !== html) {
                    positionControls.display_title_div.text = html;
                }
            }
        });

        if (models.paramSelect && models.paramSelect.value !== selectedParameter) {
            models.paramSelect.value = selectedParameter;
        }
    }

    app.services = app.services || {};
    app.services.renderers = app.services.renderers || {};
    app.services.renderers.controlWidgets = {
        render: renderControlWidgets
    };
})(window.NoiseSurveyApp);
