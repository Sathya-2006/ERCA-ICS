"""
LLM provider abstraction for RCA generation.

Providers, tried in order based on LLM_PROVIDER / available credentials:
  - "openai":      OpenAI-compatible chat-completions endpoint (OPENAI_API_KEY)
  - "huggingface":  HuggingFace Inference API (HF_TOKEN + HF_MODEL)
  - "offline":     deterministic, evidence-driven local reasoner (no network)

The LLM is NEVER asked to invent a root cause from nothing -- callers always
pass structured evidence (code intelligence + RAG history + ownership) and
the prompt instructs the model to answer strictly from that evidence and
return JSON matching the RCA schema. The offline provider applies the same
evidence-weighting logic without an LLM call, so the platform is fully
functional with zero external keys.
"""
from __future__ import annotations

import json
import logging
import re

import requests

from app.config import get_settings

logger = logging.getLogger("erca_ris.rca.llm_provider")
settings = get_settings()

RCA_JSON_SCHEMA_HINT = """
Respond with ONLY a JSON object (no markdown fences, no commentary) matching:
{
  "root_cause": "string",
  "confidence": 0.0,
  "agreement_ratio": 0.0,
  "status": "LOW|MEDIUM|HIGH|UNVERIFIED",
  "novel_incident": true|false,
  "requires_manual_review": true|false,
  "recommended_resolution": "string",
  "recommended_prevention": "string",
  "evidence": ["string", ...]
}
Base your answer strictly on the evidence provided (code_evidence, rag_evidence,
ownership). Do not invent facts, file/line numbers, past incidents, or root
causes that are not directly supported by that evidence.

CRITICAL RULE - NO HISTORICAL / CODE MATCH:
If rag_evidence is empty (no similar incident found in the historical
knowledge base) AND code_evidence has no confident match, you MUST NOT
present a confident root cause. Instead:
  - set "novel_incident": true and "requires_manual_review": true
  - set "status": "UNVERIFIED" and keep "confidence" <= 0.3
  - set "root_cause" to something like: "No matching historical incident or
    confident code match found for this error. This may be a new/first-time
    failure pattern."
  - list only clearly-labelled UNVERIFIED possibilities in "evidence", e.g.
    "Possible cause (unverified): <short hypothesis based only on the error
    text>" -- never state these as confirmed causes.
  - "recommended_resolution" must ask a human to investigate manually (e.g.
    "Not enough evidence to auto-diagnose; escalate to the owning team for
    manual investigation."), not describe a fix as if it were confirmed.
Never fabricate a similarity score, incident ID, file path, or line number
that isn't present in the evidence you were given.
confidence and agreement_ratio are floats in [0,1].
"""


def _build_prompt(context: dict) -> str:
    return (
        "You are an SRE root-cause-analysis assistant.\n"
        f"Incident service: {context['service']}\n"
        f"Error message: {context['error_message']}\n\n"
        f"Code evidence: {json.dumps(context.get('code_evidence') or {})}\n"
        f"Historical/RAG evidence: {json.dumps(context.get('rag_evidence') or [])}\n"
        f"Ownership: {json.dumps(context.get('ownership') or {})}\n\n"
        f"{RCA_JSON_SCHEMA_HINT}"
    )


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


def _call_openai(prompt: str) -> dict | None:
    if not settings.OPENAI_API_KEY:
        return None
    try:
        resp = requests.post(
            f"{settings.OPENAI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={
                "model": settings.OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
            },
            timeout=30,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(content)
    except Exception as exc:
        logger.warning("OpenAI RCA call failed, falling back: %s", exc)
        return None


def _call_huggingface(prompt: str) -> dict | None:
    if not settings.HF_TOKEN or not settings.HF_MODEL:
        return None
    try:
        resp = requests.post(
            f"https://api-inference.huggingface.co/models/{settings.HF_MODEL}",
            headers={"Authorization": f"Bearer {settings.HF_TOKEN}"},
            json={"inputs": prompt},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data[0]["generated_text"] if isinstance(data, list) else str(data)
        return _extract_json(text)
    except Exception as exc:
        logger.warning("HuggingFace RCA call failed, falling back: %s", exc)
        return None


def _offline_reason(context: dict) -> dict:
    """
    Deterministic, evidence-weighted reasoner used when no LLM credentials
    are configured. It does not hallucinate: every field is derived directly
    from the code evidence / RAG evidence / ownership passed in.
    """
    error = (context.get("error_message") or "").lower()
    code_evidence = context.get("code_evidence") or {}
    rag_evidence = context.get("rag_evidence") or []

    # Weight historical agreement.
    causes: dict[str, float] = {}
    for item in rag_evidence:
        cause = (item.get("metadata") or {}).get("root_cause")
        if cause:
            causes[cause] = causes.get(cause, 0.0) + float(item.get("similarity") or 0.0)

    historical_cause = max(causes, key=causes.get) if causes else None
    total_weight = sum(causes.values())
    agreement_ratio = round(causes[historical_cause] / total_weight, 2) if historical_cause and total_weight else 0.0

    exception_type = code_evidence.get("exception_type")
    function = code_evidence.get("function")
    file_path = code_evidence.get("file")

    # No historical match AND no confident code match: this is a genuinely
    # novel incident. Do NOT synthesize a confident-sounding root cause --
    # surface it as unverified and route it to a human instead.
    no_history = not historical_cause
    no_code_match = not code_evidence.get("found")
    novel_incident = no_history and no_code_match

    if novel_incident:
        root_cause = (
            "No matching historical incident or confident code match found "
            "for this error. This may be a new/first-time failure pattern "
            "not yet present in the incident knowledge base."
        )
    elif historical_cause:
        root_cause = historical_cause
    elif exception_type == "TimeoutError" or "timed out" in error or "timeout" in error:
        root_cause = f"Downstream dependency latency/timeout triggered in {function or 'the affected function'}"
    elif exception_type in ("ConnectionError", "PermissionError") or "unavailable" in error:
        root_cause = f"Dependency or configuration unavailability triggered in {function or 'the affected function'}"
    elif code_evidence.get("found"):
        root_cause = f"Failure condition triggered by {code_evidence.get('code') or 'the identified code path'}"
    else:
        root_cause = "Insufficient evidence to pinpoint a definitive root cause"

    # Confidence: evidence-based composite of code match strength + historical agreement.
    code_component = min(float(code_evidence.get("match_score") or 0.0) / 4.0, 1.0) if code_evidence.get("found") else 0.0
    history_component = agreement_ratio
    confidence = round(min(0.35 + 0.4 * code_component + 0.4 * history_component, 0.99), 2) if code_evidence.get("found") or causes else 0.3

    if novel_incident:
        confidence = min(confidence, 0.3)
        status = "UNVERIFIED"
    elif confidence >= 0.75:
        status = "HIGH"
    elif confidence >= 0.5:
        status = "MEDIUM"
    else:
        status = "LOW"

    if novel_incident:
        # Give the human a starting point without ever asserting it as fact.
        if exception_type == "TimeoutError" or "timed out" in error or "timeout" in error:
            hint = "downstream dependency latency/timeout"
        elif exception_type in ("ConnectionError", "PermissionError") or "unavailable" in error:
            hint = "dependency or configuration unavailability"
        else:
            hint = "an unrecognized failure condition"
        resolution = (
            "Not enough evidence to auto-diagnose this incident with confidence. "
            "Escalate to the owning team for manual investigation before applying any fix."
        )
        prevention = (
            "Once resolved, record the confirmed root cause and resolution back into the "
            "incident knowledge base so future occurrences can be auto-detected."
        )
    elif "unavailable" in error:
        resolution = "Restore the unavailable dependency/configuration, then rerun the affected operation."
        prevention = "Add automated dependency health checks, alerting, and regression validation."
    elif "timed out" in error or "timeout" in error:
        resolution = "Validate the downstream dependency, correct timeout/configuration conditions, then replay the affected workload."
        prevention = "Add dependency latency monitoring, timeout alerts, and integration/recovery tests."
    else:
        resolution = "Inspect the identified source evidence, correct the failing condition, and validate service health."
        prevention = "Add regression coverage and monitoring for the failure condition."

    evidence_list = []
    if code_evidence.get("found"):
        evidence_list.append(f"{file_path}::{function} line {code_evidence.get('line')} raises {exception_type}")
    for item in rag_evidence[:3]:
        evidence_list.append(f"Historical incident {item.get('incident_id')} (similarity {item.get('similarity')})")
    if novel_incident:
        evidence_list.append(
            f"No DB/RAG match and no confident code match. Possible cause (unverified, based only on "
            f"error text): {hint}. Manual verification required."
        )

    return {
        "root_cause": root_cause,
        "confidence": confidence,
        "agreement_ratio": agreement_ratio,
        "status": status,
        "novel_incident": novel_incident,
        "requires_manual_review": novel_incident,
        "recommended_resolution": resolution,
        "recommended_prevention": prevention,
        "evidence": evidence_list,
    }


def generate_rca(context: dict) -> dict:
    """Returns a dict matching the RCA JSON schema, from the configured provider."""
    provider = settings.LLM_PROVIDER
    prompt = _build_prompt(context)

    if provider in ("openai", "auto"):
        result = _call_openai(prompt)
        if result:
            return _coerce_schema(result)

    if provider in ("huggingface", "auto"):
        result = _call_huggingface(prompt)
        if result:
            return _coerce_schema(result)

    return _offline_reason(context)


def _coerce_schema(result: dict) -> dict:
    novel_incident = bool(result.get("novel_incident", False))
    return {
        "root_cause": result.get("root_cause") or "Unknown",
        "confidence": float(result.get("confidence") or 0.0),
        "agreement_ratio": float(result.get("agreement_ratio") or 0.0),
        "status": result.get("status") or "LOW",
        "novel_incident": novel_incident,
        "requires_manual_review": bool(result.get("requires_manual_review", novel_incident)),
        "recommended_resolution": result.get("recommended_resolution") or "",
        "recommended_prevention": result.get("recommended_prevention") or "",
        "evidence": result.get("evidence") or [],
    }
