from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Point at a throwaway SQLite file BEFORE importing anything from `app`,
# so every module that reads settings.DATABASE_URL at import time gets
# the test database instead of the real runtime/erca_ris.db.
_tmp_dir = tempfile.mkdtemp(prefix="erca_ris_test_")
_tmp_db = Path(_tmp_dir) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db}"
os.environ["LLM_PROVIDER"] = "offline"
os.environ["EMBEDDING_PROVIDER"] = "offline"
os.environ["GITHUB_TOKEN"] = ""
os.environ["GITHUB_REPOSITORY"] = ""
os.environ["SLACK_WEBHOOK_URL"] = ""
os.environ["SMTP_HOST"] = ""

from app.config import get_settings  # noqa: E402
get_settings.cache_clear()

from app.db.database import engine, Base, SessionLocal  # noqa: E402
from app.db import models  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
