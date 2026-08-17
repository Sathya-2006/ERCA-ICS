"""
GitHub integration abstraction.

Real mode (GITHUB_TOKEN + GITHUB_REPOSITORY configured): uses PyGithub to
  - create a branch
  - commit the patch file to that branch
  - open a pull request
  - add labels
  - assign the resolved owner/team
  - comment the RCA summary
  - link the incident ID

Mock mode (no credentials): every method returns a realistic, clearly
labeled MOCK response so the rest of the pipeline (and the frontend) can be
exercised end-to-end without a real GitHub account. This satisfies the
safety requirement that nothing is ever pushed to main/master automatically
-- both modes only ever operate on a dedicated feature branch + PR.
"""
from __future__ import annotations

import logging

from app.config import get_settings

logger = logging.getLogger("erca_ris.remediation.github_client")
settings = get_settings()


class GitHubClient:
    def __init__(self):
        self.enabled = bool(settings.GITHUB_TOKEN and settings.GITHUB_REPOSITORY)
        self._repo = None
        if self.enabled:
            try:
                from github import Github  # PyGithub
                gh = Github(settings.GITHUB_TOKEN)
                self._repo = gh.get_repo(settings.GITHUB_REPOSITORY)
            except Exception as exc:
                logger.warning("GitHub client init failed, falling back to mock mode: %s", exc)
                self.enabled = False

    # -- branch --------------------------------------------------------
    def create_branch(self, branch_name: str) -> dict:
        if not self.enabled:
            return {"mocked": True, "branch": branch_name}
        try:
            base = self._repo.get_branch(settings.GITHUB_BASE_BRANCH)
            self._repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base.commit.sha)
            return {"mocked": False, "branch": branch_name}
        except Exception as exc:
            logger.warning("create_branch failed: %s", exc)
            return {"mocked": True, "branch": branch_name, "error": str(exc)}

    # -- commit ----------------------------------------------------------
    def commit_patch(self, branch_name: str, path: str, content: str, message: str) -> dict:
        if not self.enabled:
            return {"mocked": True, "path": path}
        try:
            try:
                existing = self._repo.get_contents(path, ref=branch_name)
                self._repo.update_file(path, message, content, existing.sha, branch=branch_name)
            except Exception:
                self._repo.create_file(path, message, content, branch=branch_name)
            return {"mocked": False, "path": path}
        except Exception as exc:
            logger.warning("commit_patch failed: %s", exc)
            return {"mocked": True, "path": path, "error": str(exc)}

    # -- PR ----------------------------------------------------------
    def create_pull_request(self, branch_name: str, title: str, body: str) -> dict:
        if not self.enabled:
            return {
                "mocked": True,
                "url": f"https://github.com/{settings.GITHUB_REPOSITORY or 'mock/repo'}/pull/0",
                "number": 0,
                "title": title,
            }
        try:
            pr = self._repo.create_pull(
                title=title, body=body, head=branch_name, base=settings.GITHUB_BASE_BRANCH
            )
            return {"mocked": False, "url": pr.html_url, "number": pr.number, "title": title}
        except Exception as exc:
            logger.warning("create_pull_request failed: %s", exc)
            return {
                "mocked": True,
                "url": f"https://github.com/{settings.GITHUB_REPOSITORY or 'mock/repo'}/pull/0",
                "number": 0,
                "title": title,
                "error": str(exc),
            }

    def add_labels(self, pr_number: int, labels: list[str]) -> dict:
        if not self.enabled or pr_number == 0:
            return {"mocked": True, "labels": labels}
        try:
            pr = self._repo.get_pull(pr_number)
            pr.add_to_labels(*labels)
            return {"mocked": False, "labels": labels}
        except Exception as exc:
            logger.warning("add_labels failed: %s", exc)
            return {"mocked": True, "labels": labels, "error": str(exc)}

    def assign(self, pr_number: int, assignees: list[str]) -> dict:
        if not self.enabled or pr_number == 0:
            return {"mocked": True, "assignees": assignees}
        try:
            pr = self._repo.get_pull(pr_number)
            valid = [a for a in assignees if a]
            if valid:
                pr.add_to_assignees(*valid)
            return {"mocked": False, "assignees": assignees}
        except Exception as exc:
            logger.warning("assign failed: %s", exc)
            return {"mocked": True, "assignees": assignees, "error": str(exc)}

    def comment(self, pr_number: int, body: str) -> dict:
        if not self.enabled or pr_number == 0:
            return {"mocked": True, "comment": body}
        try:
            pr = self._repo.get_pull(pr_number)
            pr.create_issue_comment(body)
            return {"mocked": False}
        except Exception as exc:
            logger.warning("comment failed: %s", exc)
            return {"mocked": True, "error": str(exc)}


def get_github_client() -> GitHubClient:
    return GitHubClient()
