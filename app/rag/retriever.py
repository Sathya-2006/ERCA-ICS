from __future__ import annotations

from sqlalchemy.orm import Session

from app.rag.vector_store import similarity_search


def retrieve_similar_incidents(db: Session, query: str, top_k: int = 5) -> list[dict]:
    """Semantic retrieval over historical/resolved incident knowledge documents."""
    return similarity_search(db, query, top_k=top_k)


def best_match(db: Session, query: str) -> dict | None:
    results = retrieve_similar_incidents(db, query, top_k=1)
    return results[0] if results else None
