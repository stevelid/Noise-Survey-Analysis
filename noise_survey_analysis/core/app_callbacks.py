# noise_survey_analysis/core/app_callbacks.py

import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor, wait as futures_wait
from copy import deepcopy
from bokeh.plotting import curdoc
from bokeh.models import ColumnDataSource, Button, Select, Div, CustomJS
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, Optional

# Assuming AudioPlaybackHandler has been updated with set_amplification
from .audio_handler import AudioPlaybackHandler
from .config import STALE_SESSION_RELEASE_SECONDS, STREAMING_DEBOUNCE_MS, STREAMING_ENABLED

logger = logging.getLogger(__name__)

def session_destroyed(session_context):
    """Called by Bokeh when a user session ends."""
    callback_manager = getattr(session_context, '_app_callback_manager', None)
    if callback_manager:
        logger.info(f"Session {session_context.id} destroyed. Cleaning up AppCallbacks.")
        callback_manager.cleanup()
    else:
        logger.warning(f"Session {session_context.id} destroyed, but no AppCallback manager found in session context.")

# JS -> Python session actions (sent with triggerServerSessionAction on the JS side).
# name -> fn(callbacks: AppCallbacks, payload, request_id). The handler reports through
# callbacks._publish_session_status(level, message, done=..., output_path=..., request_id=...)
# and must not clear the command; the dispatcher clears it once after the handler returns.
# A handler that raises is reported to the user as an error status.
_SESSION_ACTIONS: Dict[str, Callable] = {}


def register_session_action(name: str, fn: Callable) -> None:
    """Register (or replace) the handler for session action ``name``."""
    if not isinstance(name, str) or not name or not callable(fn):
        raise ValueError("register_session_action requires a non-empty name and a callable")
    _SESSION_ACTIONS[name] = fn


class AppCallbacks:
    """
    Manages Python-side callbacks for the Bokeh application.
    Connects UI events to application logic.
    """

    _AUDIO_THREAD_PREFIX = 'nsa-audio-cmd'
    # How long cleanup waits for an in-flight audio command before releasing VLC anyway.
    # Commands are bounded (VLC settle sleeps plus a 0.5s monitor join), so this is
    # generous; exceeding it means something is wedged and hanging teardown is worse.
    AUDIO_SHUTDOWN_GRACE_SECONDS = 5.0
    # Status ticks (200ms each) a session may sit with no browser connected before its
    # audio is paused. A refreshed or closed tab never reconnects to its old session,
    # and Bokeh only destroys that session after --unused-session-lifetime, so without
    # this the old player keeps playing for minutes.
    DISCONNECTED_PAUSE_TICKS = 5
    # Seconds a built session may sit with no browser before it is released (see
    # _release_if_stale). Bokeh itself would keep it for --unused-session-lifetime (5 minutes).
    STALE_RELEASE_SECONDS = STALE_SESSION_RELEASE_SECONDS

    def __init__(
        self,
        doc,
        audio_handler: AudioPlaybackHandler | None,
        audio_control_source: ColumnDataSource,
        audio_status_source: ColumnDataSource,
        session_action_source: Optional[ColumnDataSource] = None,
        session_status_source: Optional[ColumnDataSource] = None,
        static_export_request_handler: Optional[Callable[..., dict]] = None,
        save_setup_request_handler: Optional[Callable[..., dict]] = None,
        workspace_autosave=None,
        server_data_handler=None,
        streaming_enabled: bool = STREAMING_ENABLED,
        streaming_debounce_ms: int = STREAMING_DEBOUNCE_MS,
        media_token: Optional[str] = None,
    ):
        self.doc = doc
        # Session token registered with the localhost media server (browser audio backend).
        self.media_token = media_token
        # Callables run once when a stale session is released (e.g. unregistering from the bridge).
        self.release_hooks: list = []
        self._disconnected_since: Optional[float] = None
        self._session_released = False
        self._cleaned_up = False
        self.audio_handler = audio_handler
        self.audio_control_source = audio_control_source
        self.audio_status_source = audio_status_source
        self.session_action_source = session_action_source
        self.session_status_source = session_status_source
        self.static_export_request_handler = static_export_request_handler
        self.save_setup_request_handler = save_setup_request_handler
        # core.workspace_autosave.WorkspaceAutosave for this session (None = autosave off).
        self.workspace_autosave = workspace_autosave
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
        self._annotation_export_in_progress = False
        # Single worker so audio commands stay ordered relative to each other while
        # staying off the document's IOLoop.
        self._audio_command_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=self._AUDIO_THREAD_PREFIX
        )
        self._audio_commands_lock = threading.Lock()
        self._pending_audio_commands = set()
        self._transport_seq = 0
        self._audio_shutdown = False
        self._audio_release_lock = threading.Lock()
        self._audio_released = False
        self._disconnected_ticks = 0

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
        else:
            logger.warning("Audio callbacks not attached: Audio handler missing or audio unavailable.")
        # The tick also watches for a vanished browser, so it runs with or without VLC.
        self._start_periodic_update()

        if self.session_action_source is not None:
            self.session_action_source.on_change('data', self._handle_session_action_command)

        self.attach_js_callbacks()
        logger.info("All callbacks attached.")

    def _handle_audio_control_command(self, attr, old, new):
        if not self.audio_handler or not getattr(self.audio_handler, 'audio_available', False):
            logger.debug("Ignoring audio control command: audio handler missing or unavailable.")
            return

        command = new.get('command', [None])[0]
        if command is None:
            return
        position_id = new.get('position_id', [None])[0]
        value = new.get('value', [None])[0]

        # Opening media and settling VLC blocks for hundreds of milliseconds. Bokeh runs
        # document callbacks on a single IOLoop, so doing that here freezes the whole
        # dashboard - streaming, rendering and status ticks alike - for the duration.
        # Hand it to a single worker so commands still apply in order.
        # Rapid arrow-key taps or position switches queue many play/seek commands behind
        # a slow one. Only the newest matters, so number them and let superseded ones
        # skip themselves when the worker reaches them.
        transport_seq = None
        if command in self._COALESCED_AUDIO_COMMANDS:
            with self._audio_commands_lock:
                self._transport_seq += 1
                transport_seq = self._transport_seq
        self._submit_audio_task(
            command, self._execute_audio_control_command, command, position_id, value, transport_seq
        )

    # Commands where only the most recent pending one needs to run.
    _COALESCED_AUDIO_COMMANDS = ('play', 'seek')

    def _submit_audio_task(self, label, fn, *args):
        """Queue work that touches VLC on the single audio worker, unless shut down."""
        with self._audio_commands_lock:
            if self._audio_shutdown:
                logger.debug("Ignoring audio control command after shutdown: %s", label)
                return
            future = self._audio_command_executor.submit(fn, *args)
            self._pending_audio_commands.add(future)
        future.add_done_callback(self._forget_audio_command)

    def _forget_audio_command(self, future):
        with self._audio_commands_lock:
            self._pending_audio_commands.discard(future)

    def _execute_audio_control_command(self, command, position_id, value, transport_seq=None):
        if self._audio_shutdown:
            # Queued behind a command that outlived the session; VLC may already be gone.
            logger.debug("Skipping audio control command after shutdown: %s", command)
            return
        if transport_seq is not None and transport_seq != self._transport_seq:
            logger.debug("Skipping superseded audio command: %s (%s)", command, transport_seq)
            return
        try:
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

        handler = _SESSION_ACTIONS.get(command)
        if handler is None:
            self._publish_session_status(
                'warning',
                f"Unhandled session action '{command}'.",
                done=True,
                request_id=request_id,
            )
        else:
            try:
                handler(self, payload, request_id)
            except Exception as exc:
                logger.error(f"Session action '{command}' failed: {exc}", exc_info=True)
                self._publish_session_status(
                    'error',
                    f"Session action '{command}' failed: {exc}",
                    done=True,
                    request_id=request_id,
                )
        # The handler never clears the command itself; it is cleared exactly once here.
        self._clear_session_action_command()

    def _session_action_save_setup(self, payload, request_id):
        # Cheap and synchronous -- a small JSON rewrite, no need to thread it.
        if not callable(self.save_setup_request_handler):
            self._publish_session_status(
                'error',
                'Saving setup to config is unavailable in this session.',
                done=True,
                request_id=request_id,
            )
            return
        result = self.save_setup_request_handler(payload=payload, request_id=request_id)
        success = bool(result.get('success')) if isinstance(result, dict) else bool(result)
        message = result.get('message', '') if isinstance(result, dict) else ''
        self._publish_session_status(
            'info' if success else 'error',
            message or ('Setup saved.' if success else 'Saving setup failed.'),
            done=True,
            output_path=result.get('output_path', '') if isinstance(result, dict) else '',
            request_id=request_id,
        )

    def _session_action_generate_static_html(self, payload, request_id):
        if self._static_export_in_progress:
            self._publish_session_status(
                'warning',
                'Static HTML export is already running. Please wait for it to finish.',
                done=True,
                request_id=request_id,
            )
            return

        if not callable(self.static_export_request_handler):
            self._publish_session_status(
                'error',
                'Static HTML export is unavailable in this session.',
                done=True,
                request_id=request_id,
            )
            return

        self._static_export_in_progress = True
        self._publish_session_status(
            'info',
            'Generating static HTML. This can take a minute for large datasets.',
            done=False,
            request_id=request_id,
        )

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

    # One writer thread: autosaves from a session stay in order and never block the Bokeh loop
    # (the write can retry for a second or two while Google Drive holds the file).
    _autosave_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='nsa-autosave')

    @classmethod
    def read_autosave_in_order(cls, config_path, timeout=15.0):
        """Open ``config_path``'s autosave behind every write already queued on the writer thread,
        so a reload never restores the file before the old tab's pagehide flush has landed."""
        from .workspace_autosave import WorkspaceAutosave
        try:
            return cls._autosave_executor.submit(WorkspaceAutosave.for_config, config_path).result(timeout=timeout)
        except Exception as exc:  # timeout / executor shut down: fall back to a plain (locked) read
            logger.warning("Ordered autosave read failed (%s); reading directly.", exc)
            return WorkspaceAutosave.for_config(config_path)

    def _session_action_autosave_workspace(self, payload, request_id):
        """Write the browser's workspace beside the config. Replies with an ``autosave:`` status
        (``output_path`` = ``autosave:<status>:<rev>:<saved_at>``) that the browser consumes
        silently; only conflicts and errors surface as toasts (``done=True``)."""
        autosave = self.workspace_autosave
        if autosave is None or not getattr(autosave, 'available', False):
            self._publish_session_status(
                'info', 'Autosave is off: no config file is attached to this session.',
                done=False, output_path='autosave:unavailable:0:', request_id=request_id)
            return
        snapshot = deepcopy(payload)

        def run_save():
            result = autosave.save(snapshot)
            tag = f"autosave:{result.status}:{result.rev}:{result.saved_at}"
            if result.ok:
                self._publish_session_status('info', result.message, done=False,
                                             output_path=tag, request_id=request_id)
            else:
                self._publish_session_status('warning' if result.status == 'conflict' else 'error',
                                             result.message, done=True, output_path=tag,
                                             request_id=request_id)

        try:
            self._autosave_executor.submit(run_save)
        except RuntimeError as exc:  # executor shut down during interpreter exit
            logger.warning("Autosave could not be scheduled: %s", exc)

    def _handle_annotation_export(self, payload, request_id):
        if self._annotation_export_in_progress:
            self._publish_session_status('warning', 'An annotation export is already running.',
                                         done=True, request_id=request_id)
            return
        # The worker owns a stable lightweight snapshot, even if another session
        # action arrives before it begins reading the queued request.
        payload = deepcopy(payload)
        self._annotation_export_in_progress = True
        self._publish_session_status('info', 'Exporting full-resolution source windows…',
                                     done=False, request_id=request_id)

        def run_export():
            try:
                from .annotation_export_service import export_workspace_request
                result = export_workspace_request(payload)
                self._publish_session_status('info', result['message'], done=True,
                                             output_path=result['output_path'], request_id=request_id)
            except Exception as error:
                logger.exception('Full-resolution annotation export failed')
                self._publish_session_status('error', f'Annotation export failed: {error}',
                                             done=True, request_id=request_id)
            finally:
                self._annotation_export_in_progress = False

        try:
            threading.Thread(target=run_export, name='nsa-annotation-export', daemon=True).start()
        except Exception as error:
            self._annotation_export_in_progress = False
            logger.exception('Could not start annotation export worker')
            self._publish_session_status('error', f'Could not start annotation export: {error}',
                                         done=True, request_id=request_id)

    def _periodic_update_audio_status(self):
        """Periodically updates the audio status source with current playback information."""
        if self._release_if_stale():
            return
        if not self.audio_handler or not getattr(self.audio_handler, 'audio_available', False):
            return

        self._pause_if_disconnected()

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

    def _browser_connection_count(self):
        """WebSocket connections to this document's session, or None outside a server."""
        try:
            count = self.doc.session_context.session.connection_count
        except Exception:
            return None
        return count if isinstance(count, int) else None

    def _pause_if_disconnected(self):
        """Pause playback once the session has had no browser for a short grace period."""
        count = self._browser_connection_count()
        if count is None or count > 0:
            self._disconnected_ticks = 0
            return
        self._disconnected_ticks += 1
        if self._disconnected_ticks == self.DISCONNECTED_PAUSE_TICKS and self.audio_handler.is_playing():
            logger.info("No browser connected to session; pausing audio.")
            self._submit_audio_task('pause (disconnected)', self.audio_handler.pause)

    def _release_if_stale(self, now: Optional[float] = None) -> bool:
        """
        Release this session once its browser has been gone for STALE_RELEASE_SECONDS.

        A refreshed or closed tab never comes back to its old session, but Bokeh only
        destroys that session after --unused-session-lifetime, and until then it holds a full
        DataManager copy, the 1 s logs, a VLC instance and the lazy-load executor. A tab that
        reconnects inside the grace period resets the clock, so a network blip is harmless.

        Returns True once the session has been released (the tick then does nothing more).
        """
        if self._session_released:
            return True
        seconds = self.STALE_RELEASE_SECONDS
        if not seconds or seconds <= 0:
            return False
        count = self._browser_connection_count()
        if count is None or count > 0:
            self._disconnected_since = None
            return False
        now = time.monotonic() if now is None else now
        if self._disconnected_since is None:
            self._disconnected_since = now
            return False
        if now - self._disconnected_since < seconds:
            return False
        self._release_stale_session()
        return True

    def _release_stale_session(self):
        """Free everything a disconnected session holds. Idempotent; session_destroyed later is a no-op."""
        if self._session_released:
            return
        self._session_released = True
        logger.info("No browser for %.0f s; releasing the session's data, audio and workers.",
                    self.STALE_RELEASE_SECONDS)
        try:
            from . import status_console
            status_console.event('info', 'Released a closed tab\'s session (data, audio, workers)')
        except Exception:  # pragma: no cover - console is cosmetic
            pass
        try:
            self.cleanup()
        except Exception as exc:
            logger.warning("Error cleaning up stale session: %s", exc)
        for hook in list(self.release_hooks):
            try:
                hook()
            except Exception as exc:
                logger.warning("Stale-session release hook failed: %s", exc)
        self.release_hooks.clear()
        # Drop references to the data. The handlers below close over the DataManager.
        self.server_data_handler = None
        self.static_export_request_handler = None
        self.save_setup_request_handler = None
        try:
            self.doc.clear()
            self.doc.add_root(Div(
                text="<h2 style='font-family:sans-serif;color:#334155;margin:40px;'>This session was released "
                     "after the browser disconnected. Reload the page to continue.</h2>",
            ))
        except Exception as exc:
            logger.warning("Could not clear the released session's document: %s", exc)
        # The DataManager copy sits in reference cycles (models <-> callbacks); collect now so the
        # memory comes back promptly rather than at the next automatic collection.
        try:
            import gc
            gc.collect()
        except Exception:  # pragma: no cover
            pass

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

    def _shutdown_audio_commands(self):
        """
        Stop accepting audio commands and let any in-flight one finish.

        Ordering matters: `release()` invalidates the VLC player and instance, so a
        command still running on the worker would be calling into freed resources.
        Queued commands are cancelled, and the flag makes any that already escaped
        cancellation return without touching VLC.

        Returns:
            The futures still running when the grace period expired. The caller must not
            release VLC while any of these are outstanding - they hand ownership of the
            release to the command itself.
        """
        with self._audio_commands_lock:
            self._audio_shutdown = True
            pending = list(self._pending_audio_commands)

        for future in pending:
            future.cancel()  # No-op for the one already running.

        still_running = []
        if threading.current_thread().name.startswith(self._AUDIO_THREAD_PREFIX):
            # Waiting on our own executor would deadlock. Only reachable if a command
            # somehow triggers session teardown.
            logger.warning("Audio command shutdown requested from the worker; skipping wait.")
        elif pending:
            _, unfinished = futures_wait(pending, timeout=self.AUDIO_SHUTDOWN_GRACE_SECONDS)
            still_running = list(unfinished)
            if still_running:
                logger.warning(
                    "Audio command still running after %.1fs; deferring VLC release to it.",
                    self.AUDIO_SHUTDOWN_GRACE_SECONDS,
                )

        try:
            self._audio_command_executor.shutdown(wait=False)
        except Exception as e:
            logger.warning(f"Error shutting down audio command executor: {e}")

        return still_running

    def _release_audio_handler_once(self):
        """
        Release the VLC handler, at most once across every caller.

        Both cleanup() and the deferred completion callback can reach here, and freeing
        VLC twice is its own hazard.
        """
        if not self.audio_handler:
            return
        with self._audio_release_lock:
            if self._audio_released:
                return
            self._audio_released = True
        try:
            self.audio_handler.release()
            logger.info("Audio handler released.")
        except Exception as e:
            logger.warning(f"Error releasing audio handler: {e}")

    def _release_audio_when_commands_finish(self, outstanding):
        """
        Hand the release to the commands still holding VLC.

        Whichever finishes last releases. If one never finishes we deliberately keep the
        player and instance alive: leaking them is far safer than freeing memory that a
        live thread is still calling into.
        """
        remaining = {'count': len(outstanding)}
        guard = threading.Lock()

        def on_done(_future):
            with guard:
                remaining['count'] -= 1
                last = remaining['count'] == 0
            if last:
                logger.info("Deferred audio command finished; releasing VLC now.")
                self._release_audio_handler_once()

        for future in outstanding:
            future.add_done_callback(on_done)

    def cleanup(self):
        """Cleans up resources when the session is destroyed (a second call is a no-op)."""
        if getattr(self, '_cleaned_up', False):
            return
        self._cleaned_up = True
        self._stop_periodic_update()
        if self.media_token:
            try:
                from .media_server import unregister_session
                unregister_session(self.media_token)
            except Exception as e:
                logger.debug(f"Could not unregister from the media server: {e}")
            self.media_token = None
        ending = getattr(self.workspace_autosave, 'end', None)
        if callable(ending):
            ending()  # a newer tab may adopt whatever this session last flushed
        # Must precede any release below: a command still on the worker owns VLC.
        outstanding = self._shutdown_audio_commands()
        if self.server_data_handler is not None and hasattr(self.server_data_handler, 'cleanup'):
            try:
                self.server_data_handler.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up server data handler: {e}")

        if outstanding:
            # A command outlived the grace period. It still owns the player, so it - not
            # us - performs the release when it finishes.
            self._release_audio_when_commands_finish(outstanding)
        else:
            self._release_audio_handler_once()
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

        logger.debug(
            "[STREAM CALLBACK] Attached to master_x_range type=%s start=%s end=%s debounce_ms=%s",
            type(master_x_range).__name__,
            getattr(master_x_range, 'start', None),
            getattr(master_x_range, 'end', None),
            self.streaming_debounce_ms,
        )

        def schedule_range_update(attr, old, new):
            self._pending_stream_range = (master_x_range.start, master_x_range.end)
            logger.debug(
                "[STREAM CALLBACK] schedule attr=%s old=%s new=%s current=(%s, %s) timeout_pending=%s",
                attr,
                old,
                new,
                master_x_range.start,
                master_x_range.end,
                self._streaming_timeout_id is not None,
            )
            if self._streaming_timeout_id is not None:
                logger.debug(
                    "[STREAM CALLBACK] coalesced pending range=(%s, %s)",
                    master_x_range.start,
                    master_x_range.end,
                )
                return

            def run_update():
                self._streaming_timeout_id = None
                pending = self._pending_stream_range
                self._pending_stream_range = None
                if not pending:
                    logger.debug("[STREAM CALLBACK] run_update skipped because no pending range remained")
                    return
                start_ms, end_ms = pending
                logger.debug(
                    "[STREAM CALLBACK] run_update dispatching range=(%s, %s)",
                    start_ms,
                    end_ms,
                )
                self.server_data_handler.handle_range_update(start_ms, end_ms)

            self._streaming_timeout_id = self.doc.add_timeout_callback(
                run_update,
                self.streaming_debounce_ms,
            )
            logger.debug(
                "[STREAM CALLBACK] scheduled timeout id=%s pending_range=(%s, %s)",
                self._streaming_timeout_id,
                master_x_range.start,
                master_x_range.end,
            )

        master_x_range.on_change('start', schedule_range_update)
        master_x_range.on_change('end', schedule_range_update)

        # The Chart Offset (s) spinner next to each position is otherwise wired
        # entirely client-side (js_on_change -> handlePositionChartOffsetChange,
        # see components.py) so the Overview chart - fully preloaded in the
        # browser - can apply it without a server round trip. The Log/spectrogram
        # view streams from the server though, so without this the server has no
        # idea a position's data needs shifting and buffers the wrong window once
        # the offset exceeds the small buffer margin. Mirror each spinner's value
        # into the server_data_handler so it can shift what it buffers/streams for
        # that position to match what the client displays.
        for position_id in self.server_data_handler.app_data.positions():
            spinner = self.doc.get_model_by_name(f"chart_offset_spinner_{position_id}")
            if spinner is None:
                continue

            def on_chart_offset_change(attr, old, new, position_id=position_id):
                self.server_data_handler.set_position_chart_offset(position_id, new)

            spinner.on_change('value', on_chart_offset_change)
            # Pick up any initial value already on the widget (e.g. restored from a
            # saved workspace/job config) rather than waiting for the first change.
            if spinner.value:
                self.server_data_handler.set_position_chart_offset(position_id, spinner.value)

        param_select = self.doc.get_model_by_name('global_parameter_selector')
        if param_select:
            def on_param_change(attr, old, new):
                self.server_data_handler.set_selected_parameter(new)
                self.server_data_handler.handle_range_update(master_x_range.start, master_x_range.end)

            param_select.on_change('value', on_param_change)

        logger.debug(
            "[STREAM CALLBACK] initial dispatch range=(%s, %s)",
            master_x_range.start,
            master_x_range.end,
        )
        self.server_data_handler.handle_range_update(master_x_range.start, master_x_range.end)

    def attach_js_callbacks(self):
        pass


# Built-in session actions. Other modules call register_session_action() the same way.
register_session_action("export_annotations", lambda cb, payload, request_id: cb._handle_annotation_export(payload, request_id))
register_session_action("save_setup_to_config", AppCallbacks._session_action_save_setup)
register_session_action("generate_static_html", AppCallbacks._session_action_generate_static_html)
register_session_action("autosave_workspace", AppCallbacks._session_action_autosave_workspace)
