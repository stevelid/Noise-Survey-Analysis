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
        'audio': None,  # New field for audio file path
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
                    
                    # Handle audio path if included in the source_info
                    if 'audio_path' in source_info and source_info['audio_path'] and os.path.exists(source_info['audio_path']):
                        position_results[position]['audio'] = source_info['audio_path']
                        logger.info(f"Added audio path for position '{position}': {source_info['audio_path']}")
                        # Store audio path in metadata as well for consistency
                        position_results[position]['metadata']['audio_path'] = source_info['audio_path']

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
                        
                        # Handle audio path if included in the source_info
                        if 'audio_path' in source_info and source_info['audio_path'] and os.path.exists(source_info['audio_path']):
                            position_results[position]['audio'] = source_info['audio_path']
                            logger.info(f"Added audio path for position '{position}': {source_info['audio_path']}")
                        
                        # Store basic metadata
                        position_results[position]['metadata']['parser_type'] = parser_type
                        position_results[position]['metadata']['original_path'] = path
                        if 'audio_path' in source_info and source_info['audio_path']:
                            position_results[position]['metadata']['audio_path'] = source_info['audio_path']
                    else:
                         logger.warning(f"Parsing returned empty DataFrame for {parser_type} from {path}")
                else:
                     logger.warning(f"Unexpected result format from {parser_type} parser for {path}: {result}")
            
            elif parser_type == 'audio':
                # Handle audio parser result
                if isinstance(result, dict) and result.get('type') == 'audio' and 'path' in result:
                    audio_path = result['path']
                    position_results[position]['audio'] = audio_path
                    logger.info(f"Added audio file for position '{position}': {audio_path}")
                    
                    # Add metadata
                    if 'metadata' in result:
                        position_results[position]['metadata']['audio'] = result['metadata']
                    
                    # Also store the original path for consistency
                    position_results[position]['metadata']['audio_path'] = audio_path
                else:
                    logger.warning(f"Unexpected result format from audio parser for {path}: {result}")
            
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
                     
        # Check for audio file path
        if 'audio' in data_dict and data_dict['audio']:
            audio_path = data_dict['audio']
            if isinstance(audio_path, str):
                file_exists = os.path.exists(audio_path)
                print(f"  - audio: {audio_path}")
                print(f"    Path exists: {file_exists}")
                
                # Display file details if exists
                if file_exists:
                    try:
                        # Check if this is a directory
                        if os.path.isdir(audio_path):
                            # Check if we have audio files metadata
                            audio_metadata = data_dict.get('metadata', {}).get('audio', {})
                            if audio_metadata and 'audio_files' in audio_metadata:
                                audio_files = audio_metadata.get('audio_files', [])
                                print(f"    Directory containing {len(audio_files)} audio file(s)")
                                
                                # Print details about each audio file (up to 5)
                                for i, file_info in enumerate(audio_files[:5]):
                                    print(f"    [{i+1}] {file_info['filename']}")
                                    print(f"        Size: {file_info['size_mb']:.2f} MB")
                                    print(f"        Last modified: {file_info['modified']}")
                                
                                if len(audio_files) > 5:
                                    print(f"    ... and {len(audio_files) - 5} more file(s)")
                            else:
                                # If metadata isn't available, just scan directory
                                audio_files = [f for f in os.listdir(audio_path) 
                                              if "_Audio_" in f and f.lower().endswith('.wav')]
                                print(f"    Directory containing {len(audio_files)} matching audio file(s)")
                                if audio_files and len(audio_files) <= 5:
                                    print(f"    Files: {', '.join(audio_files)}")
                        else:
                            # It's a single file
                            audio_stats = os.stat(audio_path)
                            size_mb = audio_stats.st_size / (1024 * 1024)
                            mod_time = pd.to_datetime(audio_stats.st_mtime, unit='s')
                            print(f"    Size: {size_mb:.2f} MB")
                            print(f"    Last modified: {mod_time}")
                    except Exception as e:
                        print(f"    Error getting audio details: {e}")
            else:
                print(f"  - audio: Unexpected type {type(audio_path)}")

        # Print Metadata
        if 'metadata' in data_dict and isinstance(data_dict['metadata'], dict):
             print(f"  - metadata: Dictionary with keys: {list(data_dict['metadata'].keys())}")

# --- Optional: Directory Scanning Function (Example Structure) ---
def scan_directory_for_sources(directory_path, auto_group=True):
    """
    Scans a directory for potential noise survey files and suggests
    a configuration list. Can optionally group files by position.

    Parameters:
    directory_path (str): The path to the directory to scan.
    auto_group (bool): Whether to automatically group files by position.

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
        '*_Rpt_Report.txt': 'nti',
        '*_RTA_*_Rpt_Report.txt': 'nti',
        '*_Log.txt': 'nti',
        '*.wav': 'audio', # General audio parser
        '*.mp3': 'audio', # General audio parser
        '*.ogg': 'audio'  # General audio parser
    }
    
    # Dictionary to group files by position
    position_groups = defaultdict(list)
    
    # First scan for regular files
    for root, _, files in os.walk(directory_path):
        for pattern, parser_type in patterns.items():
            import fnmatch # Use fnmatch for pattern matching
            for filename in fnmatch.filter(files, pattern):
                full_path = os.path.join(root, filename)

                # --- Guess position name using several methods ---
                position_name_guess = None
                
                # Method 1: Try to extract from parent directory name
                relative_dir = os.path.relpath(root, directory_path)
                parent_dir = os.path.basename(root)
                
                # If parent dir is not the base directory and looks like a position name
                if parent_dir and parent_dir != os.path.basename(directory_path):
                    if re.match(r'^[A-Za-z0-9_\-]+$', parent_dir):  # Simple check for valid position name
                        position_name_guess = parent_dir
                
                # Method 2: Try to extract from filename (e.g., before '_SLM_' or '_Rpt_')
                if not position_name_guess:
                    # Common patterns in noise survey files
                    name_patterns = [
                        r"^([A-Za-z0-9_\-]+)_SLM_",
                        r"^([A-Za-z0-9_\-]+)_Rpt_",
                        r"^([A-Za-z0-9_\-]+)_RTA_",
                        r"^([A-Za-z0-9_\-]+)_Log",
                        r"^([A-Za-z0-9_\-]+)_Audio_",
                        r"^([A-Za-z0-9_\-]+)[_\.]"  # More general fallback
                    ]
                    
                    for pattern in name_patterns:
                        match = re.match(pattern, filename)
                        if match:
                            position_name_guess = match.group(1)
                            break
                            
                # Method 3: Fallback - use filename without extension
                if not position_name_guess:
                    position_name_guess = os.path.splitext(filename)[0]
                    
                # Clean up the position name - remove any remaining special chars
                if position_name_guess:
                    position_name_guess = re.sub(r'[^A-Za-z0-9_\-]', '_', position_name_guess)
                else:
                    position_name_guess = "Unknown"

                # Determine data type
                data_type = None
                if parser_type == 'nti':
                    if '_Rpt_Report.txt' in filename:
                        data_type = 'overview'  # RPT files are overview (broadband) data
                    elif '_RTA_' in filename:
                        data_type = 'spectral'  # RTA files contain spectral data
                    elif '_Log.txt' in filename:
                        if '_RTA_' in filename:
                            data_type = 'spectral_log'  # RTA log files
                        else:
                            data_type = 'log'  # RPT log files
                elif parser_type in ['sentry', 'svan']:
                    data_type = 'overview'  # Default for sentry/svan
                elif parser_type == 'audio':
                    data_type = 'audio'

                source_entry = {
                    "position_name": position_name_guess,
                    "file_path": full_path,
                    "parser_type": parser_type,
                    "data_type": data_type,
                    "filename": filename,
                    "enabled": True  # Default to enabled
                }
                
                if auto_group:
                    # Group by position name
                    position_groups[position_name_guess].append(source_entry)
                else:
                    discovered_sources.append(source_entry)
                logger.debug(f"Discovered file: {source_entry}")
    
    # Also search for directories that might contain audio files
    for root, dirs, _ in os.walk(directory_path):
        for dirname in dirs:
            dir_path = os.path.join(root, dirname)
            # Check if this directory contains any audio files matching our pattern
            has_audio_files = False
            for filename in os.listdir(dir_path):
                if "_Audio_" in filename and filename.lower().endswith('.wav'):
                    has_audio_files = True
                    break
                    
            if has_audio_files:
                # Guess position name using similar methods as above
                position_name_guess = None
                
                # Method 1: Try parent directory name
                parent_dir = os.path.basename(os.path.dirname(dir_path))
                if parent_dir and parent_dir != os.path.basename(directory_path):
                    if re.match(r'^[A-Za-z0-9_\-]+$', parent_dir):
                        position_name_guess = parent_dir
                
                # Method 2: Try dirname itself if it contains position-like pattern
                if not position_name_guess:
                    name_patterns = [
                        r"^([A-Za-z0-9_\-]+)_Audio",
                        r"^Audio_([A-Za-z0-9_\-]+)",
                        r"^([A-Za-z0-9_\-]+)_Files"
                    ]
                    
                    for pattern in name_patterns:
                        match = re.match(pattern, dirname)
                        if match:
                            position_name_guess = match.group(1)
                            break
                
                # Fallback: use directory name
                if not position_name_guess:
                    position_name_guess = dirname
                
                # Clean up the position name
                position_name_guess = re.sub(r'[^A-Za-z0-9_\-]', '_', position_name_guess)
                
                source_entry = {
                    "position_name": position_name_guess,
                    "file_path": dir_path,
                    "parser_type": "audio",
                    "data_type": "audio",
                    "filename": dirname,
                    "enabled": True
                }
                
                if auto_group:
                    position_groups[position_name_guess].append(source_entry)
                else:
                    discovered_sources.append(source_entry)
                logger.debug(f"Discovered audio directory: {source_entry}")

    # If auto_group is enabled, process the grouped sources
    if auto_group:
        # Process each position group
        for position_name, entries in position_groups.items():
            # Sort entries by data_type to prioritize certain types
            entries.sort(key=lambda x: {
                'overview': 0,
                'spectral': 1,
                'log': 2,
                'spectral_log': 3,
                'audio': 4
            }.get(x.get('data_type', ''), 999))
            
            for entry in entries:
                discovered_sources.append(entry)

    return discovered_sources

# New function for UI: get file counts by position and type
def summarize_scanned_sources(sources):
    """
    Summarizes scanned sources by position and data type.
    
    Parameters:
    sources (list): List of source dictionaries from scan_directory_for_sources
    
    Returns:
    dict: Summary of positions and their data types
    """
    summary = defaultdict(lambda: defaultdict(int))
    
    for source in sources:
        position = source.get("position_name", "Unknown")
        data_type = source.get("data_type", "unknown")
        
        summary[position][data_type] += 1
        
    return dict(summary)

# --- FileSelector class remains the same conceptually ---
class FileSelector:
    """UI-independent file selection utility class."""
    # Implementation would go here if needed
    pass

def extract_spectral_parameters(spectral_df):
    """
    Extracts available spectral parameters from a spectral DataFrame.
    
    Consistently identifies parameter names like 'LZeq', 'LAF90', etc. from column names
    that follow the pattern 'LZeq_1000Hz', 'LAF90_250Hz', etc.
    
    Args:
        spectral_df (pd.DataFrame): DataFrame containing spectral data with columns
                                   following the pattern 'Parameter_Frequency'
                                   
    Returns:
        list: Sorted list of unique parameter names found in the DataFrame
    """
    if not isinstance(spectral_df, pd.DataFrame) or spectral_df.empty:
        return []
        
    parameters = []
    for col in spectral_df.columns:
        # Look for columns matching 'Parameter_Frequency' pattern
        if '_' in col and col.split('_')[0].startswith('L'):
            param = col.split('_')[0]
            parameters.append(param)
            
    # Return a sorted list of unique parameters
    return sorted(list(set(parameters)))