import pandas as pd
import numpy as np
import os
from pathlib import Path
from typing import Any

# ==================== CONFIGURATION VARIABLES ====================
# Input folder containing multiple parquet files
INPUT_FOLDER = "data/parts/"

# Output file path (full path with filename)
OUTPUT_FILE = "data/allmetadata.parquet"

# File pattern to match (e.g., "*.parquet" for all parquet files)
FILE_PATTERN = "*.parquet"

# Compression codec for output file ('snappy', 'gzip', 'brotli', 'lz4', 'zstd', or None)
COMPRESSION = "snappy"

# Whether to reset index in the combined dataframe
RESET_INDEX = True

# Whether to print progress information
VERBOSE = True
# =================================================================


def is_list_like(value: Any) -> bool:
    """Check if a value is list-like (list, tuple, numpy array, etc.)"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return False
    return isinstance(value, (list, tuple, np.ndarray))


def normalize_mixed_types(value: Any) -> Any:
    """
    Normalizes mixed-type values (lists, strings, etc.) to consistent types.
    Lists are converted to comma-separated strings for consistency.
    """
    # Handle None and NaN
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    
    # Convert lists/arrays to comma-separated strings
    if is_list_like(value):
        try:
            # Handle numpy arrays
            if isinstance(value, np.ndarray):
                value = value.tolist()
            
            # Filter out empty/None values and convert to strings
            clean_list = [str(v).strip() for v in value if v is not None and str(v).strip()]
            return ', '.join(clean_list) if clean_list else None
        except Exception as e:
            print(f"    Warning: Error converting list-like value: {e}")
            return str(value) if value else None
    
    # Return strings as-is (stripped)
    if isinstance(value, str):
        return value.strip() or None
    
    # Convert other types to string
    return str(value) if value is not None else None


def detect_mixed_types_in_column(series: pd.Series) -> bool:
    """
    Detect if a column has mixed list and non-list types.
    Uses a more robust check that handles numpy arrays and pandas data structures.
    """
    has_list_like = False
    has_non_list_like = False
    
    # Sample up to 1000 non-null values for efficiency
    non_null_values = series.dropna()
    sample_size = min(len(non_null_values), 1000)
    sample = non_null_values.sample(n=sample_size, random_state=42) if len(non_null_values) > sample_size else non_null_values
    
    for val in sample:
        if is_list_like(val):
            has_list_like = True
        else:
            has_non_list_like = True
        
        # Early exit if we found both types
        if has_list_like and has_non_list_like:
            return True
    
    return False


def fix_dataframe_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fixes mixed-type columns in the dataframe to ensure Parquet compatibility.
    """
    print("\nChecking for mixed-type columns...")
    
    fixed_columns = []
    
    for col in df.columns:
        # Skip columns that are already consistent numeric types
        if df[col].dtype in ['int64', 'float64', 'bool', 'datetime64[ns]']:
            continue
        
        # Check if column has mixed list/non-list types
        if detect_mixed_types_in_column(df[col]):
            print(f"  Normalizing mixed-type column: '{col}'")
            df[col] = df[col].apply(normalize_mixed_types)
            fixed_columns.append(col)
        else:
            # Check if all non-null values are list-like
            non_null = df[col].dropna()
            if len(non_null) > 0:
                first_non_null = non_null.iloc[0]
                if is_list_like(first_non_null):
                    # Sample to verify all are list-like
                    sample_size = min(len(non_null), 100)
                    sample = non_null.sample(n=sample_size, random_state=42) if len(non_null) > sample_size else non_null
                    all_list_like = all(is_list_like(val) for val in sample)
                    
                    if all_list_like:
                        print(f"  Converting list column to strings: '{col}'")
                        df[col] = df[col].apply(normalize_mixed_types)
                        fixed_columns.append(col)
    
    if fixed_columns:
        print(f"\nFixed {len(fixed_columns)} columns with type inconsistencies")
    else:
        print("  No mixed-type columns found")
    
    return df


def validate_for_parquet(df: pd.DataFrame) -> tuple[bool, list]:
    """
    Validate that all columns are safe to write to Parquet.
    Returns (is_valid, list_of_problematic_columns)
    """
    print("\nValidating dataframe for Parquet compatibility...")
    problematic = []
    
    for col in df.columns:
        try:
            # Try to convert to PyArrow
            import pyarrow as pa
            pa.array(df[col])
        except Exception as e:
            problematic.append((col, str(e)))
    
    if problematic:
        print(f"  Found {len(problematic)} problematic columns")
        for col, error in problematic:
            print(f"    - {col}: {error}")
        return False, [col for col, _ in problematic]
    else:
        print("  All columns are Parquet-compatible")
        return True, []


def force_fix_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """
    Force-fix specific columns by converting all values to strings.
    """
    print(f"\nForce-fixing {len(columns)} columns...")
    for col in columns:
        print(f"  Converting '{col}' to strings")
        df[col] = df[col].apply(normalize_mixed_types)
    return df


def combine_parquet_files(input_folder, output_file, file_pattern, 
                          compression, reset_index):
    input_path = Path(input_folder)
    parquet_files = sorted(list(input_path.glob(file_pattern)))
    
    if not parquet_files:
        print(f"No parquet files found matching pattern '{file_pattern}' in {input_folder}")
        return
    
    print(f"Found {len(parquet_files)} parquet files")
    print("Files to combine:")
    for f in parquet_files:
        print(f"  -> {f.name}")
    print()
    
    # Read and combine all parquet files
    dfs = []
    for i, file_path in enumerate(parquet_files, 1):
        print(f"Reading file {i}/{len(parquet_files)}: {file_path.name}")
        
        try:
            df = pd.read_parquet(file_path)
            dfs.append(df)
            print(f"  Rows: {len(df)}, Columns: {len(df.columns)}")
        except Exception as e:
            print(f"  ERROR reading {file_path.name}: {e}")
            print(f"  Skipping this file...")
            continue
    
    if not dfs:
        print("\nNo dataframes were successfully loaded!")
        return
    
    # Concatenate all dataframes
    print("\nCombining dataframes...")
    combined_df = pd.concat(dfs, ignore_index=reset_index)
    
    print(f"Combined dataframe shape: {combined_df.shape}")
    print(f"Total rows: {len(combined_df)}")
    print(f"Total columns: {len(combined_df.columns)}")
    
    # Fix mixed-type columns before saving
    combined_df = fix_dataframe_types(combined_df)
    
    # Validate and force-fix if needed
    is_valid, problematic = validate_for_parquet(combined_df)
    if not is_valid:
        combined_df = force_fix_columns(combined_df, problematic)
        # Validate again
        is_valid, still_problematic = validate_for_parquet(combined_df)
        if not is_valid:
            print("\n✗ ERROR: Some columns still cannot be converted after force-fixing!")
            for col in still_problematic:
                print(f"\nDumping sample values from '{col}':")
                print(combined_df[col].head(10))
            return
    
    # Create output directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Save combined dataframe to parquet
    print(f"\nSaving to {output_file}...")
    
    try:
        combined_df.to_parquet(output_file, compression=compression, index=False)
        
        file_size = os.path.getsize(output_file) / (1024 * 1024)  # Size in MB
        print(f"\n✓ Successfully saved! File size: {file_size:.2f} MB")
        
        # Print summary statistics
        print("\nDataset Summary:")
        print(f"  Total floats: {len(combined_df)}")
        print(f"  Total columns: {len(combined_df.columns)}")
        print(f"  Memory usage: {combined_df.memory_usage(deep=True).sum() / 1024 / 1024:.2f} MB")
        
        # Show column names
        print(f"\nColumns in merged file:")
        for i, col in enumerate(combined_df.columns, 1):
            print(f"  {i:2d}. {col}")
            
    except Exception as e:
        print(f"\n✗ ERROR saving to Parquet: {e}")
        raise


if __name__ == "__main__":
    combine_parquet_files(
        input_folder=INPUT_FOLDER,
        output_file=OUTPUT_FILE,
        file_pattern=FILE_PATTERN,
        compression=COMPRESSION,
        reset_index=RESET_INDEX
    )