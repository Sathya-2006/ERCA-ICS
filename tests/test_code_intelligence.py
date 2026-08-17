from app.code_intelligence.scanner import analyze_code


def test_payment_timeout_is_located():
    result = analyze_code("Payment gateway connection timed out", service="payment")
    assert result["found"] is True
    assert "payment_service.py" in result["file"]
    assert result["function"] == "process_payment"


def test_notification_failure_is_located():
    result = analyze_code("Email provider unavailable", service="notification")
    assert result["found"] is True
    assert "email_service.py" in result["file"]


def test_unknown_error_is_not_found_with_high_confidence():
    result = analyze_code("Completely unrelated nonsense error xyzzy", service="payment")
    # Either not found, or found with a low match score -- never a fabricated high-confidence match.
    if result["found"]:
        assert result["match_score"] < 2.0
