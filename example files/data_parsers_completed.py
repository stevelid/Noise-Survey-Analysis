"""
Improved data parsing module for noise survey analysis.
Focuses on robust parsing with standardised outputs and modular design.
"""

import pandas as pd
import numpy as np
import re
import os
import logging
from io import StringIO
from collections import Counter
from typing import Dict, List, Optional, Union, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def safe_convert_to_float(df: pd.DataFrame, columns: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Convert specified columns in a DataFrame to float type, handling errors gracefully.
    
    Parameters:
    df: DataFrame containing columns to convert
    columns: List of column names to convert. If None, all non-datetime columns are converted.
    
    Returns:
    DataFrame with converted columns
    """
    if columns is None:
        columns = [col for col in df.columns if not pd.api.types.is_datetime64_any_dtype(df[col])]

    for col in columns:
        if col in df.columns and isinstance(col, str) and col not in [
            "", "Datetime", "_", "Start Date", "Start Time", "End Date", "End Time", 
            "Date", "Time", "Band [Hz]"
        ]:
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            except Exception as e:
                logger.warning(f"Could not convert column '{col}' to numeric values: {e}")

    return df


def standardize_datetime_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize datetime column to 'Datetime' and ensure proper datetime format.
    
    Parameters:
    df: DataFrame with potential datetime columns
    
    Returns:
    DataFrame with standardized 'Datetime' column
    """
    # Common datetime column patterns
    datetime_patterns = [
        'datetime', 'date_time', 'date & time', 'start date & time', 'start_date_time', 'start_date__time',
        'timestamp', 'time_stamp'
    ]
    
    # Find datetime column
    datetime_col = None
    for col in df.columns:
        if col.lower().strip() in datetime_patterns:
            datetime_col = col
            break
    
    # If no datetime column found, try to create from Date/Time columns
    if datetime_col is None:
        date_cols = [col for col in df.columns if 'date' in col.lower()]
        time_cols = [col for col in df.columns if 'time' in col.lower()]
        
        if date_cols and time_cols:
            # Use first available date and time columns
            df['Datetime'] = pd.to_datetime(
                df[date_cols[0]].astype(str) + ' ' + df[time_cols[0]].astype(str), 
                errors='coerce'
            )
        else:
            logger.warning("No datetime columns found in DataFrame")
            return df
    else:
        # Rename existing datetime column
        df.rename(columns={datetime_col: 'Datetime'}, inplace=True)
        df['Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')
    
    # Remove rows with invalid datetime
    df.dropna(subset=['Datetime'], inplace=True)
    
    return df


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """
    Standardize column names to match expected format.
    
    Expected format: LAeq, LAFmax, LAF10, LAF90, plus spectral like LAeq_63, LAFmax_125
    
    Parameters:
    df: DataFrame with raw column names
    
    Returns:
    DataFrame with standardized column names
    """
    # Mapping of common variations to standard names
    standard_mapping = {
        # Broadband mappings
        'leq': 'LAeq',
        'laeq': 'LAeq',
        'la eq': 'LAeq',
        'lmax': 'LAFmax',
        'lamax': 'LAFmax',
        'lafmax': 'LAFmax',
        'la max': 'LAFmax',
        'l10': 'LAF10',
        'laf10': 'LAF10',
        'la10': 'LAF10',
        'la f10': 'LAF10',
        'l90': 'LAF90',
        'laf90': 'LAF90',
        'la90': 'LAF90',
        'la f90': 'LAF90',
        # Common variations
        'leq db-a': 'LAeq',
        'lmax db-a': 'LAFmax',
        'l10 db-a': 'LAF10',
        'l90 db-a': 'LAF90'
    }
    
    new_columns = {}
    for col in df.columns:
        if col == 'Datetime':
            continue
            
        # Clean column name
        clean_col = re.sub(r'\s*\([^)]*\)|\s*\[[^\]]*\]', '', str(col))
        clean_col = clean_col.strip().lower()
        
        # Check for spectral data (contains frequency)
        freq_match = re.search(r'(\d+\.?\d*)\s*(?:hz|k)?', clean_col) #TODO: too simple, matchs any digit. need to match to known patterns
        if freq_match:
            freq = freq_match.group(1)
            # Convert frequency format (e.g., 1k -> 1000)
            if 'k' in clean_col.lower():
                freq = str(int(float(freq) * 1000))
            
            # Determine parameter type
            if any(param in clean_col for param in ['leq', 'eq']):
                new_columns[col] = f'LAeq_{freq}'
            elif any(param in clean_col for param in ['lmax', 'max']):
                new_columns[col] = f'LAFmax_{freq}'
            elif 'l10' in clean_col or 'f10' in clean_col:
                new_columns[col] = f'LAF10_{freq}'
            elif 'l90' in clean_col or 'f90' in clean_col:
                new_columns[col] = f'LAF90_{freq}'
            else:
                # Default to LAeq for spectral data
                new_columns[col] = f'LAeq_{freq}'
        else:
            # Check for broadband mapping
            if clean_col in standard_mapping:
                new_columns[col] = standard_mapping[clean_col]
            else:
                # Keep original if no mapping found
                new_columns[col] = col
    
    df.rename(columns=new_columns, inplace=True)
    return df


def separate_broadband_spectral(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Separate DataFrame into broadband and spectral components.
    
    Parameters:
    df: DataFrame with mixed broadband and spectral data
    
    Returns:
    Tuple of (broadband_df, spectral_df)
    """
    broadband_cols = ['Datetime', 'LAeq', 'LAFmax', 'LAF10', 'LAF90']
    spectral_cols = ['Datetime'] + [col for col in df.columns if '_' in col and col != 'Datetime']
    
    # Filter to only existing columns
    broadband_cols = [col for col in broadband_cols if col in df.columns]
    spectral_cols = [col for col in spectral_cols if col in df.columns]
    
    broadband_df = df[broadband_cols].copy() if len(broadband_cols) > 1 else pd.DataFrame()
    spectral_df = df[spectral_cols].copy() if len(spectral_cols) > 1 else pd.DataFrame()
    
    return broadband_df, spectral_df


class NoiseDataParser:
    """Base class for noise data parsers with standardized output."""
    
    @staticmethod
    def get_parser(parser_type: str) -> 'NoiseDataParser':
        """Factory method to get the appropriate parser instance."""
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

    def standardize_output(self, df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
        """
        Standardize parser output to consistent format.
        
        Parameters:
        df: Raw parsed DataFrame
    
        Returns:
        Dictionary with 'broadband' and 'spectral' DataFrames
        """
        if df.empty:
            return {'broadband': pd.DataFrame(), 'spectral': pd.DataFrame()}
        
        # Step 1: Standardize datetime
        df = standardize_datetime_column(df)
        
        # Step 2: Standardize column names
        df = standardize_column_names(df)
        
        # Step 3: Convert to numeric
        df = safe_convert_to_float(df)
        
        # Step 4: Separate broadband and spectral
        broadband_df, spectral_df = separate_broadband_spectral(df)
        
        return {
            'broadband': broadband_df,
            'spectral': spectral_df
        }


class SvanParser(NoiseDataParser):
    """
    Enhanced Svan parser with robust multi-level header handling.
    """
    
    def __init__(self):
        # Patterns for cleaning column names
        self.clean_patterns = [
            r'\s*\((?:SR|TH|Lin|Fast|Slow)\)',
            r'\s*\[dB\]',
            r'\s*Histogram',
            r'\s*\([^)]*\)',
            r'\s*\[[^\]]*\]'
        ]
        self.clean_regex = re.compile('|'.join(self.clean_patterns), flags=re.IGNORECASE)
        
        # Frequency extraction pattern
        self.freq_pattern = re.compile(r'(\d+\.?\d*)\s*(?:hz|k)?', flags=re.IGNORECASE)

    def _extract_svan_metadata(self, lines: List[str], file_path: str) -> Dict:
        """Extract metadata from Svan file headers/content."""
        metadata = {
            'original_path': file_path,
            'parser': 'svan',
            'device_info': None,
            'logger_step': None,
            'file_type_guess': 'svan_unknown' # Default
        }
        filename_lower = os.path.basename(file_path).lower()
        if "_log" in filename_lower:
            metadata['file_type_guess'] = 'svan_log'
        elif "_summary" in filename_lower:
            metadata['file_type_guess'] = 'svan_summary'

        # Attempt to extract device info and logger step from the first few lines
        for line_idx, line_content in enumerate(lines[:5]): # Check first 5 lines
            stripped_line_content = line_content.strip()
            if line_idx == 0 and not (stripped_line_content.startswith(',') or ';' in stripped_line_content or '\t' in stripped_line_content or stripped_line_content.lower().startswith("date")):
                 # If the first line doesn't look like a CSV header row or data, assume it's device info
                metadata['device_info'] = stripped_line_content
            
            match_step = re.search(r"logger step\s*=\s*(\S+)", stripped_line_content, re.IGNORECASE)
            if match_step:
                metadata['logger_step'] = match_step.group(1)
            
            # More specific Svan device name patterns could be added here
            if "SVAN" in stripped_line_content.upper() and not metadata['device_info']:
                 if not (stripped_line_content.startswith(',') or ';' in stripped_line_content or '\t' in stripped_line_content or stripped_line_content.lower().startswith("date")):
                    metadata['device_info'] = stripped_line_content
        self._temp_extracted_metadata = metadata # Store metadata for potential error handling
        return metadata

    def parse(self, file_path: str) -> Optional[Dict]:
        """
        Parse Svan CSV file with robust header detection.
        
        Parameters:
        file_path: Path to Svan CSV file
        
        Returns:
        A dictionary with parsed data, or None on failure.
        """
        logger.info(f"Parsing Svan file: {os.path.basename(file_path)}")
        
        try:
            # Read file with multiple encoding attempts
            content = self._read_file_robust(file_path)

            # DEBUG: Log status of file reading
            with open("debug_svan_parser_output.txt", "a", encoding="utf-8") as f_debug:
                log_msg = f"--- DEBUG: _read_file_robust {'succeeded' if content else 'FAILED'} for {os.path.basename(file_path)} ---\n"
                f_debug.write(log_msg)

            if not content:
                return None
                
            lines = content.splitlines() # Use splitlines for robust line splitting
            
            # Extract metadata early
            extracted_metadata = self._extract_svan_metadata(lines, file_path)
            
            # Find header structure
            header_info = self._find_header_structure(lines)

            # DEBUG: Log header_info
            # This logging is now also part of the try block
            with open("debug_svan_parser_output.txt", "a", encoding="utf-8") as f_debug:
                f_debug.write(f"--- DEBUG: header_info for {os.path.basename(file_path)} ---\n")
                f_debug.write(str(header_info) + "\n")
            if not header_info:
                logger.error(f"Could not identify header structure in {file_path}")
                # Return metadata even if header parsing fails
                return {
                    'type': extracted_metadata.get('file_type_guess', 'svan_unknown_header_fail'),
                    'broadband': pd.DataFrame(),
                    'spectral': pd.DataFrame(),
                    'metadata': extracted_metadata
                }
            
            # Parse based on header structure
            df = self._parse_with_header_info(lines, header_info, file_path)
            if df.empty:
                return {
                    'type': extracted_metadata.get('file_type_guess', 'svan_empty_data'),
                    'broadband': pd.DataFrame(),
                    'spectral': pd.DataFrame(),
                    'metadata': extracted_metadata
                }
            
            # Standardize output
            standardized = self.standardize_output(df)
            
            # Construct the single result dictionary
            final_result = {
                'type': extracted_metadata.get('file_type_guess', 'svan_unknown'),
                'broadband': standardized['broadband'],
                'spectral': standardized['spectral'],
                'metadata': extracted_metadata
            }
            
            logger.info(f"Successfully parsed Svan file into a single dataset structure.")
            return final_result
            
        except Exception as e:
            logger.error(f"Error parsing Svan file {file_path}: {e}", exc_info=True)
            # Attempt to return a minimal structure on error, including any metadata we might have
            # If extracted_metadata was populated before error, use it, else create a basic one.
            base_metadata = getattr(self, '_temp_extracted_metadata', None) # Check if metadata was extracted
            if base_metadata is None: # if _extract_svan_metadata failed or wasn't called
                base_metadata = {'original_path': file_path, 'parser': 'svan'}
            base_metadata['error'] = str(e)

            file_type_guess = 'svan_error'
            filename_lower = os.path.basename(file_path).lower()
            if "_log" in filename_lower:
                file_type_guess = 'svan_log_error'
            elif "_summary" in filename_lower:
                file_type_guess = 'svan_summary_error'

            return {
                'type': file_type_guess,
                'broadband': pd.DataFrame(),
                'spectral': pd.DataFrame(),
                'metadata': base_metadata
            }
    
    # Add a temporary attribute to self in case _extract_svan_metadata is called before an error
    # This is a bit of a workaround for accessing extracted_metadata in the except block
    # A cleaner way might involve passing metadata through the call stack or structuring try-except differently.
    _temp_extracted_metadata = None # Class attribute for fallback

    def _read_file_robust(self, file_path: str) -> Optional[str]:
        """Attempt to read file with multiple encodings."""
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
                    return f.read()
            except Exception as e:
                logger.debug(f"Failed to read with {encoding}: {e}")
                continue
        
        logger.error(f"Could not read file with any encoding: {file_path}")
        return None

    def _find_header_structure(self, lines: List[str]) -> Optional[Dict]:
        """
        Identify header structure in Svan files. Can detect 1, 2, or 3-level headers.
        """
        datetime_patterns = ['date & time', 'start date & time']
        datetime_row_idx = -1

        for i, line in enumerate(lines[:50]):
            if any(p in line.lower() for p in datetime_patterns):
                datetime_row_idx = i
                break
        
        if datetime_row_idx == -1:
            logger.warning("No datetime header row found.")
            return None

        header_info = {'datetime_row': datetime_row_idx}
        header_rows = []

        # Check for up to two rows above the datetime row
        for i in range(1, 3):
            if datetime_row_idx - i >= 0:
                potential_header_line = lines[datetime_row_idx - i].strip()
                # A line is considered a header if it contains commas
                if potential_header_line and ',' in potential_header_line:
                    header_rows.insert(0, datetime_row_idx - i) # Prepend to keep order
                else:
                    break # Stop if a non-header line (e.g., blank) is found
        
        header_info['header_rows'] = header_rows
        header_info['data_start'] = datetime_row_idx + 1
        return header_info

    def _parse_with_header_info(self, lines: List[str], header_info: Dict, file_path: str) -> pd.DataFrame:
        """Parse Svan data using the dynamically identified header structure."""
        try:
            header_row_indices = header_info['header_rows']
            
            # Always include the datetime row as the final level of the header
            all_header_indices = header_row_indices + [header_info['datetime_row']]
            
            parsed_headers = [self._parse_csv_line(lines[i]) for i in all_header_indices]
            
            # Forward-fill and combine headers
            max_cols = max(len(h) for h in parsed_headers)
            combined_headers = [''] * max_cols
            
            for i in range(max_cols):
                parts = []
                last_part = ''
                for level_parts in parsed_headers:
                    part = level_parts[i] if i < len(level_parts) else ''
                    part = part.strip()
                    if part:
                        last_part = part
                    parts.append(last_part)
                
                # Combine unique parts to form the header
                unique_parts = []
                [unique_parts.append(p) for p in parts if p not in unique_parts and p]
                combined_headers[i] = "_".join(unique_parts)

            # Clean the final combined headers
            cleaned_headers = [self._clean_header(h) for h in combined_headers]
            
            # Ensure headers are unique
            final_headers = []
            counts = Counter()
            for header in cleaned_headers:
                counts[header] += 1
                if counts[header] > 1:
                    final_headers.append(f"{header}_{counts[header]-1}")
                else:
                    final_headers.append(header)

            # DEBUG: Log final_headers
            with open("debug_svan_parser_output.txt", "a", encoding="utf-8") as f_debug:
                f_debug.write(f"--- DEBUG: final_headers for {os.path.basename(file_path)} ---\n")
                f_debug.write(str(final_headers) + "\n")

            data_start_index = header_info['data_start']
            data_lines_str = "\n".join(lines[data_start_index:])
            data_io = StringIO(data_lines_str)
            
            # Read data using the generated unique headers
            df = pd.read_csv(data_io, header=None, names=final_headers, on_bad_lines='warn', engine='python')
            
            df = df.dropna(how='all')
            return df

        except Exception as e:
            logger.error(f"Error parsing Svan data structure in {file_path}: {e}", exc_info=True)
            return pd.DataFrame()

    def _parse_csv_line(self, line: str) -> List[str]:
        """Parse a CSV line handling quoted fields."""
        try:
            return next(pd.read_csv(StringIO(line), header=None, chunksize=1)).iloc[0].fillna('').astype(str).tolist()
        except (StopIteration, Exception):
            return [part.strip() for part in line.split(',')]

    def _clean_header(self, header: str) -> str:
        """Clean header names by removing unwanted patterns."""
        
        cleaned = self.clean_regex.sub('', str(header))
        # Do not apply to Date & Time header
        if 'date & time' in header.lower():
            return header
        cleaned = cleaned.strip().replace(' ', '_').replace('__', '_')
        return cleaned


class NoiseSentryParser(NoiseDataParser):
    """Parser for Noise Sentry CSV files with standardized output."""
    
    def parse(self, file_path: str) -> Dict[str, pd.DataFrame]:
        """Parse Noise Sentry CSV file."""
        if not isinstance(file_path, str) or not file_path.lower().endswith('.csv'):
            raise ValueError(f"Invalid file path or type for Sentry parser: {file_path}")

        logger.info(f'Reading Sentry file: {file_path}')
        
        try:
            # Use pandas for more efficient reading
            df = pd.read_csv(file_path, encoding='utf-8', errors='ignore', on_bad_lines='warn')
            if df.empty:
                 logger.warning(f"Sentry file is empty or could not be read: {file_path}")
                 return {'broadband': pd.DataFrame(), 'spectral': pd.DataFrame()}

            # Standardize columns
            df.rename(columns={
                df.columns[0]: 'Datetime',
                'LEQ dB-A ': 'LAeq',
                'Lmax dB-A ': 'LAFmax',
                'L10 dB-A ': 'LAF10',
                'L90 dB-A ': 'LAF90'
            }, inplace=True)
            
            return self.standardize_output(df)
            
        except Exception as e:
            logger.error(f"Error parsing Sentry file {file_path}: {e}", exc_info=True)
            return {'broadband': pd.DataFrame(), 'spectral': pd.DataFrame()}


class NTiParser(NoiseDataParser):
    """Enhanced NTi parser with standardized output."""
    
    def parse(self, file_path: str) -> Optional[Dict]:
        """Parse NTi file and return standardized format."""
        if not isinstance(file_path, str) or not os.path.exists(file_path):
            logger.error(f"NTi file not found or invalid path: {file_path}")
            return None

        logger.info(f"Parsing NTi file: {file_path}")
        filename = os.path.basename(file_path).lower()

        try:
            # Determine file type and parse
            if filename.endswith('_123_rpt_report.txt'):
                return self._parse_specific_file(file_path, self._parse_rpt_content, 'nti_rpt')
            elif filename.endswith('_rta_3rd_rpt_report.txt'):
                return self._parse_specific_file(file_path, self._parse_rta_content, 'nti_rta')
            elif filename.endswith('_123_log.txt'):
                return self._parse_specific_file(file_path, self._parse_rpt_log_content, 'nti_rpt_log')
            elif filename.endswith('_rta_3rd_log.txt'):
                return self._parse_specific_file(file_path, self._parse_rta_log_content, 'nti_rta_log')
            else:
                logger.warning(f"Unknown NTi file type: {file_path}")
                return None
                
        except Exception as e:
            logger.error(f"Error parsing NTi file {file_path}: {e}", exc_info=True)
            return None

    def _parse_specific_file(self, file_path: str, parse_func, file_type: str) -> Dict:
        """Helper to parse specific NTi file types."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Remove checksum lines
            checksum_index = next((i for i, line in enumerate(lines) if "#CheckSum" in line), len(lines))
            lines_to_parse = lines[:checksum_index]

            if not lines_to_parse:
                return {'type': file_type, 'broadband': pd.DataFrame(), 'spectral': pd.DataFrame()}

            # Extract metadata
            metadata = self._extract_metadata(lines_to_parse)
            
            # Parse content
            df = parse_func(lines_to_parse, file_path)
            
            # Standardize output
            standardized = self.standardize_output(df)
            
            return {
                'type': file_type,
                'broadband': standardized['broadband'],
                'spectral': standardized['spectral'],
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Error processing {file_type} file {file_path}: {e}", exc_info=True)
            return {'type': file_type, 'broadband': pd.DataFrame(), 'spectral': pd.DataFrame()}

    def _extract_metadata(self, lines: List[str]) -> Dict:
        """Extract metadata from NTi file headers."""
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
            elif stripped_line.startswith("#"):
                current_section = None
                continue

            if current_section is not None:
                parts = stripped_line.split(':', 1)
                if len(parts) == 2:
                    key, value = map(str.strip, parts)
                    if key:
                        current_section[key] = value

        return {'hardware_config': hardware_config, 'measurement_setup': measurement_setup}

    def _parse_rpt_content(self, lines: List[str], file_path: str) -> pd.DataFrame:
        """Parse RPT file content with enhanced error handling."""
        data_start_marker = "# Broadband Results"
        try:
            table_start_idx = next((i for i, line in enumerate(lines) 
                                    if line.strip().startswith(data_start_marker)), -1)
            if table_start_idx == -1:
                logger.warning(f"'{data_start_marker}' not found in RPT file: {file_path}")
                return pd.DataFrame()
            
            data_string = "\n".join(lines[table_start_idx+1:])
            df = pd.read_csv(StringIO(data_string), sep='\t', header=1, on_bad_lines='warn')
            df.columns = [col.strip().replace('.0%', '') for col in df.columns]
            df = df.drop(0).reset_index(drop=True) # Drop the units row
            
            return df
            
        except Exception as e:
            logger.error(f"Error parsing RPT content: {e}", exc_info=True)
            return pd.DataFrame()

    def _parse_rta_content(self, lines: List[str], file_path: str) -> pd.DataFrame:
        """Parse RTA file content with spectral data."""
        data_start_marker = "# RTA Results"
        try:
            table_start_idx = next((i for i, line in enumerate(lines) 
                                    if line.strip().startswith(data_start_marker)), -1)
            if table_start_idx == -1: return pd.DataFrame()

            data_string = "\n".join(lines[table_start_idx+1:])
            
            # Read headers separately
            header_df = pd.read_csv(StringIO(data_string), sep='\t', header=None, nrows=2).fillna('')
            h1 = header_df.iloc[0].ffill()
            h2 = header_df.iloc[1]
            headers = [f"{p1}_{p2}" if p1 and p2 != 'Band [Hz]' else p2 for p1,p2 in zip(h1, h2)]
            
            # Read data
            df = pd.read_csv(StringIO(data_string), sep='\t', header=2)
            df.columns = headers[:len(df.columns)]
            
            return df
            
        except Exception as e:
            logger.error(f"Error parsing RTA content: {e}", exc_info=True)
            return pd.DataFrame()

    def _parse_rpt_log_content(self, lines: List[str], file_path: str) -> pd.DataFrame:
        """Parse RPT LOG file content."""
        data_start_marker = "# Broadband LOG Results"
        try:
            table_start_idx = next((i for i, line in enumerate(lines) if line.strip().startswith(data_start_marker)), -1)
            if table_start_idx == -1: return pd.DataFrame()

            data_string = '\n'.join(lines[table_start_idx + 1:])
            df = pd.read_csv(StringIO(data_string), sep='\t', header=0, on_bad_lines='warn')
            df.columns = [col.strip() for col in df.columns]

            if df.iloc[-1, 0].startswith('not available'):
                df = df.iloc[:-1]

            return df

        except Exception as e:
            logger.error(f"Error parsing RPT LOG content from {file_path}: {e}", exc_info=True)
            return pd.DataFrame()

    def _parse_rta_log_content(self, lines: List[str], file_path: str) -> pd.DataFrame:
        """Parse RTA LOG file content."""
        data_start_marker = "# RTA LOG Results"
        try:
            table_start_idx = next((i for i, line in enumerate(lines) if line.strip().startswith(data_start_marker)), -1)
            if table_start_idx == -1: return pd.DataFrame()

            data_string = "\n".join(lines[table_start_idx+1:])
            header_df = pd.read_csv(StringIO(data_string), sep='\t', header=None, nrows=2).fillna('')
            h1 = header_df.iloc[0].ffill()
            h2 = header_df.iloc[1]
            headers = [f"{p1}_{p2}" if p1 else p2 for p1,p2 in zip(h1, h2)]
            
            df = pd.read_csv(StringIO(data_string), sep='\t', header=2)
            df.columns = headers[:len(df.columns)]

            if str(df.iloc[-1, 0]).startswith('not available'):
                df = df.iloc[:-1]

            return df
            
        except Exception as e:
            logger.error(f"Error parsing RTA LOG content from {file_path}: {e}", exc_info=True)
            return pd.DataFrame()


class AudioParser(NoiseDataParser):
    """Parser for audio files with standardized metadata output."""
    
    def parse(self, path: str) -> Optional[Dict]:
        """Parse audio directory and return file metadata."""
        if not isinstance(path, str) or not os.path.exists(path):
            logger.error(f"Audio path not found: {path}")
            return None

        logger.info(f'Processing audio path: {path}')
        
        try:
            audio_files = []
            
            if os.path.isdir(path):
                for filename in os.listdir(path):
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
            else:
                # Single file
                if path.lower().endswith(('.wav', '.mp3', '.ogg')):
                    file_stats = os.stat(path)
                    audio_files.append({
                        'filename': os.path.basename(path),
                        'path': path,
                        'size': file_stats.st_size,
                        'size_mb': file_stats.st_size / (1024 * 1024),
                        'modified': pd.to_datetime(file_stats.st_mtime, unit='s'),
                        'created': pd.to_datetime(file_stats.st_ctime, unit='s')
                    })

            audio_files.sort(key=lambda x: x['modified'])
            
            return {
                'type': 'audio',
                'path': path,
                'metadata': {
                    'directory': os.path.dirname(path) if os.path.isfile(path) else path,
                    'file_count': len(audio_files),
                    'audio_files': audio_files
                }
            }
            
        except Exception as e:
            logger.error(f"Error processing audio path {path}: {e}", exc_info=True)
            return None
