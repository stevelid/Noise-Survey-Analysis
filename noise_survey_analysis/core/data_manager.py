""" data_manager.py"""

import os
import pandas as pd
from collections import defaultdict # Not strictly needed with current PositionData, but good for other aggregations
import logging
from typing import List, Dict, Optional, Any, Set, Union # Added Union

# Assuming your refactored parsers are in a file named 'data_parsers_refactored.py'
# in the same directory or a properly configured package.
try:
    from .data_parsers import NoiseParserFactory, ParsedData, AbstractNoiseParser
except ImportError: # Fallback for running script directly
    from data_parsers import NoiseParserFactory, ParsedData, AbstractNoiseParser


logger = logging.getLogger(__name__)

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

        # Store combined metadata from all contributing files for this position
        self.source_file_metadata: Optional[List[Dict[str, Any]]] = []
        # Key overall metadata for the position (derived from sources)
        self.parser_types_used: Optional[Set[str]] = set()
        self.sample_periods_seconds: Optional[Set[Optional[float]]] = set()
        self.spectral_data_types_present: Optional[Set[str]] = set()


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

        logger.info(f"Merging new data into existing DataFrame for position {self.name}.")
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

        if profile == 'overview': # Typically summary reports
            if parsed_data_obj.totals_df is not None:
                self.overview_totals = self._merge_df(self.overview_totals, parsed_data_obj.totals_df)
            logger.debug(f"  After merge - overview_totals shape: {self.overview_totals.shape if self.overview_totals is not None else 'None'}")

            if parsed_data_obj.spectral_df is not None:
                self.overview_spectral = self._merge_df(self.overview_spectral, parsed_data_obj.spectral_df)
            logger.debug(f"  After merge - overview_spectral shape: {self.overview_spectral.shape if self.overview_spectral is not None else 'None'}")

        elif profile == 'log': # Typically time-history logs
            if parsed_data_obj.totals_df is not None:
                self.log_totals = self._merge_df(self.log_totals, parsed_data_obj.totals_df)
            logger.debug(f"  After merge - log_totals shape: {self.log_totals.shape if self.log_totals is not None else 'None'}")

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


# ==============================================================================
#  2. The Main Data Orchestrator Class
# ==============================================================================
class DataManager:
    """
    Manages loading, parsing, and accessing all survey data.
    Acts as the primary interface for retrieving noise data.
    """
    def __init__(self, source_configurations: Optional[List[Dict[str, Any]]] = None):
        self._positions_data: Dict[str, PositionData] = {}
        self._position_order: List[str] = []  # Preserve order from config file
        self.parser_factory = NoiseParserFactory() # Uses your refactored factory

        if source_configurations:
            self.load_from_configs(source_configurations)

    def load_from_configs(self, source_configs: List[Dict[str, Any]], 
                          return_all_columns_override: Optional[bool] = None):
        """
        Loads and processes data from a list of configuration dictionaries.
        Each dictionary should define a 'position_name' and either
        'file_path' (str) or 'file_paths' (Set[str] or List[str]).
        """
        for config in source_configs:
            if not config.get("enabled", True): # Default to enabled if not specified
                logger.info(f"Skipping disabled source config: {config.get('position_name', 'N/A')}")
                continue
            
            position_name = config.get("position_name")
            if not position_name:
                logger.warning(f"Skipping source config with no 'position_name': {config}")
                continue

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
                self.add_source_file(path, position_name,
                                     parser_type_hint=config.get("parser_type_hint"),
                                     return_all_columns=use_return_all_cols)

    def add_source_file(self, file_path: str, position_name: str, 
                        parser_type_hint: Optional[str] = None,
                        return_all_columns: bool = False):
        """
        Parses a single file and adds its data to the specified position.
        """
        logger.info(f"DataManager: Processing '{file_path}' for position '{position_name}' (AllCols: {return_all_columns}).")
        
        if position_name not in self._positions_data:
            self._positions_data[position_name] = PositionData(name=position_name)
            # Preserve the order from config file
            if position_name not in self._position_order:
                self._position_order.append(position_name)
        
        position_obj = self._positions_data[position_name]

        parser = self.parser_factory.get_parser(file_path) # Factory can use hint if we modify it
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
            position_obj.add_parsed_file_data(parsed_data_obj)
            logger.info(f"Successfully processed and added data from '{file_path}' to '{position_name}'.")
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

    
    
