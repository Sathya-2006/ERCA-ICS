"""
Generates a proposed, human-reviewable patch for the identified failure
location. This NEVER touches the working tree directly -- it only produces
patch text (unified diff style) that the branch/PR pipeline can apply on an
isolated git branch. Nothing is ever applied to main/master (see pr_service.py).
"""
from __future__ import annotations

from pathlib import Path

from app.config import get_settings

settings = get_settings()

REMEDIATION_TEMPLATES = {
    "TimeoutError": (
        "# ERCA&RIS auto-remediation: increase timeout tolerance and add retry/backoff\n"
        "# around the failing call at line {line} in {function}.\n"
    ),
    "ConnectionError": (
        "# ERCA&RIS auto-remediation: add dependency availability check and\n"
        "# graceful degradation around the failing call at line {line} in {function}.\n"
    ),
    "PermissionError": (
        "# ERCA&RIS auto-remediation: validate credentials/permissions before\n"
        "# the failing call at line {line} in {function}.\n"
    ),
}

DEFAULT_TEMPLATE = (
    "# ERCA&RIS auto-remediation: add defensive handling around the failing\n"
    "# condition at line {line} in {function}.\n"
)


def generate_patch(code_evidence: dict, rca: dict) -> str:
    """
    Returns a unified-diff-style patch (as text) proposing a fix.
    If the exact source location isn't known, returns a documented
    placeholder patch the developer can act on manually -- never a
    fabricated/silent modification.
    """
    file_path = code_evidence.get("file")
    line = code_evidence.get("line")
    function = code_evidence.get("function") or "unknown_function"
    exc_type = code_evidence.get("exception_type")

    if not file_path or not line:
        return (
            "# ERCA&RIS could not confidently locate the exact source line.\n"
            f"# Recommended resolution: {rca.get('recommended_resolution', '')}\n"
            "# No automated patch was generated. Manual investigation required.\n"
        )

    template = REMEDIATION_TEMPLATES.get(exc_type, DEFAULT_TEMPLATE)
    header = template.format(line=line, function=function)

    diff = (
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -{line},1 +{line},{2 + header.count(chr(10))} @@\n"
        + "".join(f"+{l}\n" for l in header.splitlines())
        + f"     # NOTE: review and adapt this remediation before merging.\n"
        f"     # Root cause: {rca.get('root_cause', '')}\n"
        f"     # Recommended resolution: {rca.get('recommended_resolution', '')}\n"
    )
    return diff
