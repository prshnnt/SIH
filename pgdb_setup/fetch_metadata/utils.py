"""
ARGO Float Metadata Extractor and Parquet Converter

This script extracts comprehensive metadata from ARGO floats available on the
Ifremer GDAC server (https://data-argo.ifremer.fr) and converts it to Parquet format.

Features:
- Extracts all available metadata including sensors, battery info, WMO numbers
- Supports both individual float extraction and bulk processing
- Handles NetCDF metadata files from the ARGO GDAC
- Converts to efficient Parquet format for analysis
- Includes error handling and progress tracking

Requirements:
- netCDF4
- pandas
- pyarrow
- requests
- numpy
- tqdm (for progress bars)
"""

import os
import sys
import json
import requests
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Union
import tempfile

from urllib.parse import urljoin
from tqdm import tqdm

import netCDF4 as nc
import pyarrow.parquet as pq
import pyarrow as pa

class ArgoMetadataExtractor:
    """Extract and process ARGO float metadata from Ifremer GDAC server."""

    def __init__(self, base_url: str = "https://data-argo.ifremer.fr"):
        """
        Initialize the ARGO metadata extractor.

        Args:
            base_url: Base URL for the ARGO GDAC server
        """
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ARGO-Metadata-Extractor/1.0'
        })
        self.metadata_fields = {
            # Float identification
            'PLATFORM_NUMBER': 'WMO number',
            'PROJECT_NAME': 'project_name',
            'PI_NAME': 'principal_investigator',
            'PLATFORM_TYPE': 'platform_type',
            'FLOAT_SERIAL_NO': 'float_serial_number',
            'FIRMWARE_VERSION': 'firmware_version',

            # Deployment information
            'LAUNCH_DATE': 'launch_date',
            'LAUNCH_LONGITUDE': 'launch_longitude',
            'LAUNCH_LATITUDE': 'launch_latitude',
            'DEPLOYMENT_PLATFORM': 'deployment_platform',
            'DEPLOYMENT_CRUISE_ID': 'deployment_cruise_id',

            # Configuration
            'LAUNCH_CONFIG_PARAMETER_NAME': 'launch_config_parameters',
            'LAUNCH_CONFIG_PARAMETER_VALUE': 'launch_config_values',
            'CONFIG_PARAMETER_NAME': 'config_parameters',
            'CONFIG_PARAMETER_VALUE': 'config_values',

            # Sensors
            'SENSOR': 'sensors',
            'SENSOR_MAKER': 'sensor_makers',
            'SENSOR_MODEL': 'sensor_models',
            'SENSOR_SERIAL_NO': 'sensor_serial_numbers',

            # Technical specifications
            'BATTERY_TYPE': 'battery_type',
            'BATTERY_PACKS': 'battery_packs',
            'CONTROLLER_BOARD_TYPE_PRIMARY': 'controller_board_primary',
            'CONTROLLER_BOARD_SERIAL_NO_PRIMARY': 'controller_board_serial_primary',

            # Data management
            'DATA_CENTRE': 'data_centre',
            'DC_REFERENCE': 'data_centre_reference',
            'DATA_STATE_INDICATOR': 'data_state_indicator',
            'DATA_MODE': 'data_mode',
            'WMO_INST_TYPE': 'wmo_instrument_type',

            # Positioning system
            'POSITIONING_SYSTEM': 'positioning_system',
            'TRANS_SYSTEM': 'transmission_system',
            'TRANS_SYSTEM_ID': 'transmission_system_id',
            'TRANS_FREQUENCY': 'transmission_frequency',

            # Dates and status
            'START_DATE': 'start_date',
            'START_DATE_QC': 'start_date_qc',
            'END_MISSION_DATE': 'end_mission_date',
            'END_MISSION_STATUS': 'end_mission_status'
            }

        # ARGO metadata fields to extract


    def get_float_list(self) -> List[str]:
        """
        Get list of available ARGO floats from the server.

        Args:
            limit: Maximum number of floats to return (None for all)

        Returns:
            List of float WMO numbers
        """
        try:
            # Try to get index of available floats
            index_url = urljoin(self.base_url, "ar_index_global_meta.txt")
            response = self.session.get(index_url, timeout=30)

            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                # Skip header line
                float_list = []
                for line in lines[9:]:
                    if line.strip():
                        parts = line.split(',')
                        if len(parts) > 0:
                            float_wmo = parts[0].strip().split('/')[1]
                            if float_wmo.isdigit():
                                float_list.append(float_wmo)

                print(f"Found {len(float_list)} floats")
                return float_list
            else:
                print("Could not fetch float index, using alternative method")
                return self._get_float_list_alternative()

        except Exception as e:
            print(f"Error getting float list: {e}")
            return self._get_float_list_alternative()

    def _get_float_list_alternative(self) -> List[str]:
        """Alternative method to get float list by browsing directory structure."""
        try:
            # Browse the dac directory structure
            dac_url = urljoin(self.base_url, "dac/")
            response = self.session.get(dac_url, timeout=30)

            float_list = []
            if response.status_code == 200:
                # Parse HTML to find DAC directories
                import re
                dac_pattern = re.compile(r'href="([^"]+)/"')
                dacs = dac_pattern.findall(response.text)

                for dac in dacs[:5]:  # Limit to first 5 DACs to avoid overwhelming
                    if dac in ['..', '.']:
                        continue

                    dac_dir_url = urljoin(dac_url, f"{dac}/")
                    dac_response = self.session.get(dac_dir_url, timeout=30)

                    if dac_response.status_code == 200:
                        float_pattern = re.compile(r'href="(\d{7})/"')
                        floats = float_pattern.findall(dac_response.text)
                        float_list.extend(floats)

            print(f"Found {len(float_list)} floats using alternative method")
            return float_list

        except Exception as e:
            print(f"Error in alternative float list method: {e}")
            # Return a few example WMO numbers for testing
            return ['1900722', '1901393', '5903248', '6901929', '2902746']
    def save_float_list(self, float_list: List[str], output_file: str = 'float_list.txt'):
        """
        Save list of float WMO numbers to a text file.

        Args:
            float_list: List of WMO numbers
            output_file: Output file path
        """
        try:
            with open(output_file, 'w') as f:
                f.write(','.join(float_list))
            print(f"Saved float list to {output_file}")
        except Exception as e:
            print(f"Error saving float list: {e}")
    def load_float_list(self, input_file: str) -> List[str]:
        """
        Load list of float WMO numbers from a text file.

        Args:
            input_file: Input file path
        """
        try:
            with open(input_file, 'r') as f:
                content = f.read().strip()
                float_list = content.split(',')
            print(f"Loaded float list from {input_file}")
            return float_list
        except Exception as e:
            print(f"Error loading float list: {e}")
            return []

    def download_metadata_file(self, wmo_number: str) -> Optional[str]:
        """
        Download metadata file for a specific float.

        Args:
            wmo_number: WMO number of the float

        Returns:
            Path to downloaded file or None if failed
        """
        try:
            # Find which DAC contains this float
            dac = self._find_float_dac(wmo_number)
            if not dac:
                print(f"Could not find DAC for float {wmo_number}")
                return None

            # Construct metadata file URL
            meta_filename = f"{wmo_number}_meta.nc"
            meta_url = f"{self.base_url}/dac/{dac}/{wmo_number}/{meta_filename}"
            

            response = self.session.get(meta_url, timeout=60)

            if response.status_code == 200:
                # Save to temporary file
                temp_file = tempfile.NamedTemporaryFile(
                    delete=False, suffix='.nc', prefix=f'argo_{wmo_number}_'
                )
                temp_file.write(response.content)
                temp_file.close()

                print(f"Downloaded metadata for {wmo_number} to {temp_file.name}")
                return temp_file.name
            else:
                print(f"Could not download metadata for {wmo_number}: HTTP {response.status_code}")
                return None

        except Exception as e:
            print(f"Error downloading metadata for {wmo_number}: {e}")
            return None

    def _find_float_dac(self, wmo_number: str) -> Optional[str]:
        """Find which DAC (Data Assembly Center) contains the specified float."""
        # Common DACs to try first
        common_dacs = ['coriolis', 'aoml', 'bodc', 'csio', 'csiro', 'incois', 'jma', 'kma', 'kordi', 'meds', 'nmdis']

        for dac in common_dacs:
            try:
                test_url = f"{self.base_url}/dac/{dac}/{wmo_number}/"
                response = self.session.head(test_url, timeout=10)
                if response.status_code == 200:
                    return dac
            except:
                continue

        # If not found in common DACs, try a broader search
        try:
            dac_url = urljoin(self.base_url, "dac/")
            response = self.session.get(dac_url, timeout=30)

            if response.status_code == 200:
                import re
                dac_pattern = re.compile(r'href="([^"]+)/"')
                all_dacs = dac_pattern.findall(response.text)

                for dac in all_dacs:
                    if dac in ['..', '.'] or dac in common_dacs:
                        continue

                    try:
                        test_url = f"{self.base_url}/dac/{dac}/{wmo_number}/"
                        response = self.session.head(test_url, timeout=10)
                        if response.status_code == 200:
                            return dac
                    except:
                        continue
        except:
            pass

        return None

    def extract_metadata_from_file(self, file_path: str, wmo_number: str) -> Dict:
        """
        Extract metadata from NetCDF file.

        Args:
            file_path: Path to NetCDF metadata file
            wmo_number: WMO number of the float

        Returns:
            Dictionary containing extracted metadata
        """
        metadata = {'wmo_number': wmo_number}

        try:
            with nc.Dataset(file_path, 'r') as dataset:
                # Extract global attributes
                for attr_name in dataset.ncattrs():
                    try:
                        attr_value = dataset.getncattr(attr_name)
                        if isinstance(attr_value, np.ndarray):
                            attr_value = attr_value.tolist()
                        elif isinstance(attr_value, (bytes, np.bytes_)):
                            attr_value = attr_value.decode('utf-8', errors='ignore')
                        metadata[f'global_{attr_name.lower()}'] = attr_value
                    except:
                        continue

                # Extract variable data
                for var_name, field_name in self.metadata_fields.items():
                    if var_name in dataset.variables:
                        try:
                            var = dataset.variables[var_name]
                            data = var[:]

                            # Handle different data types
                            if hasattr(data, 'mask'):  # Masked array
                                if data.mask.all():
                                    metadata[field_name] = None
                                else:
                                    valid_data = data.compressed()
                                    if len(valid_data) > 0:
                                        if isinstance(valid_data[0], (bytes, np.bytes_)):
                                            metadata[field_name] = [
                                                item.decode('utf-8', errors='ignore').strip()
                                                for item in valid_data
                                            ]
                                        else:
                                            metadata[field_name] = valid_data.tolist()
                            else:
                                if isinstance(data, (bytes, np.bytes_)):
                                    metadata[field_name] = data.decode('utf-8', errors='ignore').strip()
                                elif isinstance(data, np.ndarray):
                                    if data.dtype.kind == 'S':  # String array
                                        metadata[field_name] = [
                                            item.decode('utf-8', errors='ignore').strip()
                                            if isinstance(item, (bytes, np.bytes_)) else str(item).strip()
                                            for item in data.flatten()
                                        ]
                                    else:
                                        metadata[field_name] = data.tolist()
                                else:
                                    metadata[field_name] = data
                        except Exception as e:
                            print(f"Could not extract {var_name}: {e}")
                            metadata[field_name] = None

                # Add technical information
                metadata['extraction_date'] = datetime.now().isoformat()
                metadata['file_path'] = file_path

                # Process sensor information into structured format
                self._process_sensor_data(metadata)

        except Exception as e:
            print(f"Error extracting metadata from {file_path}: {e}")
            metadata['extraction_error'] = str(e)

        return metadata

    def _process_sensor_data(self, metadata: Dict):
        """Process sensor information into a more structured format."""
        try:
            sensors = metadata.get('sensors', [])
            sensor_makers = metadata.get('sensor_makers', [])
            sensor_models = metadata.get('sensor_models', [])
            sensor_serials = metadata.get('sensor_serial_numbers', [])

            if sensors and isinstance(sensors, list):
                sensor_info = []
                max_len = max(
                    len(sensors),
                    len(sensor_makers) if sensor_makers else 0,
                    len(sensor_models) if sensor_models else 0,
                    len(sensor_serials) if sensor_serials else 0
                )

                for i in range(max_len):
                    sensor_dict = {}
                    if i < len(sensors):
                        sensor_dict['type'] = sensors[i]
                    if sensor_makers and i < len(sensor_makers):
                        sensor_dict['maker'] = sensor_makers[i]
                    if sensor_models and i < len(sensor_models):
                        sensor_dict['model'] = sensor_models[i]
                    if sensor_serials and i < len(sensor_serials):
                        sensor_dict['serial_number'] = sensor_serials[i]

                    if sensor_dict:
                        sensor_info.append(sensor_dict)

                metadata['sensor_details'] = sensor_info

        except Exception as e:
            print(f"Error processing sensor data: {e}")

    def extract_multiple_floats(self, wmo_numbers: List[str], output_file: str):
        """
        Extract metadata for multiple floats and save to Parquet.

        Args:
            wmo_numbers: List of WMO numbers
            output_file: Output Parquet file path
        """
        all_metadata = []
        failed_extractions = []

        print(f"Extracting metadata for {len(wmo_numbers)} floats")

        for wmo in tqdm(wmo_numbers, desc="Processing floats"):
            try:
                # Download metadata file
                temp_file = self.download_metadata_file(wmo)

                if temp_file:
                    # Extract metadata
                    metadata = self.extract_metadata_from_file(temp_file, wmo)
                    all_metadata.append(metadata)

                    # Clean up temporary file
                    try:
                        os.unlink(temp_file)
                    except:
                        pass
                else:
                    failed_extractions.append(wmo)

            except Exception as e:
                print(f"Failed to process float {wmo}: {e}")
                failed_extractions.append(wmo)

        if all_metadata:
            # Convert to DataFrame
            df = pd.json_normalize(all_metadata)

            # Save to Parquet
            self._save_to_parquet(df, output_file)

            print(f"Successfully extracted metadata for {len(all_metadata)} floats")
            print(f"Saved to: {output_file}")

            if failed_extractions:
                print(f"Failed to extract metadata for {len(failed_extractions)} floats: {failed_extractions}")
        else:
            print("No metadata was successfully extracted")

    def _save_to_parquet(self, df: pd.DataFrame, output_file: str):
        """Save DataFrame to Parquet format with metadata."""
        try:
            # Prepare metadata for Parquet file
            parquet_metadata = {
                'created_by': 'ARGO Metadata Extractor',
                'creation_date': datetime.now().isoformat(),
                'source': 'https://data-argo.ifremer.fr',
                'description': 'ARGO float metadata extracted from Ifremer GDAC',
                'total_floats': str(len(df))
            }

            # Create PyArrow table with metadata
            table = pa.Table.from_pandas(df)
            table = table.replace_schema_metadata(parquet_metadata)

            # Write to Parquet file
            pq.write_table(table, output_file, compression='snappy')

            print(f"Parquet file created: {output_file}")
            print(f"File size: {os.path.getsize(output_file) / 1024 / 1024:.2f} MB")
            print(f"Columns: {len(df.columns)}")
            print(f"Records: {len(df)}")

        except Exception as e:
            print(f"Error saving to Parquet: {e}")
            # Fallback to CSV
            csv_file = output_file.replace('.parquet', '.csv')
            df.to_csv(csv_file, index=False)
            print(f"Saved as CSV instead: {csv_file}")

    def extract_single_float(self, wmo_number: str, output_file: str):
        """
        Extract metadata for a single float.

        Args:
            wmo_number: WMO number of the float
            output_file: Output file path
        """
        print(f"Extracting metadata for float {wmo_number}")

        temp_file = self.download_metadata_file(wmo_number)

        if temp_file:
            metadata = self.extract_metadata_from_file(temp_file, wmo_number)

            # Clean up
            try:
                os.unlink(temp_file)
            except:
                pass

            # Convert to DataFrame
            df = pd.json_normalize([metadata])

            # Save to Parquet
            self._save_to_parquet(df, output_file)

            print(f"Successfully extracted metadata for float {wmo_number}")
        else:
            print(f"Could not download metadata for float {wmo_number}")


