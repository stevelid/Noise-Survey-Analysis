/**
 * audio.js
 * 
 * Audio playback visualization for Noise Survey Analysis
 * 
 * This file contains functions for visualizing audio playback position
 * and handling audio control interactions.
 */

/**
 * Update visualization based on current audio playback position
 * @param {number} currentTimeMs - Current playback time in milliseconds
 */
function updatePlaybackPosition(currentTimeMs) {
    console.log('Audio playback position updated:', new Date(currentTimeMs).toLocaleString());
    
    // Update all chart lines to show current playback position
    if (window.updateAllLines) {
        window.updateAllLines(currentTimeMs);
    } else {
        console.error('updateAllLines function not available');
    }
}

/**
 * Initialize audio playback visualization
 * @param {Object} playbackSource - ColumnDataSource that tracks playback position
 */
function initializeAudioVisualization(playbackSource) {
    console.log('Initializing audio visualization');
    
    // Watch for changes to the playback source
    if (playbackSource) {
        playbackSource.on_change('data', function() {
            if (playbackSource.data && playbackSource.data.current_time && 
                playbackSource.data.current_time.length > 0) {
                
                const currentTime = playbackSource.data.current_time[0];
                updatePlaybackPosition(currentTime);
            }
        });
    } else {
        console.error('Playback source not provided');
    }
}

/**
 * Handle play button click
 * This function should be called from Python when the play button is clicked
 * @param {number} timestamp - Timestamp to start playing from
 */
function onPlayButtonClick(timestamp) {
    console.log('Play button clicked, timestamp:', timestamp);
    updatePlaybackPosition(timestamp);
}

/**
 * Handle pause button click
 * This function should be called from Python when the pause button is clicked
 */
function onPauseButtonClick() {
    console.log('Pause button clicked');
    // Any visualization updates needed when paused
}

/**
 * Handle stop button click
 * This function should be called from Python when the stop button is clicked
 */
function onStopButtonClick() {
    console.log('Stop button clicked');
    // Any visualization updates needed when stopped
}

// Export functions for use in Bokeh callbacks
window.updatePlaybackPosition = updatePlaybackPosition;
window.initializeAudioVisualization = initializeAudioVisualization;
window.onPlayButtonClick = onPlayButtonClick;
window.onPauseButtonClick = onPauseButtonClick;
window.onStopButtonClick = onStopButtonClick; 