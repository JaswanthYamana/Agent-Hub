"""
storage/pg_database.py – Async PostgreSQL persistence layer via asyncpg.

Provides the same public interface as storage/database.py so that
storage/__init__.py can transparently swap backends:

    init()      – creates the connection pool and applies the schema
    close()     – closes the pool
    get_pool()  – returns the live asyncpg.Pool

Usage note: asyncpg uses $1, $2, …  positional parameters, not ?.
Tables mirror the SQLite schema but use PostgreSQL-native types:
  – DOUBLE PRECISION  instead of REAL
  – BOOLEAN           instead of INTEGER (0/1) for flag columns
  – No PRAGMA statements (those are SQLite-only)
  – UNIQUE constraints enforced with ON CONFLICT … DO UPDATE SET
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import asyncpg  # type: ignore

from core.config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


# ── Public interface ───────────────────────────────────────────────────────

async def init() -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2,
        max_size=10,
        command_timeout=60,
    )
    async with _pool.acquire() as conn:
        await _create_schema(conn)
    logger.info("PostgreSQL pool initialised (DSN: %s)", _redact(DATABASE_URL))


async def close() -> None:
    if _pool:
        await _pool.close()
        logger.info("PostgreSQL pool closed.")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database not initialised; call await init() first.")
    return _pool


# ── Schema ─────────────────────────────────────────────────────────────────

async def _create_schema(conn: Any) -> None:
    """Idempotent schema creation — safe to call on every startup."""
    await conn.execute(_SCHEMA)
    logger.debug("PostgreSQL schema verified.")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    trace_id           TEXT PRIMARY KEY,
    project_id         TEXT NOT NULL DEFAULT 'default',
    session_id         TEXT,
    task               TEXT NOT NULL,
    scenario           TEXT NOT NULL DEFAULT 'normal',
    tags               TEXT NOT NULL DEFAULT '[]',
    start_time         DOUBLE PRECISION NOT NULL,
    end_time           DOUBLE PRECISION,
    duration_ms        DOUBLE PRECISION,
    total_steps        INTEGER NOT NULL DEFAULT 0,
    tool_call_count    INTEGER NOT NULL DEFAULT 0,
    error_count        INTEGER NOT NULL DEFAULT 0,
    token_usage        TEXT NOT NULL DEFAULT '{}',
    metrics            TEXT NOT NULL DEFAULT '{}',
    attack_active      BOOLEAN NOT NULL DEFAULT FALSE,
    attack_type        TEXT,
    attack_succeeded   BOOLEAN NOT NULL DEFAULT FALSE,
    completed          BOOLEAN NOT NULL DEFAULT FALSE,
    success            BOOLEAN NOT NULL DEFAULT FALSE,
    partial_completion BOOLEAN NOT NULL DEFAULT FALSE,
    final_summary      TEXT NOT NULL DEFAULT '',
    root_span_id       TEXT,
    created_at         DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_traces_project  ON traces(project_id);
CREATE INDEX IF NOT EXISTS idx_traces_start    ON traces(start_time DESC);
CREATE INDEX IF NOT EXISTS idx_traces_scenario ON traces(scenario);
CREATE INDEX IF NOT EXISTS idx_traces_complete ON traces(completed);

CREATE TABLE IF NOT EXISTS spans (
    span_id            TEXT PRIMARY KEY,
    trace_id           TEXT NOT NULL REFERENCES traces(trace_id),
    parent_span_id     TEXT,
    kind               TEXT NOT NULL,
    name               TEXT NOT NULL,
    start_time         DOUBLE PRECISION NOT NULL,
    end_time           DOUBLE PRECISION,
    duration_ms        DOUBLE PRECISION,
    status             TEXT NOT NULL DEFAULT 'PENDING',
    attributes         TEXT NOT NULL DEFAULT '{}',
    events             TEXT NOT NULL DEFAULT '[]',
    error_message      TEXT,
    contains_injection BOOLEAN NOT NULL DEFAULT FALSE,
    injection_payload  TEXT,
    service_name       TEXT NOT NULL DEFAULT 'demo-agent',
    project_id         TEXT NOT NULL DEFAULT 'default',
    session_id         TEXT,
    token_usage        TEXT NOT NULL DEFAULT '{}',
    created_at         DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_spans_trace  ON spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_spans_kind   ON spans(kind);
CREATE INDEX IF NOT EXISTS idx_spans_status ON spans(status);
CREATE INDEX IF NOT EXISTS idx_spans_name   ON spans(name);

CREATE TABLE IF NOT EXISTS anomalies (
    id          TEXT PRIMARY KEY,
    trace_id    TEXT NOT NULL REFERENCES traces(trace_id),
    span_id     TEXT NOT NULL DEFAULT '',
    span_name   TEXT NOT NULL DEFAULT '',
    type        TEXT NOT NULL,
    severity    TEXT NOT NULL,
    description TEXT NOT NULL,
    evidence    TEXT NOT NULL DEFAULT '{}',
    created_at  DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_anomalies_trace    ON anomalies(trace_id);
CREATE INDEX IF NOT EXISTS idx_anomalies_severity ON anomalies(severity);
CREATE INDEX IF NOT EXISTS idx_anomalies_type     ON anomalies(type);

CREATE TABLE IF NOT EXISTS baselines (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL DEFAULT 'default',
    span_name    TEXT NOT NULL,
    metric       TEXT NOT NULL,
    mean         DOUBLE PRECISION NOT NULL,
    std          DOUBLE PRECISION NOT NULL,
    p50          DOUBLE PRECISION NOT NULL,
    p95          DOUBLE PRECISION NOT NULL,
    p99          DOUBLE PRECISION NOT NULL,
    sample_count INTEGER NOT NULL,
    computed_at  DOUBLE PRECISION NOT NULL,
    UNIQUE (project_id, span_name, metric)
);

CREATE TABLE IF NOT EXISTS domains (
    domain_name TEXT PRIMARY KEY,
    config      TEXT NOT NULL,
    updated_at  DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS attack_results (
    attack_id           TEXT PRIMARY KEY,
    timestamp           DOUBLE PRECISION NOT NULL,
    attack_type         TEXT NOT NULL,
    intensity           TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    baseline_metrics    TEXT NOT NULL DEFAULT '{}',
    attacked_metrics    TEXT NOT NULL DEFAULT '{}',
    baseline_trace_id   TEXT,
    attacked_trace_id   TEXT,
    attack_success_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
    reliability_delta   DOUBLE PRECISION NOT NULL DEFAULT 0,
    platform_detection  BOOLEAN NOT NULL DEFAULT FALSE,
    anomalies_detected  TEXT NOT NULL DEFAULT '[]',
    injection_payload   TEXT NOT NULL DEFAULT '',
    countermeasures     TEXT NOT NULL DEFAULT '[]',
    created_at          DOUBLE PRECISION NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attacks_type ON attack_results(attack_type);

-- ── LLM judge results ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS judge_results (
    id               TEXT PRIMARY KEY,
    trace_id         TEXT NOT NULL REFERENCES traces(trace_id),
    tool_selection   TEXT NOT NULL,
    param_correct    TEXT NOT NULL,
    faithfulness     TEXT NOT NULL,
    workflow_order   TEXT NOT NULL DEFAULT 'PASS',
    task_completion  TEXT NOT NULL,
    explanation      TEXT NOT NULL DEFAULT '',
    confidence_score DOUBLE PRECISION,
    source           TEXT NOT NULL DEFAULT 'llm',
    judge_backend    TEXT NOT NULL DEFAULT 'llm',
    model            TEXT,
    created_at       DOUBLE PRECISION NOT NULL
);

ALTER TABLE judge_results ADD COLUMN IF NOT EXISTS judge_backend TEXT NOT NULL DEFAULT 'llm';

CREATE UNIQUE INDEX IF NOT EXISTS idx_judge_trace ON judge_results(trace_id);

-- ── Time-series reliability metrics ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS time_series_metrics (
    id           TEXT PRIMARY KEY,
    timestamp    DOUBLE PRECISION NOT NULL,
    project_id   TEXT NOT NULL DEFAULT 'default',
    agent_name   TEXT NOT NULL DEFAULT 'demo-agent',
    metric_name  TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    trace_id     TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tsm_metric_ts  ON time_series_metrics(metric_name, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_tsm_project    ON time_series_metrics(project_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_tsm_trace      ON time_series_metrics(trace_id);

-- ── Attack evolution tables ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS evolution_attacks (
    id               TEXT PRIMARY KEY,
    test_id          TEXT NOT NULL,
    generation       INTEGER NOT NULL,
    prompt           TEXT NOT NULL,
    parent_attack_id TEXT,
    created_at       DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS evolution_attack_runs (
    id               TEXT PRIMARY KEY,
    attack_id        TEXT NOT NULL REFERENCES evolution_attacks(id),
    trace_id         TEXT,
    success          BOOLEAN NOT NULL DEFAULT FALSE,
    latency          DOUBLE PRECISION NOT NULL DEFAULT 0,
    tokens_used      INTEGER NOT NULL DEFAULT 0,
    response         TEXT NOT NULL DEFAULT '',
    created_at       DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS evolution_metrics (
    id                  TEXT PRIMARY KEY,
    test_id             TEXT NOT NULL,
    generation          INTEGER NOT NULL,
    total_attacks       INTEGER NOT NULL DEFAULT 0,
    successful_attacks  INTEGER NOT NULL DEFAULT 0,
    success_rate        DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_latency         DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at          DOUBLE PRECISION NOT NULL
);
"""


# ── Helpers ────────────────────────────────────────────────────────────────

def _redact(url: str) -> str:
    """Replace the password in a DSN string before logging."""
    try:
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(parsed.password, "***")
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass
    return url
