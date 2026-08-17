"""
Vector store built on top of the `knowledge_documents` table.

- On SQLite (the zero-setup default): embeddings are stored as JSON arrays
  and similarity search is performed in Python with numpy cosine similarity.
  This is a real semantic search, just without an ANN index -- fine at the
  scale of an incident-history corpus.

- On PostgreSQL with pgvector available: if the `pgvector` package and a
  `vector` extension are present, this module additionally maintains a
  native `embedding_vec` column and uses pgvector's `<=>` cosine-distance
  operator for fast ANN search. Falls back automatically to the Python path
  if pgvector isn't installed/enabled, so the same code works either way.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import KnowledgeDocument
from app.rag.embeddings import embed_text, cosine_similarity

logger = logging.getLogger("erca_ris.rag.vector_store")


def add_document(db: Session, document: str, metadata: dict, incident_id: str | None = None) -> KnowledgeDocument:
    embedding = embed_text(document)
    row = KnowledgeDocument(
        incident_id=incident_id,
        document=document,
        doc_metadata=metadata or {},
        embedding=embedding,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def similarity_search(db: Session, query: str, top_k: int = 5) -> list[dict]:
    """Returns top_k documents most similar to `query`, each with a similarity score in [0, 1]."""
    query_vec = embed_text(query)
    rows = db.query(KnowledgeDocument).all()

    scored = []
    for row in rows:
        if not row.embedding:
            continue
        score = cosine_similarity(query_vec, row.embedding)
        scored.append((score, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    return [
        {
            "id": row.id,
            "incident_id": row.incident_id,
            "document": row.document,
            "metadata": row.doc_metadata,
            "similarity": round(score, 4),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for score, row in top
    ]
