from erca_ris.code_analysis import analyze_code
from erca_ris.evidence import find_owner
from erca_ris.history import search_history


def _extract_error(query):
    marker = "Error:"
    if marker in query:
        return query.split(marker, 1)[1].strip()
    return query.strip()


def analyze_incident(query):
    error = _extract_error(query)
    code = analyze_code(error)
    ownership = find_owner(code.get("file")) if code.get("found") else {
        "owner": None, "team": None, "developer": None, "matched_rule": None
    }
    history = search_history(query)

    causes = {}
    for item in history:
        cause = item.get("root_cause")
        if cause:
            causes[cause] = causes.get(cause, 0) + 1

    predicted = max(causes, key=causes.get) if causes else "Insufficient historical evidence"
    total = sum(causes.values())
    agreement = round(causes[predicted] / total, 2) if total else 0

    if code.get("found") and "unavailable" in error.lower():
        resolution = "Restore the unavailable dependency/configuration, then rerun the affected operation."
        prevention = "Add automated dependency health checks, alerting, and regression validation."
    elif "timed out" in error.lower():
        resolution = "Validate the downstream dependency, correct timeout/configuration conditions, then replay the affected workload."
        prevention = "Add dependency latency monitoring, timeout alerts, and integration/recovery tests."
    else:
        resolution = "Inspect the identified source evidence, correct the failing condition, and validate service health."
        prevention = "Add regression coverage and monitoring for the failure condition."

    return {
        "query": query,
        "root_cause": {
            "predicted_root_cause": predicted,
            "candidate_root_causes": list(causes.keys()),
            "agreement_ratio": agreement,
            "status": "CONFIDENT" if agreement >= 0.5 else "REVIEW_REQUIRED",
        },
        "code_intelligence": code,
        "ownership": ownership,
        "historical_incidents": history,
        "recommended_resolution": resolution,
        "recommended_prevention": prevention,
    }
