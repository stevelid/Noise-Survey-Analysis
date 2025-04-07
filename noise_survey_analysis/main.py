import logging
from bokeh.plotting import curdoc
from bokeh.layouts import LayoutDOM # Import base layout class for assertions
from bokeh.models import Div, ColumnDataSource # Import for assertions and error messages
import pandas as pd
import numpy as np  # Import numpy for array operations
import os
from bokeh.resources import CDN
from bokeh.embed import file_html  # Add import for standalone HTML generation

# Don't reconfigure logging - use the configuration from the parent process
logger = logging.getLogger(__name__)

# Import refactored modules and configuration
try:
    # Assuming media_path will be added to config.py
    from .core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS, GENERAL_SETTINGS, REQUIRED_SPECTRAL_PREFIXES
    from .core.data_loaders import load_and_process_data
    from .core.data_processors import synchronize_time_range, prepare_spectral_data_for_js
    from .core.audio_handler import AudioPlaybackHandler
    from .core.app_callbacks import AppCallbacks, session_destroyed
    from .core.utils import add_error_to_doc  # Import our new error handling function
    from .visualization.dashboard import DashboardBuilder
except ImportError as e:
    # Handle potential import errors if structure is different or files don't exist yet
    logging.basicConfig(level=logging.ERROR) # Ensure logging is configured for early errors
    logging.error(f"Failed to import necessary application modules: {e}", exc_info=True)
    # Add a placeholder to the doc if possible, otherwise the app might fail silently
    doc = curdoc()
    try:
        error_div = Div(text=f"<h3 style='color:red;'>Critical Error: Failed to import application modules ({e}). Check installation and paths.</h3>", height=100, width=800)
        doc.add_root(error_div)
    except:
        # If we can't even add an error div, there's not much we can do
        logger.error(f"Failed to add error div: {e}", exc_info=True)
        pass
    raise # Re-raise error to stop execution if imports fail catastrophically


# --- Development Flag (Set to False for Production) ---
# This allows easily disabling all temporary asserts
_DEV_ASSERTS_ENABLED = True # TODO: Set to False for production deployment
# ---

def create_app(doc, custom_data_sources=None, enable_audio=True):
    """
    Sets up the Bokeh application document.
    Orchestrates data loading, visualization building, and callback attachment.
    
    Parameters:
    -----------
    doc : bokeh.document.Document
        The Bokeh document to attach the UI components to.
    custom_data_sources : list, optional
        A list of data source dictionaries to use instead of the default ones.
        If None, the default data sources from config will be used.
    enable_audio : bool, optional
        Whether to enable audio playback. Default is True.
    """
    # Don't override logging level here - it should be inherited from run_app.py
    logger.info("Setting up Bokeh application...")

    # 1. Load and Process Data
    position_data = None
    try:
        position_data = load_and_process_data(custom_data_sources) # Modified to use custom sources if provided
        if _DEV_ASSERTS_ENABLED:
            assert isinstance(position_data, dict), f"load_and_process_data returned type {type(position_data)}, expected dict"

        if CHART_SETTINGS.get("sync_ranges", False) and position_data and len(position_data) > 1:
             logger.info("Synchronizing time ranges across positions.")
             position_data = synchronize_time_range(position_data)
             if _DEV_ASSERTS_ENABLED:
                 assert isinstance(position_data, dict), f"synchronize_time_range returned type {type(position_data)}, expected dict"
        elif len(position_data or {}) <= 1:
             logger.info("Skipping time range synchronization (0 or 1 position).")
    except Exception as e:
        add_error_to_doc(doc, "Failed during data loading/processing. Check logs and configuration.", e, height=100)
        return # Stop execution

    # Exit gracefully if no data loaded
    if not position_data:
        add_error_to_doc(doc, "No valid data loaded. Check configuration (config.py) and file paths/content.")
        logger.error("No data loaded, exiting app setup.")
        return
    
    if _DEV_ASSERTS_ENABLED:
        assert position_data, "Position data is unexpectedly empty after loading check."
        logger.debug(f"Data loaded for positions: {list(position_data.keys())}")

    # 2. Initialize Core Components (Audio Handler)
    audio_handler = None
    
    # Only initialize audio if enabled
    if enable_audio:
        # Check if any position has audio paths defined
        positions_with_audio = {pos: data.get('audio') for pos, data in position_data.items() 
                               if data.get('audio') and os.path.exists(data.get('audio'))}
        
        if len(positions_with_audio) > 0:
            try:
                # Use the first position's audio path as the default media path
                pos, audio_path = next(iter(positions_with_audio.items()))
                logger.info(f"Initializing AudioPlaybackHandler with position '{pos}' media path as default: {audio_path}")
                audio_handler = AudioPlaybackHandler(audio_path)
                
                # Now add all position-specific audio paths
                if audio_handler and positions_with_audio:
                    for pos, audio_path in positions_with_audio.items():
                        logger.info(f"Adding position-specific audio path for '{pos}': {audio_path}")
                        audio_handler.add_position_media_path(pos, audio_path)
                    
                    # Log summary
                    logger.info(f"AudioPlaybackHandler initialized with {len(positions_with_audio)} position-specific audio paths")
                    
            except ImportError:
                 logger.warning("python-vlc library not found or failed to import. Audio playback will be disabled.", exc_info=False)
                 audio_handler = None
            except Exception as e:
                logger.error(f"Failed to initialize AudioPlaybackHandler: {e}", exc_info=True)
                audio_handler = None
        else:
            logger.warning("No audio paths found in position data and no 'media_path' in GENERAL_SETTINGS. Audio playback will be disabled.")

    if _DEV_ASSERTS_ENABLED:
        assert audio_handler is None or isinstance(audio_handler, AudioPlaybackHandler), f"Audio handler has unexpected type: {type(audio_handler)}"
        if audio_handler is None:
             logger.warning("DEV_ASSERT: Proceeding without Audio Handler.")
        else:
             logger.info("DEV_ASSERT: Audio Handler initialized.")

    # 3. Build Visualization and UI Layout using DashboardBuilder
    main_layout = None
    try:
        logger.info("Building dashboard layout...")
        dashboard_builder = DashboardBuilder(
            position_data=position_data,
            chart_settings=CHART_SETTINGS,
            visualization_settings=VISUALIZATION_SETTINGS,
            audio_handler_available=(audio_handler is not None)
        )
        if _DEV_ASSERTS_ENABLED:
            assert isinstance(dashboard_builder, DashboardBuilder), "DashboardBuilder instantiation failed or returned wrong type"

        main_layout = dashboard_builder.build()
        logger.info("Dashboard layout built.")

        # --- Temporary Asserts for Builder Output ---
        if _DEV_ASSERTS_ENABLED:
            logger.debug("Running DEV_ASSERTS on DashboardBuilder output...")
            assert isinstance(main_layout, LayoutDOM), f"Dashboard builder.build() did not return a valid layout (got {type(main_layout)})"

            bokeh_models = dashboard_builder.bokeh_models
            assert isinstance(bokeh_models, dict), f"Dashboard builder.bokeh_models is not a dictionary (got {type(bokeh_models)})"

            # Essential keys checks...
            essential_keys = ['all_charts', 'all_sources', 'charts_for_js', 'click_lines', 'labels']
            if audio_handler:
                 essential_keys.extend(['playback_source', 'playback_controls'])
            
            has_spectral = any(isinstance(pos_info.get('spectral'), pd.DataFrame) and not pos_info.get('spectral').empty 
                              for pos_info in position_data.values())
            if has_spectral:
                 essential_keys.extend(['param_select', 'param_holder', 'freq_bar_source', 'freq_bar_x_range'])

            missing_keys = [key for key in essential_keys if key not in bokeh_models]
            assert not missing_keys, f"Essential keys missing from models in dashboard_builder.bokeh_models: {missing_keys}"
            logger.debug(f"Essential keys check passed. Found: {list(bokeh_models.keys())}")

            # Type checks...
            assert isinstance(bokeh_models.get('all_charts'), list), f"'all_charts' in models is not a list (got {type(bokeh_models.get('all_charts'))})"
            assert isinstance(bokeh_models.get('all_sources'), dict), f"'all_sources' in models is not a dict (got {type(bokeh_models.get('all_sources'))})"
            if audio_handler:
                assert isinstance(bokeh_models.get('playback_source'), ColumnDataSource), f"'playback_source' has wrong type (got {type(bokeh_models.get('playback_source'))})"
                assert isinstance(bokeh_models.get('playback_controls'), dict), f"'playback_controls' is not a dict (got {type(bokeh_models.get('playback_controls'))})"
            if has_spectral:
                 assert bokeh_models.get('param_select') is not None, "'param_select' is missing/None"
                 assert bokeh_models.get('param_holder') is not None, "'param_holder' is missing/None"
            logger.debug("DEV_ASSERTS on builder output passed.")
        # --- End Temporary Asserts ---

    except Exception as e:
        add_error_to_doc(doc, "Failed to build dashboard layout. Check logs.", e, height=100)
        return

    # 4. Setup Callbacks using AppCallbacks
    callback_manager = None
    if audio_handler and 'playback_source' in bokeh_models and 'playback_controls' in bokeh_models:
        logger.info("Audio handler and necessary models found, setting up callbacks...")
        if _DEV_ASSERTS_ENABLED:
            assert audio_handler is not None, "DEV_ASSERT: Pre-condition failed - audio_handler is None"
            assert bokeh_models.get('playback_source') is not None, "DEV_ASSERT: Pre-condition failed - playback_source model is None"
            assert bokeh_models.get('playback_controls') is not None, "DEV_ASSERT: Pre-condition failed - playback_controls model is None"
        try:
            callback_manager = AppCallbacks(
                doc=doc,
                audio_handler=audio_handler,
                models=bokeh_models
            )
            if _DEV_ASSERTS_ENABLED:
                assert isinstance(callback_manager, AppCallbacks), "AppCallbacks instantiation failed or returned wrong type"

            callback_manager.attach_callbacks()
            logger.info("Application callbacks attached successfully.")

            # Store callback manager on session context for cleanup
            try:
                doc.session_context._app_callback_manager = callback_manager
                doc.on_session_destroyed(session_destroyed)
                logger.info("Session destroyed handler registered for callback cleanup.")
            except Exception as e:
                logger.error(f"Failed to register session destroyed handler: {e}", exc_info=True)

        except Exception as e:
             logger.error(f"Failed to instantiate or attach callbacks via AppCallbacks: {e}", exc_info=True)
    else:
         logger.warning("Skipping callback setup. Reasons: "
                        f"{'Audio handler not available' if not audio_handler else ''} "
                        f"{'Playback source missing from models' if 'playback_source' not in bokeh_models else ''} "
                        f"{'Playback controls missing from models' if 'playback_controls' not in bokeh_models else ''}")
         if _DEV_ASSERTS_ENABLED:
             logger.debug("DEV_ASSERT: Callback setup skipped as expected based on available components.")

    # 5. Add root layout to document
    if main_layout:
        try:
            doc.add_root(main_layout)
            if _DEV_ASSERTS_ENABLED:
                assert main_layout in doc.roots, "DEV_ASSERT: Main layout was not added to doc roots"
            logger.info("Main layout added to document.")
        except Exception as e:
            add_error_to_doc(doc, "Failed to add layout to document.", e)
            return
    else:
        add_error_to_doc(doc, "Critical Error: Main layout was not created by the dashboard builder.")
        return

    # 6. Add essential sources explicitly if not already referenced by the main layout
    sources_to_ensure = ['playback_source', 'param_holder']
    layout_references = main_layout.references() if main_layout else set()

    for key in sources_to_ensure:
        source_model = bokeh_models.get(key)
        if source_model and source_model not in layout_references:
            try:
                doc.add_root(source_model)
                if _DEV_ASSERTS_ENABLED:
                    assert source_model in doc.roots, f"DEV_ASSERT: Essential source '{key}' was not added to doc roots"
                logger.info(f"Essential source '{key}' added explicitly to document roots.")
            except Exception as e:
                logger.error(f"Failed to add essential source '{key}' to document: {e}", exc_info=True)

    doc.title = "Noise Survey Analysis"
    logger.info("Bokeh application setup complete.")


def generate_standalone_html(custom_data_sources=None, output_path='noise_survey_standalone.html'):
    """
    Generates a standalone HTML file of the Bokeh plots without audio functionality.
    
    Parameters:
    -----------
    custom_data_sources : list, optional
        A list of data source dictionaries to use instead of the default ones.
    output_path : str, optional
        The path where the HTML file will be saved. Default is 'noise_survey_standalone.html'.
        
    Returns:
    --------
    str : The path to the generated HTML file.
    """
    from bokeh.plotting import Document
    
    logger.info(f"Generating standalone HTML at {output_path}...")
    
    # Create a new document
    doc = Document()
    
    # Create the app with audio disabled
    create_app(doc, custom_data_sources=custom_data_sources, enable_audio=False)
    
    # Generate HTML
    html = file_html(doc, CDN, "Noise Survey Analysis")
    
    # Write to file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    logger.info(f"Standalone HTML file generated at {output_path}")
    return output_path


# --- Server Execution Logic ---
if __name__.startswith('bokeh_app_'):
     # Use existing logging configuration instead of overriding it
     # This allows debugging level to propagate from run_app.py
     logger.info(f"Starting app creation for document: {curdoc()}")
     create_app(curdoc())

# Command-line interface for generating standalone HTML
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Noise Survey Analysis Standalone HTML Generator")
    parser.add_argument("--output", type=str, default="noise_survey_standalone.html",
                        help="Path to save the generated HTML file")
    args = parser.parse_args()
    
    # Set up logging for standalone mode
    logging.basicConfig(level=logging.INFO, 
                      format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Generate the standalone HTML
    output_path = generate_standalone_html(output_path=args.output)
    print(f"Standalone HTML file generated at: {output_path}")
