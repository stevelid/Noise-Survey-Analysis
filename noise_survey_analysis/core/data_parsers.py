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
import wave
import contextlib
try:
    import soundfile as sf  # Supports WAV/FLAC/OGG and more via libsndfile
    _HAS_SF = True
except Exception:
    sf = None  # type: ignore
    _HAS_SF = False

logger = logging.getLogger(__name__)

# --- Standard Column Definitions ---
# These are the columns we aim to provide by default if available in the source.
STANDARD_OUTPUT_COLUMNS = ['Datetime', 'LAF90', 'LAF10', 'LAFmax', 'LAeq']
STANDARD_SPECTRAL_PREFIXES = ['LZeq', 'LZmax', 'LZFmax', 'LZF90']

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


@dataclass
class FileValidityHint:
    """Lightweight metadata produced during a fast header inspection."""

    status: str = "unknown"
    reason: str = ""
    header_excerpt: str = ""

    def clipped_excerpt(self, max_chars: int = 200) -> str:
        if not self.header_excerpt:
            return ""
        excerpt = self.header_excerpt.strip().replace("\r", " ")
        return excerpt[:max_chars]


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
        """Safely convert all non-'Datetime' columns to numeric.

        - Leaves None/empty dataframes unchanged
        - Uses pandas' to_numeric with errors='coerce' to avoid exceptions
        - Preserves already numeric columns
        """
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

    def inspect_file_header(self, file_path: str, max_lines: int = 20) -> FileValidityHint:
        """Quickly inspect the top of a file to gauge if it looks parseable."""

        return FileValidityHint()

    def _read_file_head(self, file_path: str, max_lines: int = 20) -> List[str]:
        lines: List[str] = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as handle:
                for _ in range(max_lines):
                    line = handle.readline()
                    if not line:
                        break
                    lines.append(line.rstrip('\n'))
        except Exception as exc:
            logger.debug(f"Failed to read header for {file_path}: {exc}")
        return lines

    def _normalize_datetime_column(self, df: pd.DataFrame,
                                   dt_col_names: List[str],
                                   new_name: str = 'Datetime',
                                   sort: bool = True) -> pd.DataFrame:
        """Create a single timezone-aware UTC 'Datetime' column from 1 or 2 source columns.

        Accepts either a single combined datetime column or separate date/time columns.
        If multiple potential date/time columns are provided, it will pick the most
        appropriate pair (e.g., 'Date'+'Time' or 'Start Date'+'Start Time').
        Any unparsable rows are dropped.
        """
        if df.empty:
            return df

        # Determine which datetime source(s) to use
        selected: Optional[Tuple[str, ...]] = None
        # Common pairs first
        if {'Date', 'Time'}.issubset(df.columns):
            selected = ('Date', 'Time')
        elif {'Start Date', 'Start Time'}.issubset(df.columns):
            selected = ('Start Date', 'Start Time')
        elif len(dt_col_names) == 2 and all(c in df.columns for c in dt_col_names):
            selected = (dt_col_names[0], dt_col_names[1])
        elif len(dt_col_names) >= 1 and dt_col_names[0] in df.columns:
            selected = (dt_col_names[0],)

        def _to_utc(series: pd.Series) -> pd.Series:
            s = pd.to_datetime(series, errors='coerce')
            try:
                # Match original semantics: always treat values as local Europe/London
                # regardless of any incoming timezone info.
                s = s.dt.tz_localize(None)
                s = s.dt.tz_localize('Europe/London', ambiguous='infer')
                s = s.dt.tz_convert('UTC')
            except Exception as e:
                logger.warning(f"Failed to localize/convert timezone: {e}")
            return s

        if selected is None:
            logger.warning(f"Could not form datetime from columns: {dt_col_names}")
            df[new_name] = pd.NaT
        else:
            if len(selected) == 1:
                df[new_name] = _to_utc(df[selected[0]])
            else:
                # Combine date + time to a single string
                combined = df[selected[0]].astype(str) + ' ' + df[selected[1]].astype(str)
                df[new_name] = _to_utc(combined)

        # Drop original date/time columns to avoid duplicates
        for old_dt_col in dt_col_names:
            if old_dt_col != new_name and old_dt_col in df.columns:
                df = df.drop(columns=[old_dt_col])

        # Drop rows where datetime failed to parse
        df = df.dropna(subset=[new_name])

        if sort and not df.empty:
            df = df.sort_values(by=new_name).reset_index(drop=True)
        return df

    def _calculate_sample_period(self, df: Optional[pd.DataFrame]) -> Optional[float]:
        """Estimate the most common sample period (seconds) from a Datetime column.

        Uses mode of time differences with sensible fallbacks. Returns None if
        insufficient data or Datetime not present.
        """
        if df is None or df.empty or 'Datetime' not in df.columns or len(df) < 2:
            return None
        if len(df) < 3: # Only one interval
            if len(df) == 2:
                delta = (df['Datetime'].iloc[1] - df['Datetime'].iloc[0]).total_seconds()
                return round(delta, 3) if delta > 0 else None
            return None # Only one data point

        try:
            # Datetime should already be sorted by _normalize_datetime_column
            time_deltas = df['Datetime'].diff().dt.total_seconds()
            
            # Use deltas from the 2nd to the 2nd-to-last original data point.
            if len(time_deltas) >= 3: # Requires at least df length 3, so 2 actual deltas
                valid_deltas = time_deltas.iloc[1:-1] # All deltas except the first NaN and potentially last
                if len(valid_deltas) > 20: # If many samples, trim ends to avoid startup/shutdown effects
                    valid_deltas = valid_deltas.iloc[5:-5] 
                
                valid_deltas = valid_deltas.dropna()
                if not valid_deltas.empty:
                    # Mode is good for finding the most common interval in logged data
                    # If mode has multiple values (equally common), median of modes or first mode is fine.
                    mode_val = valid_deltas.mode()
                    if not mode_val.empty:
                        return round(float(mode_val[0]), 3)
                    # Fallback to median if mode is weird (e.g., all unique values)
                    return round(valid_deltas.median(), 3)
            elif len(time_deltas) > 1: # Only one actual delta (df length 2)
                 first_valid_delta = time_deltas.iloc[1:].dropna()
                 if not first_valid_delta.empty:
                     return round(first_valid_delta.iloc[0], 3)

        except Exception as e:
            logger.warning(f"Could not calculate sample period: {e}")
        return None

    def sort_columns_by_prefix_and_frequency(self, columns: List[str]) -> List[str]:
        """Sort spectral-like columns by their parameter prefix then frequency.

        Keeps 'Datetime' first (if present) and sorts the remainder by parsing
        names of the form '<prefix>_<freq>' where freq may include 'k' for thousands.
        """
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
                return (col_name, 0.0)  # Non-standard format, sort by name
            
            prefix, freq_str = parts
            try:
                # Handle cases like '1k', '2.5k' if they exist, though not in standard list
                freq_val = float(freq_str.lower().replace('k', '')) * (1000 if 'k' in freq_str.lower() else 1)
                return (prefix, freq_val)
            except ValueError:
                # Fallback to string sorting for non-numeric frequencies
                return (prefix, float('inf'))  # Push unparseable to end
        
        sorted_other_cols = sorted(other_cols, key=parse_column_key)
        return datetime_cols + sorted_other_cols

    def _filter_df_columns(self,
                           df: Optional[pd.DataFrame],
                           data_category: str,  # 'totals' or 'spectral'
                           available_columns_from_parser: List[str],  # Canonical names already set by parser
                           return_all_columns: bool = False) -> Optional[pd.DataFrame]:
        """Filter dataframe to the expected set of columns for a given category.

        - If return_all_columns is True, returns all available columns (plus Datetime if present)
        - For 'totals', keeps standard broadband columns
        - For 'spectral', keeps standard broadband columns plus recognized spectral bands
        Always returns a copy to avoid SettingWithCopy warnings.
        """
        if df is None or df.empty:
            return None
        
        cols_to_keep = []
        if 'Datetime' in available_columns_from_parser and 'Datetime' in df.columns:
            cols_to_keep.append('Datetime')

        if return_all_columns:
            for col in available_columns_from_parser:
                if col not in cols_to_keep:
                    cols_to_keep.append(col)
            # Use a copy to avoid SettingWithCopyWarning
            return df[[c for c in cols_to_keep if c in df.columns]].copy()

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
                        param_prefix = parts[0]
                        freq_suffix = parts[1]
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

        # Use a copy to avoid SettingWithCopyWarning
        return df[final_cols_present].copy() if final_cols_present else pd.DataFrame()


class NoiseSentryFileParser(AbstractNoiseParser):
    EXPECTED_KEYWORDS = (
        'time', 'leq', 'lmax', 'l10', 'l90'
    )

    def inspect_file_header(self, file_path: str, max_lines: int = 20) -> FileValidityHint:
        lines = self._read_file_head(file_path, max_lines=max_lines)
        if not lines:
            return FileValidityHint(status='unlikely_valid', reason='File appears to be empty.')

        header_line = next((line for line in lines if line.strip()), '')
        if not header_line:
            return FileValidityHint(status='unlikely_valid', reason='No header row detected in file head.')

        tokens = [t.strip().strip('"') for t in re.split('[;\t,]', header_line) if t.strip()]
        normalized = [token.lower() for token in tokens]
        matches = sum(1 for keyword in self.EXPECTED_KEYWORDS if any(keyword in token for token in normalized))

        excerpt = header_line[:200]

        if matches >= 4:
            return FileValidityHint(
                status='likely_valid',
                reason=f"Detected {matches} standard Noise Sentry header columns.",
                header_excerpt=excerpt,
            )
        if matches >= 2:
            return FileValidityHint(
                status='needs_review',
                reason='Only a subset of expected Noise Sentry columns were detected.',
                header_excerpt=excerpt,
            )
        return FileValidityHint(
            status='needs_review',
            reason='Header does not match typical Noise Sentry structure.',
            header_excerpt=excerpt,
        )

    def parse(self, file_path: str, return_all_columns: bool = False) -> ParsedData:
        logger.info(f"SentryParser: Parsing {file_path}")
        parsed_data_obj = ParsedData(
            original_file_path=file_path,
            parser_type='NoiseSentry',
            spectral_data_type='none'
        )
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                header_line = ""
                line_count = 0
                for line in f:
                    line_count += 1
                    potential_header = line.strip()
                    if potential_header:
                        header_line = potential_header
                        break
                    
                if not header_line:
                    parsed_data_obj.metadata['error'] = "File is empty or contains only blank lines"
                    return parsed_data_obj
            
                raw_headers = [h.strip() for h in header_line.split(',')]
                raw_headers = [h for h in raw_headers if h] 
            
                sentry_map = {
                    'Time (Date hh:mm:ss.ms)': 'Datetime', 'LEQ dB-A': 'LAeq',
                    'Lmax dB-A': 'LAFmax', 'L10 dB-A': 'LAF10', 'L90 dB-A': 'LAF90'
                }
                canonical_headers = [sentry_map.get(h, h.replace(' ', '_')) for h in raw_headers]
                
                df_raw = pd.read_csv(file_path, skiprows=line_count, header=None, names=canonical_headers, 
                                     usecols=range(len(canonical_headers)), 
                                     na_filter=False,
                                     on_bad_lines='warn', low_memory=False)
                
                df_raw = df_raw.replace('', np.nan).dropna(how='all')

                if df_raw.empty:
                    parsed_data_obj.metadata['error'] = "No data rows found"
                    return parsed_data_obj

            df_raw = self._normalize_datetime_column(df_raw, dt_col_names=['Datetime'])
            if df_raw.empty:
                parsed_data_obj.metadata['error'] = "All rows failed Datetime parsing"
                return parsed_data_obj

            df_raw = self._safe_convert_to_float(df_raw)
            
            parsed_data_obj.sample_period_seconds = self._calculate_sample_period(df_raw)
            if parsed_data_obj.sample_period_seconds is not None and parsed_data_obj.sample_period_seconds > 60:
                parsed_data_obj.data_profile = 'overview'
            else:
                parsed_data_obj.data_profile = 'log'
                
            found_cols = [col for col in canonical_headers if col in df_raw.columns]
            parsed_data_obj.totals_df = self._filter_df_columns(df_raw, 'totals', found_cols, return_all_columns)
            
            return parsed_data_obj

        except FileNotFoundError:
            parsed_data_obj.metadata['error'] = "File not found"
            return parsed_data_obj

class SvanFileParser(AbstractNoiseParser):

    CLEAN_PAT = re.compile(r'\s*\((?:SR|TH|Lin|Fast|Slow|SPL)\)\s*|\s*\[dB\]\s*|\s*Histogram\s*', flags=re.IGNORECASE)
    FREQ_SUFFIX_PAT = re.compile(r'(\d+(?:\.\d+)?)(k?)_?Hz$', flags=re.IGNORECASE)

    EXPECTED_KEYWORDS = (
        'date', 'time', 'laeq', 'lafmax', 'lafmin', 'laf10', 'laf90', 'lzeq', 'band [hz]'
    )

    def inspect_file_header(self, file_path: str, max_lines: int = 25) -> FileValidityHint:
        lines = self._read_file_head(file_path, max_lines=max_lines)
        if not lines:
            return FileValidityHint(status='unlikely_valid', reason='File appears to be empty.')

        non_empty = [line for line in lines if line.strip()]
        excerpt = '\n'.join(non_empty[:2])[:200]
        if not non_empty:
            return FileValidityHint(status='unlikely_valid', reason='No readable lines found in file header.')

        header_line = ''
        for line in non_empty:
            lowered = line.lower()
            if any(keyword in lowered for keyword in self.EXPECTED_KEYWORDS):
                header_line = line
                break
        if not header_line:
            header_line = non_empty[0]

        tokens = [token.strip().strip('"') for token in re.split('[;\t,]', header_line) if token.strip()]
        normalized = [token.lower() for token in tokens]
        matches = sum(1 for keyword in self.EXPECTED_KEYWORDS if any(keyword in token for token in normalized))

        if matches >= 4:
            return FileValidityHint(
                status='likely_valid',
                reason=f"Detected {matches} typical SVAN column markers.",
                header_excerpt=excerpt,
            )
        summary_text = '\n'.join(non_empty[:5]).lower()
        if matches >= 2 or 'svan' in summary_text or 'svantek' in summary_text:
            return FileValidityHint(
                status='needs_review',
                reason='Only a subset of SVAN markers detected in header.',
                header_excerpt=excerpt,
            )
        return FileValidityHint(
            status='needs_review',
            reason='Header did not resemble typical SVAN exports.',
            header_excerpt=excerpt,
        )

    def _get_data_profile_heuristic(self, lines: List[str], file_path: str) -> str:
        filename_upper = os.path.basename(file_path).upper()
        # Check for log files: _LOG.CSV or _LOG_*.CSV (e.g., _log_1s.csv, _log_10s.csv)
        if '_LOG.CSV' in filename_upper or '_LOG_' in filename_upper: return 'log'
        if '_SUMMARY.CSV' in filename_upper: return 'overview'
        for line in lines[:5]:
            if '(TH)' in line.upper(): return 'log'
            if '(SR)' in line.upper(): return 'overview'
        return 'unknown'

    def _clean_freq_suffix(self, freq_str_original: str) -> Optional[str]:
        freq_str = freq_str_original.replace(" ", "")
        match = self.FREQ_SUFFIX_PAT.match(freq_str)
        if match:
            num, k_suffix = match.groups()
            val = float(num)
            if k_suffix.lower() == 'k': val *= 1000
            return str(int(val)) if val == int(val) else str(val)

        if freq_str.replace('.', '', 1).isdigit():
            return freq_str
        if freq_str.lower().endswith('k') and freq_str[:-1].replace('.', '', 1).isdigit():
             val = float(freq_str[:-1]) * 1000
             return str(int(val)) if val == int(val) else str(val)
            
        return None

    def _map_svan_column(self, original_col: str) -> Tuple[Optional[str], Optional[str]]:
        cleaned = self.CLEAN_PAT.sub('', original_col)
        cleaned = cleaned.replace(' ', '_').replace('-', '_').replace('/', '_')
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')

        if 'Date_&_time' in cleaned or 'Start_date_&_time' in cleaned: return 'Datetime', 'datetime'

        bb_map = {
            "LAeq": r"^P\d_.*LAeq$", "LAFmax": r"^P\d_.*LAFmax$", "LAFmin": r"^P\d_.*LAFmin$",
            "LAF10": r"^P\d_.*LAeq_L10$", "LAF90": r"^P\d_.*LAeq_L90$",
            "LAeq_svan_overall": r"1/3_Oct_Leq_TOTAL_A" 
        }
        for can_name, pattern in bb_map.items():
            if re.fullmatch(pattern, cleaned, re.IGNORECASE):
                return "LAeq" if can_name == "LAeq_svan_overall" else can_name, 'totals'

        if "Oct" in cleaned:
            parts = cleaned.split('_')
            param_prefix = None
            for p in parts:
                if p.upper() in [prefix.upper() for prefix in self.standard_spectral_prefixes]:
                    param_prefix = p
                    break
            
            if not param_prefix:
                for p in parts:
                    if p.startswith('L') and len(p) > 1 and p[1].isalpha():
                        param_prefix = p
                        break
            
            if param_prefix:
                param_prefix = param_prefix.lower().replace("laf","LAF").replace("lzf","LZF").replace("lcf","LCF").replace("la","LA").replace("lc","LC").replace("lz","LZ")

                for p_val in reversed(parts):
                    cleaned_freq = self._clean_freq_suffix(p_val)
                    if cleaned_freq in self.expected_third_octave_suffixes:
                        return f"{param_prefix}_{cleaned_freq}", 'spectral'
        return None, None

    def parse(self, file_path: str, return_all_columns: bool = False) -> ParsedData:
        logger.info(f"SvanParser: Parsing {file_path}")
        parsed_data_obj = ParsedData(original_file_path=file_path, parser_type='Svan')
        try:
            # Handle Excel files separately
            if file_path.lower().endswith('.xlsx'):
                df_raw = pd.read_excel(file_path, header=None)
                # Find the header row by looking for 'Date & time'
                header_row_idx = -1
                for i, row in df_raw.iterrows():
                    if 'Date & time' in str(row.values):
                        header_row_idx = i
                        break
                if header_row_idx == -1: raise ValueError("Header 'Date & time' not found in Excel file.")
                
                df_excel = pd.read_excel(file_path, header=header_row_idx)
                # Clean up column names from Excel
                df_excel.columns = [str(c).replace('\n', ' ').strip() for c in df_excel.columns]
                sentry_map = {
                    'Date & time': 'Datetime', 'LAeq (TH) [dB]': 'LAeq', 'LAFmax (TH) [dB]': 'LAFmax',
                    'LAeq Histogram (SR) [dB] L10': 'LAF10', 'LAeq Histogram (SR) [dB] L90': 'LAF90'
                }
                df_excel = df_excel.rename(columns=sentry_map)
                df_renamed = self._normalize_datetime_column(df_excel, ['Datetime'])
                df_renamed = self._safe_convert_to_float(df_renamed)
                parsed_data_obj.sample_period_seconds = self._calculate_sample_period(df_renamed)
                parsed_data_obj.data_profile = 'overview'
                parsed_data_obj.spectral_data_type = 'none'
                available_cols = list(df_renamed.columns)
                parsed_data_obj.totals_df = self._filter_df_columns(df_renamed, 'totals', available_cols, return_all_columns)
                return parsed_data_obj

            # Continue with CSV parsing logic
            # First pass: find headers without loading entire file into memory
            h_indices = [-1,-1,-1]
            header_lines = []
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f):
                    if i < 100:  # Keep first 100 lines for profile heuristic
                        header_lines.append(line)
                    if 'date & time' in line.lower() or 'start date & time' in line.lower():
                        if i > 1:
                            h_indices = [i-2, i-1, i]
                            # Ensure we have the header lines
                            if len(header_lines) <= i:
                                # Need to re-read to get these lines
                                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f2:
                                    header_lines = [f2.readline() for _ in range(i+1)]
                            break
                    if i > 10000:  # Safety: don't search forever
                        break

            if not header_lines:
                parsed_data_obj.metadata['error'] = "File empty"; return parsed_data_obj

            parsed_data_obj.data_profile = self._get_data_profile_heuristic(header_lines, file_path)

            if h_indices[2] == -1:
                try:
                    simple_header_idx = -1
                    for i, line in enumerate(header_lines[:50]):
                        lowered = line.lower()
                        if 'start time' in lowered and 'laeq' in lowered:
                            simple_header_idx = i
                            break

                    if simple_header_idx != -1:
                        # Count non-blank lines before the header to adjust for pandas skipping blank lines by default
                        non_blank_count = sum(1 for i, line in enumerate(header_lines[:simple_header_idx]) if line.strip())
                        df_simple = pd.read_csv(
                            file_path,
                            header=non_blank_count,
                            sep=',',
                            na_filter=False,
                            on_bad_lines='warn',
                            low_memory=False,
                            encoding='utf-8',
                            encoding_errors='ignore'
                        )
                        df_simple = df_simple.replace('', np.nan).dropna(how='all')
                        if df_simple.empty:
                            parsed_data_obj.metadata['error'] = "No data rows"; return parsed_data_obj

                        rename_map = {}
                        for col in df_simple.columns:
                            col_str = str(col).strip()
                            lower = col_str.lower()
                            if lower == 'start time':
                                rename_map[col] = 'Datetime'
                            elif lower == 'la10':
                                rename_map[col] = 'LAF10'
                            elif lower == 'la90':
                                rename_map[col] = 'LAF90'
                            else:
                                rename_map[col] = col_str
                        df_simple = df_simple.rename(columns=rename_map)

                        if 'Datetime' not in df_simple.columns:
                            parsed_data_obj.metadata['error'] = "Datetime column not established"; return parsed_data_obj

                        df_simple = self._normalize_datetime_column(df_simple, dt_col_names=['Datetime'])
                        if df_simple.empty:
                            parsed_data_obj.metadata['error'] = "All rows failed Datetime"; return parsed_data_obj

                        df_simple = self._safe_convert_to_float(df_simple)
                        parsed_data_obj.sample_period_seconds = self._calculate_sample_period(df_simple)
                        parsed_data_obj.spectral_data_type = 'none'

                        available_cols = list(df_simple.columns)
                        parsed_data_obj.totals_df = self._filter_df_columns(df_simple, 'totals', available_cols, return_all_columns)
                        return parsed_data_obj
                except Exception as e:
                    logger.warning(f"Failed to parse simple SVAN log format for {file_path}: {e}")

                parsed_data_obj.metadata['error'] = "Svan datetime header not found"; return parsed_data_obj

            raw_headers = []
            temp_headers_parts = [pd.read_csv(StringIO(header_lines[idx]), header=None, dtype=str).iloc[0].fillna('').tolist() if idx >=0 and idx < len(header_lines) else [] for idx in h_indices]
            max_h_len = max(len(h) for h in temp_headers_parts) if temp_headers_parts else 0
            for i in range(max_h_len):
                parts = [h[i].strip() if i < len(h) else '' for h in temp_headers_parts]
                raw_headers.append(re.sub(r'_+', '_', "_".join(p for p in parts if p)).strip('_') or f"Unnamed_{i}")

            # Check trailing unnamed columns by sampling data rows
            while raw_headers and raw_headers[-1].startswith("Unnamed_"):
                col_idx_to_check = len(raw_headers) -1
                is_col_empty_in_data = True
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line_idx, line in enumerate(f):
                        if h_indices[2] < line_idx <= h_indices[2] + 10:
                            data_parts = line.strip().split(',')
                            if col_idx_to_check < len(data_parts) and data_parts[col_idx_to_check].strip():
                                is_col_empty_in_data = False
                                break
                        elif line_idx > h_indices[2] + 10:
                            break
                if is_col_empty_in_data: raw_headers.pop()
                else: break

            # Read CSV directly from file, skipping header rows
            df_full_raw = pd.read_csv(file_path, header=None, names=raw_headers, usecols=range(len(raw_headers)),
                                     sep=',', na_filter=False, on_bad_lines='warn', low_memory=False,
                                     skiprows=h_indices[2]+1, encoding='utf-8', encoding_errors='ignore')
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
                    while unique_can_name in canonical_map.values(): unique_can_name = f"{can_name}_{c}"; c+=1
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

            actual_spectral_type = 'none'
            if any("1/3 Oct" in col for col in df_full_raw.columns): actual_spectral_type = 'third_octave'
            elif any("1/1 Oct" in col for col in df_full_raw.columns): actual_spectral_type = 'octave'
                
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

    HEADER_MARKERS = (
        '# HARDWARE CONFIGURATION',
        '# MEASUREMENT SETUP',
        '# BROADBAND RESULTS',
        '# RTA RESULTS',
        '# RTA LOG RESULTS',
        '# BROADBAND LOG RESULTS',
        'SERIAL NUMBER',
        'NTI',
    )

    def inspect_file_header(self, file_path: str, max_lines: int = 40) -> FileValidityHint:
        lines = self._read_file_head(file_path, max_lines=max_lines)
        if not lines:
            return FileValidityHint(status='unlikely_valid', reason='File appears to be empty.')

        non_empty = [line for line in lines if line.strip()]
        excerpt = '\n'.join(non_empty[:4])[:200]
        if not non_empty:
            return FileValidityHint(status='unlikely_valid', reason='No readable lines found in file header.')

        upper_lines = [line.upper() for line in non_empty]
        matches = sum(1 for marker in self.HEADER_MARKERS if any(marker in line for line in upper_lines))

        if matches >= 3:
            return FileValidityHint(
                status='likely_valid',
                reason=f"Found {matches} NTi section markers in header.",
                header_excerpt=excerpt,
            )
        if matches >= 1:
            return FileValidityHint(
                status='needs_review',
                reason='Detected limited NTi markers; double-check file contents.',
                header_excerpt=excerpt,
            )
        return FileValidityHint(
            status='needs_review',
            reason='Header did not include recognizable NTi markers.',
            header_excerpt=excerpt,
        )

    def _extract_nti_metadata(self, lines: List[str]) -> Dict[str, Any]:
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

    def _get_nti_headers_and_data_start(self, table_lines: List[str], is_spectral: bool, content_lines: List[str], table_start_idx: int) -> Tuple[Optional[List[str]], int]:
        # --- NEW: Pass in original content_lines and table_start_idx to inspect section title ---

        # --- Use a dedicated path for non-spectral (broadband) files ---
        if not is_spectral:
            broadband_param_row_idx = -1
            # Find the first row that contains a standard broadband parameter. That's our header row.
            broadband_markers = ['LAeq', 'LAFmax', 'LAF10', 'LAF90', 'LCSmax', 'LCFmax', 'LZSmax', 'LZFmax']
            for i, line in enumerate(table_lines):
                if any(marker in line for marker in broadband_markers):
                    broadband_param_row_idx = i
                    break
            
            if broadband_param_row_idx == -1:
                logger.error("Could not identify any suitable header row for broadband file.")
                return None, -1

            header_row_parts = table_lines[broadband_param_row_idx].strip().split('\t')
            
            # Clean the headers for standardization
            final_headers = [h.replace('_dt', '').replace('.0%', '').strip() for h in header_row_parts]

            data_start_idx = broadband_param_row_idx + 1
            # Skip any empty lines or unit lines between header and data
            while data_start_idx < len(table_lines):
                line_content = table_lines[data_start_idx].strip()
                if not line_content or line_content.startswith('[') :
                    data_start_idx += 1
                else:
                    break # Found the first data line

            # Make headers unique to prevent pandas from mangling them
            seen = {}
            for i, h in enumerate(final_headers):
                if not h:
                    h = f"__EMPTY_{i}__"  # Handle empty header columns
                if h in seen:
                    seen[h] += 1
                    final_headers[i] = f"{h}_{seen[h]}"
                else:
                    seen[h] = 1
            
            logger.info(f"Using broadband header logic. Headers found: {len(final_headers)}")
            return final_headers, data_start_idx

        # --- MODIFIED SPECTRAL LOGIC ---

        # --- NEW: Logic for Format 2 (parameter in section title) ---
        section_title_line = content_lines[table_start_idx].strip()
        title_parts = section_title_line.split()
        # Check if the last part of the title is a parameter like 'LZeq_dt'
        if len(title_parts) > 3 and title_parts[-1].startswith('L'):
            param_from_title = title_parts[-1].replace('_dt', '')
            logger.info(f"Detected Format 2 RTA Log. Parameter from title: '{param_from_title}'")
            
            # Find the frequency band row
            band_row_idx = -1
            for i, line in enumerate(table_lines):
                if 'Band [Hz]' in line:
                    band_row_idx = i
                    break
            
            if band_row_idx != -1:
                header_parts = table_lines[band_row_idx].strip().split('\t')
                final_headers = []
                for part in header_parts:
                    part = part.strip()
                    if part.replace('.', '', 1).isdigit(): # Check if it's a frequency
                        freq = part.replace('.0', '')
                        final_headers.append(f"{param_from_title}_{freq}")
                    else: # It's a non-data column like 'Date', 'Time', etc.
                        final_headers.append(part)
                
                data_start_idx = band_row_idx + 1
                while data_start_idx < len(table_lines) and (not table_lines[data_start_idx].strip() or table_lines[data_start_idx].strip().startswith('[')):
                    data_start_idx += 1
                
                return final_headers, data_start_idx
            
        # --- ORIGINAL LOGIC (now a fallback for Format 1) ---
        logger.info("Did not find parameter in title, falling back to Format 1 RTA Log parsing.")
        unit_row_idx = -1
        for i, line in enumerate(table_lines):
            if '[dB]' in line:
                unit_row_idx = i
                break 

        if unit_row_idx == -1:
            logger.error("Could not identify the unit marker row ('[dB]') for spectral file.")
            return None, -1
        
        data_start_idx = unit_row_idx + 1
        while data_start_idx < len(table_lines) and not table_lines[data_start_idx].strip():
            data_start_idx += 1

        header_rows_raw = [line.strip('\n').split('\t') for line in table_lines[:unit_row_idx + 1]]

        max_len = 0
        if header_rows_raw:
            max_len = max(len(r) for r in header_rows_raw)
        if len(table_lines) > data_start_idx:
            first_data_row = table_lines[data_start_idx].strip('\n').split('\t')
            max_len = max(max_len, len(first_data_row))

        header_rows = [row + [''] * (max_len - len(row)) for row in header_rows_raw]
        unit_row_parts = header_rows[unit_row_idx]
        potential_header_parts = header_rows[:unit_row_idx]

        final_headers = []
        for i in range(max_len):
            is_data_col = unit_row_parts[i].strip() == '[dB]'
            col_names = [row[i].strip() for row in potential_header_parts]

            header = ''
            if is_data_col:
                param, freq = '', ''
                for name in col_names:
                    if name.replace('.', '', 1).isdigit():
                        freq = name.replace('.0', '')
                    elif name and not name.startswith('['):
                        param = name.replace('_dt', '').replace('.0%', '')
                if param and freq:
                    header = f"{param}_{freq}"
                elif param:
                    header = param
                else:
                    header = f"__UNKNOWN_DB_{i}__"
            else:
                base_names = [name for name in col_names if name and not name.startswith('[')]
                if base_names:
                    header = base_names[-1]
                else:
                    header = f"__EMPTY_{i}__"
            final_headers.append(header)

        seen = {}
        for i, h in enumerate(final_headers):
            if h in seen:
                seen[h] += 1
                final_headers[i] = f"{h}_{seen[h]}"
            else:
                seen[h] = 1
        return final_headers, data_start_idx

    def parse(self, file_path: str, return_all_columns: bool = False) -> ParsedData:
        logger.info(f"NTiParser: Parsing {file_path}")
        parsed_data_obj = ParsedData(original_file_path=file_path, parser_type='NTi')
        
        filename_lower = os.path.basename(file_path).lower()
        if "_report.txt" in filename_lower and "_rpt_" not in filename_lower:
            parsed_data_obj.metadata['error'] = "Single measurement report files are not currently supported."
            logger.warning(f"Skipping unsupported single measurement report: {file_path}")
            return parsed_data_obj

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f: lines = f.readlines()
            if not lines: parsed_data_obj.metadata['error'] = "File empty"; return parsed_data_obj

            checksum_idx = next((i for i, line in enumerate(lines) if "#CheckSum" in line), len(lines))
            content_lines = lines[:checksum_idx]
            if not content_lines: parsed_data_obj.metadata['error'] = "No content before checksum"; return parsed_data_obj
            
            parsed_data_obj.metadata.update(self._extract_nti_metadata(content_lines))
            
            is_log_file = "_log.txt" in filename_lower
            is_spectral = "_rta_" in filename_lower
            
            parsed_data_obj.data_profile = 'log' if is_log_file else 'overview'
            parsed_data_obj.spectral_data_type = 'third_octave' if is_spectral else 'none'

            data_start_marker = "# RTA LOG Results" if is_spectral and is_log_file else \
                                "# RTA Results" if is_spectral and not is_log_file else \
                                "# Broadband LOG Results" if not is_spectral and is_log_file else \
                                "# Broadband Results"

            table_start_idx = next((i for i, l in enumerate(content_lines) if l.strip().startswith(data_start_marker)), -1)
            if table_start_idx == -1:
                parsed_data_obj.metadata['error'] = f"Data marker '{data_start_marker}' not found"; return parsed_data_obj
            
            table_lines = [line for line in content_lines[table_start_idx + 1:] if line.strip()]
            if not table_lines: parsed_data_obj.metadata['error'] = "No data table found after marker"; return parsed_data_obj

            headers, data_start_row = self._get_nti_headers_and_data_start(table_lines, is_spectral, content_lines, table_start_idx)
            
            if not headers: parsed_data_obj.metadata['error'] = "Failed to construct headers from table"; return parsed_data_obj

            data_str = "".join(table_lines[data_start_row:])
            df_raw = pd.read_csv(StringIO(data_str), sep='\t', header=None, names=headers, on_bad_lines='warn', low_memory=False)

            cols_to_drop = [h for h in df_raw.columns if h.startswith('__') and df_raw[h].isnull().all()]
            df_raw = df_raw.drop(columns=cols_to_drop)

            if df_raw.empty: parsed_data_obj.metadata['error'] = "No data parsed from table"; return parsed_data_obj
            
            datetime_cols_in_raw = [c for c in ['Date', 'Time', 'Start Date', 'Start Time'] if c in df_raw.columns]
            if not datetime_cols_in_raw: parsed_data_obj.metadata['error']="Could not determine datetime columns"; return parsed_data_obj

            df_processed = self._normalize_datetime_column(df_raw.copy(), dt_col_names=datetime_cols_in_raw)
            if df_processed.empty: parsed_data_obj.metadata['error']="All rows failed Datetime parsing"; return parsed_data_obj
            
            df_processed = self._safe_convert_to_float(df_processed)
            parsed_data_obj.sample_period_seconds = self._calculate_sample_period(df_processed)
            
            rename_map = {}
            for col in df_processed.columns:
                for std_name in self.standard_output_columns:
                    if std_name.lower() == col.lower():
                        rename_map[col] = std_name
                        break
            df_processed = df_processed.rename(columns=rename_map)
            
            available_cols = list(df_processed.columns)
            
            # --- FINALIZED LOGIC ---
            # Use the is_spectral flag to cleanly separate file type handling.
            if is_spectral:
                # This is an RTA file. It ONLY produces a spectral_df.
                # The _filter_df_columns with 'spectral' will keep all valid spectral bands
                # and also any standard broadband metrics if they happen to be present.
                parsed_data_obj.spectral_df = self._filter_df_columns(df_processed, 'spectral', available_cols, return_all_columns)
                # The totals_df for an RTA file should be None.
                parsed_data_obj.totals_df = None
            else:
                # This is a non-spectral (_123_) file. It ONLY produces a totals_df.
                # The _filter_df_columns with 'totals' will pick out only the standard broadband columns.
                parsed_data_obj.totals_df = self._filter_df_columns(df_processed, 'totals', available_cols, return_all_columns)
                # The spectral_df for a broadband file should be None.
                parsed_data_obj.spectral_df = None

            return parsed_data_obj

        except FileNotFoundError:
            parsed_data_obj.metadata['error'] = "File not found"; return parsed_data_obj
        except Exception as e:
            parsed_data_obj.metadata['error'] = str(e)
            logger.error(f"NTiParser: Error parsing {file_path}: {e}", exc_info=True)
            return parsed_data_obj


class GenericFileParser(AbstractNoiseParser):
    """Generic parser for line-plot-only data sources.

    Requirements:
    - At least one datetime-like column (or Date + Time pair)
    - At least one numeric data column

    Output:
    - totals_df populated with Datetime + numeric columns
    - spectral_df remains None
    """

    _DATETIME_PRIORITY = [
        'datetime',
        'date_time',
        'timestamp',
        'time_stamp',
        'start datetime',
        'start date time',
        'start time',
    ]

    def inspect_file_header(self, file_path: str, max_lines: int = 20) -> FileValidityHint:
        lines = self._read_file_head(file_path, max_lines=max_lines)
        if not lines:
            return FileValidityHint(status='unlikely_valid', reason='File appears to be empty.')

        header_line = next((line for line in lines if line.strip()), '')
        lowered = header_line.lower()
        if any(token in lowered for token in ('date', 'time', 'timestamp')):
            return FileValidityHint(
                status='likely_valid',
                reason='Header contains datetime-related tokens.',
                header_excerpt=header_line[:200],
            )
        return FileValidityHint(
            status='needs_review',
            reason='Header does not clearly indicate datetime columns.',
            header_excerpt=header_line[:200],
        )

    def _read_tabular_file(self, file_path: str) -> pd.DataFrame:
        if file_path.lower().endswith(('.xlsx', '.xls')):
            return pd.read_excel(file_path)

        # First attempt: pandas delimiter inference.
        try:
            return pd.read_csv(
                file_path,
                sep=None,
                engine='python',
                on_bad_lines='warn',
                low_memory=False,
                encoding='utf-8',
                encoding_errors='ignore',
            )
        except Exception:
            pass

        # Fallback delimiters for unusual exports.
        for sep in [',', ';', '\t', '|']:
            try:
                return pd.read_csv(
                    file_path,
                    sep=sep,
                    on_bad_lines='warn',
                    low_memory=False,
                    encoding='utf-8',
                    encoding_errors='ignore',
                )
            except Exception:
                continue

        raise ValueError("Unable to parse file as a tabular dataset.")

    def _find_datetime_columns(self, df: pd.DataFrame) -> List[str]:
        if df.empty:
            return []

        col_map = {str(col).strip().lower(): col for col in df.columns}

        # Most explicit names first.
        for key in self._DATETIME_PRIORITY:
            if key in col_map:
                return [col_map[key]]

        # Explicit date + time combinations.
        if 'date' in col_map and 'time' in col_map:
            return [col_map['date'], col_map['time']]
        if 'start date' in col_map and 'start time' in col_map:
            return [col_map['start date'], col_map['start time']]

        # Fuzzy single-column matches.
        for key, original in col_map.items():
            if 'datetime' in key or 'timestamp' in key:
                return [original]
        for key, original in col_map.items():
            if key == 'time' or key.endswith(' time') or key.startswith('time '):
                return [original]

        # Final heuristic: first non-numeric column with strong datetime parse ratio.
        for col in df.columns:
            series = df[col]
            if pd.api.types.is_numeric_dtype(series):
                continue
            parsed = pd.to_datetime(series, errors='coerce', utc=True)
            valid_ratio = float(parsed.notna().mean()) if len(parsed) else 0.0
            if valid_ratio >= 0.8:
                return [col]

        return []

    def _normalize_datetime_utc(self, df: pd.DataFrame, dt_cols: List[str]) -> pd.DataFrame:
        if len(dt_cols) == 2:
            raw = df[dt_cols[0]].astype(str) + ' ' + df[dt_cols[1]].astype(str)
        else:
            raw = df[dt_cols[0]]

        parsed = pd.to_datetime(raw, errors='coerce', utc=True)
        df['Datetime'] = parsed

        for col in dt_cols:
            if col != 'Datetime' and col in df.columns:
                df = df.drop(columns=[col])

        df = df.dropna(subset=['Datetime'])
        if not df.empty:
            df = df.sort_values(by='Datetime').reset_index(drop=True)
        return df

    def parse(self, file_path: str, return_all_columns: bool = False) -> ParsedData:
        logger.info(f"GenericParser: Parsing {file_path}")
        parsed_data_obj = ParsedData(
            original_file_path=file_path,
            parser_type='Generic',
            spectral_data_type='none',
        )

        try:
            df_raw = self._read_tabular_file(file_path)
            if df_raw is None or df_raw.empty:
                parsed_data_obj.metadata['error'] = "No rows parsed from file."
                return parsed_data_obj

            df_raw = df_raw.replace('', np.nan).dropna(how='all')
            if df_raw.empty:
                parsed_data_obj.metadata['error'] = "No usable rows after removing empty rows."
                return parsed_data_obj

            dt_cols = self._find_datetime_columns(df_raw)
            if not dt_cols:
                parsed_data_obj.metadata['error'] = "No datetime column found. Expected Datetime/Timestamp or Date+Time."
                return parsed_data_obj

            df_processed = self._normalize_datetime_utc(df_raw.copy(), dt_cols)
            if df_processed.empty:
                parsed_data_obj.metadata['error'] = "All rows failed datetime parsing."
                return parsed_data_obj

            non_dt_cols = [col for col in df_processed.columns if col != 'Datetime']
            for col in non_dt_cols:
                df_processed[col] = pd.to_numeric(df_processed[col], errors='coerce')

            numeric_cols = [col for col in non_dt_cols if df_processed[col].notna().any()]
            if not numeric_cols:
                parsed_data_obj.metadata['error'] = "No numeric columns found to plot."
                return parsed_data_obj

            parsed_data_obj.totals_df = df_processed[['Datetime', *numeric_cols]].copy()
            parsed_data_obj.sample_period_seconds = self._calculate_sample_period(parsed_data_obj.totals_df)

            filename_lower = os.path.basename(file_path).lower()
            if 'summary' in filename_lower or 'overview' in filename_lower:
                parsed_data_obj.data_profile = 'overview'
            elif 'log' in filename_lower:
                parsed_data_obj.data_profile = 'log'
            elif parsed_data_obj.sample_period_seconds is not None and parsed_data_obj.sample_period_seconds > 60:
                parsed_data_obj.data_profile = 'overview'
            else:
                parsed_data_obj.data_profile = 'log'

            parsed_data_obj.metadata['numeric_columns'] = numeric_cols
            parsed_data_obj.metadata['return_all_columns_requested'] = bool(return_all_columns)
            return parsed_data_obj

        except FileNotFoundError:
            parsed_data_obj.metadata['error'] = "File not found"
            return parsed_data_obj
        except Exception as e:
            parsed_data_obj.metadata['error'] = str(e)
            logger.error(f"GenericParser: Error parsing {file_path}: {e}", exc_info=True)
            return parsed_data_obj


class AudioFileParser(AbstractNoiseParser):
    def _get_wav_duration(self, filepath: str) -> float:
        """Reads the duration in seconds from an audio file.

        Uses soundfile (libsndfile) when available to support more formats (WAV/FLAC/OGG, etc.).
        Falls back to Python's wave module for WAV files if soundfile is unavailable or fails.
        """
        # Preferred: soundfile
        if _HAS_SF:
            try:
                info = sf.info(filepath)
                if info.samplerate > 0:
                    return float(info.frames) / float(info.samplerate)
            except Exception as e:
                logger.debug(f"soundfile failed to read duration for {os.path.basename(filepath)}: {e}. Falling back to wave if possible.")
        # Fallback: wave (WAV only)
        try:
            with contextlib.closing(wave.open(filepath, 'r')) as f:
                frames = f.getnframes()
                rate = f.getframerate()
                return frames / float(rate) if rate > 0 else 0
        except (wave.Error, EOFError, FileNotFoundError) as e:
            logger.warning(f"Could not read duration from {os.path.basename(filepath)}: {e}. Defaulting to 0s.")
            return 0

    def parse(self, path: str, return_all_columns: bool = False) -> ParsedData:
        logger.info(f"AudioFileParser: Processing path {path}")
        parsed_data_obj = ParsedData(
            original_file_path=path, 
            parser_type='Audio',
            data_profile='file_list',
            spectral_data_type='none',
        )
        audio_files_details = []
        try:
            if not os.path.exists(path):
                parsed_data_obj.metadata['error'] = "Path does not exist"; return parsed_data_obj

            if os.path.isdir(path):
                parsed_data_obj.metadata['type'] = 'directory_scan'
                for item_name in os.listdir(path):
                    item_path = os.path.join(path, item_name)

                    is_svan = item_name.lower().startswith("r") and item_name.lower().endswith(".wav")
                    is_nti = "_audio_" in item_name.lower() and item_name.lower().endswith('.wav')
                    if os.path.isfile(item_path) and (is_svan or is_nti):
                        stats = os.stat(item_path)
                        duration = self._get_wav_duration(item_path)
                        if duration > 0:
                            audio_files_details.append({
                                'filename': item_name,
                                'full_path': item_path,
                                'size_mb': round(stats.st_size / (1024 * 1024), 2),
                                'modified_time': pd.to_datetime(stats.st_mtime, unit='s', utc=True).round('s'),
                                'Datetime': pd.to_datetime(stats.st_mtime, unit='s', utc=True).round('s'),
                                'duration_sec': duration
                            })
            else:
                parsed_data_obj.metadata['error'] = "Path is not a directory. Audio parser only scans directories."; return parsed_data_obj

            parsed_data_obj.metadata['audio_files_count'] = len(audio_files_details)
            
            if audio_files_details:
                df_audio_list = pd.DataFrame(audio_files_details)
                # This function will extract the numeric index from Svan (R##) or NTi (..._##) filenames
                def get_sort_key(filename):
                    # For Svan: R1, R2, R10 etc.
                    svan_match = re.search(r'^R(\d+)\.wav$', filename, re.IGNORECASE)
                    if svan_match:
                        return int(svan_match.group(1))
                    
                    # For NTi: ..._Audio_AGC_00.wav, ..._01.wav etc.
                    nti_match = re.search(r'_(\d+)\.wav$', filename, re.IGNORECASE)
                    if nti_match:
                        return int(nti_match.group(1))
                    
                    # Fallback for unknown formats
                    return filename

                df_audio_list['sort_key'] = df_audio_list['filename'].apply(get_sort_key)
                df_audio_list = df_audio_list.sort_values(by='sort_key').drop(columns=['sort_key'])
                
                parsed_data_obj.totals_df = df_audio_list.reset_index(drop=True)
            
            return parsed_data_obj
        except Exception as e:
            parsed_data_obj.metadata['error'] = str(e)
            logger.error(f"AudioFileParser: Error processing {path}: {e}", exc_info=True)
            return parsed_data_obj

class NoiseParserFactory:
    @staticmethod
    def get_parser(file_path: str, parser_type: str = 'auto') -> Optional[AbstractNoiseParser]:
        forced_type = (parser_type or 'auto').strip().lower().replace('_', '').replace('-', '')

        if forced_type not in ('', 'auto'):
            if forced_type in ('sentry', 'noisesentry'):
                return NoiseSentryFileParser()
            if forced_type in ('svan', 'svantek'):
                return SvanFileParser()
            if forced_type == 'nti':
                return NTiFileParser()
            if forced_type in ('audio', 'wav'):
                return AudioFileParser()
            if forced_type in ('generic', 'plotlinesonly', 'lineonly'):
                return GenericFileParser()

            logger.warning(f"Unknown forced parser type '{parser_type}' for {file_path}; falling back to auto detection.")

        filename_lower = os.path.basename(file_path).lower()
        
        # Audio directory check is now first and more specific
        if os.path.isdir(file_path):
             return AudioFileParser()

        # Individual WAV files (Svan or NTi audio files)
        if filename_lower.endswith('.wav'):
            # For individual WAV files, we'll use AudioFileParser on the parent directory
            # This allows the audio parser to scan the entire directory containing the WAV file
            parent_dir = os.path.dirname(file_path)
            if parent_dir and os.path.isdir(parent_dir):
                return AudioFileParser()
            else:
                logger.warning(f"WAV file found but parent directory invalid: {file_path}")
                return None

        # NTi files have very specific naming conventions
        if '_report.txt' in filename_lower or '_log.txt' in filename_lower:
            if "_rta_" in filename_lower or "_123_" in filename_lower:
                return NTiFileParser()

        # Svan or Noise Sentry
        if filename_lower.endswith(('.csv','.svl')) or "overview.xlsx" in filename_lower :
            if re.search(r'_\d{4}_\d{2}_\d{2}__\d{2}h\d{2}m\d{2}s.*\.csv$', filename_lower):
                return NoiseSentryFileParser()
            return SvanFileParser()
             
        logger.warning(f"Could not determine parser type for: {file_path}")
        return None

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # --- Noise Sentry Example ---
    sentry_file_path = r"G:\My Drive\Programing\example files\Noise Sentry\cricket nets 2A _2025_06_03__20h55m22s_2025_05_29__15h30m00s.csv"   
    print(f"\n--- Testing NoiseSentryParser on {os.path.basename(sentry_file_path)} ---")
    sentry_parser = NoiseParserFactory.get_parser(sentry_file_path)
    if sentry_parser:
        sentry_data = sentry_parser.parse(sentry_file_path)
        print("Sentry Metadata:", sentry_data.metadata)
        print("Sentry Data Profile:", sentry_data.data_profile)
        print("Sentry Sample Period:", sentry_data.sample_period_seconds)
        if sentry_data.totals_df is not None: print("Sentry Totals DF Head:\n", sentry_data.totals_df.head())

    # --- Svan Log Example ---
    svan_log_path = r"G:\My Drive\Programing\example files\Svan full data\L259_log.csv"
    print(f"\n--- Testing SvanFileParser on {os.path.basename(svan_log_path)} (Log File) ---")
    svan_parser = NoiseParserFactory.get_parser(svan_log_path)
    if svan_parser:
        svan_data = svan_parser.parse(svan_log_path)
        print("Svan Metadata:", svan_data.metadata)
        print("Svan Data Profile:", svan_data.data_profile)
        print("Svan Spectral Type:", svan_data.spectral_data_type)
        print("Svan Sample Period:", svan_data.sample_period_seconds)
        if svan_data.totals_df is not None: print("Svan Totals DF Head:\n", svan_data.totals_df.head(2))
        if svan_data.spectral_df is not None: print("Svan Spectral DF Head:\n", svan_data.spectral_df.head(2))

    # --- Svan Summary Example ---
    svan_summary_path = r"G:\My Drive\Programing\example files\Svan full data\L259_summary.csv"
    print(f"\n--- Testing SvanFileParser on {os.path.basename(svan_summary_path)} (Summary File) ---")
    svan_parser = NoiseParserFactory.get_parser(svan_summary_path)
    if svan_parser:
        svan_data = svan_parser.parse(svan_summary_path)
        print("Svan Metadata:", svan_data.metadata)
        print("Svan Data Profile:", svan_data.data_profile)
        print("Svan Spectral Type:", svan_data.spectral_data_type)
        print("Svan Sample Period:", svan_data.sample_period_seconds)
        if svan_data.totals_df is not None: print("Svan Totals DF Head:\n", svan_data.totals_df.head(2))
        if svan_data.spectral_df is not None: print("Svan Spectral DF Head:\n", svan_data.spectral_df.head(2))

    # --- NTi Test Files ---
    nti_files_to_test = [
        r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_123_Log.txt",
        r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_123_Rpt_Report.txt",
        r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Log.txt",
        r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Rpt_Report.txt",
        r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_123_Report.txt",
        r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Report.txt"
    ]

    for nti_path in nti_files_to_test:
        print(f"\n--- Testing NTiFileParser on {os.path.basename(nti_path)} ---")
        nti_parser = NoiseParserFactory.get_parser(nti_path)
        if nti_parser:
            nti_data = nti_parser.parse(nti_path)
            print("NTi Metadata:", nti_data.metadata)
            print("NTi Data Profile:", nti_data.data_profile)
            print("NTi Spectral Type:", nti_data.spectral_data_type)
            print("NTi Sample Period:", nti_data.sample_period_seconds)
            if nti_data.totals_df is not None and not nti_data.totals_df.empty: 
                print("NTi Totals DF Head:\n", nti_data.totals_df.head(2))
            if nti_data.spectral_df is not None and not nti_data.spectral_df.empty:
                print("NTi Spectral DF Head:\n", nti_data.spectral_df.head(2))
        else:
            print(f"No parser found for {os.path.basename(nti_path)}")
