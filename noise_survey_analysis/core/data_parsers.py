"""
data_parsers.py
Data parsing module for noise survey analysis.
Parses individual files based on specified parser type.
"""
import pandas as pd
import numpy as np
import re
import os
import logging
from io import StringIO
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# --- Standard Column Definitions ---
# These are the columns we aim to provide by default if available in the source.
STANDARD_OUTPUT_COLUMNS = ['Datetime', 'LAF90', 'LAF10', 'LAFmax', 'LAeq']
STANDARD_SPECTRAL_PREFIXES = ['LZeq', 'LZmax', 'LZFmax']

# Standard 1/3 octave band center frequencies (as strings for matching cleaned column suffixes)
# Used by parsers to identify and normalize frequency parts of column names.
# And by _filter_and_standardize_columns to identify spectral columns.
EXPECTED_THIRD_OCTAVE_SUFFIXES = [
    "6.3", "8", "10", "12.5", "16", "20", "25", "31.5", "31", "40", "50", "63", "80", "100",
    "125", "160", "200", "250", "315", "400", "500", "630", "800", "1000",
    "1250", "1600", "2000", "2500", "3150", "4000", "5000", "6300", "8000",
    "10000", "12500", "16000", "20000"
]

@dataclass
class ParsedData:
    """
    Holds the results of parsing a single noise data file.
    """
    totals_df: Optional[pd.DataFrame] = None
    spectral_df: Optional[pd.DataFrame] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Standardized metadata fields
    original_file_path: Optional[str] = None
    parser_type: Optional[str] = None
    data_profile: Optional[str] = None  # 'log', 'overview', 'file_list'
    spectral_data_type: Optional[str] = None # 'third_octave', 'octave', 'none'
    sample_period_seconds: Optional[float] = None


class AbstractNoiseParser(ABC):
    """
    Abstract Base Class for all noise file parsers.
    """
    def __init__(self):
        self.standard_output_columns = STANDARD_OUTPUT_COLUMNS
        self.standard_spectral_prefixes = STANDARD_SPECTRAL_PREFIXES
        self.expected_third_octave_suffixes = EXPECTED_THIRD_OCTAVE_SUFFIXES

    @abstractmethod
    def parse(self, file_path: str, return_all_columns: bool = False) -> ParsedData:
        """
        Parses a given file and returns its contents as a ParsedData object.
        """
        pass

    def _safe_convert_to_float(self, df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return df
        
        columns_to_convert = [col for col in df.columns if col not in ['Datetime']]
        for col in columns_to_convert:
            if col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    continue
                try:
                    # Use pd.to_numeric for efficient conversion and error handling
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                except Exception as e:
                    logger.warning(f"Could not convert column '{col}' to numeric: {e}. Values set to NaN.")
        return df

    def _normalize_datetime_column(self, df: pd.DataFrame, 
                                   dt_col_names: List[str], # e.g., ['Datetime'] or ['Date', 'Time']
                                   new_name: str = 'Datetime',
                                   sort: bool = True) -> pd.DataFrame:
        if df.empty:
            return df

        datetime_series = None
        if len(dt_col_names) == 1 and dt_col_names[0] in df.columns:
            datetime_series = pd.to_datetime(df[dt_col_names[0]], errors='coerce')
        elif len(dt_col_names) == 2 and dt_col_names[0] in df.columns and dt_col_names[1] in df.columns:
            datetime_series = pd.to_datetime(df[dt_col_names[0]] + ' ' + df[dt_col_names[1]], errors='coerce')
        
        if datetime_series is None:
            logger.warning(f"Could not form datetime from columns: {dt_col_names}")
            return df # Or raise error

        df[new_name] = datetime_series
        
        # Drop original date/time columns if they are different from the new_name and exist
        for old_dt_col in dt_col_names:
            if old_dt_col != new_name and old_dt_col in df.columns:
                df = df.drop(columns=[old_dt_col])
        
        df = df.dropna(subset=[new_name])
        if sort and not df.empty:
             df = df.sort_values(by=new_name).reset_index(drop=True)
        return df

    def _calculate_sample_period(self, df: Optional[pd.DataFrame]) -> Optional[float]:
        if df is None or df.empty or 'Datetime' not in df.columns or len(df) < 3: # Need at least 2 intervals
            return None
        try:
            # Datetime should already be sorted by _normalize_datetime_column
            time_deltas = df['Datetime'].diff().dt.total_seconds()
            
            # Use deltas from the 2nd to the 2nd-to-last original data point.
            if len(time_deltas) >= 3: # Requires at least df length 3, so 2 actual deltas
                valid_deltas = time_deltas.iloc[1:-1] # All deltas except the first NaN
                if len(valid_deltas) > 20: # If many samples, trim ends to avoid startup/shutdown effects
                    valid_deltas = valid_deltas.iloc[5:-5] 
                
                valid_deltas = valid_deltas.dropna()
                if not valid_deltas.empty:
                    # Mode is good for finding the most common interval in logged data
                    # If mode has multiple values (equally common), median of modes or first mode is fine.
                    mode_val = valid_deltas.mode()
                    if not mode_val.empty:
                        return round(float(mode_val[0]), 3)
                    elif not valid_deltas.empty: # Fallback to median if mode is weird
                        logger.warning("Mode is weird, using median instead.")
                        return round(valid_deltas.median(), 3)
            elif len(time_deltas) > 1: # Only one actual delta (df length 2)
                 logger.warning("Only one actual delta, using it.")
                 first_valid_delta = time_deltas.iloc[1:].dropna()
                 if not first_valid_delta.empty:
                     return round(first_valid_delta.iloc[0], 3)

        except Exception as e:
            logger.warning(f"Could not calculate sample period: {e}")
        return None

    def sort_columns_by_prefix_and_frequency(self, columns: List[str]) -> List[str]:
        if len(columns) <= 1:
            return columns
    
        # Separate datetime and other columns
        datetime_cols = [col for col in columns if col == 'Datetime']
        other_cols = [col for col in columns if col != 'Datetime']
        
        # Sort other columns by prefix and frequency
        def parse_column_key(col_name: str) -> tuple[str, float]:
            """Extract prefix and numeric frequency from column name."""
            parts = col_name.split('_', 1)
            if len(parts) != 2:
                return (col_name, 0.0)  # Non-standard format
            
            prefix, freq_str = parts
            try:
                freq_val = float(freq_str)
                return (prefix, freq_val)
            except ValueError:
                # Fallback to string sorting for non-numeric frequencies
                return (prefix, float('inf'))  # Push unparseable to end
        
        sorted_other_cols = sorted(other_cols, key=parse_column_key)
        return datetime_cols + sorted_other_cols

    def _filter_df_columns(self, 
                           df: Optional[pd.DataFrame], 
                           data_category: str, # 'totals' or 'spectral'
                           available_columns_from_parser: List[str], # Canonical names already set by parser
                           return_all_columns: bool = False) -> Optional[pd.DataFrame]:
        if df is None or df.empty:
            return None
        
        cols_to_keep = []
        if 'Datetime' in available_columns_from_parser and 'Datetime' in df.columns:
            cols_to_keep.append('Datetime')

        if return_all_columns:
            for col in available_columns_from_parser:
                if col not in cols_to_keep:
                    cols_to_keep.append(col)
            return df[[c for c in cols_to_keep if c in df.columns]]

        if data_category == 'totals':
            for std_col in self.standard_output_columns:
                if std_col in available_columns_from_parser and std_col not in cols_to_keep:
                    cols_to_keep.append(std_col)
        
        elif data_category == 'spectral':
            # For spectral, always include standard broadband if available (overall levels)
            for std_col in self.standard_output_columns:
                if std_col in available_columns_from_parser and std_col not in cols_to_keep:
                    cols_to_keep.append(std_col)
            
            allowed_spectral_prefixes = self.standard_spectral_prefixes
           
            # And then add all recognized spectral bands
            for col in available_columns_from_parser:
                if col not in cols_to_keep:
                    parts = col.split('_', 1) # Split only on the first underscore
                    if len(parts) == 2:
                        param_prefix = parts[0] # e.g., LZeq, LAFmax
                        freq_suffix = parts[1]  # e.g., 8, 1000, 20k
                        # Check if the suffix (after cleaning if needed by parser) is a recognized freq
                        if param_prefix in allowed_spectral_prefixes and freq_suffix in self.expected_third_octave_suffixes: 
                            cols_to_keep.append(col)

            cols_to_keep = self.sort_columns_by_prefix_and_frequency(cols_to_keep)
        
        if not cols_to_keep or (len(cols_to_keep) == 1 and 'Datetime' in cols_to_keep):
            if len(available_columns_from_parser) > 1 and 'Datetime' in df.columns:
                logger.warning(f"Default filtering for '{data_category}' resulted in minimal columns. Returning all available from parser.")
                cols_to_keep = []
                if 'Datetime' in available_columns_from_parser: cols_to_keep.append('Datetime')
                for col in available_columns_from_parser:
                    if col not in cols_to_keep: cols_to_keep.append(col)

        final_cols_present = [col for col in cols_to_keep if col in df.columns]

        return df[final_cols_present] if final_cols_present else pd.DataFrame()


class NoiseSentryFileParser(AbstractNoiseParser):
    def parse(self, file_path: str, return_all_columns: bool = False) -> ParsedData:
        logger.info(f"SentryParser: Parsing {file_path}")
        parsed_data_obj = ParsedData(
            original_file_path=file_path,
            parser_type='NoiseSentry',
            data_profile='overview',
            spectral_data_type='none'
        )
        try:
            # Using pandas.read_csv directly can be much faster for well-formed CSVs
            # We'll handle the header row and potential trailing commas more carefully
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Skip blank lines at the beginning of the file
                header_line = ""
                line_count = 0
                for line in f:
                    line_count += 1
                    potential_header = line.strip()
                    if potential_header:  # Found a non-empty line
                        header_line = potential_header
                        break
                    
                if not header_line:
                    parsed_data_obj.metadata['error'] = "File is empty or contains only blank lines"
                    return parsed_data_obj
            
                raw_headers = [h.strip() for h in header_line.split(',')]
                # Filter out completely empty headers that result from trailing commas
                raw_headers = [h for h in raw_headers if h] 
            
                sentry_map = {
                    'Time (Date hh:mm:ss.ms)': 'Datetime', 'LEQ dB-A': 'LAeq',
                    'Lmax dB-A': 'LAFmax', 'L10 dB-A': 'LAF10', 'L90 dB-A': 'LAF90'
                }
                canonical_headers = [sentry_map.get(h, h.replace(' ', '_')) for h in raw_headers]
                
                # Read the rest of the file, using only the number of identified canonical headers
                # This helps pandas ignore extraneous columns from trailing commas in data rows
                df_raw = pd.read_csv(file_path, skiprows=line_count, header=None, names=canonical_headers, 
                                     usecols=range(len(canonical_headers)), 
                                     na_filter=False, # Handle empty strings as empty, not NaN initially
                                     on_bad_lines='warn', low_memory=False)
                
                df_raw = df_raw.replace('', np.nan) # Now convert actual empty strings to NaN
                df_raw = df_raw.dropna(how='all') # Drop rows that are entirely NaN

                if df_raw.empty:
                    parsed_data_obj.metadata['error'] = "No data rows found"
                    return parsed_data_obj

            df_raw = self._normalize_datetime_column(df_raw, dt_col_names=['Datetime'])
            if df_raw.empty: # Datetime parsing failed for all rows
                parsed_data_obj.metadata['error'] = "All rows failed Datetime parsing"
                return parsed_data_obj

            df_raw = self._safe_convert_to_float(df_raw)
            
            #assume an overview if longer than 60 seconds
            parsed_data_obj.sample_period_seconds = self._calculate_sample_period(df_raw)
            if parsed_data_obj.sample_period_seconds > 60:
                parsed_data_obj.data_profile = 'overview'
            else:
                parsed_data_obj.data_profile = 'log'
                
            
            found_cols = [col for col in canonical_headers if col in df_raw.columns]
            parsed_data_obj.totals_df = self._filter_df_columns(df_raw, 'totals', found_cols, return_all_columns)
            
            return parsed_data_obj

        except FileNotFoundError:
            parsed_data_obj.metadata['error'] = "File not found"
            return parsed_data_obj
        except Exception as e:
            parsed_data_obj.metadata['error'] = str(e)
            logger.error(f"SentryParser: Error parsing {file_path}: {e}", exc_info=True)
            return parsed_data_obj

class SvanFileParser(AbstractNoiseParser):
    CLEAN_PAT = re.compile(r'\s*\((?:SR|TH|Lin|Fast|Slow|SPL)\)\s*|\s*\[dB\]\s*|\s*Histogram\s*', flags=re.IGNORECASE)
    # For "8_Hz" -> "8", "12.5_Hz" -> "12.5", "1k_Hz" -> "1000"
    FREQ_SUFFIX_PAT = re.compile(r'(\d+(?:\.\d+)?)(k?)_?Hz$', flags=re.IGNORECASE)

    def _get_data_profile_heuristic(self, lines: List[str], file_path: str) -> str:
        filename_upper = os.path.basename(file_path).upper()
        if '_LOG.CSV' in filename_upper: return 'log'
        if '_SUMMARY.CSV' in filename_upper: return 'overview'
        for line in lines[:5]: # Check first few lines for markers
            if '(TH)' in line.upper(): return 'log' # Time History
            if '(SR)' in line.upper(): return 'overview' # Summary Result
        return 'unknown'

    def _clean_freq_suffix(self, freq_str_original: str) -> Optional[str]:
        # Try to match "8_Hz", "10Hz", "12.5_Hz", "1kHz", "1k_Hz"
        # Remove any internal spaces first
        freq_str = freq_str_original.replace(" ", "")
        match = self.FREQ_SUFFIX_PAT.match(freq_str)
        if match:
            num, k_suffix = match.groups()
            val = float(num)
            if k_suffix.lower() == 'k':
                val *= 1000
            # Return as string, matching EXPECTED_THIRD_OCTAVE_SUFFIXES format (e.g. "1000", "12.5")
            return str(int(val)) if val == int(val) else str(val)

        # Fallback for cases like just "8", "12.5", "1000" if Hz part is missing
        if freq_str.replace('.', '', 1).isdigit():
            return freq_str
        if freq_str.lower().endswith('k') and freq_str[:-1].replace('.', '', 1).isdigit():
             val = float(freq_str[:-1]) * 1000
             return str(int(val)) if val == int(val) else str(val)
            
        return None # Not a recognized frequency pattern

    def _map_svan_column(self, original_col: str) -> Tuple[Optional[str], Optional[str]]:
        cleaned = self.CLEAN_PAT.sub('', original_col)
        cleaned = cleaned.replace(' ', '_').replace('-', '_').replace('/', '_')
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')

        if 'Date_&_time' in cleaned or 'Start_date_&_time' in cleaned: return 'Datetime', 'datetime'

        bb_map = {
            "LAeq": r"^P\d_.*LAeq$", "LAFmax": r"^P\d_.*LAFmax$", "LAFmin": r"^P\d_.*LAFmin$",
            "LAF10": r"^P\d_.*LAeq_L10$", "LAF90": r"^P\d_.*LAeq_L90$",
            # Svan broadband "total" from spectral can also be LAeq
            "LAeq_svan_overall": r"1/3_Oct_Leq_TOTAL_A" 
        }
        for can_name, pattern in bb_map.items():
            if re.fullmatch(pattern, cleaned, re.IGNORECASE):
                return "LAeq" if can_name == "LAeq_svan_overall" else can_name, 'totals' # Map total_A to LAeq

        # Spectral: e.g., 1/3_Octave_1/3_Oct_LZeq_8_Hz
        if "Oct" in cleaned: # Indicates a spectral column
            parts = cleaned.split('_')
            param_prefix = None
            freq_suffix_cleaned = None
            for p in parts:
                # Find a known parameter type (case-insensitive for robustness)
                if p.upper() in [prefix.upper() for prefix in self.standard_output_columns + ['LZeq', 'LCeq', 'LZFmin', 'LCFmin', 'LZFmax', 'LCFmax']]: # Check against a broader list
                    param_prefix = p.upper().replace("LAF","LA").replace("LZF","LZ").replace("LCF","LC") # Normalize LAFmax to LAmax for consistency if desired
                    if param_prefix.startswith("LA"): param_prefix = param_prefix.replace("LA","LAF") # but keep LAF for standard outputs
                    break
            
            if not param_prefix: # Try to find any 'L' starting parameter
                for p in parts:
                    if p.startswith('L') and len(p) > 1 and p[1].isalpha():
                        param_prefix = p
                        break
            
            #correct the case
            param_prefix = param_prefix.lower().replace("laf","LAF").replace("lzf","LZF").replace("lcf","LCF").replace("la","LA").replace("lc","LC").replace("lz","LZ")

            for p_val in reversed(parts): # Search from end for frequency
                cleaned_freq = self._clean_freq_suffix(p_val)
                if cleaned_freq in self.expected_third_octave_suffixes:
                    freq_suffix_cleaned = cleaned_freq
                    break
            
            if param_prefix and freq_suffix_cleaned:
                return f"{param_prefix}_{freq_suffix_cleaned}", 'spectral'
        return None, None

    def parse(self, file_path: str, return_all_columns: bool = False) -> ParsedData:
        logger.info(f"SvanParser: Parsing {file_path}")
        parsed_data_obj = ParsedData(original_file_path=file_path, parser_type='Svan')
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: lines = f.readlines()
            if not lines: parsed_data_obj.metadata['error'] = "File empty"; return parsed_data_obj

            parsed_data_obj.data_profile = self._get_data_profile_heuristic(lines, file_path)
            
            h_indices = [-1,-1,-1] # r1_idx, r2_idx, r3_idx (datetime row)
            for i, line in enumerate(lines):
                if 'date & time' in line.lower() or 'start date & time' in line.lower():
                    if i > 1: h_indices = [i-2, i-1, i]; break
            if h_indices[2] == -1:
                parsed_data_obj.metadata['error'] = "Svan datetime header not found"; return parsed_data_obj

            raw_headers = []
            temp_headers_parts = [
                pd.read_csv(StringIO(lines[idx]), header=None, dtype=str).iloc[0].fillna('').tolist() if idx >=0 else [] 
                for idx in h_indices
            ]
            max_h_len = max(len(h) for h in temp_headers_parts) if temp_headers_parts else 0
            for i in range(max_h_len):
                parts = [h[i].strip() if i < len(h) else '' for h in temp_headers_parts]
                raw_headers.append(re.sub(r'_+', '_', "_".join(p for p in parts if p)).strip('_') or f"Unnamed_{i}")
            
            # Trim trailing unnamed columns from headers list if data suggests they are empty
            while raw_headers and raw_headers[-1].startswith("Unnamed_"):
                col_idx_to_check = len(raw_headers) -1
                is_col_empty_in_data = True
                for data_line_idx in range(h_indices[2] + 1, min(h_indices[2] + 11, len(lines))):
                    data_parts = lines[data_line_idx].strip().split(',')
                    if col_idx_to_check < len(data_parts) and data_parts[col_idx_to_check].strip():
                        is_col_empty_in_data = False; break
                if is_col_empty_in_data: raw_headers.pop()
                else: break
            
            df_full_raw = pd.read_csv(StringIO("".join(lines[h_indices[2]+1:])), header=None, 
                                      names=raw_headers, usecols=range(len(raw_headers)), 
                                      sep=',', na_filter=False, on_bad_lines='warn', low_memory=False)
            df_full_raw = df_full_raw.replace('', np.nan).dropna(how='all')
            if df_full_raw.empty: 
                parsed_data_obj.metadata['error'] = "No data rows"; return parsed_data_obj

            canonical_map = {}
            found_totals_cols, found_spectral_cols = set(), set()
            for raw_col in df_full_raw.columns:
                can_name, cat = self._map_svan_column(str(raw_col))
                if can_name:
                    unique_can_name = can_name
                    c = 1
                    while unique_can_name in canonical_map.values(): # Ensure unique canonical names if collisions
                        unique_can_name = f"{can_name}_{c}"; c+=1
                    canonical_map[raw_col] = unique_can_name
                    if cat == 'datetime': found_totals_cols.add(unique_can_name); found_spectral_cols.add(unique_can_name)
                    if cat == 'totals': found_totals_cols.add(unique_can_name)
                    if cat == 'spectral': found_spectral_cols.add(unique_can_name)
            
            df_renamed = df_full_raw.rename(columns=canonical_map)
            if 'Datetime' not in df_renamed.columns:
                parsed_data_obj.metadata['error'] = "Datetime column not established"; return parsed_data_obj
            
            df_renamed = self._normalize_datetime_column(df_renamed, dt_col_names=['Datetime'])
            if df_renamed.empty: parsed_data_obj.metadata['error'] = "All rows failed Datetime"; return parsed_data_obj
            
            df_renamed = self._safe_convert_to_float(df_renamed)
            parsed_data_obj.sample_period_seconds = self._calculate_sample_period(df_renamed)

            # Determine spectral type from raw headers
            actual_spectral_type = 'none'
            raw_headers_joined = ' '.join(raw_headers).lower()
            if '1/3 octave' in raw_headers_joined:
                actual_spectral_type = 'third_octave'
            elif '1/1 octave' in raw_headers_joined:
                actual_spectral_type = 'octave'
                
            if found_spectral_cols and 'Datetime' in found_spectral_cols:
                spectral_cols_for_df = [c for c in found_spectral_cols if c in df_renamed.columns]
                if len(spectral_cols_for_df) > 1:
                    df_spec_subset = df_renamed[spectral_cols_for_df].copy()
                    parsed_data_obj.spectral_df = self._filter_df_columns(df_spec_subset, 'spectral', spectral_cols_for_df, return_all_columns)
            
            if found_totals_cols and 'Datetime' in found_totals_cols:
                totals_cols_for_df = [c for c in found_totals_cols if c in df_renamed.columns]
                if len(totals_cols_for_df) > 1:
                    df_totals_subset = df_renamed[totals_cols_for_df].copy()
                    parsed_data_obj.totals_df = self._filter_df_columns(df_totals_subset, 'totals', totals_cols_for_df, return_all_columns)

            parsed_data_obj.spectral_data_type = actual_spectral_type
            return parsed_data_obj

        except FileNotFoundError:
            parsed_data_obj.metadata['error'] = "File not found"; return parsed_data_obj
        except Exception as e:
            parsed_data_obj.metadata['error'] = str(e)
            logger.error(f"SvanParser: Error parsing {file_path}: {e}", exc_info=True)
            return parsed_data_obj


class NTiFileParser(AbstractNoiseParser):
    # ... (NTi specific metadata extraction and table parsing logic as before) ...
    # The key change will be in how _parse_nti_table returns column names
    # and how the main parse method sets up ParsedData.

    def _extract_nti_metadata(self, lines: List[str]) -> Dict[str, Any]:
        # (Same as your previous version)
        meta = {'hardware_config': {}, 'measurement_setup': {}, 'time_info': {}}
        current_section_dict = None
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("---"): continue
            if stripped.startswith("# Hardware Configuration"): current_section_dict = meta['hardware_config']; continue
            if stripped.startswith("# Measurement Setup"): current_section_dict = meta['measurement_setup']; continue
            if stripped.startswith("# Time"): current_section_dict = meta['time_info']; continue
            if stripped.startswith(("# RTA Results", "# Broadband Results", "# RTA LOG Results", "# Broadband LOG Results")):
                break 
            if current_section_dict is not None:
                parts = stripped.split(':', 1)
                if len(parts) == 2:
                    key, value = map(str.strip, parts)
                    if key: current_section_dict[key] = value
        return meta

    def _parse_nti_table(self, data_lines: List[str], 
                         base_header_config: List[Tuple[int, int]], 
                         param_type_header_row_idx: Optional[int], 
                         freq_header_row_idx: Optional[int],       
                         data_start_offset: int,                   
                         is_log_file: bool = False) -> Optional[pd.DataFrame]:
        # (Largely same logic, but ensure canonical names for spectral columns)
        parsed_block = [[item.strip() for item in line.strip().split('\t')] for line in data_lines]
        parsed_block = [row for row in parsed_block if any(item.strip() for item in row)]

        if not parsed_block or len(parsed_block) < data_start_offset + (param_type_header_row_idx if param_type_header_row_idx is not None else 0) +1:
            return None

        all_column_headers = []
        current_col_offset = 0 # Keep track of columns consumed by base headers
        for row_idx, col_slice_end in base_header_config:
            all_column_headers.extend(parsed_block[row_idx][:col_slice_end])
            current_col_offset = max(current_col_offset, col_slice_end) # Update offset

        if param_type_header_row_idx is not None and freq_header_row_idx is not None: # Spectral
            band_hz_col_idx = -1
            try: band_hz_col_idx = parsed_block[freq_header_row_idx].index("Band [Hz]")
            except ValueError: return None # Critical

            param_types = parsed_block[param_type_header_row_idx][band_hz_col_idx + 1:]
            frequencies = parsed_block[freq_header_row_idx][band_hz_col_idx + 1:]
            
            num_spectral_cols = min(len(param_types), len(frequencies))
            for i in range(num_spectral_cols):
                param_type = param_types[i].replace('_dt', '').replace('.0%', '')
                freq = frequencies[i].replace('.0', '') # "6.3", "8", "1000"
                if param_type and freq: all_column_headers.append(f"{param_type}_{freq}")
        
        elif param_type_header_row_idx is not None : # Broadband Report/Log (params after base)
            # Parameters start after the base headers on their designated row
            params_on_row = parsed_block[param_type_header_row_idx]
            # Check if base_header_config correctly identified the span of base headers
            # For RPT files, base headers are on row 0, params on row 1.
            # For LOG files, params are on row 0, after base headers.
            start_col_for_params = current_col_offset if is_log_file and param_type_header_row_idx == base_header_config[0][0] else 0
            if not is_log_file and len(base_header_config) > 0: # RPT report style
                 start_col_for_params = base_header_config[0][1] # Params start after the first block of base headers


            all_column_headers.extend([h.replace('.0%', '').replace('_dt','') for h in params_on_row[start_col_for_params:]])
        
        # Deduplicate headers (e.g. if "Time" appeared twice)
        seen = set()
        unique_headers = []
        for x in all_column_headers:
            if x not in seen:
                unique_headers.append(x)
                seen.add(x)
        all_column_headers = unique_headers


        actual_data_start_row = 0
        if freq_header_row_idx is not None: # Spectral case
            actual_data_start_row = freq_header_row_idx + data_start_offset
        elif param_type_header_row_idx is not None: # Broadband case
            actual_data_start_row = param_type_header_row_idx + data_start_offset
        else: # Should not happen if configured correctly
            actual_data_start_row = max(idx for idx, _ in base_header_config) + data_start_offset
        
        data_rows_list = []
        for row_idx_loop, row_content in enumerate(parsed_block[actual_data_start_row:]):
            if is_log_file and (not row_content or row_content[0].count('-') != 2): continue 
            
            # Pad row if shorter than headers (can happen with missing trailing values)
            if len(row_content) < len(all_column_headers):
                row_content.extend([np.nan] * (len(all_column_headers) - len(row_content)))
            data_rows_list.append(row_content[:len(all_column_headers)])


        if not data_rows_list: return None
        df = pd.DataFrame(data_rows_list, columns=all_column_headers)
        return df


    def parse(self, file_path: str, return_all_columns: bool = False) -> ParsedData:
        logger.info(f"NTiParser: Parsing {file_path}")
        parsed_data_obj = ParsedData(original_file_path=file_path, parser_type='NTi')
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: lines = f.readlines()
            if not lines: parsed_data_obj.metadata['error'] = "File empty"; return parsed_data_obj

            checksum_idx = next((i for i, line in enumerate(lines) if "#CheckSum" in line), len(lines))
            content_lines = lines[:checksum_idx]
            if not content_lines: parsed_data_obj.metadata['error'] = "No content before checksum"; return parsed_data_obj
            
            parsed_data_obj.metadata.update(self._extract_nti_metadata(content_lines))

            filename_lower = os.path.basename(file_path).lower()
            df_raw = None
            data_category = 'totals'
            spectral_type = 'none'
            is_log = False
            datetime_cols_in_raw = ['Date', 'Time'] # Default for logs

            if filename_lower.endswith('_123_rpt_report.txt'):
                data_start_marker = "# Broadband Results"; table_start_idx = next((i for i,l in enumerate(content_lines) if l.strip().startswith(data_start_marker)),-1)
                if table_start_idx != -1:
                    df_raw = self._parse_nti_table(content_lines[table_start_idx+1:], [(0,4)], 1, None, 2, False)
                parsed_data_obj.data_profile = 'overview'; data_category='totals'; datetime_cols_in_raw = ['Start Date', 'Start Time']
            elif filename_lower.endswith('_rta_3rd_rpt_report.txt'):
                data_start_marker = "# RTA Results"; table_start_idx = next((i for i,l in enumerate(content_lines) if l.strip().startswith(data_start_marker)),-1)
                if table_start_idx != -1:
                    df_raw = self._parse_nti_table(content_lines[table_start_idx+1:], [(0,4)], 0, 1, 2, False)
                parsed_data_obj.data_profile = 'overview'; data_category='spectral'; spectral_type='third_octave'; datetime_cols_in_raw = ['Start Date', 'Start Time']
            elif filename_lower.endswith('_123_log.txt'):
                data_start_marker = "# Broadband LOG Results"; table_start_idx = next((i for i,l in enumerate(content_lines) if l.strip().startswith(data_start_marker)),-1)
                if table_start_idx != -1:
                    df_raw = self._parse_nti_table(content_lines[table_start_idx+1:], [(0,3)], 0, None, 1, True)
                parsed_data_obj.data_profile = 'log'; data_category='totals'; is_log = True
            elif filename_lower.endswith('_rta_3rd_log.txt'):
                data_start_marker = "# RTA LOG Results"; table_start_idx = next((i for i,l in enumerate(content_lines) if l.strip().startswith(data_start_marker)),-1)
                if table_start_idx != -1:
                     df_raw = self._parse_nti_table(content_lines[table_start_idx+1:], [(1,3)], 0, 1, 1, True) # Date/Time/Timer are on row 1 of block
                parsed_data_obj.data_profile = 'log'; data_category='spectral'; spectral_type='third_octave'; is_log = True
            else:
                parsed_data_obj.metadata['error'] = "Unknown NTi subtype"; return parsed_data_obj

            if df_raw is None or df_raw.empty:
                parsed_data_obj.metadata['error'] = f"No data parsed for {parsed_data_obj.data_profile} type"
                return parsed_data_obj
            
            df_processed = self._normalize_datetime_column(df_raw.copy(), dt_col_names=datetime_cols_in_raw)
            if df_processed.empty: parsed_data_obj.metadata['error']="All rows failed Datetime"; return parsed_data_obj
            
            df_processed = self._safe_convert_to_float(df_processed)
            parsed_data_obj.sample_period_seconds = self._calculate_sample_period(df_processed)
            
            available_cols = [col for col in df_processed.columns if col]
            filtered_df = self._filter_df_columns(df_processed, data_category, available_cols, return_all_columns)
            
            parsed_data_obj.spectral_data_type = spectral_type
            if data_category == 'totals': parsed_data_obj.totals_df = filtered_df
            elif data_category == 'spectral': parsed_data_obj.spectral_df = filtered_df
            
            return parsed_data_obj

        except FileNotFoundError:
            parsed_data_obj.metadata['error'] = "File not found"; return parsed_data_obj
        except Exception as e:
            parsed_data_obj.metadata['error'] = str(e)
            logger.error(f"NTiParser: Error parsing {file_path}: {e}", exc_info=True)
            return parsed_data_obj

class AudioFileParser(AbstractNoiseParser):
    def parse(self, path: str, return_all_columns: bool = False) -> ParsedData:
        # ... (implementation largely same as before, ensuring ParsedData fields are set) ...
        logger.info(f"AudioFileParser: Processing path {path}")
        parsed_data_obj = ParsedData(
            original_file_path=path, 
            parser_type='Audio',
            data_profile='file_list',
            spectral_data_type='none',
            # sample_period_seconds is not applicable for file listing
        )
        audio_files_details = []
        try:
            if not os.path.exists(path):
                parsed_data_obj.metadata['error'] = "Path does not exist"; return parsed_data_obj

            if os.path.isdir(path):
                parsed_data_obj.metadata['type'] = 'directory_scan'
                for item_name in os.listdir(path):
                    item_path = os.path.join(path, item_name)
                    # Filter for common audio survey filenames
                    if os.path.isfile(item_path) and "_Audio_".lower() in item_name.lower() and item_name.lower().endswith(('.wav', '.mp3', '.ogg', '.flac')):
                        stats = os.stat(item_path)
                        audio_files_details.append({
                            'filename': item_name, 'full_path': item_path,
                            'size_mb': round(stats.st_size / (1024 * 1024), 2),
                            'modified_time': pd.to_datetime(stats.st_mtime, unit='s', utc=True).tz_localize(None).round('S'),
                            'Datetime': pd.to_datetime(stats.st_mtime, unit='s', utc=True).tz_localize(None).round('S')
                        })
            elif os.path.isfile(path) and path.lower().endswith(('.wav', '.mp3', '.ogg', '.flac')):
                parsed_data_obj.metadata['type'] = 'single_file'
                stats = os.stat(path)
                audio_files_details.append({
                    'filename': os.path.basename(path), 'full_path': path,
                    'size_mb': round(stats.st_size / (1024 * 1024), 2),
                    'modified_time': pd.to_datetime(stats.st_mtime, unit='s', utc=True).tz_localize(None).round('S'),
                    'Datetime': pd.to_datetime(stats.st_mtime, unit='s', utc=True).tz_localize(None).round('S')
                })
            else:
                parsed_data_obj.metadata['error'] = "Not a recognized audio file or directory"; return parsed_data_obj

            parsed_data_obj.metadata['audio_files_count'] = len(audio_files_details)
            
            if audio_files_details:
                df_audio_list = pd.DataFrame(audio_files_details)
                if 'Datetime' in df_audio_list.columns:
                     df_audio_list = df_audio_list.sort_values(by='Datetime').reset_index(drop=True)
                parsed_data_obj.totals_df = df_audio_list # Storing file list as totals_df
            
            return parsed_data_obj
        except Exception as e:
            parsed_data_obj.metadata['error'] = str(e)
            logger.error(f"AudioFileParser: Error processing {path}: {e}", exc_info=True)
            return parsed_data_obj

class NoiseParserFactory:
    @staticmethod
    def get_parser(file_path: str, parser_type: str = 'auto') -> Optional[AbstractNoiseParser]:
        # ... (same as before) ...
        filename_lower = os.path.basename(file_path).lower()
        if '_rpt_report.txt' in filename_lower or '_log.txt' in filename_lower:
            if "_rta_" in filename_lower or "_123_" in filename_lower : # more specific for NTi
                return NTiFileParser()
        if filename_lower.endswith(('.csv','.svl')) or "overview.xlsx" in filename_lower : # More specific for Svan and Sentry
            # Sentry CSVs often have a very specific naming pattern
            if re.search(r'_\d{4}_\d{2}_\d{2}__\d{2}h\d{2}m\d{2}s.*\.csv$', filename_lower):
                return NoiseSentryFileParser()
            # Otherwise, assume Svan for .csv, .svl, or overview.xlsx
            return SvanFileParser()
        if os.path.isdir(file_path) or filename_lower.endswith(('.wav', '.mp3', '.ogg', '.flac')):
             return AudioFileParser()
        logger.warning(f"Could not determine parser type for: {file_path}")
        return None


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # For testing, you'd set up dummy files similar to the previous example
    

    # --- Noise Sentry Example ---
    sentry_file_path = r"G:\My Drive\Programing\example files\Noise Sentry\cricket nets 2A _2025_06_03__20h55m22s_2025_05_29__15h30m00s.csv"   

    print(f"\n--- Testing NoiseSentryParser on {sentry_file_path} ---")
    sentry_parser = NoiseParserFactory.get_parser(sentry_file_path)
    if sentry_parser:
        sentry_data = sentry_parser.parse(sentry_file_path)
        print("Sentry Metadata:", sentry_data.metadata)
        print("Sentry Data Profile:", sentry_data.data_profile)
        print("Sentry Sample Period:", sentry_data.sample_period_seconds)
        if sentry_data.totals_df is not None: print("Sentry Totals DF Head:\n", sentry_data.totals_df.head())

    # --- Svan Log Example ---
    svan_log_path = r"G:\My Drive\Programing\example files\Svan full data\L259_log.csv"

    print(f"\n--- Testing SvanFileParser on {svan_log_path} (Log File) ---")
    svan_parser = NoiseParserFactory.get_parser(svan_log_path)
    if svan_parser:
        svan_data = svan_parser.parse(svan_log_path)
        print(f"\n--- Testing SvanFileParser on {svan_log_path} (Log File) ---")
        print("Svan Metadata:", svan_data.metadata)
        print("Svan Data Profile:", svan_data.data_profile)
        print("Svan Spectral Type:", svan_data.spectral_data_type)
        print("Svan Sample Period:", svan_data.sample_period_seconds)
        if svan_data.totals_df is not None: print("Svan Totals DF Head:\n", svan_data.totals_df.head())
        if svan_data.spectral_df is not None: print("Svan Spectral DF Head:\n", svan_data.spectral_df.head())

    # --- Svan Summary Example ---
    svan_summary_path = r"G:\My Drive\Programing\example files\Svan full data\L259_summary.csv"
    svan_parser = NoiseParserFactory.get_parser(svan_summary_path)
    if svan_parser:
        svan_data = svan_parser.parse(svan_summary_path)
        print(f"\n--- Testing SvanFileParser on {svan_summary_path} (Summary File) ---")
        print("Svan Metadata:", svan_data.metadata)
        print("Svan Data Profile:", svan_data.data_profile)
        print("Svan Spectral Type:", svan_data.spectral_data_type)
        print("Svan Sample Period:", svan_data.sample_period_seconds)
        if svan_data.totals_df is not None: print("Svan Totals DF Head:\n", svan_data.totals_df.head())
        if svan_data.spectral_df is not None: print("Svan Spectral DF Head:\n", svan_data.spectral_df.head())


    
    # --- NTi RTA Log Example ---
    nti_rta_log_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Log.txt"
    nti_parser = NoiseParserFactory.get_parser(nti_rta_log_path)
    if nti_parser:
        nti_data = nti_parser.parse(nti_rta_log_path)
        print(f"\n--- Testing NTiFileParser on {nti_rta_log_path} (RTA Log) ---")
        print("NTi Metadata:", nti_data.metadata)
        print("NTi Data Profile:", nti_data.data_profile)
        print("NTi Spectral Type:", nti_data.spectral_data_type)
        print("NTi Sample Period:", nti_data.sample_period_seconds)
        if nti_data.totals_df is not None: print("NTi Totals DF Head:\n", nti_data.totals_df.head()) # Should be None or empty for RTA
        if nti_data.spectral_df is not None: print("NTi Spectral DF Head:\n", nti_data.spectral_df.head())