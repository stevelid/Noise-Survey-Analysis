""" data_manager.py"""

import os
import pandas as pd
import numpy as np
import copy
from collections import defaultdict, Counter
import logging
import time
from typing import List, Dict, Optional, Any, Set, Union, Tuple, Callable

# Assuming your refactored parsers are in a file named 'data_parsers_refactored.py'
# in the same directory or a properly configured package.
try:
    from .data_parsers import NoiseParserFactory, ParsedData, AbstractNoiseParser
    from .parsed_data_cache import get_parsed_data_cache
except ImportError: # Fallback for running script directly
    from data_parsers import NoiseParserFactory, ParsedData, AbstractNoiseParser
    from parsed_data_cache import get_parsed_data_cache


logger = logging.getLogger(__name__)

from noise_survey_analysis.core import status_console


# ==============================================================================
#  Helper Functions
# ==============================================================================

# --- Gap-break detection for merged totals series ---------------------------
# When multiple source files are merged into one position's totals series
# (e.g. several Svan/Svantek spot-measurement segments, or an NTi log split
# across multiple files), we insert a NaN "break" row wherever consecutive
# timestamps in the fully time-sorted series are not a plausible continuation
# of one another. "Plausible continuation" means the gap between them is
# close to the position's expected sample period for that series (i.e. the
# next point lands where the very next regular sample would fall) -
# genuinely contiguous multi-file logs satisfy this and stay unbroken, while
# separate recordings (meter stopped/restarted between spot checks, or a
# real deployment gap) do not, and get a visible break instead of an
# interpolated line across unmeasured time.
#
# This is computed on the fully merged + time-sorted DataFrame (not
# incrementally as files arrive), so it is independent of the order files
# happen to be processed in - config/file-discovery order is not guaranteed
# to be chronological (e.g. mtime-based directory scans).
_GAP_TOLERANCE_FRACTION = 0.10   # allowed deviation from the expected period, as a fraction of it
_GAP_TOLERANCE_FLOOR_SECONDS = 5.0  # absolute floor so very fine (e.g. 1 Hz) periods still get a sane tolerance
_GAP_DEFAULT_PERIOD_SECONDS = 60.0  # fallback "expected period" when no period info is known yet
_GAP_MARKER_OFFSET = pd.Timedelta(milliseconds=1)  # marker placed just after the last real point before a gap

def _parse_single_file(file_path: str, position_name: str,
                       parser_type_hint: Optional[str] = None,
                       return_all_columns: bool = False,
                       timezone: Optional[str] = None,
                       use_cache: bool = True) -> Tuple[str, str, ParsedData]:
    """
    Worker function to parse a single file.

    Returns:
        Tuple of (file_path, position_name, parsed_data)
    """
    try:
        # Check cache first
        if use_cache:
            cache = get_parsed_data_cache()
            if timezone is None:
                cached_data = cache.get(file_path, return_all_columns)
            else:
                cached_data = cache.get(file_path, return_all_columns, timezone=timezone)
            if cached_data is not None:
                logger.debug(f"Using cached data for: {os.path.basename(file_path)}")
                return (file_path, position_name, cached_data)

        # Parse the file
        factory = NoiseParserFactory()
        parser = factory.get_parser(
            file_path,
            parser_type=parser_type_hint or 'auto',
            timezone=timezone,
        )

        if not parser:
            err_msg = f"No suitable parser found for file: {file_path}"
            logger.error(err_msg)
            error_data = ParsedData(
                original_file_path=file_path,
                parser_type='None',
                metadata={'error': err_msg}
            )
            return (file_path, position_name, error_data)

        parsed_data = parser.parse(file_path, return_all_columns=return_all_columns)

        # Record the resolved timezone so callers can inspect it
        if parsed_data is not None and parsed_data.metadata is not None:
            parsed_data.metadata.setdefault('timezone', getattr(parser, 'timezone', None))

        # Cache the result
        if use_cache and 'error' not in parsed_data.metadata:
            cache = get_parsed_data_cache()
            cache.put(file_path, parsed_data, return_all_columns, timezone=parser.timezone)

        return (file_path, position_name, parsed_data)

    except Exception as e:
        logger.error(f"Error parsing {file_path}: {e}", exc_info=True)
        error_data = ParsedData(
            original_file_path=file_path,
            parser_type='Error',
            metadata={'error': str(e)}
        )
        return (file_path, position_name, error_data)


# ==============================================================================
#  1. The Data Holder Class for a Single Position
# ==============================================================================
class PositionData:
    """
    A container for all data associated with a single measurement position.
    This class provides convenient `.has_overview` style accessors and stores
    standardized metadata.
    """
    def __init__(self, name: str):
        self.name: str = name
        # Standardized data holders
        self.overview_totals: Optional[pd.DataFrame] = None
        self.overview_spectral: Optional[pd.DataFrame] = None
        self.log_totals: Optional[pd.DataFrame] = None
        self.log_spectral: Optional[pd.DataFrame] = None
        self.audio_files_list: Optional[pd.DataFrame] = None # For list of audio files
        self.audio_files_path: Optional[str] = None # For path to audio files
        self.y_axis_label: Optional[str] = None
        self.y_range: Optional[List[float]] = None
        
        # Lazy loading: store file paths for on-demand loading
        self.log_file_paths: List[Dict[str, Any]] = []  # List of {file_path, parser_type, return_all_cols}
        self._log_data_loaded: bool = False  # Track if log data has been loaded

        # Store combined metadata from all contributing files for this position
        self.source_file_metadata: Optional[List[Dict[str, Any]]] = []
        # Key overall metadata for the position (derived from sources)
        self.parser_types_used: Optional[Set[str]] = set()
        self.sample_periods_seconds: Optional[Set[Optional[float]]] = set()
        self.spectral_data_types_present: Optional[Set[str]] = set()

        # Gap-break tracking for the totals (line-chart) series only - see
        # module-level comment above _GAP_TOLERANCE_FRACTION. Keyed by
        # 'overview' / 'log'; each value is the list of per-file sample
        # periods (seconds) seen so far for that series, used to derive a
        # stable "expected period" reference regardless of file arrival order.
        self._gap_known_periods: Dict[str, List[float]] = {}


    def __repr__(self) -> str:
        overview_shape = self.overview_totals.shape if self.has_overview_totals else "None"
        log_shape = self.log_totals.shape if self.has_log_totals else "None"
        spectral_log_shape = self.log_spectral.shape if self.has_log_spectral else "None"
        return (f"<PositionData: {self.name} | Overview: {overview_shape}, Log: {log_shape}, "
                f"SpectralLog: {spectral_log_shape}>")

    def __getitem__(self, key: str) -> Optional[pd.DataFrame]:
        """
        Allows dictionary-style access to data attributes.
        e.g., position_data['overview_totals']
        """
        if key == 'overview_totals':
            return self.overview_totals
        elif key == 'overview_spectral':
            return self.overview_spectral
        elif key == 'log_totals':
            return self.log_totals
        elif key == 'log_spectral':
            return self.log_spectral
        elif key == 'audio_files_list':
            return self.audio_files_list
        elif key == 'audio_files_path':
            return self.audio_files_path
        else:
            raise KeyError(f"'{key}' is not a valid data attribute for PositionData. "
                           f"Valid keys are: 'overview_totals', 'overview_spectral', "
                           f"'log_totals', 'log_spectral', 'audio_files_list'.")

    # --- Boolean properties for easy checking ---
    @property
    def has_overview_totals(self) -> bool:
        return self.overview_totals is not None and not self.overview_totals.empty
    @property
    def has_overview_spectral(self) -> bool:
        return self.overview_spectral is not None and not self.overview_spectral.empty
    @property
    def has_log_totals(self) -> bool:
        return self.log_totals is not None and not self.log_totals.empty
    @property
    def has_log_spectral(self) -> bool:
        return self.log_spectral is not None and not self.log_spectral.empty
    @property
    def has_audio_files(self) -> bool:
        return self.audio_files_list is not None and not self.audio_files_list.empty
    @property
    def has_audio(self) -> bool:
        return self.has_audio_files
    @property
    def has_spectral_data(self) -> bool:
        return self.has_overview_spectral or self.has_log_spectral

    def _merge_df(self, existing_df: Optional[pd.DataFrame], new_df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """Helper to concatenate and de-duplicate DataFrames by Datetime."""
        if new_df is None or new_df.empty:
            return existing_df
        if existing_df is None or existing_df.empty:
            return new_df

        logger.debug(f"Merging new data into existing DataFrame for position {self.name}.")
        # Ensure both have Datetime column for merging
        if 'Datetime' not in existing_df.columns or 'Datetime' not in new_df.columns:
            logger.warning("Cannot merge DataFrames without a 'Datetime' column.")
            return existing_df # Return original

        try:
            # Combine, sort by datetime, and remove duplicates, keeping the first entry
            combined_df = pd.concat([existing_df, new_df], ignore_index=True)
            combined_df = combined_df.sort_values(by='Datetime', ascending=True)
            combined_df = combined_df.drop_duplicates(subset=['Datetime'], keep='first')
            return combined_df.reset_index(drop=True)
        except Exception as e:
            logger.error(f"Error merging DataFrames for {self.name}: {e}")
            return existing_df # Return original on error

    @staticmethod
    def _strip_gap_marker_rows(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """Remove previously-inserted gap-marker rows (Datetime set, every other
        column NaN) so gap detection can be recomputed cleanly from scratch."""
        if df is None or df.empty:
            return df
        data_cols = [c for c in df.columns if c != 'Datetime']
        if not data_cols:
            return df
        is_marker = df[data_cols].isna().all(axis=1)
        if not bool(is_marker.any()):
            return df
        return df.loc[~is_marker].reset_index(drop=True)

    def _insert_gap_break_rows(self, df: Optional[pd.DataFrame], profile_key: str) -> Optional[pd.DataFrame]:
        """
        Scan a fully time-sorted totals DataFrame and insert a NaN-valued
        marker row wherever a consecutive gap deviates materially from the
        series' expected sample period - see module-level comment above
        _GAP_TOLERANCE_FRACTION. Bokeh's line glyph breaks at NaN values, so
        the plotted line shows a visible gap there instead of interpolating
        straight across unmeasured time.
        """
        if df is None or df.empty or len(df) < 2 or 'Datetime' not in df.columns:
            return df

        periods = self._gap_known_periods.get(profile_key) or []
        if periods:
            # A position's meter/period setting is normally constant across
            # its contributing files; the mode is robust to the occasional
            # short/truncated final period of a file.
            period_ref = Counter(periods).most_common(1)[0][0]
        else:
            period_ref = _GAP_DEFAULT_PERIOD_SECONDS
        if not period_ref or period_ref <= 0:
            period_ref = _GAP_DEFAULT_PERIOD_SECONDS
        tolerance = max(period_ref * _GAP_TOLERANCE_FRACTION, _GAP_TOLERANCE_FLOOR_SECONDS)

        try:
            dt = df['Datetime']
            diffs_seconds = dt.diff().dt.total_seconds().to_numpy()
            gap_mask = (diffs_seconds > 0) & (np.abs(diffs_seconds - period_ref) > tolerance)
            gap_positions = np.flatnonzero(gap_mask)
            if gap_positions.size == 0:
                return df

            marker_times = (dt.iloc[gap_positions - 1] + _GAP_MARKER_OFFSET).reset_index(drop=True)
            marker_df = pd.DataFrame({'Datetime': marker_times})
            combined = pd.concat([df, marker_df], ignore_index=True, sort=False)
            combined = combined.sort_values(by='Datetime').reset_index(drop=True)
            logger.debug(
                "Inserted %d gap-break marker(s) for %s [%s] (expected period=%.1fs, tolerance=%.1fs)",
                gap_positions.size, self.name, profile_key, period_ref, tolerance,
            )
            return combined
        except Exception as e:
            logger.error(f"Error inserting gap-break rows for {self.name} [{profile_key}]: {e}")
            return df

    def _merge_totals_with_gap_break(
        self,
        profile_key: str,
        existing_df: Optional[pd.DataFrame],
        new_df: Optional[pd.DataFrame],
        new_period_seconds: Optional[float],
    ) -> Optional[pd.DataFrame]:
        """
        Like _merge_df, but for a position's totals (line-chart) series only:
        merges the new file's data in, then recomputes gap-break marker rows
        across the whole (now time-sorted) series so genuinely separate
        recordings (meter stopped/restarted between spot checks, a real
        deployment gap) show a visible break rather than an interpolated
        line, while files that genuinely abut (e.g. NTi's own multi-file
        hourly log rollovers) stay connected.

        profile_key: 'overview' or 'log' - tracked separately since each has
            its own expected sample period.
        """
        if new_df is None or new_df.empty:
            return existing_df

        if new_period_seconds:
            self._gap_known_periods.setdefault(profile_key, []).append(new_period_seconds)

        existing_clean = self._strip_gap_marker_rows(existing_df)
        merged = self._merge_df(existing_clean, new_df)
        return self._insert_gap_break_rows(merged, profile_key)

    def _apply_source_options(
        self,
        parsed_data_obj: ParsedData,
        selected_columns: Optional[List[str]] = None,
        forced_profile: Optional[str] = None,
    ) -> ParsedData:
        """Apply source-level display options from the config after parsing."""
        if forced_profile:
            parsed_data_obj.data_profile = forced_profile

        if not selected_columns:
            return parsed_data_obj

        requested = [col for col in selected_columns if col and col != 'Datetime']

        def filter_columns(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
            if df is None or df.empty or 'Datetime' not in df.columns:
                return df
            available = [col for col in requested if col in df.columns]
            missing = [col for col in requested if col not in df.columns]
            if missing:
                logger.warning(
                    "Selected columns missing for %s: %s",
                    parsed_data_obj.original_file_path,
                    missing,
                )
            if not available:
                return df[['Datetime']].copy()
            return df[['Datetime', *available]].copy()

        parsed_data_obj.totals_df = filter_columns(parsed_data_obj.totals_df)
        parsed_data_obj.metadata['selected_columns'] = requested
        return parsed_data_obj

    def add_parsed_file_data(self, parsed_data_obj: ParsedData):
        """
        Adds data from a single parsed file (ParsedData object) to this position.
        """
        if not isinstance(parsed_data_obj, ParsedData):
            logger.warning(f"Invalid data type passed to add_parsed_file_data for {self.name}")
            return

        # Store this file's specific metadata #NOTE: this is not quite right as this should be per file, not per position.
        # however, we dont want more depth when accessing the data and this data may not be used by the app
        file_meta = {
            'original_file_path': parsed_data_obj.original_file_path,
            'parser_type': parsed_data_obj.parser_type,
            'data_profile': parsed_data_obj.data_profile,
            'spectral_data_type': parsed_data_obj.spectral_data_type,
            'sample_period_seconds': parsed_data_obj.sample_period_seconds,
            'parser_specific_details': parsed_data_obj.metadata # The raw dict from parser
        }
        self.source_file_metadata.append(file_meta)

        # Update aggregated metadata for the position
        if parsed_data_obj.parser_type: self.parser_types_used.add(parsed_data_obj.parser_type)
        if parsed_data_obj.sample_period_seconds is not None: self.sample_periods_seconds.add(parsed_data_obj.sample_period_seconds)
        if parsed_data_obj.spectral_data_type and parsed_data_obj.spectral_data_type != 'none':
            self.spectral_data_types_present.add(parsed_data_obj.spectral_data_type)

        # Distribute DataFrames based on data_profile
        profile = parsed_data_obj.data_profile

        logger.debug(f"Adding data from {os.path.basename(parsed_data_obj.original_file_path)} to {self.name}")
        logger.debug(f"  ParsedData profile: {parsed_data_obj.data_profile}, parser_type: {parsed_data_obj.parser_type}")
        logger.debug(f"  ParsedData totals_df shape: {parsed_data_obj.totals_df.shape if parsed_data_obj.totals_df is not None else 'None'}")
        logger.debug(f"  ParsedData spectral_df shape: {parsed_data_obj.spectral_df.shape if parsed_data_obj.spectral_df is not None else 'None'}")
        if parsed_data_obj.totals_df is not None:
            logger.debug(f"  totals_df columns: {list(parsed_data_obj.totals_df.columns)[:10]}")
            logger.debug(f"  totals_df has 'Datetime' column: {'Datetime' in parsed_data_obj.totals_df.columns}")
        if parsed_data_obj.spectral_df is not None:
            logger.debug(f"  spectral_df columns: {list(parsed_data_obj.spectral_df.columns)[:10]}")
            logger.debug(f"  spectral_df has 'Datetime' column: {'Datetime' in parsed_data_obj.spectral_df.columns}")

        if profile == 'overview': # Typically summary reports
            if parsed_data_obj.totals_df is not None:
                self.overview_totals = self._merge_totals_with_gap_break(
                    'overview', self.overview_totals, parsed_data_obj.totals_df,
                    parsed_data_obj.sample_period_seconds,
                )
            logger.debug(f"  After merge - overview_totals shape: {self.overview_totals.shape if self.overview_totals is not None else 'None'}")
            if self.overview_totals is not None:
                logger.debug(f"  overview_totals has 'Datetime' column: {'Datetime' in self.overview_totals.columns}")

            if parsed_data_obj.spectral_df is not None:
                self.overview_spectral = self._merge_df(self.overview_spectral, parsed_data_obj.spectral_df)
            logger.debug(f"  After merge - overview_spectral shape: {self.overview_spectral.shape if self.overview_spectral is not None else 'None'}")

        elif profile == 'log': # Typically time-history logs
            if parsed_data_obj.totals_df is not None:
                self.log_totals = self._merge_totals_with_gap_break(
                    'log', self.log_totals, parsed_data_obj.totals_df,
                    parsed_data_obj.sample_period_seconds,
                )
            logger.debug(f"  After merge - log_totals shape: {self.log_totals.shape if self.log_totals is not None else 'None'}")
            if self.log_totals is not None:
                logger.debug(f"  log_totals has 'Datetime' column: {'Datetime' in self.log_totals.columns}")

            if parsed_data_obj.spectral_df is not None:
                self.log_spectral = self._merge_df(self.log_spectral, parsed_data_obj.spectral_df)
            logger.debug(f"  After merge - log_spectral shape: {self.log_spectral.shape if self.log_spectral is not None else 'None'}")

        elif profile == 'file_list' and parsed_data_obj.parser_type == 'Audio': # Audio parser result
            # Set the path for the audio handler to use later
            if self.audio_files_path is None:
                self.audio_files_path = parsed_data_obj.original_file_path      
            # Audio parser puts file list into totals_df                
            if self.audio_files_list is None:
                self.audio_files_list = parsed_data_obj.totals_df
            elif parsed_data_obj.totals_df is not None:
                self.audio_files_list = pd.concat([self.audio_files_list, parsed_data_obj.totals_df], ignore_index=True)
                if 'full_path' in self.audio_files_list.columns:
                    self.audio_files_list = self.audio_files_list.drop_duplicates(subset=['full_path']).reset_index(drop=True)
        elif parsed_data_obj.totals_df is not None or parsed_data_obj.spectral_df is not None:
            # Fallback for unknown profiles, try to merge into log if data exists
            logger.warning(f"Unknown data_profile '{profile}' for {parsed_data_obj.original_file_path}. "
                           "Attempting to merge into log attributes.")
            if parsed_data_obj.totals_df is not None:
                self.log_totals = self._merge_df(self.log_totals, parsed_data_obj.totals_df)

            if parsed_data_obj.spectral_df is not None:
                self.log_spectral = self._merge_df(self.log_spectral, parsed_data_obj.spectral_df)

    def load_log_data_lazy(self, parser_factory, use_cache: bool = True) -> bool:
        """
        Load log data on-demand from stored file paths.
        This is called by ServerDataHandler when streaming is first triggered.
        Preserves the exact same data format as the old eager loading approach.

        Returns:
            True if at least one file was loaded, False if every file failed. Callers
            use this to decide whether the position can be retried later - a network
            share that was unavailable may come back, and a position that silently
            reported success could never recover.

        Partial success counts as loaded: usable data beats none, and re-running would
        re-parse the files that did work. The failures are logged individually and
        summarized, so a missing file is visible rather than silent.
        """
        if self._log_data_loaded:
            logger.debug(f"Log data already loaded for {self.name}, skipping lazy load")
            return True

        if not self.log_file_paths:
            logger.debug(f"No log file paths stored for {self.name}, nothing to load")
            return False

        loaded_files: List[str] = []
        failed_files: List[str] = []

        logger.info(f"[LAZY LOAD] Loading log data for {self.name} from {len(self.log_file_paths)} file(s)")
        _first_name = os.path.basename(str(self.log_file_paths[0].get('file_path', '?')))
        _extra = f" +{len(self.log_file_paths) - 1} more" if len(self.log_file_paths) > 1 else ""
        try:
            _mb = sum(
                os.path.getsize(str(f.get('file_path', '')))
                for f in self.log_file_paths
                if os.path.exists(str(f.get('file_path', '')))
            ) / (1024 * 1024)
            _size = f", {_mb:,.0f} MB" if _mb >= 1 else ""
        except OSError:
            _size = ""
        status_console.start_phase(
            'load',
            f"{self.name}: first log load, parsing {_first_name}{_extra}{_size}",
        )
        load_started_at = time.perf_counter()
        total_parse_ms = 0.0
        total_merge_ms = 0.0
        total_cache_lookup_ms = 0.0
        total_parser_lookup_ms = 0.0
        total_cache_put_ms = 0.0
        cache_hits = 0
        cache_misses = 0
        cache = get_parsed_data_cache() if use_cache else None
        
        for file_info in self.log_file_paths:
            file_path = file_info['file_path']
            parser_type = file_info.get('parser_type')
            return_all_cols = file_info.get('return_all_cols', False)
            timezone = file_info.get('timezone')
            selected_columns = file_info.get('selected_columns')
            forced_profile = file_info.get('data_profile')
            
            try:
                file_started_at = time.perf_counter()
                cache_lookup_ms = 0.0
                parser_lookup_ms = 0.0
                parse_ms = 0.0
                merge_ms = 0.0
                cache_put_ms = 0.0
                cache_label = 'disabled'
                parsed_data = None

                if cache is not None:
                    cache_lookup_started_at = time.perf_counter()
                    if timezone is None:
                        parsed_data = cache.get(file_path, return_all_cols)
                    else:
                        parsed_data = cache.get(file_path, return_all_cols, timezone=timezone)
                    cache_lookup_ms = (time.perf_counter() - cache_lookup_started_at) * 1000
                    total_cache_lookup_ms += cache_lookup_ms
                    if parsed_data is not None:
                        cache_hits += 1
                        cache_label = 'hit'
                    else:
                        cache_misses += 1
                        cache_label = 'miss'

                if parsed_data is not None:
                    parsed_data = copy.deepcopy(parsed_data)
                    merge_started_at = time.perf_counter()
                    parsed_data = self._apply_source_options(parsed_data, selected_columns, forced_profile)
                    self.add_parsed_file_data(parsed_data)
                    merge_ms = (time.perf_counter() - merge_started_at) * 1000
                    total_merge_ms += merge_ms
                    logger.info(
                        "[LAZY LOAD PERF] position=%s file=%s cache=%s cache_lookup_ms=%.1f merge_ms=%.1f total_ms=%.1f",
                        self.name,
                        os.path.basename(file_path),
                        cache_label,
                        cache_lookup_ms,
                        merge_ms,
                        (time.perf_counter() - file_started_at) * 1000,
                    )
                    logger.debug(f"[LAZY LOAD] Loaded {file_path} for {self.name} (cache hit)")
                    loaded_files.append(file_path)
                    continue

                parser_lookup_started_at = time.perf_counter()
                parser = parser_factory.get_parser(
                    file_path,
                    parser_type=parser_type or 'auto',
                    timezone=timezone,
                )
                parser_lookup_ms = (time.perf_counter() - parser_lookup_started_at) * 1000
                total_parser_lookup_ms += parser_lookup_ms
                if not parser:
                    logger.warning(f"[LAZY LOAD] No suitable parser for {file_path}")
                    failed_files.append(file_path)
                    continue

                parse_started_at = time.perf_counter()
                parsed_data = parser.parse(file_path, return_all_columns=return_all_cols)
                parse_ms = (time.perf_counter() - parse_started_at) * 1000
                total_parse_ms += parse_ms
                
                if parsed_data:
                    if cache is not None and 'error' not in parsed_data.metadata:
                        cache_put_started_at = time.perf_counter()
                        cache.put(file_path, parsed_data, return_all_cols, timezone=parser.timezone)
                        cache_put_ms = (time.perf_counter() - cache_put_started_at) * 1000
                        total_cache_put_ms += cache_put_ms

                    merge_started_at = time.perf_counter()
                    parsed_data = self._apply_source_options(parsed_data, selected_columns, forced_profile)
                    self.add_parsed_file_data(parsed_data)
                    merge_ms = (time.perf_counter() - merge_started_at) * 1000
                    total_merge_ms += merge_ms

                    logger.info(
                        "[LAZY LOAD PERF] position=%s file=%s cache=%s cache_lookup_ms=%.1f parser_lookup_ms=%.1f parse_ms=%.1f merge_ms=%.1f cache_put_ms=%.1f total_ms=%.1f",
                        self.name,
                        os.path.basename(file_path),
                        cache_label,
                        cache_lookup_ms,
                        parser_lookup_ms,
                        parse_ms,
                        merge_ms,
                        cache_put_ms,
                        (time.perf_counter() - file_started_at) * 1000,
                    )
                    logger.debug(f"[LAZY LOAD] Loaded {file_path} for {self.name}")
                    loaded_files.append(file_path)
                else:
                    logger.warning(f"[LAZY LOAD] Failed to parse {file_path}")
                    failed_files.append(file_path)

            except Exception as e:
                logger.error(f"[LAZY LOAD] Error loading {file_path}: {e}")
                failed_files.append(file_path)

        if not loaded_files:
            # Every file failed. Leave _log_data_loaded unset so the position stays
            # eligible for a retry once whatever broke - an unmounted share, a locked
            # file - is fixed.
            logger.error(
                "[LAZY LOAD] No log files could be loaded for %s (%s attempted); "
                "leaving the position unloaded so it can be retried",
                self.name,
                len(failed_files),
            )
            status_console.end_phase(
                f"{self.name}: log load failed ({len(failed_files)} file(s))",
                category='warn',
            )
            return False

        if failed_files:
            logger.warning(
                "[LAZY LOAD] Partial load for %s: %s of %s file(s) failed (%s). "
                "Continuing with the data that loaded.",
                self.name,
                len(failed_files),
                len(self.log_file_paths),
                ', '.join(os.path.basename(path) for path in failed_files),
            )

        self._log_data_loaded = True
        rows = len(self.log_totals) if self.log_totals is not None else 0
        spectral = " + spectra" if self.has_log_spectral else ""
        span = ""
        if self.log_totals is not None and 'Datetime' in self.log_totals.columns and rows:
            try:
                span = (f", {self.log_totals['Datetime'].iloc[0]:%d/%m %H:%M}"
                        f"->{self.log_totals['Datetime'].iloc[-1]:%d/%m %H:%M}")
            except Exception:
                span = ""
        source = "from cache" if cache_misses == 0 else f"parsed {cache_misses} file(s)"
        status_console.end_phase(
            f"{self.name}: log ready, {rows:,} rows{spectral}{span} ({source})",
            category='ok',
        )
        logger.info(
            "[LAZY LOAD PERF] position=%s files=%s cache_hits=%s cache_misses=%s cache_lookup_ms=%.1f parser_lookup_ms=%.1f parse_ms=%.1f merge_ms=%.1f cache_put_ms=%.1f total_ms=%.1f",
            self.name,
            len(self.log_file_paths),
            cache_hits,
            cache_misses,
            total_cache_lookup_ms,
            total_parser_lookup_ms,
            total_parse_ms,
            total_merge_ms,
            total_cache_put_ms,
            (time.perf_counter() - load_started_at) * 1000,
        )
        logger.debug(f"[LAZY LOAD] Completed for {self.name}. Log totals: {self.log_totals.shape if self.log_totals is not None else 'None'}, Log spectral: {self.log_spectral.shape if self.log_spectral is not None else 'None'}")
        return True


# ==============================================================================
#  2. The Main Data Orchestrator Class
# ==============================================================================
class DataManager:
    """
    Manages loading, parsing, and accessing all survey data.
    Acts as the primary interface for retrieving noise data.
    """
    def __init__(self, source_configurations: Optional[List[Dict[str, Any]]] = None,
                 use_cache: bool = True,
                 progress_callback: Optional[Callable[[int, int], None]] = None):
        """
        Initialize DataManager.

        Args:
            source_configurations: List of source configuration dictionaries
            use_cache: If True, use file-level caching to avoid re-parsing (default: True)
            progress_callback: Optional callback function(completed, total) for progress updates
        """
        self._positions_data: Dict[str, PositionData] = {}
        self._position_order: List[str] = []  # Preserve order from config file
        self.parser_factory = NoiseParserFactory() # Uses your refactored factory
        self.use_cache = use_cache
        self.progress_callback = progress_callback

        if source_configurations:
            self.load_from_configs(source_configurations)

    def load_from_configs(self, source_configs: List[Dict[str, Any]],
                          return_all_columns_override: Optional[bool] = None):
        """
        Loads and processes data from a list of configuration dictionaries.
        Each dictionary should define a 'position_name' and either
        'file_path' (str) or 'file_paths' (Set[str] or List[str]).
        """
        # Build a list of all file parsing tasks
        parse_tasks: List[Tuple[str, str, bool, Optional[str], Dict[str, Any]]] = []  # (file_path, position_name, return_all_cols, parser_hint, options)

        for config in source_configs:
            if not config.get("enabled", True): # Default to enabled if not specified
                logger.debug(f"Skipping disabled source config: {config.get('position_name', 'N/A')}")
                continue

            position_name = config.get("position_name")
            if not position_name:
                logger.warning(f"Skipping source config with no 'position_name': {config}")
                continue

            # Ensure position exists in our data structure
            if position_name not in self._positions_data:
                self._positions_data[position_name] = PositionData(name=position_name)
                if position_name not in self._position_order:
                    self._position_order.append(position_name)

            # Determine how 'return_all_columns' is set for this source
            use_return_all_cols = config.get('return_all_columns', False) # Default from config
            if return_all_columns_override is not None:
                use_return_all_cols = return_all_columns_override # Global override

            file_paths_to_process: List[str] = []
            if "file_path" in config and isinstance(config["file_path"], str):
                file_paths_to_process.append(config["file_path"])
            elif "file_paths" in config and isinstance(config["file_paths"], (list, set)):
                file_paths_to_process.extend(list(config["file_paths"]))

            if not file_paths_to_process:
                logger.warning(f"No valid 'file_path' or 'file_paths' found for position '{position_name}'. Config: {config}")
                continue

            for path in file_paths_to_process:
                parser_hint = config.get("parser_type_hint") or config.get("parser_type")
                source_options = {
                    'selected_columns': config.get('selected_columns') or config.get('columns'),
                    'data_profile': config.get('data_profile') or config.get('profile'),
                    'y_axis_label': config.get('y_axis_label'),
                    'y_range': config.get('y_range'),
                    'timezone': config.get('timezone'),
                }
                parse_tasks.append((path, position_name, use_return_all_cols, parser_hint, source_options))

        # Process files sequentially
        if not parse_tasks:
            logger.warning("No files to process")
            return

        self._load_files_sequential(parse_tasks)

    def _load_files_sequential(self, parse_tasks: List[Tuple[str, str, bool, Optional[str], Dict[str, Any]]]):
        """Load files sequentially."""
        total = len(parse_tasks)
        for idx, (file_path, position_name, return_all_cols, parser_hint, source_options) in enumerate(parse_tasks, 1):
            self.add_source_file(file_path, position_name,
                                parser_type_hint=parser_hint,
                                return_all_columns=return_all_cols,
                                selected_columns=source_options.get('selected_columns'),
                                data_profile=source_options.get('data_profile'),
                                y_axis_label=source_options.get('y_axis_label'),
                                y_range=source_options.get('y_range'),
                                timezone=source_options.get('timezone'))
            if self.progress_callback:
                self.progress_callback(idx, total)

    def add_source_file(self, file_path: str, position_name: str,
                        parser_type_hint: Optional[str] = None,
                        return_all_columns: bool = False,
                        skip_log_files: bool = True,
                        selected_columns: Optional[List[str]] = None,
                        data_profile: Optional[str] = None,
                        y_axis_label: Optional[str] = None,
                        y_range: Optional[List[float]] = None,
                        timezone: Optional[str] = None):
        """
        Parses a single file and adds its data to the specified position.
        This method is used for sequential processing and backwards compatibility.
        
        Args:
            skip_log_files: If True, log files are not loaded immediately. Instead, their paths
                           are stored for lazy loading. This speeds up initial dashboard load.
        """
        logger.debug(f"DataManager: Processing '{file_path}' for position '{position_name}' (AllCols: {return_all_columns}).")

        if position_name not in self._positions_data:
            self._positions_data[position_name] = PositionData(name=position_name)
            # Preserve the order from config file
            if position_name not in self._position_order:
                self._position_order.append(position_name)

        position_obj = self._positions_data[position_name]
        if y_axis_label:
            position_obj.y_axis_label = y_axis_label
        if y_range is not None:
            position_obj.y_range = y_range

        # Check if this is a log file by quick heuristic (before parsing)
        # Log files typically have "_log" in filename or are large CSV/TXT files
        # Summary files (_summary) are always loaded eagerly regardless of size
        filename_lower = os.path.basename(file_path).lower()
        is_summary_file = '_summary' in filename_lower
        is_report_file = '_rpt_report' in filename_lower or filename_lower.endswith('_report.txt')
        is_likely_log_file = not is_summary_file and (
            (not is_report_file and '_log' in filename_lower) or
            'log_' in filename_lower or
            (
                not is_report_file and
                filename_lower.endswith(('.csv', '.txt')) and
                os.path.getsize(file_path) > 1_000_000
            )  # > 1MB
        )
        
        if skip_log_files and is_likely_log_file:
            # Store file path for lazy loading instead of parsing now
            logger.debug(f"[LAZY LOAD] Deferring log file: {os.path.basename(file_path)}")
            position_obj.log_file_paths.append({
                'file_path': file_path,
                'parser_type': parser_type_hint,
                'return_all_cols': return_all_columns,
                'timezone': timezone,
                'selected_columns': selected_columns,
                'data_profile': data_profile,
            })
            return

        # Try cache first if enabled
        parsed_data_obj = None
        if self.use_cache:
            cache = get_parsed_data_cache()
            if timezone is None:
                parsed_data_obj = cache.get(file_path, return_all_columns)
            else:
                parsed_data_obj = cache.get(file_path, return_all_columns, timezone=timezone)
            if parsed_data_obj is not None:
                logger.debug(f"Using cached data for: {os.path.basename(file_path)}")
                parsed_data_obj = copy.deepcopy(parsed_data_obj)
                parsed_data_obj = position_obj._apply_source_options(parsed_data_obj, selected_columns, data_profile)
                position_obj.add_parsed_file_data(parsed_data_obj)
                return

        parser = self.parser_factory.get_parser(
            file_path,
            parser_type=parser_type_hint or 'auto',
            timezone=timezone,
        )
        if not parser:
            err_msg = f"No suitable parser found for file: {file_path}"
            logger.error(err_msg)
            # Store error info in the PositionData's source metadata
            position_obj.source_file_metadata.append({
                'original_file_path': file_path, 'error': err_msg,
                'parser_type': 'None', 'data_profile': 'error',
                'spectral_data_type': 'none', 'sample_period_seconds': None
            })
            return

        try:
            parsed_data_obj = parser.parse(file_path, return_all_columns=return_all_columns)

            # Cache the result if enabled and no errors
            if self.use_cache and 'error' not in parsed_data_obj.metadata:
                cache = get_parsed_data_cache()
                cache.put(file_path, parsed_data_obj, return_all_columns, timezone=parser.timezone)

            parsed_data_obj = position_obj._apply_source_options(parsed_data_obj, selected_columns, data_profile)
            position_obj.add_parsed_file_data(parsed_data_obj)

            logger.debug(f"Successfully processed and added data from '{file_path}' to '{position_name}'.")
        except Exception as e:
            err_msg = f"Critical error parsing file {file_path} with {parser.__class__.__name__}: {e}"
            logger.error(err_msg, exc_info=True)
            position_obj.source_file_metadata.append({
                'original_file_path': file_path, 'error': err_msg,
                'parser_type': parser.__class__.__name__, 'data_profile': 'error',
                'spectral_data_type': 'none', 'sample_period_seconds': None
            })

    # --- Methods for clean access ---
    def positions(self) -> List[str]:
        """Returns a list of all loaded position names in config file order."""
        # Return positions in the order they were defined in the config file
        # Include any positions that might exist but aren't in the order list (fallback)
        ordered_positions = [pos for pos in self._position_order if pos in self._positions_data]
        remaining_positions = [pos for pos in self._positions_data.keys() if pos not in self._position_order]
        return ordered_positions + sorted(remaining_positions)

    def __getitem__(self, position_name: str) -> PositionData:
        """
        Enables dictionary-style access, e.g., `data_manager['SW']`.
        """
        if position_name not in self._positions_data:
            # Option: Create an empty PositionData on demand if you prefer not to raise KeyError
            # logger.warning(f"Position '{position_name}' not found. Creating an empty one.")
            # self._positions_data[position_name] = PositionData(name=position_name)
            raise KeyError(f"Position '{position_name}' not found in DataManager.")
        return self._positions_data[position_name]

    def __contains__(self, position_name: str) -> bool:
        """Allows `in` operator, e.g., `if 'SW' in data_manager:`"""
        return position_name in self._positions_data

    def __iter__(self):
        """Allows iterating directly over the manager, yielding PositionData objects."""
        return iter(self._positions_data.values())

    def __len__(self) -> int:
        """Returns the number of positions loaded."""
        return len(self._positions_data)

    def get_all_position_data(self):
        """Returns a dictionary of all loaded positions."""
        return self._positions_data
    
    def examine_all_positions(self, max_files_to_detail=3):
        """Prints a summary of all loaded positions and their data."""
        if not self._positions_data:
            print("DataManager contains no loaded positions.")
            return

        print("\n=== DataManager: Examination of All Loaded Positions ===")
        for pos_name in self.positions():
            all_pos_data = self._positions_data[pos_name]
            print(f"\n=== {pos_name} ===")
            for type in ['overview_totals', 'overview_spectral', 'log_totals', 'log_spectral', 'audio_files_list']:
                
                if hasattr(all_pos_data, type) and getattr(all_pos_data, type) is not None:
                    print(f"\n--- {type} ---")
                    pos_data = getattr(all_pos_data, type)
                    if type == 'audio_files_list':
                        print(f"  Count: {len(pos_data)}")
                        for i, file in enumerate(pos_data):
                            print(f"    - File: {file}")
                        continue
                    else:
                        print(f"  {pos_data.head()}")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    
    sentry_file_path = r"G:\My Drive\Programing\example files\Noise Sentry\cricket nets 2A _2025_06_03__20h55m22s_2025_05_29__15h30m00s.csv"   

    svan_log_path = r"G:\My Drive\Programing\example files\Svan full data\L259_log.csv"
    svan_summary_path = r"G:\My Drive\Programing\example files\Svan full data\L259_summary.csv"

    nti_rta_log_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Log.txt"
    nti_123_log_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_00_123_Log.txt"
    nti_123_Rpt_Report_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_00_123_Rpt_Report.txt"
    nti_RTA_Rpt_Report_path = r"G:\My Drive\Programing\example files\Nti\2025-06-02_SLM_000_RTA_3rd_Rpt_Report.txt"

    audio_dir = r"G:\Shared drives\Venta\Jobs\5793 Alton Road, Ross-on-wye\5793 Surveys\5793-1"

    sources_config = [
        {"position_name": "SiteSvan", "file_paths": {svan_log_path, svan_summary_path}, "enabled": True}, # Use set for file_paths
        {"position_name": "SiteNTi", "file_paths": {nti_rta_log_path, nti_123_log_path}, "parser_type_hint": "NTi"},
        {"position_name": "SiteNti", "file_path": audio_dir, "enabled": True},
        {"position_name": "SiteMissing", "file_path": "nonexistent.csv", "enabled": True}
    ]

    data_manager = DataManager(source_configurations=sources_config)
    
    # Add another file post-initialization
    data_manager.add_source_file(nti_123_Rpt_Report_path, "SiteNTi")
    data_manager.add_source_file(nti_RTA_Rpt_Report_path, "SiteNTi")
    data_manager.add_source_file(sentry_file_path, "SiteSentry")


    print("\n--- FINAL DATA MANAGER STATE ---")
    data_manager.examine_all_positions()

    print("\n--- Accessing Data Example ---")
    if "SiteSvan" in data_manager:
        svan_pos_data = data_manager["SiteSvan"]
        if svan_pos_data.has_log_totals:
            print("\nSiteSvan Log Totals DF:")
            print(svan_pos_data.log_totals)
        if svan_pos_data.has_overview_spectral: # Svan summary puts spectral into overview_spectral
            print("\nSiteSvan Overview Spectral DF:")
            print(svan_pos_data.overview_spectral)
    
    if data_manager["SiteNTi"].has_log_totals:
            print("\nSiteNTi Log Totals (all columns due to config):")
            print(data_manager["SiteNTi"].log_totals)
            print("\nSiteNTi Files List:")
            print(data_manager["SiteNTi"].audio_files_list)

    if data_manager["SiteSentry"]:
        print("\nSiteSentry Files List:")
        print(data_manager["SiteSentry"].overview_totals)

    
    
