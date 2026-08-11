import { describe, it, expect } from 'vitest';

import './loadCoreModules.js';

const utils = window.NoiseSurveyApp.features.classifications.utils;

describe('classification utils', () => {
    it('parses classifier CSV with timestamp aliases', () => {
        const csv = [
            'position_id,source_id,source_label,start_utc,end_utc,state,confidence,description,audio_file,color',
            'P1,fan,Extract fan,2026-06-20 13:05:10,2026-06-20 13:22:40,on,0.91,"steady, tonal fan",audio_001.wav,#e4572e'
        ].join('\n');

        const rows = utils.parseClassificationsCsv(csv);
        expect(rows).toHaveLength(1);
        expect(rows[0]).toMatchObject({
            positionId: 'P1',
            sourceId: 'fan',
            sourceLabel: 'Extract fan',
            state: 'on',
            confidence: '0.91',
            description: 'steady, tonal fan',
            audioFile: 'audio_001.wav',
            color: '#e4572e'
        });
        expect(rows[0].start).toBe(Date.UTC(2026, 5, 20, 13, 5, 10));
        expect(rows[0].end).toBe(Date.UTC(2026, 5, 20, 13, 22, 40));
    });

    it('reads classifications from supported JSON shapes', () => {
        expect(utils.parseClassificationsJson(JSON.stringify({
            classifications: [{ positionId: 'P1', sourceId: 'fan', start: 1, end: 2 }]
        }))).toHaveLength(1);

        expect(utils.parseClassificationsJson(JSON.stringify({
            annotations: [
                { type: 'classification', data: { positionId: 'P2', sourceId: 'music', start: 3, end: 4 } },
                { type: 'region', positionId: 'P2', start: 3, end: 4 }
            ]
        }))).toEqual([{ positionId: 'P2', sourceId: 'music', start: 3, end: 4 }]);
    });

    it('exports classifier CSV with ISO timestamps', () => {
        const csv = utils.buildClassificationsCsv([
            { positionId: 'P1', sourceId: 'fan', sourceLabel: 'Fan', start: 1000, end: 2000, state: 'on', confidence: 0.5 }
        ]);
        expect(csv).toContain('position_id,source_id,source_label,start,end,state,confidence,description,audio_file,color');
        expect(csv).toContain('1970-01-01T00:00:01.000Z');
        expect(csv).toContain('1970-01-01T00:00:02.000Z');
    });
});
