import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def load_config_and_prepare_sources(config_path='config.json'):
    """
    Loads and parses a JSON configuration file to prepare data sources for the dashboard.

    This function is designed to handle two main use cases:
    1.  Loading a pre-generated configuration file for static HTML output.
    2.  Loading a configuration file saved from the interactive data source selector,
        which can then be used to launch the live application directly.

    The key responsibilities of this function are:
    -   Locating and reading the specified JSON configuration file.
    -   Resolving relative file paths within the config to absolute paths, using the
        config file's own directory as the base. This makes the configurations portable.
    -   Grouping multiple file entries (e.g., different data types for the same
        measurement position) into a single source configuration dictionary per position.
    -   Handling files that may not be found and logging appropriate warnings without
        crashing the application.

    Args:
        config_path (str or Path): The path to the configuration file. Can be an
            absolute path or a path relative to the project root. Defaults to 'config.json'.

    Returns:
        tuple[str, list[dict]] | tuple[None, None]: A tuple containing the desired
        output filename and the list of prepared source configurations. Returns
        (None, None) if the configuration file cannot be loaded or parsed.
    """
    # --- Project Root Setup ---
    current_file = Path(__file__)
    project_root = current_file.parent.parent.parent

    if not os.path.isabs(config_path):
        config_full_path = project_root / config_path
    else:
        config_full_path = Path(config_path)

    logger.info(f"Attempting to load configuration from: {config_full_path}")
    try:
        with open(config_full_path, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_full_path}")
        return None, None
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {config_full_path}")
        return None, None

    output_filename = config.get("output_filename", "default_dashboard.html")
    
    source_configurations = []
    config_dir = os.path.dirname(config_full_path)

    # Group files by position, as the saved config has one entry per file
    grouped_sources = {}
    for source in config.get("sources", []):
        position = source.get("position")
        if not position:
            continue

        if position not in grouped_sources:
            grouped_sources[position] = {
                "position_name": position,
                "file_paths": set(),
                "parser_type": source.get("parser_type", "auto") # Assume parser is consistent per position
            }

        # Resolve the relative path from the config file's location
        relative_path = source.get("path")
        if relative_path:
            absolute_path = os.path.abspath(os.path.join(config_dir, relative_path))
            if os.path.exists(absolute_path):
                grouped_sources[position]["file_paths"].add(absolute_path)
            else:
                logger.warning(f"File not found and will be skipped: {absolute_path}")

    source_configurations = list(grouped_sources.values())

    return output_filename, source_configurations
