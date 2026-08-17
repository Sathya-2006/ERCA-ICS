from flask import Flask, jsonify, render_template
import requests

from sample_app.services.payment.payment_service import process_payment
from sample_app.services.auth.auth_service import login_user
from sample_app.services.orders.order_service import create_order
from sample_app.services.inventory.inventory_service import check_inventory
from sample_app.services.notification.email_service import send_email
from sample_app.services.search.search_service import search_products
from sample_app.services.storage.storage_service import upload_file
from sample_app.services.reports.reports_service import generate_report

app = Flask(__name__)
ERCA_URL = "http://127.0.0.1:5001/api/incidents"


SCENARIOS = {
    "payment": ("Payment Service", "Payment Gateway Timeout"),
    "auth": ("Authentication Service", "Authentication Failure"),
    "orders": ("Orders Service", "Database Connection Failure"),
    "inventory": ("Inventory Service", "Inventory Service Failure"),
    "notification": ("Notification Service", "Notification Provider Failure"),
    "search": ("Search Service", "Search Service Timeout"),
    "storage": ("Storage Service", "File Storage Failure"),
    "reports": ("Reporting Service", "Report Query Timeout"),
}


def notify_erca(scenario, service, error):
    """
    Reports the captured failure to the ERCA&RIS backend, which creates the
    incident and immediately runs the full RCA pipeline (RAG retrieval,
    code intelligence, CODEOWNERS resolution, confidence scoring). The demo
    UI renders whatever comes back -- nothing here is hardcoded.
    """
    try:
        response = requests.post(
            ERCA_URL,
            json={
                "scenario": scenario,
                "service": service,
                "error_message": error,
                "environment": "demo",
                "severity": "HIGH",
                "priority": "P2",
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {
            "status": "ERROR",
            "message": "Application error was captured, but ERCA&RIS notification failed. "
                       "Is the backend running on http://127.0.0.1:5001 ?",
            "error": str(exc),
        }


@app.get("/")
def home():
    return render_template("index.html")


@app.post("/api/demo/<scenario>")
def demo_failure(scenario):
    if scenario not in SCENARIOS:
        return jsonify({"status": "ERROR", "error": "Unknown scenario"}), 404

    service, _ = SCENARIOS[scenario]
    try:
        if scenario == "payment":
            result = process_payment(100)
        elif scenario == "auth":
            result = login_user("demo@example.com", "wrong-password")
        elif scenario == "orders":
            result = create_order(101, 5001)
        elif scenario == "inventory":
            result = check_inventory(5001)
        elif scenario == "notification":
            result = send_email("demo@example.com", "Order confirmation")
        elif scenario == "search":
            result = search_products("laptop")
        elif scenario == "storage":
            result = upload_file("demo-receipt.pdf")
        else:
            result = generate_report("sales")

        return jsonify(result)
    except Exception as exc:
        error = str(exc)
        erca = notify_erca(scenario, service, error)
        return jsonify({
            "status": "FAILED",
            "scenario": scenario,
            "service": service,
            "error_type": type(exc).__name__,
            "error": error,
            "erca": erca,
        }), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
