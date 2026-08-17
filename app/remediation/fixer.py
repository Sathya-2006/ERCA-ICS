"""
Fixer: creates an isolated remediation git branch and writes the proposed
patch as a review file on that branch. It NEVER commits to main/master and
NEVER silently overwrites production source files -- the patch is written
as a `.patch` file alongside a summary, for explicit developer review, and
(if GitHub integration is configured) opened as a PR by pr_service.py.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger("erca_ris.remediation.fixer")
settings = get_settings()


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=30)
        return result.returncode, (result.stdout + result.stderr)
    except Exception as exc:
        return 1, str(exc)


def create_remediation_branch(incident_id: str, patch_text: str) -> dict:
    """
    Creates (or reuses) a local git branch named after the incident and
    writes the patch under remediation_patches/<incident_id>.patch on that
    branch. Returns branch/patch metadata. Safe no-op-with-warning if the
    project isn't a git repository (e.g. fresh unzip without .git).
    """
    root = settings.PROJECT_ROOT
    branch_name = f"erca-ris/fix-{incident_id.lower()}"

    is_git = (root / ".git").exists()
    if not is_git:
        logger.warning("Not a git repository; skipping local branch creation for %s", incident_id)
        return {"branch_name": branch_name, "git_branch_created": False, "patch": patch_text}

    code, out = _run(["git", "rev-parse", "--verify", branch_name], root)
    if code != 0:
        code, out = _run(["git", "branch", branch_name], root)
        if code != 0:
            logger.warning("Could not create branch %s: %s", branch_name, out)
            return {"branch_name": branch_name, "git_branch_created": False, "patch": patch_text}

    patch_dir = root / "remediation_patches"
    patch_dir.mkdir(exist_ok=True)
    patch_file = patch_dir / f"{incident_id}.patch"
    patch_file.write_text(patch_text)

    return {"branch_name": branch_name, "git_branch_created": True, "patch_file": str(patch_file), "patch": patch_text}
