"""
MongoDB setup for ARGO float variable metadata.

Stores schema-less blobs: sensor lists, launch_config params, config_history,
predeployment calibration, free-form fields that vary per float.

Mongo is the source of truth for these blobs; the vector store mirrors a
text summary derived from them for semantic retrieval.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.collection import Collection
from pymongo.database import Database
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "argo")

FLOAT_DETAILS_COLLECTION = "float_details"


def get_client() -> MongoClient:
    return MongoClient(MONGO_URI)


def get_db() -> Database:
    return get_client()[MONGO_DB]


def get_float_details() -> Collection:
    return get_db()[FLOAT_DETAILS_COLLECTION]


def init_indexes() -> None:
    coll = get_float_details()
    coll.create_index([("wmo", ASCENDING)], unique=True)
    coll.create_index([("data_centre", ASCENDING)])
    coll.create_index([("extraction_date", DESCENDING)])


def upsert_float_details(wmo: str, payload: Dict[str, Any]) -> None:
    """Idempotent insert keyed by wmo."""
    payload = {"wmo": wmo, **payload}
    get_float_details().update_one(
        {"wmo": wmo},
        {"$set": payload},
        upsert=True,
    )


def get_float_details_doc(wmo: str) -> Dict[str, Any] | None:
    return get_float_details().find_one({"wmo": wmo})


if __name__ == "__main__":
    init_indexes()
    print(f"Connected to {MONGO_URI}/{MONGO_DB}, indexes ready on '{FLOAT_DETAILS_COLLECTION}'.")
