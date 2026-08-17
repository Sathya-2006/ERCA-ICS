from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CODEOWNERS_PATH = PROJECT_ROOT / "repositories" / "repo" / "CODEOWNERS"

TEAM_DIRECTORY = {
    "@payment-team": {"team": "Payment Engineering", "developer": "Payment Service Developer"},
    "@auth-team": {"team": "Authentication Engineering", "developer": "Authentication Service Developer"},
    "@orders-team": {"team": "Orders Engineering", "developer": "Orders Service Developer"},
    "@inventory-team": {"team": "Inventory Engineering", "developer": "Inventory Service Developer"},
    "@notification-team": {"team": "Notification Engineering", "developer": "Notification Service Developer"},
    "@search-team": {"team": "Search Engineering", "developer": "Search Service Developer"},
    "@storage-team": {"team": "Storage Engineering", "developer": "Storage Service Developer"},
    "@reporting-team": {"team": "Reporting Engineering", "developer": "Reporting Service Developer"},
    "@demo-platform-team": {"team": "Demo Platform Engineering", "developer": "Platform Developer"},
}


def load_codeowners():
    rules = []
    if not CODEOWNERS_PATH.exists():
        return rules
    for raw in CODEOWNERS_PATH.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            rules.append({"pattern": parts[0], "owner": parts[-1]})
    return rules


def find_owner(file_path):
    if not file_path:
        return {"owner": None, "team": None, "developer": None, "matched_rule": None}

    normalized = "/" + file_path.replace("\\", "/").lstrip("/")
    best = None

    for rule in load_codeowners():
        pattern = rule["pattern"].rstrip("/")
        if normalized.startswith(pattern):
            if best is None or len(pattern) > len(best["pattern"]):
                best = rule

    if not best:
        return {"owner": None, "team": None, "developer": None, "matched_rule": None}

    owner = best["owner"]
    directory = TEAM_DIRECTORY.get(owner, {"team": owner, "developer": owner})
    return {
        "owner": owner,
        "team": directory["team"],
        "developer": directory["developer"],
        "matched_rule": best["pattern"],
    }
