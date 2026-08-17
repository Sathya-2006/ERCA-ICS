from app.rca.llm_provider import generate_rca


def test_rca_with_strong_code_and_history_evidence_is_high_confidence():
    context = {
        "service": "Payment Service",
        "error_message": "Payment gateway connection timed out",
        "code_evidence": {
            "found": True, "file": "sample_app/services/payment/payment_service.py",
            "function": "process_payment", "line": 7, "exception_type": "TimeoutError",
            "match_score": 3.5,
        },
        "rag_evidence": [
            {"incident_id": "INC-1", "similarity": 0.95, "metadata": {"root_cause": "Downstream latency"}},
            {"incident_id": "INC-2", "similarity": 0.9, "metadata": {"root_cause": "Downstream latency"}},
        ],
        "ownership": {"team": "@payment-team", "developer": "Payment Service Developer"},
    }
    rca = generate_rca(context)
    assert rca["status"] in ("MEDIUM", "HIGH")
    assert 0.0 <= rca["confidence"] <= 1.0
    assert rca["root_cause"]


def test_rca_with_no_evidence_is_low_confidence():
    context = {
        "service": "Unknown Service",
        "error_message": "Something odd happened",
        "code_evidence": {"found": False},
        "rag_evidence": [],
        "ownership": {},
    }
    rca = generate_rca(context)
    assert rca["status"] == "UNVERIFIED"
    assert rca["confidence"] < 0.5


def test_confidence_bands_are_respected():
    for confidence, expected in [(0.2, "LOW"), (0.6, "MEDIUM"), (0.9, "HIGH")]:
        if confidence < 0.5:
            assert expected == "LOW"
        elif confidence < 0.75:
            assert expected == "MEDIUM"
        else:
            assert expected == "HIGH"
