"""
Vector store setup for ARGO float metadata.

Stores one document per float:
  - id       = wmo (matches Postgres PK)
  - text     = concatenated natural-language summary of the float
  - metadata = filterable facets (platform_type, data_centre, deployment_year, ...)

Uses ChromaDB in embedded (persistent) mode — no external server needed.
The same collection is read from server/ at RAG time.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

# Persistent client (writes to disk). The same path is read by server/.
VECTOR_DIR = os.getenv("VECTOR_DIR", "./.vector_store")
COLLECTION_NAME = os.getenv("VECTOR_COLLECTION", "argo_floats")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")

_client = None
_collection = None


def get_client():
    global _client
    if _client is None:
        import chromadb
        from chromadb.config import Settings
        os.makedirs(VECTOR_DIR, exist_ok=True)
        _client = chromadb.PersistentClient(path=VECTOR_DIR, settings=Settings(anonymized_telemetry=False))
    return _client


def get_collection():
    global _collection
    if _collection is None:
        from chromadb.utils import embedding_functions
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        _collection = get_client().get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def upsert_float(
    wmo: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    coll = get_collection()
    safe_meta = {k: v for k, v in (metadata or {}).items() if v is not None and isinstance(v, (str, int, float, bool))}
    coll.upsert(ids=[wmo], documents=[text], metadatas=[safe_meta])


def query(text: str, n_results: int = 5, where: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return get_collection().query(query_texts=[text], n_results=n_results, where=where)


def count() -> int:
    return get_collection().count()


if __name__ == "__main__":
    c = get_collection()
    print(f"Vector store ready: {VECTOR_DIR} / '{COLLECTION_NAME}', docs={c.count()}")
