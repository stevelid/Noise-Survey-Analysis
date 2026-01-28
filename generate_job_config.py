#!/usr/bin/env python3
"""
Generate a config file for a job by scanning its survey directory.
"""
import os
import sys
import json
import glob
import re
from datetime import datetime
from collections import defaultdict
from pathlib import Path


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

    # Pattern for SVL-derived files: "L{number}_log.csv"
    match = re.match(r'^(L\d+)_(?:log|summary)\.csv$', filename)
    if match:
        return match.group(1)

    return None


def scan_survey_directory(scan_dir):
    """
    Scan directory and organize files by position.
    Returns: dict with positions as keys, containing lists of files and audio info.
    """
    positions = defaultdict(lambda: {'log': [], 'summary': [], 'audio_files': []})
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

        # Skip non-data files
        if not (filename.endswith('_log.csv') or filename.endswith('_summary.csv')):
            continue

        # Extract position
        position = extract_position_from_filename(filename)
        if not position:
            continue

        # Categorize
        if filename.endswith('_log.csv'):
            positions[position]['log'].append(filename)
        elif filename.endswith('_summary.csv'):
            positions[position]['summary'].append(filename)

    # Also check for subdirectories (like in job 5931)
    for item in os.listdir(scan_dir):
        item_path = os.path.join(scan_dir, item)
        if os.path.isdir(item_path):
            # Check if this directory contains audio files
            audio_in_subdir = [f for f in os.listdir(item_path)
                              if f.upper().endswith('.WAV')]
            if audio_in_subdir:
                positions[item]['audio_dir'] = item

            # Check for log/summary files in subdirectories
            for subfile in os.listdir(item_path):
                if subfile.endswith('_log.csv'):
                    positions[item]['log'].append(os.path.join(item, subfile))
                elif subfile.endswith('_summary.csv'):
                    positions[item]['summary'].append(os.path.join(item, subfile))

    return positions, audio_files


def generate_config_file(job_number, scan_dir):
    """Generate a config file for the job."""
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
        # Add log files
        for log_file in files['log']:
            config_data["sources"].append({
                "path": log_file.replace('\\', '/'),
                "position": position,
                "type": "Svan",
                "parser_type": "svan"
            })

        # Add summary files
        for summary_file in files['summary']:
            config_data["sources"].append({
                "path": summary_file.replace('\\', '/'),
                "position": position,
                "type": "Svan",
                "parser_type": "svan"
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
    config_filename = f"noise_survey_config_{job_number}.json"
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


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_job_config.py <job_number> [base_dir]")
        sys.exit(1)

    job_number = sys.argv[1]
    base_dir = sys.argv[2] if len(sys.argv) > 2 else "G:/Shared drives/Venta/Jobs"

    print(f"Searching for job {job_number} in {base_dir}...")

    # Find job directory
    job_dir = find_job_directory(base_dir, job_number)
    if not job_dir:
        print(f"[ERROR] Job directory not found for job {job_number}")
        sys.exit(1)

    print(f"[OK] Found job directory: {job_dir}")

    # Get scan directory
    scan_dir = get_scan_directory(job_dir, job_number)
    print(f"[OK] Scanning directory: {scan_dir}")

    # Generate config
    config_path = generate_config_file(job_number, scan_dir)

    if config_path:
        print(f"\n[OK] Config file ready: {config_path}")
        return config_path
    else:
        print("\n[ERROR] Failed to generate config file")
        sys.exit(1)


if __name__ == "__main__":
    main()
