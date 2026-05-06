#!/usr/bin/env python3
"""
Generate a dashboard config by scanning a job survey directory or a specific
subfolder within it.
"""
import os
import sys
import json
import glob
import re
import argparse
from datetime import datetime
from collections import defaultdict

from noise_survey_analysis.core.config import DEFAULT_BASE_JOB_DIR


def find_job_directory(base_dir, job_number):
    """Find the job directory matching the job number."""
    pattern = os.path.join(base_dir, f"{job_number}*")
    matches = glob.glob(pattern)
    if not matches:
        return None
    # Return first directory match
    for match in sorted(matches):
        if os.path.isdir(match):
            return match
    return None


def get_scan_directory(job_dir, job_number):
    """Determine which directory to scan (surveys subdir or job root)."""
    surveys_dir = os.path.join(job_dir, f"{job_number} surveys")
    if os.path.exists(surveys_dir) and os.path.isdir(surveys_dir):
        return surveys_dir
    return job_dir


def extract_position_from_filename(filename):
    """
    Extract position identifier from filename.
    Examples:
        "6210 2A_2026_01_08__11h23m33s_log.csv" -> "6210 2A"
        "L420_log.csv" -> "L420"
        "R11.WAV" -> None (audio file)
    """
    # Pattern for meter files: "{meter_id} {position}_YYYY_MM_DD..."
    match = re.match(r'^(\d{4}\s+\w+)_\d{4}_\d{2}_\d{2}', filename)
    if match:
        return match.group(1)

    # Noise Sentry exports often keep the full descriptive site/position label
    # before the timestamp suffix, for example:
    # "6305 Barrosa Way NS6A_2026_04_11__17h58m09s_log.csv"
    match = re.match(r'^(.+?)_\d{4}_\d{2}_\d{2}__\d{2}h\d{2}m\d{2}s_(?:log|summary)\.csv$', filename)
    if match:
        return match.group(1)

    # Pattern for SVL-derived files: "L{number}_log.csv"
    match = re.match(r'^(L\d+)_(?:log|summary)\.csv$', filename)
    if match:
        return match.group(1)

    return None


def detect_source_type(filename):
    """Return the source type/parser_type for a known survey-data filename."""
    lower = filename.lower()

    # Noise Sentry exports commonly retain the Convergence Instruments timestamp
    # pattern: *_YYYY_MM_DD__HHhMMmSSs_(log|summary).csv
    if re.search(r'_\d{4}_\d{2}_\d{2}__\d{2}h\d{2}m\d{2}s_(log|summary)\.csv$', lower):
        return "Noise Sentry", "sentry"

    if lower.endswith(('_log.csv', '_summary.csv')):
        return "Svan", "svan"

    if lower.endswith('.txt') and (
        '_123_' in lower or '_rta_3rd_' in lower
    ) and (
        lower.endswith('_log.txt') or lower.endswith('_rpt_report.txt')
    ):
        return "NTi", "nti"

    return None, None


def scan_survey_directory(scan_dir):
    """
    Scan directory and organize files by position.
    Returns: dict with positions as keys, containing lists of files and audio info.
    """
    positions = defaultdict(lambda: {'sources': [], 'audio_files': []})
    audio_files = []

    # Get all files
    all_files = []
    for item in os.listdir(scan_dir):
        item_path = os.path.join(scan_dir, item)
        if os.path.isfile(item_path):
            all_files.append(item)

    # Categorize files
    for filename in sorted(all_files):
        file_path = os.path.join(scan_dir, filename)

        # Audio files
        if filename.upper().endswith('.WAV'):
            audio_files.append(filename)
            continue

        source_type, parser_type = detect_source_type(filename)
        if not source_type:
            continue

        # Extract position
        position = extract_position_from_filename(filename)
        if not position:
            continue

        positions[position]['sources'].append({
            'path': filename,
            'type': source_type,
            'parser_type': parser_type,
        })

    # Also check for subdirectories (like in job 5931)
    for item in os.listdir(scan_dir):
        item_path = os.path.join(scan_dir, item)
        if os.path.isdir(item_path):
            # Check if this directory contains audio files
            audio_in_subdir = [f for f in os.listdir(item_path)
                              if f.upper().endswith('.WAV')]
            if audio_in_subdir:
                positions[item]['audio_dir'] = item

            # Check for supported data files in subdirectories
            for subfile in os.listdir(item_path):
                source_type, parser_type = detect_source_type(subfile)
                if source_type:
                    positions[item]['sources'].append({
                        'path': os.path.join(item, subfile),
                        'type': source_type,
                        'parser_type': parser_type,
                    })

    return positions, audio_files


def generate_config_file(job_number, scan_dir, config_name=None):
    """Generate a config file for the requested scan directory."""
    positions, root_audio_files = scan_survey_directory(scan_dir)

    if not positions and not root_audio_files:
        print(f"No valid data files found in {scan_dir}")
        return None

    # Build config structure
    config_data = {
        "version": "1.2",
        "created_at": datetime.now().isoformat(),
        "config_base_path": scan_dir.replace('\\', '/'),
        "output_filename": f"{job_number}_survey_dashboard.html",
        "sources": []
    }

    # Add sources for each position
    for position, files in sorted(positions.items()):
        for source in files['sources']:
            config_data["sources"].append({
                "path": source['path'].replace('\\', '/'),
                "position": position,
                "type": source['type'],
                "parser_type": source['parser_type']
            })

        # Add audio directory if it exists
        if 'audio_dir' in files:
            config_data["sources"].append({
                "path": files['audio_dir'].replace('\\', '/'),
                "position": position,
                "type": "Audio",
                "parser_type": "audio"
            })

    # If there are audio files in the root, create an "Audio" position
    if root_audio_files:
        # Group by position if possible (based on filename patterns)
        # For now, just add as a generic "Audio" position
        config_data["sources"].append({
            "path": ".",  # Current directory (scan_dir)
            "position": "Audio",
            "type": "Audio",
            "parser_type": "audio"
        })

    # Save config file
    config_filename = config_name or f"noise_survey_config_{job_number}.json"
    config_path = os.path.join(scan_dir, config_filename)

    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2)

    print(f"[OK] Config file created: {config_path}")
    print(f"[OK] Found {len(positions)} position(s)")
    if root_audio_files:
        print(f"[OK] Found {len(root_audio_files)} audio file(s)")
    print(f"\nSources included:")
    for source in config_data["sources"]:
        print(f"  - {source['position']}: {source['path']} ({source['type']})")

    return config_path


def build_parser():
    parser = argparse.ArgumentParser(
        description="Generate a dashboard config for a job or a specific survey subfolder."
    )
    parser.add_argument("job_number", help="Job number, e.g. 5882")
    parser.add_argument(
        "base_dir",
        nargs="?",
        default=DEFAULT_BASE_JOB_DIR,
        help=f"Base jobs directory. Defaults to {DEFAULT_BASE_JOB_DIR}",
    )
    parser.add_argument(
        "--scan-dir",
        help="Specific directory to scan instead of the default job surveys folder.",
    )
    parser.add_argument(
        "--config-name",
        help="Optional output config filename. Defaults to noise_survey_config_<job>.json",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    job_number = args.job_number
    base_dir = args.base_dir

    print(f"Searching for job {job_number} in {base_dir}...")

    # Find job directory
    job_dir = find_job_directory(base_dir, job_number)
    if not job_dir:
        print(f"[ERROR] Job directory not found for job {job_number}")
        sys.exit(1)

    print(f"[OK] Found job directory: {job_dir}")

    # Get scan directory
    scan_dir = args.scan_dir if args.scan_dir else get_scan_directory(job_dir, job_number)
    print(f"[OK] Scanning directory: {scan_dir}")

    # Generate config
    config_path = generate_config_file(job_number, scan_dir, args.config_name)

    if config_path:
        print(f"\n[OK] Config file ready: {config_path}")
        return config_path
    else:
        print("\n[ERROR] Failed to generate config file")
        sys.exit(1)


if __name__ == "__main__":
    main()
