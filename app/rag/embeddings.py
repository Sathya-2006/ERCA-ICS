"""
Embedding provider abstraction.

Two backends:

1. "openai"  - calls an OpenAI-compatible embeddings endpoint
               (OPENAI_API_KEY / OPENAI_BASE_URL). Real semantic embeddings.
2. "offline" - a deterministic, dependency-light local embedding built from
               hashed n-gram term frequencies (a HashingVectorizer). It is
               genuinely semantic-ish (cosine similarity over token
               distributions), requires no network access or model download,
               and is used automatically whenever no OPENAI_API_KEY is
               configured -- so RAG works out of the box.

Both backends return L2-normalized float vectors of the same fixed
dimensionality (settings.EMBEDDING_DIM) so they are interchangeable in
vector_store.py.
"""
from __future__ import annotations

import logging
import math
from functools import lru_cache

import numpy as np
import requests
from sklearn.feature_extraction.text import HashingVectorizer

from app.config import get_settings

logger = logging.getLogger("erca_ris.rag.embeddings")
settings = get_settings()


def _normalize(vec: np.ndarray) -> list[float]:
    norm = np.linalg.norm(vec)
    if norm == 0 or math.isnan(norm):
        return vec.tolist()
    return (vec / norm).tolist()


@lru_cache
def _hashing_vectorizer() -> HashingVectorizer:
    return HashingVectorizer(
        n_features=settings.EMBEDDING_DIM,
        alternate_sign=False,
        ngram_range=(1, 2),
        norm=None,
    )


def _offline_embed(text: str) -> list[float]:
    vec = _hashing_vectorizer().transform([text or ""]).toarray()[0]
    return _normalize(vec)


def _openai_embed(text: str) -> list[float] | None:
    if not settings.OPENAI_API_KEY:
        return None
    try:
        resp = requests.post(
            f"{settings.OPENAI_BASE_URL}/embeddings",
            headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
            json={"model": "text-embedding-3-small", "input": text},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()["data"][0]["embedding"]
        vec = np.array(data, dtype=float)
        # Project/pad to configured dimensionality so it's comparable with
        # offline embeddings already stored (best-effort; recommend keeping
        # one provider consistent per deployment).
        if len(vec) != settings.EMBEDDING_DIM:
            if len(vec) > settings.EMBEDDING_DIM:
                vec = vec[: settings.EMBEDDING_DIM]
            else:
                vec = np.pad(vec, (0, settings.EMBEDDING_DIM - len(vec)))
        return _normalize(vec)
    except Exception as exc:  # network / auth / rate-limit errors all fall back
        logger.warning("OpenAI embedding call failed, falling back to offline embedder: %s", exc)
        return None


def embed_text(text: str) -> list[float]:
    """Returns a normalized embedding vector for `text` using the configured provider."""
    provider = settings.EMBEDDING_PROVIDER
    if provider in ("openai", "auto"):
        vec = _openai_embed(text)
        if vec is not None:
            return vec
        if provider == "openai":
            logger.warning("EMBEDDING_PROVIDER=openai but no key/response; using offline embedder")
    return _offline_embed(text)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    if va.size == 0 or vb.size == 0:
        return 0.0
    denom = (np.linalg.norm(va) * np.linalg.norm(vb))
    if denom == 0:
        return 0.0
    return float(np.dot(va, vb) / denom)
