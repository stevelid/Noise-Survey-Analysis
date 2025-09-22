// noise_survey_analysis/static/js/features/audio/audioThunks.js

/**
 * @fileoverview Thunks for orchestrating audio playback requests.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actions } = app;

    function togglePlayPauseIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') return;

            const positionId = typeof payload?.positionId === 'string' ? payload.positionId : null;
            const isActive = typeof payload?.isActive === 'boolean' ? payload.isActive : null;
            if (!positionId || isActive === null) {
                return;
            }

            const state = getState();
            const audioState = state?.audio;
            if (!audioState) {
                return;
            }

            const { isPlaying, activePositionId } = audioState;

            if (isActive) {
                if (isPlaying && activePositionId === positionId) {
                    return;
                }
            } else {
                if (!isPlaying || activePositionId !== positionId) {
                    return;
                }
            }

            dispatch(actions.audioPlayPauseToggle(positionId, isActive));
        };
    }

    function changePlaybackRateIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') return;

            const positionId = typeof payload?.positionId === 'string' ? payload.positionId : null;
            if (!positionId) {
                return;
            }

            const state = getState();
            const audioState = state?.audio;
            if (!audioState || audioState.activePositionId !== positionId) {
                return;
            }

            const requestedRate = Number(payload?.playbackRate);
            if (Number.isFinite(requestedRate) && requestedRate === audioState.playbackRate) {
                return;
            }

            dispatch(actions.audioRateChangeRequest(positionId));
        };
    }

    function toggleVolumeBoostIntent(payload) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') return;

            const positionId = typeof payload?.positionId === 'string' ? payload.positionId : null;
            const isBoostActive = typeof payload?.isBoostActive === 'boolean' ? payload.isBoostActive : null;
            if (!positionId || isBoostActive === null) {
                return;
            }

            const state = getState();
            const audioState = state?.audio;
            if (!audioState || audioState.activePositionId !== positionId) {
                return;
            }

            if (audioState.volumeBoost === isBoostActive) {
                return;
            }

            dispatch(actions.audioBoostToggleRequest(positionId, isBoostActive));
        };
    }

    app.features = app.features || {};
    app.features.audio = app.features.audio || {};
    app.features.audio.thunks = {
        togglePlayPauseIntent,
        changePlaybackRateIntent,
        toggleVolumeBoostIntent
    };
})(window.NoiseSurveyApp);
