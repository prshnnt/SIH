import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch, execute_values
from datetime import datetime
import json
import numpy as np

# Database connection configuration
DEFAULT_DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'postgres',
    'user': 'postgres',
    'password': 'hello'
}

# Batch size for bulk inserts
BATCH_SIZE = 1000

def parse_date(date_str):
    """Parse date string in format YYYYMMDDHHMMSS to datetime"""
    if pd.isna(date_str) or date_str is None or date_str == '':
        return None
    
    # If it's already a datetime object, return it
    if isinstance(date_str, (datetime, pd.Timestamp)):
        return date_str
    
    try:
        date_str = str(date_str).strip()
        if len(date_str) == 14:
            return datetime.strptime(date_str, '%Y%m%d%H%M%S')
        elif len(date_str) == 8:
            return datetime.strptime(date_str, '%Y%m%d')
        # Try ISO format as fallback
        return pd.to_datetime(date_str)
    except:
        return None

def clean_value(value):
    """Clean and convert values, handling nulls and invalid data"""
    if pd.isna(value) or value is None:
        return None
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    if isinstance(value, str):
        value = value.strip()
        if value.lower() in ['nan', 'n/a', 'null', '']:
            return None
    return value

def prepare_float_metadata_batch(df):
    """Prepare batch data for float metadata insertion"""
    batch_data = []
    skipped = []
    
    for idx, row in df.iterrows():
        try:
            # Parse dates
            launch_date = parse_date(row.get('launch_date'))
            date_update = parse_date(row.get('date_update'))
            start_date = parse_date(row.get('start_date'))
            end_mission_date = parse_date(row.get('end_mission_date'))
            extraction_date = parse_date(row.get('extraction_date'))
            
            # Skip if missing required fields
            if launch_date is None:
                skipped.append((idx, row.get('wmo'), "Missing launch_date"))
                continue
            
            # Ensure extraction_date has a value
            if extraction_date is None:
                extraction_date = datetime.now()
            
            batch_data.append((
                clean_value(row.get('wmo')),
                clean_value(row.get('file')),
                clean_value(row.get('profiler_type')),
                clean_value(row.get('institution')),
                date_update,
                clean_value(row.get('global_title')),
                clean_value(row.get('global_institution')),
                clean_value(row.get('global_source')),
                clean_value(row.get('global_history')),
                clean_value(row.get('global_references')),
                clean_value(row.get('global_comment')),
                clean_value(row.get('global_user_manual_version')),
                clean_value(row.get('global_conventions')),
                clean_value(row.get('platform_number')),
                clean_value(row.get('project_name')),
                clean_value(row.get('principal_investigator')),
                clean_value(row.get('platform_type')),
                clean_value(row.get('float_serial_number')),
                clean_value(row.get('firmware_version')),
                launch_date,
                clean_value(row.get('launch_longitude')),
                clean_value(row.get('launch_latitude')),
                clean_value(row.get('deployment_platform')),
                clean_value(row.get('deployment_cruise_id')),
                clean_value(row.get('battery_type')),
                clean_value(row.get('battery_packs')),
                clean_value(row.get('controller_board_primary')),
                clean_value(row.get('controller_board_serial_primary')),
                clean_value(row.get('data_centre')),
                clean_value(row.get('wmo_instrument_type')),
                clean_value(row.get('transmission_system')),
                clean_value(row.get('transmission_system_id')),
                clean_value(row.get('transmission_frequency')),
                start_date,
                clean_value(row.get('start_date_qc')),
                end_mission_date,
                clean_value(row.get('end_mission_status')),
                extraction_date
            ))
        except Exception as e:
            skipped.append((idx, row.get('wmo'), str(e)))
    
    if skipped:
        print(f"  ! Skipped {len(skipped)} records in batch:")
        for idx, wmo, reason in skipped[:5]:  # Show first 5
            print(f"    - Row {idx} (WMO: {wmo}): {reason}")
        if len(skipped) > 5:
            print(f"    ... and {len(skipped) - 5} more")
    
    return batch_data

def bulk_insert_float_metadata(cursor, batch_data):
    """Bulk insert float metadata and return mapping of (wmo, platform_number, launch_date) -> (id, launch_date)"""
    query = """
        INSERT INTO argo_float_metadata (
            wmo, file_path, profiler_type, institution, date_update,
            global_title, global_institution, global_source, global_history,
            global_references, global_comment, global_user_manual_version, global_conventions,
            platform_number, project_name, principal_investigator, platform_type,
            float_serial_number, firmware_version,
            launch_date, launch_longitude, launch_latitude,
            deployment_platform, deployment_cruise_id,
            battery_type, battery_packs, controller_board_primary, controller_board_serial_primary,
            data_centre, wmo_instrument_type,
            transmission_system, transmission_system_id, transmission_frequency,
            start_date, start_date_qc, end_mission_date, end_mission_status,
            extraction_date
        ) VALUES %s
        RETURNING id, wmo, platform_number, launch_date;
    """
    
    result = execute_values(cursor, query, batch_data, fetch=True)
    
    # Create mapping: (wmo, platform_number, launch_date) -> (id, launch_date)
    id_mapping = {}
    for row in result:
        float_id, wmo, platform_number, launch_date = row
        id_mapping[(wmo, platform_number, launch_date)] = (float_id, launch_date)
    
    return id_mapping

def prepare_sensor_batch(df, id_mapping):
    """Prepare batch data for sensors"""
    batch_data = []
    
    for idx, row in df.iterrows():
        wmo = clean_value(row.get('wmo'))
        platform_number = clean_value(row.get('platform_number'))
        launch_date = parse_date(row.get('launch_date'))
        
        key = (wmo, platform_number, launch_date)
        if key not in id_mapping:
            continue
        
        float_id, float_launch_date = id_mapping[key]
        
        sensors = row.get('sensor_details', [])
        if sensors is None or (isinstance(sensors, (list, np.ndarray)) and len(sensors) == 0):
            continue
        if not isinstance(sensors, list):
            continue
        
        for sensor_idx, sensor in enumerate(sensors):
            if isinstance(sensor, dict):
                batch_data.append((
                    float_id,
                    float_launch_date,
                    clean_value(sensor.get('type')),
                    clean_value(sensor.get('maker')),
                    clean_value(sensor.get('model')),
                    clean_value(sensor.get('serial_number')),
                    sensor_idx + 1
                ))
    
    return batch_data

def prepare_positioning_systems_batch(df, id_mapping):
    """Prepare batch data for positioning systems"""
    batch_data = []
    
    for idx, row in df.iterrows():
        wmo = clean_value(row.get('wmo'))
        platform_number = clean_value(row.get('platform_number'))
        launch_date = parse_date(row.get('launch_date'))
        
        key = (wmo, platform_number, launch_date)
        if key not in id_mapping:
            continue
        
        float_id, float_launch_date = id_mapping[key]
        
        positioning_system = row.get('positioning_system')
        if positioning_system is None or pd.isna(positioning_system):
            continue
        
        # Handle both single string and list of systems
        if isinstance(positioning_system, str):
            systems = [positioning_system]
        else:
            systems = positioning_system
        
        for sys_idx, sys in enumerate(systems):
            if sys is not None and not pd.isna(sys):
                batch_data.append((
                    float_id,
                    float_launch_date,
                    clean_value(sys),
                    sys_idx + 1
                ))
    
    return batch_data

def prepare_transmission_systems_batch(df, id_mapping):
    """Prepare batch data for transmission systems"""
    batch_data = []
    
    for idx, row in df.iterrows():
        wmo = clean_value(row.get('wmo'))
        platform_number = clean_value(row.get('platform_number'))
        launch_date = parse_date(row.get('launch_date'))
        
        key = (wmo, platform_number, launch_date)
        if key not in id_mapping:
            continue
        
        float_id, float_launch_date = id_mapping[key]
        
        transmission_system = row.get('transmission_system')
        if transmission_system is None or pd.isna(transmission_system):
            continue
        
        batch_data.append((
            float_id,
            float_launch_date,
            clean_value(transmission_system),
            clean_value(row.get('transmission_system_id')),
            clean_value(row.get('transmission_frequency')),
            1
        ))
    
    return batch_data

def prepare_launch_config_batch(df, id_mapping):
    """Prepare batch data for launch configuration"""
    batch_data = []
    
    for idx, row in df.iterrows():
        wmo = clean_value(row.get('wmo'))
        platform_number = clean_value(row.get('platform_number'))
        launch_date = parse_date(row.get('launch_date'))
        
        key = (wmo, platform_number, launch_date)
        if key not in id_mapping:
            continue
        
        float_id, float_launch_date = id_mapping[key]
        
        launch_config = row.get('launch_config', [])
        if launch_config is None or (isinstance(launch_config, (list, np.ndarray)) and len(launch_config) == 0):
            continue
        if not isinstance(launch_config, list):
            continue
        
        for config_idx, config in enumerate(launch_config):
            if isinstance(config, dict):
                param_name = config.get('parameter')
                param_value = config.get('value')
                
                # Try to convert value to numeric
                try:
                    if param_value is not None and str(param_value) != 'nan' and not pd.isna(param_value):
                        param_value = float(str(param_value).replace('[', '').replace(']', '').split()[0])
                    else:
                        param_value = None
                except:
                    param_value = None
                
                batch_data.append((
                    float_id,
                    float_launch_date,
                    param_name,
                    param_value,
                    config_idx + 1
                ))
    
    return batch_data

def prepare_config_history_batch(df, id_mapping):
    """Prepare batch data for configuration history"""
    batch_data = []
    
    for idx, row in df.iterrows():
        wmo = clean_value(row.get('wmo'))
        platform_number = clean_value(row.get('platform_number'))
        launch_date = parse_date(row.get('launch_date'))
        
        key = (wmo, platform_number, launch_date)
        if key not in id_mapping:
            continue
        
        float_id, float_launch_date = id_mapping[key]
        
        config = row.get('config', [])
        if config is None or (isinstance(config, (list, np.ndarray)) and len(config) == 0):
            continue
        if not isinstance(config, list):
            continue
        
        for config_idx, cfg in enumerate(config):
            if isinstance(cfg, dict):
                param_name = cfg.get('parameter')
                param_value = cfg.get('value')
                
                # Try to convert value to numeric (taking first value if array)
                try:
                    if param_value is not None and str(param_value) != 'nan' and not pd.isna(param_value):
                        # Handle array values
                        str_value = str(param_value).replace('[', '').replace(']', '').split()[0]
                        param_value = float(str_value)
                    else:
                        param_value = None
                except:
                    param_value = None
                
                batch_data.append((
                    float_id,
                    float_launch_date,
                    1,  # config_set
                    param_name,
                    param_value,
                    config_idx + 1
                ))
    
    return batch_data

def load_parquet_to_postgres(parquet_file_path, URL=None, DB_CONFIG=DEFAULT_DB_CONFIG):
    """Main function to load parquet data into PostgreSQL using bulk inserts"""
    
    # Read parquet file
    print(f"Reading parquet file: {parquet_file_path}")
    df = pd.read_parquet(parquet_file_path)
    total_records = len(df)
    print(f"Loaded {total_records} records")
    
    # Connect to database
    print("Connecting to PostgreSQL...")
    if URL:
        conn = psycopg2.connect(URL)
    else:
        conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Track errors
    error_log = []
    
    try:
        total_processed = 0
        total_errors = 0
        
        # Process in batches
        for batch_start in range(0, total_records, BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, total_records)
            batch_df = df.iloc[batch_start:batch_end]
            
            print(f"\nProcessing batch {batch_start}-{batch_end}...")
            
            try:
                # 1. Bulk insert main metadata
                print("  - Inserting float metadata...")
                metadata_batch = prepare_float_metadata_batch(batch_df)
                if not metadata_batch:
                    print("  - No valid metadata in this batch")
                    continue
                
                id_mapping = bulk_insert_float_metadata(cursor, metadata_batch)
                print(f"  - Inserted {len(id_mapping)} float records")
                
                # 2. Bulk insert sensors
                print("  - Inserting sensors...")
                sensor_batch = prepare_sensor_batch(batch_df, id_mapping)
                if sensor_batch:
                    execute_values(cursor, """
                        INSERT INTO argo_sensors 
                        (float_id, float_launch_date, sensor_type, maker, model, serial_number, sensor_order)
                        VALUES %s
                    """, sensor_batch)
                    print(f"  - Inserted {len(sensor_batch)} sensor records")
                
                # 3. Bulk insert positioning systems
                print("  - Inserting positioning systems...")
                positioning_batch = prepare_positioning_systems_batch(batch_df, id_mapping)
                if positioning_batch:
                    execute_values(cursor, """
                        INSERT INTO argo_positioning_systems 
                        (float_id, float_launch_date, system_name, system_order)
                        VALUES %s
                    """, positioning_batch)
                    print(f"  - Inserted {len(positioning_batch)} positioning system records")
                
                # 4. Bulk insert transmission systems
                print("  - Inserting transmission systems...")
                transmission_batch = prepare_transmission_systems_batch(batch_df, id_mapping)
                if transmission_batch:
                    execute_values(cursor, """
                        INSERT INTO argo_transmission_systems 
                        (float_id, float_launch_date, system_name, system_id, frequency, system_order)
                        VALUES %s
                    """, transmission_batch)
                    print(f"  - Inserted {len(transmission_batch)} transmission system records")
                
                # 5. Bulk insert launch config
                print("  - Inserting launch configurations...")
                launch_config_batch = prepare_launch_config_batch(batch_df, id_mapping)
                if launch_config_batch:
                    execute_values(cursor, """
                        INSERT INTO argo_launch_config 
                        (float_id, float_launch_date, parameter_name, parameter_value, parameter_order)
                        VALUES %s
                    """, launch_config_batch)
                    print(f"  - Inserted {len(launch_config_batch)} launch config records")
                
                # 6. Bulk insert config history
                print("  - Inserting config history...")
                config_history_batch = prepare_config_history_batch(batch_df, id_mapping)
                if config_history_batch:
                    execute_values(cursor, """
                        INSERT INTO argo_config_history 
                        (float_id, float_launch_date, config_set, parameter_name, parameter_value, parameter_order)
                        VALUES %s
                    """, config_history_batch)
                    print(f"  - Inserted {len(config_history_batch)} config history records")
                
                # Commit batch
                conn.commit()
                total_processed += len(id_mapping)
                print(f"  ✓ Batch committed successfully")
                
            except Exception as e:
                error_msg = f"Batch {batch_start}-{batch_end}: {str(e)}"
                print(f"  ✗ Batch Error: {error_msg}")
                conn.rollback()
                
                # Try processing records individually as fallback
                print(f"  → Retrying batch records individually...")
                individual_success = 0
                individual_errors = 0
                
                for idx in range(len(batch_df)):
                    single_row_df = batch_df.iloc[idx:idx+1]
                    try:
                        # Try individual insert
                        metadata_batch = prepare_float_metadata_batch(single_row_df)
                        if not metadata_batch:
                            individual_errors += 1
                            continue
                        
                        id_mapping = bulk_insert_float_metadata(cursor, metadata_batch)
                        
                        # Insert related data
                        sensor_batch = prepare_sensor_batch(single_row_df, id_mapping)
                        if sensor_batch:
                            execute_values(cursor, """
                                INSERT INTO argo_sensors 
                                (float_id, float_launch_date, sensor_type, maker, model, serial_number, sensor_order)
                                VALUES %s
                            """, sensor_batch)
                        
                        positioning_batch = prepare_positioning_systems_batch(single_row_df, id_mapping)
                        if positioning_batch:
                            execute_values(cursor, """
                                INSERT INTO argo_positioning_systems 
                                (float_id, float_launch_date, system_name, system_order)
                                VALUES %s
                            """, positioning_batch)
                        
                        transmission_batch = prepare_transmission_systems_batch(single_row_df, id_mapping)
                        if transmission_batch:
                            execute_values(cursor, """
                                INSERT INTO argo_transmission_systems 
                                (float_id, float_launch_date, system_name, system_id, frequency, system_order)
                                VALUES %s
                            """, transmission_batch)
                        
                        launch_config_batch = prepare_launch_config_batch(single_row_df, id_mapping)
                        if launch_config_batch:
                            execute_values(cursor, """
                                INSERT INTO argo_launch_config 
                                (float_id, float_launch_date, parameter_name, parameter_value, parameter_order)
                                VALUES %s
                            """, launch_config_batch)
                        
                        config_history_batch = prepare_config_history_batch(single_row_df, id_mapping)
                        if config_history_batch:
                            execute_values(cursor, """
                                INSERT INTO argo_config_history 
                                (float_id, float_launch_date, config_set, parameter_name, parameter_value, parameter_order)
                                VALUES %s
                            """, config_history_batch)
                        
                        conn.commit()
                        individual_success += 1
                        total_processed += 1
                        
                    except Exception as ind_error:
                        wmo = single_row_df.iloc[0].get('wmo', 'unknown')
                        error_detail = f"WMO {wmo}: {str(ind_error)}"
                        if "duplicate key" in str(ind_error).lower():
                            error_detail = f"WMO {wmo}: Duplicate record (already exists)"
                        error_log.append(error_detail)
                        conn.rollback()
                        individual_errors += 1
                
                print(f"  → Individual processing: {individual_success} succeeded, {individual_errors} failed")
                total_errors += individual_errors
                continue
        
        print(f"\n{'='*60}")
        print(f"Load complete!")
        print(f"Successfully loaded: {total_processed} float records")
        print(f"Errors: {total_errors} records")
        print(f"{'='*60}")
        
        # Print error summary
        if error_log:
            print(f"\n{'='*60}")
            print(f"ERROR SUMMARY ({len(error_log)} records failed):")
            print(f"{'='*60}")
            
            # Group errors by type
            duplicate_errors = [e for e in error_log if "duplicate" in e.lower()]
            other_errors = [e for e in error_log if "duplicate" not in e.lower()]
            
            if duplicate_errors:
                print(f"\nDuplicate Records ({len(duplicate_errors)}):")
                for err in duplicate_errors[:10]:
                    print(f"  - {err}")
                if len(duplicate_errors) > 10:
                    print(f"  ... and {len(duplicate_errors) - 10} more duplicates")
            
            if other_errors:
                print(f"\nOther Errors ({len(other_errors)}):")
                for err in other_errors[:10]:
                    print(f"  - {err}")
                if len(other_errors) > 10:
                    print(f"  ... and {len(other_errors) - 10} more errors")
            
            print(f"{'='*60}")
        
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        conn.rollback()
        raise
    
    finally:
        cursor.close()
        conn.close()
        print("Database connection closed")