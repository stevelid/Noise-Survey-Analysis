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

    function togglePlaybackFromKeyboardIntent() {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function' || typeof getState !== 'function') return;

            const state = getState();
            const audioState = state?.audio;
            const tapState = state?.interaction?.tap;

            if (!audioState) {
                return;
            }

            if (audioState.isPlaying && audioState.activePositionId) {
                dispatch(togglePlayPauseIntent({
                    positionId: audioState.activePositionId,
                    isActive: false
                }));
                return;
            }

            if (!tapState?.isActive || !Number.isFinite(tapState.timestamp)) {
                return;
            }

            const targetPosition = tapState.position || audioState.activePositionId;
            if (!targetPosition) {
                return;
            }

            dispatch(togglePlayPauseIntent({
                positionId: targetPosition,
                isActive: true
            }));
        };
    }

    function handleAudioStatusUpdateIntent(statusPayload) {
        return function (dispatch, getState) {
            if (!actions || typeof dispatch !== 'function') return;

            const state = typeof getState === 'function' ? getState() : null;
            const offsets = state?.view?.positionEffectiveOffsets || {};

            const nextStatus = {};
            if (statusPayload && typeof statusPayload === 'object') {
                Object.keys(statusPayload).forEach(key => {
                    const value = statusPayload[key];
                    nextStatus[key] = Array.isArray(value) ? value.slice() : value;
                });
            }

            const activePositionId = Array.isArray(nextStatus.active_position_id)
                ? nextStatus.active_position_id[0]
                : null;
            const offsetMs = Number(offsets?.[activePositionId]) || 0;

            if (Array.isArray(nextStatus.current_time) && nextStatus.current_time.length) {
                const raw = Number(nextStatus.current_time[0]);
                if (Number.isFinite(raw)) {
                    nextStatus.current_time[0] = raw + offsetMs;
                }
            }

            if (Array.isArray(nextStatus.current_file_start_time) && nextStatus.current_file_start_time.length) {
                const rawStart = Number(nextStatus.current_file_start_time[0]);
                if (Number.isFinite(rawStart)) {
                    nextStatus.current_file_start_time[0] = rawStart + offsetMs;
                }
            }

            dispatch(actions.audioStatusUpdate(nextStatus));
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
        togglePlaybackFromKeyboardIntent,
        handleAudioStatusUpdateIntent,
        changePlaybackRateIntent,
        toggleVolumeBoostIntent
    };
})(window.NoiseSurveyApp);
