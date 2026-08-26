-- argo_postgres_schema.sql
-- Lean relational schema for ARGO float metadata.
-- Only core, universally-present, queryable facts go here.
-- Variable / nested data lives in MongoDB (see mongo_setup.py).
-- Embedded summaries for RAG live in the vector store (see vector_setup.py).

CREATE TABLE IF NOT EXISTS argo_floats (
    wmo                       VARCHAR(10)  PRIMARY KEY,        -- WMO platform number (natural key)
    platform_number           VARCHAR(10),
    platform_type             VARCHAR(50),
    platform_maker            VARCHAR(100),
    float_serial_no           VARCHAR(50),
    firmware_version          VARCHAR(50),
    manual_version            VARCHAR(50),
    wmo_inst_type             VARCHAR(10),
    data_centre               VARCHAR(10),
    data_centre_reference     VARCHAR(255),
    project_name              VARCHAR(255),
    pi_name                   VARCHAR(255),
    deployment_platform       VARCHAR(255),
    deployment_cruise_id      VARCHAR(50),
    deployment_date           TIMESTAMPTZ,
    deployment_lat            DOUBLE PRECISION,
    deployment_lon            DOUBLE PRECISION,
    start_date                TIMESTAMPTZ,
    end_mission_date          TIMESTAMPTZ,
    end_mission_status        VARCHAR(50),
    battery_type              VARCHAR(100),
    battery_packs             VARCHAR(50),
    controller_board_type     VARCHAR(100),
    controller_board_serial   VARCHAR(50),
    transmission_system       VARCHAR(50),
    transmission_id           VARCHAR(50),
    transmission_frequency    VARCHAR(50),
    positioning_system        VARCHAR(50),
    data_mode                 VARCHAR(20),
    data_state_indicator      VARCHAR(20),
    source_url                TEXT,
    extraction_date           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT valid_dep_lon  CHECK (deployment_lon IS NULL OR (deployment_lon >= -180 AND deployment_lon <= 180)),
    CONSTRAINT valid_dep_lat  CHECK (deployment_lat IS NULL OR (deployment_lat >= -90  AND deployment_lat <= 90))
);

CREATE INDEX IF NOT EXISTS idx_floats_deployment_date ON argo_floats (deployment_date DESC);
CREATE INDEX IF NOT EXISTS idx_floats_platform_type   ON argo_floats (platform_type);
CREATE INDEX IF NOT EXISTS idx_floats_data_centre     ON argo_floats (data_centre);
CREATE INDEX IF NOT EXISTS idx_floats_pi_name         ON argo_floats (pi_name);
CREATE INDEX IF NOT EXISTS idx_floats_project         ON argo_floats (project_name);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION argo_floats_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_argo_floats_touch ON argo_floats;
CREATE TRIGGER trg_argo_floats_touch
    BEFORE UPDATE ON argo_floats
    FOR EACH ROW
    EXECUTE FUNCTION argo_floats_touch_updated_at();
