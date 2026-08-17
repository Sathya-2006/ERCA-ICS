from app.rag.indexer import index_raw_document
from app.rag.retriever import retrieve_similar_incidents
from app.rag.rag_service import detect_known_incident


def test_indexed_document_is_retrievable(db_session):
    index_raw_document(
        db_session,
        document="Incident: INC-TEST-0001\nService: Payment Service\nError: Payment gateway connection timed out\nRoot Cause: Downstream latency",
        metadata={"incident_id": "INC-TEST-0001", "root_cause": "Downstream latency"},
        incident_id="INC-TEST-0001",
    )
    results = retrieve_similar_incidents(db_session, "Payment gateway connection timed out", top_k=3)
    assert len(results) >= 1
    assert results[0]["incident_id"] == "INC-TEST-0001"
    assert results[0]["similarity"] > 0.3


def test_dissimilar_query_scores_lower(db_session):
    index_raw_document(
        db_session,
        document="Service: Payment Service\nError: Payment gateway connection timed out",
        metadata={"incident_id": "INC-TEST-0002", "root_cause": "Latency"},
        incident_id="INC-TEST-0002",
    )
    close = retrieve_similar_incidents(db_session, "Payment gateway connection timed out", top_k=1)
    far = retrieve_similar_incidents(db_session, "Completely unrelated topic about gardening", top_k=1)
    assert close[0]["similarity"] >= far[0]["similarity"]


def test_known_incident_detection_threshold(db_session):
    document = "Service: Payment Service\nError: Payment gateway connection timed out"
    index_raw_document(
        db_session,
        document=document,
        metadata={"incident_id": "INC-TEST-0003", "root_cause": "Latency"},
        incident_id="INC-TEST-0003",
    )
    # Query in the same "Service: ...\nError: ..." shape the RCA pipeline actually uses,
    # so an (near-)identical incident is correctly recognized as maximally similar.
    evidence = retrieve_similar_incidents(db_session, document, top_k=1)
    known = detect_known_incident(evidence)
    assert known is not None
    assert known["previous_incident_id"] == "INC-TEST-0003"
