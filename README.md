# sih_ps_rag

MAIN/
│
├── frontend/                 # Your React/Vite frontend
│
├── server/                   # FastAPI backend
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI app entrypoint
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── chat.py       # Chat-related endpoints
│   │   │   └── health.py     # Health check or other endpoints
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   └── llm_service.py  # Calls to llm_backend graph
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── chat_models.py  # Pydantic models for requests/responses
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── helpers.py      # Common helper functions
│   └── requirements.txt
│
└── llm_backend/              # LangGraph backend
    ├── __init__.py
    ├── graph/
    │   ├── __init__.py
    │   ├── nodes/
    │   │   ├── __init__.py
    │   │   ├── data_fetch_node.py     # Node for fetching data
    │   │   ├── formatting_node.py    # Node for formatting
    │   │   └── decision_node.py      # Node for decision-making
    │   └── main_graph.py             # Build and run your LangGraph graph
    ├── utils/
    │   ├── __init__.py
    │   └── llm_helpers.py            # Helpers for LangGraph
    └── requirements.txt
