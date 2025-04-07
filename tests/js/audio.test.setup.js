// audio.test.setup.js
// Mock implementations of audio.js functions for testing

// Implementation of updatePlaybackLine
function updatePlaybackLine(timeMs) {
  console.log('Playback position updated:', timeMs);
  
  // Update the playback source if available
  if (window.playbackSource) {
    window.playbackSource.data.currentPosition = [timeMs];
    window.playbackSource.change.emit();
  } else {
    console.warn('Playback source not available for update');
  }
}

// Implementation of setPlayState
function setPlayState(isPlaying) {
  // Update playback source if available
  if (window.playbackSource) {
    window.playbackSource.data.playing = [isPlaying];
    window.playbackSource.change.emit();
  }
  
  // Update UI buttons
  if (window.document) {
    const playBtn = window.document.getElementById('play-btn');
    const pauseBtn = window.document.getElementById('pause-btn');
    
    if (playBtn && pauseBtn) {
      playBtn.style.display = isPlaying ? 'none' : 'inline-block';
      pauseBtn.style.display = isPlaying ? 'inline-block' : 'none';
    }
  }
}

// Implementation of handleTimeClick
function handleTimeClick(event) {
  if (event && typeof event.x === 'number') {
    updatePlaybackLine(event.x);
    
    // If already playing, restart playback from the new position
    if (window.playbackSource && 
        window.playbackSource.data && 
        window.playbackSource.data.playing && 
        window.playbackSource.data.playing[0]) {
      
      stopAudio();
      playAudio();
    }
  }
}

// Implementation of stopAudio
function stopAudio() {
  console.log('Stopping audio playback');
  setPlayState(false);
}

// Implementation of playAudio
function playAudio() {
  console.log('Starting audio playback');
  setPlayState(true);
}

module.exports = {
  updatePlaybackLine,
  setPlayState,
  handleTimeClick,
  stopAudio,
  playAudio
}; 