import sys
import os
from pprint import pprint
from noise_survey_analysis.core.data_parsers import NoiseDataParser

# --- Define paths to the test files based on your provided samples ---
# Please ensure this base path is correct for your system
BASE_SURVEY_PATH = r"G:\Shared drives\Venta\Jobs\5792 Swyncombe Field, Padel Courts\5792 Surveys\971-2"

SUMMARY_FILE_PATH = os.path.join(BASE_SURVEY_PATH, "L251_summary.csv")
LOG_FILE_PATH = os.path.join(BASE_SURVEY_PATH, "L251_log.csv")

def test_svan_parser(file_path, parser):
    """
    Tests the Svan parser with a given file and prints the results.
    """
    print(f"\n{'='*60}")
    print(f"Attempting to parse file: {os.path.basename(file_path)}")
    print(f"{'='*60}")

    if not os.path.exists(file_path):
        print(f"---! ERROR: File not found at path: {file_path}")
        return

    try:
        # The parse method now returns a list of result dictionaries
        results = parser.parse(file_path)
        
        print(f"Parser returned {len(results)} data object(s).")
        print("-" * 25)

        for i, result in enumerate(results):
            print(f"\n--- Result Object #{i+1} ---")
            
            # Use pprint for cleanly printing the dictionary structure
            # We print metadata first, then details of the data
            if isinstance(result, dict):
                data_df = result.get('data')
                metadata = {k: v for k, v in result.items() if k != 'data'}
                
                print("Metadata:")
                pprint(metadata)
                
                print("\nData Head:")
                if data_df is not None and not data_df.empty:
                    print(data_df.head())
                    print(f"\nShape: {data_df.shape}")
                    print(f"Columns: {data_df.columns.to_list()}")
                else:
                    print(" (No data in this object)")
            else:
                print(f"Unexpected result format: {type(result)}")
        
        print(f"\n--- Successfully parsed {os.path.basename(file_path)} ---")

    except Exception as e:
        print(f"---! Svan parse failed for {file_path}: {e}")
        # In case of an exception, you might want to see the traceback
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Initialize a single Svan parser instance
    svan_parser = NoiseDataParser.get_parser("svan")
    
    # Test the summary file
    test_svan_parser(SUMMARY_FILE_PATH, svan_parser)
    
    # Test the log file
    test_svan_parser(LOG_FILE_PATH, svan_parser)

    print(f"\n{'='*60}")
    print("Test script finished.")
    print(f"{'='*60}")