import pandas as pd
import numpy as np
import os

# --- Configuration ---
# Set the path to your input data file here.
# This example path is based on the one in your request.
input_file = r"C:\Users\steve\OneDrive\Documents\Convergence_Instruments\All_Instruments\Records\5973 1-a Norfolk Feather Site, _2025_07_03__16h34m10s_2025_07_01__10h44m01s.csv"

# --- Automatic File Path Generation ---
# Derive output file paths from the input file name.
file_dir = os.path.dirname(input_file)
file_name = os.path.basename(input_file)
file_base, _ = os.path.splitext(file_name)

output_file_log = os.path.join(file_dir, f"{file_base}_log.csv")
output_file_summary = os.path.join(file_dir, f"{file_base}_summary.csv")


def aggregate_noise_data(df_indexed, rule):
    """
    Resamples and aggregates noise data to a specified time interval.

    Args:
        df_indexed (pd.DataFrame): The input DataFrame with a datetime index and columns 
                                   'LAeq', 'Lmax', and 'LAeq_linear'.
        rule (str): The resampling rule string (e.g., '1S' for 1 second, 
                    '5T' for 5 minutes).

    Returns:
        pd.DataFrame: A new DataFrame with aggregated noise data and standard column names.
    """
    # Create a resampler object based on the specified time interval rule.
    resampler = df_indexed.resample(rule)

    # 1. Calculate aggregated LAeq (Logarithmic Average)
    # The mean of the linear energy values is calculated first.
    laeq_linear_mean = resampler['LAeq_linear'].mean()
    # Then it's converted back to decibels. An offset is added to avoid log(0) errors.
    laeq_agg = 10 * np.log10(laeq_linear_mean.where(laeq_linear_mean > 0, np.nan))
    laeq_agg.name = 'LEQ dB-A'

    # 2. Calculate aggregated Lmax (the highest of all Lmax values in the interval)
    lmax_agg = resampler['Lmax'].max()
    lmax_agg.name = 'Lmax dB-A'

    # 3. Calculate L10 and L90 from the distribution of the original LAeq values.
    # L10 is the sound level exceeded 10% of the time, which is the 90th percentile.
    l10_agg = resampler['LAeq'].quantile(0.90)
    l10_agg.name = 'L10 dB-A'
    
    # L90 is the sound level exceeded 90% of the time, which is the 10th percentile.
    l90_agg = resampler['LAeq'].quantile(0.10)
    l90_agg.name = 'L90 dB-A'
    
    # 4. Combine the aggregated series into a single DataFrame
    result_df = pd.concat([laeq_agg, lmax_agg, l10_agg, l90_agg], axis=1)
    
    # Drop rows where all values are NaN (this happens for intervals that had no source data)
    result_df.dropna(how='all', inplace=True)
    
    # Reset the index to turn the 'Time' index back into a column
    result_df.reset_index(inplace=True)
    
    # Rename the 'Time' column back to the original desired format
    result_df.rename(columns={'Time': 'Time (Date hh:mm:ss.ms)'}, inplace=True)
    
    return result_df

# --- Main Script Execution ---

# 1. Read and clean the input data
print(f"Reading input file: {input_file}")
try:
    # Use skipinitialspace=True to handle potential spaces after commas in the header
    df = pd.read_csv(input_file, parse_dates=[0], skipinitialspace=True)
except FileNotFoundError:
    print(f"Error: The file was not found at the specified path.")
    print(f"Path: {input_file}")
    exit()
except Exception as e:
    print(f"An error occurred while reading the CSV file: {e}")
    exit()

# Clean up column names by stripping leading/trailing whitespace
df.columns = [col.strip() for col in df.columns]

# Drop any "Unnamed" columns that can be created by trailing commas in the CSV header
df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

# 2. Prepare data for aggregation
# Define a mapping for renaming columns to a simple, standard format for internal processing
column_rename_map = {
    "Time (Date hh:mm:ss.ms)": "Time",
    "LEQ dB-A": "LAeq",
    "Lmax dB-A": "Lmax"
    # We ignore input L10/L90 as they must be recalculated for the new time periods
}
# Keep only the columns we need and rename them
df = df[list(column_rename_map.keys())].rename(columns=column_rename_map)


# Convert LAeq from decibels (dB) to a linear energy scale for correct averaging
df['LAeq_linear'] = 10 ** (df['LAeq'] / 10)

# Set the 'Time' column as the DataFrame index, which is required for resampling
df.set_index('Time', inplace=True)

# 3. Generate 1-second log data
print("Processing 1-second log data...")
log_df = aggregate_noise_data(df, '1S')

# 4. Generate 5-minute summary data
print("Processing 5-minute summary data...")
summary_df = aggregate_noise_data(df, '5T')

# 5. Save the results to new CSV files
# The float_format parameter ensures consistent decimal precision in the output file.
if not log_df.empty:
    log_df.to_csv(output_file_log, index=False, float_format='%.6f')
    print(f"✔ 1-second log data saved to: {output_file_log}")
else:
    print("No 1-second data was generated.")

if not summary_df.empty:
    summary_df.to_csv(output_file_summary, index=False, float_format='%.6f')
    print(f"✔ 5-minute summary data saved to: {output_file_summary}")
else:
    print("No 5-minute data was generated.")

print("\nProcessing complete.")