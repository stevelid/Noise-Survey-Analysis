// noise_survey_analysis/static/js/services/session/sessionManager.js

/**
 * @fileoverview Manages workspace save/load actions and bridges them to the
 *               Redux-style store. Exposes a small API on `NoiseSurveyApp.session`
 *               that is used by the Bokeh toolbar dropdown.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const SESSION_FILE_VERSION = 1;
    let initialStateApplied = false;

    function triggerJsonDownload(filename, jsonText) {
        try {
            const blob = new Blob([jsonText], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const anchor = document.createElement('a');
            anchor.href = url;
            anchor.download = filename;
            document.body.appendChild(anchor);
            anchor.click();
            document.body.removeChild(anchor);
            URL.revokeObjectURL(url);
        } catch (error) {
            console.error('[Session] Failed to trigger download:', error);
        }
    }

    function getCurrentSourceConfigs() {
        const configs = app.registry?.models?.sourceConfigs;
        return Array.isArray(configs) ? configs : [];
    }

    function canonicalizeConfigs(configs) {
        if (!Array.isArray(configs)) {
            return '';
        }
        try {
            return configs
                .map(cfg => JSON.stringify(cfg ?? {}))
                .sort()
                .join('|');
        } catch (error) {
            console.warn('[Session] Unable to canonicalize source configs for comparison:', error);
            return '';
        }
    }

    function warnOnSourceMismatch(savedConfigs) {
        if (!Array.isArray(savedConfigs) || savedConfigs.length === 0) {
            return;
        }
        const currentKey = canonicalizeConfigs(getCurrentSourceConfigs());
        const savedKey = canonicalizeConfigs(savedConfigs);
        if (currentKey && savedKey && currentKey !== savedKey) {
            console.warn('[Session] Saved workspace references different source files than the ones currently loaded. Reload the matching data sources to ensure results are accurate before continuing.');
        }
    }

    function buildWorkspacePayload(state) {
        return {
            version: SESSION_FILE_VERSION,
            savedAt: new Date().toISOString(),
            sourceConfigs: getCurrentSourceConfigs(),
            appState: state,
        };
    }

    function saveWorkspace() {
        if (!app.store || typeof app.store.getState !== 'function') {
            console.error('[Session] Store not available; cannot save workspace.');
            return;
        }
        const state = app.store.getState();
        const payload = buildWorkspacePayload(state);
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const filename = `workspace-${timestamp}.json`;
        const jsonText = JSON.stringify(payload, null, 2);
        triggerJsonDownload(filename, jsonText);
    }

    function applyWorkspaceState(payload) {
        if (!payload || typeof payload !== 'object') {
            console.error('[Session] Invalid workspace payload.');
            return false;
        }

        if (!app.store || typeof app.store.dispatch !== 'function') {
            console.error('[Session] Store not available; cannot apply workspace.');
            return false;
        }

        if (!app.actions || typeof app.actions.rehydrateState !== 'function') {
            console.error('[Session] Rehydrate action is not available.');
            return false;
        }

        const nextState = payload.appState;
        if (!nextState || typeof nextState !== 'object') {
            console.error('[Session] Workspace payload missing appState.');
            return false;
        }

        warnOnSourceMismatch(payload.sourceConfigs);
        app.store.dispatch(app.actions.rehydrateState(nextState));
        return true;
    }

    function loadWorkspace() {
        const fileInput = document.createElement('input');
        fileInput.type = 'file';
        fileInput.accept = 'application/json';
        fileInput.addEventListener('change', event => {
            const file = event.target?.files?.[0];
            if (!file) {
                return;
            }

            const reader = new FileReader();
            reader.onload = () => {
                try {
                    const payload = JSON.parse(reader.result);
                    const applied = applyWorkspaceState(payload);
                    if (applied) {
                        console.info('[Session] Workspace restored successfully.');
                    }
                } catch (error) {
                    console.error('[Session] Failed to parse workspace file:', error);
                }
            };
            reader.readAsText(file);
        });
        fileInput.click();
    }

    function handleMenuAction(action) {
        switch (action) {
            case 'save':
                saveWorkspace();
                break;
            case 'load':
                loadWorkspace();
                break;
            case 'export_regions':
                if (app.regions && typeof app.regions.handleExport === 'function') {
                    app.regions.handleExport();
                } else {
                    console.error('[Session] Region export handler not available.');
                }
                break;
            case 'import_regions':
                if (app.regions && typeof app.regions.handleImport === 'function') {
                    app.regions.handleImport();
                } else {
                    console.error('[Session] Region import handler not available.');
                }
                break;
            default:
                console.warn('[Session] Unhandled session menu action:', action);
        }
    }

    function applyInitialWorkspaceState() {
        if (initialStateApplied) {
            return false;
        }
        const savedState = app.registry?.models?.savedWorkspaceState;
        if (!savedState || typeof savedState !== 'object') {
            return false;
        }
        const applied = applyWorkspaceState({
            appState: savedState,
            sourceConfigs: getCurrentSourceConfigs(),
        });
        if (applied) {
            initialStateApplied = true;
            app.registry.models.savedWorkspaceState = null;
        }
        return applied;
    }

    app.session = {
        saveWorkspace,
        loadWorkspace,
        handleMenuAction,
        applyWorkspaceState,
        applyInitialWorkspaceState,
    };
})(window.NoiseSurveyApp);
