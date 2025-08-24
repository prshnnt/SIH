# app.py
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

import chromadb
from sentence_transformers import SentenceTransformer

from sqlalchemy import create_engine, Column, String, Text
from sqlalchemy.orm import declarative_base, sessionmaker, Session as SASession

# ----------------------------
# SQLAlchemy setup
# ----------------------------
DATABASE_URL = "sqlite:///sih_ps.db"
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

class SIHPS(Base):
    __tablename__ = "sih_ps"
    Statement_id = Column(String, primary_key=True, unique=True, nullable=False)
    Title = Column(Text)
    Technology_Bucket = Column(Text)
    Department = Column(Text)
    Organisation = Column(Text)
    Description = Column(Text)

# ----------------------------
# Pydantic schemas
# ----------------------------
class SIHPSOut(BaseModel):
    Statement_id: str
    Title: Optional[str] = None
    Technology_Bucket: Optional[str] = None
    Department: Optional[str] = None
    Organisation: Optional[str] = None
    Description: Optional[str] = None

class SIHPSLIST(BaseModel):
    record: List[SIHPSOut]

class SearchHit(BaseModel):
    Statement_id: str
    score: Optional[float] = None  # distance or similarity depending on Chroma settings
    record: SIHPSOut

class SearchResponse(BaseModel):
    query: str
    results: List[SearchHit]

# ----------------------------
# FastAPI app & globals
# ----------------------------
app = FastAPI(title="SIH Problem Statements Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],            # or ["*"] to allow all (not recommended for production)
    allow_credentials=False,
    allow_methods=["*"],             # Allow all HTTP methods
    allow_headers=["*"],             # Allow all headers
)
# Global (lazy) resources
_chroma_client = None
_collection = None
_model = None

def get_db() -> SASession:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------------
# Startup: load embeddings model & Chroma collection
# ----------------------------
@app.on_event("startup")
def startup_event():
    global _chroma_client, _collection, _model
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path="chroma_db")
    if _collection is None:
        _collection = _chroma_client.get_collection("sih_ps")
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")


# ----------------------------
# Get a single record by Statement_id
# ----------------------------
@app.get("/items/{statement_id}", response_model=SIHPSOut)
def get_item(statement_id: str, db: SASession = Depends(get_db)):
    rec = db.query(SIHPS).filter(SIHPS.Statement_id == statement_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Statement_id not found")
    return SIHPSOut(
        Statement_id=rec.Statement_id,
        Title=rec.Title,
        Technology_Bucket=rec.Technology_Bucket,
        Department=rec.Department,
        Organisation=rec.Organisation,
        Description=rec.Description,
    )
@app.get("/items/", response_model=SIHPSLIST)
def get_items(db: SASession = Depends(get_db)):
    recs = db.query(SIHPS).all()
    return SIHPSLIST(record=[
        SIHPSOut(
            Statement_id=rec.Statement_id,
            Title=rec.Title,
            Technology_Bucket=rec.Technology_Bucket,
            Department=rec.Department,
            Organisation=rec.Organisation,
            Description=rec.Description,
        ) for rec in recs
    ])

# ----------------------------
# Semantic search endpoint
# ----------------------------
@app.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., description="Search query text"),
    top_k: int = Query(5, ge=1, le=150),
    db: SASession = Depends(get_db),
):
    # Encode query
    query_embedding = _model.encode([q])

    # Query Chroma
    results = _collection.query(
        query_embeddings=query_embedding,
        include=["distances"]  # returns distances; lower is closer for default metric
    )

    # Chroma returns lists-of-lists
    ids = results.get("ids", [[]])[0] if results.get("ids") else []
    distances = results.get("distances", [[]])[0] if results.get("distances") else []

    ids = [id_ for id_, dist in zip(ids, distances) if dist < 1.8]

    if not ids:
        return SearchResponse(query=q, results=[])

    # Fetch all matching records from SQL in one round-trip
    rows = (
        db.query(SIHPS)
        .filter(SIHPS.Statement_id.in_(ids))
        .all()
    )
    row_map = {r.Statement_id: r for r in rows}

    # Preserve the order returned by Chroma
    hits: List[SearchHit] = []
    for i, sid in enumerate(ids):
        rec = row_map.get(sid)
        if not rec:
            # If an ID exists in Chroma but not in SQL, skip or add placeholder
            continue
        hits.append(
            SearchHit(
                Statement_id=sid,
                score=distances[i] if i < len(distances) else None,
                record=SIHPSOut(
                    Statement_id=rec.Statement_id,
                    Title=rec.Title,
                    Technology_Bucket=rec.Technology_Bucket,
                    Department=rec.Department,
                    Organisation=rec.Organisation,
                    Description=rec.Description,
                ),
            )
        )

    return SearchResponse(query=q, results=hits)

@app.get("/")
def root():
    return {"endpoints": ["/health", "/search?q=...", "/items/{statement_id}"]}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="localhost", port=8000, log_level="info")