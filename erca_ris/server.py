from flask import Flask, jsonify, request
from flask_cors import CORS

from erca_ris.incident_analysis import analyze_incident
from erca_ris.remediation import apply_safe_fix, get_fix
from erca_ris.store import create_incident, get_incident, list_incidents, mark_read, update_incident

app = Flask(__name__, template_folder="templates")
CORS(app, resources={r"/api/*": {"origins": "*"}})


@app.get("/")
def dashboard():
    from flask import render_template
    return render_template("dashboard.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "OK", "service": "ERCA & RIS"})


@app.get("/api/incidents")
def incidents():
    return jsonify({"status": "SUCCESS", "incidents": list_incidents()})


@app.get("/api/incidents/<incident_id>")
def incident(incident_id):
    item = get_incident(incident_id)
    if not item:
        return jsonify({"status": "ERROR", "message": "Incident not found"}), 404
    return jsonify({"status": "SUCCESS", "incident": item})


@app.post("/api/incidents/<incident_id>/read")
def read_incident(incident_id):
    item = mark_read(incident_id)
    if not item:
        return jsonify({"status": "ERROR", "message": "Incident not found"}), 404
    return jsonify({"status": "SUCCESS", "incident": item})


@app.post("/api/analyze")
def analyze():
    data = request.get_json(silent=True) or {}
    error = (data.get("error") or "").strip()
    scenario = data.get("scenario") or "unknown"
    service = data.get("service") or "Unknown Service"

    if not error:
        return jsonify({"status": "ERROR", "message": "error is required"}), 400

    query = f"Service: {service}\nIncident Scenario: {scenario}\nError:\n{error}"

    try:
        analysis = analyze_incident(query)
        incident = create_incident({
            "scenario": scenario,
            "service": service,
            "error": error,
            "analysis": analysis,
            "developer": analysis["ownership"].get("developer"),
            "team": analysis["ownership"].get("team"),
            "owner": analysis["ownership"].get("owner"),
        })
        return jsonify({
            "status": "SUCCESS",
            "incident": incident,
            "analysis": analysis,
            "notification": {
                "status": "CREATED",
                "developer": analysis["ownership"].get("developer"),
                "team": analysis["ownership"].get("team"),
            },
        })
    except Exception as exc:
        return jsonify({
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
        }), 500


@app.post("/api/incidents/<incident_id>/remediate")
def remediate(incident_id):
    item = get_incident(incident_id)
    if not item:
        return jsonify({"status": "ERROR", "message": "Incident not found"}), 404

    error = item["error"]
    fix = get_fix(error)
    if not fix:
        return jsonify({
            "status": "REVIEW_REQUIRED",
            "message": "No deterministic safe fix is available. Create a normal developer PR instead.",
        }), 409

    update_incident(incident_id, status="REMEDIATING", remediation=fix)

    result = apply_safe_fix(error)

    if result.get("ok"):
        updated = update_incident(
            incident_id,
            status="RESOLVED",
            notification_status="READ",
            remediation_result=result,
        )
    else:
        updated = update_incident(
            incident_id,
            status="OPEN",
            remediation_result=result,
        )

    return jsonify({"status": "SUCCESS" if result.get("ok") else "FAILED", "incident": updated})


app.run(host="127.0.0.1", port=5001, debug=True)
