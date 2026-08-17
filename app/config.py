"""
Central configuration for the ERCA&RIS backend.

All secrets/credentials are read from environment variables (see .env.example).
Nothing here is hardcoded. If a variable is missing, the relevant integration
falls back to a safe local/mock implementation so the platform stays fully
runnable without any external accounts.
"""
from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


class Settings:
    # --- General ---
    APP_NAME: str = "ERCA&RIS"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # --- Database ---
    # Defaults to a local SQLite file so the project runs with zero setup.
    # Point DATABASE_URL at a real Postgres+pgvector instance to use that instead;
    # the RAG layer automatically switches its vector search strategy based on
    # the resulting SQLAlchemy dialect (see app/rag/vector_store.py).
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL"
    ) or f"sqlite:///{PROJECT_ROOT / 'runtime' / 'erca_ris.db'}"

    # --- GitHub ---
    GITHUB_TOKEN: str | None = os.getenv("GITHUB_TOKEN") or None
    GITHUB_REPOSITORY: str | None = os.getenv("GITHUB_REPOSITORY") or None
    GITHUB_BASE_BRANCH: str = os.getenv("GITHUB_BASE_BRANCH", "main")
    SCM_PROVIDER: str = os.getenv("SCM_PROVIDER", "github")  # github|gitlab|bitbucket|azure|local
    TEAM_DEVELOPERS_JSON: str = os.getenv("TEAM_DEVELOPERS_JSON", "{}")
    DEVELOPER_EMAILS_JSON: str = os.getenv("DEVELOPER_EMAILS_JSON", "{}")

    # --- LLM providers ---
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY") or None
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    HF_TOKEN: str | None = os.getenv("HF_TOKEN") or None
    HF_MODEL: str = os.getenv("HF_MODEL", "")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "auto")  # auto|openai|huggingface|offline

    # --- Embeddings ---
    EMBEDDING_PROVIDER: str = os.getenv("EMBEDDING_PROVIDER", "auto")  # auto|openai|offline
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", "256"))

    # --- Notifications ---
    SLACK_WEBHOOK_URL: str | None = os.getenv("SLACK_WEBHOOK_URL") or None
    SMTP_HOST: str | None = os.getenv("SMTP_HOST") or None
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587") or 587)
    SMTP_USERNAME: str | None = os.getenv("SMTP_USERNAME") or None
    SMTP_PASSWORD: str | None = os.getenv("SMTP_PASSWORD") or None
    NOTIFY_EMAIL_FROM: str = os.getenv("NOTIFY_EMAIL_FROM", "erca-ris@example.com")

    # --- CORS ---
    ALLOWED_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5000,http://localhost:5000").split(",")
        if origin.strip()
    ]

    # --- Repository under analysis ---
    PROJECT_ROOT: Path = PROJECT_ROOT
    SOURCE_ROOT: Path = PROJECT_ROOT / "sample_app"
    CODEOWNERS_PATH: Path = PROJECT_ROOT / "repositories" / "repo" / "CODEOWNERS"

    # --- RAG ---
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "5"))
    RAG_KNOWN_INCIDENT_THRESHOLD: float = float(os.getenv("RAG_KNOWN_INCIDENT_THRESHOLD", "0.92"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
