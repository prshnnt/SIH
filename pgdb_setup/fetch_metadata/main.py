# from utils import ArgoMetadataExtractor

# extractor = ArgoMetadataExtractor()
# float_list = extractor.load_float_list("float_list_oferror.csv")

# import sys

# lower_bound = 0 #int(sys.argv[1])
# upper_bound = len(float_list) #int(sys.argv[2])

# extractor.extract_multiple_floats(float_list[lower_bound:upper_bound], "data/parts/metadata_error_"+str(lower_bound)+"-"+str(upper_bound)+".parquet")

import pandas as pd
import os
from pathlib import Path

# ==================== CONFIGURATION VARIABLES ====================
# Input folder containing multiple parquet files
INPUT_FOLDER = "data/parts/"

# Output file path (full path with filename)
OUTPUT_FILE = "./data/allmetadata.parquet"

# File pattern to match (e.g., "*.parquet" for all parquet files)
FILE_PATTERN = "*.parquet"

# Compression codec for output file ('snappy', 'gzip', 'brotli', 'lz4', 'zstd', or None)
COMPRESSION = "snappy"

# Whether to reset index in the combined dataframe
RESET_INDEX = True

# Whether to print progress information
VERBOSE = True
# =================================================================


def combine_parquet_files(input_folder, output_file, file_pattern, 
                          compression, reset_index):
    input_path = Path(input_folder)
    parquet_files = list(input_path.glob(file_pattern))
    
    print(f"Found {len(parquet_files)} parquet files")
    print("Files to combine:")
    for f in parquet_files:
        print(f"  -> {f.name}")
    print('/n')
    
    # Read and combine all parquet files
    dfs = []
    for i, file_path in enumerate(parquet_files, 1):
        print(f"Reading file {i}/{len(parquet_files)}: {file_path.name}")
        
        df = pd.read_parquet(file_path)
        dfs.append(df)
        
        print(f"  Rows: {len(df)}, Columns: {len(df.columns)}")
    
    # Concatenate all dataframes
    print("\nCombining dataframes...")

    combined_df = pd.concat(dfs, ignore_index=reset_index)

    print(f"Combined dataframe shape: {combined_df.shape}")
    print(f"Total rows: {len(combined_df)}")
    print(f"Total columns: {len(combined_df.columns)}")
    
    # Create output directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save combined dataframe to parquet
    print(f"\nSaving to {output_file}...")
    
    combined_df.to_parquet(output_file, compression=compression, index=False)

    file_size = os.path.getsize(output_file) / (1024 * 1024)  # Size in MB
    print(f"Successfully saved! File size: {file_size:.2f} MB")


if __name__ == "__main__":
    combine_parquet_files(
        input_folder=INPUT_FOLDER,
        output_file=OUTPUT_FILE,
        file_pattern=FILE_PATTERN,
        compression=COMPRESSION,
        reset_index=RESET_INDEX
    )