#TODO: when playback stops because of end of file, the JS play button needs to be reset to enabled. 

import logging
import time
from bokeh.plotting import curdoc # Required for add_next_tick_callback, add_periodic_callback
from bokeh.models import ColumnDataSource, Button, Select, Div, CustomJS # Import necessary models
from datetime import datetime, timedelta

# Assuming AudioPlaybackHandler has methods like play, pause, seek, get_time, is_playing, release
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
        Initializes the Callback Manager.

        Args:
            doc: The Bokeh document instance.
            audio_handler: An instance of AudioPlaybackHandler, or None if audio is disabled.
            models (dict): A dictionary containing necessary Bokeh models created by
                           DashboardBuilder (e.g., playback_source, playback_controls).
        """
        self.doc = doc
        self.audio_handler = audio_handler # Can be None
        self.models = models # Store the dictionary of models

        # Extract required models for easier access, handle potential None values
        self.playback_source = models.get('playback_source')
        self.seek_command_source = models.get('seek_command_source')  # New seek command source
        self.playback_controls = models.get('playback_controls', {}) # Use default empty dict
        # Click lines and labels are mainly for JS, but might be useful here later
        # self.click_lines = models.get('click_lines', {})
        # self.labels = models.get('labels', {})
        self.param_holder = models.get('param_holder') # For spectral param changes
        self.param_select = models.get('param_select') # The dropdown itself

        # Log warnings if essential components for enabled features are missing
        if self.audio_handler:
            if not self.playback_source:
                 logger.error("AppCallbacks initialized with audio handler but without 'playback_source' in models!")
            if not self.seek_command_source:
                 logger.error("AppCallbacks initialized with audio handler but without 'seek_command_source' in models!")
            if not self.playback_controls:
                 logger.error("AppCallbacks initialized with audio handler but without 'playback_controls' in models!")
        else:
            logger.info("AppCallbacks initialized without audio handler. Audio features disabled.")

        if self.param_select and not self.param_holder:
             logger.warning("AppCallbacks initialized with 'param_select' but without 'param_holder'. Spectral updates might not work.")

        # Internal state
        self._periodic_callback_id = None
        self._last_seek_time = 0 # To prevent rapid seeking updates from JS

    def attach_callbacks(self):
        """
        Main method to attach all callbacks based on available components.
        """
        logger.info("Attaching application callbacks...")
        
        # First attach non-audio callbacks (these don't depend on audio handler)
        self.attach_non_audio_callbacks()
        
        # Then attach audio callbacks if audio is enabled
        if self.audio_handler and self.playback_source and self.playback_controls:
            self.attach_audio_callbacks()
        else:
            logger.warning("Audio callbacks not attached: Audio handler or required components missing.")
            
        # Attach JS visualization callbacks (can work with or without audio)
        self.attach_js_visualization_callbacks()
        
        logger.info("Application callbacks attached successfully.")

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
        
        # --- Start Periodic Update ---
        self._start_periodic_update()
    
    def _attach_playback_button_callbacks(self):
        """Attaches callbacks to play and pause buttons."""
        play_button = self.playback_controls.get('play_button')
        pause_button = self.playback_controls.get('pause_button')

        if play_button and isinstance(play_button, Button):
            play_button.on_click(self._play_click)
            logger.debug("Attached _play_click to play_button.")
        else:
             logger.warning("Play button not found or invalid in models, cannot attach callback.")

        if pause_button and isinstance(pause_button, Button):
             pause_button.on_click(self._pause_click)
             logger.debug("Attached _pause_click to pause_button.")
        else:
             logger.warning("Pause button not found or invalid in models, cannot attach callback.")
    
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
        This provides a clean separation between state updates and user commands.
        """
        if not self.audio_handler:
            logger.warning("Seek command handler called but audio handler is not available.")
            return

        try:
            # Only process if target_time exists and is not None
            if 'target_time' not in new or new['target_time'][0] is None:
                return
                
            seek_time_ms = new['target_time'][0]  # Get the target time in milliseconds
            
            # Log the seek command
            logger.debug(f"Seek command received: {seek_time_ms} ms")
            
            # Process the seek command
            self._process_seek_command(seek_time_ms)
            
            # Clear the command to prevent re-processing
            self.seek_command_source.data = {'target_time': [None]}
            
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Could not extract time from seek_command_source data change: {new}. Error: {e}")
        except Exception as e:
            logger.error(f"Error processing seek command: {e}", exc_info=True)
    
    def _process_seek_command(self, seek_time_ms):
        """
        Processes a seek command - shared logic for both seek handlers.
        
        Args:
            seek_time_ms: The target seek time in milliseconds (absolute timestamp)
        """
        if not self.audio_handler:
            return
            
        # Apply debouncing
        now = time.time()
        debounce_time = 0.05  # seconds
        if now - self._last_seek_time < debounce_time:
            return
            
        self._last_seek_time = now
        
        try:
            if self.audio_handler.is_playing():
                # --- Seeking While Playing ---
                # Calculate offset relative to the start of the current file
                target_timestamp = datetime.fromtimestamp(seek_time_ms / 1000.0)
                if target_timestamp and isinstance(target_timestamp, datetime):     
                    set_time_result = self.audio_handler.seek_to_time(timestamp=target_timestamp)
                else:
                    logger.error("Cannot seek while playing: target_seek_time is not available.")
            else:
                # If not playing, we'll update playback_source which will be used when play is pressed
                logger.debug(f"Audio not playing. Updating playback_source to {seek_time_ms} ms for future playback.")
                self.playback_source.patch({'current_time': [(0, seek_time_ms)]})
                
        except Exception as e:
            logger.error(f"Error during seek command processing: {e}", exc_info=True)
    
    def _start_periodic_update(self):
        """Starts periodic callback to update playback time from audio handler."""
        # Periodically update playback time from audio_handler to playback_source
        # Adjust period (ms) as needed for responsiveness vs performance
        update_period_ms = 500
        try:
            self._periodic_callback_id = self.doc.add_periodic_callback(self._periodic_update, update_period_ms)
            logger.info(f"Periodic update callback attached (runs every {update_period_ms}ms). ID: {self._periodic_callback_id}")
        except Exception as e:
             logger.error(f"Failed to add periodic callback: {e}", exc_info=True)
             self._periodic_callback_id = None # Ensure it's None if adding failed
    
    def _play_click(self):
        """Handles the Play button click event."""
        logger.debug("Play button clicked.")
        if self.audio_handler and not self.audio_handler.is_playing():
            try:
                # Get the absolute timestamp in milliseconds from the UI source
                current_time_ms = self.playback_source.data['current_time'][0]

                # Convert the absolute timestamp (ms epoch) to a datetime object
                target_timestamp = datetime.fromtimestamp(current_time_ms / 1000.0) # More direct conversion

                logger.debug(f"Attempting to play directly from calculated target timestamp: {target_timestamp}")

                # Pass the absolute datetime object to the play method
                play_initiated = self.audio_handler.play(timestamp=target_timestamp)

                # Update button states via doc callback to ensure it happens in the next tick
                if play_initiated: # Only update states if play was successfully initiated (not blocked by lockout)
                     self.doc.add_next_tick_callback(self._update_button_states)
                     logger.info(f"Audio playback requested to start/resume at {target_timestamp}.")
                else:
                     logger.warning(f"Audio playback initiation failed or was blocked (e.g., by lockout) for timestamp {target_timestamp}.")


            except (KeyError, IndexError):
                 logger.error("Error starting audio playback: Could not get 'current_time' from playback_source data.", exc_info=True)
            except ValueError as e:
                 # Catch potential errors from fromtimestamp (e.g., invalid timestamp value)
                 logger.error(f"Error converting timestamp from UI: {current_time_ms}. Error: {e}", exc_info=True)
            except AttributeError as e:
                 # Catch if media_start_time or play() doesn't exist on audio_handler (should exist based on provided code)
                 logger.error(f"Error starting audio playback: Audio handler missing expected method or attribute. Details: {e}", exc_info=True)
            except TypeError as e:
                 # Catch potential issues with timedelta calculation or if play() signature is wrong
                 logger.error(f"TypeError during playback start. Check timestamp conversion or play() signature: {e}", exc_info=True)
            except Exception as e:
                 logger.error(f"Unexpected error starting audio playback: {e}", exc_info=True)

        elif not self.audio_handler:
             logger.warning("Play clicked but audio handler is not available.")
        # If already playing, do nothing (or log it)
        elif self.audio_handler.is_playing():
            logger.debug("Play clicked but audio is already playing.")

    def _pause_click(self):
        """Handles the Pause button click event."""
        logger.debug("Pause button clicked.")
        if self.audio_handler and self.audio_handler.is_playing():
            try:
                self.audio_handler.pause()
                # Update button states via doc callback
                self.doc.add_next_tick_callback(self._update_button_states)
                logger.info("Audio playback paused.")
            except Exception as e:
                 logger.error(f"Error pausing audio playback: {e}", exc_info=True)
        elif not self.audio_handler:
             logger.warning("Pause clicked but audio handler is not available.")

    def _update_button_states(self):
        """Updates the enabled/disabled state of play/pause buttons."""
        if not self.audio_handler: # Should not happen if called from play/pause, but safeguard
            return

        try:
            is_playing = self.audio_handler.is_playing()
            play_button = self.playback_controls.get('play_button')
            pause_button = self.playback_controls.get('pause_button')

            if play_button and isinstance(play_button, Button):
                play_button.disabled = is_playing
            if pause_button and isinstance(pause_button, Button):
                pause_button.disabled = not is_playing
            # logger.debug(f"Button states updated: Play disabled={is_playing}, Pause disabled={not is_playing}") # Can be verbose
        except Exception as e:
            logger.error(f"Error updating button states: {e}", exc_info=True)

    def _python_seek_handler(self, attr, old, new):
        """
        Handles seek requests originating from JS chart interactions updating playback_source.
        Updates the audio playback position only if audio is playing.
        
        Note: This handler is maintained for backward compatibility. New code should
        use the seek_command_source and _seek_command_handler instead.
        """
        
        if not self.audio_handler:
            logger.warning("Seek handler called but audio handler is not available.")
            return

        try:
            current_time_ms = new['current_time'][0] # Expecting time in milliseconds
        except (KeyError, IndexError, TypeError) as e:
            logger.error(f"Could not extract time from playback_source data change: {new}. Error: {e}")
            return

        # Log the legacy seek method
        logger.debug(f"Legacy seek handler triggered via playback_source change to: {current_time_ms} ms")
        
        # Use the shared seek command processing logic
        self._process_seek_command(current_time_ms)

    def _periodic_update(self):
        """
        Periodically checks the audio player's current time and updates the
        playback_source if the player is playing. This drives the JS updates.
        """
        if not self.audio_handler or not self.playback_source:
            # Should not happen if periodic callback was started correctly, but safeguard
            # logger.warning("Periodic update skipped: audio_handler or playback_source missing.")
            return

        if self.audio_handler.is_playing():

            try:
                current_pos = self.audio_handler.get_current_position()
                if current_pos is not None:
                    current_time_ms = int(current_pos.timestamp() * 1000)
                    
                    # Update Python-side data
                    # Replace patch with complete data replacement to trigger js_on_change
                    self.playback_source.data = {'current_time': [current_time_ms]}
                    
                        
                        # Call the JS updateTapLinePositions function directly
                        # The NoiseSurveyApp JS will handle the visual update via the
                        # already attached _setupPlaybackListener callback on playback_source
                        
                        # No need for CustomJS execution - the source update triggers the
                        # JavaScript callback that updates visuals

                        
                else:
                    # Player might have stopped unexpectedly (e.g., end of file or error)
                    logger.info(f"Periodic update: get_current_position returned None. Checking terminal state.")
                    # Check if the player genuinely stopped or errored, not just finished a segment
                    if self.audio_handler.is_in_terminal_state():
                        self.audio_handler.pause() # Ensure state consistency in the handler
                        self.doc.add_next_tick_callback(self._update_button_states) # Update UI
                    # else: # Player might just be between files, monitor thread handles this
                        # pass

            except Exception as e:
                 logger.error(f"Error during periodic update: {e}", exc_info=True)
                 # Consider stopping periodic updates on error?
                 # self.cleanup_periodic_callback()
    
    #----------------------------------------------------------------------
    # Non-audio callbacks (Python)
    #----------------------------------------------------------------------
    
    def attach_non_audio_callbacks(self):
        """Attaches callbacks that don't depend on the audio handler."""
        logger.debug("Attaching non-audio callbacks...")
        
        # --- Spectral Parameter Change Callback ---
        self._attach_param_select_callback()
        
        # Add other non-audio callbacks here in the future
    
    def _attach_param_select_callback(self):
        """Attaches the parameter selection callback."""
        if self.param_select and self.param_holder:
            if isinstance(self.param_select, Select) and isinstance(self.param_holder, Div):
                # We'll use the JS callback instead of the Python callback for better responsiveness
                # Keep the Python callback as a reference/fallback
                # self.param_select.on_change('value', self._param_select_change)
                logger.debug("Parameter select callback attached via JS (see JS callbacks section)")
            else:
                logger.warning("param_select or param_holder has unexpected type, cannot attach change callback.")
        else:
            logger.debug("Parameter select/holder missing, skipping parameter change callback attachment.")
    
    def _param_select_change(self, attr, old, new):
        """Handles changes in the spectral parameter selection dropdown."""
        logger.debug(f"Parameter selection changed from '{old}' to '{new}'")
        if self.param_holder and isinstance(self.param_holder, Div):
             # Update the hidden Div; JS callbacks on the spectrograms listen to this Div's text.
             try:
                self.param_holder.text = str(new) # Ensure it's a string
                logger.info(f"Updated param_holder text to: {new}")
             except Exception as e:
                  logger.error(f"Failed to update param_holder text: {e}", exc_info=True)
        else:
             logger.warning("param_holder model not found or invalid, cannot update selection state for JS.")
    
    #----------------------------------------------------------------------
    # JavaScript callbacks
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
            # Create a direct JS callback that will update visualization when playback_source changes
            js_callback = CustomJS(code="""
                // Get the current time from the updated data
                if (this.data.current_time && this.data.current_time.length > 0) {
                    const currentTime = this.data.current_time[0];
                    if (window.synchronizePlaybackPosition && typeof window.synchronizePlaybackPosition === 'function') {
                        window.synchronizePlaybackPosition(currentTime);
                    } else {
                        console.error('NoiseSurveyApp.synchronizePlaybackPosition function not available');
                    }
                }
            """)
            
            # Attach the callback to the 'data' property changes
            self.playback_source.js_on_change('data', js_callback)
            logger.info("Attached JavaScript visualization callback to playback_source")
        else:
            logger.warning("Cannot attach JavaScript visualization callbacks: playback_source is missing")
    
    def _attach_js_param_select_callback(self):
        """Attaches JavaScript callback for parameter selection change."""
        if self.param_select and self.param_holder:
            if isinstance(self.param_select, Select) and isinstance(self.param_holder, Div):
                # Create a JavaScript callback using handleParameterChange from app.js
                js_callback = CustomJS(code="""
                    // Get the new parameter value
                    const param = cb_obj.value;
                    
                    // Update the parameter holder div to maintain Python-side state
                    if (window.selectedParamHolder) {
                        window.selectedParamHolder.text = param;
                    }
                    
                    // Call the JavaScript handleParameterChange function
                    if (window.NoiseSurveyApp && typeof window.NoiseSurveyApp.handleParameterChange === 'function') {
                        window.NoiseSurveyApp.handleParameterChange(param);
                    } else {
                        console.error('NoiseSurveyApp.handleParameterChange function not available');
                    }
                """)
                
                # Attach the JS callback to the param_select change event
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
                 # This can happen if the callback was already removed or session ended abruptly
                 logger.warning(f"Could not remove periodic callback {self._periodic_callback_id}, might have already been removed or session ended.")
            except Exception as e:
                 logger.error(f"Error removing periodic callback: {e}", exc_info=True)
            finally:
                self._periodic_callback_id = None # Ensure it's marked as removed

    def cleanup(self):
         """Removes callbacks and cleans up resources (e.g., audio handler)."""
         logger.info("Cleaning up AppCallbacks...")
         self.cleanup_periodic_callback() # Remove periodic callback first

         if self.audio_handler:
             try:
                 self.audio_handler.release() # Release VLC resources
                 logger.info("Audio handler resources released.")
             except Exception as e:
                  logger.error(f"Error releasing audio handler resources: {e}", exc_info=True)
             self.audio_handler = None # Clear reference

         # Clear references to models to help garbage collection
         self.models = {}
         self.playback_source = None
         self.playback_controls = {}
         self.param_holder = None
         self.param_select = None
         self.doc = None # Clear doc reference

         logger.info("AppCallbacks cleanup finished.")

# --- End of AppCallbacks class ---

# Reminder: In create_app (app.py), after creating callback_manager:
# 1. Store the instance on the session context:
#    doc.session_context._app_callback_manager = callback_manager
# 2. Register the session destroyed handler:
#    doc.on_session_destroyed(session_destroyed) # Use the global function defined above 