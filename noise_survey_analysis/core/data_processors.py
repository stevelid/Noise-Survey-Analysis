import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Optional, Set, Tuple, Any
import math

# Assuming PositionData is defined elsewhere and imported (e.g., from data_manager)
import sys
from pathlib import Path
current_file = Path(__file__)
project_root = current_file.parent.parent.parent  # Go up to "Noise Survey Analysis"
sys.path.insert(0, str(project_root))

from noise_survey_analysis.core.config import CHART_SETTINGS, VISUALIZATION_SETTINGS
from noise_survey_analysis.core.data_manager import PositionData

logger = logging.getLogger(__name__)


def downsample_dataframe_max(df: pd.DataFrame, target_points: int) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if target_points <= 0:
        return df
    if 'Datetime' not in df.columns:
        logger.warning("Cannot downsample DataFrame without 'Datetime' column.")
        return df

    if not pd.api.types.is_datetime64_any_dtype(df['Datetime']):
        df = df.copy()
        df.loc[:, 'Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')
        df.dropna(subset=['Datetime'], inplace=True)

    if df.empty or len(df) <= target_points:
        return df

    df_sorted = df.sort_values(by='Datetime')
    time_start = df_sorted['Datetime'].iloc[0]
    time_end = df_sorted['Datetime'].iloc[-1]
    total_ms = (time_end - time_start).total_seconds() * 1000
    if total_ms <= 0:
        return df_sorted.head(target_points)

    interval_ms = max(1, math.ceil(total_ms / target_points))
    resample_interval = pd.to_timedelta(interval_ms, unit='ms')
    resampled = (
        df_sorted.set_index('Datetime')
        .resample(resample_interval)
        .max()
        .dropna(how='all')
        .reset_index()
    )
    return resampled


class GlyphDataProcessor:
    """
    A class dedicated to transforming DataFrames into specific data structures
    required by Bokeh glyphs, such as the Image glyph for spectrograms.
    """

    def prepare_all_spectral_data(self, position_data_obj: PositionData,
                                  chart_settings: Optional[Dict] = None,
                                  log_target_points: Optional[int] = None) -> Dict[str, Dict[str, Any]]:
        """
        Processes all available spectral data (overview and log) for a single position.

        Args:
            position_data_obj: An instance of the PositionData class.
            chart_settings: A dictionary of chart settings. Uses defaults if None.

        Returns:
            A nested dictionary structured for potential JavaScript front-end or component use, e.g.:
            {
                'overview': {
                    'available_params': ['LZeq', 'LZFmax'],
                    'prepared_params': {
                        'LZeq': { ... spectrogram data for LZeq ... },
                        'LZFmax': { ... spectrogram data for LZFmax ... }
                    }
                },
                'log': {
                    'available_params': ['LZeq'],
                    'prepared_params': {
                        'LZeq': { ... spectrogram data for LZeq ... }
                    }
                }
            }
            Returns an empty dict if no spectral data is processable.
        """
        if chart_settings is None:
            chart_settings = CHART_SETTINGS.copy()

        final_prepared_data: Dict[str, Dict[str, Any]] = {}
        logger.info(f"Processor: Preparing all spectral data for position '{position_data_obj.name}'")
        
        # Process overview spectral data
        if position_data_obj.has_overview_spectral:
            df = position_data_obj.overview_spectral
            params = self._extract_spectral_parameters(df)
            if params:
                prepared_params_dict = {}
                for param in params:
                    prepared_data = self.prepare_single_spectrogram_data(df, param, chart_settings)
                    if prepared_data:
                        prepared_params_dict[param] = prepared_data
                if prepared_params_dict: # Only add if some params were successfully processed
                    final_prepared_data['overview'] = {
                        'available_params': params,
                        'prepared_params': prepared_params_dict
                    }
        else:
            logger.debug(f"No overview_spectral data for {position_data_obj.name}")


        # Process log spectral data
        if position_data_obj.has_log_spectral:
            df = position_data_obj.log_spectral
            params = self._extract_spectral_parameters(df)
            if params:
                prepared_params_dict = {}
                for param in params:
                    if log_target_points:
                        prepared_data = self.prepare_downsampled_spectral_data(
                            df, param, chart_settings, log_target_points
                        )
                    else:
                        prepared_data = self.prepare_single_spectrogram_data(df, param, chart_settings)
                    if prepared_data:
                        prepared_params_dict[param] = prepared_data
                if prepared_params_dict:
                    final_prepared_data['log'] = {
                        'available_params': params,
                        'prepared_params': prepared_params_dict
                    }
        else:
            logger.debug(f"No log_spectral data for {position_data_obj.name}")
        
        return final_prepared_data

    
    def prepare_single_spectrogram_data(self, df: pd.DataFrame, param_prefix: str, 
                                        chart_settings: Dict) -> Optional[Dict[str, Any]]:
        """
        Process spectral data from a DataFrame for a single parameter into the format
        needed for Bokeh image spectrogram visualization. If the size of the data is larger than a 
        set limit, we will chunk the data client side. Here we will set up the initial source to the correct size. 

        Args:
            df (pd.DataFrame): DataFrame with frequency data. Must contain 'Datetime'.
            param_prefix (str): Base parameter name (e.g., 'LZeq', 'LAFmax').
            chart_settings (dict): Configuration for chart appearance.
        
        Returns:
            dict: A dictionary containing all chunked processed data needed for visualization, or None if processing fails.
        """
        logger.debug(f"Preparing single spectrogram data for parameter: {param_prefix} from DF shape {df.shape}")
        
        MAX_DATA_SIZE = 95000 # this should be (MAX_SPECTRAL_POINTS_TO_RENDER from app.js  + buffer) * num_freqs # TODO: Make this a config parameter
        n_freqs = 0 # Initialize n_freqs

        if df is None or df.empty:
            logger.warning(f"Empty DataFrame provided for spectral data preparation: {param_prefix}")
            return None
            
        if 'Datetime' not in df.columns:
            logger.error(f"Missing 'Datetime' column for spectral data preparation: {param_prefix}")
            return None
            
        # Ensure Datetime is actually datetime type
        if not pd.api.types.is_datetime64_any_dtype(df['Datetime']):
            # Make a copy to avoid SettingWithCopyWarning if df is a slice
            df = df.copy() 
            df.loc[:, 'Datetime'] = pd.to_datetime(df['Datetime'], errors='coerce')
            df.dropna(subset=['Datetime'], inplace=True)
            if df.empty:
                logger.warning("No valid dates after conversion in spectral data")
                return None
        
        # --- Find and Sort Frequency Columns for the given parameter_prefix ---
        freq_cols_found: List[str] = []
        all_frequencies_numeric: List[float] = []

        for col in df.columns:
            if col.startswith(param_prefix + '_'):
                # Extract frequency part after the LAST underscore
                freq_str_part = col.split('_')[-1] 
                try:
                    # Attempt to convert to float (handles "8", "12.5", "1000")
                    # Suffixes like 'k' or 'Hz' should have been normalized by the parser
                    # to match EXPECTED_THIRD_OCTAVE_SUFFIXES (which are numeric strings)
                    freq_numeric = float(freq_str_part)
                    freq_cols_found.append(col)
                    all_frequencies_numeric.append(freq_numeric)
                except ValueError:
                    logger.debug(f"Could not parse frequency from column suffix '{freq_str_part}' in '{col}' for param '{param_prefix}'. Skipping.")
                    continue
        
        if not freq_cols_found:
            logger.warning(f"No frequency columns found for parameter '{param_prefix}' in the provided DataFrame.")
            return None
        
        # Sort by numeric frequency
        sorted_indices = np.argsort(all_frequencies_numeric)
        frequencies_numeric_sorted = np.array(all_frequencies_numeric)[sorted_indices]
        freq_columns_sorted = np.array(freq_cols_found)[sorted_indices]
        
        # --- Apply Hz-Based Frequency Filtering ---
        min_hz, max_hz = chart_settings.get('data_prep_freq_range_hz', [20, 20000])
        
        # Find the indices of the frequencies that fall within our desired master range.
        valid_indices = np.where((frequencies_numeric_sorted >= min_hz) & (frequencies_numeric_sorted <= max_hz))[0]
        
        if valid_indices.size == 0:
            logger.warning(f"No frequencies found in the configured range {min_hz}-{max_hz} Hz for param '{param_prefix}'.")
            return None

        # Slice the arrays to get the final set of data we will send to the browser.
        selected_frequencies = frequencies_numeric_sorted[valid_indices]
        selected_freq_columns = freq_columns_sorted[valid_indices]
        
        n_freqs = len(selected_frequencies)
        frequency_labels_str = [(str(int(f)) if f.is_integer() else f"{f:.1f}") + " Hz" for f in selected_frequencies]
        
        # --- Prepare Data for `image` Glyph ---
        # Ensure Datetime is sorted before creating levels_matrix and times_dt
        df_sorted = df.sort_values(by='Datetime')
        levels_matrix = df_sorted[selected_freq_columns].values  # Shape: (n_times, n_freqs)
        times_dt = df_sorted['Datetime'].values # Already pandas Timestamps or numpy datetime64
        n_times = len(times_dt)
        
        if n_times == 0:
            logger.warning(f"No time points for spectral data parameter: {param_prefix}")
            return None
        
        times_ms = pd.to_datetime(times_dt).astype('int64') // 10**6 # Bokeh image x-coords
        freq_indices = np.arange(n_freqs) # Bokeh image y-coords (categorical)
        
        valid_levels = levels_matrix[~pd.isna(levels_matrix) & np.isfinite(levels_matrix)]
        if len(valid_levels) > 0:
            min_val = np.min(valid_levels)
            max_val = np.max(valid_levels)
        else:
            min_val, max_val = 0, 100 # Default if all NaNs or infinite
        
        nan_replace_val = min_val + chart_settings.get('nan_replace_offset', -20)
        
        # Replace NaNs for visualization; ensure it's float for np.nan_to_num
        levels_matrix_clean = np.nan_to_num(levels_matrix.astype(float), nan=nan_replace_val, posinf=max_val+10, neginf=min_val-10)

        #round to integer
        levels_matrix_clean = np.round(levels_matrix_clean).astype(np.int16)

        levels_transposed = levels_matrix_clean.T
        

        #get the correct size for the first chunk. If data is smaller than MAX_DATA_SIZE, this will be the full data.
        chunk_time_length = math.ceil(MAX_DATA_SIZE / n_freqs) #TODO: set the max value to the smaller of MAX_DATA_SIZE and the size of the overview spectrogram (avoid padding out the overview)

        #pad the data
        pad_width = 0
        if n_times < chunk_time_length:
            pad_width = chunk_time_length - n_times
        elif n_times % chunk_time_length != 0:
            pad_width = chunk_time_length - (n_times % chunk_time_length)
        
        max_time = times_ms[-1] if n_times > 0 else 0
        min_time = times_ms[0] if n_times > 0 else 0
        
        if pad_width > 0:
            # Pad the transposed matrix along the time axis (axis=1)
            levels_transposed_padded = np.pad(levels_transposed, ((0, 0), (0, pad_width)), 'constant', constant_values=nan_replace_val)
            # Pad the time array
            last_time_val = times_ms[-1] if n_times > 0 else 0
            times_ms_padded = np.pad(times_ms, (0, pad_width), 'constant', constant_values=last_time_val)
        else:
            levels_transposed_padded = levels_transposed
            times_ms_padded = times_ms
        
        
        final_n_times = len(times_ms_padded)

        # Flatten the padded, transposed matrix into a 1D array. This is the exact format Bokeh will use for the glyph's data buffer.
        levels_flat_transposed = levels_transposed_padded.flatten()
        
        first_data_chunk = levels_transposed_padded[:, :chunk_time_length]

        time_step = (times_ms_padded[10] - times_ms_padded[5]) / 5 if final_n_times > 10 else (times_ms_padded[1] - times_ms_padded[0] if final_n_times > 1 else 0)
        
        # Image glyph parameters
        x_coord = times_ms_padded[0] if final_n_times > 0 else 0
        y_coord = -0.5 # Image covers cells from y to y+dh; -0.5 to n_freqs-0.5
        dw_val = chunk_time_length * time_step
        dh_val = n_freqs
          
        return {
            'frequency_labels': frequency_labels_str,         # Formatted string labels for ticks
            'frequencies_hz': selected_frequencies.tolist(),  # Numeric frequency values for robust JS indexing
            'n_times': int(final_n_times),                    # total number of times
            'n_freqs': int(n_freqs),                          # total number of frequencies
            'chunk_time_length': int(chunk_time_length),      # number of times in a chunk
            'time_step': time_step,                           # time step in ms

            'times_ms': times_ms_padded.tolist(),         # Timestamps in ms for x-axis
            'levels_flat_transposed': levels_flat_transposed, # Flattened levels matrix for glyph data

            'min_val': min_val,
            'max_val': max_val,

            'min_time': min_time,
            'max_time': max_time,
            
            'initial_glyph_data': {
                'x': [float(x_coord)],    # For image glyph 'x'
                'y': [float(y_coord)],    # For image glyph 'y'
                'dw': [float(dw_val)],     # For image glyph 'dw'
                'dh': [float(dh_val)],      # For image glyph 'dh'
                'image': [first_data_chunk]
            }
        }

    def prepare_downsampled_spectral_data(self, df: pd.DataFrame, param_prefix: str,
                                          chart_settings: Dict, target_points: int) -> Optional[Dict[str, Any]]:
        if df is None or df.empty:
            return None
        downsampled = downsample_dataframe_max(df, target_points)
        return self.prepare_single_spectrogram_data(downsampled, param_prefix, chart_settings)

    def _extract_spectral_parameters(self, df: Optional[pd.DataFrame]) -> List[str]:
        """
        Utility to find all unique parameter prefixes (e.g., 'LZeq', 'LAFmax') 
        from columns that appear to be spectral data (PARAM_FREQ format).
        """
        if df is None or df.empty: return []
        
        params: Set[str] = set()
        for col in df.columns:
            if '_' in col:
                parts = col.split('_', 1) # Split only on the first underscore
                if len(parts) == 2:
                    param_prefix = parts[0]
                    freq_suffix = parts[1]
                    # A simple check: does the prefix start with L and suffix look like a number?
                    # More robust: check if freq_suffix is in a list of known freq strings (like from parsers)
                    # For now, if it starts with L and has underscore, assume it's a candidate.
                    if param_prefix.startswith('L') and freq_suffix.replace('.', '', 1).isdigit():
                        params.add(param_prefix)
        return sorted(list(params))

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    processor = GlyphDataProcessor()

    # --- Example Usage ---
    # 1. Create a dummy PositionData object (as if loaded by DataManager)
    class DummyPosData(PositionData): # Inherit from actual if available
        pass
    
    test_pos = DummyPosData(name="TestSite")

    # Create dummy overview_spectral data
    overview_dates = pd.to_datetime(['2023-01-01 10:00:00', '2023-01-01 10:05:00'])
    test_pos.overview_spectral = pd.DataFrame({
        'Datetime': overview_dates,
        'LAeq': [60, 62], # Overall LAeq
        'LZeq_1000': [55.1, 56.2],
        'LZeq_2000': [50.5, 51.8],
        'LZFmax_1000': [65.0, 66.0],
        'LAF90_ignore': [40, 41] # This should be ignored as spectral if not PARAM_FREQ
    })
    
    # Create dummy log_spectral data
    log_dates = pd.date_range('2023-01-01 10:00:00', periods=5, freq='1min')
    test_pos.log_spectral = pd.DataFrame({
        'Datetime': log_dates,
        'LZeq_500': np.random.rand(5) * 20 + 40,
        'LZeq_1000': np.random.rand(5) * 20 + 45,
        'LAFmax': np.random.rand(5) * 10 + 60, # Overall LAFmax
    })

    print(f"Position has overview spectral: {test_pos.has_overview_spectral}")
    print(f"Position has log spectral: {test_pos.has_log_spectral}")

    # 2. Process all spectral data for this position
    chart_settings_test = {
        'lower_freq_band': 0, 
        'upper_freq_band': -1, # All bands
        'nan_replace_offset': -30
    }
    prepared_data_for_site = processor.prepare_all_spectral_data(test_pos, chart_settings_test)

    # 3. Inspect the output
    if 'overview_spectral' in prepared_data_for_site:
        print("\n--- Prepared Overview Spectral Data ---")
        print(f"Available params: {prepared_data_for_site['overview_spectral']['available_params']}")
        for param, data_dict in prepared_data_for_site['overview_spectral']['prepared_params'].items():
            print(f"  Parameter: {param}")
            print(f"    Frequencies: {data_dict['frequency_labels']}")
            print(f"    Times (ms): {data_dict['times_ms'][:2]}... ({data_dict['n_times']} total)")
            print(f"    Levels Matrix Transposed Shape: ({len(data_dict['levels_matrix_transposed'])}, {len(data_dict['levels_matrix_transposed'][0]) if data_dict['levels_matrix_transposed'] else 0})")
            print(f"    Min/Max Val: {data_dict['min_val']:.1f} / {data_dict['max_val']:.1f}")

    if 'log_spectral' in prepared_data_for_site:
        print("\n--- Prepared Log Spectral Data ---")
        print(f"Available params: {prepared_data_for_site['log_spectral']['available_params']}")
        for param, data_dict in prepared_data_for_site['log_spectral']['prepared_params'].items():
            print(f"  Parameter: {param}")
            print(f"    Frequencies: {data_dict['frequency_labels']}")
            # print(f"    Levels Matrix (first 2x2): {np.array(data_dict['levels_matrix'])[:2,:2]}")
            print(f"    Image x,y,dw,dh: {data_dict['x_coord']}, {data_dict['y_coord']}, {data_dict['dw_val']}, {data_dict['dh_val']}")

    # Test with no spectral data
    empty_pos = DummyPosData(name="EmptySite")
    prepared_empty = processor.prepare_all_spectral_data(empty_pos, chart_settings_test)
    print(f"\n--- Prepared Empty Site Data ---: {prepared_empty}")
    assert not prepared_empty 
