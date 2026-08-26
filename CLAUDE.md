# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`sih_ps_rag` — SQL RAG chatbot for ARGO oceanographic float metadata. Three independent modules:

- `frontend/` — React 19 + Vite UI. Currently a stub (`App.jsx` returns `<>Home</>`).
- `server/` — FastAPI backend exposing chat endpoints.
- `pgdb_setup/` — Offline ETL: fetch ARGO float metadata → parquet → bulk-insert into Postgres.

## Commands

### Frontend (`frontend/`)
```bash
npm install          # one-time
npm run dev          # Vite dev server
npm run build        # production build → dist/
npm run preview      # preview prod build
npm run lint         # ESLint (flat config, eslint.config.js)
```

### Server (`server/`)
Activate venv first: `server/activate.bat` (Windows) or `source server/.venv/bin/activate` (Unix).

```bash
pip install -r requirements.txt                    # one-time
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000   # dev server
```

No test runner configured. No `npm test`, no `pytest` setup.

### pgdb_setup ETL
No CLI framework — run scripts directly. Typical pipeline:

```bash
cd pgdb_setup/fetch/metadata
python main.py <start_index> <end_index>          # fetch a slice of floats → data/parts/metadata_<a>-<b>.parquet

cd ../../
python fetch/metadata/merge_parts.py              # combine parts → data/allmetadata.parquet

cd push/metadata
python main.py                                     # bulk-insert parquet → Postgres
```

Scripts read creds from `.env` (`DATABASE_URL`) and `commit.py`'s `DEFAULT_DB_CONFIG` (local fallback).

## Architecture

### Server → LangGraph SQL RAG pipeline

`server/app/main.py` mounts two routers: `/chat/*` (chat.py) and `/health/*` (health.py).

The core flow lives in `server/app/llm_backend/graph/chat_graph.py`:

1. **`generate_sql_query`** — Groq LLM (`ChatGroq`, model `openai/gpt-oss-20b`) converts user question → PostgreSQL SELECT. Hardcoded schema string in `get_database_schema()` describes 5 tables + 1 view (`argo_float_metadata`, `argo_launch_config`, `argo_config_history`, `argo_sensors`, `argo_positioning_systems`, `argo_transmission_systems`, view `v_argo_float_complete`).
2. **`is_safe_sql_query`** — rejects any query containing INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/GRANT/REVOKE/EXEC, multiple statements, or comments. Read-only enforcement.
3. **`execute_sql_query`** — `psycopg2` connection (URL hardcoded at `chat_graph.py:71` — Neon Postgres, see Security), `SET statement_timeout = 30000`, executes, formats as `col | col | ...` rows.
4. **`generate_natural_response`** — Groq LLM (temperature 0.7) turns results → conversational reply.

State flows via `SQLRAGState` TypedDict. Two API surfaces wrap the graph:
- `chat_graph.chat_with_database(question)` — sync, used by `routes/chat.py` at `POST /chat/send_stream` (despite the name, returns a plain dict, not a stream).
- `services/llm_services.py` imports `run_chat_graph_stream` — **does not exist** in `chat_graph.py`. That module only defines `create_sql_rag_graph`, `chat_with_database`, and the three node functions. The streaming path is broken.

### pgdb_setup ETL

- **fetch** — `fetch/metadata/utils.py::ArgoMetadataExtractor` pulls the global float list from ARGO GDAC, then per-float metadata. `fetch/metadata/main.py` slices the list by index and writes per-batch parquet parts.
- **merge_parts.py** — combines `data/parts/*.parquet` into `data/allmetadata.parquet` with explicit PyArrow schema (`list<string>` for sensor/config arrays, `list<struct<parameter,value>>` for launch_config/config).
- **push/metadata/commit.py** — `load_parquet_to_postgres()` bulk-inserts in batches of 1000 across 6 tables (`argo_float_metadata`, `argo_sensors`, `argo_positioning_systems`, `argo_transmission_systems`, `argo_launch_config`, `argo_config_history`). On batch failure, falls back to row-by-row insert and logs errors grouped by duplicate vs other.

`testdb/` is a separate SQLite sandbox with SQLAlchemy models — used for the fetch/push users example only, not connected to the ARGO data.

## Critical files

- `server/app/llm_backend/graph/chat_graph.py` — entire RAG logic in one file. Edit here for query/safety/LLM changes.
- `pgdb_setup/push/metadata/commit.py` — bulk-insert pipeline. Six `prepare_*_batch` functions share the same `(wmo, platform_number, launch_date)` join key.
- `pgdb_setup/fetch/metadata/merge_parts.py` — PyArrow schema construction; required before push because `commit.py` expects nested list/struct columns.

## Environment

- `server/app/llm_backend/.env` — Groq key (`GROQ_API_KEY`) and DB URL expected.
- `pgdb_setup/push/metadata/.env` — `DATABASE_URL` for push target.
- `activate.bat` / `deactivate.bat` exist for both `server/` and `pgdb_setup/`.

## Security

Hardcoded credentials in source — rotate before sharing externally:
- `server/app/llm_backend/graph/chat_graph.py:71` — Neon Postgres URL with password.
- `pgdb_setup/push/metadata/commit.py:14` — local Postgres `password='hello'`.

Safety check `is_safe_sql_query` blocks write operations but does not restrict which tables/columns the LLM can SELECT. Schema is hardcoded; if DB structure changes, update `get_database_schema()` or the LLM will hallucinate column names.
