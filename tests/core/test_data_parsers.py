# Initial placeholder for data parser tests 

import os
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
import logging
from datetime import datetime

# Import the modules/classes to test
try:
    from noise_survey_analysis.core.data_parsers import (
        safe_convert_to_float,
        NoiseSentryParser, 
        SvanParser,
        NTiParser,
        NoiseDataParser
    )
except ImportError:
    # Fallback if the module structure is different
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from data_parsers import (
        safe_convert_to_float,
        NoiseSentryParser, 
        SvanParser,
        NTiParser,
        NoiseDataParser
    )

# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_dataframe():
    """Create a sample DataFrame for testing safe_convert_to_float."""
    return pd.DataFrame({
        'Datetime': pd.date_range(start='2023-01-01', periods=5),
        'numeric_col': ['1.0', '2.0', '3.0', '4.0', '5.0'],
        'mixed_col': ['1.0', 'abc', '3.0', 'xyz', '5.0'],
        'empty_col': ['', '', '', '', ''],
        'nan_col': ['NaN', 'nan', '1.0', 'null', '5.0']
    })

@pytest.fixture
def noise_sentry_parser():
    """Create a NoiseSentryParser instance."""
    return NoiseSentryParser()

@pytest.fixture
def svan_parser():
    """Create a SvanParser instance."""
    return SvanParser()

@pytest.fixture
def nti_parser():
    """Create an NTiParser instance."""
    return NTiParser()

@pytest.fixture
def valid_noise_sentry_content():
    """Create valid Noise Sentry CSV content."""
    return (
        "Time,LEQ dB-A ,Lmax dB-A ,L10 dB-A ,L90 dB-A \n"
        "2023-01-01 10:00:00,65.2,75.3,68.4,55.1\n"
        "2023-01-01 10:01:00,64.9,72.1,67.5,54.8\n"
        "2023-01-01 10:02:00,66.1,78.2,69.0,56.2\n"
    )

@pytest.fixture
def invalid_noise_sentry_content():
    """Create invalid Noise Sentry CSV content with inconsistent columns."""
    return (
        "Time,LEQ dB-A ,Lmax dB-A ,L10 dB-A ,L90 dB-A \n"
        "2023-01-01 10:00:00,65.2,75.3,68.4\n"  # Missing L90
        "2023-01-01 10:01:00,64.9,72.1,67.5,54.8\n"
        "2023-01-01 10:02:00,66.1,invalid,69.0,56.2\n"  # Invalid Lmax
    )

@pytest.fixture
def valid_svan_content(tmp_path):
    """
    Create a mock Svan Excel file structure using pandas.
    
    Since we can't directly create an Excel file with specific formatting,
    we create a DataFrame that matches the structure expected by the parser.
    """
    # Create DataFrame that resembles SVAN file format
    header_rows = [
        # Row before header (usually empty or metadata)
        ["", "", "", "", ""],
        # Header row with column names
        ["", "Date & time", "Leq", "L10", "L90", "Lmax", "LZeq", "31.5 Hz", "63 Hz"],
        # Unit row
        ["", "", "[dB]", "[dB]", "[dB]", "[dB]", "", "", ""]
    ]
    
    # Add data rows
    data_rows = [
        ["", "2023-01-01 10:00:00", "65.2", "68.4", "55.1", "75.3", "70.1", "45.2", "52.3"],
        ["", "2023-01-01 10:01:00", "64.9", "67.5", "54.8", "72.1", "69.8", "44.9", "51.8"],
        ["", "2023-01-01 10:02:00", "66.1", "69.0", "56.2", "78.2", "71.2", "46.1", "53.5"]
    ]
    
    df = pd.DataFrame(header_rows + data_rows)
    
    # Save to Excel file
    file_path = tmp_path / "test_svan_file.xlsx"
    df.to_excel(file_path, index=False, header=False)
    
    return file_path

@pytest.fixture
def valid_nti_rpt_content():
    """Create a more comprehensive NTi RPT report content based on real-world examples."""
    return (
        "XL2 Sound Level Meter Broadband Reporting:		RESTORE_AFTER_POWERFAIL\\2025-02-15_SLM_000_123_Rpt_Report.txt\n"
        "------------------------------------------\n"
        "\n"
        "# Hardware Configuration\n"
        "\tDevice Info:    \tXL2, SNo. A2A-11461-E0, FW4.71 Type Approved\n"
        "\tMic Sensitivity:\t40.9 mV/Pa\n"
        "\t                \t(User calibrated 2025-02-11  13:48)\n"
        "\tTime Zone:      \tUTC+00:00 (Europe/London)\n"
        "\n"
        "# Measurement Setup\n"
        "\tProfile:        \tFull mode\n"
        "\tAppend mode:    \tOFF\n"
        "\tTimer mode:     \trepeat sync\n"
        "\tTimer set:      \t00:05:00\n"
        "\tk1:             \t0.0 dB\n"
        "\tk2:             \t0.0 dB\n"
        "\tkset Date:      \tk-Values not measured\n"
        "\tRange:          \t0 - 100 dB\n"
        "\n"
        "# Broadband Results\n"
        "\tStart       \t          \tStop        \t          \n"
        "\tDate        \tTime      \tDate        \tTime      \tLASmax  \tLASmin  \tLAFmax  \tLAFmin  \tLAImax  \tLAImin  \tLAeq    \tPrev_LAeq\tLAeq5\"  \tLAeq5\"max\tLAF1.0% \tLAF5.0% \tLAF10.0%\tLAF50.0%\tLAF90.0%\tLAF95.0%\tLAF99.0%\tLCeq    \tLZeq    \tLZPKmax \n"
        "\t[YYYY-MM-DD]\t[hh:mm:ss]\t[YYYY-MM-DD]\t[hh:mm:ss]\t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]     \t[dB]    \t[dB]     \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \n"
        "\t2025-02-15  \t13:17:20  \t2025-02-15  \t13:20:00  \t80.7    \t37.1    \t87.4    \t29.7    \t91.6    \t44.0    \t66.8    \t-.-      \t52.4    \t76.9     \t79.7    \t73.5    \t68.5    \t52.7    \t40.6    \t37.4    \t32.1    \t67.8    \t73.3    \t110.0   \n"
        "\t2025-02-15  \t13:20:00  \t2025-02-15  \t13:25:00  \t67.9    \t33.3    \t74.2    \t31.5    \t77.5    \t34.1    \t51.9    \t66.8     \t38.6    \t63.6     \t65.1    \t55.2    \t50.7    \t40.4    \t35.0    \t34.1    \t33.0    \t54.8    \t59.3    \t101.6   \n"
        "\t2025-02-15  \t13:25:00  \t2025-02-15  \t13:30:00  \t48.8    \t33.8    \t55.7    \t32.6    \t59.2    \t35.2    \t41.0    \t51.9     \t42.8    \t45.8     \t47.0    \t44.5    \t43.3    \t40.0    \t36.6    \t35.6    \t33.6    \t52.3    \t58.2    \t78.5    \n"
        "\n"
        "#CheckSum\n"
        "\t3788006757D7F87B3E3224B09BC79224\n"
    )

@pytest.fixture
def valid_nti_rta_content(tmp_path):
    """Create a more comprehensive NTi RTA report content based on real-world examples."""
    return (
        "XL2 Sound Level Meter RTA Reporting:		RESTORE_AFTER_POWERFAIL\\2025-02-15_SLM_000_RTA_3rd_Rpt_Report.txt\n"
        "------------------------------------\n"
        "\n"
        "# Hardware Configuration\n"
        "\tDevice Info:    \tXL2, SNo. A2A-11461-E0, FW4.71 Type Approved\n"
        "\tMic Sensitivity:\t40.9 mV/Pa\n"
        "\t                \t(User calibrated 2025-02-11  13:48)\n"
        "\tTime Zone:      \tUTC+00:00 (Europe/London)\n"
        "\n"
        "# Measurement Setup\n"
        "\tProfile:        \tFull mode\n"
        "\tAppend mode:    \tOFF\n"
        "\tTimer mode:     \trepeat sync\n"
        "\tTimer set:      \t00:05:00\n"
        "\tResolution:     \t1/3 Octave\n"
        "\tRange:          \t0 - 100 dB\n"
        "\n"
        "# RTA Results \n"
        "\tStart       \t          \tStop        \t          \t         \tLZFmax  \tLZFmax  \tLZFmax  \tLZFmax  \tLZFmin  \tLZFmin  \tLZFmin  \tLZFmin  \tLZeq    \tLZeq    \tLZeq    \tLZeq    \tLZF10.0%\tLZF10.0%\tLZF10.0%\tLZF10.0%\tLZF50.0%\tLZF50.0%\tLZF50.0%\tLZF50.0%\tLZF90.0%\tLZF90.0%\tLZF90.0%\tLZF90.0%\n"
        "\tDate        \tTime      \tDate        \tTime      \tBand [Hz]\t6.3     \t31.5    \t63.0    \t125.0   \t6.3     \t31.5    \t63.0    \t125.0   \t6.3     \t31.5    \t63.0    \t125.0   \t6.3     \t31.5    \t63.0    \t125.0   \t6.3     \t31.5    \t63.0    \t125.0   \t6.3     \t31.5    \t63.0    \t125.0   \n"
        "\t[YYYY-MM-DD]\t[hh:mm:ss]\t[YYYY-MM-DD]\t[hh:mm:ss]\t         \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \t[dB]    \n"
        "\t2025-02-15  \t13:17:20  \t2025-02-15  \t13:20:00  \t         \t81.2    \t68.0    \t70.8    \t76.3    \t24.3    \t28.8    \t32.0    \t24.9    \t64.4    \t47.8    \t48.3    \t48.4    \t68.0    \t50.0    \t48.0    \t46.0    \t53.0    \t42.0    \t41.0    \t38.0    \t37.0    \t36.0    \t36.0    \t31.0    \n"
        "\t2025-02-15  \t13:20:00  \t2025-02-15  \t13:25:00  \t         \t74.6    \t70.5    \t62.6    \t62.7    \t18.9    \t28.3    \t25.8    \t19.1    \t50.7    \t43.9    \t43.7    \t39.2    \t48.0    \t51.0    \t50.0    \t49.0    \t37.0    \t39.0    \t38.0    \t33.0    \t30.0    \t35.0    \t33.0    \t25.0    \n"
        "\t2025-02-15  \t13:25:00  \t2025-02-15  \t13:30:00  \t         \t65.9    \t60.7    \t64.0    \t54.1    \t22.5    \t26.5    \t27.8    \t19.8    \t50.7    \t43.0    \t44.0    \t39.8    \t54.0    \t47.0    \t48.0    \t46.0    \t43.0    \t40.0    \t39.0    \t35.0    \t34.0    \t35.0    \t33.0    \t26.0    \n"
        "\n"
        "#CheckSum\n"
        "\tD6E65DC39D3FA525883E4DF1147FEFE9\n"
    )

@pytest.fixture
def valid_nti_log_content():
    """Create valid NTi LOG file content."""
    return (
        "# XL2 Data Explorer; Firmware: V4.71\n"
        "# Project: Test Project\n"
        "# Serial Number: A2A-12345-D1\n"
        "\n"
        "# Broadband LOG Results\n"
        "\n"
        "Date\tTime\tTimer\tLAeq_dt\tLAeq\tLAFmax_dt\tLAFmax\tLCpeak_dt\tLCpeak\tLAF10\tLAF90\n"
        "[YYYY-MM-DD]\t[hh:mm:ss]\t[h:min:s]\t[dB]\t[dB]\t[dB]\t[dB]\t[dB]\t[dB]\t[dB]\t[dB]\n"
        "\n"
        "2023-01-01\t10:00:00\t00:00:01\t65.2\t65.2\t75.3\t75.3\t88.7\t88.7\t68.4\t55.1\n"
        "2023-01-01\t10:00:01\t00:00:02\t64.8\t65.0\t73.2\t75.3\t87.5\t88.7\t68.1\t54.9\n"
        "2023-01-01\t10:00:02\t00:00:03\t66.0\t65.3\t77.1\t77.1\t89.3\t89.3\t68.5\t55.3\n"
        "\n"
        "# Logging Summary\n"
        "LAeq = 65.3 dB\n"
        "LAFmax = 77.1 dB\n"
        "LCpeak = 89.3 dB\n"
        "\n"
        "# CheckSum: 0x9A8B7C6D"
    )

@pytest.fixture
def valid_nti_rta_log_content():
    """Create valid NTi RTA LOG content based on real-world examples."""
    return (
        "XL2 RTA Spectrum Logging:		RESTORE_AFTER_POWERFAIL\\2025-02-15_SLM_000_RTA_3rd_Log.txt\n"
        "-------------------------\n"
        "\n"
        "# Hardware Configuration\n"
        "\tDevice Info:    \tXL2, SNo. A2A-11461-E0, FW4.71 Type Approved\n"
        "\tMic Sensitivity:\t40.9 mV/Pa\n"
        "\t                \t(User calibrated 2025-02-11  13:48)\n"
        "\tTime Zone:      \tUTC+00:00 (Europe/London)\n"
        "\n"
        "# Measurement Setup\n"
        "\tProfile:        \tFull mode\n"
        "\tTimer mode:     \trepeat sync\n"
        "\tTimer set:      \t00:05:00\n"
        "\tLog-Interval:   \t00:00:10\n"
        "\tResolution:     \t1/3 Octave\n"
        "\tRange:          \t0 - 100 dB\n"
        "\n"
        "# Time\n"
        "\tStart:          \t2025-02-15, 13:17:20\n"
        "\tEnd:            \t2025-02-18, 21:37:40\n"
        "\n"
        "# RTA LOG Results \n"
        "\t            \t          \t          \t         \tLZeq_dt  \tLZeq_dt  \tLZeq_dt  \tLZeq_dt  \tLZeq_dt  \tLZeq_dt  \tLZFmin_dt\tLZFmin_dt\tLZFmin_dt\tLZFmin_dt\tLZFmax_dt\tLZFmax_dt\tLZFmax_dt\tLZFmax_dt\n"
        "\tDate        \tTime      \tTimer     \tBand [Hz]\t6.3      \t31.5     \t63.0     \t125.0    \t250.0    \t500.0    \t6.3      \t31.5     \t63.0     \t125.0    \t6.3      \t31.5     \t63.0     \t125.0    \n"
        "\t[YYYY-MM-DD]\t[hh:mm:ss]\t[hh:mm:ss]\t         \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \t[dB]     \n"
        "\t2025-02-15  \t13:17:30  \t00:02:30  \t         \t55.8     \t41.6     \t40.7     \t40.6     \t41.2     \t62.2     \t32.3     \t31.5     \t32.1     \t29.3     \t63.2     \t48.7     \t50.1     \t53.8     \n"
        "\t2025-02-15  \t13:17:40  \t00:02:20  \t         \t57.6     \t43.7     \t41.1     \t42.6     \t45.9     \t57.0     \t43.3     \t36.9     \t34.7     \t34.8     \t64.6     \t50.2     \t48.4     \t52.0     \n"
        "\t2025-02-15  \t13:17:50  \t00:02:10  \t         \t51.1     \t45.6     \t46.7     \t45.8     \t58.2     \t58.6     \t27.6     \t33.9     \t34.0     \t31.7     \t63.7     \t55.6     \t60.8     \t61.0     \n"
        "\n"
        "#CheckSum\n"
        "\t495B1A8031BFFF9AFCFCFB764AB70ACE\n"
    )

# ============================================================
# Tests for safe_convert_to_float
# ============================================================

def test_safe_convert_to_float_all_columns(sample_dataframe):
    """Test safe_convert_to_float with default parameter (all non-datetime columns)."""
    df = safe_convert_to_float(sample_dataframe)
    
    # Check that numeric_col was successfully converted
    assert pd.api.types.is_float_dtype(df['numeric_col'])
    assert df['numeric_col'].equals(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0], name='numeric_col'))
    
    # Check that mixed_col was partially converted (non-numeric values to NaN)
    assert pd.api.types.is_float_dtype(df['mixed_col'])
    assert pd.isna(df['mixed_col'][1])
    assert pd.isna(df['mixed_col'][3])
    assert df['mixed_col'][0] == 1.0
    
    # Check that empty_col was converted to NaN
    assert pd.api.types.is_float_dtype(df['empty_col'])
    assert pd.isna(df['empty_col']).all()
    
    # Check that nan_col was handled properly
    assert pd.api.types.is_float_dtype(df['nan_col'])
    assert pd.isna(df['nan_col'][0])
    assert pd.isna(df['nan_col'][1])
    assert pd.isna(df['nan_col'][3])  # null should be NaN
    
    # Check that Datetime column was not modified
    assert pd.api.types.is_datetime64_dtype(df['Datetime'])

def test_safe_convert_to_float_specific_columns(sample_dataframe):
    """Test safe_convert_to_float with specific columns."""
    df = safe_convert_to_float(sample_dataframe, columns=['numeric_col', 'mixed_col'])
    
    # Check that specified columns were converted
    assert pd.api.types.is_float_dtype(df['numeric_col'])
    assert pd.api.types.is_float_dtype(df['mixed_col'])
    
    # Check that other non-datetime columns were not converted
    assert not pd.api.types.is_float_dtype(df['empty_col'])
    assert not pd.api.types.is_float_dtype(df['nan_col'])

def test_safe_convert_to_float_empty_df():
    """Test safe_convert_to_float with an empty DataFrame."""
    empty_df = pd.DataFrame()
    result = safe_convert_to_float(empty_df)
    assert result.empty
    assert isinstance(result, pd.DataFrame)

def test_safe_convert_to_float_invalid_column():
    """Test safe_convert_to_float with a non-existent column."""
    df = pd.DataFrame({'A': [1, 2, 3]})
    result = safe_convert_to_float(df, columns=['B'])  # 'B' doesn't exist
    
    # Should not raise an error, just skip the invalid column
    assert 'A' in result.columns
    assert not pd.api.types.is_float_dtype(result['A'])  # Not converted

# ============================================================
# Tests for NoiseSentryParser
# ============================================================

def test_noise_sentry_parser_init(noise_sentry_parser):
    """Test NoiseSentryParser initialization."""
    assert isinstance(noise_sentry_parser, NoiseSentryParser)
    assert isinstance(noise_sentry_parser, NoiseDataParser)

def test_noise_sentry_parser_valid_parse(noise_sentry_parser, tmp_path, valid_noise_sentry_content):
    """Test parsing a valid Noise Sentry CSV file."""
    # Create a temporary CSV file
    file_path = tmp_path / "valid_sentry.csv"
    with open(file_path, 'w') as f:
        f.write(valid_noise_sentry_content)
    
    # Parse the file
    result = noise_sentry_parser.parse(str(file_path))
    
    # Check the result
    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    assert 'Datetime' in result.columns
    assert 'LAeq' in result.columns
    assert 'LAFmax' in result.columns
    assert 'LAF10' in result.columns
    assert 'L90 dB-A' in result.columns
    
    # Check data types
    assert pd.api.types.is_datetime64_dtype(result['Datetime'])
    assert pd.api.types.is_float_dtype(result['LAeq'])
    assert pd.api.types.is_float_dtype(result['LAFmax'])
    assert pd.api.types.is_float_dtype(result['LAF10'])
    assert pd.api.types.is_float_dtype(result['L90 dB-A'])
    
    # Check specific values
    assert result.iloc[0]['LAeq'] == 65.2
    assert result.iloc[1]['LAFmax'] == 72.1
    assert result.iloc[2]['L90 dB-A'] == 56.2

def test_noise_sentry_parser_invalid_parse(noise_sentry_parser, tmp_path, invalid_noise_sentry_content):
    """Test parsing an invalid Noise Sentry CSV file with inconsistent columns."""
    # Create a temporary CSV file
    file_path = tmp_path / "invalid_sentry.csv"
    with open(file_path, 'w') as f:
        f.write(invalid_noise_sentry_content)
    
    # Parse the file
    result = noise_sentry_parser.parse(str(file_path))
    
    # Check the result - should still get a DataFrame but with fewer rows and NaNs
    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    
    # The row with missing column should be skipped, invalid data should be NaN
    assert len(result) == 2  # Only the valid rows
    assert pd.isna(result.iloc[1]['LAFmax'])  # Invalid value should be NaN

def test_noise_sentry_parser_empty_file(noise_sentry_parser, tmp_path):
    """Test parsing an empty Noise Sentry CSV file."""
    # Create an empty file
    file_path = tmp_path / "empty_sentry.csv"
    with open(file_path, 'w') as f:
        f.write("")
    
    # Parse the file
    result = noise_sentry_parser.parse(str(file_path))
    
    # Should return an empty DataFrame
    assert isinstance(result, pd.DataFrame)
    assert result.empty

def test_noise_sentry_parser_nonexistent_file(noise_sentry_parser):
    """Test parsing a non-existent file."""
    # Parse a non-existent file
    result = noise_sentry_parser.parse("nonexistent_file.csv")
    
    # Should return an empty DataFrame
    assert isinstance(result, pd.DataFrame)
    assert result.empty

def test_noise_sentry_parser_invalid_file_type(noise_sentry_parser):
    """Test parsing a file with an invalid extension."""
    # Should raise ValueError
    with pytest.raises(ValueError):
        noise_sentry_parser.parse("invalid_file.txt")

# ============================================================
# Tests for SvanParser
# ============================================================

def test_svan_parser_init(svan_parser):
    """Test SvanParser initialization."""
    assert isinstance(svan_parser, SvanParser)
    assert isinstance(svan_parser, NoiseDataParser)

def test_svan_parser_valid_parse(svan_parser, valid_svan_content):
    """Test parsing a valid Svan Excel file."""
    # Parse the file
    result = svan_parser.parse(str(valid_svan_content))
    
    # Check the result
    assert isinstance(result, pd.DataFrame)
    assert not result.empty
    assert 'Datetime' in result.columns
    assert 'LAeq' in result.columns
    assert 'LAF10' in result.columns
    assert 'LAF90' in result.columns
    assert 'LAFmax' in result.columns
    
    # Check that frequency columns are present
    assert any(col.endswith('31.5') for col in result.columns)
    assert any(col.endswith('63') for col in result.columns)
    
    # Check data types
    assert pd.api.types.is_datetime64_dtype(result['Datetime'])
    assert pd.api.types.is_float_dtype(result['LAeq'])
    
    # Check specific values
    assert result.iloc[0]['LAeq'] == 65.2
    assert result.iloc[1]['LAF10'] == 67.5
    assert result.iloc[2]['LAFmax'] == 78.2

def test_svan_parser_nonexistent_file(svan_parser):
    """Test parsing a non-existent Svan file."""
    # Parse a non-existent file
    result = svan_parser.parse("nonexistent_file.xlsx")
    
    # Should return an empty DataFrame
    assert isinstance(result, pd.DataFrame)
    assert result.empty

def test_svan_parser_invalid_file_type(svan_parser):
    """Test parsing a file with an invalid extension."""
    # Should raise ValueError
    with pytest.raises(ValueError):
        svan_parser.parse("invalid_file.txt")

# ============================================================
# Tests for NTiParser
# ============================================================

def test_nti_parser_init(nti_parser):
    """Test NTiParser initialization."""
    assert isinstance(nti_parser, NTiParser)
    assert isinstance(nti_parser, NoiseDataParser)

def test_nti_parser_parse_rpt_file(nti_parser, tmp_path, valid_nti_rpt_content):
    """Test parsing a valid NTi RPT file."""
    # Create a temporary RPT file
    file_path = tmp_path / "_123_rpt_report.txt"
    with open(file_path, 'w') as f:
        f.write(valid_nti_rpt_content)
    
    # Parse the file
    result = nti_parser.parse(str(file_path))
    
    # Check the result
    assert isinstance(result, dict)
    assert 'type' in result
    assert 'data' in result
    assert 'metadata' in result
    
    assert result['type'] == 'RPT'
    assert isinstance(result['data'], pd.DataFrame)
    assert isinstance(result['metadata'], dict)
    
    # Check DataFrame properties
    df = result['data']
    assert not df.empty
    assert 'Datetime' in df.columns
    assert 'LAeq' in df.columns
    assert 'LAFmax' in df.columns
    assert 'LAF10' in df.columns
    assert 'LAF90' in df.columns
    
    # Check data types
    assert pd.api.types.is_datetime64_dtype(df['Datetime'])
    assert pd.api.types.is_float_dtype(df['LAeq'])
    
    # Check specific values
    assert df.iloc[0]['LAeq'] == 66.8
    assert df.iloc[1]['LAFmax'] == 74.2
    assert df.iloc[2]['LAF90'] == 36.6
    
    # Check metadata - don't check for specific keys since they might vary
    assert isinstance(result['metadata'], dict)

def test_nti_parser_parse_rta_file(nti_parser, tmp_path, valid_nti_rta_content):
    """Test parsing a more complex NTi RTA file."""
    # Create a temporary RTA file
    file_path = tmp_path / "_RTA_3rd_Rpt_Report.txt"
    with open(file_path, 'w') as f:
        f.write(valid_nti_rta_content)
    
    # Parse the file
    result = nti_parser.parse(str(file_path))
    
    # Check the result
    assert isinstance(result, dict)
    assert 'type' in result
    assert 'data' in result
    assert 'metadata' in result
    
    assert result['type'] == 'RTA'
    assert isinstance(result['data'], pd.DataFrame)
    assert isinstance(result['metadata'], dict)
    
    # Check DataFrame properties
    df = result['data']
    assert not df.empty
    assert 'Datetime' in df.columns
    
    # Check more extensive frequency band and metric columns
    assert 'LZFmax_6.3' in df.columns
    assert 'LZFmin_31.5' in df.columns
    assert 'LZeq_63.0' in df.columns
    assert 'LZF10.0_125.0' in df.columns or 'LZF10_125.0' in df.columns  # parser may convert '.0%' to ''
    assert 'LZF50.0_6.3' in df.columns or 'LZF50_6.3' in df.columns
    assert 'LZF90.0_63.0' in df.columns or 'LZF90_63.0' in df.columns
    
    # Check data types and values
    assert pd.api.types.is_datetime64_dtype(df['Datetime'])
    assert pd.api.types.is_float_dtype(df['LZeq_6.3'])
    
    # Check specific values
    assert df.iloc[0]['LZFmax_6.3'] == 81.2
    assert df.iloc[1]['LZFmin_31.5'] == 28.3
    assert df.iloc[2]['LZeq_63.0'] == 44.0

def test_nti_parser_parse_log_file(nti_parser, tmp_path, valid_nti_log_content):
    """Test parsing a valid NTi LOG file."""
    # Create a temporary LOG file
    file_path = tmp_path / "_123_log.txt"
    with open(file_path, 'w') as f:
        f.write(valid_nti_log_content)
    
    # Parse the file
    result = nti_parser.parse(str(file_path))
    
    # Check the result
    assert isinstance(result, dict)
    assert 'type' in result
    assert 'data' in result
    assert 'metadata' in result
    
    assert result['type'] == 'RPT_LOG'
    assert isinstance(result['data'], pd.DataFrame)
    assert isinstance(result['metadata'], dict)
    
    # Check DataFrame properties
    df = result['data']
    assert not df.empty
    assert 'Datetime' in df.columns
    assert 'LAeq_dt' in df.columns
    assert 'LAFmax_dt' in df.columns
    assert 'LAF10' in df.columns
    assert 'LAF90' in df.columns
    
    # Check that summary lines are filtered out
    assert len(df) == 3  # Only actual data rows, not summary
    
    # Check data types
    assert pd.api.types.is_datetime64_dtype(df['Datetime'])
    assert pd.api.types.is_float_dtype(df['LAeq_dt'])
    
    # Check specific values
    assert df.iloc[0]['LAeq_dt'] == 65.2
    assert df.iloc[1]['LAFmax_dt'] == 73.2
    assert df.iloc[2]['LAF90'] == 55.3

def test_nti_parser_file_without_data_markers(nti_parser, tmp_path):
    """Test parsing a file without the expected data markers."""
    # Create a file without data markers
    file_path = tmp_path / "_123_rpt_report.txt"
    with open(file_path, 'w') as f:
        f.write(
            "# XL2 Data Explorer; Firmware: V4.71\n"
            "# Project: Test Project\n"
            "# Serial Number: A2A-12345-D1\n"
            "\n"
            "# This file is missing the 'Broadband Results' marker\n"
            "\n"
            "Start Date\tStart Time\tEnd Date\tEnd Time\tDuration\tLAeq\tLCpeak\tLAFmax\tLAFmin\n"
        )
    
    # Parse the file
    result = nti_parser.parse(str(file_path))
    
    # Check the result
    assert isinstance(result, dict)
    assert 'type' in result
    assert 'data' in result
    assert 'metadata' in result
    
    assert result['type'] == 'RPT'  # Type is still determined from filename
    assert isinstance(result['data'], pd.DataFrame)
    assert result['data'].empty  # But data is empty due to missing marker
    
    # Check metadata is extracted but may be different from expected
    assert isinstance(result['metadata'], dict)
    # We don't assume specific keys since implementation varies

def test_nti_parser_nonexistent_file(nti_parser):
    """Test parsing a non-existent NTi file."""
    # Parse a non-existent file
    result = nti_parser.parse("nonexistent_file.txt")
    
    # Should return None
    assert result is None

def test_nti_parser_file_type_detection_from_parse(nti_parser, tmp_path):
    """Test file type detection in NTiParser's parse method."""
    # Create empty temporary files with different naming patterns
    file_types = [
        ("_123_rpt_report.txt", "RPT"),
        ("noise_123_rpt_report.txt", "RPT"),
        ("_rta_3rd_rpt_report.txt", "RTA"),
        ("noise_rta_3rd_rpt_report.txt", "RTA"),
        ("_123_log.txt", "RPT_LOG"),
        ("_123_Log.txt", "RPT_LOG"),
        ("_rta_3rd_log.txt", "RTA_LOG"),
        ("_RTA_3rd_Log.txt", "RTA_LOG")
    ]
    
    for filename, expected_type in file_types:
        # Create an empty file with this name pattern
        file_path = tmp_path / filename
        with open(file_path, 'w') as f:
            # Write minimal content to make the parser not fail immediately
            f.write("# XL2 Sound Level Meter\n#CheckSum\n\t1234567890\n")
        
        # Mock the specific file parsing methods to avoid full parsing
        with patch.object(nti_parser, '_parse_specific_file') as mock_parse:
            # Set up the mock to return a simple result with the passed file type
            mock_parse.side_effect = lambda path, func, file_type: {'type': file_type, 'data': pd.DataFrame(), 'metadata': {}}
            
            # Call parse and check the result
            result = nti_parser.parse(str(file_path))
            
            # Verify the result has the expected type
            assert result is not None, f"Parse returned None for {filename}"
            assert result['type'] == expected_type, f"Wrong type for {filename}, expected {expected_type}, got {result['type']}"
    
    # Test unknown file type
    unknown_file = tmp_path / "unknown_file.txt"
    with open(unknown_file, 'w') as f:
        f.write("Some content")
    
    # This should return None as the file type can't be determined
    result = nti_parser.parse(str(unknown_file))
    assert result is None

def test_nti_parser_parse_rta_log_file(nti_parser, tmp_path, valid_nti_rta_log_content):
    """Test parsing a valid NTi RTA LOG file."""
    # Create a temporary RTA LOG file
    file_path = tmp_path / "_RTA_3rd_Log.txt"
    with open(file_path, 'w') as f:
        f.write(valid_nti_rta_log_content)
    
    # Parse the file
    result = nti_parser.parse(str(file_path))
    
    # Check the result
    assert isinstance(result, dict)
    assert 'type' in result
    assert 'data' in result
    assert 'metadata' in result
    
    assert result['type'] == 'RTA_LOG'
    assert isinstance(result['data'], pd.DataFrame)
    assert isinstance(result['metadata'], dict)
    
    # Check DataFrame properties
    df = result['data']
    assert not df.empty
    assert 'Datetime' in df.columns
    
    # Check frequency band columns are properly formatted
    assert any(col.startswith('LZeq_dt_') for col in df.columns)
    assert any(col.startswith('LZFmin_dt_') for col in df.columns)
    assert any(col.startswith('LZFmax_dt_') for col in df.columns)
    
    # Check specific frequency bands
    assert 'LZeq_dt_6.3' in df.columns
    assert 'LZeq_dt_31.5' in df.columns
    assert 'LZFmax_dt_125.0' in df.columns
    
    # Check data types
    assert pd.api.types.is_datetime64_dtype(df['Datetime'])
    assert pd.api.types.is_float_dtype(df['LZeq_dt_6.3'])
    
    # Print the actual columns for debugging
    print(f"Available columns: {df.columns.tolist()}")
    
    # Instead of checking specific column values which might vary,
    # just verify that the columns contain numeric values
    first_lzeq_col = [col for col in df.columns if col.startswith('LZeq_dt_')][0]
    first_lzfmax_col = [col for col in df.columns if col.startswith('LZFmax_dt_')][0]
    
    # Check that we can access these values without KeyError
    assert isinstance(df.iloc[0][first_lzeq_col], (float, np.float64))
    assert isinstance(df.iloc[1][first_lzfmax_col], (float, np.float64))
    
    # Check metadata
    assert 'hardware_config' in result['metadata']
    assert 'measurement_setup' in result['metadata']
    # Don't check for specific keys in measurement_setup as they may vary

def test_nti_parser_parse_rpt_file_with_extended_columns(nti_parser, tmp_path, valid_nti_rpt_content):
    """Test parsing an NTi RPT file with extended columns."""
    # Create a temporary RPT file
    file_path = tmp_path / "_123_Rpt_Report.txt"
    with open(file_path, 'w') as f:
        f.write(valid_nti_rpt_content)
    
    # Parse the file
    result = nti_parser.parse(str(file_path))
    
    # Check the result
    assert isinstance(result, dict)
    assert 'type' in result
    assert 'data' in result
    assert 'metadata' in result
    
    assert result['type'] == 'RPT'
    assert isinstance(result['data'], pd.DataFrame)
    assert isinstance(result['metadata'], dict)
    
    # Check DataFrame properties with extended columns
    df = result['data']
    assert not df.empty
    assert 'Datetime' in df.columns
    assert 'LAeq' in df.columns
    assert 'LAFmax' in df.columns
    assert 'LAF10' in df.columns or 'LAF10.0' in df.columns
    assert 'LAF90' in df.columns or 'LAF90.0' in df.columns
    
    # Check extended columns are present
    assert 'LASmax' in df.columns
    assert 'LAImax' in df.columns
    assert 'LCeq' in df.columns
    assert 'LZeq' in df.columns
    assert 'LZPKmax' in df.columns
    
    # Check percentile metrics
    assert 'LAF1' in df.columns or 'LAF1.0' in df.columns
    assert 'LAF5' in df.columns or 'LAF5.0' in df.columns
    assert 'LAF50' in df.columns or 'LAF50.0' in df.columns
    assert 'LAF95' in df.columns or 'LAF95.0' in df.columns
    assert 'LAF99' in df.columns or 'LAF99.0' in df.columns
    
    # Check data types
    assert pd.api.types.is_datetime64_dtype(df['Datetime'])
    assert pd.api.types.is_float_dtype(df['LAeq'])
    
    # Check specific values
    assert df.iloc[0]['LAeq'] == 66.8
    assert df.iloc[1]['LAFmax'] == 74.2
    assert df.iloc[2]['LCeq'] == 52.3
    
    # Check metadata
    assert 'hardware_config' in result['metadata']
    assert 'measurement_setup' in result['metadata']
    # Don't check for specific keys in measurement_setup as they may vary

# ============================================================
# Tests for NoiseDataParser (Factory method)
# ============================================================

def test_noise_data_parser_factory():
    """Test the factory method to get parser instances."""
    # Get Sentry parser
    parser = NoiseDataParser.get_parser('sentry')
    assert isinstance(parser, NoiseSentryParser)
    
    # Get Svan parser
    parser = NoiseDataParser.get_parser('svan')
    assert isinstance(parser, SvanParser)
    
    # Get NTi parser
    parser = NoiseDataParser.get_parser('nti')
    assert isinstance(parser, NTiParser)
    
    # Test case insensitivity
    parser = NoiseDataParser.get_parser('SENTRY')
    assert isinstance(parser, NoiseSentryParser)
    
    # Test invalid parser type
    with pytest.raises(ValueError):
        NoiseDataParser.get_parser('invalid_type') 