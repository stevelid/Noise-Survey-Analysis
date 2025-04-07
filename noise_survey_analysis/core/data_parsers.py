"""
Data parsing module for noise survey analysis.
Parses individual files based on specified parser type.
"""

import pandas as pd
import numpy as np
import re
import os
import logging # Use logging

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
    """Parser for Svan Excel files."""
    
    def parse(self, file_path):
        """
        Parse a Svan Excel file into a DataFrame.
        
        Parameters:
        file_path (str): Path to the Excel file
        
        Returns:
        pd.DataFrame: DataFrame containing parsed data
        """
        if not isinstance(file_path, str) or not file_path.lower().endswith(('.xls', '.xlsx')):
            raise ValueError(f"Invalid file path or type for Svan parser: {file_path}")

        logger.info(f'Reading Svan file: {file_path}')
        try:
            df = pd.read_excel(file_path)

            # Find header rows robustly
            header_start_row = -1
            unit_row = -1
            for i, row in enumerate(df.itertuples()):
                 # Look for common header indicators like 'Date & time' or 'LAeq'
                 if any(str(cell).strip() == 'Date & time' for cell in row[1:]):
                      header_start_row = i
                      # Assume unit row is right below
                      if i + 1 < len(df):
                          unit_row = i + 1
                      break
                 elif i > 20: # Stop searching after a reasonable number of rows
                     break

            if header_start_row == -1 or unit_row == -1:
                 logger.error(f"Could not reliably determine header rows in Svan file: {file_path}")
                 return pd.DataFrame()

            header_vals = df.iloc[header_start_row].fillna('').astype(str)
            unit_vals = df.iloc[unit_row].fillna('').astype(str)

            headers = []
            for h, u in zip(header_vals, unit_vals):
                h = h.strip()
                u = u.strip()
                if h == 'Date & time':
                    headers.append('Datetime')
                    continue
                if 'Histogram' in h or not h: # Skip histogram summaries or empty headers
                    headers.append(f"_col_{len(headers)}") # Placeholder for empty
                    continue

                # Clean up units and combine
                u = u.replace('(TH)', '').replace('[dB]', '').strip()
                h = h.replace('.0%', '') # Clean percentages if any
                h = re.sub(r'\s*\(SR\)', '', h) # Remove (SR)
                h = re.sub(r'1/3 Oct\s*', '', h) # Remove 1/3 Oct prefix

                # Standardize common metrics
                if h == 'Leq': h = 'LAeq' # Assuming A-weighted if not specified
                elif h == 'L10': h = 'LAF10'
                elif h == 'L90': h = 'LAF90'
                elif h == 'Lmax': h = 'LAFmax'

                # Handle frequency columns (e.g., 'LZeq', '31.5 Hz')
                if h.endswith(' Hz'):
                    freq = h[:-3].strip()
                    param = u if u else 'L?' # Use unit row or placeholder 'L?'
                    headers.append(f"{param}_{freq}")
                elif u.endswith(' Hz'): # Sometimes freq is in unit row
                    freq = u[:-3].strip()
                    param = h if h else 'L?'
                    headers.append(f"{param}_{freq}")
                else:
                     # Combine header and unit if unit is not frequency
                     full_header = f"{h}_{u}" if u and h != u else h
                     headers.append(full_header if full_header else f"_col_{len(headers)}")

            data_start_row = unit_row + 1
            df_data = df.iloc[data_start_row:].copy()
            if df_data.empty:
                 logger.warning(f"No data rows found after headers in Svan file: {file_path}")
                 return pd.DataFrame()

            # Assign cleaned headers, ensuring length matches
            if len(headers) == df_data.shape[1]:
                 df_data.columns = headers
            else:
                 logger.warning(f"Header length mismatch ({len(headers)}) vs data columns ({df_data.shape[1]}) in {file_path}. Using numbered columns.")
                 df_data.columns = [f"_col_{j}" for j in range(df_data.shape[1])]
                 # Attempt to find Datetime column again if headers failed
                 for j, col in enumerate(df_data.columns):
                      if 'Date & time' in str(df.iloc[header_start_row, j]):
                           df_data.rename(columns={col: 'Datetime'}, inplace=True)
                           break


            if 'Datetime' not in df_data.columns:
                 logger.error(f"Could not find 'Datetime' column in Svan file: {file_path}")
                 return pd.DataFrame()

            df_data['Datetime'] = pd.to_datetime(df_data['Datetime'], dayfirst=True, errors='coerce')
            df_data.dropna(subset=['Datetime'], inplace=True)

            df_data = safe_convert_to_float(df_data)

            # Drop placeholder columns if they exist
            df_data = df_data[[col for col in df_data.columns if not str(col).startswith('_col_')]]

            return df_data
        except FileNotFoundError:
            logger.error(f"Svan file not found: {file_path}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"Error parsing Svan file {file_path}: {e}", exc_info=True)
            return pd.DataFrame()

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