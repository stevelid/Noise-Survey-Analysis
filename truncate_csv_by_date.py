"""
Truncate CSV files to keep only data before a specified timestamp.
Preserves file structure including multi-row headers.
"""

import os
import sys
from datetime import datetime
import re

def find_timestamp_column(header_line):
    """Find which column contains the timestamp based on header."""
    parts = header_line.split(',')
    for i, part in enumerate(parts):
        if 'date' in part.lower() and 'time' in part.lower():
            return i
    return None

def extract_timestamp(line, timestamp_col):
    """Extract timestamp from a CSV line."""
    parts = line.split(',')
    if timestamp_col is None or timestamp_col >= len(parts):
        return None
    
    timestamp_str = parts[timestamp_col].strip()
    
    # Match timestamp format: YYYY-MM-DD HH:MM:SS.mmm
    match = re.search(r'(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', timestamp_str)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None
    return None

def estimate_cutoff_line(input_path, cutoff_datetime, max_lines_to_check=500000):
    """
    Estimate where the cutoff timestamp occurs without reading entire file.
    Returns approximate line number.
    """
    print(f"  Estimating cutoff line for {os.path.basename(input_path)}...")
    
    timestamp_col = None
    header_lines = 0
    first_data_line = None
    first_timestamp = None
    
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f):
            if i < 10:
                if 'date' in line.lower() and 'time' in line.lower():
                    timestamp_col = find_timestamp_column(line)
                    header_lines = i + 1
            elif first_data_line is None:
                ts = extract_timestamp(line, timestamp_col)
                if ts:
                    first_data_line = i
                    first_timestamp = ts
                    print(f"    First data timestamp: {first_timestamp} at line {first_data_line}")
                    break
            
            if i > 20:
                break
    
    if first_timestamp is None:
        print(f"    WARNING: Could not find valid timestamp in first 20 lines")
        return None
    
    # Sample a line much later to estimate rate
    sample_line = min(100000, max_lines_to_check)
    with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
        for i, line in enumerate(f):
            if i == sample_line:
                ts = extract_timestamp(line, timestamp_col)
                if ts:
                    time_diff = (ts - first_timestamp).total_seconds()
                    lines_diff = i - first_data_line
                    if time_diff > 0:
                        seconds_per_line = time_diff / lines_diff
                        target_seconds = (cutoff_datetime - first_timestamp).total_seconds()
                        estimated_line = first_data_line + int(target_seconds / seconds_per_line)
                        print(f"    Estimated cutoff at line ~{estimated_line:,} (sampling rate: {seconds_per_line:.3f}s/line)")
                        return estimated_line
                break
    
    return None

def truncate_csv_file(input_path, output_path, cutoff_datetime, max_lines=300000):
    """
    Truncate CSV file to keep only data before cutoff_datetime.
    Preserves all header rows.
    
    Args:
        input_path: Path to input CSV file
        output_path: Path to output CSV file
        cutoff_datetime: datetime object - keep data before this time
        max_lines: Safety limit - stop if we exceed this many lines
    """
    print(f"\nProcessing: {os.path.basename(input_path)}")
    print(f"  Output: {os.path.basename(output_path)}")
    print(f"  Cutoff: {cutoff_datetime}")
    
    if not os.path.exists(input_path):
        print(f"  ERROR: Input file not found: {input_path}")
        return False
    
    # Get estimate
    estimated_line = estimate_cutoff_line(input_path, cutoff_datetime)
    if estimated_line:
        print(f"  Expected output: ~{estimated_line:,} lines")
        if estimated_line > max_lines:
            print(f"  WARNING: Estimated lines ({estimated_line:,}) exceeds safety limit ({max_lines:,})")
            response = input("  Continue anyway? (yes/no): ")
            if response.lower() != 'yes':
                print("  Skipped by user")
                return False
    
    timestamp_col = None
    header_lines = []
    data_lines_written = 0
    last_timestamp = None
    
    try:
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as infile:
            with open(output_path, 'w', encoding='utf-8', newline='') as outfile:
                
                for line_num, line in enumerate(infile, 1):
                    
                    # Progress indicator every 50k lines
                    if line_num % 50000 == 0:
                        print(f"    Progress: {line_num:,} lines read, {data_lines_written:,} data lines written...")
                    
                    # Detect header rows (first few rows before timestamps start)
                    if line_num <= 10:
                        if 'date' in line.lower() and 'time' in line.lower():
                            timestamp_col = find_timestamp_column(line)
                        header_lines.append(line)
                        outfile.write(line)
                        continue
                    
                    # Write remaining header lines if we haven't found data yet
                    if timestamp_col is None or data_lines_written == 0:
                        ts = extract_timestamp(line, timestamp_col)
                        if ts is None:
                            outfile.write(line)
                            continue
                    
                    # Process data lines
                    ts = extract_timestamp(line, timestamp_col)
                    
                    if ts is None:
                        # Line without valid timestamp - keep it (might be continuation)
                        outfile.write(line)
                        continue
                    
                    if ts < cutoff_datetime:
                        outfile.write(line)
                        data_lines_written += 1
                        last_timestamp = ts
                        
                        # Safety check
                        if data_lines_written > max_lines:
                            print(f"  ERROR: Exceeded safety limit of {max_lines:,} data lines")
                            print(f"  Last timestamp written: {last_timestamp}")
                            return False
                    else:
                        # Reached cutoff
                        print(f"  Cutoff reached at line {line_num:,}")
                        print(f"  Last timestamp written: {last_timestamp}")
                        break
        
        print(f"  ✓ Complete: {data_lines_written:,} data lines written")
        print(f"  Output file: {output_path}")
        return True
        
    except Exception as e:
        print(f"  ERROR: {str(e)}")
        return False

def main():
    """Main execution function."""
    
    # Configuration
    cutoff_datetime = datetime(2025, 12, 24, 16, 0, 0)
    
    tasks = [
        {
            'folder': r"G:\Shared drives\Venta\Jobs\5931 Lains Shooting School, Quarley\5931 Surveys\917-4",
            'files': [
                ('L419_log.csv', 'L419_log_short.csv'),
                ('L419_summary.csv', 'L419_summary_short.csv')
            ]
        },
        {
            'folder': r"G:\Shared drives\Venta\Jobs\5931 Lains Shooting School, Quarley\5931 Surveys\971-2",
            'files': [
                ('L341_log.csv', 'L341_log_short.csv'),
                ('L341_summary.csv', 'L341_summary_short.csv')
            ]
        }
    ]
    
    print("=" * 70)
    print("CSV Truncation Script")
    print("=" * 70)
    print(f"Cutoff datetime: {cutoff_datetime}")
    print(f"Will keep data from start of file until {cutoff_datetime}")
    print("=" * 70)
    
    results = []
    
    for task in tasks:
        folder = task['folder']
        print(f"\n{'=' * 70}")
        print(f"Processing folder: {folder}")
        print('=' * 70)
        
        if not os.path.exists(folder):
            print(f"ERROR: Folder not found: {folder}")
            continue
        
        for input_file, output_file in task['files']:
            input_path = os.path.join(folder, input_file)
            output_path = os.path.join(folder, output_file)
            
            success = truncate_csv_file(input_path, output_path, cutoff_datetime)
            results.append({
                'file': input_file,
                'success': success
            })
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for result in results:
        status = "✓ SUCCESS" if result['success'] else "✗ FAILED"
        print(f"{status}: {result['file']}")
    print("=" * 70)

if __name__ == "__main__":
    main()
