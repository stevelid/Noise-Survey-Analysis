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
    def __init__(self, doc, audio_handler: AudioPlaybackHandler | None, bokeh_models: dict):
        self.doc = doc
        self.audio_handler = audio_handler

        # Store component references from models
        self.playback_source = bokeh_models.get('sources', {}).get('playback', {}).get('position')
        self.seek_command_source = bokeh_models.get('sources', {}).get('playback', {}).get('seek_command')
        self.play_request_source = bokeh_models.get('sources', {}).get('playback', {}).get('play_request')
        self.js_trigger_source = bokeh_models.get('sources', {}).get('playback', {}).get('js_trigger')
        self.playback_controls = bokeh_models.get('ui', {}).get('controls', {}).get('playback', {})
        self.position_play_buttons = self.playback_controls.get('position_buttons', {})
        self.speed_control = self.playback_controls.get('speed_control')
        self.amp_control = self.playback_controls.get('amp_control')
        self.param_select = bokeh_models.get('ui', {}).get('controls', {}).get('parameter', {}).get('select')
        self.param_holder = bokeh_models.get('ui', {}).get('controls', {}).get('parameter', {}).get('holder')
        self.status_source = bokeh_models.get('sources', {}).get('playback', {}).get('status')
        
        self.position_callbacks = []
        self._periodic_callback_id = None
        self.is_periodic_running = False
        self._last_seek_time = 0.0

        if not self.audio_handler:
            logger.info("AppCallbacks initialized without audio handler. Audio features disabled.")

    def attach_callbacks(self):
        """Attaches all Python callbacks to the document."""
        self.attach_non_audio_callbacks()

        if self.audio_handler:
            if self.playback_source and self.playback_controls:
                self.attach_audio_callbacks()
            if self.position_play_buttons:
                self.attach_position_audio_callbacks()
        else:
            logger.warning("Audio callbacks not attached: Audio handler or required components missing.")

        self.attach_js_callbacks()
        logger.info("All callbacks attached.")

    def attach_position_audio_callbacks(self):
        """Attaches callbacks for position-specific play buttons."""
        logger.info("Attaching position-specific audio callbacks...")
        for position, button in self.position_play_buttons.items():
            if button is None:
                logger.warning(f"No button found for position '{position}', skipping.")
                continue

            pos_name_js = position
            js_code = f"""
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.handlePositionPlayClick) {{
                    window.NoiseSurveyApp.handlePositionPlayClick('{pos_name_js}');
                }} else {{
                    console.error('window.NoiseSurveyApp.handlePositionPlayClick function not found!');
                }}
            """
            button.js_on_click(CustomJS(code=js_code))
        logger.info(f"Position audio callbacks attached for {len(self.position_play_buttons)} positions")

    def attach_audio_callbacks(self):
        """Attaches all audio-related Python callbacks."""
        logger.info("Attaching audio-related callbacks...")
        self._attach_speed_control_callback()
        self._attach_amp_control_callback()
        self._attach_seek_handler_callback()
        self._attach_play_request_handler()
        self._start_periodic_update()

    def _attach_speed_control_callback(self):
        """Attaches callback to the speed control widget."""
        if self.speed_control:
            self.speed_control.on_change('active', self._speed_change_handler)
            logger.debug("Attached _speed_change_handler to speed_control.")

    def _attach_amp_control_callback(self):
        """Attaches callback to the amplification control widget."""
        if self.amp_control:
            self.amp_control.on_change('active', self._amp_change_handler)
            logger.debug("Attached _amp_change_handler to amp_control.")

    def _speed_change_handler(self, attr, old, new):
        """Handles changes in the speed control widget."""
        if not self.audio_handler: return
        speed_map = {0: 1.0, 1: 1.25, 2: 1.5, 3: 2.0, 4: 4.0}   
        rate = speed_map.get(new, 1.0)
        self.audio_handler.set_playback_rate(rate)

    def _amp_change_handler(self, attr, old, new):
        """Handles changes in the amplification control widget."""
        if not self.audio_handler: return
        amp_map = {0: 0, 1: 20, 2: 40}
        db_level = amp_map.get(new, 0)
        self.audio_handler.set_amplification(db_level)

    def _attach_seek_handler_callback(self):
        if self.seek_command_source:
            self.seek_command_source.on_change('data', self._seek_command_handler)
            logger.debug("Attached _seek_command_handler to seek_command_source.")

    def _attach_play_request_handler(self):
        if self.play_request_source:
            self.play_request_source.on_change('data', self._handle_play_request)
            logger.debug("Attached play request handler callback.")

    def _handle_play_request(self, attr, old, new):
        if not self.audio_handler: return
        try:
            position = new.get('position', [None])[0]

            # Check for the special pause command from JavaScript
            if position == 'pause_request':
                logger.info("Handling pause request from JS.")
                if self.audio_handler.is_playing():                    
                    self.audio_handler.pause()
            
            # Handle a regular play request
            elif position is not None:
                time_ms = new.get('time', [None])[0]
                if time_ms is None: return

                logger.info(f"Handling play request for position '{position}' at {time_ms}ms")
                set_pos_success = self.audio_handler.set_current_position(position)
                if not set_pos_success:
                    logger.error(f"Failed to set audio position to '{position}'.")
                    return

                self._process_seek_command(time_ms)
            # Clear the request after processing, deferring to avoid recursion
            self.doc.add_next_tick_callback(lambda: self._clear_play_request_source())
        except Exception as e:
            logger.error(f"Unexpected error in play request handler: {e}", exc_info=True)
            self.doc.add_next_tick_callback(self._call_js_notify_stopped)

    def _clear_play_request_source(self):
        self.play_request_source.data = {'position': [None], 'time': [None]}

    def _seek_command_handler(self, attr, old, new):
        if not self.audio_handler: return
        try:
            if 'target_time' not in new or new['target_time'][0] is None: return
            seek_time_ms = new['target_time'][0]
            position = new.get('position', [None])[0]
            if position:
                self.audio_handler.set_current_position(position)
            else:
                logger.warning("Seek command received without a position. Seeking in current handler position.")
            logger.debug(f"Seek command received: {seek_time_ms} ms")
            self._process_seek_command(seek_time_ms)
            if time.time() - self._last_seek_time < 0.01:
                self.seek_command_source.data = {'target_time': [None]}
        except Exception as e:
            logger.error(f"Error processing seek command: {e}", exc_info=True)

    def _process_seek_command(self, seek_time_ms):
        if not self.audio_handler: 
            logger.error("Audio handler not initialized. Cannot process seek command.")
            return
        now = time.time()
        if now - self._last_seek_time < 0.05: return
        self._last_seek_time = now

        try:
            target_timestamp = datetime.fromtimestamp(seek_time_ms / 1000.0)
            if self.audio_handler.is_playing():
                self.audio_handler.seek_to_time(timestamp=target_timestamp)
                self.playback_source.patch({'current_time': [(0, seek_time_ms)]})
            else:
                self.playback_source.patch({'current_time': [(0, seek_time_ms)]})
                self.audio_handler.seek_to_time(timestamp=target_timestamp)
        except Exception as e:
            logger.error(f"Error during seek command processing: {e}", exc_info=True)

    def _start_periodic_update(self):
        if self._periodic_callback_id: return
        try:
            self._periodic_callback_id = self.doc.add_periodic_callback(self._periodic_update, 500)
            self.is_periodic_running = True
            logger.info("Periodic update callback attached.")
        except Exception as e:
            logger.error(f"Failed to add periodic callback: {e}", exc_info=True)

    def _periodic_update(self):
        if not self.audio_handler or not self.playback_source or not self.is_periodic_running: return
        
        if not self.status_source: 
            logger.warning("Status source not found. Periodic update callback will not function.")
            return

        current_time_ms = None
        is_playing_in_handler = self.audio_handler.is_playing()

        if is_playing_in_handler:
            current_pos_dt = self.audio_handler.get_current_position()
            if current_pos_dt:
                current_time_ms = int(current_pos_dt.timestamp() * 1000)
            elif self.audio_handler.is_in_terminal_state():
                logger.info("Audio handler reached terminal state. Stopping playback.")
                self.audio_handler.pause()
                is_playing_in_handler = False

        #update vertical line position
        if current_time_ms is not None and self.playback_source.data.get('current_time', [None])[0] != current_time_ms:
            self.playback_source.data = {'current_time': [current_time_ms]}
        
        # Update the central status if it has changed
        if (self.status_source.data['is_playing'][0] != is_playing_in_handler or
            self.status_source.data['active_position'][0] != self.audio_handler.current_position):
            logger.debug(f"Pushing state to JS: is_playing={is_playing_in_handler}, position={self.audio_handler.current_position}")
            self.status_source.data = {
                'is_playing': [is_playing_in_handler],
                'active_position': [self.audio_handler.current_position]
            }
        
        if self.audio_handler.is_playing():
            try:
                current_pos_dt = self.audio_handler.get_current_position()
                if current_pos_dt:
                    current_time_ms = int(current_pos_dt.timestamp() * 1000)
                    if self.playback_source.data.get('current_time', [None])[0] != current_time_ms:
                        self.playback_source.data = {'current_time': [current_time_ms]}
                elif self.audio_handler.is_in_terminal_state():
                    logger.info("Audio handler reached terminal state. Stopping playback.")
                    self.audio_handler.pause()
                    self.doc.add_next_tick_callback(self._call_js_notify_stopped)
            except Exception as e:
                logger.error(f"Error during periodic update: {e}", exc_info=True)

    def _call_js_notify_stopped(self):
        logger.debug("Scheduling JS call: window.notifyPlaybackStopped()")
        if self.js_trigger_source:
            # Trigger the JS listener by updating the data of the dummy source.
            # We change the data to a unique value to ensure the change event fires.
            self.js_trigger_source.data = {'event': [f'playback_stopped_{time.time()}']}
        else:
            logger.error("Cannot call JS: js_trigger_source is not available.")

    def attach_non_audio_callbacks(self):
        logger.debug("Attaching non-audio callbacks.")

    def attach_js_callbacks(self):
        logger.info("Attaching JavaScript callbacks...")
        if self.playback_source:
            js_code = """
                if (this.data && this.data.current_time && this.data.current_time.length > 0) {
                    const currentTime = this.data.current_time[0];
                    if (currentTime !== null && typeof currentTime === 'number') {
                        if (window.NoiseSurveyApp && window.NoiseSurveyApp.synchronizePlaybackPosition) {
                            window.NoiseSurveyApp.synchronizePlaybackPosition(currentTime);
                        }
                    }
                }
            """
            self.playback_source.js_on_change('data', CustomJS(code=js_code))
            logger.info("Attached JavaScript visualization callback to playback_source")

        if self.param_select and self.param_holder:
            js_callback = CustomJS(args=dict(param_holder=self.param_holder), code="""
                const param = cb_obj.value;
                param_holder.text = param;
                if (window.NoiseSurveyApp && window.NoiseSurveyApp.handleParameterChange) {
                    window.NoiseSurveyApp.handleParameterChange(param);
                }
            """)
            self.param_select.js_on_change('value', js_callback)
            logger.debug("Attached JavaScript callback for param_select 'value' change.")

    def cleanup(self):
        logger.info("Cleaning up AppCallbacks...")
        if self._periodic_callback_id and self.doc:
            try:
                self.doc.remove_periodic_callback(self._periodic_callback_id)
            except Exception as e:
                logger.error(f"Error removing periodic callback: {e}", exc_info=True)
            finally:
                self._periodic_callback_id = None
                self.is_periodic_running = False

        if self.audio_handler:
            self.audio_handler.release()
            self.audio_handler = None
        self.doc = None