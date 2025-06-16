import os
import pandas as pd
import csv

def process_file(filepath, output_file):
    """Process a single file and write its first 30 and last 5 lines to the output."""
    print(f"Processing file: {filepath}")
    filename = os.path.basename(filepath)
    extension = os.path.splitext(filename)[1].lower()
    
    try:
        output_file.write(f"\n{'='*50}\n")
        output_file.write(f"File: {filepath}\n")
        output_file.write(f"Format: {extension}\n")
        output_file.write(f"First 30 lines (or less if shorter):\n")
        output_file.write("-"*50 + "\n")
        
        if extension in ['.xlsx', '.xls']:
            print(f"Reading Excel file: {filename}")
            df = pd.read_excel(filepath)
            # First 30 lines
            first_lines = df.head(30).to_string().split('\n')
            for line in first_lines:
                output_file.write(f"{line}\n")
            # Add ellipsis if there’s more data
            if len(df) > 30:
                output_file.write("...\n")
                last_lines = df.tail(5).to_string().split('\n')
                for line in last_lines:
                    output_file.write(f"{line}\n")
            print(f"Successfully processed {filename}")
                
        elif extension == '.csv':
            print(f"Reading CSV file: {filename}")
            with open(filepath, 'r', newline='') as f:
                lines = list(csv.reader(f))
                # First 30 lines
                for i, row in enumerate(lines[:30]):
                    output_file.write(f"{','.join(row)}\n")
                # Add ellipsis and last 5 if there’s more data
                if len(lines) > 30:
                    output_file.write("...\n")
                    for row in lines[-5:]:
                        output_file.write(f"{','.join(row)}\n")
            print(f"Successfully processed {filename}")
                    
        elif extension == '.txt':
            print(f"Reading text file: {filename}")
            with open(filepath, 'r') as f:
                lines = f.readlines()
                # First 30 lines
                for line in lines[:30]:
                    output_file.write(line)
                # Add ellipsis and last 5 if there’s more data
                if len(lines) > 30:
                    output_file.write("...\n")
                    for line in lines[-5:]:
                        output_file.write(line)
            print(f"Successfully processed {filename}")
                    
    except Exception as e:
        error_msg = f"Error processing {filename}: {str(e)}"
        print(error_msg)
        output_file.write(f"{error_msg}\n")

def print_directory_tree(parent_dir, output_file, prefix=""):
    """Recursively print the directory tree."""
    print(f"Scanning directory: {parent_dir}")
    items = sorted(os.listdir(parent_dir))
    for index, item in enumerate(items):
        path = os.path.join(parent_dir, item)
        is_last = index == len(items) - 1
        output_file.write(f"{prefix}{'└── ' if is_last else '├── '}{item}\n")
        
        if os.path.isdir(path):
            new_prefix = prefix + ("    " if is_last else "│   ")
            print_directory_tree(path, output_file, new_prefix)

def analyze_directory(parent_dir, output_filename="file_samples.txt"):
    """Walk through directory, collect file samples and structure, skipping 'overview' or 'TH' files."""
    print(f"Starting analysis of directory: {parent_dir}")
    supported_extensions = {'.xlsx', '.xls', '.csv', '.txt'}
    
    with open(output_filename, 'w', encoding='utf-8') as output_file:
        print(f"Writing output to: {output_filename}")
        output_file.write("Directory Structure and File Samples\n")
        output_file.write(f"Parent Directory: {parent_dir}\n")
        output_file.write(f"Generated on: March 29, 2025\n")
        output_file.write("="*50 + "\n\n")
        
        output_file.write("Directory Tree:\n")
        output_file.write("-"*50 + "\n")
        print("Generating directory tree...")
        print_directory_tree(parent_dir, output_file)
        output_file.write("\n" + "="*50 + "\n\n")
        print("Directory tree completed.")
        
        output_file.write("File Samples:\n")
        output_file.write("="*50 + "\n")
        print("Starting file samples collection...")
        
        for root, _, files in os.walk(parent_dir):
            print(f"Entering directory: {root}")
            for filename in files:
                # Skip files containing 'overview' or 'TH' (case-insensitive)
                if 'overview' in filename.lower() or 'th' in filename.lower():
                    print(f"Skipping file: {filename} (contains 'overview' or 'TH')")
                   # continue
                
                if os.path.splitext(filename)[1].lower() in supported_extensions:
                    filepath = os.path.join(root, filename)
                    process_file(filepath, output_file)
            print(f"Finished processing files in: {root}")
        print("File samples collection completed.")

def main():
    # Hardcode your directory path here
    parent_directory = r"G:\My Drive\Programing\Noise Survey Analysis\example files"
    print(f"Checking directory: {parent_directory}")
    print(f"Exists: {os.path.exists(parent_directory)}")
    print(f"Is directory: {os.path.isdir(parent_directory)}")
    
    if not os.path.isdir(parent_directory):
        print(f"Invalid directory path: {parent_directory}")
        print("Possible reasons:")
        print("- Path doesn't exist")
        print("- Permission denied")
        print("- Typo in path")
        print("Please verify the path and try again.")
        return
        
    try:
        analyze_directory(parent_directory)
        print(f"Analysis complete. Results written to 'file_samples.txt'")
    except Exception as e:
        print(f"An error occurred during analysis: {str(e)}")

if __name__ == "__main__":
    main()