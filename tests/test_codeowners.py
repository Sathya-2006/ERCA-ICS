import json

import app.code_intelligence.codeowners as codeowners
from app.code_intelligence.codeowners import find_owner


def test_payment_owner_resolves_multiple_developers():
    result = find_owner("sample_app/services/payment/payment_service.py")
    assert result["team"] == "@payment-team"
    assert result["developer"] == "Payment Service Developer"
    assert result["username"] == "payment-dev"
    assert result["email"] == "payment-dev@example.com"
    assert result["active"] is True
    assert "payment-dev" in result["candidates"]
    assert "payment-backup" in result["candidates"]


def test_inactive_developer_is_not_selected(monkeypatch):
    original = codeowners._json_env

    def fake_json_env(name):
        if name == "TEAM_DEVELOPERS_JSON":
            return {
                "@payment-team": {
                    "team": "Payment Engineering",
                    "developers": [
                        {"username": "former-dev", "display_name": "Former Developer", "email": "former@example.com", "active": False},
                        {"username": "current-dev", "display_name": "Current Developer", "email": "current@example.com", "active": True},
                    ],
                }
            }
        return original(name)

    monkeypatch.setattr(codeowners, "_json_env", fake_json_env)
    monkeypatch.setattr(codeowners, "_github_recent_author", lambda _: None)
    result = find_owner("sample_app/services/payment/payment_service.py")
    assert result["username"] == "current-dev"
    assert result["email"] == "current@example.com"
    assert result["active"] is True


def test_recent_github_contributor_wins_when_member_of_team(monkeypatch):
    original = codeowners._json_env

    def fake_json_env(name):
        if name == "TEAM_DEVELOPERS_JSON":
            return {
                "@payment-team": {
                    "team": "Payment Engineering",
                    "developers": [
                        {"username": "payment-dev", "display_name": "Payment Developer", "email": "payment@example.com", "active": True, "priority": 20},
                        {"username": "payment-backup", "display_name": "Payment Backup", "email": "backup@example.com", "active": True, "priority": 10},
                    ],
                }
            }
        return original(name)

    monkeypatch.setattr(codeowners, "_json_env", fake_json_env)
    monkeypatch.setattr(codeowners, "_github_recent_author", lambda _: {"username": "payment-dev", "email": "payment@example.com", "active": True, "source": "github_recent_contributor"})
    result = find_owner("sample_app/services/payment/payment_service.py")
    assert result["username"] == "payment-dev"
    assert result["resolution_source"] == "github_recent_contributor_team_match"


def test_recent_non_member_does_not_receive_team_alert(monkeypatch):
    original = codeowners._json_env

    def fake_json_env(name):
        if name == "TEAM_DEVELOPERS_JSON":
            return {
                "@payment-team": {
                    "team": "Payment Engineering",
                    "developers": [
                        {"username": "payment-dev", "display_name": "Payment Developer", "email": "payment@example.com", "active": True, "priority": 10},
                    ],
                }
            }
        return original(name)

    monkeypatch.setattr(codeowners, "_json_env", fake_json_env)
    monkeypatch.setattr(codeowners, "_github_recent_author", lambda _: {"username": "unrelated-user", "email": "unrelated@example.com", "active": True, "source": "github_recent_contributor"})
    result = find_owner("sample_app/services/payment/payment_service.py")
    assert result["username"] == "payment-dev"


def test_most_specific_rule_wins_over_catch_all():
    result = find_owner("sample_app/services/auth/auth_service.py")
    assert result["team"] == "@auth-team"


def test_unmapped_path_returns_none():
    result = find_owner("some/unrelated/path.py")
    assert result["team"] is None
