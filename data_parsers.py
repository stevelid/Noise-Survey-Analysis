"""
Data parsing module for noise survey analysis.
This module contains parsers for different sound meter data file formats:
- Noise Sentry Parser: For CSV files from Noise Sentry meters
- NTi Parser: For NTi sound meter data files (RPT, RTA and log files)
- Svan Parser: For Excel files from Svan meters
"""

import pandas as pd
import numpy as np
import re
import os


def safe_convert_to_float(df, columns=None):
    """
    Safely convert columns in a dataframe to float values.
    
    Parameters:
    df (pd.DataFrame): DataFrame to process
    columns (list, optional): List of columns to convert. If None, converts all except datetime columns.
    
    Returns:
    pd.DataFrame: DataFrame with converted columns
    """
    if columns is None:
        # Skip datetime columns
        columns = [col for col in df.columns if not pd.api.types.is_datetime64_any_dtype(df[col])]
    
    for col in columns:
        if col in df.columns and col != "" and col != "Datetime" and col != "_":
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            except Exception as e:
                print(f"Warning: Could not convert column '{col}' to numeric values: {e}")
    
    return df


class NoiseDataParser:
    """Base class for noise data parsers"""
    
    @staticmethod
    def get_parser(parser_type):
        """
        Factory method to get the appropriate parser based on type.
        
        Parameters:
        parser_type (str): The type of parser to use ('sentry', 'nti', or 'svan')
        
        Returns:
        object: An instance of the appropriate parser class
        """
        parser_mapping = {
            'sentry': NoiseSentryParser,
            'nti': NTiParser,
            'svan': SvanParser
        }
        
        if parser_type.lower() not in parser_mapping:
            raise ValueError(f"Unknown parser type: {parser_type}. "
                            f"Available types: {list(parser_mapping.keys())}")
        
        return parser_mapping[parser_type.lower()]()


class NoiseSentryParser(NoiseDataParser):
    """Parser for Noise Sentry CSV files"""
    
    def parse(self, file_path):
        """
        Read and parse a Noise Sentry CSV file.
        
        Parameters:
        file_path (str): Path to the Noise Sentry CSV file
        
        Returns:
        pd.DataFrame: DataFrame containing the parsed data
        """
        if not file_path.endswith('.csv'):
            raise ValueError("Error: File must be .csv")
        
        print(f'Reading file: {file_path}')
        with open(file_path, 'r') as f:
            lines = f.readlines()
        
        headers = lines[0].strip().split(',')
        headers[0] = 'Datetime'
        
        # Replace specific header names with standardized versions
        replacements = {
            'LEQ dB-A ': 'LAeq', 
            'Lmax dB-A ': 'LAFmax', 
            'L10 dB-A ': 'LAF10', 
            'L90 dB-A ': 'LAF90'
        }
        
        for old, new in replacements.items():
            if old in headers:
                headers[headers.index(old)] = new
        
        data = [line.strip().split(',') for line in lines[1:]]
        ns_df = pd.DataFrame(data, columns=headers)
        ns_df['Datetime'] = pd.to_datetime(ns_df['Datetime'])
        
        # Convert numeric columns to float
        for col in ns_df.columns[1:]:
            try:
                ns_df[col] = ns_df[col].astype(float)
            except ValueError:
                pass
        
        return ns_df


class SvanParser(NoiseDataParser):
    """Parser for Svan Excel files"""
    
    def parse(self, file_path):
        """
        Read and parse a Svan Excel file.
        
        Parameters:
        file_path (str): Path to the Svan Excel file
        
        Returns:
        pd.DataFrame: DataFrame containing the parsed data
        """
        print(f'Reading file: {file_path}')
        df = pd.read_excel(file_path)
        
        # Find the first row with values in the third column (index 2)
        i = df[df.iloc[:, 2].notna()].index[0]
        rows = df.iloc[i+1:i+3]
        
        headers = []
        for col in df.columns:
            parts = []
            for val in rows[col]:
                if pd.notna(val):
                    if val == 'LAeq Histogram (SR) [dB]':
                        continue
                    if val.endswith("Hz"):
                        val = str(float(val[:-2]))
                    val = re.sub("1/3 Oct (\\w+) \\(SR\\) \\[dB]", r'\\1', val)
                    val = val.replace('(TH) [dB]', '').replace('Date & time', 'Datetime')
                    val = re.sub(r'L(10|90)', r'LAF\1', str(val))
                    parts.append(str(val))
            headers.append('_'.join(parts).strip())
        
        df.columns = headers
        df = df.iloc[i+3:]
        df['Datetime'] = pd.to_datetime(df['Datetime'], dayfirst=True)
        
        return df


class NTiParser(NoiseDataParser):
    """Parser for NTi sound meter data files"""
    
    def parse(self, file_path, file_types=None):
        """
        Generic parser for NTi files (RPT, RTA, and log files).
        
        Parameters:
        file_path (str): Base path to the NTi files without file type suffix.
                       For example: "/path/to/folder/2025-02-15_SLM_000"
        file_types (list, optional): List of file types to read. 
                                  If None, reads all available types.
                                  Options: 'RPT', 'RTA', 'RPT_LOG', 'RTA_LOG'
        
        Returns:
        dict: Dictionary containing DataFrames for each file type and metadata
              Structure: {
                  'RPT': DataFrame,
                  'RTA': DataFrame,
                  'RPT_LOG': DataFrame,
                  'RTA_LOG': DataFrame,
                  'RPT_metadata': dict,
                  'RTA_metadata': dict,
                  'combined': DataFrame
              }
        """
        print(f"Reading NTi files with base path: {file_path}")
        
        if file_types is None:
            file_types = ['RPT', 'RTA', 'RPT_LOG', 'RTA_LOG']
        
        # Strip any existing suffixes to ensure base_path is clean
        base_path = file_path
        for suffix in ['_123_Rpt_Report.txt', '_RTA_3rd_Rpt_Report.txt', '_123_Log.txt', '_RTA_3rd_Log.txt']:
            if base_path.endswith(suffix):
                base_path = base_path[:-len(suffix)]
                break
        
        result = {}
        
        # Read RPT file (123 Report)
        if 'RPT' in file_types:
            result.update(self._parse_rpt_file(base_path))
        
        # Read RTA file (RTA 3rd Report)
        if 'RTA' in file_types:
            result.update(self._parse_rta_file(base_path))
        
        # Read RPT LOG file (123 Log)
        if 'RPT_LOG' in file_types:
            result.update(self._parse_rpt_log_file(base_path))
        
        # Read RTA LOG file (RTA 3rd Log)
        if 'RTA_LOG' in file_types:
            result.update(self._parse_rta_log_file(base_path))
        
        # Create a combined data frame from RPT and RTA files
        self._create_combined_dataframe(result)
        
        if not result:
            print(f"Warning: No data could be loaded from NTi files at {file_path}")
        
        return result
    
    def _parse_rpt_file(self, base_path):
        """Parse the RPT file (123 Report)"""
        result = {}
        rpt_file_path = f"{base_path}_123_Rpt_Report.txt"
        
        print(f'Checking for RPT file: {rpt_file_path}')
        if not os.path.exists(rpt_file_path):
            print(f"Warning: RPT file not found: {rpt_file_path}")
            return result
            
        print(f'Reading RPT file: {rpt_file_path}')
        with open(rpt_file_path, 'r') as f:
            lines = f.readlines()
        
        # Filter out lines after "#CheckSum" is reached
        checksum_index = next((i for i, line in enumerate(lines) if "#CheckSum" in line), len(lines))
        lines = lines[:checksum_index]
        
        hardware_config = {}
        measurement_setup = {}
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("Hardware Configuration"):
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("#"):
                    parts = lines[i].split(':', 1)
                    if len(parts) == 2:
                        key, value = map(str.strip, parts)
                        hardware_config[key] = value
                    i += 1
            elif line.startswith("Measurement Setup"):
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("#"):
                    parts = lines[i].split(':', 1)
                    if len(parts) == 2:
                        key, value = map(str.strip, parts)
                        measurement_setup[key] = value
                    i += 1
            elif line.startswith("# Broadband Results"):
                break
            i += 1
        
        table_start_idx = i + 1
        data_lines = lines[table_start_idx:]
        data = [[item.strip() for item in line.strip().split('\t')] for line in data_lines]
        
        # Filter out rows that contain NaN values or are empty
        data = [row for row in data if row and any(item.strip() != '' for item in row)]
        
        if len(data) <= 3:
            print(f"Warning: Insufficient data found in RPT file. Found {len(data)} lines.")
        else:
            max_num_columns = max(len(row) for row in data[3:])
            column_headers = ["Start Date", "Start Time", "End Date", "End Time"] + list(data[1][4:max_num_columns])
            column_headers = [header.replace('.0%', '') for header in column_headers]
            rpt_df = pd.DataFrame([row[:max_num_columns] for row in data[3:]], columns=column_headers)
            rpt_df['Datetime'] = pd.to_datetime(rpt_df['Start Date'] + ' ' + rpt_df['Start Time'])
            rpt_df = safe_convert_to_float(rpt_df)
            result['RPT'] = rpt_df
        
        result['RPT_metadata'] = {'hardware_config': hardware_config, 'measurement_setup': measurement_setup}
        return result
    
    def _parse_rta_file(self, base_path):
        """Parse the RTA file (RTA 3rd Report)"""
        result = {}
        rta_file_path = f"{base_path}_RTA_3rd_Rpt_Report.txt"
        
        print(f'Checking for RTA file: {rta_file_path}')
        if not os.path.exists(rta_file_path):
            print(f"Warning: RTA file not found: {rta_file_path}")
            return result
            
        print(f'Reading RTA file: {rta_file_path}')
        with open(rta_file_path, 'r') as f:
            lines = f.readlines()
        
        # Filter out lines after "#CheckSum" is reached
        checksum_index = next((i for i, line in enumerate(lines) if "#CheckSum" in line), len(lines))
        lines = lines[:checksum_index]
        
        hardware_config = {}
        measurement_setup = {}
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("Hardware Configuration"):
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("#"):
                    parts = lines[i].split(':', 1)
                    if len(parts) == 2:
                        key, value = map(str.strip, parts)
                        hardware_config[key] = value
                    i += 1
            elif line.startswith("Measurement Setup"):
                i += 1
                while i < len(lines) and not lines[i].strip().startswith("#"):
                    parts = lines[i].split(':', 1)
                    if len(parts) == 2:
                        key, value = map(str.strip, parts)
                        measurement_setup[key] = value
                    i += 1
            elif line.startswith("# RTA Results"):
                break
            i += 1
        
        table_start_idx = i + 1
        data = [[item.strip() for item in line.strip().split('\t')] for line in lines[table_start_idx:]]
        
        # Filter out rows that contain NaN values or are empty
        data = [row for row in data if row and any(item.strip() != '' for item in row)]
        
        if len(data) <= 3:
            print(f"Warning: Insufficient data found in RTA file. Found {len(data)} lines.")
        else:
            band_row, band_col = next(
                (i, j) for i, row in enumerate(data)
                for j, cell in enumerate(row)
                if cell == "Band [Hz]"
            )
            
            types_row = data[band_row-1][band_col+1:]
            frequencies_row = data[band_row][band_col+1:]
            rta_headers = [f"{type_}_{freq}" for type_, freq in zip(types_row, frequencies_row)]
            rta_headers = [header.replace('.0%', '') for header in rta_headers]
            column_headers = ["Start Date", "Start Time", "End Date", "End Time", "Band [Hz]"] + rta_headers
            rta_df = pd.DataFrame(data[band_row+2:], columns=column_headers)
            rta_df['Datetime'] = pd.to_datetime(rta_df['Start Date'] + ' ' + rta_df['Start Time'])
            rta_df = safe_convert_to_float(rta_df)
            result['RTA'] = rta_df
        
        result['RTA_metadata'] = {'hardware_config': hardware_config, 'measurement_setup': measurement_setup}
        return result
    
    def _parse_rpt_log_file(self, base_path):
        """Parse the RPT LOG file (123 Log)"""
        
        desired_columns = ['Datetime', 'LAF90', 'LAF10', 'LAFmax_dt', 'LAeq_dt']
        result = {}
        log_file_path = f"{base_path}_123_Log.txt"
        
        print(f'Checking for RPT log file: {log_file_path}')
        if not os.path.exists(log_file_path):
            print(f"Warning: RPT log file not found: {log_file_path}")
            return result
            
        print(f'Reading RPT log file: {log_file_path}')
        with open(log_file_path, 'r') as f:
            lines = f.readlines()
        
        # Filter out lines after "#CheckSum" is reached
        checksum_index = next((i for i, line in enumerate(lines) if "#CheckSum" in line), len(lines))
        lines = lines[:checksum_index]
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("# Broadband LOG Results"):
                break
            i += 1
        
        table_start_idx = i + 1
        data_lines = lines[table_start_idx:]
        data = [[item.strip() for item in line.split('\t')] for line in data_lines]
        
        # Filter out rows that contain NaN values or are empty
        data = [row for row in data if row and any(item.strip() != '' for item in row)]
        
        if len(data) <= 2:
            print(f"Warning: Insufficient data found in RPT log file. Found {len(data)} lines.")
        else:
            max_num_columns = max(len(row[:-3]) for row in data)
            column_headers = list(data[0][:max_num_columns])
            column_headers = [header.replace('.0%', '') for header in column_headers]
            log_df = pd.DataFrame([row[:max_num_columns] for row in data[2:][:-3]], columns=column_headers)
            log_df['Datetime'] = pd.to_datetime(log_df['Date'] + ' ' + log_df['Time'])
            log_df = safe_convert_to_float(log_df)
            result['RPT_LOG'] = log_df[desired_columns]
        
        return result
    
    def _parse_rta_log_file(self, base_path):
        """Parse the RTA LOG file (RTA 3rd Log)"""
        result = {}
        log_file_path = f"{base_path}_RTA_3rd_Log.txt"
        
        print(f'Checking for RTA log file: {log_file_path}')
        if not os.path.exists(log_file_path):
            print(f"Warning: RTA log file not found: {log_file_path}")
            return result
            
        print(f'Reading RTA log file: {log_file_path}')
        with open(log_file_path, 'r') as f:
            lines = f.readlines()
        
        # Filter out lines after "#CheckSum" is reached
        checksum_index = next((i for i, line in enumerate(lines) if "#CheckSum" in line), len(lines))
        lines = lines[:checksum_index]
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("# RTA LOG Results"):
                break
            i += 1
        
        table_start_idx = i + 1
        data_lines = lines[table_start_idx:]
        data = [[item.strip() for item in line.split('\t')] for line in data_lines]
        
        # Filter out rows that contain NaN values or are empty
        data = [row for row in data if row and any(item.strip() != '' for item in row)]
        
        if len(data) <= 2:
            print(f"Warning: Insufficient data found in RTA log file. Found {len(data)} lines.")
        else:
            band_row, band_col = next(
                (i, j) for i, row in enumerate(data)
                for j, cell in enumerate(row)
                if cell == "Band [Hz]"
            )
            
            types_row = data[band_row-1][band_col+1:]
            frequencies_row = data[band_row][band_col+1:]
            rta_headers = [f"{type_}_{freq}" for type_, freq in zip(types_row, frequencies_row)]
            rta_headers = [header.replace('.0%', '') for header in rta_headers]
            column_headers = data[band_row][:band_col+1] + rta_headers
            log_df = pd.DataFrame(data[band_row+2:], columns=column_headers)
            if 'Date' in log_df.columns and 'Time' in log_df.columns:
                log_df['Datetime'] = pd.to_datetime(log_df['Date'] + ' ' + log_df['Time'])
            log_df = safe_convert_to_float(log_df)
            result['RTA_LOG'] = log_df
        
        return result
    
    def _create_combined_dataframe(self, result):
        """Create a combined DataFrame from RPT and RTA data"""
        if 'RPT' in result and 'RTA' in result:
            try:
                rpt_df = result['RPT']
                rta_df = result['RTA']
                
                # Extract only basic metrics from RPT
                rpt_metrics = ["Datetime", "LAeq", "LAF90", "LAF10", "LAFmax"]
                rpt_cols = [col for col in rpt_metrics if col in rpt_df.columns]
                if not rpt_cols:
                    print("Warning: No standard RPT metrics found. Looking for alternative columns.")
                    potential_cols = [col for col in rpt_df.columns if any(m in col for m in ["LAeq", "LA90", "L90", "LA10", "L10", "LAmax", "Lmax"])]
                    rpt_cols = ["Datetime"] + potential_cols
                
                rpt_subset = rpt_df[rpt_cols].copy()
                
                # Extract frequency metrics from RTA
                metrics_to_keep = ["LZeq", "LZFmax", "LZF90", "LZF10"]
                rta_subset = rta_df.loc[:, rta_df.columns.str.contains('|'.join(metrics_to_keep))]
                
                # Combine the dataframes - aligning by index since they should match
                combined_df = pd.concat([rpt_subset, rta_subset], axis=1)
                
                # Convert numeric columns to float
                combined_df = safe_convert_to_float(combined_df)
                
                # Drop the last few rows which might be summary statistics
                result['combined'] = combined_df[:-3] if len(combined_df) > 3 else combined_df
                
            except Exception as e:
                print(f"Error creating combined DataFrame: {e}")
                # Still create a combined DataFrame with what's available
                if 'RPT' in result:
                    result['combined'] = result['RPT']
                elif 'RTA' in result:
                    result['combined'] = result['RTA']
        elif 'RPT' in result:
            result['combined'] = result['RPT']
        elif 'RTA' in result:
            result['combined'] = result['RTA']


# Convenience functions for backward compatibility
def read_in_noise_sentry_file(file_path):
    """Backward compatibility function for reading Noise Sentry files"""
    parser = NoiseSentryParser()
    return parser.parse(file_path)

def read_in_Svan_file(file_path):
    """Backward compatibility function for reading Svan files"""
    parser = SvanParser()
    return parser.parse(file_path)

def read_NTi(file_path, file_types=None):
    """Backward compatibility function for reading NTi files"""
    parser = NTiParser()
    return parser.parse(file_path, file_types)


def get_parser(parser_type):
    """
    Get a parser instance by type.
    
    Parameters:
    parser_type (str): Type of parser ('sentry', 'nti', or 'svan')
    
    Returns:
    object: An instance of the appropriate parser class
    """
    return NoiseDataParser.get_parser(parser_type)
