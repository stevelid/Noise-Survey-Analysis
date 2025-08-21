# noise_survey_analysis/core/data_loaders.py

import os
import glob
import logging
from typing import List, Dict, Any, Optional
from .data_parsers import NoiseParserFactory, ParsedData
from collections import defaultdict

logger = logging.getLogger(__name__)

def scan_directory_for_sources(base_dir: str) -> List[Dict[str, Any]]:
    """
    Scans a directory for supported data files. When a .wav file is found,
    it creates a source entry pointing to its parent directory, but displays
    the .wav filename in the UI.
    """
    found_sources = []
    processed_audio_dirs = set()  # Track which directories have been added as an 'Audio' source
    logger.info(f"Scanning directory: {base_dir}")

    supported_file_extensions = ('.csv', '.svl', '.txt', '.xlsx', '.xls', '.json', '.wav')

    for root, dirs, files in os.walk(base_dir):
        for file in files:
            if not file.lower().endswith(supported_file_extensions):
                continue
            
            file_path = os.path.join(root, file)

            # --- Audio File Handling ---
            if file.lower().endswith('.wav'):
                audio_dir_path = root  # The source is the directory
                
                # Add the directory source only once, represented by the first .wav file found.
                if audio_dir_path in processed_audio_dirs:
                    continue 

                try:
                    num_wav_files = len([f for f in os.listdir(audio_dir_path) if f.lower().endswith('.wav')])
                    
                    found_sources.append({
                        'position_name': os.path.basename(audio_dir_path),
                        'file_path': audio_dir_path,
                        'display_path': os.path.relpath(file_path, base_dir).replace('\\', '/'),
                        'enabled': True,
                        'data_type': 'Audio',
                        'parser_type': 'audio',
                        'file_size': f"{num_wav_files} .wav files"
                    })
                    processed_audio_dirs.add(audio_dir_path)
                    logger.info(f"Found audio source directory: {audio_dir_path} (represented by {file})")
                except Exception as e:
                    logger.warning(f"Could not process audio directory {audio_dir_path}: {e}")
                
                continue # Done with this .wav file, move to the next file in the loop

            # --- Config File Handling ---
            if file.startswith("noise_survey_config_") and file.endswith(".json"):
                try:
                    import json
                    with open(file_path, 'r') as f: config_data = json.load(f)
                    job_number = config_data.get("job_number", "unknown")
                    source_count = len(config_data.get("sources", []))
                    
                    found_sources.append({
                        'position_name': f"Config ({job_number})",
                        'file_path': file_path,
                        'display_path': os.path.relpath(file_path, base_dir).replace('\\', '/'),
                        'enabled': True,
                        'data_type': 'Config',
                        'parser_type': 'config',
                        'file_size': f"{os.path.getsize(file_path)} B ({source_count} sources)"
                    })
                except Exception as e:
                    logger.warning(f"Could not parse config file {file_path}: {e}")
                continue

            # --- Regular Data File Handling ---
            try_parser = NoiseParserFactory.get_parser(file_path)
            if try_parser:
                try:
                    folder_name = os.path.basename(root)
                    position_name = folder_name if folder_name != os.path.basename(base_dir) else os.path.splitext(file)[0]
                    position_name = position_name.replace('log', '').replace('summary', '').strip(' _-')
                    if not position_name: position_name = os.path.splitext(file)[0]
                    
                    file_size = os.path.getsize(file_path)
                    
                    found_sources.append({
                        'position_name': position_name,
                        'file_path': file_path,
                        'display_path': os.path.relpath(file_path, base_dir).replace('\\', '/'),
                        'enabled': True,
                        'data_type': type(try_parser).__name__.replace('FileParser', ''),
                        'parser_type': type(try_parser).__name__.replace('FileParser', '').lower(),
                        'file_size': f"{file_size / 1048576:.1f} MB" if file_size > 1048576 else f"{file_size/1024:.1f} KB"
                    })
                except Exception as e:
                    logger.error(f"Error processing file '{file_path}' with parser '{type(try_parser).__name__}': {e}")
            else:
                logger.debug(f"No suitable parser found for: {file_path}")

    logger.info(f"Finished scanning {base_dir}. Found {len(found_sources)} potential sources.")
    return found_sources

def summarize_scanned_sources(scanned_sources: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """
    Summarizes the types and counts of sources found per position.
    """
    summary = defaultdict(lambda: defaultdict(int))
    for source in scanned_sources:
        pos_name = source.get("position_name", "Unknown Position")
        data_type = source.get("data_type", "Unknown Type")
        summary[pos_name][data_type] += 1
    return summary