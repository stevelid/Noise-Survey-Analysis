import sys
from noise_survey_analysis.core.data_parsers import NoiseDataParser

CSV_PATH = r"G:\Shared drives\Venta\Jobs\5879 Land At Redhayes, Exeter\5879 Surveys\5879 Svan\L242_summary.csv"

if __name__ == "__main__":
    # Try NoiseSentryParser first
    print(f"Attempting to parse as Svan CSV: {CSV_PATH}")
    try:
        svan_parser = NoiseDataParser.get_parser("svan")
        svan_df = svan_parser.parse(CSV_PATH)
        print("Svan parse result:")
        print(svan_df.head())
        print(f"Shape: {svan_df.shape}")
    except Exception as e:
        print(f"Svan parse failed: {e}")
        print("\nTrying SvanParser as fallback...")
        try:
            svan_parser = NoiseDataParser.get_parser("svan")
            svan_df = svan_parser.parse(CSV_PATH)
            print("Svan parse result:")
            print(svan_df.head())
            print(f"Shape: {svan_df.shape}")
        except Exception as e2:
            print(f"Svan parse failed: {e2}")
            sys.exit(1)
    print("\nParsing complete.")
