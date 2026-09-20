"""NagarNetra API - PS-18 "CivicFix" (Global SDG + AI Hackathon 2026).

Decision-support for municipal grievance triage. Not an autonomous enforcement
system: every consequential decision is made by a named officer, and every
override is recorded with a reason.

Start with::

    uvicorn app.main:app --reload --app-dir backend
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.db import init_db, session_scope
from app.routers import admin, analytics, auth, complaints, public

# Complaints arrive in Devanagari. A Windows console defaults to cp1252 and
# raises UnicodeEncodeError the first time a Marathi string reaches a log
# handler - which would take the server down mid-demo. Force UTF-8 early.
for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):  # pragma: no branch
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover
            pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("nagarnetra")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create tables and load reference data before serving the first request."""
    init_db()
    db = session_scope()
    try:
        from app.services.bootstrap import ensure_reference_data

        counts = ensure_reference_data(db)
        logger.info(
            "Reference data ready: %s wards, %s POIs", counts["wards"], counts["pois"]
        )
    except Exception:  # noqa: BLE001 - never block startup on seed data
        logger.exception("Could not load reference data; run scripts/build_wards.py")
        db.rollback()
    finally:
        db.close()

    logger.info(
        "%s (%s) starting | LLM=%s active=%s | demo_mode=%s",
        settings.app_name,
        settings.challenge_id,
        settings.llm_provider,
        settings.llm_active,
        settings.demo_mode,
    )
    yield
    logger.info("%s shutting down", settings.app_name)


app = FastAPI(
    title="NagarNetra API",
    version="1.0.0",
    summary="Intelligent citizen grievance triage, deduplication and accountability (PS-18).",
    description=(
        "NagarNetra collapses duplicate civic complaints into single issues, ranks them "
        "with a transparent published formula, and audits whether every ward and every "
        "language is served equally.\n\n"
        "**Scope:** decision-support for municipal staff. Not an autonomous enforcement "
        "system. Final decisions rest with officers."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Never show a stack trace to a citizen, and never leak complaint text."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Something went wrong at our end. Your data is safe and nothing was lost.",
            "path": request.url.path,
        },
    )


app.include_router(public.router)
app.include_router(auth.router)
app.include_router(complaints.router)
app.include_router(admin.router)
app.include_router(analytics.router)

# Uploaded photos. Served from a dedicated directory so nothing else in the
# application tree is ever reachable over HTTP.
app.mount("/media", StaticFiles(directory=str(settings.resolved_upload_dir)), name="media")


@app.get("/", include_in_schema=False)
def root() -> dict[str, Any]:
    return {
        "name": settings.app_name,
        "challenge": settings.challenge_id,
        "docs": "/docs",
        "health": "/api/health",
        "citizen_app": "http://localhost:5173",
    }
