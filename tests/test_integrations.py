from unittest.mock import patch
import pytest

from app.remediation.github_client import GitHubClient
from app.notifications.email_service import send_email
from app.notifications.slack_service import send_slack


def test_github_client_runs_in_mock_mode_without_credentials():
    client = GitHubClient()
    assert client.enabled is False

    branch = client.create_branch("erca-ris/fix-inc-test")
    assert branch["mocked"] is True

    pr = client.create_pull_request("erca-ris/fix-inc-test", "Fix", "body")
    assert pr["mocked"] is True
    assert pr["url"].startswith("https://github.com/")


def test_github_client_uses_pygithub_when_credentials_present():
    pytest.importorskip("github")
    with patch("app.remediation.github_client.settings") as mock_settings:
        mock_settings.GITHUB_TOKEN = "fake-token"
        mock_settings.GITHUB_REPOSITORY = "org/repo"
        with patch("github.Github") as MockGithub:
            mock_repo = MockGithub.return_value.get_repo.return_value
            client = GitHubClient()
            assert client.enabled is True
            mock_repo.get_branch.return_value.commit.sha = "abc123"
            client.create_branch("erca-ris/fix-inc-test")
            mock_repo.create_git_ref.assert_called_once()


def test_email_notification_mocked_without_smtp_config():
    result = send_email("dev@example.com", "Test Subject", "Test body")
    assert result["status"] == "MOCKED"
    assert result["channel"] == "email"


def test_slack_notification_mocked_without_webhook():
    result = send_slack("Test message")
    assert result["status"] == "MOCKED"
    assert result["channel"] == "slack"


def test_slack_notification_sends_when_webhook_configured():
    with patch("app.notifications.slack_service.settings") as mock_settings, \
         patch("app.notifications.slack_service.requests.post") as mock_post:
        mock_settings.SLACK_WEBHOOK_URL = "https://hooks.slack.test/xyz"
        mock_post.return_value.raise_for_status.return_value = None
        result = send_slack("Hello")
        assert result["status"] == "SENT"
        mock_post.assert_called_once()
