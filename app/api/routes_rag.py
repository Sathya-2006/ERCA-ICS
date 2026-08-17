from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas import RagSearchRequest, RagIndexRequest
from app.rag.retriever import retrieve_similar_incidents
from app.rag.indexer import index_raw_document

router = APIRouter(prefix="/api/rag", tags=["rag"])


@router.post("/search")
def search(payload: RagSearchRequest, db: Session = Depends(get_db)):
    results = retrieve_similar_incidents(db, payload.query, top_k=payload.top_k)
    return {"query": payload.query, "results": results}


@router.post("/index")
def index_document(payload: RagIndexRequest, db: Session = Depends(get_db)):
    row = index_raw_document(db, payload.document, payload.metadata, payload.incident_id)
    return {"id": row.id, "incident_id": row.incident_id, "created_at": row.created_at.isoformat()}
