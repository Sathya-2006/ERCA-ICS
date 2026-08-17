from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache

from app.config import get_settings

logger = logging.getLogger("erca_ris.code_intelligence.codeowners")
settings = get_settings()

# Local/demo fallback. Production deployments should resolve the same team
# through the configured SCM provider. Each team may contain multiple active
# developers; the resolver chooses the best current developer for the file.
TEAM_DEVELOPERS = {
    "@payment-team": {
        "team": "Payment Engineering",
        "developers": [{"display_name": "Payment Service Developer", "username": "payment-dev", "email": "payment-dev@example.com", "active": True}],
    },
    "@auth-team": {
        "team": "Authentication Engineering",
        "developers": [{"display_name": "Auth Service Developer", "username": "auth-dev", "email": "auth-dev@example.com", "active": True}],
    },
    "@orders-team": {
        "team": "Orders Engineering",
        "developers": [{"display_name": "Orders Service Developer", "username": "orders-dev", "email": "orders-dev@example.com", "active": True}],
    },
    "@inventory-team": {
        "team": "Inventory Engineering",
        "developers": [{"display_name": "Inventory Service Developer", "username": "inventory-dev", "email": "inventory-dev@example.com", "active": True}],
    },
    "@notification-team": {
        "team": "Notification Engineering",
        "developers": [{"display_name": "Notification Service Developer", "username": "notification-dev", "email": "notification-dev@example.com", "active": True}],
    },
    "@search-team": {
        "team": "Search Engineering",
        "developers": [{"display_name": "Search Service Developer", "username": "search-dev", "email": "search-dev@example.com", "active": True}],
    },
    "@storage-team": {
        "team": "Storage Engineering",
        "developers": [{"display_name": "Storage Service Developer", "username": "storage-dev", "email": "storage-dev@example.com", "active": True}],
    },
    "@reporting-team": {
        "team": "Reporting Engineering",
        "developers": [{"display_name": "Reporting Service Developer", "username": "reporting-dev", "email": "reporting-dev@example.com", "active": True}],
    },
    "@demo-platform-team": {
        "team": "Demo Platform Engineering",
        "developers": [{"display_name": "Platform Developer", "username": "platform-dev", "email": "platform-dev@example.com", "active": True}],
    },
}


@dataclass
class OwnerRule:
    pattern: str
    owners: list[str]


def _json_env(name: str) -> dict:
    raw = getattr(settings, name, "{}") or "{}"
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        logger.warning("Invalid JSON in %s; using empty mapping", name)
        return {}


@lru_cache
def _load_rules() -> list[OwnerRule]:
    rules: list[OwnerRule] = []
    path = settings.CODEOWNERS_PATH
    if not path.exists():
        logger.warning("CODEOWNERS file not found at %s", path)
        return rules

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        rules.append(OwnerRule(pattern=parts[0], owners=parts[1:]))

    rules.sort(key=lambda r: len(r.pattern), reverse=True)
    return rules


def _github_recent_author(file_path: str | None) -> dict | None:
    """Return the latest GitHub contributor for a path when GitHub is configured."""
    token = getattr(settings, "GITHUB_TOKEN", None)
    repo_name = getattr(settings, "GITHUB_REPOSITORY", None)
    if not token or not repo_name or not file_path:
        return None
    try:
        from github import Github
        gh = Github(token)
        repo = gh.get_repo(repo_name)
        commits = repo.get_commits(path=file_path)
        commit = next(iter(commits), None)
        if not commit or not commit.author:
            return None
        login = getattr(commit.author, "login", None)
        email = getattr(commit.commit.author, "email", None)
        if not login:
            return None
        return {"username": login, "email": email, "source": "github_recent_contributor", "active": True}
    except Exception as exc:
        logger.debug("GitHub contributor lookup unavailable: %s", exc)
        return None


def _normalise_developers(configured, owner: str, email_map: dict) -> list[dict]:
    """Accept both the legacy single-developer format and the new list format."""
    if configured is None:
        configured = TEAM_DEVELOPERS.get(owner)

    if isinstance(configured, str):
        configured = {"display_name": configured}

    if not isinstance(configured, dict):
        return []

    raw_developers = configured.get("developers")
    if raw_developers is None:
        raw_developers = [configured]

    if isinstance(raw_developers, dict):
        raw_developers = [raw_developers]

    result = []
    for item in raw_developers or []:
        if not isinstance(item, dict):
            continue
        username = item.get("username") or item.get("login")
        result.append({
            "display_name": item.get("display_name") or item.get("developer") or username,
            "username": username,
            "email": item.get("email") or (email_map.get(username) if username else None),
            "active": bool(item.get("active", True)),
            "priority": item.get("priority", 100),
        })
    return result


def _identity_for_owner(owner: str, file_path: str | None) -> dict:
    team_map = _json_env("TEAM_DEVELOPERS_JSON")
    email_map = _json_env("DEVELOPER_EMAILS_JSON")
    roster_path = settings.PROJECT_ROOT / "repositories" / "repo" / "developer_roster.json"
    if not team_map and roster_path.exists():
        try:
            data = json.loads(roster_path.read_text(encoding="utf-8"))
            team_map = data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            team_map = {}

    # A direct CODEOWNER username is already an exact identity.
    if owner.startswith("@") and owner not in TEAM_DEVELOPERS and owner not in team_map:
        username = owner[1:]
        return {
            "developer": username,
            "username": username,
            "email": email_map.get(username),
            "active": True,
            "source": "codeowners_user",
            "candidates": [username],
        }

    configured = team_map.get(owner)
    developers = _normalise_developers(configured, owner, email_map)
    active = [d for d in developers if d.get("active", True)]

    if not active:
        recent = _github_recent_author(file_path)
        if recent:
            return {
                "developer": recent["username"],
                "username": recent["username"],
                "email": recent.get("email") or email_map.get(recent["username"]),
                "active": True,
                "source": "github_recent_contributor_after_inactive_team",
                "candidates": [],
            }
        return {
            "developer": TEAM_DEVELOPERS.get(owner, {}).get("team", "Owning Team") if isinstance(TEAM_DEVELOPERS.get(owner), dict) else "Owning Team",
            "username": None,
            "email": None,
            "active": False,
            "source": "inactive_team_fallback",
            "candidates": [],
        }

    # Primary automatic selection: latest GitHub contributor, but only when
    # that contributor is an active member of the CODEOWNERS team. This prevents
    # an unrelated contributor from receiving an incident alert.
    recent = _github_recent_author(file_path)
    if recent:
        recent_username = recent.get("username")
        for developer in active:
            if developer.get("username", "").lower() == str(recent_username).lower():
                return {
                    "developer": developer.get("display_name") or recent_username,
                    "username": developer.get("username") or recent_username,
                    "email": developer.get("email") or recent.get("email") or email_map.get(recent_username),
                    "active": True,
                    "source": "github_recent_contributor_team_match",
                    "candidates": [d.get("username") for d in active if d.get("username")],
                }

    # Offline/demo fallback: deterministic priority among active developers.
    # Lower priority wins; list order breaks ties. This makes selection stable
    # without randomly assigning incidents to a team member.
    selected = sorted(enumerate(active), key=lambda pair: (pair[1].get("priority", 100), pair[0]))[0][1]
    return {
        "developer": selected.get("display_name") or selected.get("username") or "Unassigned Developer",
        "username": selected.get("username"),
        "email": selected.get("email") or (email_map.get(selected.get("username")) if selected.get("username") else None),
        "active": True,
        "source": "active_team_priority_fallback",
        "candidates": [d.get("username") for d in active if d.get("username")],
    }


def find_owner(file_path: str | None) -> dict:
    if not file_path:
        return {"owner": None, "team": None, "developer": None, "username": None, "email": None,
                "active": False, "resolution_source": None, "matched_rule": None, "candidates": []}

    normalized = "/" + file_path.lstrip("/")
    for rule in _load_rules():
        pattern = rule.pattern
        if pattern.endswith("/"):
            matches = normalized.startswith(pattern) or (normalized + "/").startswith(pattern)
        else:
            matches = normalized == pattern or normalized.startswith(pattern)
        if matches:
            owner = rule.owners[0]
            identity = _identity_for_owner(owner, file_path)
            configured = _json_env("TEAM_DEVELOPERS_JSON").get(owner)
            team_name = configured.get("team") if isinstance(configured, dict) else None
            if not team_name and owner in TEAM_DEVELOPERS and isinstance(TEAM_DEVELOPERS[owner], dict):
                team_name = TEAM_DEVELOPERS[owner].get("team")
            return {
                "owner": team_name or owner.lstrip("@").replace("-", " ").title(),
                "team": owner if owner.startswith("@") else None,
                "developer": identity["developer"],
                "username": identity.get("username"),
                "email": identity.get("email"),
                "active": identity.get("active", True),
                "resolution_source": identity.get("source"),
                "matched_rule": pattern,
                "candidates": identity.get("candidates", []),
            }

    return {"owner": None, "team": None, "developer": None, "username": None, "email": None,
            "active": False, "resolution_source": None, "matched_rule": None, "candidates": []}
