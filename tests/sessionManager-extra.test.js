import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

let app;
let session;

async function loadSessionManager() {
    vi.resetModules();
    document.body.innerHTML = '';
    window.NoiseSurveyApp = {
        dataCache: {},
        registry: {
            models: {
                sourceConfigs: []
            }
        },
        store: {
            dispatch: vi.fn(),
            getState: vi.fn(() => ({
                regions: { byId: {}, allIds: [] }
            }))
        },
        actions: {
            rehydrateState: vi.fn(state => ({ type: 'rehydrate', payload: state })),
            markersReplace: vi.fn(markers => ({ type: 'markers/replace', payload: markers })),
            regionReplaceAll: vi.fn(regions => ({ type: 'regions/replaceAll', payload: regions })),
            regionsAdded: vi.fn(regions => ({ type: 'regions/added', payload: regions }))
        },
        features: {
            regions: {
                selectors: {
                    selectAllRegions: vi.fn(() => [])
                },
                utils: {
                    getRegionMetrics: vi.fn(region => region?.metrics || null),
                    importRegions: vi.fn(() => []),
                    invalidateMetricsCache: vi.fn()
                }
            },
            markers: {
                selectors: {
                    selectAllMarkers: vi.fn(() => [])
                }
            }
        },
        regions: {
            invalidateMetricsCache: vi.fn()
        }
    };

    await import('../noise_survey_analysis/static/js/services/session/sessionManager.js');
    app = window.NoiseSurveyApp;
    session = app.session;
}

function interceptDownloads() {
    const originalCreateElement = document.createElement.bind(document);
    const anchors = [];
    const blobs = [];

    class MockBlob {
        constructor(parts) {
            this.parts = parts;
        }

        async text() {
            return this.parts.join('');
        }
    }

    vi.stubGlobal('Blob', MockBlob);
    if (typeof URL.createObjectURL !== 'function') {
        URL.createObjectURL = () => '';
    }
    if (typeof URL.revokeObjectURL !== 'function') {
        URL.revokeObjectURL = () => {};
    }

    vi.spyOn(URL, 'createObjectURL').mockImplementation(blob => {
        blobs.push(blob);
        return `blob:${blobs.length}`;
    });
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(document, 'createElement').mockImplementation(tagName => {
        const element = originalCreateElement(tagName);
        if (tagName === 'a') {
            element.click = vi.fn();
            anchors.push(element);
        }
        return element;
    });

    return { anchors, blobs };
}

function interceptFilePicker() {
    const originalCreateElement = document.createElement.bind(document);
    const inputs = [];

    class MockFileReader {
        constructor() {
            this.result = '';
            this.error = null;
            this.onload = null;
            this.onerror = null;
        }

        readAsText(file) {
            if (file.fail) {
                this.error = new Error('read failed');
                if (typeof this.onerror === 'function') {
                    this.onerror();
                }
                return;
            }

            this.result = file.contents;
            if (typeof this.onload === 'function') {
                this.onload();
            }
        }
    }

    vi.stubGlobal('FileReader', MockFileReader);
    vi.spyOn(document, 'createElement').mockImplementation(tagName => {
        if (tagName === 'input') {
            const listeners = {};
            const input = {
                type: '',
                accept: '',
                click: vi.fn(),
                addEventListener: vi.fn((eventName, handler) => {
                    listeners[eventName] = handler;
                }),
                triggerChange(event) {
                    listeners.change?.(event);
                }
            };
            inputs.push(input);
            return input;
        }
        return originalCreateElement(tagName);
    });

    return { inputs };
}

describe('NoiseSurveyApp.session extra flows', () => {
    beforeEach(async () => {
        vi.useFakeTimers();
        vi.restoreAllMocks();
        vi.spyOn(console, 'error').mockImplementation(() => {});
        vi.spyOn(console, 'warn').mockImplementation(() => {});
        vi.spyOn(console, 'info').mockImplementation(() => {});
        await loadSessionManager();
    });

    afterEach(() => {
        vi.runOnlyPendingTimers();
        vi.useRealTimers();
        vi.unstubAllGlobals();
        document.body.innerHTML = '';
    });

    it('saves workspace JSON and exports annotations CSV through downloads', async () => {
        const { anchors, blobs } = interceptDownloads();
        app.registry.models.sourceConfigs = [{ position_name: 'P1', file_path: 'a.csv' }];
        app.store.getState.mockReturnValue({ view: { selectedParameter: 'LAeq' } });

        session.saveWorkspace();

        expect(anchors).toHaveLength(1);
        expect(anchors[0].click).toHaveBeenCalledTimes(1);
        expect(anchors[0].download).toMatch(/^workspace-.*\.json$/);
        const workspacePayload = JSON.parse(await blobs[0].text());
        expect(workspacePayload).toMatchObject({
            version: 1,
            sourceConfigs: [{ position_name: 'P1', file_path: 'a.csv' }],
            appState: { view: { selectedParameter: 'LAeq' } }
        });
        expect(typeof workspacePayload.savedAt).toBe('string');

        app.features.markers.selectors.selectAllMarkers.mockReturnValue([
            { id: 1, positionId: 'P1', timestamp: Date.UTC(2024, 0, 1, 0, 0, 0), note: 'Marker' }
        ]);
        app.features.regions.selectors.selectAllRegions.mockReturnValue([
            { id: 2, positionId: 'P1', start: Date.UTC(2024, 0, 1, 1, 0, 0), end: Date.UTC(2024, 0, 1, 1, 5, 0), note: 'Region' }
        ]);

        session.handleExportCsv();

        expect(anchors).toHaveLength(2);
        expect(anchors[1].download).toMatch(/^annotations-.*\.csv$/);
        const csvText = await blobs[1].text();
        expect(csvText).toContain('marker');
        expect(csvText).toContain('region');
        expect(csvText).toContain('Marker');
        expect(csvText).toContain('Region');
    });

    it('applies workspace state, warns on source mismatch, and only restores initial state once', () => {
        const restoredState = {
            regions: {
                byId: {
                    4: { id: 4, positionId: 'P1', start: 1000, end: 2000 }
                },
                allIds: [4]
            }
        };
        const statusConnect = vi.fn();
        app.registry.models.sourceConfigs = [{ file_path: 'current.csv' }];
        app.registry.models.sessionStatusSource = { change: { connect: statusConnect }, data: {} };
        app.store.getState.mockReturnValue(restoredState);

        const applied = session.applyWorkspaceState({
            appState: restoredState,
            sourceConfigs: [{ file_path: 'saved.csv' }]
        });

        expect(applied).toBe(true);
        expect(console.warn).toHaveBeenCalledWith(
            '[Session] Saved workspace references different source files than the ones currently loaded. Reload the matching data sources to ensure results are accurate before continuing.'
        );
        expect(app.actions.rehydrateState).toHaveBeenCalledWith(restoredState);
        expect(app.store.dispatch).toHaveBeenCalledWith({
            type: 'rehydrate',
            payload: restoredState
        });
        expect(app.regions.invalidateMetricsCache).toHaveBeenCalledTimes(1);
        expect(app.features.regions.utils.getRegionMetrics).toHaveBeenCalledWith(
            restoredState.regions.byId[4],
            restoredState,
            app.dataCache,
            app.registry.models
        );

        app.registry.models.savedWorkspaceState = restoredState;
        const firstApply = session.applyInitialWorkspaceState();
        const secondApply = session.applyInitialWorkspaceState();

        expect(firstApply).toBe(true);
        expect(secondApply).toBe(false);
        expect(app.registry.models.savedWorkspaceState).toBeNull();
        expect(statusConnect).toHaveBeenCalledTimes(1);
    });

    it('requests static HTML export and reports server status updates once per timestamp', () => {
        let statusListener = null;
        app.registry.models.sessionActionSource = {
            data: {},
            change: { emit: vi.fn() }
        };
        app.registry.models.sessionStatusSource = {
            data: {},
            change: {
                connect: vi.fn(callback => {
                    statusListener = callback;
                })
            }
        };

        session.handleGenerateStaticHtml();

        expect(app.registry.models.sessionStatusSource.change.connect).toHaveBeenCalledTimes(1);
        expect(app.registry.models.sessionActionSource.data.command).toEqual(['generate_static_html']);
        expect(app.registry.models.sessionActionSource.data.payload).toEqual([null]);
        expect(app.registry.models.sessionActionSource.data.request_id[0]).toMatch(/^\d+-[0-9a-f]+$/);
        expect(app.registry.models.sessionActionSource.change.emit).toHaveBeenCalledTimes(1);
        expect(document.body.textContent).toContain('Static HTML export started');

        app.registry.models.sessionStatusSource.data = {
            updated_at: [101],
            level: ['warning'],
            done: [true],
            message: ['Export finished with warning']
        };
        statusListener();
        statusListener();

        expect(console.warn).toHaveBeenCalledWith('[Session]', 'Export finished with warning');
        const toastTexts = Array.from(document.querySelectorAll('#session-toast-container > div')).map(el => el.textContent);
        expect(toastTexts).toContain('Static HTML export started. You can keep using the dashboard.');
        expect(toastTexts).toContain('Export finished with warning');
        expect(toastTexts.filter(text => text === 'Export finished with warning')).toHaveLength(1);
    });

    it('loads a workspace file and dispatches the rehydrated state', () => {
        const { inputs } = interceptFilePicker();
        const restoredState = {
            markers: {
                byId: { 1: { id: 1, timestamp: 123 } },
                allIds: [1]
            }
        };
        app.store.getState.mockReturnValue({ regions: { byId: {}, allIds: [] } });

        session.loadWorkspace();

        expect(inputs).toHaveLength(1);
        expect(inputs[0].type).toBe('file');
        expect(inputs[0].accept).toBe('application/json');
        expect(inputs[0].click).toHaveBeenCalledTimes(1);

        inputs[0].triggerChange({
            target: {
                files: [{ name: 'workspace.json', contents: JSON.stringify({ appState: restoredState }) }]
            }
        });

        expect(app.actions.rehydrateState).toHaveBeenCalledWith(restoredState);
        expect(app.store.dispatch).toHaveBeenCalledWith({
            type: 'rehydrate',
            payload: restoredState
        });
        expect(console.info).toHaveBeenCalledWith('[Session] Workspace restored successfully.');
    });

    it('imports JSON annotations and CSV annotations through the file picker', () => {
        const { inputs } = interceptFilePicker();
        const importedRegion = {
            id: 2,
            positionId: 'P1',
            start: 1000,
            end: 2000,
            areas: [{ start: 1000, end: 2000 }]
        };
        app.features.regions.utils.importRegions.mockReturnValue([importedRegion]);
        app.store.getState.mockReturnValue({
            regions: {
                byId: { 2: importedRegion },
                allIds: [2]
            }
        });

        session.handleImportCsv();
        const jsonEventTarget = {
            files: [
                {
                    name: 'annotations.json',
                    contents: JSON.stringify({
                        markers: [{ id: 1, timestamp: 5000, note: 'JSON marker', color: '#123456', positionId: 'P1' }],
                        regions: [{ id: 2, positionId: 'P1', start: 1000, end: 2000, note: 'JSON region' }]
                    })
                }
            ],
            value: 'selected'
        };
        inputs[0].triggerChange({ target: jsonEventTarget });

        expect(app.actions.markersReplace).toHaveBeenCalledWith([
            { id: 1, timestamp: 5000, note: 'JSON marker', color: '#123456', positionId: 'P1' }
        ]);
        expect(app.actions.regionsAdded).toHaveBeenCalledWith([importedRegion]);
        expect(app.store.dispatch).toHaveBeenCalledWith({
            type: 'markers/replace',
            payload: [{ id: 1, timestamp: 5000, note: 'JSON marker', color: '#123456', positionId: 'P1' }]
        });
        expect(app.store.dispatch).toHaveBeenCalledWith({
            type: 'regions/added',
            payload: [importedRegion]
        });
        expect(app.features.regions.utils.invalidateMetricsCache).toHaveBeenCalledTimes(1);
        expect(app.features.regions.utils.getRegionMetrics).toHaveBeenCalledWith(
            importedRegion,
            app.store.getState.mock.results.at(-1).value,
            app.dataCache,
            app.registry.models
        );
        expect(jsonEventTarget.value).toBe('');

        app.store.dispatch.mockClear();
        app.actions.markersReplace.mockClear();
        app.actions.regionReplaceAll.mockClear();
        app.regions.invalidateMetricsCache.mockClear();

        session.handleImportCsv();
        const csvText = [
            session.__testHelpers.CSV_HEADER.join(','),
            'marker,3,P2,2024-03-10 09:08:07,,CSV marker,#abcdef,',
            'region,4,P2,2024-03-10 09:00:00,2024-03-10 09:30:00,CSV region,#fedcba,'
        ].join('\n');
        const csvEventTarget = {
            files: [{ name: 'annotations.csv', contents: csvText }],
            value: 'selected'
        };
        inputs[1].triggerChange({ target: csvEventTarget });

        expect(app.actions.markersReplace).toHaveBeenCalledWith([
            { id: 3, positionId: 'P2', timestamp: Date.UTC(2024, 2, 10, 9, 8, 7), note: 'CSV marker', color: '#abcdef' }
        ]);
        expect(app.actions.regionReplaceAll).toHaveBeenCalledWith([
            {
                id: 4,
                positionId: 'P2',
                start: Date.UTC(2024, 2, 10, 9, 0, 0),
                end: Date.UTC(2024, 2, 10, 9, 30, 0),
                areas: [{ start: Date.UTC(2024, 2, 10, 9, 0, 0), end: Date.UTC(2024, 2, 10, 9, 30, 0) }],
                note: 'CSV region',
                color: '#fedcba'
            }
        ]);
        expect(app.regions.invalidateMetricsCache).toHaveBeenCalledTimes(1);
        expect(csvEventTarget.value).toBe('');
    });
});
