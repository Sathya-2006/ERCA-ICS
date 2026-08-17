from __future__ import annotations

from sqlalchemy.orm import Session

from app.config import get_settings
from app.rag.retriever import retrieve_similar_incidents

settings = get_settings()


def get_historical_evidence(db: Session, error_message: str, service: str) -> list[dict]:
    query = f"Service: {service}\nError: {error_message}"
    return retrieve_similar_incidents(db, query, top_k=settings.RAG_TOP_K)


def detect_known_incident(evidence: list[dict]) -> dict | None:
    """
    If the top historical match is extremely similar to the new incident,
    surface it as a "KNOWN INCIDENT" hint. The system still performs a
    fresh RCA regardless (see app/rca/engine.py) -- this is informational.
    """
    if not evidence:
        return None
    top = evidence[0]
    if top["similarity"] >= settings.RAG_KNOWN_INCIDENT_THRESHOLD:
        return {
            "previous_incident_id": top["incident_id"],
            "similarity": top["similarity"],
            "previous_root_cause": top["metadata"].get("root_cause"),
            "document": top["document"],
        }
    return None
