# noise_survey_analysis/core/app_callbacks.py

import logging
import time
import threading
from bokeh.plotting import curdoc
from bokeh.models import ColumnDataSource, Button, Select, Div, CustomJS
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

# Assuming AudioPlaybackHandler has been updated with set_amplification
from .audio_handler import AudioPlaybackHandler
from .config import STREAMING_DEBOUNCE_MS, STREAMING_ENABLED

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
    def __init__(
        self,
        doc,
        audio_handler: AudioPlaybackHandler | None,
        audio_control_source: ColumnDataSource,
        audio_status_source: ColumnDataSource,
        session_action_source: Optional[ColumnDataSource] = None,
        session_status_source: Optional[ColumnDataSource] = None,
        static_export_request_handler: Optional[Callable[..., dict]] = None,
        server_data_handler=None,
        streaming_enabled: bool = STREAMING_ENABLED,
        streaming_debounce_ms: int = STREAMING_DEBOUNCE_MS,
    ):
        self.doc = doc
        self.audio_handler = audio_handler
        self.audio_control_source = audio_control_source
        self.audio_status_source = audio_status_source
        self.session_action_source = session_action_source
        self.session_status_source = session_status_source
        self.static_export_request_handler = static_export_request_handler
        self.server_data_handler = server_data_handler
        self.streaming_enabled = streaming_enabled
        self.streaming_debounce_ms = streaming_debounce_ms

        logger.debug(f"[AppCallbacks.__init__] Received audio_control_source with id: {id(self.audio_control_source)}")
        
        self.position_callbacks = []
        self._periodic_callback_id = None
        self._last_seek_time = 0.0
        self._streaming_timeout_id = None
        self._pending_stream_range = None
        self._static_export_in_progress = False

        if not self.audio_handler:
            logger.info("AppCallbacks initialized without audio handler. Audio features disabled.")
        elif not getattr(self.audio_handler, 'audio_available', True):
            logger.warning("AppCallbacks initialized with audio handler but VLC is unavailable. Audio callbacks will be disabled.")

    def attach_callbacks(self):
        """Attaches all Python callbacks to the document."""
        self.attach_non_audio_callbacks()

        if self.audio_handler and getattr(self.audio_handler, 'audio_available', False):
            logger.debug(f"[AppCallbacks.attach] Attaching audio control callback to source id: {id(self.audio_control_source)}")
            self.audio_control_source.on_change('data', self._handle_audio_control_command)
            self._start_periodic_update()
        else:
            logger.warning("Audio callbacks not attached: Audio handler missing or audio unavailable.")

        if self.session_action_source is not None:
            self.session_action_source.on_change('data', self._handle_session_action_command)

        self.attach_js_callbacks()
        logger.info("All callbacks attached.")

    def _handle_audio_control_command(self, attr, old, new):
        if not self.audio_handler or not getattr(self.audio_handler, 'audio_available', False):
            logger.debug("Ignoring audio control command: audio handler missing or unavailable.")
            return
        try:
            command = new.get('command', [None])[0]
            if command is None:
                return
            position_id = new.get('position_id', [None])[0] 
            value = new.get('value', [None])[0]

            logger.info(f"Received audio control command: {command}, position_id: {position_id}, value: {value}")

            if command == 'play':
                if position_id:
                    self.audio_handler.set_current_position(position_id)
                    # The audio handler now defaults to playing from the start of the file if no valid time is given.
                    if value:
                        play_timestamp = datetime.utcfromtimestamp(value / 1000.0).replace(tzinfo=timezone.utc)
                    else:
                        play_timestamp = None
                    self.audio_handler.play(play_timestamp)
            elif command == 'pause':
                self.audio_handler.pause()
            elif command == 'seek':
                # If a seek command is issued, it must set the active position first.
                if position_id and self.audio_handler.current_position != position_id:
                    logger.info(f"Seek command received for new position '{position_id}', switching audio source.")
                    self.audio_handler.set_current_position(position_id)                
                if value:
                    seek_timestamp = datetime.utcfromtimestamp(value / 1000.0).replace(tzinfo=timezone.utc)
                    self.audio_handler.seek_to_time(seek_timestamp)
            elif command == 'set_rate':
                if position_id:
                    self.audio_handler.set_current_position(position_id)
                self.audio_handler.set_playback_rate(value)
            elif command == 'toggle_boost':
                if position_id:
                    self.audio_handler.set_current_position(position_id)
                # value will be a boolean from the JS toggle
                self.audio_handler.set_amplification(20 if value else 0)
            
            # Clear the command after processing to allow the same command to be sent again
            self.doc.add_next_tick_callback(lambda: self.audio_control_source.patch({'command': [(0, None)]}))
        except Exception as e:
            logger.error(f"Error processing audio control command: {e}", exc_info=True)

    def _publish_session_status(
        self,
        level: str,
        message: str,
        *,
        done: bool = False,
        output_path: str = '',
        request_id: str | None = None,
    ) -> None:
        if self.session_status_source is None:
            return

        updated_at = int(time.time() * 1000)

        def update_status():
            try:
                self.session_status_source.data = {
                    'request_id': [request_id],
                    'level': [str(level or 'info')],
                    'message': [str(message or '')],
                    'output_path': [str(output_path or '')],
                    'done': [bool(done)],
                    'updated_at': [updated_at],
                }
            except Exception as exc:
                logger.error(f"Failed to publish session status: {exc}", exc_info=True)

        self.doc.add_next_tick_callback(update_status)

    def _clear_session_action_command(self) -> None:
        if self.session_action_source is None:
            return

        def clear_command():
            try:
                self.session_action_source.data = {
                    'command': [None],
                    'request_id': [None],
                    'payload': [None],
                }
            except Exception as exc:
                logger.error(f"Failed to clear session action command: {exc}", exc_info=True)

        self.doc.add_next_tick_callback(clear_command)

    def _handle_session_action_command(self, attr, old, new):
        try:
            command = new.get('command', [None])[0]
            request_id = new.get('request_id', [None])[0]
            payload = new.get('payload', [None])[0]
        except Exception:
            self._clear_session_action_command()
            return

        if command is None:
            return

        logger.info(f"Received session action command: {command} (request_id={request_id})")

        if command != 'generate_static_html':
            self._publish_session_status(
                'warning',
                f"Unhandled session action '{command}'.",
                done=True,
                request_id=request_id,
            )
            self._clear_session_action_command()
            return

        if self._static_export_in_progress:
            self._publish_session_status(
                'warning',
                'Static HTML export is already running. Please wait for it to finish.',
                done=True,
                request_id=request_id,
            )
            self._clear_session_action_command()
            return

        if not callable(self.static_export_request_handler):
            self._publish_session_status(
                'error',
                'Static HTML export is unavailable in this session.',
                done=True,
                request_id=request_id,
            )
            self._clear_session_action_command()
            return

        self._static_export_in_progress = True
        self._publish_session_status(
            'info',
            'Generating static HTML. This can take a minute for large datasets.',
            done=False,
            request_id=request_id,
        )
        self._clear_session_action_command()

        def run_export():
            try:
                result = self.static_export_request_handler(payload=payload, request_id=request_id)
                success = bool(result.get('success')) if isinstance(result, dict) else bool(result)
                output_path = ''
                if isinstance(result, dict):
                    output_path = str(result.get('output_path') or '')
                    message = result.get('message')
                else:
                    message = None

                if not message:
                    if success:
                        message = (
                            f"Static HTML export complete: {output_path}"
                            if output_path
                            else 'Static HTML export complete.'
                        )
                    else:
                        message = 'Static HTML export failed.'

                self._publish_session_status(
                    'info' if success else 'error',
                    str(message),
                    done=True,
                    output_path=output_path,
                    request_id=request_id,
                )
            except Exception as exc:
                logger.error(f"Static export request failed: {exc}", exc_info=True)
                self._publish_session_status(
                    'error',
                    f"Static HTML export failed: {exc}",
                    done=True,
                    request_id=request_id,
                )
            finally:
                self._static_export_in_progress = False

        threading.Thread(target=run_export, daemon=True).start()

    def _periodic_update_audio_status(self):
        """Periodically updates the audio status source with current playback information."""
        if not self.audio_handler or not getattr(self.audio_handler, 'audio_available', False):
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
        
        # Get current file name (just the basename)
        import os
        current_file_name = ''
        if self.audio_handler.current_file:
            current_file_name = os.path.basename(self.audio_handler.current_file)

        # Patch the ColumnDataSource with all fields expected by JS
        self.audio_status_source.patch({
            'is_playing': [(0, is_playing)],
            'current_time': [(0, current_position_ms)],
            'playback_rate': [(0, playback_rate)],
            'current_file_duration': [(0, current_file_duration)],
            'current_file_start_time': [(0, current_file_start_time_ms)],
            'active_position_id': [(0, current_position_id)],
            'volume_boost': [(0, boost_active)],
            'current_file_name': [(0, current_file_name)]
        })

    def _start_periodic_update(self):
        """Starts the periodic callback for audio status updates."""
        if self._periodic_callback_id is None:
            # Use 200ms interval instead of 100ms to reduce WebSocket traffic
            # This improves zoom responsiveness during audio playback
            self._periodic_callback_id = self.doc.add_periodic_callback(self._periodic_update_audio_status, 200)
            logger.info("Started periodic audio status update.")

    def _stop_periodic_update(self):
        """Stops the periodic callback for audio status updates."""
        if self._periodic_callback_id is not None:
            try:
                self.doc.remove_periodic_callback(self._periodic_callback_id)
                logger.info("Stopped periodic audio status update.")
            except Exception as e:
                logger.warning(f"Error removing periodic callback (likely already removed): {e}")
            finally:
                self._periodic_callback_id = None

    def cleanup(self):
        """Cleans up resources when the session is destroyed."""
        self._stop_periodic_update()
        if self.audio_handler:
            try:
                self.audio_handler.release()
                logger.info("Audio handler released.")
            except Exception as e:
                logger.warning(f"Error releasing audio handler: {e}")
        logger.info("AppCallbacks cleaned up.")

    def set_server_data_handler(self, server_data_handler):
        self.server_data_handler = server_data_handler

    def attach_non_audio_callbacks(self):
        if not self.streaming_enabled or not self.server_data_handler:
            return

        master_x_range = self.doc.get_model_by_name('master_x_range')
        if not master_x_range:
            logger.warning("Streaming enabled but 'master_x_range' model not found.")
            return

        def schedule_range_update(attr, old, new):
            self._pending_stream_range = (master_x_range.start, master_x_range.end)
            if self._streaming_timeout_id is not None:
                return

            def run_update():
                self._streaming_timeout_id = None
                pending = self._pending_stream_range
                self._pending_stream_range = None
                if not pending:
                    return
                start_ms, end_ms = pending
                self.server_data_handler.handle_range_update(start_ms, end_ms)

            self._streaming_timeout_id = self.doc.add_timeout_callback(
                run_update,
                self.streaming_debounce_ms,
            )

        master_x_range.on_change('start', schedule_range_update)
        master_x_range.on_change('end', schedule_range_update)

        param_select = self.doc.get_model_by_name('global_parameter_selector')
        if param_select:
            def on_param_change(attr, old, new):
                self.server_data_handler.set_selected_parameter(new)
                self.server_data_handler.handle_range_update(master_x_range.start, master_x_range.end)

            param_select.on_change('value', on_param_change)

        self.server_data_handler.handle_range_update(master_x_range.start, master_x_range.end)

    def attach_js_callbacks(self):
        pass
