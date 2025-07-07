# noise_survey_analysis/core/app_callbacks.py

import logging
import time
from bokeh.plotting import curdoc
from bokeh.models import ColumnDataSource, Button, Select, Div, CustomJS
from datetime import datetime, timedelta

# Assuming AudioPlaybackHandler has been updated with set_amplification
from .audio_handler import AudioPlaybackHandler

logger = logging.getLogger(__name__)

def session_destroyed(session_context):
    """Called by Bokeh when a user session ends."""
    callback_manager = getattr(session_context, '_app_callback_manager', None)
    if callback_manager:
        logger.info(f"Session {session_context.id} destroyed. Cleaning up AppCallbacks.")
        callback_manager.cleanup()
    else:
        logger.warning(f"Session {session_context.id} destroyed, but no AppCallback manager found in session context.")

class AppCallbacks:
    """
    Manages Python-side callbacks for the Bokeh application.
    Connects UI events to application logic.
    """
    def __init__(self, doc, audio_handler: AudioPlaybackHandler | None, audio_control_source: ColumnDataSource, audio_status_source: ColumnDataSource):
        self.doc = doc
        self.audio_handler = audio_handler
        self.audio_control_source = audio_control_source
        self.audio_status_source = audio_status_source
        
        self.position_callbacks = []
        self._periodic_callback_id = None
        self._last_seek_time = 0.0

        if not self.audio_handler:
            logger.info("AppCallbacks initialized without audio handler. Audio features disabled.")

    def attach_callbacks(self):
        """Attaches all Python callbacks to the document."""
        self.attach_non_audio_callbacks()

        if self.audio_handler:
            self.audio_control_source.on_change('data', self._handle_audio_control_command)
            self._start_periodic_update()
        else:
            logger.warning("Audio callbacks not attached: Audio handler missing.")

        self.attach_js_callbacks()
        logger.info("All callbacks attached.")

    def _handle_audio_control_command(self, attr, old, new):
        if not self.audio_handler: return
        try:
            command = new.get('command', [None])[0]
            position_id = new.get('position_id', [None])[0]
            value = new.get('value', [None])[0]

            if command == 'play':
                if position_id:
                    self.audio_handler.set_current_position(position_id)
                    # If value is None or 0, it means we don't have a tap time, so don't play.
                    if value:
                        self.audio_handler.play(datetime.fromtimestamp(value / 1000.0))
            elif command == 'pause':
                self.audio_handler.pause()
            elif command == 'seek':
                if position_id:
                    self.audio_handler.set_current_position(position_id)
                self.audio_handler.seek_to_time(datetime.fromtimestamp(value / 1000.0))
            elif command == 'set_rate':
                self.audio_handler.set_playback_rate(value)
            elif command == 'toggle_boost':
                if value: # If boost is requested
                    self.audio_handler.set_amplification(20)
                else:
                    self.audio_handler.set_amplification(0)
            
            # Clear the command after processing to allow the same command to be sent again
            self.doc.add_next_tick_callback(lambda: self.audio_control_source.patch({'command': [(0, None)]}))
        except Exception as e:
            logger.error(f"Error processing audio control command: {e}", exc_info=True)

    def _periodic_update_audio_status(self):
        """Periodically updates the audio status source with current playback information."""
        if not self.audio_handler:
            return

        is_playing = self.audio_handler.is_playing()
        current_position_dt = self.audio_handler.get_current_position()
        playback_rate = self.audio_handler.get_playback_rate()
        current_position_id = self.audio_handler.current_position
        # FIX: Check if current_amplification property exists and use it
        boost_active = getattr(self.audio_handler, 'current_amplification', 0) > 0

        current_position_ms = int(current_position_dt.timestamp() * 1000) if current_position_dt else 0
        current_file_duration = self.audio_handler.current_file_duration if self.audio_handler.current_file_duration is not None else 0
        current_file_start_time_dt = self.audio_handler.media_start_time
        current_file_start_time_ms = int(current_file_start_time_dt.timestamp() * 1000) if current_file_start_time_dt else 0

        # Patch the ColumnDataSource with all fields expected by JS
        self.audio_status_source.patch({
            'is_playing': [(0, is_playing)],
            'current_time': [(0, current_position_ms)],
            'playback_rate': [(0, playback_rate)],
            'current_file_duration': [(0, current_file_duration)],
            'current_file_start_time': [(0, current_file_start_time_ms)],
            'active_position_id': [(0, current_position_id)],
            'volume_boost': [(0, boost_active)]
        })

    def _start_periodic_update(self):
        """Starts the periodic callback for audio status updates."""
        if self._periodic_callback_id is None:
            self._periodic_callback_id = self.doc.add_periodic_callback(self._periodic_update_audio_status, 100)
            logger.info("Started periodic audio status update.")

    def _stop_periodic_update(self):
        """Stops the periodic callback for audio status updates."""
        if self._periodic_callback_id is not None:
            self.doc.remove_periodic_callback(self._periodic_callback_id)
            self._periodic_callback_id = None
            logger.info("Stopped periodic audio status update.")

    def cleanup(self):
        """Cleans up resources when the session is destroyed."""
        self._stop_periodic_update()
        if self.audio_handler:
            self.audio_handler.release()
            logger.info("Audio handler released.")
        logger.info("AppCallbacks cleaned up.")

    def attach_non_audio_callbacks(self):
        pass

    def attach_js_callbacks(self):
        pass