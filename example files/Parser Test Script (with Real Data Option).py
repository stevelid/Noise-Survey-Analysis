# svan_parser.py
# Standalone module for the SvanParser class.

import pandas as pd
import numpy as np
import re
import os
import logging
from io import StringIO
from collections import Counter
from typing import Dict, List, Optional, Tuple

# Configure logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from data_parsers_completed import SvanParser


# ---------------------------------------------------------------------------
# svan_test.py
# Standalone test script for the SvanParser.
# ---------------------------------------------------------------------------
import unittest

class TestSvanParser(unittest.TestCase):
    """
    Test suite specifically for the refactored SvanParser.
    It uses a hardcoded path to your real data files.
    """
    
    # --- HARDCODED PATH TO YOUR EXAMPLE FILES ---
    # Note: Using raw string (r"...") to handle backslashes correctly on Windows.
    BASE_DATA_PATH = r"G:\My Drive\Programing\Noise Survey Analysis\example files"

    @classmethod
    def setUpClass(cls):
        """Verify that the base data path exists before running tests."""
        if not os.path.isdir(cls.BASE_DATA_PATH):
            raise NotADirectoryError(
                f"The hardcoded data path does not exist: {cls.BASE_DATA_PATH}"
            )
        logger.info(f"--- Running tests against REAL data in: {cls.BASE_DATA_PATH} ---")

    def _run_and_validate(self, file_path: str):
        """Helper to run the parser and perform common checks."""
        self.assertTrue(os.path.exists(file_path), f"Test file not found: {file_path}")
        parser = SvanParser()
        result = parser.parse(file_path)
        
        self.assertIsNotNone(result, "Parser returned None")
        self.assertIsInstance(result, dict, "Parser should return a dictionary")

        # Write output to a debug file
        with open("debug_svan_parser_output.txt", "a", encoding="utf-8") as f:
            f.write(f"--- Parser returned type: {result.get('type')} ---\n")
            if 'broadband' in result and isinstance(result['broadband'], pd.DataFrame) and not result['broadband'].empty:
                f.write(f"--- Broadband DataFrame Columns (from {result.get('type')}) ---\n")
                f.write(str(result['broadband'].columns.tolist()) + "\n")
            
            if 'spectral' in result and isinstance(result['spectral'], pd.DataFrame) and not result['spectral'].empty:
                f.write(f"--- Spectral DataFrame Columns (from {result.get('type')}) ---")
                f.write(str(result['spectral'].columns.tolist()) + "\n")
            
            if 'metadata' in result and isinstance(result['metadata'], dict):
                f.write(f"--- Metadata (from {result.get('type')}) ---\n")
                for k, v in result['metadata'].items():
                    f.write(f"  {k}: {v}\n")
            f.write("\n") # Add a newline for separation between file outputs
        
        return result
        
    def test_svan_log_file(self):
        """
        Tests the SvanParser on the log file, which has a 2-level header.
        """
        file_path = os.path.join(self.BASE_DATA_PATH, "Svan full data", "L259_log.csv")
        results = self._run_and_validate(file_path)
        
        # Check the overall type and presence of data
        self.assertEqual(results.get('type'), 'svan_log', "Incorrect type for log file.")
        self.assertIn('broadband', results, "Broadband data missing from log file results.")
        self.assertIn('spectral', results, "Spectral data missing from log file results.")
        self.assertIsInstance(results['broadband'], pd.DataFrame, "Broadband data is not a DataFrame.")
        self.assertIsInstance(results['spectral'], pd.DataFrame, "Spectral data is not a DataFrame.")

        # Validate broadband data
        bb_data = results['broadband']
        self.assertFalse(bb_data.empty)
        self.assertFalse(bb_data.columns.duplicated().any(), "Duplicate columns found in broadband data")
        self.assertIn('LAFmax', bb_data.columns)
        self.assertTrue(pd.api.types.is_numeric_dtype(bb_data['LAFmax']))
        
        # Validate spectral data
        spec_data = results['spectral']
        self.assertFalse(spec_data.empty)
        self.assertFalse(spec_data.columns.duplicated().any(), "Duplicate columns found in spectral data")
        self.assertTrue(any(col.startswith('LAeq_') for col in spec_data.columns))


    def test_svan_summary_file(self):
        """
        Tests the SvanParser on the summary file, which has a 3-level header.
        """
        file_path = os.path.join(self.BASE_DATA_PATH, "Svan full data", "L259_summary.csv")
        results = self._run_and_validate(file_path)
        
        # Check the overall type and presence of data
        self.assertEqual(results.get('type'), 'svan_summary', "Incorrect type for summary file.")
        self.assertIn('broadband', results, "Broadband data missing from summary file results.")
        self.assertIn('spectral', results, "Spectral data missing from summary file results.") # Assuming summary also has spectral
        self.assertIsInstance(results['broadband'], pd.DataFrame, "Broadband data is not a DataFrame.")
        self.assertIsInstance(results['spectral'], pd.DataFrame, "Spectral data is not a DataFrame.")

        # Validate broadband data
        bb_data = results['broadband']
        # Optionally, add validation for spectral data from summary files if expected
        # spec_data = results['spectral']
        # self.assertFalse(spec_data.empty)
        # self.assertTrue(any(col.startswith('LAeq_') for col in spec_data.columns))
        self.assertFalse(bb_data.empty)
        self.assertFalse(bb_data.columns.duplicated().any(), "Duplicate columns found in summary broadband data")
        self.assertIn('LAeq', bb_data.columns)
        self.assertTrue(pd.api.types.is_numeric_dtype(bb_data['LAeq']))

if __name__ == '__main__':
    print("--- Running Standalone Svan Parser Test (Direct Method Calls for Debugging) ---")
    # Instantiate the test class
    test_instance = TestSvanParser()
    
    # Call setUpClass equivalent if needed, or ensure paths are set
    TestSvanParser.setUpClass() # Call classmethod setup
    if not os.path.isdir(TestSvanParser.BASE_DATA_PATH):
        print(f"ERROR: Base data path not found: {TestSvanParser.BASE_DATA_PATH}")
        exit(1)

    print("\n--- Testing Svan Log File ---")
    try:
        test_instance.test_svan_log_file()
        print("Svan Log File test completed.")
    except AssertionError as e:
        print(f"Svan Log File test FAILED: {e}")
    except Exception as e:
        print(f"Svan Log File test ERRORED: {e}")

    print("\n--- Testing Svan Summary File ---")
    try:
        test_instance.test_svan_summary_file()
        print("Svan Summary File test completed.")
    except AssertionError as e:
        print(f"Svan Summary File test FAILED: {e}")
    except Exception as e:
        print(f"Svan Summary File test ERRORED: {e}")
