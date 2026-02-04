// noise_survey_analysis/static/js/registry.js

/**
 * @fileoverview Initializes and holds non-state objects like Bokeh models and
 * chart/position controllers. This acts as a central registry for the application's
 * "heavy" components that need to be accessed for rendering and side-effects.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    // This object will hold direct references to Bokeh models, 
    // acting as a "Data Cache" that may be mutated by the UI
    const models = {};

    // This object will hold class instances that control chart groups.
    const controllers = {
        positions: {},
        chartsByName: new Map(),
    };

    /**
     * Populates the registry with Bokeh models and initializes the controllers.
     * This function is called once at application startup.
     * @param {object} bokehModels - The collection of models passed from the Bokeh template.
     */
    function initializeRegistry(bokehModels) {
        console.info('[Registry]', 'Initializing models and controllers...');

        const { PositionController } = app.classes;

        // 1. Populate the 'models' registry
        for (const key in bokehModels) {
            models[key] = bokehModels[key];
        }

        models.sourceConfigs = Array.isArray(bokehModels?.sourceConfigs)
            ? bokehModels.sourceConfigs
            : [];
        models.jobNumber = bokehModels?.jobNumber || null;
        models.positionDisplayTitles = bokehModels?.positionDisplayTitles || {};
        models.savedWorkspaceState = bokehModels?.savedWorkspaceState || null;
        if (bokehModels?.sessionMenu) {
            models.sessionMenu = bokehModels.sessionMenu;
        }

        //Robustly find essential models by name from the Bokeh document
        if (window.Bokeh && Bokeh.documents[0]) {
            const doc = Bokeh.documents[0];
            models.audio_control_source = doc.get_model_by_name('audio_control_source');
            models.audio_status_source = doc.get_model_by_name('audio_status_source');
            //Log a warning if the models are not found, but continue execution
            if (!models.audio_control_source) console.warn("[Registry] 'audio_control_source' not found.");
            if (!models.audio_status_source) console.warn("[Registry] 'audio_status_source' not found.");
        } else {
            console.error("[Registry] Bokeh.documents[0] is not available.");
        }

        // Map nested audio control widgets for easier access
        if (bokehModels.audio_controls) {
            models.audio_controls = {};
            for (const posId in bokehModels.audio_controls) {
                models.audio_controls[posId] = {
                    playToggle: bokehModels.audio_controls[posId].play_toggle,
                    playbackRateButton: bokehModels.audio_controls[posId].playback_rate_button,
                    volumeBoostButton: bokehModels.audio_controls[posId].volume_boost_button,
                    chartOffsetSpinner: bokehModels.audio_controls[posId].chart_offset_spinner,
                    audioOffsetSpinner: bokehModels.audio_controls[posId].audio_offset_spinner,
                    effectiveOffsetDisplay: bokehModels.audio_controls[posId].effective_offset_display,
                    layout: bokehModels.audio_controls[posId].layout || null
                };
            }
        }

        // 2. Initialize controllers
        const availablePositions = Array.from(new Set(models.charts.map(c => {
            const parts = c.name.split('_');
            return parts.length >= 2 ? parts[1] : null;
        }).filter(Boolean)));

        availablePositions.forEach(pos => {
            const posController = new PositionController(pos, models);
            controllers.positions[pos] = posController;
            posController.charts.forEach(chart => {
                controllers.chartsByName.set(chart.name, chart);
            });
        });

        // 3. Prepare the payload for the INITIALIZE_STATE action
        const chartVisibility = {};
        models.charts.forEach(chart => {
            const checkbox = models.visibilityCheckBoxes.find(cb => cb.name === `visibility_${chart.name}`);
            chartVisibility[chart.name] = checkbox ? checkbox.active.includes(0) : true;
        });

        const initialStatePayload = {
            availablePositions: availablePositions,
            selectedParameter: models.paramSelect?.value || 'LZeq',
            viewport: { min: models.charts[0].x_range.start, max: models.charts[0].x_range.end },
            chartVisibility: chartVisibility,
            hoverEnabled: true,
            positionDisplayTitles: models.positionDisplayTitles,
        };

        console.info('[Registry]', 'Registry initialized successfully.');

        // Return the payload needed to initialize the pure state store
        return initialStatePayload;
    }

    // Attach the public API to the global app object
    app.registry = {
        initialize: initializeRegistry,
        models: models,
        controllers: controllers,
    };

})(window.NoiseSurveyApp);