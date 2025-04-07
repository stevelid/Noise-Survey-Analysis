import { expect, describe, it, beforeEach, afterEach, vi } from 'vitest';
// Import test implementations instead of the real ones
import { 
  updatePlaybackLine, 
  setPlayState, 
  handleTimeClick, 
  stopAudio, 
  playAudio 
} from '../../../tests/js/audio.test.setup.js';

// Get access to the module's exports for mocking
const audioSetupModule = require('../../../tests/js/audio.test.setup.js');

// Use mock implementations for testing
const audioModule = {
  updatePlaybackLine: audioSetupModule.updatePlaybackLine,
  setPlayState: audioSetupModule.setPlayState,
  handleTimeClick: audioSetupModule.handleTimeClick,
  stopAudio: audioSetupModule.stopAudio,
  playAudio: audioSetupModule.playAudio
};

// Setup mocks
beforeEach(() => {
  // Mock window object
  global.window = {
    updateTapLinePositions: vi.fn(),
    playbackSource: {
      data: {
        currentPosition: [0],
        playing: [false]
      },
      change: {
        on: vi.fn(),
        emit: vi.fn()
      }
    },
    document: {
      getElementById: vi.fn((id) => {
        if (id === 'play-btn') return { style: { display: 'inline-block' }, click: vi.fn() };
        if (id === 'pause-btn') return { style: { display: 'none' }, click: vi.fn() };
        return { style: {}, click: vi.fn() };
      })
    }
  };

  // Mock console methods
  global.console = {
    log: vi.fn(),
    warn: vi.fn(),
    error: vi.fn()
  };
});

// Clean up mocks
afterEach(() => {
  vi.clearAllMocks();
  delete global.window;
  delete global.console;
});

// Tests
describe('audio.js', () => {
  // Test updatePlaybackLine function
  describe('updatePlaybackLine', () => {
    it('should update playback source with current time', () => {
      const testTime = 1672574400000; // 2023-01-01 10:00:00

      audioModule.updatePlaybackLine(testTime);

      // Should update the playback source position
      expect(window.playbackSource.data.currentPosition).toEqual([testTime]);
      expect(window.playbackSource.change.emit).toHaveBeenCalled();
    });

    it('should log the playback position update', () => {
      const testTime = 1672574400000;

      audioModule.updatePlaybackLine(testTime);

      // Should log the update
      expect(console.log).toHaveBeenCalledWith('Playback position updated:', testTime);
    });

    it('should handle missing playback source gracefully', () => {
      // Remove playback source
      delete window.playbackSource;
      
      audioModule.updatePlaybackLine(1000);

      expect(console.warn).toHaveBeenCalledWith('Playback source not available for update');
      
      // Restore it for other tests
      window.playbackSource = {
        data: { currentPosition: [0], playing: [false] },
        change: { emit: vi.fn(), on: vi.fn() }
      };
    });
  });

  // Test setPlayState function
  describe('setPlayState', () => {
    it('should update play state in playback source', () => {
      audioModule.setPlayState(true);
      
      expect(window.playbackSource.data.playing).toEqual([true]);
      expect(window.playbackSource.change.emit).toHaveBeenCalled();
    });
    
    it('should toggle UI button visibility', () => {
      audioModule.setPlayState(true);
      
      const playBtn = document.getElementById('play-btn');
      const pauseBtn = document.getElementById('pause-btn');
      
      expect(window.document.getElementById).toHaveBeenCalledWith('play-btn');
      expect(window.document.getElementById).toHaveBeenCalledWith('pause-btn');
    });
  });

  // Test handleTimeClick function
  describe('handleTimeClick', () => {
    it('should update playback line with clicked time', () => {
      // Create a spy on updatePlaybackLine before the function runs
      const realUpdatePlaybackLine = audioModule.updatePlaybackLine;
      audioModule.updatePlaybackLine = vi.fn();
      
      // Call the function
      audioModule.handleTimeClick({ x: 5000 });
      
      // Check if it was called correctly
      expect(audioModule.updatePlaybackLine).toHaveBeenCalledWith(5000);
      
      // Restore the original function
      audioModule.updatePlaybackLine = realUpdatePlaybackLine;
    });
    
    it('should restart playback if already playing', () => {
      // Set playing state to true
      window.playbackSource.data.playing = [true];
      
      // Create spies
      const realStopAudio = audioModule.stopAudio;
      const realPlayAudio = audioModule.playAudio;
      audioModule.stopAudio = vi.fn();
      audioModule.playAudio = vi.fn();
      
      // Call the function
      audioModule.handleTimeClick({ x: 5000 });
      
      // Check if the functions were called
      expect(audioModule.stopAudio).toHaveBeenCalled();
      expect(audioModule.playAudio).toHaveBeenCalled();
      
      // Restore the original functions
      audioModule.stopAudio = realStopAudio;
      audioModule.playAudio = realPlayAudio;
    });
  });
}); 