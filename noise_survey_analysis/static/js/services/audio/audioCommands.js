// noise_survey_analysis/static/js/services/audio/audioCommands.js

/**
 * @fileoverview The one mapping from a store change to an audio transport command.
 *
 * `app.handleAudioSideEffects` (app.js) calls `deriveAudioCommand` and hands the result to
 * either the server (`audio_control_source`, VLC backend) or the in-page clip player
 * (`clipPlayer.js`, browser backend), so both backends see exactly the same time mapping:
 *   audio time = chart time - effective offset (chart offset + audio offset).
 * The player's reported time has the offset added back by `handleAudioStatusUpdateIntent`.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    /**
     * @param {object} current  state after the action
     * @param {object} previous state before the action
     * @returns {{command: string, position_id: string|null, value: *}|null}
     */
    function deriveAudioCommand(current, previous) {
        const { actionTypes } = app;
        const lastAction = current?.system?.lastAction;
        if (!lastAction || !actionTypes) return null;

        // --- A. User-initiated playback (tap, key nav, or the Play button) ---
        const audioWasPlayingPreviously = Boolean(previous?.audio?.isPlaying);
        const wasTapPlayback = lastAction.type === actionTypes.TAP && audioWasPlayingPreviously;
        const wasKeyNavPlayback = lastAction.type === actionTypes.KEY_NAV && audioWasPlayingPreviously;
        const wasPlayToggleRequest = lastAction.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE && lastAction.payload.isActive;
        const shouldSendPlayCommand = wasTapPlayback || wasKeyNavPlayback || wasPlayToggleRequest;

        if (shouldSendPlayCommand) {
            const tapState = current?.interaction?.tap || {};
            const position = wasPlayToggleRequest
                ? lastAction.payload.positionId
                : tapState.position || current.audio.activePositionId || previous?.audio?.activePositionId;

            let timestamp = Number(tapState.timestamp);
            if (!Number.isFinite(timestamp)) {
                timestamp = Number(previous?.interaction?.tap?.timestamp);
            }

            if (!position || !Number.isFinite(timestamp)) {
                console.warn('[Side Effect] Skipping play command due to missing context.', { position, timestamp });
                return null;
            }

            const offsetMs = Number(current?.view?.positionEffectiveOffsets?.[position]) || 0;
            const actualTimestamp = Math.round(timestamp - offsetMs);
            if (!Number.isFinite(actualTimestamp)) {
                console.warn('[Side Effect] Skipping play command due to invalid adjusted timestamp.', {
                    position,
                    timestamp,
                    offsetMs
                });
                return null;
            }

            console.log(`[Side Effect] Sending 'play' command for ${position} @ ${new Date(timestamp).toLocaleTimeString()} (actual ${new Date(actualTimestamp).toLocaleTimeString()})`);
            return { command: 'play', position_id: position, value: actualTimestamp };
        }

        // --- B. Pause button ---
        if (lastAction.type === actionTypes.AUDIO_PLAY_PAUSE_TOGGLE && !lastAction.payload.isActive) {
            console.log(`[Side Effect] Sending 'pause' command for ${lastAction.payload.positionId}`);
            return { command: 'pause', position_id: lastAction.payload.positionId, value: null };
        }

        // --- C. Secondary changes (rate, boost): modify the current stream, never start it ---
        if (current.audio.playbackRate !== previous.audio.playbackRate && lastAction.type === actionTypes.AUDIO_RATE_CHANGE_REQUEST) {
            console.log(`[Side Effect] Sending 'set_rate' command: ${current.audio.playbackRate}`);
            return { command: 'set_rate', position_id: current.audio.activePositionId, value: current.audio.playbackRate };
        }

        if (current.audio.volumeBoost !== previous.audio.volumeBoost && lastAction.type === actionTypes.AUDIO_BOOST_TOGGLE_REQUEST) {
            console.log(`[Side Effect] Sending 'toggle_boost' command: ${current.audio.volumeBoost}`);
            return { command: 'toggle_boost', position_id: current.audio.activePositionId, value: current.audio.volumeBoost };
        }

        return null;
    }

    app.services = app.services || {};
    app.services.audio = app.services.audio || {};
    app.services.audio.deriveAudioCommand = deriveAudioCommand;
})(window.NoiseSurveyApp);
