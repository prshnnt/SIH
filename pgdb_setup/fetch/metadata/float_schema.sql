-- QUERY TRUNCATED
-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS postgis;

-- Main Argo float metadata table
CREATE TABLE argo_float_metadata (
    id SERIAL,
    wmo VARCHAR(10) NOT NULL,
    file_path TEXT,
    profiler_type VARCHAR(10),
    institution VARCHAR(50),
    date_update TIMESTAMPTZ,
    
    -- Global attributes
    global_title TEXT,
    global_institution VARCHAR(100),
    global_source TEXT,
    global_history TEXT,
    global_references TEXT,
    global_comment TEXT,
    global_user_manual_version VARCHAR(20),
    global_conventions VARCHAR(50),
    
    -- Platform information
    platform_number VARCHAR(10) NOT NULL,
    project_name TEXT,
    principal_investigator VARCHAR(255),
    platform_type VARCHAR(50),
    float_serial_number VARCHAR(50),
    firmware_version VARCHAR(50),
    
    -- Launch information
    launch_date TIMESTAMPTZ NOT NULL,  -- NOT NULL required for partitioning
    launch_location GEOGRAPHY(POINT, 4326),
    launch_longitude DOUBLE PRECISION,
    launch_latitude DOUBLE PRECISION,
    deployment_platform VARCHAR(255),
    deployment_cruise_id VARCHAR(50),
    
    -- Hardware information
    battery_type VARCHAR(100),
    battery_packs TEXT,
    controller_board_primary VARCHAR(100),
    controller_board_serial_primary VARCHAR(50),
    
    -- Data management
    data_centre VARCHAR(10),
    wmo_instrument_type VARCHAR(10),

    -- transmission
    transmission_system VARCHAR(15),
    transmission_system_id VARCHAR(15),
    transmission_frequency VARCHAR(15),
    
    -- Mission dates
    start_date TIMESTAMPTZ,
    start_date_qc VARCHAR(1),
    end_mission_date TIMESTAMPTZ,
    end_mission_status VARCHAR(50),
    
    -- Metadata
    extraction_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Constraints - PRIMARY KEY must include partitioning column
    PRIMARY KEY (id, launch_date),
    CONSTRAINT unique_wmo_platform UNIQUE(wmo, platform_number, launch_date),
    CONSTRAINT valid_longitude CHECK (launch_longitude >= -180 AND launch_longitude <= 180),
    CONSTRAINT valid_latitude CHECK (launch_latitude >= -90 AND launch_latitude <= 90)
);

-- Create hypertable on launch_date for time-series optimization
SELECT create_hypertable('argo_float_metadata', 'launch_date', 
    chunk_time_interval => INTERVAL '1 year',
    if_not_exists => TRUE
);

-- Create spatial index on launch_location
CREATE INDEX idx_argo_launch_location ON argo_float_metadata USING GIST(launch_location);

-- Create indexes for common queries
CREATE INDEX idx_argo_wmo ON argo_float_metadata(wmo, launch_date DESC);
CREATE INDEX idx_argo_platform_number ON argo_float_metadata(platform_number, launch_date DESC);
CREATE INDEX idx_argo_institution ON argo_float_metadata(institution, launch_date DESC);
CREATE INDEX idx_argo_date_update ON argo_float_metadata(date_update DESC, launch_date DESC);
CREATE INDEX idx_argo_start_date ON argo_float_metadata(start_date, launch_date DESC);
CREATE INDEX idx_argo_extraction_date ON argo_float_metadata(extraction_date DESC, launch_date DESC);
CREATE INDEX idx_argo_id ON argo_float_metadata(id);  -- For lookups by id alone

-- Configuration parameters table (for launch config)
-- NOTE: Child tables are NOT hypertables, so they can have regular primary keys
CREATE TABLE argo_launch_config (
    id SERIAL PRIMARY KEY,
    float_id INT NOT NULL,
    float_launch_date TIMESTAMPTZ NOT NULL,
    parameter_name VARCHAR(255) NOT NULL,
    parameter_value NUMERIC,
    parameter_order INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Foreign key references the hypertable's composite key
    FOREIGN KEY (float_id, float_launch_date) 
        REFERENCES argo_float_metadata(id, launch_date) ON DELETE CASCADE,
    CONSTRAINT unique_float_param_order UNIQUE(float_id, float_launch_date, parameter_order)
);

CREATE INDEX idx_launch_config_float ON argo_launch_config(float_id, float_launch_date);

-- Configuration parameters table (for current/historical config)
CREATE TABLE argo_config_history (
    id SERIAL PRIMARY KEY,
    float_id INT NOT NULL,
    float_launch_date TIMESTAMPTZ NOT NULL,
    config_set INTEGER NOT NULL DEFAULT 1,
    parameter_name VARCHAR(255) NOT NULL,
    parameter_value NUMERIC,
    parameter_order INTEGER NOT NULL,
    effective_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (float_id, float_launch_date) 
        REFERENCES argo_float_metadata(id, launch_date) ON DELETE CASCADE,
    CONSTRAINT unique_float_config_param UNIQUE(float_id, float_launch_date, config_set, parameter_order)
);

CREATE INDEX idx_config_history_float ON argo_config_history(float_id, float_launch_date);
CREATE INDEX idx_config_history_config_set ON argo_config_history(float_id, float_launch_date, config_set);

-- Sensors table
CREATE TABLE argo_sensors (
    id SERIAL PRIMARY KEY,
    float_id INT NOT NULL,
    float_launch_date TIMESTAMPTZ NOT NULL,
    sensor_type VARCHAR(50) NOT NULL,
    maker VARCHAR(100),
    model VARCHAR(100),
    serial_number VARCHAR(100),
    sensor_order INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (float_id, float_launch_date) 
        REFERENCES argo_float_metadata(id, launch_date) ON DELETE CASCADE,
    CONSTRAINT unique_float_sensor_order UNIQUE(float_id, float_launch_date, sensor_order)
);

CREATE INDEX idx_sensors_float ON argo_sensors(float_id, float_launch_date);
CREATE INDEX idx_sensors_type ON argo_sensors(sensor_type);

-- Positioning systems table
CREATE TABLE argo_positioning_systems (
    id SERIAL PRIMARY KEY,
    float_id INT NOT NULL,
    float_launch_date TIMESTAMPTZ NOT NULL,
    system_name VARCHAR(50) NOT NULL,
    system_order INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (float_id, float_launch_date) 
        REFERENCES argo_float_metadata(id, launch_date) ON DELETE CASCADE,
    CONSTRAINT unique_float_positioning UNIQUE(float_id, float_launch_date, system_order)
);

CREATE INDEX idx_positioning_float ON argo_positioning_systems(float_id, float_launch_date);

-- Transmission systems table
CREATE TABLE argo_transmission_systems (
    id SERIAL PRIMARY KEY,
    float_id INT NOT NULL,
    float_launch_date TIMESTAMPTZ NOT NULL,
    system_name VARCHAR(50) NOT NULL,
    system_id VARCHAR(50),
    frequency VARCHAR(50),
    system_order INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    FOREIGN KEY (float_id, float_launch_date) 
        REFERENCES argo_float_metadata(id, launch_date) ON DELETE CASCADE,
    CONSTRAINT unique_float_transmission UNIQUE(float_id, float_launch_date, system_order)
);

CREATE INDEX idx_transmission_float ON argo_transmission_systems(float_id, float_launch_date);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update updated_at
CREATE TRIGGER update_argo_float_metadata_updated_at
    BEFORE UPDATE ON argo_float_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to update launch_location from coordinates
CREATE OR REPLACE FUNCTION update_launch_location()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.launch_longitude IS NOT NULL AND NEW.launch_latitude IS NOT NULL THEN
        NEW.launch_location = ST_SetSRID(
            ST_MakePoint(NEW.launch_longitude, NEW.launch_latitude),
            4326
        )::geography;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to automatically update launch_location
CREATE TRIGGER update_argo_launch_location
    BEFORE INSERT OR UPDATE OF launch_longitude, launch_latitude ON argo_float_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_launch_location();

-- View for complete float information with sensor details
CREATE VIEW v_argo_float_complete AS
SELECT 
    fm.*,
    ST_X(fm.launch_location::geometry) as computed_longitude,
    ST_Y(fm.launch_location::geometry) as computed_latitude,
    json_agg(DISTINCT jsonb_build_object(
        'type', s.sensor_type,
        'maker', s.maker,
        'model', s.model,
        'serial_number', s.serial_number
    ) ORDER BY jsonb_build_object(
        'type', s.sensor_type,
        'maker', s.maker,
        'model', s.model,
        'serial_number', s.serial_number
    )) FILTER (WHERE s.id IS NOT NULL) as sensor_details,
    array_agg(DISTINCT ps.system_name ORDER BY ps.system_name) 
        FILTER (WHERE ps.id IS NOT NULL) as positioning_systems,
    array_agg(DISTINCT ts.system_name ORDER BY ts.system_name) 
        FILTER (WHERE ts.id IS NOT NULL) as transmission_systems
FROM argo_float_metadata fm
LEFT JOIN argo_sensors s ON fm.id = s.float_id AND fm.launch_date = s.float_launch_date
LEFT JOIN argo_positioning_systems ps ON fm.id = ps.float_id AND fm.launch_date = ps.float_launch_date
LEFT JOIN argo_transmission_systems ts ON fm.id = ts.float_id AND fm.launch_date = ts.float_launch_date
GROUP BY fm.id, fm.launch_date;