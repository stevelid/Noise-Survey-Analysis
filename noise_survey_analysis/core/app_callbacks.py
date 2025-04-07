# callback.py (Updated)

import logging
import time
from bokeh.plotting import curdoc # Required for add_next_tick_callback, add_periodic_callback
from bokeh.models import ColumnDataSource, Button, Select, Div, CustomJS # Import necessary models
from datetime import datetime, timedelta

# Assuming AudioPlaybackHandler has methods like play, pause, stop, seek_to_time, get_current_position, is_playing, is_in_terminal_state, release, set_current_position
from .audio_handler import AudioPlaybackHandler

logger = logging.getLogger(__name__)

# Define session cleanup hook function globally
def session_destroyed(session_context):
    """Called by Bokeh when a user session ends."""
    # Access the callback manager instance stored on the document's session context
    # The key '_app_callback_manager' must match the key used in app.py
    callback_manager = getattr(session_context, '_app_callback_manager', None)
    if callback_manager:
        logger.info(f"Session {session_context.id} destroyed. Cleaning up AppCallbacks.")
        callback_manager.cleanup()
    else:
        logger.warning(f"Session {session_context.id} destroyed, but no AppCallback manager found in session context.")

class AppCallbacks:
    """
    Manages Python-side callbacks for the Bokeh application.
    Connects UI events (button clicks, source changes) to application logic
    (audio playback, data updates).
    """
    def __init__(self, doc, audio_handler: AudioPlaybackHandler | None, models: dict):
        """
        Initialize a callback manager for the application.

        Parameters:
        doc (Bokeh Document): The Bokeh document to attach callbacks to.
        audio_handler: An instance of AudioPlaybackHandler, or None if audio is disabled.
        models (dict): Dictionary of Bokeh models to attach callbacks to
            (e.g., playback_source, seek_command_source, parameters, etc.).
        """
        self.doc = doc
        self.audio_handler = audio_handler # Can be None

        # Store component references from models
        self.playback_source = models.get('playback_source') # Main timeline source for audio position
        self.seek_command_source = models.get('seek_command_source') # Command channel for seek requests
        self.playback_controls = models.get('playback_controls', {}) # Use default empty dict

        # Get position play buttons if they exist
        self.position_play_buttons = models.get('position_play_buttons', {})

        # Get play request source for position play button requests
        self.play_request_source = models.get('play_request_source')

        # Get spectral parameter controls if they exist
        self.param_select = models.get('param_select')
        self.param_holder = models.get('param_holder')

        self.position_callbacks = []  # List to keep references to position callbacks

        # Track if periodic callback is active
        self._periodic_callback_id = None # Initialize attribute
        self.is_periodic_running = False # Keep track if it's supposed to be running

        # For debouncing seek operations
        self._last_seek_time = 0.0

        # Validate components
        if self.audio_handler:
            if not self.playback_source:
                logger.error("AppCallbacks initialized with audio handler but without 'playback_source' in models!")
            if not self.seek_command_source:
                logger.error("AppCallbacks initialized with audio handler but without 'seek_command_source' in models!")
            if not self.playback_controls:
                logger.error("AppCallbacks initialized with audio handler but without 'playback_controls' in models!")
            if not self.play_request_source:
                logger.error("AppCallbacks initialized with audio handler but without 'play_request_source' in models!")
        else:
            logger.info("AppCallbacks initialized without audio handler. Audio features disabled.")

    def attach_callbacks(self):
        """Attaches all Python callbacks to the document.

        This serves as the main entry point for setting up all interactions.
        """
        # First attach non-audio callbacks (these don't depend on audio handler)
        self.attach_non_audio_callbacks()

        # Then attach audio callbacks if audio is enabled
        if self.audio_handler and self.playback_source and self.playback_controls:
            self.attach_audio_callbacks()

            # Attach callbacks for position-specific play buttons
            if self.position_play_buttons:
                self.attach_position_audio_callbacks()
        else:
            logger.warning("Audio callbacks not attached: Audio handler or required components missing.")

        # Attach JS visualization callbacks (can work with or without audio)
        self.attach_js_visualization_callbacks()
        logger.info("All callbacks attached.")

    def attach_position_audio_callbacks(self):
        """Attaches callbacks for position-specific play buttons."""
        logger.info("Attaching position-specific audio callbacks...")

        for position, button in self.position_play_buttons.items():
            if button is None:
                logger.warning(f"No button found for position '{position}', skipping callback attachment")
                continue

            # --- JavaScript Callback (Handles UI state update immediately) ---
            # Use the position name directly. Ensure position names are JS-safe strings.
            pos_name_js = position # Assuming position names are simple strings like 'SW', 'N' etc.
            # JavaScript callback that triggers handlePositionPlayClick in app.js
            js_code = f"""
                console.log('Position Play Button JS Click for: {pos_name_js}');
                if (window.handlePositionPlayClick) {{
                    window.handlePositionPlayClick('{pos_name_js}');
                }} else {{
                    console.error('window.handlePositionPlayClick function not found!');
                }}
            """
            js_callback = CustomJS(code=js_code)
            button.js_on_click(js_callback) # Attach JS callback here

            logger.debug(f"Added position button JS callback for position '{position}'")

        logger.info(f"Position audio callbacks attached for {len(self.position_play_buttons)} positions")

    def _attach_play_request_handler(self):
        """Attaches callback to handle position play requests from JavaScript."""
        if not self.play_request_source:
            logger.error("Cannot attach play request handler: play_request_source is missing")
            return
            
        logger.info("Attaching play request handler callback...")
        self.play_request_source.on_change('data', self._handle_play_request)
        
    def _handle_play_request(self, attr, old, new):
        """
        Handles position play requests from JavaScript through the play_request_source.
        The source data contains:
        - 'position': The position name to play ('SW', 'N', etc.)
        - 'time': The timestamp (in ms) to start playing from
        """
        if not self.audio_handler:
            logger.warning("Play request handler called but audio handler is not available")
            return
            
        try:
            # Check if we have valid data
            if 'position' not in new or 'time' not in new:
                logger.warning("Play request data missing required fields")
                return
                
            position = new.get('position', [None])[0]
            time_ms = new.get('time', [None])[0]
            
            if not position or not time_ms:
                logger.warning(f"Invalid play request data: position={position}, time={time_ms}")
                return
                
            logger.info(f"Handling play request for position '{position}' at {time_ms}ms")
            
            # 1. Pause any currently playing audio
            if self.audio_handler.is_playing():
                logger.debug(f"Pausing existing playback before starting {position}")
                self.audio_handler.pause()
                
            # 2. Set the new position
            set_pos_success = self.audio_handler.set_current_position(position)
            if not set_pos_success:
                logger.error(f"Failed to set audio position to '{position}'. Aborting playback.")
                self.doc.add_next_tick_callback(self._update_button_states)
                self.doc.add_next_tick_callback(self._call_js_notify_stopped)
                return
                
            # 3. Convert timestamp and start playback
            target_timestamp = datetime.fromtimestamp(time_ms / 1000.0)
            logger.debug(f"Starting playback for position '{position}' at {target_timestamp}")
            
            play_initiated = self.audio_handler.play(timestamp=target_timestamp)
            
            # 4. Update UI based on result
            if play_initiated:
                logger.info(f"Audio playback started for position '{position}'")
                self.doc.add_next_tick_callback(self._update_button_states)
            else:
                logger.warning(f"Failed to start playback for position '{position}'")
                self.doc.add_next_tick_callback(self._call_js_notify_stopped)
                self.doc.add_next_tick_callback(self._update_button_states)
                
            # 5. Clear the request data
            self.play_request_source.data = {'position': [None], 'time': [None]}
            
        except (KeyError, IndexError):
            logger.error("Error in play request handler: Could not extract data", exc_info=True)
            self.doc.add_next_tick_callback(self._call_js_notify_stopped)
        except ValueError as e:
            logger.error(f"Error converting timestamp: {e}", exc_info=True)
            self.doc.add_next_tick_callback(self._call_js_notify_stopped)
        except Exception as e:
            logger.error(f"Unexpected error in play request handler: {e}", exc_info=True)
            self.doc.add_next_tick_callback(self._call_js_notify_stopped)
            self.doc.add_next_tick_callback(self._update_button_states)

    #----------------------------------------------------------------------
    # Audio-related callbacks
    #----------------------------------------------------------------------

    def attach_audio_callbacks(self):
        """Attaches all audio-related Python callbacks."""
        logger.info("Attaching audio-related callbacks...")

        # --- Play/Pause Button Callbacks ---
        self._attach_playback_button_callbacks()

        # --- Seek Handler Callback ---
        self._attach_seek_handler_callback()

        # --- Play Request Handler Callback (for position-specific play) ---
        self._attach_play_request_handler()

        # --- Start Periodic Update ---
        self._start_periodic_update()

    def _attach_playback_button_callbacks(self):
        """Attaches callbacks to main play and pause buttons."""
        play_button = self.playback_controls.get('play_button')
        pause_button = self.playback_controls.get('pause_button')

        if play_button and isinstance(play_button, Button):
            play_button.on_click(self._play_click)
            logger.debug("Attached _play_click to main play_button.")
        else:
             logger.warning("Main Play button not found or invalid in models, cannot attach callback.")

        if pause_button and isinstance(pause_button, Button):
             pause_button.on_click(self._pause_click)
             logger.debug("Attached _pause_click to main pause_button.")
        else:
             logger.warning("Main Pause button not found or invalid in models, cannot attach callback.")

    def _attach_seek_handler_callback(self):
        """Attaches callbacks for seeking triggered by JS chart interactions."""

        if self.seek_command_source:
            self.seek_command_source.on_change('data', self._seek_command_handler)
            logger.debug("Attached _seek_command_handler to seek_command_source 'data' change.")
        else:
            logger.warning("seek_command_source not available, cannot attach command handler.")

    def _seek_command_handler(self, attr, old, new):
        """
        Handles explicit seek commands from JS using the dedicated seek_command_source.
        """
        if not self.audio_handler:
            logger.warning("Seek command handler called but audio handler is not available.")
            return

        try:
            # Only process if target_time exists and is not None
            if 'target_time' not in new or not new['target_time'] or new['target_time'][0] is None:
                # logger.debug("Seek command ignored: target_time missing or None.")
                return

            seek_time_ms = new['target_time'][0]  # Get the target time in milliseconds

            # Log the seek command
            logger.debug(f"Seek command received: {seek_time_ms} ms")

            # Process the seek command
            self._process_seek_command(seek_time_ms)

            # Clear the command to prevent re-processing ONLY IF IT WAS PROCESSED
            # This prevents clearing if debouncing skipped processing
            if time.time() - self._last_seek_time < 0.01: # Check if processing likely occurred
                 self.seek_command_source.data = {'target_time': [None]}

        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Could not extract time from seek_command_source data change: {new}. Error: {e}")
        except Exception as e:
            logger.error(f"Error processing seek command: {e}", exc_info=True)

    def _process_seek_command(self, seek_time_ms):
        """
        Processes a seek command - shared logic.
        """
        if not self.audio_handler:
            return

        # Apply debouncing
        now = time.time()
        debounce_time = 0.05  # seconds
        if now - self._last_seek_time < debounce_time:
            # logger.debug("Seek command debounced.")
            return

        self._last_seek_time = now

        try:
            target_timestamp = datetime.fromtimestamp(seek_time_ms / 1000.0)

            if self.audio_handler.is_playing():
                # --- Seeking While Playing ---
                logger.debug(f"Seeking while playing to timestamp: {target_timestamp}")
                set_time_result = self.audio_handler.seek_to_time(timestamp=target_timestamp)
                if not set_time_result:
                    logger.warning(f"Seek while playing to {target_timestamp} failed in audio handler.")
                # Update playback source immediately to reflect seek target, even if audio handler takes time
                self.playback_source.patch({'current_time': [(0, seek_time_ms)]})
            else:
                # --- Seeking While Paused ---
                # If not playing, just update playback_source. Playback will start from here when play is pressed.
                logger.debug(f"Audio not playing. Updating playback_source to {seek_time_ms} ms for future playback.")
                self.playback_source.patch({'current_time': [(0, seek_time_ms)]})
                # Also attempt to set the position in the paused player if possible
                # Some backends might support setting position while paused.
                seek_paused_result = self.audio_handler.seek_to_time(timestamp=target_timestamp)
                logger.debug(f"Seek while paused result: {seek_paused_result}")


        except ValueError as e:
            logger.error(f"Invalid seek timestamp {seek_time_ms}ms. Error: {e}")
        except Exception as e:
            logger.error(f"Error during seek command processing: {e}", exc_info=True)

    def _start_periodic_update(self):
        """Starts periodic callback to update playback time from audio handler."""
        if self._periodic_callback_id:
             logger.warning("Periodic update already started.")
             return

        update_period_ms = 500 # Adjust period (ms) as needed
        try:
            self._periodic_callback_id = self.doc.add_periodic_callback(self._periodic_update, update_period_ms)
            self.is_periodic_running = True
            logger.info(f"Periodic update callback attached (runs every {update_period_ms}ms). ID: {self._periodic_callback_id}")
        except Exception as e:
             logger.error(f"Failed to add periodic callback: {e}", exc_info=True)
             self._periodic_callback_id = None # Ensure it's None if adding failed
             self.is_periodic_running = False

    def _play_click(self):
        """Handles the MAIN Play button click event."""
        logger.debug("Main Play button clicked.")
        if self.audio_handler and not self.audio_handler.is_playing():
            try:
                # Get the absolute timestamp in milliseconds from the UI source
                current_time_ms = self.playback_source.data['current_time'][0]
                if current_time_ms is None:
                     logger.error("Cannot start main playback: current_time in playback_source is None.")
                     return

                # Convert the absolute timestamp (ms epoch) to a datetime object
                target_timestamp = datetime.fromtimestamp(current_time_ms / 1000.0)

                logger.debug(f"Attempting to play from main button at timestamp: {target_timestamp}")

                # Ensure a default position is set if none was selected via position buttons
                # This relies on the JS setting a default activeAudioPosition if needed
                # Or we can query the JS state here if complex state management is added via JSFunction
                # For now, assume audio_handler has a valid current_position set.
                current_audio_pos = self.audio_handler.get_current_file_position() # Get the position name ('SW', 'N' etc)
                if not current_audio_pos:
                    logger.warning("No current audio position set in handler. Attempting to set a default.")
                    if self.position_play_buttons:
                        first_pos = next(iter(self.position_play_buttons.keys()), None)
                        if first_pos:
                            self.audio_handler.set_current_position(first_pos)
                            logger.info(f"Defaulted audio position to '{first_pos}' for main play.")
                        else:
                            logger.error("Cannot play: No default position available.")
                            return
                    else:
                         logger.error("Cannot play: No position buttons found to determine default position.")
                         return


                # Pass the absolute datetime object to the play method
                play_initiated = self.audio_handler.play(timestamp=target_timestamp)

                if play_initiated:
                    self.doc.add_next_tick_callback(self._update_button_states)
                    logger.info(f"Audio playback requested to start/resume at {target_timestamp}.")
                else:
                    logger.warning(f"Audio playback initiation failed or was blocked for timestamp {target_timestamp}.")
                    # Ensure buttons reflect failed state
                    self.doc.add_next_tick_callback(self._call_js_notify_stopped) # Tell JS it failed
                    self.doc.add_next_tick_callback(self._update_button_states)

            except (KeyError, IndexError):
                 logger.error("Error starting audio playback: Could not get 'current_time' from playback_source data.", exc_info=True)
                 self.doc.add_next_tick_callback(self._call_js_notify_stopped)
            except ValueError as e:
                 logger.error(f"Error converting timestamp from UI: {current_time_ms}. Error: {e}", exc_info=True)
                 self.doc.add_next_tick_callback(self._call_js_notify_stopped)
            except Exception as e:
                 logger.error(f"Unexpected error starting audio playback: {e}", exc_info=True)
                 self.doc.add_next_tick_callback(self._call_js_notify_stopped)
                 self.doc.add_next_tick_callback(self._update_button_states)

        elif not self.audio_handler:
             logger.warning("Play clicked but audio handler is not available.")
        elif self.audio_handler.is_playing():
             logger.debug("Play clicked but audio is already playing.")

    def _pause_click(self):
        """Handles the MAIN Pause button click event."""
        logger.debug("Main Pause button clicked.")
        if self.audio_handler and self.audio_handler.is_playing():
            try:
                self.audio_handler.pause()
                # Update button states via doc callback
                self.doc.add_next_tick_callback(self._update_button_states)
                logger.info("Audio playback paused.")
                # We don't call notifyPlaybackStopped here, as this is an intentional pause.
            except Exception as e:
                 logger.error(f"Error pausing audio playback: {e}", exc_info=True)
        elif not self.audio_handler:
             logger.warning("Pause clicked but audio handler is not available.")
        elif not self.audio_handler.is_playing():
             logger.debug("Pause clicked but audio was not playing.")

    def _update_button_states(self):
        """Updates the enabled/disabled state of Python-side MAIN play/pause buttons."""
        # Note: JS side handles the position button states via _updatePlayButtonsState in app.js
        if not self.audio_handler:
            return

        try:
            is_playing = self.audio_handler.is_playing()
            play_button = self.playback_controls.get('play_button')
            pause_button = self.playback_controls.get('pause_button')

            if play_button and isinstance(play_button, Button):
                play_button.disabled = is_playing
            if pause_button and isinstance(pause_button, Button):
                pause_button.disabled = not is_playing
            # logger.debug(f"Python button states updated: Play disabled={is_playing}, Pause disabled={not is_playing}")
        except Exception as e:
            logger.error(f"Error updating python button states: {e}", exc_info=True)

    def _python_seek_handler(self, attr, old, new):
        """ LEGACY seek handler - Should not be used if seek_command_source is implemented."""
        logger.warning("Legacy _python_seek_handler triggered. Use seek_command_source.")
        # ... (rest of legacy logic) ...

    def _periodic_update(self):
        """
        Periodically checks the audio player's current time and updates the
        playback_source if the player is playing. Also handles end-of-playback.
        """
        if not self.audio_handler or not self.playback_source or not self.is_periodic_running:
            return

        if self.audio_handler.is_playing():
            try:
                current_pos_dt = self.audio_handler.get_current_position() # Expecting datetime object or None
                if current_pos_dt is not None and isinstance(current_pos_dt, datetime):
                    current_time_ms = int(current_pos_dt.timestamp() * 1000)

                    # Update Python-side source data - this triggers JS update via js_on_change
                    if self.playback_source.data.get('current_time', [None])[0] != current_time_ms:
                        self.playback_source.data = {'current_time': [current_time_ms]}
                        # logger.debug(f"Periodic update: Set playback_source to {current_time_ms} ms") # Verbose

                else:
                    # Player is marked as 'playing' but position is None. Check terminal state.
                    # This handles the case where playback finishes between checks.
                    logger.debug("Periodic update: is_playing is True, but get_current_position returned None. Checking terminal state.")
                    if self.audio_handler.is_in_terminal_state():
                        logger.info("Audio handler reached terminal state (e.g., end of file). Stopping playback.")
                        self.audio_handler.pause() # Ensure state consistency
                        # Update Python button states
                        self.doc.add_next_tick_callback(self._update_button_states)
                        # *** TODO Addressed: Explicitly notify JS to reset state ***
                        self.doc.add_next_tick_callback(self._call_js_notify_stopped)
                    # else: # Not terminal, maybe just between files or a transient issue? Log?
                    #    logger.debug("Periodic update: Position None, but not terminal state.")


            except Exception as e:
                 logger.error(f"Error during periodic update: {e}", exc_info=True)
                 # Consider stopping periodic updates on error?
                 # self.cleanup_periodic_callback()
        # else: # Not playing, do nothing in periodic update


    def _call_js_notify_stopped(self):
        """Helper function to schedule the JS notifyPlaybackStopped call."""
        logger.debug("Scheduling JS call: window.notifyPlaybackStopped()")
        # Use js_on_change on a dummy property like 'title' to execute JS code
        # Ensure the document still exists before scheduling
        if self.doc:
             js_code = """
                if (window.notifyPlaybackStopped) {
                    console.log('Python requesting JS state reset via notifyPlaybackStopped.');
                    window.notifyPlaybackStopped();
                } else {
                    console.error('window.notifyPlaybackStopped function not found in JS!');
                }
             """
             # Attaching to 'title' change is a common workaround.
             # We don't actually change the title, just use the event hook.
             self.doc.js_on_change('title', CustomJS(code=js_code))
             # Immediately trigger the dummy change to execute the JS
             # Add a check to prevent infinite loops if title changes trigger this somehow
             current_title = self.doc.title
             self.doc.title = current_title + " " # Add space
             self.doc.title = current_title # Change back immediately

    #----------------------------------------------------------------------
    # Non-audio callbacks (Python)
    #----------------------------------------------------------------------

    def attach_non_audio_callbacks(self):
        """Attaches callbacks that don't depend on the audio handler."""
        logger.debug("Attaching non-audio callbacks...")

        # --- Spectral Parameter Change Callback ---
        # Keep this commented out - JS handles the primary update via _attach_js_param_select_callback
        # self._attach_param_select_callback()

    def _attach_param_select_callback(self):
        """Attaches the parameter selection callback (Python side - DEPRECATED)."""
        if self.param_select and self.param_holder:
            if isinstance(self.param_select, Select) and isinstance(self.param_holder, Div):
                # self.param_select.on_change('value', self._param_select_change) # Keep commented
                logger.debug("Python parameter select callback is available but not attached (JS handles primary update).")
            else:
                logger.warning("param_select or param_holder has unexpected type.")
        else:
            logger.debug("Parameter select/holder missing.")

    def _param_select_change(self, attr, old, new):
        """Handles changes in the spectral parameter selection (Python side - DEPRECATED)."""
        logger.debug(f"Python _param_select_change: '{old}' to '{new}'")
        if self.param_holder and isinstance(self.param_holder, Div):
             try:
                 self.param_holder.text = str(new) # Update hidden Div for potential Python-side access
                 logger.info(f"Updated param_holder text (Python side) to: {new}")
             except Exception as e:
                  logger.error(f"Failed to update param_holder text (Python side): {e}", exc_info=True)

    #----------------------------------------------------------------------
    # JavaScript callbacks (Attached from Python)
    #----------------------------------------------------------------------

    def attach_js_visualization_callbacks(self):
        """Attaches all JavaScript callbacks for visualization updates."""
        logger.info("Attaching JavaScript visualization callbacks...")

        # --- Playback visualization update ---
        self._attach_js_playback_position_callback()

        # --- Parameter selection callback ---
        self._attach_js_param_select_callback()

    def _attach_js_playback_position_callback(self):
        """Attaches JavaScript callback to update visualization when playback position changes."""
        if self.playback_source:
            # JS callback triggered when self.playback_source.data changes
            js_code = """
                // Get the current time from the updated data
                if (this.data && this.data.current_time && this.data.current_time.length > 0) {
                    const currentTime = this.data.current_time[0];
                    // Check if time is valid before calling sync
                    if (currentTime !== null && typeof currentTime === 'number') {
                        // console.log(`JS: playback_source changed, calling synchronizePlaybackPosition(${currentTime})`);
                        if (window.synchronizePlaybackPosition && typeof window.synchronizePlaybackPosition === 'function') {
                            window.synchronizePlaybackPosition(currentTime);
                        } else {
                            console.error('window.synchronizePlaybackPosition function not available');
                        }
                    } else {
                         // console.log('JS: playback_source changed, but currentTime is null or invalid.');
                    }
                } else {
                    // console.log('JS: playback_source changed, but data format is unexpected.');
                }
            """
            js_callback = CustomJS(code=js_code)
            self.playback_source.js_on_change('data', js_callback)
            logger.info("Attached JavaScript visualization callback to playback_source")
        else:
            logger.warning("Cannot attach JavaScript visualization callbacks: playback_source is missing")

    def _attach_js_param_select_callback(self):
        """Attaches JavaScript callback for parameter selection change."""
        if self.param_select and self.param_holder:
            if isinstance(self.param_select, Select) and isinstance(self.param_holder, Div):
                # Pass the param_holder model to the JS callback args
                js_callback = CustomJS(args=dict(param_holder=self.param_holder), code="""
                    // Get the new parameter value from the Select widget that triggered the callback
                    const param = cb_obj.value;
                    console.log('JS: Param select JS callback triggered. New value:', param);

                    // Update the parameter holder div's text property
                    // The 'param_holder' arg comes from the args dict passed to CustomJS
                    if (param_holder) {
                         param_holder.text = param;
                         // console.log('JS: Updated param_holder.text to:', param);
                    } else {
                         console.warn('JS: param_holder model not found in callback args.');
                    }

                    // Call the main JavaScript handleParameterChange function in NoiseSurveyApp
                    if (window.NoiseSurveyApp && typeof window.NoiseSurveyApp.handleParameterChange === 'function') {
                        window.NoiseSurveyApp.handleParameterChange(param);
                    } else {
                        console.error('window.NoiseSurveyApp.handleParameterChange function not available');
                    }
                """)

                self.param_select.js_on_change('value', js_callback)
                logger.debug("Attached JavaScript callback for param_select 'value' change using NoiseSurveyApp.handleParameterChange")
            else:
                logger.warning("param_select or param_holder has unexpected type, cannot attach JS callback.")
        else:
            logger.debug("Parameter select/holder missing, skipping JS parameter change callback attachment.")

    #----------------------------------------------------------------------
    # Cleanup Methods
    #----------------------------------------------------------------------

    def cleanup_periodic_callback(self):
        """Removes the periodic callback."""
        if self._periodic_callback_id and self.doc:
            try:
                self.doc.remove_periodic_callback(self._periodic_callback_id)
                logger.debug(f"Removed periodic callback: {self._periodic_callback_id}")
            except ValueError:
                logger.warning(f"Could not remove periodic callback {self._periodic_callback_id}, might have already been removed.")
            except Exception as e:
                logger.error(f"Error removing periodic callback: {e}", exc_info=True)
            finally:
                self._periodic_callback_id = None
                self.is_periodic_running = False

    def cleanup(self):
         """Removes callbacks and cleans up resources (e.g., audio handler)."""
         logger.info("Cleaning up AppCallbacks...")
         self.cleanup_periodic_callback() # Remove periodic callback first

         if self.audio_handler:
             try:
                  self.audio_handler.release() # Release audio resources
                  logger.info("Audio handler resources released.")
             except Exception as e:
                  logger.error(f"Error releasing audio handler resources: {e}", exc_info=True)
             self.audio_handler = None # Clear reference

         # Clear references to models to help garbage collection
         # self.models = {} # Don't clear models dict if it's shared/owned elsewhere
         self.playback_source = None
         self.seek_command_source = None
         self.play_request_source = None
         self.playback_controls = {}
         self.position_play_buttons = {}
         self.param_holder = None
         self.param_select = None
         self.position_callbacks = []
         self.doc = None # Clear doc reference

         logger.info("AppCallbacks cleanup finished.")

# --- End of AppCallbacks class ---
