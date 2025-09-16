// noise_survey_analysis/static/js/init.js

/**
 * @fileoverview Initializes the core components of the application.
 * This script should be loaded before any other application script to ensure
 * that the global `app` object and the `store` are available.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    // Create the store and attach it to the app object immediately.
    // This ensures that any subsequently loaded module can safely destructure `store`.
    if (app.createStore && app.rootReducer) {
        app.store = app.createStore(app.rootReducer);
        console.info('[Init]', 'Store created.');
        
        function reInitializeStore() {
            app.store = app.createStore(app.rootReducer);
        }

        app.init = {
            reInitializeStore: reInitializeStore
        };
    } else {
        console.error('[Init]', 'createStore or rootReducer is not available. Ensure Store.js and reducers.js are loaded before init.js');
    }

})(window.NoiseSurveyApp);
