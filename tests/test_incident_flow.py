from erca_ris.code_analysis import analyze_code
from erca_ris.evidence import find_owner
from erca_ris.incident_analysis import analyze_incident


def test_notification_code_is_found():
    result = analyze_code("Email provider unavailable")
    assert result["found"] is True
    assert result["file"] == "sample_app/services/notification/email_service.py"
    assert result["function"] == "send_email"


def test_notification_owner_is_found():
    result = find_owner("sample_app/services/notification/email_service.py")
    assert result["owner"] == "@notification-team"
    assert result["team"] == "Notification Engineering"


def test_full_analysis_contains_code_and_owner():
    result = analyze_incident(
        "Service: Notification Service\n"
        "Incident Scenario: notification\n"
        "Error:\nEmail provider unavailable"
    )
    assert result["code_intelligence"]["found"] is True
    assert result["ownership"]["owner"] == "@notification-team"
    assert result["root_cause"]["predicted_root_cause"]


def test_payment_code_is_found():
    result = analyze_code("Payment gateway connection timed out")
    assert result["found"] is True
    assert result["function"] == "process_payment"
