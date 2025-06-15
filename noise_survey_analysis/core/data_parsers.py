"""
Data parsing module for noise survey analysis.
Parses individual files based on specified parser type.
"""

import pandas as pd
import numpy as np
import re
import os
import logging # Use logging
from io import StringIO
from collections import Counter

logger = logging.getLogger(__name__) # Setup logger for this module

def safe_convert_to_float(df, columns=None):
    """
    Convert specified columns in a DataFrame to float type, handling errors gracefully.
    
    Parameters:
    df (pd.DataFrame): DataFrame containing columns to convert
    columns (list, optional): List of column names to convert. If None, all non-datetime columns are converted.
    
    Returns:
    pd.DataFrame: DataFrame with converted columns
    """
    if columns is None:
        columns = [col for col in df.columns if not pd.api.types.is_datetime64_any_dtype(df[col])]

    for col in columns:
        # Added more checks for robustness
        if col in df.columns and isinstance(col, str) and col not in ["", "Datetime", "_", "Start Date", "Start Time", "End Date", "End Time", "Date", "Time", "Band [Hz]"]:
            try:
                # Use pd.to_numeric for better handling of various non-numeric strings
                df[col] = pd.to_numeric(df[col], errors='coerce')
            except Exception as e:
                logger.warning(f"Could not convert column '{col}' to numeric values: {e}")

    return df


class NoiseDataParser:
    """Base class for noise data parsers."""
    
    @staticmethod
    def get_parser(parser_type):
        """
        Factory method to get the appropriate parser instance based on type.
        
        Parameters:
        parser_type (str): Type of parser to create ('sentry', 'nti', 'svan', 'audio')
        
        Returns:
        NoiseDataParser: An instance of the appropriate parser subclass
        
        Raises:
        ValueError: If parser_type is not recognized
        """
        parser_mapping = {
            'sentry': NoiseSentryParser,
            'nti': NTiParser,
            'svan': SvanParser,
            'audio': AudioParser
        }
        parser_type_lower = parser_type.lower()
        if parser_type_lower not in parser_mapping:
            raise ValueError(f"Unknown parser type: {parser_type}. "
                            f"Available types: {list(parser_mapping.keys())}")
        return parser_mapping[parser_type_lower]()


class NoiseSentryParser(NoiseDataParser):
    """Parser for Noise Sentry CSV files."""
    
    def parse(self, file_path):
        """
        Parse a Noise Sentry CSV file into a DataFrame.
        
        Parameters:
        file_path (str): Path to the CSV file
        
        Returns:
        pd.DataFrame: DataFrame containing parsed data
        """
        if not isinstance(file_path, str) or not file_path.lower().endswith('.csv'):
             raise ValueError(f"Invalid file path or type for Sentry parser: {file_path}")

        logger.info(f'Reading Sentry file: {file_path}')
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: # Added encoding/errors
                lines = f.readlines()

            if not lines:
                logger.warning(f"Sentry file is empty: {file_path}")
                return pd.DataFrame() # Return empty DataFrame

            headers = lines[0].strip().split(',')
            if not headers:
                 logger.warning(f"Could not parse headers in Sentry file: {file_path}")
                 return pd.DataFrame()

            headers[0] = 'Datetime' # Assume first column is always Datetime

            replacements = {
                'LEQ dB-A ': 'LAeq',
                'Lmax dB-A ': 'LAFmax',
                'L10 dB-A ': 'LAF10',
                'L90 dB-A ': 'LAF90'
            }
            headers = [replacements.get(h, h) for h in headers] # More concise replacement

            # Handle potential empty lines or lines with wrong number of columns
            data = []
            num_headers = len(headers)
            for i, line in enumerate(lines[1:]):
                parts = line.strip().split(',')
                if len(parts) == num_headers:
                    data.append(parts)
                else:
                    logger.warning(f"Skipping line {i+2} in {file_path}: expected {num_headers} columns, got {len(parts)}")

            if not data:
                 logger.warning(f"No valid data rows found in Sentry file: {file_path}")
                 return pd.DataFrame()

            ns_df = pd.DataFrame(data, columns=headers)
            ns_df['Datetime'] = pd.to_datetime(ns_df['Datetime'], errors='coerce') # Coerce errors
            ns_df.dropna(subset=['Datetime'], inplace=True) # Drop rows where datetime failed

            # Use safe_convert_to_float
            ns_df = safe_convert_to_float(ns_df)

            return ns_df
        except FileNotFoundError:
             logger.error(f"Sentry file not found: {file_path}")
             return pd.DataFrame()
        except Exception as e:
             logger.error(f"Error parsing Sentry file {file_path}: {e}", exc_info=True)
             return pd.DataFrame()


class SvanParser(NoiseDataParser):
    """
    Parses Svan CSV files using a heuristic based on finding the 'Date & Time' row
    and combining it with the row above for header information.
    Extracts Datetime, LAeq, LAmax, LA10, LA90, and Spectral Leq/Lmax data.
    """

    # Regex for cleaning combined headers
    CLEAN_PAT = re.compile(r'\s*\((?:SR|TH|Lin|Fast|Slow)\)|\[dB\]|\s*Histogram|\s*1/3\s+Oct', flags=re.IGNORECASE)
    # Regex to identify potential frequency columns in the second header row
    FREQ_PAT = re.compile(r'^\s*(\d+(?:\.\d+)?)\s?Hz\s*$', flags=re.IGNORECASE)


    def parse(self, file_path):
        """
        Parses Svan CSV files using the two-row combination heuristic.
        """
        if not isinstance(file_path, str) or not file_path.lower().endswith(('.csv', '.txt')): # Allow txt
             raise ValueError(f"Invalid file path or type for Svan parser: {file_path}")

        logger.info(f'Parsing Svan file with heuristic: {file_path}')

        try:
            # --- 1. Read Header Lines ---
            max_header_read = 20 # Read enough lines to find headers
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    header_lines = [f.readline() for _ in range(max_header_read)]
                    if not header_lines:
                        logger.warning(f"Svan file appears empty: {file_path}")
                        return pd.DataFrame()
            except Exception as e:
                logger.error(f"Could not read initial lines of Svan file: {file_path}. Error: {e}", exc_info=True)
                return pd.DataFrame()

            # --- 2. Find 'Date & Time' Row (headerRow2) ---
            header_row2_idx = -1
            for idx, line in enumerate(header_lines):
                line_lower = line.lower().strip()
                # Check if it starts with date & time pattern (flexible check)
                if line_lower.startswith('date & time') or line_lower.startswith('start date & time'):
                    # Check if the *first column* specifically contains it more reliably
                    try:
                         first_cell = line.split(',')[0].strip().lower()
                         if 'date & time' in first_cell:
                              header_row2_idx = idx
                              logger.debug(f"Found 'Date & Time' row marker at index {header_row2_idx}")
                              break
                    except IndexError:
                         continue # Ignore lines that can't be split

            if header_row2_idx == -1:
                logger.error(f"Could not find 'Date & Time' or 'Start Date & Time' row within first {max_header_read} lines of {file_path}")
                return pd.DataFrame()

            # --- 3. Identify headerRow1 ---
            header_row1_idx = header_row2_idx - 1
            if header_row1_idx < 0:
                logger.error(f"Header structure error: 'Date & Time' row found at index 0, no preceding header row in {file_path}")
                return pd.DataFrame()

            # --- 4. Parse and Combine Header Rows ---
            try:
                # Use pandas read_csv on StringIO for robust parsing of the two header lines
                row1_content = pd.read_csv(StringIO(header_lines[header_row1_idx]), header=None, low_memory=False).iloc[0].fillna('').astype(str).tolist()
                row2_content = pd.read_csv(StringIO(header_lines[header_row2_idx]), header=None, low_memory=False).iloc[0].fillna('').astype(str).tolist()
            except Exception as e:
                 logger.error(f"Error parsing header line content using pandas for {file_path}: {e}", exc_info=True)
                 return pd.DataFrame()

            num_cols = max(len(row1_content), len(row2_content))
            row1_content += [''] * (num_cols - len(row1_content))
            row2_content += [''] * (num_cols - len(row2_content))

            combined_headers = [
                f"{r1.strip().rstrip()}_{r2.strip().lstrip()}" for r1, r2 in zip(row1_content, row2_content)
            ]
            # Remove trailing underscores if row2 was empty
            combined_headers = [h[:-1] if h.endswith('_') else h for h in combined_headers]
            # Remove leading underscores if row1 was empty
            combined_headers = [h[1:] if h.startswith('_') else h for h in combined_headers]


            # --- 5. Clean Combined Headers ---
            # Skip columns with empty headers
            cleaned_headers = []
            valid_indices = []
            
            for i, header in enumerate(combined_headers):
                # First apply regex cleanup
                cleaned_header = self.CLEAN_PAT.sub('', header).strip()
                
                # Then ensure no spaces before underscores
                cleaned_header = re.sub(r'\s+_', '_', cleaned_header)
                
                if cleaned_header: # Skip empty headers
                    cleaned_headers.append(cleaned_header)
                    valid_indices.append(i)
                    
            logger.debug(f"Cleaned combined headers: {cleaned_headers}")

            # --- 6. Standardize Headers ---
            # Map cleaned headers to final standard names
            final_standard_names = []
            processed_indices = set() # Track original indices to avoid re-mapping
            for idx, (i, header) in enumerate(zip(valid_indices, cleaned_headers)):
                standard_name = None
                # --- Prioritized Mapping ---
                # Datetime (must be first column according to heuristic)
                if idx == 0 and ('date & time' in header.lower() or 'start date & time' in header.lower()):
                    standard_name = 'Datetime'
                # Broadband LAeq
                elif re.match(r'^LAeq\s*\*?$', header, re.IGNORECASE):
                    standard_name = 'LAeq'
                # Broadband LAmax
                elif re.match(r'^LAFmax\s*\*?$', header, re.IGNORECASE):
                    standard_name = 'LAmax'
                # Broadband L10
                elif re.match(r'^LAeq\s*LN\s*\*?_L10$', header, re.IGNORECASE):
                    standard_name = 'LA10'
                # Broadband L90
                elif re.match(r'^LAeq\s*LN\s*\*?_L90$', header, re.IGNORECASE):
                    standard_name = 'LA90'
                # Spectral Data (Check if row2 was a frequency)
                else:
                    # Use the header parts directly instead of rechecking row2_content
                    parts = header.split('_')
                    if len(parts) > 1:
                        freq_match = self.FREQ_PAT.match(parts[1])
                        if freq_match:
                            freq = freq_match.group(1)
                            base_param_cleaned = parts[0]
                            # Standardize base parameter
                            if base_param_cleaned.upper().startswith('LAEQ') or base_param_cleaned.upper().startswith('LEQ'):
                                standard_name = f"LZeq_{freq}"  # Changed to LZeq to match REQUIRED_SPECTRAL_PREFIXES
                            elif base_param_cleaned.upper().startswith('LAFMAX') or base_param_cleaned.upper().startswith('LFMAX'):
                                standard_name = f"LZFmax_{freq}"  # Changed to LZFmax to match REQUIRED_SPECTRAL_PREFIXES
                            elif base_param_cleaned.upper().startswith('LA90') or base_param_cleaned.upper().startswith('L90'):
                                standard_name = f"LZF90_{freq}"  # Added to match REQUIRED_SPECTRAL_PREFIXES
                            elif base_param_cleaned.upper().startswith('LA10') or base_param_cleaned.upper().startswith('L10'):
                                standard_name = f"LZF10_{freq}"  # Added for consistency
                            else:
                                # For other parameters, try to convert to expected format
                                # Extract weighting and parameter type
                                weighting_match = re.match(r'^L([A-Z])[F]?(.+)$', base_param_cleaned, re.IGNORECASE)
                                if weighting_match:
                                    # Replace with Z weighting for consistency
                                    param_type = weighting_match.group(2)
                                    standard_name = f"LZ{param_type}_{freq}"
                                else:
                                    standard_name = f"{base_param_cleaned}_{freq}"  # Fallback, removed Hz suffix
                    # If we couldn't extract frequency from header parts, use the original header
                    if not standard_name:
                        standard_name = header # Keep cleaned name if no standard match

                # Store the final name
                if standard_name:
                    final_standard_names.append(standard_name)
                    processed_indices.add(i)
                else:
                    # Should not happen if standard_name = header fallback works
                    logger.warning(f"Could not determine standard name for cleaned header: '{header}' at original index {i}")
                    final_standard_names.append(f"_unknown_{i}") # Placeholder


            # --- 7. Prepare for Reading ---
            if 'Datetime' not in final_standard_names:
                 logger.error(f"Critical: 'Datetime' column could not be standardized in {file_path}. Standard names: {final_standard_names}")
                 # Attempt fallback: If first column wasn't mapped, assume it's Datetime
                 if cleaned_headers and 0 not in processed_indices:
                      logger.warning("Applying fallback: Assuming first column is Datetime.")
                      final_standard_names[0] = 'Datetime'
                 else:
                      return pd.DataFrame() # Fail if no datetime

            # Check for duplicate standard names before reading
            name_counts = Counter(final_standard_names)
            duplicates = {item: count for item, count in name_counts.items() if count > 1}
            if duplicates:
                logger.warning(f"Duplicate standard column names generated for {file_path}: {duplicates}. Implementing renaming strategy.")
                
                # Implement renaming strategy by appending _1, _2, etc.
                renamed_headers = []
                counter_dict = {}
                
                for header in final_standard_names:
                    if header in duplicates:
                        # Initialize counter if this is the first occurrence
                        if header not in counter_dict:
                            counter_dict[header] = 1
                        
                        # Append counter to duplicate name
                        new_name = f"{header}+{counter_dict[header]}"
                        renamed_headers.append(new_name)
                        
                        # Increment counter for next occurrence
                        counter_dict[header] += 1
                    else:
                        # Non-duplicate names pass through unchanged
                        renamed_headers.append(header)
                
                # Replace the original headers with renamed ones
                final_standard_names = renamed_headers
                
                logger.debug(f"Renamed duplicate headers: {final_standard_names}")
                # No need to return empty DataFrame, we've fixed the issue
                
            # Final cleanup - ensure no spaces before underscores in any column names
            final_standard_names = [re.sub(r'\s+_', '_', name) for name in final_standard_names]

            logger.debug(f"Final standard names: {final_standard_names}")

            # --- 8. Read Data ---
            data_start_row = header_row2_idx + 1
            try:
                # We need to use usecols to select only the columns with valid headers
                df = pd.read_csv(
                    file_path,
                    header=None,
                    names=range(num_cols),  # Temporary numeric names
                    skiprows=data_start_row,
                    low_memory=False,
                    encoding='utf-8',
                    on_bad_lines='warn',
                    skip_blank_lines=True
                )
                
                # Select only the columns with valid headers and rename them
                df = df.iloc[:, valid_indices].copy()
                df.columns = final_standard_names
            except ValueError as ve:
                 if "names implies" in str(ve) and "columns" in str(ve):
                       logger.error(f"Column count mismatch error reading data for {file_path}. "
                                    f"Expected {len(final_standard_names)} columns based on headers. Check file structure or header parsing. Error: {ve}")
                       return pd.DataFrame()
                 else: raise # Re-raise other ValueErrors
            except Exception as e:
                 logger.error(f"Error during pandas read_csv for Svan data {file_path}: {e}", exc_info=True)
                 return pd.DataFrame()

            # --- 9. Post-process ---
            # Filter summary rows (heuristic: check if Datetime looks valid)
            if 'Datetime' in df.columns:
                original_rows = len(df)
                # Attempt conversion to datetime, coercing errors
                dt_converted = pd.to_datetime(df['Datetime'], errors='coerce')
                # Keep rows where conversion was successful
                df = df[dt_converted.notna()].copy() # Use .copy() to avoid SettingWithCopyWarning
                df['Datetime'] = dt_converted[dt_converted.notna()] # Assign back the converted values
                if len(df) < original_rows:
                     logger.info(f"Removed {original_rows - len(df)} potential summary/invalid rows based on Datetime conversion in {file_path}")

            if df.empty:
                logger.warning(f"DataFrame is empty after reading/filtering summary rows: {file_path}")
                return df

            # Apply remaining post-processing (numeric conversion)
            df = self._post_process_data(df, file_path)

            return df

        except FileNotFoundError:
             logger.error(f"Svan file not found: {file_path}")
             return pd.DataFrame()
        except Exception as e:
            logger.error(f"General error parsing Svan file {file_path} with heuristic: {e}", exc_info=True)
            return pd.DataFrame()

    def _post_process_data(self, df, file_path):
        """ Post-processing specific to this parser (mainly numeric conversion)."""
        if df.empty: return df

        # Datetime conversion already attempted during summary row filtering

        # Additional standardization for spectral columns
        from .config import REQUIRED_SPECTRAL_PREFIXES
        
        # First, standardize any remaining spectral columns that might have been missed
        renamed_columns = {}
        for col in df.columns:
            if col != 'Datetime':
                # Check if this is a spectral column (has frequency in the name)
                parts = col.split('_')
                if len(parts) > 1 and parts[1].isnumeric():
                    # Try to extract frequency value
                    freq_match = re.search(r'(\d+(?:\.\d+)?)', parts[-1])
                    if freq_match:
                        freq = freq_match.group(1)
                        base_param = '_'.join(parts[:-1])
                        
                        # Standardize to required format
                        if base_param.upper().startswith('LAEQ') or base_param.upper().startswith('LEQ'):
                            new_name = f"LZeq_{freq}"
                        elif base_param.upper().startswith('LAFMAX') or base_param.upper().startswith('LFMAX'):
                            new_name = f"LZFmax_{freq}"
                        elif base_param.upper().startswith('LA90') or base_param.upper().startswith('L90'):
                            new_name = f"LZF90_{freq}"
                        elif base_param.upper().startswith('LA10') or base_param.upper().startswith('L10'):
                            new_name = f"LZF10_{freq}"
                        elif base_param.upper().startswith('L'):
                            # Try to extract weighting and parameter type
                            weighting_match = re.match(r'^L([A-Z])[F]?(.+)$', base_param, re.IGNORECASE)
                            if weighting_match:
                                param_type = weighting_match.group(2)
                                new_name = f"LZ{param_type}_{freq}"
                            else:
                                # Keep original but remove Hz suffix if present
                                new_name = f"{base_param}_{freq}"
                        else:
                            # Keep original but remove Hz suffix if present
                            new_name = f"{base_param}_{freq}"
                        
                        # Remove Hz suffix if present and clean up any trailing spaces
                        new_name = re.sub(r'Hz\s*$', '', new_name).strip()
                        
                        if new_name != col:
                            renamed_columns[col] = new_name
        
        # Apply column renames if any
        if renamed_columns:
            logger.info(f"Standardizing {len(renamed_columns)} spectral column names in {file_path}")
            df = df.rename(columns=renamed_columns)

        # Convert other columns to numeric
        numeric_cols = [col for col in df.columns if col != 'Datetime']
        df = safe_convert_to_float(df, columns=numeric_cols)

        logger.info(f"Post-processing complete for {file_path}. Final shape: {df.shape}")
        return df

class NTiParser(NoiseDataParser):
    """Parser for individual NTi sound meter data files (RPT, RTA, LOG)."""

    def parse(self, file_path):
        """
        Parses a single NTi file and determines its type.

        Parameters:
        file_path (str): Full path to the specific NTi file.

        Returns:
        dict or None: A dictionary containing {'type': file_type, 'data': df, 'metadata': metadata}
                      (e.g., {'type': 'RPT', 'data': rpt_df, 'metadata': {...}})
                      Returns None if the file type cannot be determined or parsing fails.
        """
        if not isinstance(file_path, str) or not os.path.exists(file_path):
             logger.error(f"NTi file not found or invalid path: {file_path}")
             return None # Indicate failure

        logger.info(f"Attempting to parse NTi file: {file_path}")
        filename = os.path.basename(file_path).lower() # Use lowercase for matching

        try:
            # Determine file type based on filename suffix
            if filename.endswith('_123_rpt_report.txt'):
                logger.debug(f"Detected NTi RPT file: {file_path}")
                return self._parse_specific_file(file_path, self._parse_rpt_content, 'RPT')
            elif filename.endswith('_rta_3rd_rpt_report.txt'):
                logger.debug(f"Detected NTi RTA file: {file_path}")
                return self._parse_specific_file(file_path, self._parse_rta_content, 'RTA')
            elif filename.endswith('_123_log.txt'):
                logger.debug(f"Detected NTi RPT_LOG file: {file_path}")
                return self._parse_specific_file(file_path, self._parse_rpt_log_content, 'RPT_LOG')
            elif filename.endswith('_rta_3rd_log.txt'):
                logger.debug(f"Detected NTi RTA_LOG file: {file_path}")
                return self._parse_specific_file(file_path, self._parse_rta_log_content, 'RTA_LOG')
            else:
                logger.warning(f"Could not determine NTi file type from filename: {file_path}")
                return None # Indicate failure
        except Exception as e:
             logger.error(f"Error parsing NTi file {file_path}: {e}", exc_info=True)
             return None # Indicate failure


    def _parse_specific_file(self, file_path, parse_content_func, file_type):
        """Helper to read file content and call the appropriate content parser."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Filter out lines after "#CheckSum" is reached
            checksum_index = next((i for i, line in enumerate(lines) if "#CheckSum" in line), len(lines))
            lines_to_parse = lines[:checksum_index]

            if not lines_to_parse:
                 logger.warning(f"NTi file appears empty (or only checksum): {file_path}")
                 return {'type': file_type, 'data': pd.DataFrame(), 'metadata': {}}

            # Parse metadata (common logic)
            metadata = self._extract_metadata(lines_to_parse)

            # Call the specific content parsing function
            df = parse_content_func(lines_to_parse, file_path) # Pass file_path for logging

            return {'type': file_type, 'data': df, 'metadata': metadata}

        except FileNotFoundError:
             logger.error(f"NTi file disappeared before parsing?: {file_path}")
             return None
        except Exception as e:
             logger.error(f"Error reading or processing content for {file_type} file {file_path}: {e}", exc_info=True)
             return {'type': file_type, 'data': pd.DataFrame(), 'metadata': metadata if 'metadata' in locals() else {}} # Return empty df but keep metadata if extracted

    def _extract_metadata(self, lines):
        """Extracts Hardware Configuration and Measurement Setup sections."""
        hardware_config = {}
        measurement_setup = {}
        current_section = None
        for line in lines:
            stripped_line = line.strip()
            if stripped_line.startswith("Hardware Configuration"):
                current_section = hardware_config
                continue
            elif stripped_line.startswith("Measurement Setup"):
                current_section = measurement_setup
                continue
            elif stripped_line.startswith("#"): # Start of data sections
                current_section = None
                continue # Stop processing metadata lines

            if current_section is not None:
                parts = stripped_line.split(':', 1)
                if len(parts) == 2:
                    key, value = map(str.strip, parts)
                    if key: # Ensure key is not empty
                         current_section[key] = value

        return {'hardware_config': hardware_config, 'measurement_setup': measurement_setup}


    # --- Content Parsing Functions ---
    # These now take the *lines* and file_path as input

    def _parse_rpt_content(self, lines, file_path):
        """Parse content from an RPT file (123 Report)"""
        data_start_marker = "# Broadband Results"
        try:
            table_start_idx = next((i for i, line in enumerate(lines) if line.strip().startswith(data_start_marker)), -1)
            if table_start_idx == -1:
                logger.warning(f"'{data_start_marker}' not found in RPT file: {file_path}")
                return pd.DataFrame()

            data_lines = lines[table_start_idx + 1:]
            data = [[item.strip() for item in line.strip().split('\t')] for line in data_lines]
            data = [row for row in data if row and any(item.strip() for item in row)] # Filter empty rows

            if len(data) <= 3: # Header lines + potentially summary
                logger.warning(f"Insufficient data rows found in RPT file content: {file_path}")
                return pd.DataFrame()

            # Headers are usually in the second row of the data block (index 1)
            header_row = data[1]
            # Find max columns based on actual data rows (index 3 onwards)
            max_data_cols = max(len(row) for row in data[3:]) if len(data) > 3 else 0
            num_cols_to_use = min(len(header_row), max_data_cols) # Use the minimum to avoid index errors

            column_headers = ["Start Date", "Start Time", "End Date", "End Time"] + list(header_row[4:num_cols_to_use])
            column_headers = [h.replace('.0%', '') for h in column_headers] # Clean headers

            # Ensure data rows are sliced correctly and match header length
            rpt_data_rows = [row[:num_cols_to_use] for row in data[3:]]

            rpt_df = pd.DataFrame(rpt_data_rows, columns=column_headers)
            rpt_df['Datetime'] = pd.to_datetime(rpt_df['Start Date'] + ' ' + rpt_df['Start Time'], errors='coerce')
            rpt_df.dropna(subset=['Datetime'], inplace=True)
            rpt_df = safe_convert_to_float(rpt_df)
            return rpt_df

        except Exception as e:
            logger.error(f"Error parsing RPT content from {file_path}: {e}", exc_info=True)
            return pd.DataFrame()


    def _parse_rta_content(self, lines, file_path):
        """Parse content from an RTA file (RTA 3rd Report)"""
        data_start_marker = "# RTA Results"
        try:
            table_start_idx = next((i for i, line in enumerate(lines) if line.strip().startswith(data_start_marker)), -1)
            if table_start_idx == -1:
                logger.warning(f"'{data_start_marker}' not found in RTA file: {file_path}")
                return pd.DataFrame()

            data = [[item.strip() for item in line.strip().split('\t')] for line in lines[table_start_idx + 1:]]
            data = [row for row in data if row and any(item.strip() for item in row)]

            if len(data) <= 3:
                logger.warning(f"Insufficient data rows found in RTA file content: {file_path}")
                return pd.DataFrame()

            # Find "Band [Hz]" row to locate frequency headers
            try:
                 band_row_idx, band_col_idx = next(
                     (i, j) for i, row in enumerate(data)
                     for j, cell in enumerate(row) if cell == "Band [Hz]"
                 )
            except StopIteration:
                 logger.error(f"'Band [Hz]' marker not found in RTA headers: {file_path}")
                 return pd.DataFrame()

            # Headers are complex: type row (band_row_idx-1), frequency row (band_row_idx)
            types_row = data[band_row_idx - 1][band_col_idx + 1:]
            frequencies_row = data[band_row_idx][band_col_idx + 1:]

            # Combine type and frequency, ensuring lists are same length
            min_len = min(len(types_row), len(frequencies_row))
            rta_headers = [f"{typ}_{freq}" for typ, freq in zip(types_row[:min_len], frequencies_row[:min_len])]
            rta_headers = [h.replace('.0%', '') for h in rta_headers]

            # Combine with initial columns (Date, Time, etc.)
            initial_headers = ["Start Date", "Start Time", "End Date", "End Time", "Band [Hz]"] # Assume these 5
            column_headers = initial_headers + rta_headers

            # Data starts 2 rows below "Band [Hz]" row
            data_start_row_idx = band_row_idx + 2
            if data_start_row_idx >= len(data):
                 logger.warning(f"No data rows found below headers in RTA file: {file_path}")
                 return pd.DataFrame()

            # Ensure data rows match header length
            num_cols_to_use = len(column_headers)
            rta_data_rows = [row[:num_cols_to_use] for row in data[data_start_row_idx:]]

            rta_df = pd.DataFrame(rta_data_rows, columns=column_headers)
            rta_df['Datetime'] = pd.to_datetime(rta_df['Start Date'] + ' ' + rta_df['Start Time'], errors='coerce')
            rta_df.dropna(subset=['Datetime'], inplace=True)
            rta_df = safe_convert_to_float(rta_df)
            return rta_df

        except Exception as e:
             logger.error(f"Error parsing RTA content from {file_path}: {e}", exc_info=True)
             return pd.DataFrame()


    def _parse_rpt_log_content(self, lines, file_path):
        """Parse content from an RPT LOG file (123 Log)"""
        # Note: Structure might be slightly different from RPT Report
        data_start_marker = "# Broadband LOG Results" # Check exact marker
        desired_columns = ['Datetime', 'LAF90', 'LAF10', 'LAFmax_dt', 'LAeq_dt'] # Keep desired columns for now
        try:
            table_start_idx = next((i for i, line in enumerate(lines) if line.strip().startswith(data_start_marker)), -1)
            if table_start_idx == -1:
                logger.warning(f"'{data_start_marker}' not found in RPT LOG file: {file_path}")
                return pd.DataFrame()

            data_lines = lines[table_start_idx + 1:]
            data = [[item.strip() for item in line.split('\t')] for line in data_lines]
            data = [row for row in data if row and any(item.strip() for item in row)]

            if len(data) <= 2: # Header row + possibly summary
                logger.warning(f"Insufficient data rows found in RPT LOG file content: {file_path}")
                return pd.DataFrame()

            # Header row is usually the first line in the data block (index 0)
            column_headers = list(data[0])
            column_headers = [h.replace('.0%', '') for h in column_headers]

            # Data starts from the third line (index 2)
            data_start_row_idx = 2
            if data_start_row_idx >= len(data):
                 logger.warning(f"No data rows found below headers in RPT LOG file: {file_path}")
                 return pd.DataFrame()

            # Ensure data rows match header length
            num_cols_to_use = len(column_headers)
            # Often log files have summary lines at the end - try to detect and exclude
            # A simple heuristic: check if the last few lines look like dates/times
            end_idx = len(data)
            for i in range(len(data) - 1, data_start_row_idx, -1):
                try:
                    # If the first two columns parse as date/time, it's likely data
                    pd.to_datetime(data[i][0] + ' ' + data[i][1], errors='raise')
                    end_idx = i + 1
                    break
                except:
                    # If it doesn't parse, it might be a summary line
                    continue

            log_data_rows = [row[:num_cols_to_use] for row in data[data_start_row_idx:end_idx]]

            if not log_data_rows:
                 logger.warning(f"No valid data rows extracted after filtering in RPT LOG: {file_path}")
                 return pd.DataFrame()

            log_df = pd.DataFrame(log_data_rows, columns=column_headers)

            if 'Date' not in log_df.columns or 'Time' not in log_df.columns:
                 logger.error(f"Missing 'Date' or 'Time' column in RPT LOG: {file_path}")
                 return pd.DataFrame()

            log_df['Datetime'] = pd.to_datetime(log_df['Date'] + ' ' + log_df['Time'], errors='coerce')
            log_df.dropna(subset=['Datetime'], inplace=True)
            log_df = safe_convert_to_float(log_df)

            # Select desired columns if they exist
            final_cols = [col for col in desired_columns if col in log_df.columns]
            missing_cols = set(desired_columns) - set(final_cols)
            if missing_cols:
                 logger.warning(f"Missing desired columns in RPT LOG {file_path}: {missing_cols}. Returning available columns.")
                 final_cols = [col for col in log_df.columns if col not in ['Date', 'Time']] # Return all parsed except original Date/Time

            return log_df[final_cols]

        except Exception as e:
            logger.error(f"Error parsing RPT LOG content from {file_path}: {e}", exc_info=True)
            return pd.DataFrame()

    def _parse_rta_log_content(self, lines, file_path):
        """Parse content from an RTA LOG file (RTA 3rd Log)"""
        # Similar structure to RTA Report, but often uses 'Date'/'Time' cols
        data_start_marker = "# RTA LOG Results" # Check exact marker
        try:
            table_start_idx = next((i for i, line in enumerate(lines) if line.strip().startswith(data_start_marker)), -1)
            if table_start_idx == -1:
                logger.warning(f"'{data_start_marker}' not found in RTA LOG file: {file_path}")
                return pd.DataFrame()

            data = [[item.strip() for item in line.strip().split('\t')] for line in lines[table_start_idx + 1:]]
            data = [row for row in data if row and any(item.strip() for item in row)]

            if len(data) <= 2:
                logger.warning(f"Insufficient data rows found in RTA LOG file content: {file_path}")
                return pd.DataFrame()

            # Find "Band [Hz]" row for headers
            try:
                band_row_idx, band_col_idx = next(
                     (i, j) for i, row in enumerate(data)
                     for j, cell in enumerate(row) if cell == "Band [Hz]"
                 )
            except StopIteration:
                 logger.error(f"'Band [Hz]' marker not found in RTA LOG headers: {file_path}")
                 return pd.DataFrame()

            # Header rows (type and frequency)
            types_row = data[band_row_idx - 1][band_col_idx + 1:]
            frequencies_row = data[band_row_idx][band_col_idx + 1:]

            min_len = min(len(types_row), len(frequencies_row))
            rta_headers = [f"{typ}_{freq}" for typ, freq in zip(types_row[:min_len], frequencies_row[:min_len])]
            rta_headers = [h.replace('.0%', '') for h in rta_headers]

            # Initial headers likely include 'Date', 'Time' instead of Start/End
            # Look for 'Date' and 'Time' in the Band [Hz] row
            initial_headers = list(data[band_row_idx][:band_col_idx + 1])
            if 'Date' not in initial_headers or 'Time' not in initial_headers:
                 logger.warning(f"Could not find 'Date'/'Time' in expected header row for RTA LOG: {file_path}. Using placeholders.")
                 initial_headers = [f"_col_{i}" for i in range(band_col_idx + 1)]
                 # Try to find Date/Time by name anyway
                 for i, h in enumerate(data[band_row_idx][:band_col_idx + 1]):
                    if h == 'Date': initial_headers[i] = 'Date'
                    if h == 'Time': initial_headers[i] = 'Time'

            column_headers = initial_headers + rta_headers

            # Data starts 2 rows below "Band [Hz]"
            data_start_row_idx = band_row_idx + 2
            if data_start_row_idx >= len(data):
                 logger.warning(f"No data rows found below headers in RTA LOG file: {file_path}")
                 return pd.DataFrame()

            # Check for summary lines at the end (similar to RPT LOG)
            end_idx = len(data)
            date_col_idx = initial_headers.index('Date') if 'Date' in initial_headers else -1
            time_col_idx = initial_headers.index('Time') if 'Time' in initial_headers else -1

            if date_col_idx != -1 and time_col_idx != -1:
                for i in range(len(data) - 1, data_start_row_idx, -1):
                    try:
                        pd.to_datetime(data[i][date_col_idx] + ' ' + data[i][time_col_idx], errors='raise')
                        end_idx = i + 1
                        break
                    except:
                        continue

            # Ensure data rows match header length
            num_cols_to_use = len(column_headers)
            log_data_rows = [row[:num_cols_to_use] for row in data[data_start_row_idx:end_idx]]

            if not log_data_rows:
                 logger.warning(f"No valid data rows extracted after filtering in RTA LOG: {file_path}")
                 return pd.DataFrame()

            log_df = pd.DataFrame(log_data_rows, columns=column_headers)

            if 'Date' not in log_df.columns or 'Time' not in log_df.columns:
                 logger.error(f"Failed to assign 'Date' or 'Time' column in RTA LOG: {file_path}")
                 return pd.DataFrame()

            log_df['Datetime'] = pd.to_datetime(log_df['Date'] + ' ' + log_df['Time'], errors='coerce')
            log_df.dropna(subset=['Datetime'], inplace=True)
            log_df = safe_convert_to_float(log_df)

            # Return all relevant columns (excluding original Date/Time and placeholders)
            final_cols = [col for col in log_df.columns if col not in ['Date', 'Time'] and not str(col).startswith('_col_')]
            return log_df[final_cols]

        except Exception as e:
            logger.error(f"Error parsing RTA LOG content from {file_path}: {e}", exc_info=True)
            return pd.DataFrame()


# --- Convenience/Backward Compatibility Functions ---
# These might need adjustment or removal depending on how you use the new structure

def read_in_noise_sentry_file(file_path):
    """Parses a single Noise Sentry file."""
    parser = NoiseSentryParser()
    return parser.parse(file_path)

def read_in_Svan_file(file_path):
    """Parses a single Svan file."""
    parser = SvanParser()
    return parser.parse(file_path)

def read_NTi(file_path):
    """Parses a single NTi file (RPT, RTA, or LOG)."""
    parser = NTiParser()
    # Returns dict {'type': ..., 'data': ..., 'metadata': ...} or None
    return parser.parse(file_path)

def get_parser(parser_type):
    """Get a parser instance by type."""
    return NoiseDataParser.get_parser(parser_type)

class AudioParser(NoiseDataParser):

    """Parser for audio files and directories containing audio files."""
    
    def parse(self, path):
        """
        Parse a directory path containing audio files. Unlike other parsers, 
        this one doesn't read data but scans a directory for audio files
        and returns the directory path with metadata about available files.
        
        Parameters:
        path (str): Path to the directory containing audio files
        
        Returns:
        dict: Dictionary with the audio directory information and file metadata
        """
        if not isinstance(path, str):
            raise ValueError(f"Invalid path: {path}")

        logger.info(f'Processing audio path: {path}')
        
        # Check if path exists
        if not os.path.exists(path):
            logger.error(f"Audio path not found: {path}")
            return None
        
        try:
            # Handle both directory and file paths
            if os.path.isdir(path):
                # It's a directory - scan for audio files
                audio_files = []
                for filename in os.listdir(path):
                    # Focus on *_Audio_*.wav files as specified
                    if "_Audio_" in filename and filename.lower().endswith('.wav'):
                        file_path = os.path.join(path, filename)
                        file_stats = os.stat(file_path)
                        audio_files.append({
                            'filename': filename,
                            'path': file_path,
                            'size': file_stats.st_size,
                            'size_mb': file_stats.st_size / (1024 * 1024),
                            'modified': pd.to_datetime(file_stats.st_mtime, unit='s'),
                            'created': pd.to_datetime(file_stats.st_ctime, unit='s')
                        })
                
                # Sort files by modified time
                audio_files.sort(key=lambda x: x['modified'])
                
                return {
                    'type': 'audio',
                    'path': path,
                    'metadata': {
                        'directory': path,
                        'file_count': len(audio_files),
                        'audio_files': audio_files
                    }
                }
            else:
                # It's a single file (backward compatibility)
                if not path.lower().endswith(('.wav', '.mp3', '.ogg')):
                    logger.warning(f"Path is not a directory or audio file: {path}")
                    return None
                
                file_stats = os.stat(path)
                return {
                    'type': 'audio',
                    'path': os.path.dirname(path),  # Use the directory containing the file
                    'metadata': {
                        'directory': os.path.dirname(path),
                        'file_count': 1,
                        'audio_files': [{
                            'filename': os.path.basename(path),
                            'path': path,
                            'size': file_stats.st_size,
                            'size_mb': file_stats.st_size / (1024 * 1024),
                            'modified': pd.to_datetime(file_stats.st_mtime, unit='s'),
                            'created': pd.to_datetime(file_stats.st_ctime, unit='s')
                        }]
                    }
                }
        except Exception as e:
            logger.error(f"Error processing audio path {path}: {e}", exc_info=True)
            return None 