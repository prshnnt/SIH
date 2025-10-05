"""
ARGO Float Metadata Extractor and Parquet Converter

This script extracts comprehensive metadata from ARGO floats available on the
Ifremer GDAC server (https://data-argo.ifremer.fr) and converts it to Parquet format.

This version has been refactored to encapsulate all functionality within a
single class and fixes issues related to incorrect string parsing from NetCDF files.

Features:
- Extracts all available metadata including sensors, battery info, WMO numbers
- Supports both individual float extraction and bulk processing
- Correctly handles NetCDF character arrays, converting them to strings
- Converts to efficient Parquet format for analysis
- Includes error handling and progress tracking

Requirements:
- netCDF4
- pandas
- pyarrow
- requests
- numpy
- tqdm (for progress bars)
- pydantic
"""

import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict, List, Optional
import tempfile
import json

from tqdm import tqdm
import netCDF4 as nc
import pyarrow.parquet as pq
import pyarrow as pa
from pydantic import BaseModel


class FloatObject(BaseModel):
    """Data model for a single ARGO float from the index file."""
    wmo: str
    file: str
    profiler_type: str
    institution: str
    date_update: str


class ArgoMetadataExtractor:
    """
    Extracts and processes ARGO float metadata from the Ifremer GDAC server.
    
    This class handles downloading metadata files, parsing complex NetCDF formats,
    cleaning the data (specifically fixing character arrays into proper strings),
    and saving the final output to a Parquet file.
    """

    def __init__(self, base_url: str = "https://data-argo.ifremer.fr"):
        """
        Initializes the ARGO metadata extractor.

        Args:
            base_url: Base URL for the ARGO GDAC server.
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ARGO-Metadata-Extractor/2.0'
        })
        
        # Mapping from NetCDF variable names to desired DataFrame column names.
        self.metadata_fields = {
            'PLATFORM_NUMBER': 'platform_number',
            'PROJECT_NAME': 'project_name',
            'PI_NAME': 'principal_investigator',
            'PLATFORM_TYPE': 'platform_type',
            'FLOAT_SERIAL_NO': 'float_serial_number',
            'FIRMWARE_VERSION': 'firmware_version',
            'LAUNCH_DATE': 'launch_date',
            'LAUNCH_LONGITUDE': 'launch_longitude',
            'LAUNCH_LATITUDE': 'launch_latitude',
            'DEPLOYMENT_PLATFORM': 'deployment_platform',
            'DEPLOYMENT_CRUISE_ID': 'deployment_cruise_id',
            'LAUNCH_CONFIG_PARAMETER_NAME': 'launch_config_parameters',
            'LAUNCH_CONFIG_PARAMETER_VALUE': 'launch_config_values',
            'CONFIG_PARAMETER_NAME': 'config_parameters',
            'CONFIG_PARAMETER_VALUE': 'config_values',
            'SENSOR': 'sensors',
            'SENSOR_MAKER': 'sensor_makers',
            'SENSOR_MODEL': 'sensor_models',
            'SENSOR_SERIAL_NO': 'sensor_serial_numbers',
            'BATTERY_TYPE': 'battery_type',
            'BATTERY_PACKS': 'battery_packs',
            'CONTROLLER_BOARD_TYPE_PRIMARY': 'controller_board_primary',
            'CONTROLLER_BOARD_SERIAL_NO_PRIMARY': 'controller_board_serial_primary',
            'DATA_CENTRE': 'data_centre',
            'DC_REFERENCE': 'data_centre_reference',
            'DATA_STATE_INDICATOR': 'data_state_indicator',
            'DATA_MODE': 'data_mode',
            'WMO_INST_TYPE': 'wmo_instrument_type',
            'POSITIONING_SYSTEM': 'positioning_system',
            'TRANS_SYSTEM': 'transmission_system',
            'TRANS_SYSTEM_ID': 'transmission_system_id',
            'TRANS_FREQUENCY': 'transmission_frequency',
            'START_DATE': 'start_date',
            'START_DATE_QC': 'start_date_qc',
            'END_MISSION_DATE': 'end_mission_date',
            'END_MISSION_STATUS': 'end_mission_status'
        }

    # =================================================================
    # Public Methods
    # =================================================================

    def get_float_list(self) -> List[FloatObject]:
        """
        Fetches the list of all available ARGO floats from the server index.

        Returns:
            A list of FloatObject instances, each representing a float.
        """
        try:
            index_url = f"{self.base_url}/ar_index_global_meta.txt"
            response = self.session.get(index_url, timeout=30)
            response.raise_for_status()

            lines = response.text.strip().split('\n')
            float_list = []
            # Skip header lines (typically the first 9 lines)
            for line in lines[9:]:
                if line.strip() and not line.startswith('#'):
                    parts = line.split(',')
                    if len(parts) >= 4:
                        file_path = parts[0].strip()
                        wmo = file_path.split('/')[1]
                        if wmo.isdigit():
                            float_list.append(FloatObject(
                                wmo=wmo,
                                file=file_path,
                                profiler_type=parts[1].strip(),
                                institution=parts[2].strip(),
                                date_update=parts[3].strip()
                            ))
            print(f"Found {len(float_list)} floats in the main index.")
            return float_list
        except requests.RequestException as e:
            print(f"Error fetching float list: {e}")
            return []

    def extract_multiple_floats(self, floats: List[FloatObject], output_file: str):
        """
        Downloads, extracts, and processes metadata for multiple floats and saves to Parquet.

        Args:
            floats: A list of FloatObject instances to process.
            output_file: The path for the output Parquet file.
        """
        all_metadata = []
        failed_extractions = []

        print(f"Starting metadata extraction for {len(floats)} floats.")
        for float_obj in tqdm(floats, desc="Processing floats"):
            temp_file_path = None
            try:
                temp_file_path = self._download_metadata_file(float_obj)
                if temp_file_path:
                    metadata = self._extract_metadata_from_file(temp_file_path, float_obj)
                    all_metadata.append(metadata)
                else:
                    failed_extractions.append(float_obj.wmo)
            except Exception as e:
                print(f"Failed to process float {float_obj.wmo}: {e}")
                failed_extractions.append(float_obj.wmo)
            finally:
                if temp_file_path and os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

        if all_metadata:
            print("Converting extracted data to DataFrame...")
            df = pd.DataFrame(all_metadata)
            
            # This post-processing step ensures any complex nested data or strings
            # that were missed during initial extraction are cleaned up.
            print("Performing final data cleaning and type conversion...")
            df = self._fix_dataframe(df)

            self._save_to_parquet(df, output_file)

            print(f"\nSuccessfully extracted metadata for {len(all_metadata)} floats.")
            if failed_extractions:
                print(f"Failed to extract metadata for {len(failed_extractions)} floats: {failed_extractions}")
        else:
            print("\nNo metadata was successfully extracted.")

    # =================================================================
    # Internal Helper Methods
    # =================================================================

    def _download_metadata_file(self, float_obj: FloatObject) -> Optional[str]:
        """Downloads a metadata file for a single float to a temporary location."""
        try:
            meta_url = f"{self.base_url}/dac/{float_obj.file}"
            response = self.session.get(meta_url, timeout=60, stream=True)
            response.raise_for_status()

            with tempfile.NamedTemporaryFile(delete=False, suffix='.nc', prefix=f'argo_{float_obj.wmo}_') as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    temp_file.write(chunk)
                return temp_file.name
        except requests.RequestException as e:
            print(f"Could not download metadata for {float_obj.wmo}: {e}")
            return None

    def _decode_netcdf_string(self, data: np.ndarray) -> Optional[str]:
        """Decodes a NetCDF character array into a single Python string."""
        if data is None or data.size == 0:
            return None
        
        if hasattr(data, 'mask') and data.mask.all():
            return None

        try:
            # Flatten the array and join characters, decoding bytes if necessary
            chars = [
                item.decode('utf-8', errors='ignore') if isinstance(item, bytes) else str(item)
                for item in data.flatten()
            ]
            result = "".join(chars).strip().rstrip('-').strip()
            return result if result else None
        except Exception:
            return None

    def _decode_netcdf_string_array(self, data: np.ndarray) -> Optional[List[str]]:
        """Decodes a 2D NetCDF character array into a list of Python strings."""
        if data is None or data.size == 0 or data.ndim != 2:
            return None
        
        if hasattr(data, 'mask') and data.mask.all():
            return None

        try:
            strings = []
            for row in data:
                decoded_row = self._decode_netcdf_string(row)
                if decoded_row:
                    strings.append(decoded_row)
            return strings if strings else None
        except Exception:
            return None

    def _extract_metadata_from_file(self, file_path: str, float_obj: FloatObject) -> Dict[str, Any]:
        """Extracts all relevant metadata from a single NetCDF file."""
        metadata = float_obj.model_dump()
        try:
            with nc.Dataset(file_path, 'r') as ds:
                # Extract global attributes
                for attr_name in ds.ncattrs():
                    metadata[f'global_{attr_name.lower()}'] = ds.getncattr(attr_name)

                # Extract data from variables
                for var_name, field_name in self.metadata_fields.items():
                    if var_name in ds.variables:
                        var = ds.variables[var_name]
                        data = var[:]
                        
                        # Handle string data (often stored as character arrays)
                        if np.issubdtype(var.dtype, np.character):
                            if var.ndim == 1: # Single string as char array
                                metadata[field_name] = self._decode_netcdf_string(data)
                            elif var.ndim == 2: # Array of strings
                                metadata[field_name] = self._decode_netcdf_string_array(data)
                            else: # Higher dimensions, flatten to single string
                                metadata[field_name] = self._decode_netcdf_string(data)
                        # Handle numeric data
                        else:
                            if hasattr(data, 'filled'):
                                data = data.filled(np.nan)
                            
                            # Convert numpy types to native Python types for JSON compatibility
                            if isinstance(data, np.ndarray):
                                metadata[field_name] = data.tolist()
                            elif np.issubdtype(type(data), np.number):
                                metadata[field_name] = data.item()
                            else:
                                metadata[field_name] = data
                
                self._process_sensor_data(metadata)
                self._process_parameter_data(metadata)

        except Exception as e:
            metadata['extraction_error'] = str(e)
            
        metadata['extraction_date'] = datetime.now().isoformat()
        return metadata

    def _process_sensor_data(self, metadata: Dict):
        """Combines separate sensor fields into a single structured JSON field."""
        sensors = metadata.get('sensors')
        makers = metadata.get('sensor_makers')
        models = metadata.get('sensor_models')
        serials = metadata.get('sensor_serial_numbers')

        if not sensors:
            return

        # Ensure all are lists for consistent processing
        sensors = [sensors] if isinstance(sensors, str) else sensors
        makers = [makers] if isinstance(makers, str) else makers or []
        models = [models] if isinstance(models, str) else models or []
        serials = [serials] if isinstance(serials, str) else serials or []

        sensor_details = []
        for i, sensor_type in enumerate(sensors):
            sensor_details.append({
                'type': sensor_type,
                'maker': makers[i] if i < len(makers) else None,
                'model': models[i] if i < len(models) else None,
                'serial_number': serials[i] if i < len(serials) else None,
            })
        metadata['sensor_details'] = json.dumps(sensor_details) if sensor_details else None

    def _process_parameter_data(self, metadata: Dict):
        """Combines separate parameter fields into a single structured JSON field."""
        params = metadata.get('parameters')
        sensors = metadata.get('parameter_sensors')
        units = metadata.get('parameter_units')
        accuracies = metadata.get('parameter_accuracy')
        resolutions = metadata.get('parameter_resolution')

        if not params:
            return

        # Ensure all are lists for consistent processing
        params = [params] if isinstance(params, str) else params
        sensors = [sensors] if isinstance(sensors, str) else sensors or []
        units = [units] if isinstance(units, str) else units or []
        accuracies = accuracies or []
        resolutions = resolutions or []

        param_details = []
        for i, param_name in enumerate(params):
            param_details.append({
                'parameter': param_name,
                'sensor': sensors[i] if i < len(sensors) else None,
                'units': units[i] if i < len(units) else None,
                'accuracy': accuracies[i] if i < len(accuracies) else None,
                'resolution': resolutions[i] if i < len(resolutions) else None
            })
        metadata['parameter_details'] = json.dumps(param_details) if param_details else None


    def _save_to_parquet(self, df: pd.DataFrame, output_file: str):
        """Saves the final DataFrame to a Parquet file with metadata."""
        try:
            table = pa.Table.from_pandas(df, preserve_index=False)
            
            # Add custom metadata to the Parquet file
            table = table.replace_schema_metadata({
                'created_by': 'ArgoMetadataExtractor',
                'creation_date': datetime.now().isoformat(),
                'source': self.base_url,
                'total_floats': str(len(df))
            })
            
            pq.write_table(table, output_file, compression='snappy')
            print(f"\nParquet file saved to: {output_file}")
            print(f"  - Size: {os.path.getsize(output_file) / 1024 / 1024:.2f} MB")
            print(f"  - Columns: {len(df.columns)}")
            print(f"  - Records: {len(df)}")

        except Exception as e:
            print(f"Error saving to Parquet: {e}")
            raise  # Re-raise the exception instead of falling back to CSV
            
    # =================================================================
    # DataFrame Post-Processing/Fixing Methods
    # =================================================================

    @staticmethod
    def _is_none_or_nan(value: Any) -> bool:
        """ 
        Safely checks if a value is None or NaN, returning False for arrays.
        """
        # An array is a valid data object, not a single null value.
        # This check prevents the "ValueError: truth value of an array is ambiguous"
        if isinstance(value, (np.ndarray, list)):
            return False
            
        # Use pandas isna for robustly checking various null types (None, np.nan, etc.)
        try:
            return pd.isna(value)
        except (ValueError, TypeError):
            # Fallback for unhashable types that pd.isna might fail on
            return False

    @staticmethod
    def _fix_string_field(value: Any) -> Any:
        """Fixes a field that might be a list of characters instead of a single string."""
        if ArgoMetadataExtractor._is_none_or_nan(value):
            return None
        # If it's a list of single characters, join them
        if isinstance(value, list) and all(isinstance(item, str) and len(item) <= 1 for item in value):
            return ''.join(value).strip() or None
        # If it's a list but not single characters, convert to string
        if isinstance(value, list):
            return str(value) if value else None
        # If it's already a string, just strip whitespace
        if isinstance(value, str):
            return value.strip() or None
        return value

    @staticmethod
    def _fix_string_list_field(value: Any) -> Any:
        """Fixes fields that should be a list of strings but might be formatted incorrectly."""
        if ArgoMetadataExtractor._is_none_or_nan(value):
            return None
        # This handles cases where a 2D char array was incorrectly processed into a list of lists of chars
        if isinstance(value, list) and all(isinstance(sublist, list) for sublist in value):
            result = [''.join(map(str, sublist)).strip() for sublist in value if sublist]
            return result if result else None
        # If it's already a proper list of strings, return as is
        if isinstance(value, list):
            return value if value else None
        # If it's a single string, return None (shouldn't be in a list field)
        return None
    
    @staticmethod
    def _normalize_to_string(value: Any) -> Optional[str]:
        """
        Normalizes any value to a consistent string representation.
        Lists are converted to comma-separated strings.
        """
        if ArgoMetadataExtractor._is_none_or_nan(value):
            return None
        if isinstance(value, list):
            # Filter out empty strings and None values, then join
            clean_list = [str(v).strip() for v in value if v is not None and str(v).strip()]
            return ', '.join(clean_list) if clean_list else None
        if isinstance(value, str):
            return value.strip() or None
        return str(value) if value is not None else None
    
    def _fix_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Applies cleaning functions to the DataFrame columns as a final post-processing step.
        This ensures data consistency before saving.
        """
        # Fields that should be normalized to single strings (handle both strings and lists)
        normalize_to_string_fields = [
            'project_name', 'principal_investigator', 'platform_type', 'float_serial_number',
            'firmware_version', 'launch_date', 'deployment_platform', 'deployment_cruise_id',
            'battery_type', 'battery_packs', 'controller_board_primary', 'controller_board_serial_primary',
            'data_centre', 'wmo_instrument_type', 'positioning_system', 'transmission_system',
            'transmission_system_id', 'transmission_frequency', 'start_date', 'start_date_qc',
            'platform_number', 'data_centre_reference', 'data_state_indicator', 'data_mode',
            'end_mission_date', 'end_mission_status'
        ]

        # Fields that should remain as JSON strings (already processed)
        json_fields = ['sensor_details', 'parameter_details']

        # Fields that can be numeric lists
        numeric_list_fields = ['launch_config_values', 'config_values', 'launch_longitude', 
                               'launch_latitude']

        for col in df.columns:
            if col in normalize_to_string_fields:
                # Convert everything to consistent string format
                df[col] = df[col].apply(self._normalize_to_string)
            elif col in json_fields:
                # Keep JSON strings as-is
                pass
            elif col in numeric_list_fields:
                # Keep numeric lists as-is, but ensure they're proper Python lists
                df[col] = df[col].apply(lambda x: x if isinstance(x, list) or pd.isna(x) else None)
            else:
                # For any other columns with mixed types, try to normalize
                # Check if column has mixed list/non-list types
                if col in df.columns:
                    has_lists = df[col].apply(lambda x: isinstance(x, list)).any()
                    has_non_lists = df[col].apply(lambda x: not isinstance(x, list) and not pd.isna(x)).any()
                    
                    if has_lists and has_non_lists:
                        # Mixed types detected - normalize to strings
                        print(f"  Normalizing mixed-type column '{col}' to strings")
                        df[col] = df[col].apply(self._normalize_to_string)

        return df

if __name__ == '__main__':
    # ==================================================
    # Example Usage
    # ==================================================
    
    # 1. Initialize the extractor
    extractor = ArgoMetadataExtractor()
    
    # 2. Get the list of all available floats
    # This can take a moment to download and parse the index file.
    print("Fetching the global list of ARGO floats...")
    all_floats = extractor.get_float_list()
    
    if all_floats:
        # 3. Select a small subset of floats for a quick test
        # Let's process the first 5 floats from the list.
        floats_to_process = all_floats[:5]
        
        # 4. Define the output file path
        output_parquet_file = 'argo_metadata_sample.parquet'
        
        # 5. Run the extraction process for the selected floats
        extractor.extract_multiple_floats(floats_to_process, output_parquet_file)
        
        print(f"\nExample run complete. Check the output file: {output_parquet_file}")
    else:
        print("Could not retrieve the float list. Please check your internet connection or the ARGO server status.")