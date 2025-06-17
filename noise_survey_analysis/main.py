import logging
from bokeh.plotting import curdoc
from bokeh.layouts import LayoutDOM
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
    from .core.data_processors import synchronize_time_range
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

    logger.info("Setting up Bokeh application...")

    # 1. Load and Process Data
    position_data = None
    try:
        position_data = load_and_process_data(custom_data_sources) # Modified to use custom sources if provided

        if CHART_SETTINGS.get("sync_ranges", False) and position_data and len(position_data) > 1:
             logger.info("Synchronizing time ranges across positions.")
             position_data = synchronize_time_range(position_data)
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
    
    logger.debug(f"Data loaded for positions: {list(position_data.keys())}")

    # 2. Initialize Core Components (Audio Handler)
    audio_handler = None
    
    # Only initialize audio if enabled
    if enable_audio:
        try:
            logger.info("Initializing AudioPlaybackHandler...")
            audio_handler = AudioPlaybackHandler(position_data)
        except ImportError:
             logger.warning("python-vlc library not found or failed to import. Audio playback will be disabled.", exc_info=False)
             audio_handler = None
        except Exception as e:
            logger.error(f"Failed to initialize AudioPlaybackHandler: {e}", exc_info=True)
            audio_handler = None


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

        main_layout = dashboard_builder.build()
        logger.info("Dashboard layout built.")
        bokeh_models = dashboard_builder.bokeh_models # Assign to local variable


    except Exception as e:
        add_error_to_doc(doc, "Failed to build dashboard layout. Check logs.", e, height=100)
        return

    # 4. Setup Callbacks using AppCallbacks
    callback_manager = None
    
    # Check for audio handler and required components in the hierarchical structure
    has_playback_source = 'sources' in bokeh_models and 'playback' in bokeh_models['sources'] and 'position' in bokeh_models['sources']['playback']
    
    has_playback_controls = 'ui' in bokeh_models and 'controls' in bokeh_models['ui'] and 'playback' in bokeh_models['ui']['controls']
    
    if audio_handler and has_playback_source and has_playback_controls:
        logger.info("Audio handler and necessary models found, setting up callbacks...")
        
        try:
            callback_manager = AppCallbacks(
                doc=doc,
                audio_handler=audio_handler,
                bokeh_models=bokeh_models,
            )
            
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
                        f"{'Playback source missing from models' if not has_playback_source else ''} "
                        f"{'Playback controls missing from models' if not has_playback_controls else ''}")

    # 5. Add root layout to document
    if main_layout:
        try:
            doc.add_root(main_layout)
            logger.info("Main layout added to document.")
        except Exception as e:
            add_error_to_doc(doc, "Failed to add layout to document.", e)
            return
    else:
        add_error_to_doc(doc, "Critical Error: Main layout was not created by the dashboard builder.")
        return

    # 6. Add essential sources explicitly if not already referenced by the main layout
    # Define sources to ensure using hierarchical paths
    sources_to_ensure = [
        ('sources.playback.position', lambda m: m['sources']['playback']['position']),
        ('ui.controls.parameter.holder', lambda m: m['ui']['controls']['parameter']['holder'])
    ]
    
    layout_references = main_layout.references() if main_layout else set()

    for key_path, accessor in sources_to_ensure:
        try:
            source_model = accessor(bokeh_models)
            if source_model and source_model not in layout_references:
                try:
                    doc.add_root(source_model)
                    logger.info(f"Essential source '{key_path}' added explicitly to document roots.")
                except Exception as e:
                    logger.error(f"Failed to add essential source '{key_path}' to document: {e}", exc_info=True)
        except Exception as e:
            logger.warning(f"Could not access source at '{key_path}': {e}")

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
