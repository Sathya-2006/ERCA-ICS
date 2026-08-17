from __future__ import annotations

from sqlalchemy import inspect, text

from app.db.database import engine, Base
from app.db import models  # noqa: F401 - register ORM models


def init_db() -> None:
    """Create tables and apply tiny additive migrations for existing SQLite DBs."""
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    if "ownership" not in inspector.get_table_names():
        return

    existing = {c["name"] for c in inspector.get_columns("ownership")}
    additions = {
        "developer_username": "VARCHAR(128)",
        "developer_email": "VARCHAR(256)",
        "developer_active": "BOOLEAN DEFAULT 1",
        "resolution_source": "VARCHAR(64)",
        "exception_type": "VARCHAR(128)",
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE ownership ADD COLUMN {name} {ddl}"))
