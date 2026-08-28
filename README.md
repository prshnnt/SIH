# sih_ps_rag

SQL RAG chatbot over ARGO oceanographic float metadata. Three independent modules.

## Layout

```
SIH/
├── frontend/                        # React 19 + Vite UI (stub — renders "Home")
├── server/                          # FastAPI backend
│   ├── app/
│   │   ├── main.py                  # mounts /chat and /health routers
│   │   ├── routes/
│   │   │   ├── chat.py              # POST /chat/send_stream (non-streaming)
│   │   │   └── health.py            # health checks
│   │   ├── services/
│   │   │   └── llm_services.py      # imports run_chat_graph_stream (DOES NOT EXIST)
│   │   ├── models/
│   │   │   └── chat_models.py       # Pydantic request/response models
│   │   ├── utils/
│   │   │   └── helpers.py           # (empty)
│   │   └── llm_backend/
│   │       ├── graph/
│   │       │   └── chat_graph.py    # entire RAG pipeline in one file
│   │       └── utils/
│   │           └── llm_helpers.py   # Pydantic memory/session models
│   ├── requirements.txt
│   ├── activate.bat / deactivate.bat
│   └── .venv/
└── pgdb_setup/                      # offline ETL: ARGO fetch → Postgres + Mongo + Vector
    ├── fetch/metadata/              # slice-based parquet fetcher
    │   ├── main.py                  # python main.py <start> <end>
    │   ├── merge_parts.py           # combine parts → allmetadata.parquet
    │   ├── save_floatlist.py
    │   └── utils.py                 # ArgoMetadataExtractor
    ├── schema/
    │   ├── postgres_schema.sql      # argo_floats table
    │   ├── mongo_setup.py           # Mongo client + collection init
    │   └── vector_setup.py          # Chroma persistent client
    ├── pipeline.py                  # orchestrator: parquet → 3 stores
    ├── push/metadata/               # OLD 6-table hypertable loader (superseded, kept for ref)
    │   ├── commit.py
    │   └── main.py
    ├── testdb/                      # separate SQLite sandbox (fetch/push users example only)
    ├── main.py
    ├── requirements.txt
    └── README.md                    # pgdb_setup-specific docs
```

## Quick start

### Frontend

```bash
cd frontend
npm install
npm run dev          # Vite dev server (default :5173)
npm run build        # production build → dist/
npm run lint
```

Current `App.jsx` is a stub returning `<>Home</>`. UI work not started.

### Server

```bash
cd server
# Windows
activate.bat
# Unix
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Endpoints:

| Method | Path | Notes |
|--------|------|-------|
| GET    | `/`         | `{"message": "Server is running"}` |
| POST   | `/chat/send_stream` | **Not streaming** — name is misleading; returns plain dict from `chat_with_database()` |
| GET    | `/health/*` | health checks |

No test runner. No `npm test`, no `pytest`.

### pgdb_setup (ETL)

```bash
cd pgdb_setup
pip install -r requirements.txt

# 1. fetch floats (slice-based, parallelisable)
cd fetch/metadata
python main.py 0 1000            # → data/parts/metadata_0-999.parquet
python main.py 1000 2000

# 2. merge
python merge_parts.py           # → data/allmetadata.parquet

# 3. ingest into Postgres + MongoDB + Chroma
cd ../..
python -m pgdb_setup.pipeline --parquet pgdb_setup/data/allmetadata.parquet
```

Idempotent — keyed by `wmo`, re-runs replace prior rows. Full per-store schema lives in [`pgdb_setup/README.md`](pgdb_setup/README.md).

## Architecture

### Server → LangGraph SQL RAG pipeline

Core flow in `server/app/llm_backend/graph/chat_graph.py`:

1. **`generate_sql_query`** — Groq LLM (`ChatGroq`, `openai/gpt-oss-20b`) converts user question → PostgreSQL SELECT. Schema is **hardcoded** in `get_database_schema()` covering 6 tables (`argo_float_metadata`, `argo_launch_config`, `argo_config_history`, `argo_sensors`, `argo_positioning_systems`, `argo_transmission_systems`) and view `v_argo_float_complete`.
2. **`is_safe_sql_query`** — read-only enforcement. Rejects: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`, `REVOKE`, `EXEC`, multi-statement queries, comments. Does **not** restrict which tables/columns the LLM can SELECT.
3. **`execute_sql_query`** — `psycopg2` connection (URL hardcoded at `chat_graph.py:71`, Neon Postgres), `SET statement_timeout = 30000`, executes, formats as `col | col | ...` rows.
4. **`generate_natural_response`** — Groq LLM (temperature 0.7) turns results → conversational reply.

State via `SQLRAGState` TypedDict. Graph entry point: `chat_with_database(question)`.

### Known broken paths

- `services/llm_services.py` imports `run_chat_graph_stream` — **does not exist** in `chat_graph.py`. That module only exposes `create_sql_rag_graph` and `chat_with_database`. Streaming path is dead code.
- `/chat/send_stream` returns a plain dict, not a stream. Rename or reimplement before exposing as SSE.

### pgdb_setup pipeline

`pgdb_setup/pipeline.py` is the canonical load path post-`merge_parts.py`:

- **Postgres** (`argo_floats`, single flat table) — keyed relational facts. Schema in `schema/postgres_schema.sql`.
- **MongoDB** (`float_details`) — variable-structure blobs: sensors, launch_config, config_history, `global_*` attrs.
- **Chroma** — one embedded text summary per float with filterable `{platform_type, data_centre, deployment_year}` metadata.

`push/metadata/commit.py` (old 6-table hypertable loader + PostGIS) is **superseded**. Kept for reference.

`testdb/` is a separate SQLite sandbox with SQLAlchemy models — used for the fetch/push users example only, not connected to the ARGO data.

## Environment

| Path | Vars |
|------|------|
| `server/app/llm_backend/.env` | `GROQ_API_KEY`, `DATABASE_URL` |
| `pgdb_setup/.env`             | `DATABASE_URL`, Mongo + Chroma config |
| `pgdb_setup/push/metadata/commit.py` | `DEFAULT_DB_CONFIG` (local fallback) |

`activate.bat` / `deactivate.bat` exist for both `server/` and `pgdb_setup/`.

## Security

Hardcoded credentials in source — **rotate before sharing externally**:

- `server/app/llm_backend/graph/chat_graph.py:71` — Neon Postgres URL with password.
- `pgdb_setup/push/metadata/commit.py:14` — local Postgres `password='hello'`.

Safety check `is_safe_sql_query` blocks writes but does not restrict SELECT scope. Schema is hardcoded; if DB structure changes, update `get_database_schema()` or the LLM will hallucinate column names.
