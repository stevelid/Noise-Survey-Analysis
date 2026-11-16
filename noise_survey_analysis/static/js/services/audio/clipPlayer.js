// noise_survey_analysis/static/js/services/audio/clipPlayer.js

/**
 * @fileoverview In-page audio playback (the 'browser' audio backend).
 *
 * Live dashboard: fetches 60 s mono PCM WAV chunks from the localhost media server
 * (core/media_server.py), `GET /clip?pos=&start_ms=&dur_s=&token=`, and plays them through an
 * HTMLAudioElement routed into a Web Audio graph:
 *     element -> GainNode (Boost = real +20 dB) -> compressor (limiter while boosted)
 *             -> soft clipper -> destination.
 * Speed is the element's native `playbackRate`. The next chunk is fetched while the current one
 * plays, and a tap inside the chunk seeks the element without refetching. Switching position
 * fetches the other position's clip at the same time.
 *
 * Static HTML: regions exported with `--audio-clips` carry `audioClips: {position: url}`; a tap
 * inside such a region plays that clip through the same player.
 *
 * Times: everything here is *audio time* (chart time - effective offset), the same value the
 * VLC path sends in its 'play' command (see audioCommands.js). Status is reported through the
 * existing `audioStatusUpdate` action (via handleAudioStatusUpdateIntent, which adds the offset
 * back), so the cursor, Play button and position switching are unchanged.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const BOOST_DB = 20;
    const BOOST_GAIN = Math.pow(10, BOOST_DB / 20);
    const DEFAULT_CLIP_SECONDS = 60;
    const PRELOAD_AHEAD_SECONDS = 15;
    const REPORT_INTERVAL_MS = 200;
    const STORAGE_KEY = 'nsa.audioBackend';
    const BACKEND_TOGGLE_NAME = 'global_audio_backend_toggle';
    const REQUEST_LOG_LIMIT = 30;

    let backend = null;              // 'vlc' | 'browser', resolved lazily
    let configTried = false;
    let config = { baseUrl: '', token: '', clipSeconds: DEFAULT_CLIP_SECONDS };

    // Web Audio graph (created on first playback, which is always inside a user gesture).
    let ctx = null;
    let gainNode = null;
    let compressor = null;
    let graphFailed = false;

    const player = {
        positionId: null,
        rate: 1,
        boost: false,
        playing: false,
        cur: null,
        next: null,
        nextLoading: false,
        timer: null,
        seq: 0
    };
    const requestLog = [];

    // ------------------------------------------------------------------ environment

    function getModels() {
        return (app.registry && app.registry.models) || {};
    }

    function isStaticMode() {
        return getModels().config?.server_mode === false;
    }

    function usesFileProtocol() {
        try { return window.location.protocol === 'file:'; } catch (e) { return false; }
    }

    function readStoredBackend() {
        try {
            const value = window.localStorage.getItem(STORAGE_KEY);
            return value === 'browser' || value === 'vlc' ? value : null;
        } catch (e) { return null; }
    }

    function storeBackend(value) {
        try { window.localStorage.setItem(STORAGE_KEY, value); } catch (e) { /* private window etc. */ }
    }

    function findModelByName(name) {
        try {
            const doc = window.Bokeh && window.Bokeh.documents && window.Bokeh.documents[0];
            return doc && typeof doc.get_model_by_name === 'function' ? doc.get_model_by_name(name) : null;
        } catch (e) { return null; }
    }

    /** Read the media server address/token and the starting backend from audio_backend_source. */
    function ensureConfig() {
        if (configTried) return;
        const source = getModels().audio_backend_source || findModelByName('audio_backend_source');
        const documentReady = Boolean(window.Bokeh && window.Bokeh.documents && window.Bokeh.documents[0]);
        if (!source && !documentReady) return;   // too early: try again on the next call
        configTried = true;
        const data = source && source.data;
        const first = key => (Array.isArray(data?.[key]) ? data[key][0] : null);
        if (data) {
            config = {
                baseUrl: String(first('base_url') || ''),
                token: String(first('token') || ''),
                clipSeconds: Number(first('clip_seconds')) > 0 ? Number(first('clip_seconds')) : DEFAULT_CLIP_SECONDS
            };
            const configured = first('backend');
            if (backend === null) {
                backend = readStoredBackend() || (configured === 'browser' ? 'browser' : 'vlc');
            }
        }
        if (backend === null) backend = readStoredBackend() === 'browser' && data ? 'browser' : 'vlc';
        syncBackendToggle();
    }

    function getBackend() {
        if (isStaticMode()) return 'browser';
        if (!configTried) ensureConfig();
        return backend || 'vlc';
    }

    function isBrowserBackend() {
        return getBackend() === 'browser';
    }

    function syncBackendToggle() {
        const toggle = findModelByName(BACKEND_TOGGLE_NAME);
        if (!toggle) return;
        const wantActive = backend === 'browser';
        if (toggle.active !== wantActive) toggle.active = wantActive;
        const label = wantActive ? 'Audio: Browser' : 'Audio: VLC';
        if (toggle.label !== label) toggle.label = label;
    }

    // ------------------------------------------------------------------ status reporting

    function dispatchStatus(payload) {
        const store = app.store;
        const thunk = app.thunks && app.thunks.handleAudioStatusUpdateIntent;
        if (!store || typeof store.dispatch !== 'function' || typeof thunk !== 'function') return;
        store.dispatch(thunk(payload, { fromBrowser: true }));
    }

    function report(overrides) {
        const cur = player.cur;
        const currentMs = cur && cur.el ? cur.startMs + (cur.el.currentTime || 0) * 1000 : 0;
        dispatchStatus(Object.assign({
            is_playing: [Boolean(player.playing)],
            current_time: [currentMs],
            playback_rate: [player.rate],
            current_file_duration: [cur ? cur.durMs / 1000 : 0],
            current_file_start_time: [cur ? cur.fileStartMs : 0],
            active_position_id: [player.positionId],
            volume_boost: [Boolean(player.boost)],
            current_file_name: [cur ? cur.fileName : '']
        }, overrides || {}));
    }

    function startTimer() {
        if (player.timer !== null) return;
        player.timer = window.setInterval(tick, REPORT_INTERVAL_MS);
    }

    function stopTimer() {
        if (player.timer === null) return;
        window.clearInterval(player.timer);
        player.timer = null;
    }

    function tick() {
        const cur = player.cur;
        if (!player.playing || !cur || !cur.el) {
            stopTimer();
            return;
        }
        report();
        maybePreloadNext();
    }

    // ------------------------------------------------------------------ Web Audio graph

    function softClipCurve() {
        // Transparent below 0.85, then a smooth knee that settles at +/-1 so a boosted peak
        // that slips past the compressor cannot hard-clip.
        const size = 2048;
        const curve = new Float32Array(size);
        const knee = 0.85;
        for (let i = 0; i < size; i += 1) {
            const x = (i / (size - 1)) * 2 - 1;
            const a = Math.abs(x);
            const y = a <= knee ? a : knee + (1 - knee) * Math.tanh((a - knee) / (1 - knee));
            curve[i] = Math.sign(x) * y;
        }
        return curve;
    }

    function ensureGraph() {
        if (ctx || graphFailed) return Boolean(ctx);
        try {
            const Context = window.AudioContext || window.webkitAudioContext;
            if (!Context) throw new Error('Web Audio unavailable');
            ctx = new Context();
            gainNode = ctx.createGain();
            compressor = ctx.createDynamicsCompressor();
            const shaper = ctx.createWaveShaper();
            shaper.curve = softClipCurve();
            gainNode.connect(compressor);
            compressor.connect(shaper);
            shaper.connect(ctx.destination);
            applyGain();
        } catch (error) {
            graphFailed = true;
            ctx = null;
            console.warn('[ClipPlayer] Web Audio graph unavailable; playing without Boost.', error);
        }
        return Boolean(ctx);
    }

    function applyGain() {
        if (!gainNode) return;
        gainNode.gain.value = player.boost ? BOOST_GAIN : 1;
        // The compressor only works as a limiter while boosted; otherwise it is transparent.
        compressor.threshold.value = player.boost ? -10 : 0;
        compressor.knee.value = player.boost ? 6 : 0;
        compressor.ratio.value = player.boost ? 20 : 1;
        compressor.attack.value = 0.002;
        compressor.release.value = 0.15;
    }

    function connectElement(chunk) {
        // File URLs taint the element for Web Audio (silence), so they play without the graph.
        if (chunk.source || chunk.noGraph || !ensureGraph()) return;
        try {
            chunk.source = ctx.createMediaElementSource(chunk.el);
            chunk.source.connect(gainNode);
        } catch (error) {
            console.warn('[ClipPlayer] Could not route a clip through Web Audio.', error);
        }
    }

    // ------------------------------------------------------------------ chunks

    function logRequest(entry) {
        requestLog.push(Object.assign({ at: Date.now() }, entry));
        while (requestLog.length > REQUEST_LOG_LIMIT) requestLog.shift();
    }

    function makeChunk(fields) {
        const el = new Audio();
        el.preload = 'auto';
        el.playbackRate = player.rate;
        const chunk = Object.assign({ el, source: null, objectUrl: null, noGraph: false }, fields);
        el.src = chunk.src;
        el.addEventListener('ended', () => onChunkEnded(chunk));
        el.addEventListener('error', () => onChunkError(chunk));
        return chunk;
    }

    function waitForMetadata(chunk) {
        const el = chunk.el;
        if (el.readyState >= 1) return Promise.resolve();
        return new Promise((resolve, reject) => {
            const done = () => { cleanup(); resolve(); };
            const fail = () => { cleanup(); reject(new Error('clip failed to load')); };
            const cleanup = () => {
                el.removeEventListener('loadedmetadata', done);
                el.removeEventListener('error', fail);
            };
            el.addEventListener('loadedmetadata', done);
            el.addEventListener('error', fail);
        });
    }

    function disposeChunk(chunk) {
        if (!chunk) return;
        try { chunk.el.pause(); } catch (e) { /* ignore */ }
        try { if (chunk.source) chunk.source.disconnect(); } catch (e) { /* ignore */ }
        try { chunk.el.removeAttribute('src'); chunk.el.load(); } catch (e) { /* ignore */ }
        if (chunk.objectUrl) {
            try { URL.revokeObjectURL(chunk.objectUrl); } catch (e) { /* ignore */ }
        }
        chunk.disposed = true;
    }

    function clipUrl(positionId, startMs, durSeconds) {
        const query = new URLSearchParams({
            pos: positionId,
            start_ms: String(Math.round(startMs)),
            dur_s: String(durSeconds),
            token: config.token
        });
        return `${config.baseUrl}/clip?${query.toString()}`;
    }

    /** Fetch one live chunk. Resolves null when the server has no audio there. */
    async function loadLiveChunk(positionId, startMs) {
        ensureConfig();
        if (!config.baseUrl || !config.token) {
            throw new Error('media server is not configured');
        }
        const url = clipUrl(positionId, startMs, config.clipSeconds);
        const response = await fetch(url, { mode: 'cors' });
        const entry = {
            url,
            positionId,
            requestedStartMs: Math.round(startMs),
            status: response.status,
            contentType: response.headers.get('Content-Type')
        };
        if (response.status === 404) {
            logRequest(entry);
            return null;
        }
        if (!response.ok) {
            logRequest(entry);
            throw new Error(`media server answered ${response.status}`);
        }
        const header = name => Number(response.headers.get(name));
        const blob = await response.blob();
        Object.assign(entry, {
            startMs: header('X-Clip-Start-Ms'),
            durationMs: header('X-Clip-Duration-Ms'),
            frames: header('X-Clip-Frames'),
            sampleRate: header('X-Sample-Rate'),
            bytes: blob.size
        });
        logRequest(entry);
        const objectUrl = URL.createObjectURL(blob);
        const chunk = makeChunk({
            positionId,
            src: objectUrl,
            objectUrl,
            startMs: entry.startMs,
            durMs: entry.durationMs,
            frames: entry.frames,
            sampleRate: entry.sampleRate,
            fileName: response.headers.get('X-File-Name') || '',
            fileStartMs: header('X-File-Start-Ms') || entry.startMs,
            short: entry.durationMs < config.clipSeconds * 1000 - 250   // ran into the end of the audio
        });
        await waitForMetadata(chunk);
        return chunk;
    }

    function regionBounds(region) {
        const areas = Array.isArray(region?.areas) && region.areas.length
            ? region.areas
            : [{ start: region?.start, end: region?.end }];
        let start = Infinity;
        let end = -Infinity;
        areas.forEach(area => {
            const s = Number(area?.start);
            const e = Number(area?.end);
            if (Number.isFinite(s)) start = Math.min(start, s);
            if (Number.isFinite(e)) end = Math.max(end, e);
        });
        return Number.isFinite(start) && Number.isFinite(end) && end > start ? { start, end } : null;
    }

    /** Static HTML: the exported clip of the region containing this audio time, if any. */
    function findStaticClip(state, positionId, audioTimeMs) {
        const offset = Number(state?.view?.positionEffectiveOffsets?.[positionId]) || 0;
        const displayMs = audioTimeMs + offset;
        const regions = state?.regions?.byId || {};
        for (const id of Object.keys(regions)) {
            const region = regions[id];
            const url = region?.audioClips?.[positionId];
            if (!url) continue;
            const bounds = regionBounds(region);
            if (bounds && displayMs >= bounds.start && displayMs <= bounds.end) {
                return { url, startMs: bounds.start - offset, durMs: bounds.end - bounds.start, regionId: id };
            }
        }
        return null;
    }

    function hasStaticClips(state) {
        const regions = (state || (app.store && app.store.getState && app.store.getState()))?.regions?.byId || {};
        return Object.keys(regions).some(id => {
            const clips = regions[id]?.audioClips;
            return clips && typeof clips === 'object' && Object.keys(clips).length > 0;
        });
    }

    async function loadStaticChunk(state, positionId, audioTimeMs) {
        const found = findStaticClip(state, positionId, audioTimeMs);
        if (!found) return null;
        logRequest({ url: found.url, positionId, status: 'static', requestedStartMs: Math.round(audioTimeMs) });
        const chunk = makeChunk({
            positionId,
            src: found.url,
            startMs: found.startMs,
            durMs: found.durMs,
            frames: null,
            sampleRate: null,
            fileName: String(found.url).split('/').pop(),
            fileStartMs: found.startMs,
            noGraph: usesFileProtocol(),
            short: true   // a clip is the whole story; there is no following chunk
        });
        await waitForMetadata(chunk);
        if (Number.isFinite(chunk.el.duration) && chunk.el.duration > 0) {
            chunk.durMs = chunk.el.duration * 1000;
        }
        return chunk;
    }

    // ------------------------------------------------------------------ transport

    function startChunk(chunk, offsetMs) {
        player.cur = chunk;
        connectElement(chunk);
        chunk.el.playbackRate = player.rate;
        try {
            chunk.el.currentTime = Math.max(0, offsetMs) / 1000;
        } catch (e) { /* metadata not ready; starts at 0 */ }
        applyGain();
        if (ctx && ctx.state === 'suspended') {
            ctx.resume().catch(() => { /* autoplay policy; the play() below reports it */ });
        }
        const promise = chunk.el.play();
        player.playing = true;
        startTimer();
        report();
        if (promise && typeof promise.catch === 'function') {
            promise.catch(error => {
                if (chunk !== player.cur || chunk.disposed) return;
                if (error && error.name === 'AbortError') return;   // pause()/seek raced the start; not a refusal
                console.warn('[ClipPlayer] Browser refused to start playback.', error);
                player.playing = false;
                stopTimer();
                report();
            });
        }
    }

    async function play(positionId, audioTimeMs, state) {
        player.seq += 1;
        const audioState = state && state.audio;
        if (audioState) {
            player.rate = Number(audioState.playbackRate) > 0 ? Number(audioState.playbackRate) : 1;
            player.boost = Boolean(audioState.volumeBoost);
        }
        const cur = player.cur;
        const sameChunk = cur && !cur.disposed && cur.positionId === positionId
            && audioTimeMs >= cur.startMs && audioTimeMs < cur.startMs + cur.durMs - 100;

        player.positionId = positionId;
        if (sameChunk) {
            // Tap inside the chunk that is already loaded: just move the playhead.
            startChunk(cur, audioTimeMs - cur.startMs);
            return;
        }

        stopPlayback({ keepPosition: true });   // bumps player.seq, cancelling older loads
        const seq = player.seq;
        try {
            const chunk = isStaticMode()
                ? await loadStaticChunk(state, positionId, audioTimeMs)
                : await loadLiveChunk(positionId, audioTimeMs);
            if (seq !== player.seq) {
                disposeChunk(chunk);
                return;
            }
            if (!chunk) {
                console.info(`[ClipPlayer] No audio for ${positionId} at ${new Date(audioTimeMs).toISOString()}`);
                player.playing = false;
                report({ current_time: [0] });
                return;
            }
            startChunk(chunk, Math.max(0, audioTimeMs - chunk.startMs));
        } catch (error) {
            if (seq !== player.seq) return;
            console.warn('[ClipPlayer] Could not load audio.', error);
            player.playing = false;
            report({ current_time: [0] });
        }
    }

    function pause() {
        player.seq += 1;
        const cur = player.cur;
        if (cur && cur.el) {
            try { cur.el.pause(); } catch (e) { /* ignore */ }
        }
        player.playing = false;
        stopTimer();
        report();
    }

    function stopPlayback(options) {
        player.seq += 1;
        stopTimer();
        disposeChunk(player.next);
        player.next = null;
        player.nextLoading = false;
        disposeChunk(player.cur);
        player.cur = null;
        player.playing = false;
        if (!options || !options.keepPosition) player.positionId = null;
    }

    /** Stop and tell the UI nothing is playing (backend switch, page hide). */
    function stop() {
        const wasActive = player.playing || player.cur;
        stopPlayback({ keepPosition: true });
        if (wasActive) report({ current_time: [0] });
    }

    function setRate(rate) {
        const value = Number(rate);
        if (!Number.isFinite(value) || value <= 0) return;
        player.rate = value;
        if (player.cur && player.cur.el) player.cur.el.playbackRate = value;
        if (player.next && player.next.el) player.next.el.playbackRate = value;
        if (player.cur) report();
    }

    function setBoost(on) {
        player.boost = Boolean(on);
        applyGain();
        if (player.cur) report();
    }

    async function maybePreloadNext() {
        const cur = player.cur;
        if (!cur || cur.short || player.next || player.nextLoading || isStaticMode()) return;
        const duration = cur.el.duration;
        if (!Number.isFinite(duration)) return;
        if (duration - cur.el.currentTime > PRELOAD_AHEAD_SECONDS) return;
        player.nextLoading = true;
        const seq = player.seq;
        try {
            const chunk = await loadLiveChunk(cur.positionId, cur.startMs + cur.durMs);
            if (seq !== player.seq || player.cur !== cur) {
                disposeChunk(chunk);
                return;
            }
            player.next = chunk;
            if (cur.endedWaiting) {
                cur.endedWaiting = false;
                advance();
            }
        } catch (error) {
            console.warn('[ClipPlayer] Could not preload the next clip.', error);
        } finally {
            player.nextLoading = false;
            if (seq === player.seq && !player.next && player.cur === cur && cur.endedWaiting) {
                finishAtEnd();
            }
        }
    }

    function advance() {
        const finished = player.cur;
        const next = player.next;
        player.next = null;
        startChunk(next, 0);
        disposeChunk(finished);
    }

    function finishAtEnd() {
        player.playing = false;
        stopTimer();
        report();
    }

    function onChunkEnded(chunk) {
        if (chunk !== player.cur || chunk.disposed) return;
        if (player.next) {
            advance();
            return;
        }
        if (!chunk.short && player.nextLoading) {
            chunk.endedWaiting = true;   // the preload finishes and continues playback
            return;
        }
        finishAtEnd();
    }

    function onChunkError(chunk) {
        if (chunk.disposed || chunk !== player.cur) return;
        console.warn('[ClipPlayer] Playback error.', chunk.el && chunk.el.error);
        finishAtEnd();
    }

    // ------------------------------------------------------------------ entry points

    /** Run a command from audioCommands.deriveAudioCommand. */
    function execute(cmd, state) {
        if (!cmd || !cmd.command) return;
        switch (cmd.command) {
            case 'play':
                play(cmd.position_id, Number(cmd.value), state);
                break;
            case 'pause':
                pause();
                break;
            case 'set_rate':
                setRate(cmd.value);
                break;
            case 'toggle_boost':
                setBoost(cmd.value);
                break;
            default:
                break;
        }
    }

    function setBackend(name, options) {
        const next = name === 'browser' ? 'browser' : 'vlc';
        if (isStaticMode()) return;
        if (backend === null) ensureConfig();
        if (backend === null) backend = 'vlc';
        if (next === backend) {
            syncBackendToggle();
            return;
        }
        const state = app.store && app.store.getState ? app.store.getState() : null;
        if (next === 'browser') {
            // Silence VLC first, then report the transport as stopped.
            const control = getModels().audio_control_source;
            if (control && state?.audio?.isPlaying) {
                control.data = { command: ['pause'], position_id: [state.audio.activePositionId], value: [null] };
            }
            backend = 'browser';
            player.positionId = state?.audio?.activePositionId || null;
            report({ is_playing: [false], current_time: [0] });
        } else {
            stop();
            backend = 'vlc';
        }
        if (!options || options.persist !== false) storeBackend(next);
        syncBackendToggle();
        console.info(`[ClipPlayer] Audio backend: ${next}`);
    }

    function debug() {
        const cur = player.cur;
        return {
            backend: getBackend(),
            playing: player.playing,
            positionId: player.positionId,
            rate: player.rate,
            boost: player.boost,
            elementRate: cur && cur.el ? cur.el.playbackRate : null,
            gain: gainNode ? gainNode.gain.value : null,
            contextState: ctx ? ctx.state : null,
            graph: Boolean(ctx),
            currentTimeMs: cur && cur.el ? cur.startMs + cur.el.currentTime * 1000 : null,
            elementPaused: cur && cur.el ? cur.el.paused : null,
            chunk: cur ? { startMs: cur.startMs, durMs: cur.durMs, frames: cur.frames, sampleRate: cur.sampleRate, positionId: cur.positionId, fileName: cur.fileName } : null,
            next: player.next ? { startMs: player.next.startMs, durMs: player.next.durMs } : null,
            requests: requestLog.slice()
        };
    }

    window.addEventListener('pagehide', () => { stopPlayback(); });

    app.services = app.services || {};
    app.services.audio = app.services.audio || {};
    app.services.audio.clipPlayer = {
        BOOST_GAIN,
        isBrowserBackend,
        getBackend,
        setBackend,
        execute,
        play,
        pause,
        stop,
        setRate,
        setBoost,
        hasStaticClips,
        findStaticClip,
        debug,
        // Test seams
        _regionBounds: regionBounds,
        _reset() {
            stopPlayback();
            backend = null;
            configTried = false;
            config = { baseUrl: '', token: '', clipSeconds: DEFAULT_CLIP_SECONDS };
            requestLog.length = 0;
        }
    };
})(window.NoiseSurveyApp);
