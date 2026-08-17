from __future__ import annotations

from fastapi import APIRouter

from app.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/api/health")
def health():
    return {
        "status": "ok",
        "service": "ERCA&RIS",
        "environment": settings.ENVIRONMENT,
        "database": settings.DATABASE_URL.split("://")[0],
        "llm_provider": settings.LLM_PROVIDER,
        "github_integration": bool(settings.GITHUB_TOKEN and settings.GITHUB_REPOSITORY),
    }
