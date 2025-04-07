"""
Data loading utilities for Noise Survey Analysis.
Uses a list of data source definitions to load and aggregate data.
"""

import logging
import pandas as pd
import os
import re
from collections import defaultdict # Useful for aggregating results

# Import the refactored parsers including the safe_convert_to_float function
from .data_parsers import NoiseDataParser  # Use relative import if in same package

# Import new configuration structure
# Make sure config path is correct relative to data_loaders.py
try:
    from .config import DEFAULT_DATA_SOURCES, REQUIRED_BROADBAND_METRICS, REQUIRED_SPECTRAL_PREFIXES
except ImportError: # Fallback for different execution contexts
     from noise_survey_analysis.core.config import DEFAULT_DATA_SOURCES, REQUIRED_BROADBAND_METRICS, REQUIRED_SPECTRAL_PREFIXES


logger = logging.getLogger(__name__)

def _filter_dataframe_columns(df, data_type, path_for_log):
    """
    Filters DataFrame columns based on required metrics or spectral prefixes.

    Args:
        df (pd.DataFrame): The DataFrame to filter.
        data_type (str): The type of data ('RPT', 'RTA', 'RPT_LOG', 'sentry_data', etc.).
        path_for_log (str): File path for logging context.

    Returns:
        pd.DataFrame: The filtered DataFrame.
    """
    if df.empty:
        return df

    original_cols = set(df.columns)
    cols_to_keep = set()

    # Always keep Datetime if it exists
    if 'Datetime' in original_cols:
        cols_to_keep.add('Datetime')
    else:
        logger.warning(f"Filtering: 'Datetime' column missing in {data_type} from {path_for_log}")

    # Check if it's spectral data (heuristic based on common keys or column names)
    is_spectral = data_type in ['RTA', 'RTA_LOG'] or \
                  any(prefix + '_' in col for col in original_cols for prefix in REQUIRED_SPECTRAL_PREFIXES)

    if is_spectral:
        logger.debug(f"Applying spectral filtering to {data_type} from {path_for_log}")
        for col in original_cols:
            for prefix in REQUIRED_SPECTRAL_PREFIXES:
                # Keep if it starts with a required prefix and looks like a freq band
                if col.startswith(prefix + '_') and col.split('_')[-1].replace('.', '', 1).isdigit():
                    cols_to_keep.add(col)
                    break # Found a match for this column, move to next column
    else:
        logger.debug(f"Applying broadband filtering to {data_type} from {path_for_log}")
        for col in original_cols:
            if col in REQUIRED_BROADBAND_METRICS:
                cols_to_keep.add(col)

    # Ensure required columns actually exist in the original df before filtering
    final_cols_to_keep = sorted([col for col in cols_to_keep if col in original_cols])

    # Re-insert 'Datetime' at the beginning if it was present
    if 'Datetime' in cols_to_keep and 'Datetime' in original_cols:
        final_cols_to_keep.remove('Datetime')
        final_cols_to_keep.insert(0, 'Datetime')

    removed_cols = original_cols - set(final_cols_to_keep)
    if removed_cols:
        logger.info(f"Filtering {data_type} from {path_for_log}: Removing columns: {sorted(list(removed_cols))}")

    if not final_cols_to_keep or ('Datetime' in final_cols_to_keep and len(final_cols_to_keep) == 1) :
         logger.warning(f"Filtering resulted in no data columns (only Datetime perhaps) for {data_type} from {path_for_log}. Returning original df.")
         return df # Avoid returning just Datetime or empty

    return df[final_cols_to_keep]



def get_default_data_sources():
    """
    Returns the default list of data source definitions.
    """
    # Return a copy to prevent modification of the original
    return [source.copy() for source in DEFAULT_DATA_SOURCES]

def load_and_process_data(data_sources=None):
    """
    Loads data based on a list of data source definitions.
    Aggregates data for the same position name under standard keys:
    'overview', 'spectral', 'log', and 'metadata'.

    Parameters:
    data_sources (list, optional): List of data source dictionaries.
                                   If None, uses DEFAULT_DATA_SOURCES.

    Returns:
    dict: Dictionary where keys are position names.
          Values are dictionaries containing DataFrames keyed by standard type
          ('overview', 'spectral', 'log') and a 'metadata' sub-dictionary.
          Example:
          {
              'SW': {
                  'overview': df_sw_sentry,
                  'metadata': {'parser_type': 'sentry', ...}
              },
              'SE': {
                  'overview': df_se_rpt,
                  'spectral': df_se_rta,
                  'log': df_se_rpt_log,
                  'metadata': {
                      'RPT': {...}, # Specific metadata from RPT parser
                      'RTA': {...},
                      'RPT_LOG': {...},
                      # Could add original file paths here too
                  }
              }
          }
    """
    if data_sources is None:
        data_sources = get_default_data_sources()

    position_results = defaultdict(lambda: {
        'overview': None,
        'spectral': None,
        'log': None,
        'spectral_log': None,
        'metadata': {}
    })

    for source_info in data_sources:
        if not source_info.get("enabled", False) or not all(k in source_info for k in ["position_name", "file_path", "parser_type"]):
            logger.warning(f"Skipping invalid or disabled data source: {source_info.get('file_path', 'N/A')}")
            continue

        position = source_info["position_name"]
        path = source_info["file_path"]
        parser_type = source_info["parser_type"]

        try:
            if not os.path.exists(path):
                logger.error(f"File not found for position '{position}': {path}")
                continue

            parser = NoiseDataParser.get_parser(parser_type)
            logger.info(f"Loading '{position}' ({parser_type}) from: {path}")
            result = parser.parse(path)

            if result is None:
                 logger.error(f"Parsing failed for {path}")
                 continue


            # --- Store results using standard keys ---
            if parser_type == 'nti':
                if isinstance(result, dict) and 'type' in result and 'data' in result:
                    data_type = result['type'] # e.g., 'RPT', 'RTA', 'RPT_LOG', 'RTA_LOG'
                    full_df = result['data']
                    metadata = result.get('metadata', {})

                    df = _filter_dataframe_columns(full_df, data_type, path)

                    if isinstance(df, pd.DataFrame) and not df.empty:
                        target_key = None
                        if data_type == 'RPT':
                            target_key = 'overview'
                        elif data_type == 'RTA':
                            target_key = 'spectral'
                        elif data_type == 'RPT_LOG':
                            target_key = 'log'
                        elif data_type == 'RTA_LOG':
                            target_key = 'spectral_log'


                        if target_key:
                            if position_results[position][target_key] is None:
                                position_results[position][target_key] = df
                            else:
                                logger.warning(f"Overwriting existing '{target_key}' data for position '{position}' with data from {data_type}")
                                position_results[position][target_key] = pd.concat([position_results[position][target_key], df])
                            logger.info(f"Stored {data_type} data as '{target_key}' for '{position}'. Shape: {df.shape}")
                            # Store specific metadata under the original type key
                            if metadata:
                                position_results[position]['metadata'][data_type] = metadata
                        else:
                             logger.warning(f"Could not determine standard key for NTi type '{data_type}' from {path}")

                    elif isinstance(df, pd.DataFrame) and df.empty:
                        logger.warning(f"Parsing returned empty DataFrame for NTi type {data_type} from {path}")
                    else:
                         logger.warning(f"NTi parser for {path} returned non-DataFrame data: {type(df)}")

                else:
                    logger.warning(f"Unexpected result format from NTi parser for {path}: {result}")

            elif parser_type in ['sentry', 'svan']:
                # Assume Sentry/Svan provide overview data primarily
                # (If Svan parsing was enhanced to separate spectral/log, logic would go here)
                if isinstance(result, pd.DataFrame):
                    if not result.empty:
                        if position_results[position]['overview'] is None:
                            position_results[position]['overview'] = result
                        else:
                            logger.warning(f"Overwriting existing 'overview' data for position '{position}' with data from {parser_type}")
                            position_results[position]['overview'] = pd.concat([position_results[position]['overview'], result])
                        logger.info(f"Stored {parser_type} data as 'overview' for '{position}'. Shape: {result.shape}")
                        # Store basic metadata
                        position_results[position]['metadata']['parser_type'] = parser_type
                        position_results[position]['metadata']['original_path'] = path
                    else:
                         logger.warning(f"Parsing returned empty DataFrame for {parser_type} from {path}")
                else:
                     logger.warning(f"Unexpected result format from {parser_type} parser for {path}: {result}")
            else:
                 logger.warning(f"Unhandled parser type '{parser_type}' for position '{position}'. Storing raw.")
                 position_results[position][f'{parser_type}_data'] = result # Fallback

        except Exception as e:
            logger.error(f"Error loading data source for position '{position}' from {path}: {e}", exc_info=True)

    return dict(position_results) # Convert back to regular dict


def examine_data(position_data):
    """
    Examine the loaded data structure (using standard keys) and print summaries.
    """
    for position, data_dict in position_data.items():
        print(f"\n=== Position: {position} ===")
        if not isinstance(data_dict, dict):
            print(f"  Unexpected data format: {type(data_dict)}")
            continue

        # Check for standard keys first
        for key in ['overview', 'spectral', 'log', 'spectral_log']:
            if key in data_dict:
                df = data_dict[key]
                if isinstance(df, pd.DataFrame):
                    print(f"  - {key}: DataFrame")
                    print(f"    Shape: {df.shape}")
                    if not df.empty:
                        print(f"    Columns: {df.columns.tolist()}")
                        if 'Datetime' in df.columns:
                            try:
                                print(f"    Date range: {df['Datetime'].min()} to {df['Datetime'].max()}")
                            except Exception as e:
                                print(f"    Could not determine date range: {e}")
                        else:
                            print("    'Datetime' column not found.")
                    else:
                        print("    (DataFrame is empty)")
                else:
                     print(f"  - {key}: Expected DataFrame, got {type(df)}")

        # Print Metadata
        if 'metadata' in data_dict and isinstance(data_dict['metadata'], dict):
             print(f"  - metadata: Dictionary with keys: {list(data_dict['metadata'].keys())}")

# --- Optional: Directory Scanning Function (Example Structure) ---
def scan_directory_for_sources(directory_path):
    """
    Scans a directory for potential noise survey files and suggests
    a configuration list.

    Parameters:
    directory_path (str): The path to the directory to scan.

    Returns:
    list: A list of suggested data source dictionaries.
    """
    discovered_sources = []
    logger.info(f"Scanning directory: {directory_path}")

    if not os.path.isdir(directory_path):
        logger.error(f"Directory not found: {directory_path}")
        return []

    # Define patterns and associated parser types/heuristics
    patterns = {
        '*.csv': 'sentry', # Assuming CSV is Sentry for now
        '*.xls': 'svan',
        '*.xlsx': 'svan',
        '*_123_Rpt_Report.txt': 'nti',
        '*_RTA_3rd_Rpt_Report.txt': 'nti',
        '*_123_Log.txt': 'nti',
        '*_RTA_3rd_Log.txt': 'nti',
    }

    for root, _, files in os.walk(directory_path):
        for pattern, parser_type in patterns.items():
            import fnmatch # Use fnmatch for pattern matching
            for filename in fnmatch.filter(files, pattern):
                full_path = os.path.join(root, filename)

                # --- Guess position name (heuristic - needs refinement) ---
                # Option 1: Use subdirectory name relative to initial path
                relative_dir = os.path.relpath(root, directory_path)
                if relative_dir and relative_dir != '.':
                    position_name_guess = relative_dir.split(os.path.sep)[0] # First subdir
                else:
                    # Option 2: Try to extract from filename (e.g., before '_SLM_')
                    match = re.match(r"([^_]+?)_.*", filename)
                    position_name_guess = match.group(1) if match else filename.split('.')[0]

                # Ensure position name is valid (e.g., replace spaces)
                position_name_guess = re.sub(r'\W+', '_', position_name_guess)

                source_entry = {
                    "position_name": position_name_guess,
                    "file_path": full_path,
                    "parser_type": parser_type,
                    "enabled": True # Default to enabled
                }
                discovered_sources.append(source_entry)
                logger.debug(f"Discovered: {source_entry}")

    # Optional: Deduplicate or further refine the list here
    # For example, group NTi files by a common base name if needed

    return discovered_sources


# --- FileSelector class remains the same conceptually ---
class FileSelector:
    """UI-independent file selection utility class."""
    # Implementation would go here if needed
    pass