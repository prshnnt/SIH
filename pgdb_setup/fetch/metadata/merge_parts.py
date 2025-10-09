import pandas as pd
import numpy as np
import os
import json
from pathlib import Path
from typing import Any
import pyarrow as pa
import pyarrow.parquet as pq

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

def safe_to_list(value: Any) -> Any:
    """Safely convert various types to Python list or None"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None

    # Already a Python list
    if isinstance(value, list):
        return value

    # Numpy array - convert to list
    if isinstance(value, np.ndarray):
        return value.tolist()

    # Tuple - convert to list
    if isinstance(value, tuple):
        return list(value)

    # Single value - wrap in list
    return [value]

def parse_json_string(value: Any) -> Any:
    """Parse JSON strings into Python objects (lists/dicts)"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None

    if isinstance(value, str):
        # Try to parse as JSON
        try:
            parsed = json.loads(value)
            return parsed
        except (json.JSONDecodeError, ValueError):
            # Not JSON, return as-is
            return value

    return value

def parse_comma_separated(value: Any) -> list:
    """Parse comma-separated strings into lists, handle numpy arrays"""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None

    # Already a list/array - convert to Python list
    if isinstance(value, (list, tuple)):
        return list(value)

    if isinstance(value, np.ndarray):
        return value.tolist()

    if isinstance(value, str):
        # Split by comma and clean
        items = [item.strip() for item in value.split(',') if item.strip()]
        return items if items else None

    # Single value - wrap in list
    return [value]

def normalize_list_values(value: Any, force_strings: bool = False) -> list:
    """
    Normalize list values to handle mixed types (floats, numpy arrays, nested lists)
    Returns a simple Python list or None

    Args:
        force_strings: If True, convert all list items to strings
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None

    # Handle numpy arrays
    if isinstance(value, np.ndarray):
        result = value.tolist()
        # Flatten if single nested list
        if isinstance(result, list) and len(result) == 1 and isinstance(result[0], list):
            result = result[0]
    # Already a list
    elif isinstance(value, list):
        # Flatten if single nested list
        if len(value) == 1 and isinstance(value[0], list):
            result = value[0]
        else:
            result = value
    elif isinstance(value, tuple):
        result = list(value)
    # Try parsing as JSON if string
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                result = parsed
            else:
                result = [str(parsed)]
        except:
            # Parse as comma-separated
            result = parse_comma_separated(value)
    else:
        # Single value
        result = [value]

    # Convert all items to strings if requested
    if force_strings and result is not None:
        string_result = []
        for item in result:
            if item is None or (isinstance(item, float) and np.isnan(item)):
                string_result.append(None)
            else:
                string_result.append(str(item))
        return string_result

    return result

def convert_to_config_dict_list(params: Any, values: Any) -> list:
    """
    Convert parallel parameter and value lists into list of dicts.
    Example: ['param1', 'param2'], [100, 200] -> [{'parameter': 'param1', 'value': '100'}, {'parameter': 'param2', 'value': '200'}]
    """
    if params is None or values is None:
        return None

    # Normalize both to lists
    params = normalize_list_values(params)
    values = normalize_list_values(values, force_strings=True)  # Force values to strings for consistency

    if params is None or values is None:
        return None

    if not isinstance(params, list) or not isinstance(values, list):
        return None

    # Create list of dicts
    result = []
    for i in range(min(len(params), len(values))):
        param_val = params[i]
        value_val = values[i]

        # Skip if parameter is None/empty
        if param_val is None or (isinstance(param_val, str) and not param_val.strip()):
            continue

        # Convert both to strings for consistency
        result.append({
            'parameter': str(param_val).strip(),
            'value': str(value_val) if value_val is not None else None
        })

    return result if result else None

def prepare_dataframe_for_arrow(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare dataframe by converting string representations to actual lists/dicts
    """
    print("\nPreparing dataframe for Arrow schema...")

    df = df.copy()

    # Columns that should be lists of strings
    list_string_columns = [
        'sensors', 'sensor_makers', 'sensor_models', 'sensor_serial_numbers',
        'launch_config_parameters', 'config_parameters'
    ]

    # Columns that need normalization to lists of strings (force string conversion)
    list_value_columns = ['launch_config_values', 'config_values']

    # Columns that need JSON parsing (already stored as JSON strings)
    json_columns = ['sensor_details']

    # Process list columns (keep as strings)
    for col in list_string_columns:
        if col in df.columns:
            print(f"  Converting '{col}' to list of strings...")
            df[col] = df[col].apply(parse_comma_separated)

    # Process value list columns (force to strings for consistency)
    for col in list_value_columns:
        if col in df.columns:
            print(f"  Normalizing '{col}' to list of strings...")
            df[col] = df[col].apply(lambda x: normalize_list_values(x, force_strings=True))

    # Process JSON columns
    for col in json_columns:
        if col in df.columns:
            print(f"  Parsing JSON in '{col}'...")
            df[col] = df[col].apply(parse_json_string)

    # Create structured config columns from parallel lists
    if 'launch_config_parameters' in df.columns and 'launch_config_values' in df.columns:
        print("  Creating 'launch_config' from parameters and values...")
        df['launch_config'] = df.apply(
            lambda row: convert_to_config_dict_list(
                row.get('launch_config_parameters'),
                row.get('launch_config_values')
            ),
            axis=1
        )

    if 'config_parameters' in df.columns and 'config_values' in df.columns:
        print("  Creating 'config' from parameters and values...")
        df['config'] = df.apply(
            lambda row: convert_to_config_dict_list(
                row.get('config_parameters'),
                row.get('config_values')
            ),
            axis=1
        )

    return df

def infer_arrow_type_from_sample(series: pd.Series, col_name: str) -> pa.DataType:
    """
    Infer Arrow type from non-null samples in the series
    """
    # Get non-null samples
    non_null = series.dropna()
    if len(non_null) == 0:
        return pa.string()  # Default

    # Check first non-null value
    sample = non_null.iloc[0]

    # List of strings
    if isinstance(sample, list):
        if len(sample) == 0:
            return pa.list_(pa.string())

        first_item = sample[0]

        # List of dicts (structs)
        if isinstance(first_item, dict):
            # Infer struct fields from first dict
            fields = []
            for key, val in first_item.items():
                fields.append(pa.field(key, pa.string()))  # Store all as strings for simplicity
            return pa.list_(pa.struct(fields))
        else:
            # List of primitives - assume strings
            return pa.list_(pa.string())

    # Default to string
    return pa.string()

def create_arrow_schema(df: pd.DataFrame) -> pa.Schema:
    """
    Create PyArrow schema with explicit nested types
    """
    print("\nCreating PyArrow schema with nested types...")

    fields = []

    # Define special column types - ALL LIST COLUMNS AS STRING LISTS
    list_string_columns = {
        'sensors', 'sensor_makers', 'sensor_models', 'sensor_serial_numbers',
        'launch_config_parameters', 'config_parameters', 
        'launch_config_values', 'config_values'  # These are now forced to strings
    }

    # Struct definitions
    config_struct = pa.struct([
        pa.field('parameter', pa.string()),
        pa.field('value', pa.string())
    ])

    for col in df.columns:
        if col in list_string_columns:
            # List of strings
            fields.append(pa.field(col, pa.list_(pa.string())))
            print(f"  {col}: list<string>")

        elif col == 'sensor_details':
            # Infer struct from data
            arrow_type = infer_arrow_type_from_sample(df[col], col)
            fields.append(pa.field(col, arrow_type))
            print(f"  {col}: {arrow_type}")

        elif col in ['launch_config', 'config']:
            # List of config structs
            fields.append(pa.field(col, pa.list_(config_struct)))
            print(f"  {col}: list<struct<parameter, value>>")

        else:
            # Infer type from pandas
            try:
                if df[col].dtype == 'object':
                    # Check if it's a list column we missed
                    arrow_type = infer_arrow_type_from_sample(df[col], col)
                    fields.append(pa.field(col, arrow_type))
                else:
                    arrow_type = pa.from_numpy_dtype(df[col].dtype)
                    fields.append(pa.field(col, arrow_type))
            except Exception:
                # Default to string for object types
                fields.append(pa.field(col, pa.string()))

    return pa.schema(fields)

def convert_df_to_arrow_table(df: pd.DataFrame, schema: pa.Schema) -> pa.Table:
    """
    Convert pandas DataFrame to PyArrow Table with explicit schema
    """
    print("\nConverting DataFrame to PyArrow Table...")

    # Build dict of arrays column by column
    arrays_dict = {}

    for field in schema:
        col_name = field.name
        col_data = df[col_name]

        try:
            # For list types, ensure we have Python lists not numpy arrays
            if pa.types.is_list(field.type):
                # Convert to pure Python objects
                clean_data = []
                for val in col_data:
                    if val is None or (isinstance(val, float) and np.isnan(val)):
                        clean_data.append(None)
                    elif isinstance(val, np.ndarray):
                        # Convert numpy array to list, ensuring all items are strings if needed
                        if pa.types.is_string(field.type.list_element_type):
                            clean_data.append([str(item) if item is not None else None for item in val.tolist()])
                        else:
                            clean_data.append(val.tolist())
                    elif isinstance(val, list):
                        # Ensure nested items are proper Python types
                        if pa.types.is_string(field.type.list_element_type):
                            # Ensure all items are strings
                            clean_data.append([str(item) if item is not None else None for item in val])
                        else:
                            # Keep as-is but convert numpy items to Python
                            clean_data.append([
                                item.tolist() if isinstance(item, np.ndarray) else item
                                for item in val
                            ])
                    else:
                        clean_data.append(val)

                arrow_array = pa.array(clean_data, type=field.type)

            elif pa.types.is_struct(field.type):
                # Handle struct types (like sensor_details, launch_config, config)
                clean_data = []
                for val in col_data:
                    if val is None or (isinstance(val, float) and np.isnan(val)):
                        clean_data.append(None)
                    else:
                        clean_data.append(val)

                arrow_array = pa.array(clean_data, type=field.type)

            else:
                # Regular scalar types
                arrow_array = pa.array(col_data, type=field.type)

            arrays_dict[col_name] = arrow_array
            print(f"  ✓ Converted '{col_name}'")

        except Exception as e:
            print(f"  ✗ Error converting '{col_name}': {e}")
            # Try without type specification
            try:
                arrays_dict[col_name] = pa.array(col_data)
                print(f"    Fallback conversion succeeded")
            except Exception as e2:
                print(f"    Fallback also failed: {e2}")

                # Last resort: convert everything to strings
                try:
                    string_data = [str(val) if val is not None else None for val in col_data]
                    arrays_dict[col_name] = pa.array(string_data)
                    print(f"    String conversion fallback succeeded")
                except Exception as e3:
                    print(f"    All fallbacks failed: {e3}")
                    raise

    # Create table from dict
    return pa.table(arrays_dict, schema=schema)

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

    # Prepare dataframe for Arrow (convert strings to lists/dicts)
    combined_df = prepare_dataframe_for_arrow(combined_df)

    # Create Arrow schema
    schema = create_arrow_schema(combined_df)

    # Convert to Arrow Table
    arrow_table = convert_df_to_arrow_table(combined_df, schema)

    # Create output directory if it doesn't exist
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Save to Parquet using PyArrow
    print(f"\nSaving to {output_file}...")

    try:
        pq.write_table(arrow_table, output_file, compression=compression)

        file_size = os.path.getsize(output_file) / (1024 * 1024)  # Size in MB
        print(f"\n✓ Successfully saved! File size: {file_size:.2f} MB")

        # Print summary statistics
        print("\nDataset Summary:")
        print(f"  Total rows: {len(combined_df)}")
        print(f"  Total columns: {len(combined_df.columns)}")

        # Show schema
        print(f"\nArrow Schema (nested columns only):")
        for field in schema:
            if pa.types.is_list(field.type) or pa.types.is_struct(field.type):
                print(f"  {field.name}: {field.type}")

        # Test reading back
        print("\nTesting read-back...")
        test_df = pd.read_parquet(output_file)
        print(f"  ✓ Read back successfully: {len(test_df)} rows")

        # Show sample of list columns
        print("\nSample of nested columns (first non-null row):")
        for col in ['sensors', 'launch_config', 'config', 'sensor_details']:
            if col in test_df.columns:
                # Find first non-null value
                non_null_idx = test_df[col].first_valid_index()
                if non_null_idx is not None:
                    sample = test_df[col].iloc[non_null_idx]
                    print(f"  {col}: {sample}")

    except Exception as e:
        print(f"\n✗ ERROR saving to Parquet: {e}")
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    combine_parquet_files(
        input_folder=INPUT_FOLDER,
        output_file=OUTPUT_FILE,
        file_pattern=FILE_PATTERN,
        compression=COMPRESSION,
        reset_index=RESET_INDEX
    )