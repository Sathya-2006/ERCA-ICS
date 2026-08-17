def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_incident_runs_full_analysis(client):
    r = client.post("/api/incidents", json={
        "service": "Payment Service",
        "scenario": "payment",
        "error_message": "Payment gateway connection timed out",
        "environment": "demo",
        "severity": "HIGH",
        "priority": "P2",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["incident_id"].startswith("INC-")
    assert data["status"] in ("ASSIGNED", "RCA_READY")
    assert data["analysis"]["root_cause"]
    assert data["ownership"]["team"] == "@payment-team"


def test_new_incident_does_not_need_to_preexist(client):
    """A brand-new, never-seen-before error still gets a full incident record."""
    r = client.post("/api/incidents", json={
        "service": "Search Service",
        "error_message": "A completely novel search failure never seen before",
    })
    assert r.status_code == 200
    assert r.json()["incident_id"]


def test_get_list_and_single_incident(client):
    r = client.post("/api/incidents", json={"service": "Auth Service", "error_message": "Authentication token validation failed"})
    incident_id = r.json()["incident_id"]

    r2 = client.get("/api/incidents")
    assert r2.status_code == 200
    assert any(i["incident_id"] == incident_id for i in r2.json())

    r3 = client.get(f"/api/incidents/{incident_id}")
    assert r3.status_code == 200
    assert r3.json()["incident_id"] == incident_id


def test_get_unknown_incident_returns_404(client):
    r = client.get("/api/incidents/INC-DOES-NOT-EXIST")
    assert r.status_code == 404


def test_full_lifecycle_to_resolution(client):
    r = client.post("/api/incidents", json={
        "service": "Storage Service", "error_message": "File storage unavailable",
    })
    incident_id = r.json()["incident_id"]

    r = client.post(f"/api/incidents/{incident_id}/remediation")
    assert r.status_code == 200
    assert r.json()["status"] == "PATCH_GENERATED"

    r = client.post(f"/api/incidents/{incident_id}/tests")
    assert r.status_code == 200
    assert "passed" in r.json()

    r = client.post(f"/api/incidents/{incident_id}/github-pr")
    assert r.status_code == 200
    assert r.json()["url"]

    r = client.post(f"/api/incidents/{incident_id}/notify", json={"channels": ["email", "slack"]})
    assert r.status_code == 200

    r = client.post(f"/api/incidents/{incident_id}/resolve")
    assert r.status_code == 200
    assert r.json()["status"] == "RESOLVED"

    timeline = client.get(f"/api/incidents/{incident_id}/timeline").json()
    statuses = [t["to_status"] for t in timeline]
    assert "OPEN" in statuses
    assert "RESOLVED" in statuses


def test_resolved_incident_becomes_rag_knowledge(client):
    r = client.post("/api/incidents", json={
        "service": "Reporting Service", "error_message": "Report database query timeout",
    })
    incident_id = r.json()["incident_id"]
    client.post(f"/api/incidents/{incident_id}/resolve")

    search = client.post("/api/rag/search", json={"query": "Report database query timeout", "top_k": 5})
    assert search.status_code == 200
    results = search.json()["results"]
    assert any(res["incident_id"] == incident_id for res in results)


def test_rag_index_endpoint(client):
    r = client.post("/api/rag/index", json={"document": "Manual knowledge doc", "metadata": {"root_cause": "manual"}})
    assert r.status_code == 200
    assert r.json()["id"]


def test_dashboard_and_operational_endpoints(client):
    assert client.get("/").status_code == 200
    assert client.get("/api/analytics/summary").status_code == 200
    assert client.get("/api/analytics/timeseries").status_code == 200
    assert client.get("/api/ownership").status_code == 200
    assert client.get("/api/remediation").status_code == 200
    assert client.get("/api/pull-requests").status_code == 200
    assert client.get("/api/notifications").status_code == 200
    assert client.get("/api/reports/incidents.csv").status_code == 200


def test_owner_identity_contains_username_and_email(client):
    r = client.post("/api/incidents", json={
        "service": "Payment Service",
        "error_message": "Payment gateway connection timed out",
    })
    assert r.status_code == 200
    owner = r.json()["ownership"]
    assert owner["developer_username"] == "payment-dev"
    assert owner["developer_email"] == "payment-dev@example.com"
    assert owner["developer_active"] is True


def test_code_context_endpoint(client):
    r = client.post("/api/incidents", json={
        "service": "Payment Service",
        "error_message": "Payment gateway connection timed out",
    })
    incident_id = r.json()["incident_id"]
    code = client.get(f"/api/incidents/{incident_id}/code")
    assert code.status_code == 200
    assert code.json()["found"] is True
    assert code.json()["function"] == "process_payment"
