import pandas as pd
import numpy as np
import os

# File paths
input_file = r"G:\Shared drives\Venta\Jobs\5764 Shell Larkshall Road, 470 Larkshall Road, Waltham Forest\5764 Surveys\5764 Shell Larkshall Road, 470 _2025_04_02__15h18m45s_2025_04_02__11h26m02s.csv"
file_dir = os.path.dirname(input_file)
file_name = os.path.basename(input_file)
output_file = os.path.join(file_dir, f"{os.path.splitext(file_name)[0]}_1second_data.csv")

# Read the data
df = pd.read_csv(input_file, parse_dates=[0])

# Rename columns to remove spaces and make them easier to work with
df.columns = [col.strip() for col in df.columns]
df.rename(columns={"Time (Date hh:mm:ss.ms)": "Time", "LEQ dB-A": "LAeq"}, inplace=True)

# Convert LAeq from dB to linear scale for averaging
df['LAeq_linear'] = 10 ** (df['LAeq'] / 10)

# Resample to 1-second intervals and calculate logarithmic average
# First set the time column as the index
df.set_index('Time', inplace=True)

# Resample and apply logarithmic averaging
resampled = df.resample('1S')['LAeq_linear'].mean()

# Convert back to dB scale
resampled_db = 10 * np.log10(resampled)

# Create new dataframe with resampled data
result_df = pd.DataFrame({'Time': resampled.index, 'LAeq': resampled_db})
result_df.reset_index(drop=True, inplace=True)

# Save to new file
result_df.to_csv(output_file, index=False)

print(f"Processing complete. Output saved to: {output_file}") 