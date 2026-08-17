from app.remediation.patch_generator import generate_patch


def test_patch_generated_for_known_location():
    code_evidence = {
        "found": True, "file": "sample_app/services/payment/payment_service.py",
        "function": "process_payment", "line": 7, "exception_type": "TimeoutError",
    }
    rca = {"root_cause": "Downstream latency", "recommended_resolution": "Increase timeout"}
    patch = generate_patch(code_evidence, rca)
    assert "payment_service.py" in patch
    assert "review and adapt" in patch
    assert "Downstream latency" in patch


def test_patch_never_fabricates_location_when_unknown():
    code_evidence = {"found": False}
    rca = {"root_cause": "Unknown", "recommended_resolution": "Investigate manually"}
    patch = generate_patch(code_evidence, rca)
    assert "could not confidently locate" in patch
    assert "No automated patch was generated" in patch
