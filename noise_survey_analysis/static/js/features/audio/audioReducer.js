// noise_survey_analysis/static/js/features/audio/audioReducer.js

/**
 * @fileoverview Reducer for audio playback state.
 */

window.NoiseSurveyApp = window.NoiseSurveyApp || {};
(function (app) {
    'use strict';

    const { actionTypes } = app;

    const initialAudioState = {
        isPlaying: false,
        activePositionId: null,
        playbackRate: 1.0,
        volumeBoost: false
    };

    function audioReducer(state = initialAudioState, action) {
        switch (action.type) {
            case actionTypes.AUDIO_STATUS_UPDATE:
                return {
                    ...state,
                    isPlaying: action.payload?.status?.is_playing?.[0] ?? state.isPlaying,
                    activePositionId: action.payload?.status?.active_position_id?.[0] ?? state.activePositionId,
                    playbackRate: action.payload?.status?.playback_rate?.[0] ?? state.playbackRate,
                    volumeBoost: action.payload?.status?.volume_boost?.[0] ?? state.volumeBoost
                };

            case actionTypes.AUDIO_PLAY_PAUSE_TOGGLE: {
                const { positionId, isActive } = action.payload || {};
                if (isActive) {
                    return {
                        ...state,
                        isPlaying: true,
                        activePositionId: positionId
                    };
                }
                if (state.activePositionId === positionId) {
                    return {
                        ...state,
                        isPlaying: false
                    };
                }
                return state;
            }

            case actionTypes.TAP: {
                const nextPosition = action.payload?.position;
                if (!state.isPlaying || !nextPosition || nextPosition === state.activePositionId) {
                    return state;
                }
                return {
                    ...state,
                    activePositionId: nextPosition
                };
            }

            default:
                return state;
        }
    }

    app.features = app.features || {};
    app.features.audio = app.features.audio || {};
    app.features.audio.initialState = initialAudioState;
    app.features.audio.audioReducer = audioReducer;
})(window.NoiseSurveyApp);
