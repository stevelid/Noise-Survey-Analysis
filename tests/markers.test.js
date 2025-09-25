import { describe, it, expect } from 'vitest';

import './loadCoreModules.js';

const { actions } = window.NoiseSurveyApp;
const {
    markersReducer,
    initialState: initialMarkersState
} = window.NoiseSurveyApp.features.markers;
const {
    formatMarkersCsv,
    parseMarkersCsv
} = window.NoiseSurveyApp.features.markers.utils;

describe('Marker reducer', () => {
    it('assigns metrics payload via MARKER_METRICS_SET', () => {
        let state = markersReducer(undefined, { type: '@@INIT' });
        state = markersReducer(state, actions.markerAdd(2500));
        const metricsPayload = {
            timestamp: 2500,
            parameter: 'LZeq',
            broadband: [{ positionId: 'P1', value: 48.2 }],
            spectral: [{ positionId: 'P1', labels: ['63'], values: [12.3] }]
        };
        state = markersReducer(state, actions.markerSetMetrics(1, metricsPayload));
        expect(state.byId[1].metrics).toEqual(metricsPayload);
    });

    it('MARKER_UPDATED normalises updates without mutating existing state', () => {
        let state = markersReducer(initialMarkersState, actions.markerAdd(1000));
        const original = state.byId[1];
        state = markersReducer(state, actions.markerUpdate(1, { note: 'Updated', color: '  #123456  ' }));
        expect(state.byId[1]).not.toBe(original);
        expect(state.byId[1].note).toBe('Updated');
        expect(state.byId[1].color).toBe('#123456');
    });
});

describe('Marker CSV helpers', () => {
    it('produces CSV with header when no markers present', () => {
        const csv = formatMarkersCsv({ markers: initialMarkersState });
        expect(csv.trim()).toBe('id,timestamp_ms,note,color,metrics_json,selected');
    });

    it('formats markers with JSON encoded metrics and selection flag', () => {
        const state = {
            markers: {
                ...initialMarkersState,
                byId: {
                    7: { id: 7, timestamp: 1234, note: 'alpha', color: '#ff0', metrics: { foo: 'bar' } }
                },
                allIds: [7],
                selectedId: 7
            }
        };
        const csv = formatMarkersCsv(state).split('\n');
        expect(csv).toHaveLength(2);
        expect(csv[1]).toContain('"{');
        expect(csv[1]).toContain(',true');
    });

    it('parses CSV rows with quoted values and metrics JSON', () => {
        const csv = [
            'id,timestamp_ms,note,color,metrics_json,selected',
            '5,2000,"Investigate, north fence",#00ff00,"{""broadband"": [1,2]}",true',
            ',invalid,"Ignore me",,#,',
            '8,2500,,,#,false'
        ].join('\n');
        const { markers, selectedId } = parseMarkersCsv(csv);
        expect(markers).toHaveLength(2);
        expect(markers[0]).toMatchObject({ id: 5, timestamp: 2000, note: 'Investigate, north fence', color: '#00ff00' });
        expect(markers[0].metrics).toEqual({ broadband: [1, 2] });
        expect(markers[1].id).toBe(8);
        expect(selectedId).toBe(5);
    });
});
