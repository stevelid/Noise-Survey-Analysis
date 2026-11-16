// Browser audio backend: the shared store -> command mapping and the in-page clip player.
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import './loadCoreModules.js';

const app = window.NoiseSurveyApp;

function flush() {
    return new Promise(resolve => setTimeout(resolve, 0));
}

class FakeAudio {
    constructor() {
        this.src = '';
        this.currentTime = 0;
        this.playbackRate = 1;
        this.readyState = 1;
        this.duration = 60;
        this.paused = true;
        this.preload = '';
        this.listeners = {};
        FakeAudio.instances.push(this);
    }
    play() { this.paused = false; return Promise.resolve(); }
    pause() { this.paused = true; }
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
    removeEventListener(type, fn) { this.listeners[type] = (this.listeners[type] || []).filter(f => f !== fn); }
    removeAttribute() { this.src = ''; }
    load() {}
    fire(type) { (this.listeners[type] || []).slice().forEach(fn => fn()); }
}
FakeAudio.instances = [];

class FakeAudioContext {
    constructor() {
        this.state = 'running';
        this.destination = {};
        FakeAudioContext.last = this;
    }
    createGain() { return { gain: { value: 1 }, connect() {} }; }
    createDynamicsCompressor() {
        const param = () => ({ value: 0 });
        return { threshold: param(), knee: param(), ratio: param(), attack: param(), release: param(), connect() {} };
    }
    createWaveShaper() { return { curve: null, connect() {} }; }
    createMediaElementSource() { return { connect() {}, disconnect() {} }; }
    resume() { return Promise.resolve(); }
}

function clipResponse(startMs, durationMs = 60000) {
    const headers = {
        'Content-Type': 'audio/wav',
        'X-Clip-Start-Ms': String(startMs),
        'X-Clip-Duration-Ms': String(durationMs),
        'X-Clip-Frames': String(Math.round(durationMs / 1000 * 48000)),
        'X-Sample-Rate': '48000',
        'X-File-Name': 'rec.wav',
        'X-File-Start-Ms': String(startMs - 5000)
    };
    return {
        status: 200,
        ok: true,
        headers: { get: name => headers[name] ?? null },
        blob: async () => ({ size: 1234 })
    };
}

function playState({ tapMs, position = 'P1', offsets = {}, playing = false, rate = 1, boost = false }) {
    return {
        system: { lastAction: { type: app.actionTypes.AUDIO_PLAY_PAUSE_TOGGLE, payload: { positionId: position, isActive: true } } },
        interaction: { tap: { isActive: true, timestamp: tapMs, position } },
        view: { positionEffectiveOffsets: offsets },
        audio: { isPlaying: playing, activePositionId: position, playbackRate: rate, volumeBoost: boost },
        regions: { byId: {} }
    };
}

describe('deriveAudioCommand (shared by VLC and browser backends)', () => {
    const derive = (current, previous) => app.services.audio.deriveAudioCommand(current, previous);

    it('play subtracts the effective offset, exactly like the VLC path', () => {
        const current = playState({ tapMs: 100000, offsets: { P1: 2500 } });
        expect(derive(current, playState({ tapMs: 0 }))).toEqual({ command: 'play', position_id: 'P1', value: 97500 });
    });

    it('a tap while playing replays at the tapped time; a tap while stopped does nothing', () => {
        const tap = { type: app.actionTypes.TAP, payload: {} };
        const current = { ...playState({ tapMs: 50000, offsets: { P1: -1000 } }), system: { lastAction: tap } };
        expect(derive(current, playState({ tapMs: 0, playing: true })).value).toBe(51000);
        expect(derive(current, playState({ tapMs: 0, playing: false }))).toBeNull();
    });

    it('maps pause, rate and boost', () => {
        const prev = playState({ tapMs: 0, playing: true });
        const pause = { ...prev, system: { lastAction: { type: app.actionTypes.AUDIO_PLAY_PAUSE_TOGGLE, payload: { positionId: 'P1', isActive: false } } } };
        expect(derive(pause, prev).command).toBe('pause');
        const rate = { ...prev, audio: { ...prev.audio, playbackRate: 2 }, system: { lastAction: { type: app.actionTypes.AUDIO_RATE_CHANGE_REQUEST } } };
        expect(derive(rate, prev)).toEqual({ command: 'set_rate', position_id: 'P1', value: 2 });
        const boost = { ...prev, audio: { ...prev.audio, volumeBoost: true }, system: { lastAction: { type: app.actionTypes.AUDIO_BOOST_TOGGLE_REQUEST } } };
        expect(derive(boost, prev)).toEqual({ command: 'toggle_boost', position_id: 'P1', value: true });
    });
});

describe('clipPlayer (browser backend)', () => {
    const player = () => app.services.audio.clipPlayer;
    let savedRegistry;
    let savedStore;
    let savedThunk;
    let dispatched;

    beforeEach(() => {
        FakeAudio.instances = [];
        savedRegistry = app.registry;
        savedStore = app.store;
        savedThunk = app.thunks && app.thunks.handleAudioStatusUpdateIntent;
        dispatched = [];
        app.registry = {
            models: {
                config: { server_mode: true },
                audio_control_source: { data: {} },
                audio_backend_source: { data: { backend: ['vlc'], base_url: ['http://127.0.0.1:5555'], token: ['tok'], clip_seconds: [60] } }
            }
        };
        app.store = { dispatch: vi.fn(), getState: () => playState({ tapMs: 0 }) };
        app.thunks = app.thunks || {};
        app.thunks.handleAudioStatusUpdateIntent = (payload, options) => {
            dispatched.push({ payload, options });
            return { type: 'test/status' };
        };
        vi.stubGlobal('Audio', FakeAudio);
        vi.stubGlobal('AudioContext', FakeAudioContext);
        vi.stubGlobal('fetch', vi.fn(async url => {
            const start = Number(new URL(url).searchParams.get('start_ms'));
            return clipResponse(start);
        }));
        if (!URL.createObjectURL) URL.createObjectURL = () => 'blob:x';
        if (!URL.revokeObjectURL) URL.revokeObjectURL = () => {};
        try { window.localStorage.removeItem('nsa.audioBackend'); } catch (e) { /* ignore */ }
        player()._reset();
    });

    afterEach(() => {
        player()._reset();
        app.registry = savedRegistry;
        app.store = savedStore;
        if (savedThunk) app.thunks.handleAudioStatusUpdateIntent = savedThunk;
        vi.unstubAllGlobals();
        try { window.localStorage.removeItem('nsa.audioBackend'); } catch (e) { /* ignore */ }
    });

    it('defaults to the configured backend (vlc) and switches to browser on request', () => {
        expect(player().getBackend()).toBe('vlc');
        player().setBackend('browser');
        expect(player().isBrowserBackend()).toBe(true);
        expect(window.localStorage.getItem('nsa.audioBackend')).toBe('browser');
    });

    it('static HTML is always the browser backend', () => {
        app.registry.models.config.server_mode = false;
        expect(player().getBackend()).toBe('browser');
    });

    it('play fetches a 60 s clip at the audio time, seeks into it and reports status', async () => {
        player().setBackend('browser');
        const state = playState({ tapMs: 1_000_000, offsets: { P1: 2000 } });
        const cmd = app.services.audio.deriveAudioCommand(state, playState({ tapMs: 0 }));
        // Server snaps to a clip that starts 10 s before the requested time.
        fetch.mockImplementationOnce(async () => clipResponse(cmd.value - 10000));
        player().execute(cmd, state);
        await flush();

        const url = new URL(fetch.mock.calls[0][0]);
        expect(url.origin + url.pathname).toBe('http://127.0.0.1:5555/clip');
        expect(url.searchParams.get('pos')).toBe('P1');
        expect(Number(url.searchParams.get('start_ms'))).toBe(998000);
        expect(url.searchParams.get('dur_s')).toBe('60');
        expect(url.searchParams.get('token')).toBe('tok');

        const el = FakeAudio.instances[0];
        expect(el.currentTime).toBeCloseTo(10, 5);
        expect(el.paused).toBe(false);
        const last = dispatched[dispatched.length - 1];
        expect(last.options).toEqual({ fromBrowser: true });
        expect(last.payload.is_playing[0]).toBe(true);
        expect(last.payload.active_position_id[0]).toBe('P1');
        expect(last.payload.current_time[0]).toBe(998000);
    });

    it('a second play inside the loaded chunk seeks without refetching', async () => {
        player().setBackend('browser');
        player().execute({ command: 'play', position_id: 'P1', value: 500000 }, playState({ tapMs: 0 }));
        await flush();
        player().execute({ command: 'play', position_id: 'P1', value: 530000 }, playState({ tapMs: 0 }));
        await flush();
        expect(fetch).toHaveBeenCalledTimes(1);
        expect(FakeAudio.instances[0].currentTime).toBeCloseTo(30, 5);
    });

    it('switching position fetches the other position at the same instant', async () => {
        player().setBackend('browser');
        player().execute({ command: 'play', position_id: 'P1', value: 500000 }, playState({ tapMs: 0 }));
        await flush();
        player().execute({ command: 'play', position_id: 'P2', value: 500000 }, playState({ tapMs: 0, position: 'P2' }));
        await flush();
        expect(fetch).toHaveBeenCalledTimes(2);
        const second = new URL(fetch.mock.calls[1][0]);
        expect(second.searchParams.get('pos')).toBe('P2');
        expect(second.searchParams.get('start_ms')).toBe('500000');
        expect(player().debug().positionId).toBe('P2');
    });

    it('Boost sets a real +20 dB gain and rate sets the native playbackRate', async () => {
        player().setBackend('browser');
        player().execute({ command: 'play', position_id: 'P1', value: 500000 }, playState({ tapMs: 0 }));
        await flush();
        expect(player().debug().gain).toBe(1);
        player().execute({ command: 'toggle_boost', position_id: 'P1', value: true });
        expect(player().debug().gain).toBeCloseTo(10, 6);
        player().execute({ command: 'set_rate', position_id: 'P1', value: 2 });
        expect(FakeAudio.instances[0].playbackRate).toBe(2);
        player().execute({ command: 'pause', position_id: 'P1', value: null });
        expect(FakeAudio.instances[0].paused).toBe(true);
        expect(dispatched[dispatched.length - 1].payload.is_playing[0]).toBe(false);
    });

    it('preloads the next chunk near the end and continues into it', async () => {
        player().setBackend('browser');
        player().execute({ command: 'play', position_id: 'P1', value: 500000 }, playState({ tapMs: 0 }));
        await flush();
        const el = FakeAudio.instances[0];
        el.currentTime = 50;   // 10 s left, inside the preload window
        await new Promise(resolve => setTimeout(resolve, 260));   // one 200 ms status tick
        await flush();
        expect(fetch).toHaveBeenCalledTimes(2);
        expect(new URL(fetch.mock.calls[1][0]).searchParams.get('start_ms')).toBe('560000');
        el.fire('ended');
        expect(player().debug().chunk.startMs).toBe(560000);
    });

    it('server status patches are ignored while the browser backend is active', () => {
        const thunks = app.features.audio.thunks;
        const dispatch = vi.fn();
        const getState = () => playState({ tapMs: 0 });
        player().setBackend('browser');
        thunks.handleAudioStatusUpdateIntent({ is_playing: [false], active_position_id: ['P1'] })(dispatch, getState);
        expect(dispatch).not.toHaveBeenCalled();
        thunks.handleAudioStatusUpdateIntent({ is_playing: [true], active_position_id: ['P1'] }, { fromBrowser: true })(dispatch, getState);
        expect(dispatch).toHaveBeenCalledTimes(1);
    });

    it('static HTML plays the exported clip of the region under the tap', async () => {
        app.registry.models.config.server_mode = false;
        const state = playState({ tapMs: 0, offsets: { P1: 1000 } });
        state.regions = { byId: { r1: { id: 'r1', start: 100000, end: 130000, audioClips: { P1: 'x_clips/region_r1_P1.wav' } } } };
        expect(player().hasStaticClips(state)).toBe(true);
        // Audio time 110000 + offset 1000 = display 111000, inside the region.
        player().execute({ command: 'play', position_id: 'P1', value: 110000 }, state);
        await flush();
        expect(fetch).not.toHaveBeenCalled();
        const el = FakeAudio.instances[0];
        expect(el.src).toBe('x_clips/region_r1_P1.wav');
        // Region starts at display 100000 = audio 99000, so the playhead is 11 s in.
        expect(el.currentTime).toBeCloseTo(11, 5);
    });
});
