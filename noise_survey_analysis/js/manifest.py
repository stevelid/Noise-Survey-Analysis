"""
manifest.py

Single list of the JavaScript files (relative to ``static/js``) that make up the dashboard
bundle, in load order. ``DashBuilder._load_all_js_files`` reads this list.

To add a new JS file, add one line here in the right place. Order matters: a file must come
after anything it uses at load time. Registry-style seams (``registerKeyBindings``,
``registerAutomationCommand``, ``registerRenderHook``) can be called from a new file as long as
the new file is listed after the module that defines the seam.

``js/loader.py`` is legacy and is not used by the dashboard; only this manifest is.
"""

JS_LOAD_ORDER = [
    # 1. State Management Core (in dependency order)
    'core/actions.js',
    'features/regions/annotationModel.js',
    'services/session/workspaceMigration.js',
    'features/view/viewResolution.js',
    'features/view/viewReducer.js',
    'features/view/viewSelectors.js',
    'features/view/viewThunks.js',
    'features/interaction/interactionReducer.js',
    'features/markers/markersReducer.js',
    'features/markers/markersSelectors.js',
    'features/markers/markersThunks.js',
    'features/classifications/classificationReducer.js',
    'features/classifications/classificationSelectors.js',
    'features/classifications/classificationUtils.js',
    'features/classifications/classificationThunks.js',
    'features/regions/regionReducer.js',
    'features/regions/regionSelectors.js',
    'features/regions/annotationMetrics.js',
    'features/regions/regionUtils.js',
    'features/regions/regionThunks.js',
    'features/regions/suggestionModel.js',
    'features/annotations/panelSelectors.js',
    'features/annotations/panelThunks.js',
    'features/interaction/interactionThunks.js',
    'features/audio/audioReducer.js',
    'features/audio/audioThunks.js',
    'services/audio/audioCommands.js',            # store change -> audio command, shared by both backends (WP5b)
    'services/audio/clipPlayer.js',               # in-page audio playback, 'browser' backend (WP5b)
    'features/layout/layoutReducer.js',
    'features/layout/layoutSelectors.js',
    'features/layout/layoutThunks.js',
    'services/layout/layoutMath.js',              # pure zoom/pan/fit/y-fit maths (WP1)
    'features/navigation/navThunks.js',           # zoom, pan, focus, spectrogram and y-mode intents (WP1)
    'core/rootReducer.js',
    'core/history.js',
    'store.js',           # Creates the store, needs rootReducer
    'init.js',            # Creates app.init and reInitializeStore, needs store

    # 2. Core setup and utilities
    'utils.js',
    'comparison-metrics.js',
    'thunks.js',

    # 3. Application modules
    'chart-classes.js',   # Defines Chart classes, needed by registry
    'registry.js',        # Defines the model/controller registry
    'processors/common.js',
    'processors/line.js',
    'processors/spectral.js',
    'processors/frequency.js',
    'data-processors.js', # Public orchestration facade, after feature processors
    # Compatibility helpers for external/fake-model integrations;
    # the dashboard creates only the HTML annotation panel.
    'services/markers/markerPanelRenderer.js',
    'services/regions/regionPanelRenderer.js',
    'services/classifications/classificationPanelRenderer.js',
    'services/renderers/controlWidgetsRenderer.js',
    'services/panels/htmlPanelEvents.js',
    'services/panels/htmlPanelRenderer.js',
    'services/renderers.js',
    'services/session/annotationCsv.js',
    'services/session/sessionManager.js',
    'services/eventHandlers/viewEventHandlers.js',
    'core/keymap.js',     # Keyboard shortcut table + registerKeyBindings, before eventHandlers
    'services/eventHandlers.js',

    # 4. Main application entry point (loads last)
    'app.js',             # Wires everything together, attaches app.init.initialize

    # 5. Extensions that plug into app.js seams (app.registerRenderHook, ...). They only register
    #    callbacks at load time; nothing runs until app.init.initialize is called.
    'services/automation/annotationCommands.js',  # control API: list/add/update/delete/show annotations
    'features/regions/suggestionKeys.js',         # A / D accept-reject, { } step through suggestions
    'services/wheelController.js',                # wheel zooms or scrolls the page (WP1)
    'services/helpOverlay.js',                    # ? key help overlay built from the keymap (WP1)
    'services/layout/layoutRenderer.js',          # fit to window, spectrogram modes, order, y-fit (WP1)
    'features/navigation/navKeys.js',             # + - 0 Z S O F Y W ? and arrow keys (WP1)
]
