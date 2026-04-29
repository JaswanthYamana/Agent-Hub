"""
main.py – AI Agent Observability Platform.

Architecture:
  • PostgreSQL persistence via asyncpg (storage.pg_database + storage.pg_repository)
  • OTLP/HTTP receiver at POST /v1/traces for real agent integration
  • SDK ingest endpoint at POST /api/ingest
  • Execution graph builder (graph.builder)
  • Statistical anomaly baselines (storage.pg_repository.compute_and_save_baselines)
  • LLM-as-a-Judge evaluation (evaluation.judge)
  • Domain-agnostic evaluation with DOMAINS config (core.config)
  • Pass@k benchmarking
  • Step-by-step replay engine (replay.engine)
  • Project isolation (project_id on all models)

Run from the backend/ directory:
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from core.config import register_domain
from storage import pg_database, pg_repository
from api.deps import limiter

# Import API routers
from api.ingest import router as ingest_router
from api.traces import router as traces_router
from api.domains import router as domains_router
from api.redteam import router as redteam_router
from api.metrics import router as metrics_router

logger = logging.getLogger(__name__)

# ── Lifespan ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize PostgreSQL connection pool and create schema
    await pg_database.init()
    # Load persisted runtime domain definitions.
    try:
        for row in await pg_repository.list_domains():
            register_domain(row["domain_name"], row.get("config") or {})
    except Exception as exc:
        logger.debug("Domain bootstrap skipped: %s", exc)
    # Auto-compute statistical baselines from any existing traces on startup
    try:
        await pg_repository.compute_and_save_baselines("default")
    except Exception as exc:
        logger.debug("Baseline pre-computation skipped (no existing traces): %s", exc)
    yield
    await pg_database.close()

# ── App factory ────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Agent Observability Platform",
    description=(
        "Telemetry ingestion · Execution graphs · Anomaly detection · "
        "Reliability evaluation · Adversarial testing · Replay debugger"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ALLOWED_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.0.0"}

# Register Routers
app.include_router(ingest_router)
app.include_router(traces_router)
app.include_router(domains_router)
app.include_router(redteam_router)
app.include_router(metrics_router)
