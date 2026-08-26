"""
ARGO ingestion pipeline.

Flow:
    parquet parts  ──►  read row-per-float
                    │
                    ├──► Postgres  : core relational facts (argo_floats)
                    ├──► MongoDB   : variable-structure blobs (sensors, launch_config, ...)
                    └──► Vector DB : embedded text summary for RAG

Idempotent: every store is keyed by `wmo`. Re-running the pipeline replaces the
prior version of each float. No destructive ops on existing rows.

Run after fetch + merge_parts have produced data/parts/*.parquet and
data/allmetadata.parquet.

CLI:
    python -m pgdb_setup.pipeline --parquet data/allmetadata.parquet
    python -m pgdb_setup.pipeline --parquet data/parts/metadata_0-999.parquet
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List

# Ensure repo root is on path BEFORE importing package modules.
ROOT = Path(__file__).resolve().parent.parent  # repo root
sys.path.insert(0, str(ROOT))

import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

from pgdb_setup.schema.mongo_setup import upsert_float_details, init_indexes as init_mongo
from pgdb_setup.schema.vector_setup import upsert_float as upsert_vector, get_collection as get_vector_collection

# --------------------------------------------------------------------- config
PG_BATCH = 500


# ===========================================================================
# 1.  Per-float field split: which fields go where
# ===========================================================================

POSTGRES_COLUMNS = [
    "wmo", "platform_number", "platform_type", "platform_maker",
    "float_serial_no", "firmware_version", "manual_version", "wmo_inst_type",
    "data_centre", "data_centre_reference", "project_name", "pi_name",
    "deployment_platform", "deployment_cruise_id",
    "deployment_date", "deployment_lat", "deployment_lon",
    "start_date", "end_mission_date", "end_mission_status",
    "battery_type", "battery_packs",
    "controller_board_type", "controller_board_serial",
    "transmission_system", "transmission_id", "transmission_frequency",
    "positioning_system", "data_mode", "data_state_indicator",
    "source_url", "extraction_date",
]

# Anything not in POSTGRES_COLUMNS but present in the row → MongoDB blob.
# These are the variable-structure, per-float fields that justify NoSQL.
MONGO_BLOB_FIELDS = [
    "sensors", "sensor_makers", "sensor_models", "sensor_serial_numbers",
    "sensor_details",
    "launch_config_parameters", "launch_config_values",
    "config_parameters", "config_values",
    "launch_config", "config",
    "global_title", "global_institution", "global_source",
    "global_history", "global_references", "global_comment",
    "global_user_manual_version", "global_conventions",
    "parameter_details", "start_date_qc",
]


# ===========================================================================
# 2.  Helpers
# ===========================================================================

def _clean(value: Any) -> Any:
    """Coerce NaN/None/empty into JSON-safe value."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        v = value.strip()
        if not v or v.lower() in {"nan", "null", "n/a"}:
            return None
        return v
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def _to_json(value: Any) -> Any:
    """Decode JSON-encoded strings (from sensor_details etc) into Python objects."""
    if isinstance(value, str):
        s = value.strip()
        if s.startswith(("[", "{")):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                return value
    return value


def _to_iso(value: Any) -> Any:
    """Best-effort coerce date-like strings to ISO 8601."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            ts = pd.to_datetime(s, errors="raise")
            if pd.isna(ts):
                return None
            return ts.to_pydatetime().isoformat()
        except Exception:
            return s
    return value


def _to_float(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ===========================================================================
# 3.  Transform: row → (pg_row, mongo_blob, vector_text)
# ===========================================================================

def split_row(row: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], str, Dict[str, Any]]:
    """Return (postgres_row, mongo_blob, vector_text, vector_meta)."""
    cleaned = {k: _clean(v) for k, v in row.items()}

    # ---- Postgres core -------------------------------------------------
    pg = {}
    for col in POSTGRES_COLUMNS:
        pg[col] = cleaned.get(col)

    # date coercions
    for dcol in ("deployment_date", "start_date", "end_mission_date", "extraction_date"):
        pg[dcol] = _to_iso(pg.get(dcol))

    # lat/lon
    pg["deployment_lat"] = _to_float(pg.get("deployment_lat"))
    pg["deployment_lon"] = _to_float(pg.get("deployment_lon"))

    # source URL the file came from
    if not pg.get("source_url") and cleaned.get("file"):
        pg["source_url"] = f"https://data-argo.ifremer.fr/dac/{cleaned['file']}"

    if not pg.get("wmo"):
        # skip rows that lack a natural key
        return None, None, "", {}

    # ---- Mongo blob ----------------------------------------------------
    mongo = {}
    for f in MONGO_BLOB_FIELDS:
        if f in cleaned and cleaned[f] is not None:
            v = _to_json(cleaned[f])
            if v is not None:
                mongo[f] = v
    mongo["file"] = cleaned.get("file")
    mongo["profiler_type"] = cleaned.get("profiler_type")
    mongo["institution"] = cleaned.get("institution")
    mongo["date_update"] = _to_iso(cleaned.get("date_update"))

    # ---- Vector summary ------------------------------------------------
    parts = []
    if pg.get("platform_type"):
        parts.append(f"Platform: {pg['platform_type']}")
    if pg.get("platform_maker"):
        parts.append(f"Maker: {pg['platform_maker']}")
    if pg.get("float_serial_no"):
        parts.append(f"Serial: {pg['float_serial_no']}")
    if pg.get("firmware_version"):
        parts.append(f"Firmware: {pg['firmware_version']}")
    if pg.get("project_name"):
        parts.append(f"Project: {pg['project_name']}")
    if pg.get("pi_name"):
        parts.append(f"PI: {pg['pi_name']}")
    if pg.get("data_centre"):
        parts.append(f"Data centre: {pg['data_centre']}")
    if pg.get("deployment_platform"):
        parts.append(f"Deployed from: {pg['deployment_platform']}")
    if pg.get("deployment_cruise_id"):
        parts.append(f"Cruise: {pg['deployment_cruise_id']}")
    if pg.get("deployment_date"):
        parts.append(f"Deployed: {pg['deployment_date'][:10]}")
    if pg.get("deployment_lat") is not None and pg.get("deployment_lon") is not None:
        parts.append(f"At lat {pg['deployment_lat']:.3f}, lon {pg['deployment_lon']:.3f}")
    if pg.get("start_date"):
        parts.append(f"Active from: {pg['start_date'][:10]}")
    if pg.get("end_mission_date"):
        parts.append(f"Mission end: {pg['end_mission_date'][:10]} ({pg.get('end_mission_status') or 'unknown'})")

    sensors = mongo.get("sensor_details") or mongo.get("sensors")
    if isinstance(sensors, list) and sensors:
        if isinstance(sensors[0], dict):
            sensor_str = ", ".join(
                f"{s.get('type','?')} ({s.get('maker','') or '?'} {s.get('model','') or '?'})".strip()
                for s in sensors[:6]
            )
        else:
            sensor_str = ", ".join(str(s) for s in sensors[:6])
        parts.append(f"Sensors: {sensor_str}")

    launch_cfg = mongo.get("launch_config")
    if isinstance(launch_cfg, list) and launch_cfg:
        sample = ", ".join(
            f"{c.get('parameter','?')}={c.get('value','?')}"
            for c in launch_cfg[:6] if isinstance(c, dict)
        )
        parts.append(f"Launch config: {sample}")

    history = mongo.get("config")
    if isinstance(history, list) and history:
        sample = ", ".join(
            f"{c.get('parameter','?')}={c.get('value','?')}"
            for c in history[:6] if isinstance(c, dict)
        )
        parts.append(f"Config history: {sample}")

    if mongo.get("global_history"):
        parts.append(f"History: {str(mongo['global_history'])[:300]}")
    if mongo.get("global_comment"):
        parts.append(f"Comment: {str(mongo['global_comment'])[:300]}")

    text = ". ".join(parts) + "."

    # Filterable vector metadata
    vmeta = {
        "platform_type": pg.get("platform_type"),
        "data_centre": pg.get("data_centre"),
        "deployment_year": pg["deployment_date"][:4] if pg.get("deployment_date") else None,
    }

    return pg, mongo, text, {k: v for k, v in vmeta.items() if v is not None}


# ===========================================================================
# 4.  Loaders
# ===========================================================================

def _pg_connect(database_url: str):
    return psycopg2.connect(database_url)


def load_postgres(rows: Iterable[Dict[str, Any]], database_url: str) -> int:
    rows = [r for r in rows if r and r.get("wmo")]
    if not rows:
        return 0

    cols = POSTGRES_COLUMNS
    update_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "wmo")
    sql = f"""
        INSERT INTO argo_floats ({",".join(cols)})
        VALUES %s
        ON CONFLICT (wmo) DO UPDATE SET
        {update_clause}
    """

    values = [
        tuple(_clean(r.get(c)) for c in cols) for r in rows
    ]

    conn = _pg_connect(database_url)
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, values, page_size=PG_BATCH)
        conn.commit()
    finally:
        conn.close()
    return len(rows)


def load_mongo(rows_payload: Iterable[tuple[str, Dict[str, Any]]]) -> int:
    n = 0
    for wmo, blob in rows_payload:
        if not wmo or not blob:
            continue
        upsert_float_details(wmo, blob)
        n += 1
    return n


def load_vector(rows_payload: Iterable[tuple[str, str, Dict[str, Any]]]) -> int:
    n = 0
    for wmo, text, meta in rows_payload:
        if not wmo or not text:
            continue
        upsert_vector(wmo, text, meta)
        n += 1
    return n


# ===========================================================================
# 5.  Orchestrator
# ===========================================================================

def run(parquet_path: str, database_url: str) -> Dict[str, int]:
    init_mongo()
    df = pd.read_parquet(parquet_path)
    print(f"Read {len(df)} rows from {parquet_path}")

    pg_rows: List[Dict[str, Any]] = []
    mongo_rows: List[tuple[str, Dict[str, Any]]] = []
    vector_rows: List[tuple[str, str, Dict[str, Any]]] = []

    for _, raw in df.iterrows():
        row = raw.to_dict()
        pg, mongo, text, vmeta = split_row(row)
        if not pg or not pg.get("wmo"):
            continue
        wmo = pg["wmo"]
        pg_rows.append(pg)
        mongo_rows.append((wmo, mongo))
        vector_rows.append((wmo, text, vmeta))

    print(f"Loading {len(pg_rows)} → Postgres")
    n_pg = load_postgres(pg_rows, database_url)

    print(f"Loading {len(mongo_rows)} → MongoDB")
    n_mg = load_mongo(mongo_rows)

    print(f"Loading {len(vector_rows)} → Vector store")
    n_vc = load_vector(vector_rows)

    print(f"Vector store total docs: {get_vector_collection().count()}")
    return {"postgres": n_pg, "mongo": n_mg, "vector": n_vc}


def main():
    ap = argparse.ArgumentParser(description="Ingest ARGO parquet → Postgres + Mongo + Vector")
    ap.add_argument("--parquet", required=True, help="Path to merged parquet file")
    ap.add_argument("--db-url", default=None, help="Postgres DATABASE_URL (else from env)")
    args = ap.parse_args()

    import os
    from dotenv import load_dotenv
    load_dotenv()

    db_url = args.db_url or os.getenv("DATABASE_URL")
    if not db_url:
        ap.error("DATABASE_URL not set (env or --db-url)")

    result = run(args.parquet, db_url)
    print("Done:", result)


if __name__ == "__main__":
    main()
