"""
Seeds at least 10 historical, RESOLVED incidents (one per major failure
scenario, plus extras) and indexes each as RAG knowledge so new incidents
have real historical evidence to retrieve against from the very first run.

Usage:
    python -m scripts.seed_data
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.db.database import session_scope
from app.db.init_db import init_db
from app.db.models import Incident, IncidentAnalysis, Ownership, Remediation, new_incident_code
from app.rag.indexer import index_resolved_incident

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("erca_ris.seed")

HISTORICAL_INCIDENTS = [
    dict(service="Payment Service", scenario="payment",
         error_message="Payment gateway connection timed out",
         root_cause="Downstream payment gateway introduced excessive latency, exceeding the configured client timeout.",
         resolution="Corrected gateway timeout configuration and added retry with exponential backoff.",
         prevention="Add dependency latency monitoring and timeout alerting for the payment gateway.",
         file_path="sample_app/services/payment/payment_service.py", function_name="process_payment",
         owner="Payment Team", team="@payment-team", developer="Payment Service Developer"),
    dict(service="Authentication Service", scenario="auth",
         error_message="Authentication token validation failed",
         root_cause="Expired signing key was not rotated before the previous key's TTL elapsed.",
         resolution="Rotated signing keys and added automated key-expiry alerts.",
         prevention="Add pre-expiry key rotation automation and validation tests.",
         file_path="sample_app/services/auth/auth_service.py", function_name="login_user",
         owner="Auth Team", team="@auth-team", developer="Auth Service Developer"),
    dict(service="Orders Service", scenario="orders",
         error_message="Database connection pool exhausted",
         root_cause="A long-running query held connections open, exhausting the pool under load.",
         resolution="Added query timeout limits and increased pool size with monitoring.",
         prevention="Add connection pool utilization alerts and slow-query detection.",
         file_path="sample_app/services/orders/order_service.py", function_name="create_order",
         owner="Orders Team", team="@orders-team", developer="Orders Service Developer"),
    dict(service="Inventory Service", scenario="inventory",
         error_message="Inventory service unavailable",
         root_cause="Inventory dependency was deployed without a health check, causing traffic to route to an unready instance.",
         resolution="Restored the inventory dependency and added readiness probes.",
         prevention="Add automated dependency health checks and deployment gating.",
         file_path="sample_app/services/inventory/inventory_service.py", function_name="check_inventory",
         owner="Inventory Team", team="@inventory-team", developer="Inventory Service Developer"),
    dict(service="Notification Service", scenario="notification",
         error_message="Email provider unavailable",
         root_cause="Upstream email provider experienced an outage, and no fallback provider was configured.",
         resolution="Configured a secondary email provider with automatic failover.",
         prevention="Add multi-provider failover and provider-status monitoring.",
         file_path="sample_app/services/notification/email_service.py", function_name="send_email",
         owner="Notification Team", team="@notification-team", developer="Notification Service Developer"),
    dict(service="Search Service", scenario="search",
         error_message="Search service timeout",
         root_cause="Search index query exceeded the configured timeout under high cardinality filters.",
         resolution="Optimized the query plan and increased the timeout with circuit breaking.",
         prevention="Add query performance monitoring and index optimization reviews.",
         file_path="sample_app/services/search/search_service.py", function_name="search_products",
         owner="Search Team", team="@search-team", developer="Search Service Developer"),
    dict(service="Storage Service", scenario="storage",
         error_message="File storage unavailable",
         root_cause="Storage backend credentials expired, rejecting all upload requests.",
         resolution="Rotated storage credentials and added credential-expiry alerting.",
         prevention="Add automated credential rotation and expiry monitoring.",
         file_path="sample_app/services/storage/storage_service.py", function_name="upload_file",
         owner="Storage Team", team="@storage-team", developer="Storage Service Developer"),
    dict(service="Reporting Service", scenario="reports",
         error_message="Report database query timeout",
         root_cause="An unindexed column caused a full table scan on the reporting database under load.",
         resolution="Added the missing index and query result caching.",
         prevention="Add query plan review to the reporting deployment pipeline.",
         file_path="sample_app/services/reports/reports_service.py", function_name="generate_report",
         owner="Reporting Team", team="@reporting-team", developer="Reporting Service Developer"),
    dict(service="Payment Service", scenario="payment",
         error_message="Payment gateway connection timed out during peak load",
         root_cause="Connection pool to the payment gateway was undersized for peak traffic, causing queued requests to time out.",
         resolution="Increased connection pool size and added load-based autoscaling.",
         prevention="Add peak-load capacity testing to the release process.",
         file_path="sample_app/services/payment/payment_service.py", function_name="process_payment",
         owner="Payment Team", team="@payment-team", developer="Payment Service Developer"),
    dict(service="Authentication Service", scenario="auth",
         error_message="Authentication token validation failed due to clock skew",
         root_cause="NTP drift on an auth node caused token issuance timestamps to fall outside the validation window.",
         resolution="Resynchronized NTP and added clock-skew monitoring.",
         prevention="Add automated NTP drift detection and alerting.",
         file_path="sample_app/services/auth/auth_service.py", function_name="login_user",
         owner="Auth Team", team="@auth-team", developer="Auth Service Developer"),
]


def run():
    init_db()
    with session_scope() as db:
        existing = db.query(Incident).count()
        if existing:
            logger.info("Database already has %s incidents; skipping seed to avoid duplicates.", existing)
            return

        base_time = datetime.now(timezone.utc) - timedelta(days=90)

        for i, item in enumerate(HISTORICAL_INCIDENTS):
            incident = Incident(
                incident_id=new_incident_code(),
                service=item["service"],
                scenario=item["scenario"],
                error_message=item["error_message"],
                environment="production",
                severity="HIGH",
                priority="P2",
                status="RESOLVED",
                created_at=base_time + timedelta(days=i),
                resolved_at=base_time + timedelta(days=i, hours=6),
            )
            db.add(incident)
            db.flush()

            analysis = IncidentAnalysis(
                incident_id=incident.incident_id,
                root_cause=item["root_cause"],
                confidence=0.9,
                agreement_ratio=1.0,
                recommended_resolution=item["resolution"],
                recommended_prevention=item["prevention"],
                analysis_status="HIGH",
            )
            db.add(analysis)

            ownership = Ownership(
                incident_id=incident.incident_id,
                owner=item["owner"], team=item["team"], developer=item["developer"],
                developer_username=item["team"].lstrip("@").replace("-team", "-dev"),
                developer_email=item["team"].lstrip("@").replace("-team", "-dev") + "@example.com",
                developer_active=True, resolution_source="seed_roster",
                exception_type={"payment": "TimeoutError", "auth": "ValueError", "orders": "ConnectionError", "inventory": "ConnectionError", "notification": "ConnectionError", "search": "TimeoutError", "storage": "ConnectionError", "reports": "TimeoutError"}.get(item["scenario"]),
                file_path=item["file_path"], function_name=item["function_name"], line_number=None,
            )
            db.add(ownership)

            remediation = Remediation(
                incident_id=incident.incident_id,
                branch_name=f"erca-ris/fix-{incident.incident_id.lower()}",
                patch="# historical remediation (seed data)",
                test_result="PASSED",
                github_pr_url=None,
                github_pr_number=None,
                status="MERGED",
            )
            db.add(remediation)
            db.flush()

            index_resolved_incident(db, incident, analysis, ownership, remediation)
            logger.info("Seeded historical incident %s (%s)", incident.incident_id, item["service"])

        db.commit()
        logger.info("Seeded %s historical incidents and indexed them into RAG.", len(HISTORICAL_INCIDENTS))


if __name__ == "__main__":
    run()
