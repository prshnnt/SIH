# ARGO Ingestion Pipeline

## What this does

Fetches ARGO float metadata from the Ifremer GDAC and stores it across three databases:

| Store | Holds | Why |
|-------|-------|-----|
| **Postgres** | `argo_floats` — single row per float, core relational facts (wmo, platform, maker, deployment, dates, hardware) | Fast, indexed, queryable. The natural place for facts you filter by. |
| **MongoDB** | `float_details` — per-float variable blobs (sensors, launch_config, config_history, global_* attrs, free-form metadata) | Schema-less. No forced columns for fields that vary wildly per float. |
| **Vector DB (Chroma)** | one embedded text summary per float + filterable facets | RAG retrieval: "tell me about floats with X" type queries over natural language. |

The pipeline is **idempotent** — keyed by `wmo`, so re-runs replace existing rows instead of duplicating.

## Layout

```
pgdb_setup/
├── fetch/metadata/             # unchanged — downloads .nc → parquet parts
│   ├── main.py                 # python main.py <start> <end>
│   ├── merge_parts.py          # combine parts → allmetadata.parquet
│   └── utils.py                # ArgoMetadataExtractor
├── schema/                     # NEW
│   ├── postgres_schema.sql     # argo_floats table
│   ├── mongo_setup.py          # Mongo client + collection init
│   └── vector_setup.py         # Chroma persistent client
├── pipeline.py                 # NEW orchestrator: parquet → 3 stores
├── requirements.txt            # NEW
└── .env.example                # NEW
```

## Setup

```bash
# 1. venv + deps
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt

# 2. config
copy .env.example .env
# edit .env: DATABASE_URL, MONGO_URI, etc.

# 3. create Postgres table (one-time)
psql "$DATABASE_URL" -f schema/postgres_schema.sql

# 4. create Mongo indexes (one-time)
python -m pgdb_setup.schema.mongo_setup
```

## Run

```bash
# 1. fetch floats (slice-based, parallelisable across machines)
cd fetch/metadata
python main.py 0 1000            # → data/parts/metadata_0-999.parquet
python main.py 1000 2000
# ...

# 2. merge
python merge_parts.py           # → data/allmetadata.parquet

# 3. ingest into all 3 stores
cd ../../                     # repo root
python -m pgdb_setup.pipeline --parquet pgdb_setup/data/allmetadata.parquet
```

## What lives where (per float)

### Postgres `argo_floats` — queryable facts
- wmo, platform_number, platform_type, platform_maker
- float_serial_no, firmware_version, manual_version
- data_centre, data_centre_reference
- project_name, pi_name, wmo_inst_type
- deployment_platform, deployment_cruise_id, deployment_date, deployment_lat/lon
- start_date, end_mission_date, end_mission_status
- battery_type, battery_packs, controller_board_type, controller_board_serial
- transmission_system, transmission_id, transmission_frequency, positioning_system
- data_mode, data_state_indicator

### MongoDB `float_details` — variable blobs
- `sensors`, `sensor_makers`, `sensor_models`, `sensor_serial_numbers`
- `sensor_details` (already-JSON or list of dicts)
- `launch_config_parameters`, `launch_config_values`, `launch_config` (struct list)
- `config_parameters`, `config_values`, `config` (struct list)
- `parameter_details`
- `global_*` attributes (history, comment, references, conventions…)
- `start_date_qc`, `file`, `profiler_type`, `institution`, `date_update`

### Vector store
- `id` = wmo
- `document` = one-paragraph natural-language summary (platform, maker, sensors, deployment, mission)
- `metadata` = `{platform_type, data_centre, deployment_year}` (filterable)

## Notes

- Old `push/metadata/commit.py` (6-table hypertable + PostGIS) is **no longer the canonical load path**. Keep it for reference; pipeline.py supersedes it.
- Old `float_schema.sql` (TimescaleDB + PostGIS) is replaced by `schema/postgres_schema.sql` (single flat table).
