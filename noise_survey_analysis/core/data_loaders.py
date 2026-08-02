# noise_survey_analysis/core/data_loaders.py

import os
import glob
import json
import logging
from typing import List, Dict, Any
from .data_parsers import NoiseParserFactory
from . import survey_layout
from collections import defaultdict

logger = logging.getLogger(__name__)

def scan_directory_for_sources(base_dir: str, probe_time_spans: bool = True) -> List[Dict[str, Any]]:
    """
    Scans a directory for supported data files. When a .wav file is found,
    it creates a source entry pointing to its parent directory, but displays
    the .wav filename in the UI.

    Each source additionally carries what can be learned cheaply about it: the visit
    and position implied by its folder, its instrument and role, and - when
    `probe_time_spans` is set - its measured time span from an ~8 KB read at each end
    of the file. That span is what separates a short manual reading from an unattended
    survey, without relying on folders being named helpfully.
    """
    found_sources = []
    processed_audio_dirs = set()  # Track which directories have been added as an 'Audio' source
    logger.info(f"Scanning directory: {base_dir}")

    survey_root_name = os.path.basename(base_dir.rstrip(os.sep))
    supported_file_extensions = ('.csv', '.svl', '.txt', '.xlsx', '.xls', '.json', '.wav')

    for root, dirs, files in os.walk(base_dir):
        # os.walk yields entries in filesystem order, which differs between platforms
        # and even between runs. For an audio folder only the first file seen supplies
        # the display name, so without sorting the name shown for a position could
        # change from one scan to the next.
        dirs.sort()
        for file in sorted(files):
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
                    
                    wav_sizes = [os.path.getsize(os.path.join(audio_dir_path, f)) for f in os.listdir(audio_dir_path)
                                 if f.lower().endswith('.wav')]
                    total_wav_bytes = sum(wav_sizes)

                    found_sources.append({
                        'position_name': os.path.basename(audio_dir_path),
                        'file_path': audio_dir_path,
                        'display_path': os.path.relpath(file_path, base_dir).replace('\\', '/'),
                        'enabled': True,
                        'data_type': 'Audio',
                        'parser_type': 'audio',
                        'file_size': f"{num_wav_files} .wav files",
                        'file_size_bytes': total_wav_bytes,
                        'visit': survey_layout.derive_group(
                            os.path.relpath(file_path, base_dir).replace('\\', '/'),
                            survey_root_name,
                        )['visit'],
                        'group_label': os.path.basename(audio_dir_path),
                        'instrument': '',
                        'role': 'audio',
                        'has_spectral': None,
                        'session': '',
                        'is_analysis_workbook': False,
                        'start_time': '',
                        'end_time': '',
                        'duration_seconds': None,
                        'is_spot_measurement': False,
                        'recommended': True,
                    })
                    processed_audio_dirs.add(audio_dir_path)
                    logger.info(f"Found audio source directory: {audio_dir_path} (represented by {file})")
                except Exception as e:
                    logger.warning(f"Could not process audio directory {audio_dir_path}: {e}")
                
                continue # Done with this .wav file, move to the next file in the loop

            # --- Config File Handling ---
            if file.startswith("noise_survey_config_") and file.endswith(".json"):
                try:
                    with open(file_path, 'r') as f:
                        config_data = json.load(f)

                    sources = config_data.get("sources")
                    if not isinstance(sources, list):
                        logger.warning(
                            f"Config file {file_path} skipped - missing or invalid 'sources' list"
                        )
                        continue

                    job_number = config_data.get("job_number", "unknown")
                    source_count = len(sources)

                    found_sources.append({
                        'position_name': f"Config ({job_number})",
                        'file_path': file_path,
                        'display_path': os.path.relpath(file_path, base_dir).replace('\\', '/'),
                        'enabled': True,
                        'data_type': 'Config',
                        'parser_type': 'config',
                        'file_size': f"{os.path.getsize(file_path)} B ({source_count} sources)",
                        'file_size_bytes': os.path.getsize(file_path),
                        'config_source_count': source_count,
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
                    display_path = os.path.relpath(file_path, base_dir).replace('\\', '/')

                    facts = survey_layout.classify_file(file_path, display_path, file_size)
                    grouping = survey_layout.derive_group(display_path, survey_root_name)
                    # The folder is the better label when there is one - it is what the
                    # user already chose. Otherwise fall back to the meter token.
                    group_label = grouping['position'] or survey_layout.position_label_from_filename(file)

                    span_start = span_end = None
                    if probe_time_spans and not facts.is_analysis_workbook:
                        span_start, span_end = survey_layout.peek_time_span(file_path)
                    duration_seconds = survey_layout.span_seconds(span_start, span_end)

                    found_sources.append({
                        'position_name': group_label or position_name,
                        'file_path': file_path,
                        'display_path': display_path,
                        'enabled': True,
                        'data_type': type(try_parser).__name__.replace('FileParser', ''),
                        'parser_type': type(try_parser).__name__.replace('FileParser', '').lower(),
                        'file_size': f"{file_size / 1048576:.1f} MB" if file_size > 1048576 else f"{file_size/1024:.1f} KB",
                        'file_size_bytes': file_size,
                        # --- layout and content facts, all cheap ---
                        'visit': grouping['visit'],
                        'group_label': group_label,
                        'instrument': facts.instrument,
                        'role': facts.role,
                        'has_spectral': facts.has_spectral,
                        'session': facts.session,
                        'is_analysis_workbook': facts.is_analysis_workbook,
                        'start_time': span_start.isoformat() if span_start is not None else '',
                        'end_time': span_end.isoformat() if span_end is not None else '',
                        'duration_seconds': duration_seconds,
                        'is_spot_measurement': survey_layout.is_spot_measurement(duration_seconds),
                        # Spot readings stay selectable but are not offered by default.
                        # Spreadsheets are NOT demoted: the only ones a parser claims
                        # are Svan "*overview.xlsx" exports, which are real data.
                        'recommended': not survey_layout.is_spot_measurement(duration_seconds),
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