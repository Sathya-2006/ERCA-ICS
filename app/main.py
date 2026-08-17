from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.config import get_settings
from app.db.init_db import init_db
from app.api import routes_health, routes_incidents, routes_rag, routes_analytics

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("erca_ris")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("ERCA&RIS backend started. Database: %s", settings.DATABASE_URL)
    yield


app = FastAPI(
    title="ERCA&RIS",
    description="Enterprise Root Cause Analysis and Recommendation Intelligence System",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS: only the demo application origin(s) are allowed -- never "*" in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_health.router)
app.include_router(routes_incidents.router)
app.include_router(routes_rag.router)
app.include_router(routes_analytics.router)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    from pathlib import Path
    dashboard_path = Path(__file__).resolve().parent.parent / "erca_ris" / "templates" / "dashboard.html"
    if dashboard_path.exists():
        return dashboard_path.read_text()
    return "<h1>ERCA&RIS</h1><p>Dashboard template not found.</p>"
