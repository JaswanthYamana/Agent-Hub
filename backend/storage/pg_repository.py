"""
storage/pg_repository.py – asyncpg-backed data-access layer.

Same public interface as storage/repository.py (SQLite).  swap is transparent
via storage/__init__.py when DB_BACKEND=postgres.

Key differences from the SQLite module:
  • $1, $2, … positional parameters instead of ?
  • INSERT … ON CONFLICT … DO UPDATE / DO NOTHING instead of INSERT OR REPLACE / IGNORE
  • asyncpg.Pool instead of aiosqlite.Connection (pool-level execute/fetch)
  • Boolean columns returned as Python bool by asyncpg (no int cast needed)
  • json_extract() → (col::jsonb->>'key')::FLOAT for PostgreSQL
  • CAST(x AS INTEGER) → x::BIGINT for numeric truncation
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
import uuid
from typing import Any, Dict, List, Optional

from storage.pg_database import get_pool
from core.models import Span, SpanEvent, SpanKind, SpanStatus, Trace

# ── SSE event queues (trace_id → asyncio.Queue) ────────────────────────────
# These are in-memory — equivalent dict as the SQLite version.
_queues: Dict[str, asyncio.Queue] = {}
_event_buffers: Dict[str, List[Dict[str, Any]]] = {}
_event_counters: Dict[str, int] = {}
_MAX_BUFFERED_EVENTS = 500


def create_queue(trace_id: str) -> None:
    """Create an SSE queue for the trace.  No-op if one already exists."""
    if trace_id not in _queues:
        _queues[trace_id] = asyncio.Queue()
    _event_buffers.setdefault(trace_id, [])
    _event_counters.setdefault(trace_id, 0)


def release_queue(trace_id: str) -> None:
    """Remove the SSE queue when the stream consumer exits (prevents memory leak)."""
    _queues.pop(trace_id, None)


async def push_event(trace_id: str, event: Dict[str, Any]) -> None:
    _event_counters[trace_id] = _event_counters.get(trace_id, 0) + 1
    enriched = dict(event)
    enriched["_event_id"] = _event_counters[trace_id]

    buf = _event_buffers.setdefault(trace_id, [])
    buf.append(enriched)
    if len(buf) > _MAX_BUFFERED_EVENTS:
        del buf[: len(buf) - _MAX_BUFFERED_EVENTS]

    q = _queues.get(trace_id)
    if q:
        await q.put(enriched)


async def pop_event(trace_id: str, timeout: float = 0.3) -> Optional[Dict[str, Any]]:
    q = _queues.get(trace_id)
    if not q:
        return None
    try:
        return await asyncio.wait_for(q.get(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


def get_buffered_events(trace_id: str, after_event_id: int = 0) -> List[Dict[str, Any]]:
    """Return buffered SSE events with event id > after_event_id."""
    return [
        e for e in _event_buffers.get(trace_id, [])
        if int(e.get("_event_id", 0)) > after_event_id
    ]


# ── Parameter builder ──────────────────────────────────────────────────────

class _P:
    """Incremental positional-parameter builder for asyncpg ($1, $2, …)."""
    def __init__(self) -> None:
        self._n = 0
        self.values: List[Any] = []

    def add(self, value: Any) -> str:
        self._n += 1
        self.values.append(value)
        return f"${self._n}"

    @property
    def next_n(self) -> int:
        return self._n + 1


# ── Trace CRUD ─────────────────────────────────────────────────────────────

async def save_trace(t: Trace) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO traces (
            trace_id, project_id, session_id, task, scenario, tags,
            start_time, end_time, duration_ms,
            total_steps, tool_call_count, error_count,
            token_usage, metrics,
            attack_active, attack_type, attack_succeeded,
            completed, success, partial_completion,
            final_summary, root_span_id, created_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
            $15,$16,$17,$18,$19,$20,$21,$22,$23
        )
        ON CONFLICT (trace_id) DO UPDATE SET
            project_id         = EXCLUDED.project_id,
            session_id         = EXCLUDED.session_id,
            task               = EXCLUDED.task,
            scenario           = EXCLUDED.scenario,
            tags               = EXCLUDED.tags,
            start_time         = EXCLUDED.start_time,
            end_time           = EXCLUDED.end_time,
            duration_ms        = EXCLUDED.duration_ms,
            total_steps        = EXCLUDED.total_steps,
            tool_call_count    = EXCLUDED.tool_call_count,
            error_count        = EXCLUDED.error_count,
            token_usage        = EXCLUDED.token_usage,
            metrics            = EXCLUDED.metrics,
            attack_active      = EXCLUDED.attack_active,
            attack_type        = EXCLUDED.attack_type,
            attack_succeeded   = EXCLUDED.attack_succeeded,
            completed          = EXCLUDED.completed,
            success            = EXCLUDED.success,
            partial_completion = EXCLUDED.partial_completion,
            final_summary      = EXCLUDED.final_summary,
            root_span_id       = EXCLUDED.root_span_id,
            created_at         = EXCLUDED.created_at
        """,
        t.trace_id, t.project_id, t.session_id,
        t.task, t.scenario, json.dumps(t.tags),
        t.start_time, t.end_time, t.duration_ms,
        t.total_steps, t.tool_call_count, t.error_count,
        json.dumps(t.token_usage), json.dumps(t.metrics),
        t.attack_active, t.attack_type, t.attack_succeeded,
        t.completed, t.success, t.partial_completion,
        t.final_summary, t.root_span_id, time.time(),
    )


async def save_trace_bundle(t: Trace, anomalies: Optional[List[Dict[str, Any]]] = None) -> None:
    """Persist trace, spans, and anomalies in a single transaction."""
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO traces (
                    trace_id, project_id, session_id, task, scenario, tags,
                    start_time, end_time, duration_ms,
                    total_steps, tool_call_count, error_count,
                    token_usage, metrics,
                    attack_active, attack_type, attack_succeeded,
                    completed, success, partial_completion,
                    final_summary, root_span_id, created_at
                ) VALUES (
                    $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,
                    $15,$16,$17,$18,$19,$20,$21,$22,$23
                )
                ON CONFLICT (trace_id) DO UPDATE SET
                    project_id         = EXCLUDED.project_id,
                    session_id         = EXCLUDED.session_id,
                    task               = EXCLUDED.task,
                    scenario           = EXCLUDED.scenario,
                    tags               = EXCLUDED.tags,
                    start_time         = EXCLUDED.start_time,
                    end_time           = EXCLUDED.end_time,
                    duration_ms        = EXCLUDED.duration_ms,
                    total_steps        = EXCLUDED.total_steps,
                    tool_call_count    = EXCLUDED.tool_call_count,
                    error_count        = EXCLUDED.error_count,
                    token_usage        = EXCLUDED.token_usage,
                    metrics            = EXCLUDED.metrics,
                    attack_active      = EXCLUDED.attack_active,
                    attack_type        = EXCLUDED.attack_type,
                    attack_succeeded   = EXCLUDED.attack_succeeded,
                    completed          = EXCLUDED.completed,
                    success            = EXCLUDED.success,
                    partial_completion = EXCLUDED.partial_completion,
                    final_summary      = EXCLUDED.final_summary,
                    root_span_id       = EXCLUDED.root_span_id,
                    created_at         = EXCLUDED.created_at
                """,
                t.trace_id, t.project_id, t.session_id,
                t.task, t.scenario, json.dumps(t.tags),
                t.start_time, t.end_time, t.duration_ms,
                t.total_steps, t.tool_call_count, t.error_count,
                json.dumps(t.token_usage), json.dumps(t.metrics),
                t.attack_active, t.attack_type, t.attack_succeeded,
                t.completed, t.success, t.partial_completion,
                t.final_summary, t.root_span_id, time.time(),
            )

            for s in t.spans:
                await conn.execute(
                    """
                    INSERT INTO spans (
                        span_id, trace_id, parent_span_id, kind, name,
                        start_time, end_time, duration_ms, status,
                        attributes, events, error_message,
                        contains_injection, injection_payload,
                        service_name, project_id, session_id, token_usage, created_at
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19
                    )
                    ON CONFLICT (span_id) DO UPDATE SET
                        trace_id           = EXCLUDED.trace_id,
                        parent_span_id     = EXCLUDED.parent_span_id,
                        kind               = EXCLUDED.kind,
                        name               = EXCLUDED.name,
                        start_time         = EXCLUDED.start_time,
                        end_time           = EXCLUDED.end_time,
                        duration_ms        = EXCLUDED.duration_ms,
                        status             = EXCLUDED.status,
                        attributes         = EXCLUDED.attributes,
                        events             = EXCLUDED.events,
                        error_message      = EXCLUDED.error_message,
                        contains_injection = EXCLUDED.contains_injection,
                        injection_payload  = EXCLUDED.injection_payload,
                        service_name       = EXCLUDED.service_name,
                        project_id         = EXCLUDED.project_id,
                        session_id         = EXCLUDED.session_id,
                        token_usage        = EXCLUDED.token_usage,
                        created_at         = EXCLUDED.created_at
                    """,
                    s.span_id, s.trace_id, s.parent_span_id,
                    s.kind.value, s.name,
                    s.start_time, s.end_time, s.duration_ms,
                    s.status.value,
                    json.dumps(s.attributes),
                    json.dumps([e.model_dump() for e in s.events]),
                    s.error_message,
                    s.contains_injection, s.injection_payload,
                    s.service_name, s.project_id, s.session_id,
                    json.dumps(s.token_usage),
                    time.time(),
                )

            for a in anomalies or []:
                await conn.execute(
                    """
                    INSERT INTO anomalies (id, trace_id, span_id, span_name,
                                           type, severity, description, evidence, created_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    str(uuid.uuid4()), t.trace_id,
                    a.get("span_id", ""), a.get("span_name", ""),
                    str(a.get("type", "")), a.get("severity", "low"),
                    a.get("description", ""),
                    json.dumps(a.get("evidence", {})),
                    time.time(),
                )


async def get_trace(trace_id: str, include_spans: bool = True) -> Optional[Trace]:
    pool = get_pool()
    row = await pool.fetchrow("SELECT * FROM traces WHERE trace_id = $1", trace_id)
    if row is None:
        return None
    t = _row_to_trace(row)
    if include_spans:
        t.spans = await list_spans(trace_id)
    t.anomalies = await _fetch_anomalies(trace_id=trace_id)
    return t


async def list_traces(
    project_id: Optional[str] = None,
    scenario:   Optional[str] = None,
    limit:      int = 200,
    offset:     int = 0,
) -> List[Trace]:
    pool = get_pool()
    p = _P()
    clauses: List[str] = []
    if project_id:
        clauses.append(f"project_id = {p.add(project_id)}")
    if scenario:
        clauses.append(f"scenario = {p.add(scenario)}")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_p  = p.add(limit)
    offset_p = p.add(offset)
    rows = await pool.fetch(
        f"SELECT * FROM traces {where} ORDER BY start_time DESC LIMIT {limit_p} OFFSET {offset_p}",
        *p.values,
    )
    return [_row_to_trace(r) for r in rows]


# ── Span CRUD ──────────────────────────────────────────────────────────────

async def save_span(s: Span) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO spans (
            span_id, trace_id, parent_span_id, kind, name,
            start_time, end_time, duration_ms, status,
            attributes, events, error_message,
            contains_injection, injection_payload,
            service_name, project_id, session_id, token_usage, created_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19
        )
        ON CONFLICT (span_id) DO UPDATE SET
            trace_id           = EXCLUDED.trace_id,
            parent_span_id     = EXCLUDED.parent_span_id,
            kind               = EXCLUDED.kind,
            name               = EXCLUDED.name,
            start_time         = EXCLUDED.start_time,
            end_time           = EXCLUDED.end_time,
            duration_ms        = EXCLUDED.duration_ms,
            status             = EXCLUDED.status,
            attributes         = EXCLUDED.attributes,
            events             = EXCLUDED.events,
            error_message      = EXCLUDED.error_message,
            contains_injection = EXCLUDED.contains_injection,
            injection_payload  = EXCLUDED.injection_payload,
            service_name       = EXCLUDED.service_name,
            project_id         = EXCLUDED.project_id,
            session_id         = EXCLUDED.session_id,
            token_usage        = EXCLUDED.token_usage,
            created_at         = EXCLUDED.created_at
        """,
        s.span_id, s.trace_id, s.parent_span_id,
        s.kind.value, s.name,
        s.start_time, s.end_time, s.duration_ms,
        s.status.value,
        json.dumps(s.attributes),
        json.dumps([e.model_dump() for e in s.events]),
        s.error_message,
        s.contains_injection, s.injection_payload,
        s.service_name, s.project_id, s.session_id,
        json.dumps(s.token_usage),
        time.time(),
    )


async def list_spans(trace_id: str) -> List[Span]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM spans WHERE trace_id = $1 ORDER BY start_time ASC",
        trace_id,
    )
    return [_row_to_span(r) for r in rows]


# ── Anomaly CRUD ───────────────────────────────────────────────────────────

async def save_anomalies(trace_id: str, anomalies: List[Dict[str, Any]]) -> None:
    pool = get_pool()
    async with pool.acquire() as conn:
        for a in anomalies:
            await conn.execute(
                """
                INSERT INTO anomalies (id, trace_id, span_id, span_name,
                                       type, severity, description, evidence, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                ON CONFLICT (id) DO NOTHING
                """,
                str(uuid.uuid4()), trace_id,
                a.get("span_id", ""), a.get("span_name", ""),
                str(a.get("type", "")), a.get("severity", "low"),
                a.get("description", ""),
                json.dumps(a.get("evidence", {})),
                time.time(),
            )


async def list_all_anomalies(
    project_id: Optional[str] = None,
    severity:   Optional[str] = None,
    limit:      int = 500,
    offset:     int = 0,
) -> List[Dict[str, Any]]:
    return await list_anomalies(project_id=project_id, severity=severity, limit=limit, offset=offset)


async def list_anomalies(
    trace_id:   Optional[str] = None,
    project_id: Optional[str] = None,
    severity:   Optional[str] = None,
    limit:      int = 500,
    offset:     int = 0,
) -> List[Dict[str, Any]]:
    """Unified anomaly query — trace-scoped or global, with optional severity filter."""
    pool = get_pool()
    p = _P()
    clauses: List[str] = []
    if trace_id:
        clauses.append(f"a.trace_id = {p.add(trace_id)}")
    if project_id:
        clauses.append(
            f"a.trace_id IN (SELECT trace_id FROM traces WHERE project_id = {p.add(project_id)})"
        )
    if severity:
        clauses.append(f"a.severity = {p.add(severity)}")
    limit_p = p.add(limit)
    offset_p = p.add(offset)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = await pool.fetch(
        f"""SELECT a.*, t.task, t.scenario, t.start_time as trace_start
            FROM anomalies a
            LEFT JOIN traces t ON t.trace_id = a.trace_id
            {where}
            ORDER BY
              CASE a.severity
                WHEN 'critical' THEN 0
                WHEN 'high'     THEN 1
                WHEN 'medium'   THEN 2
                ELSE 3
              END,
              a.created_at DESC
            LIMIT {limit_p} OFFSET {offset_p}""",
        *p.values,
    )
    return [dict(r) for r in rows]


async def _fetch_anomalies(trace_id: str) -> List[Dict[str, Any]]:
    return await list_anomalies(trace_id=trace_id)


# ── Attack results CRUD ────────────────────────────────────────────────────

async def save_attack_result(r: Dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """
        INSERT INTO attack_results (
            attack_id, timestamp, attack_type, intensity, description,
            baseline_metrics, attacked_metrics,
            baseline_trace_id, attacked_trace_id,
            attack_success_rate, reliability_delta, platform_detection,
            anomalies_detected, injection_payload, countermeasures, created_at
        ) VALUES (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16
        )
        ON CONFLICT (attack_id) DO UPDATE SET
            timestamp           = EXCLUDED.timestamp,
            attack_type         = EXCLUDED.attack_type,
            intensity           = EXCLUDED.intensity,
            description         = EXCLUDED.description,
            baseline_metrics    = EXCLUDED.baseline_metrics,
            attacked_metrics    = EXCLUDED.attacked_metrics,
            baseline_trace_id   = EXCLUDED.baseline_trace_id,
            attacked_trace_id   = EXCLUDED.attacked_trace_id,
            attack_success_rate = EXCLUDED.attack_success_rate,
            reliability_delta   = EXCLUDED.reliability_delta,
            platform_detection  = EXCLUDED.platform_detection,
            anomalies_detected  = EXCLUDED.anomalies_detected,
            injection_payload   = EXCLUDED.injection_payload,
            countermeasures     = EXCLUDED.countermeasures,
            created_at          = EXCLUDED.created_at
        """,
        r["attack_id"], r["timestamp"],
        r["attack_type"], r["intensity"],
        r.get("description", ""),
        json.dumps(r.get("baseline_metrics", {})),
        json.dumps(r.get("attacked_metrics", {})),
        r.get("baseline_trace_id"), r.get("attacked_trace_id"),
        float(r.get("attack_success_rate", 0.0)),
        float(r.get("reliability_delta", 0.0)),
        bool(r.get("platform_detection", False)),
        json.dumps(r.get("anomalies_detected", [])),
        r.get("injection_payload", ""),
        json.dumps(r.get("countermeasures", [])),
        time.time(),
    )


async def list_attack_results(limit: int = 100) -> List[Dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM attack_results ORDER BY timestamp DESC LIMIT $1", limit
    )
    results = []
    for r in rows:
        d = dict(r)
        for k in ("baseline_metrics", "attacked_metrics", "anomalies_detected", "countermeasures"):
            if k in d and isinstance(d[k], str):
                d[k] = json.loads(d[k])
        results.append(d)
    return results


# ── Dashboard aggregates ───────────────────────────────────────────────────

async def get_dashboard_stats(project_id: Optional[str] = None) -> Dict[str, Any]:
    pool = get_pool()
    p = _P()
    where_parts: List[str] = []
    if project_id:
        where_parts.append(f"project_id = {p.add(project_id)}")
    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    agg_row = await pool.fetchrow(
        f"""SELECT
              COUNT(*)                                                    AS total,
              COUNT(*) FILTER (WHERE success)                            AS successes,
              COUNT(*) FILTER (WHERE attack_active)                      AS attacks,
              COUNT(*) FILTER (WHERE attack_active AND NOT attack_succeeded) AS blocked,
              SUM(error_count)                                           AS total_errors,
              SUM(tool_call_count)                                       AS total_tool_calls,
              AVG(duration_ms)                                           AS avg_duration_ms
            FROM traces {where}""",
        *p.values,
    )
    agg = dict(agg_row or {})
    total     = int(agg.get("total", 0) or 0)
    successes = int(agg.get("successes", 0) or 0)
    attacks   = int(agg.get("attacks", 0) or 0)
    blocked   = int(agg.get("blocked", 0) or 0)

    # Avg reliability score — extract from TEXT column cast to jsonb
    p2 = _P()
    score_parts = list(where_parts)  # reuse same filter
    if where_parts:
        # re-add the same param
        for val in p.values:
            p2.add(val)
    extra = p2.add(True)  # dummy to get next param number right if needed
    # Build score query cleanly
    p3 = _P()
    score_where_parts: List[str] = ["completed = TRUE",
                                    "(metrics::jsonb->>'overall_reliability_score') IS NOT NULL"]
    if project_id:
        score_where_parts.append(f"project_id = {p3.add(project_id)}")
    score_where = "WHERE " + " AND ".join(score_where_parts)
    score_row = await pool.fetchrow(
        f"""SELECT AVG((metrics::jsonb->>'overall_reliability_score')::FLOAT) AS avg_rel
            FROM traces {score_where}""",
        *p3.values,
    )
    avg_rel = score_row["avg_rel"] if score_row else None

    # Recent traces
    p4 = _P()
    where4_parts: List[str] = []
    if project_id:
        where4_parts.append(f"t.project_id = {p4.add(project_id)}")
    where4 = f"WHERE {' AND '.join(where4_parts)}" if where4_parts else ""
    recent_rows = await pool.fetch(
        f"""SELECT t.trace_id, t.task, t.scenario, t.success, t.completed,
                   t.attack_active, t.attack_type, t.duration_ms,
                   t.start_time, t.error_count,
                   (SELECT COUNT(*) FROM anomalies a WHERE a.trace_id = t.trace_id) AS anomaly_count
            FROM traces t {where4}
            ORDER BY t.start_time DESC LIMIT 10""",
        *p4.values,
    )
    recent = [dict(r) for r in recent_rows]

    # Anomaly breakdown
    p5 = _P()
    a_where_parts: List[str] = []
    if project_id:
        a_where_parts.append(
            f"trace_id IN (SELECT trace_id FROM traces WHERE project_id = {p5.add(project_id)})"
        )
    a_where = f"WHERE {' AND '.join(a_where_parts)}" if a_where_parts else ""
    anomaly_rows = await pool.fetch(
        f"""SELECT type, severity, COUNT(*) AS count
            FROM anomalies {a_where}
            GROUP BY type, severity ORDER BY count DESC LIMIT 15""",
        *p5.values,
    )
    anomaly_breakdown = [dict(r) for r in anomaly_rows]

    # Scenario distribution
    p6 = _P()
    sd_where_parts: List[str] = []
    if project_id:
        sd_where_parts.append(f"project_id = {p6.add(project_id)}")
    sd_where = f"WHERE {' AND '.join(sd_where_parts)}" if sd_where_parts else ""
    scenario_rows = await pool.fetch(
        f"SELECT scenario, COUNT(*) AS count FROM traces {sd_where} GROUP BY scenario ORDER BY count DESC",
        *p6.values,
    )
    scenario_dist = [dict(r) for r in scenario_rows]

    return {
        "total_traces":          total,
        "success_rate":          round(successes / total * 100, 1) if total else 0,
        "attack_count":          attacks,
        "attack_block_rate":     round(blocked / attacks * 100, 1) if attacks else 0,
        "avg_reliability_score": round(avg_rel, 3) if avg_rel else None,
        "avg_duration_ms":       round(float(agg.get("avg_duration_ms") or 0), 1),
        "total_tool_calls":      int(agg.get("total_tool_calls") or 0),
        "recent_traces":         recent,
        "anomaly_breakdown":     anomaly_breakdown,
        "scenario_distribution": scenario_dist,
    }


# ── Attack Evolution CRUD ─────────────────────────────────────────────────

_TS_METRIC_KEYS = [
    "overall_reliability_score",
    "tool_selection_accuracy",
    "parameter_correctness",
    "task_completion_rate",
    "workflow_correctness",
    "anomaly_count",
    "hallucination_rate",
    "error_rate",
]


async def save_evolution_result(result: Dict[str, Any]) -> None:
    pool = get_pool()
    test_id = result.get("test_id", "")
    now = time.time()

    async with pool.acquire() as conn:
        for m in result.get("metrics", []):
            await conn.execute(
                """INSERT INTO evolution_metrics
                       (id, test_id, generation, total_attacks, successful_attacks,
                        success_rate, avg_latency, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                   ON CONFLICT (id) DO UPDATE SET
                       total_attacks      = EXCLUDED.total_attacks,
                       successful_attacks = EXCLUDED.successful_attacks,
                       success_rate       = EXCLUDED.success_rate,
                       avg_latency        = EXCLUDED.avg_latency""",
                str(uuid.uuid4()),
                test_id,
                m.get("generation", 1),
                m.get("total_attacks", 0),
                m.get("successful_attacks", 0),
                m.get("success_rate", 0.0),
                m.get("avg_latency", 0.0),
                now,
            )

        for r in result.get("runs", []):
            await conn.execute(
                """INSERT INTO evolution_attacks (id, test_id, generation, prompt, parent_attack_id, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6)
                   ON CONFLICT (id) DO NOTHING""",
                r.get("attack_id", str(uuid.uuid4())),
                test_id,
                r.get("generation", 1),
                r.get("prompt", ""),
                r.get("parent_attack_id"),
                now,
            )
            await conn.execute(
                """INSERT INTO evolution_attack_runs
                       (id, attack_id, trace_id, success, latency, tokens_used, response, created_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                   ON CONFLICT (id) DO UPDATE SET
                       success     = EXCLUDED.success,
                       latency     = EXCLUDED.latency,
                       tokens_used = EXCLUDED.tokens_used,
                       response    = EXCLUDED.response""",
                r.get("id", str(uuid.uuid4())),
                r.get("attack_id", ""),
                r.get("trace_id"),
                bool(r.get("success", False)),
                r.get("latency", 0.0),
                r.get("tokens_used", 0),
                r.get("response", ""),
                now,
            )


async def get_evolution_result(test_id: str) -> Dict[str, Any]:
    pool = get_pool()
    metrics = await pool.fetch(
        "SELECT * FROM evolution_metrics WHERE test_id = $1 ORDER BY generation",
        test_id,
    )
    runs = await pool.fetch(
        """SELECT r.*, a.prompt, a.generation, a.parent_attack_id
           FROM evolution_attack_runs r
           JOIN evolution_attacks a ON r.attack_id = a.id
           WHERE a.test_id = $1 ORDER BY a.generation""",
        test_id,
    )
    return {
        "test_id": test_id,
        "metrics": [dict(r) for r in metrics],
        "runs":    [dict(r) for r in runs],
    }


# ── Time-series emit / query ──────────────────────────────────────────────

async def emit_trace_metrics(trace: Trace) -> None:
    """Persist each reliability metric as a time-series row after evaluation."""
    if not trace.metrics:
        return
    pool = get_pool()
    ts = trace.end_time or time.time()
    agent_name = trace.spans[0].service_name if trace.spans else "demo-agent"
    rows = []
    for key in _TS_METRIC_KEYS:
        value = trace.metrics.get(key)
        if value is None:
            continue
        rows.append((str(uuid.uuid4()), ts, trace.project_id, agent_name, key, float(value), trace.trace_id))
    if trace.attack_active and "attack_success_rate" in trace.metrics:
        rows.append((
            str(uuid.uuid4()), ts, trace.project_id, agent_name,
            "attack_success_rate", float(trace.metrics["attack_success_rate"]), trace.trace_id,
        ))
    if not rows:
        return
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO time_series_metrics (id,timestamp,project_id,agent_name,metric_name,metric_value,trace_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (id) DO NOTHING""",
            rows,
        )


async def emit_attack_metrics(result: Dict[str, Any], project_id: str = "default") -> None:
    """Persist attack_success_rate and reliability_delta after a red-team run."""
    asr   = result.get("attack_success_rate")
    delta = result.get("reliability_delta")
    ts    = result.get("timestamp") or time.time()
    attacked_trace_id = result.get("attacked_trace_id") or str(uuid.uuid4())
    rows = []
    if asr is not None:
        rows.append((str(uuid.uuid4()), ts, project_id, "red-team-engine",
                     "attack_success_rate", float(asr), attacked_trace_id))
    if delta is not None:
        rows.append((str(uuid.uuid4()), ts, project_id, "red-team-engine",
                     "reliability_delta", float(delta), attacked_trace_id))
    if not rows:
        return
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO time_series_metrics (id,timestamp,project_id,agent_name,metric_name,metric_value,trace_id)
               VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT (id) DO NOTHING""",
            rows,
        )


async def get_metric_trend(
    metric_name: str,
    project_id:  Optional[str] = "default",
    agent_name:  Optional[str] = None,
    range_days:  int = 7,
    granularity: str = "day",
) -> List[Dict[str, Any]]:
    pool = get_pool()
    cutoff = time.time() - range_days * 86400
    p = _P()
    clauses = [f"metric_name = {p.add(metric_name)}", f"timestamp >= {p.add(cutoff)}"]
    if project_id:
        clauses.append(f"project_id = {p.add(project_id)}")
    if agent_name:
        clauses.append(f"agent_name = {p.add(agent_name)}")
    where = " AND ".join(clauses)

    if granularity == "hour":
        bucket_expr = "to_char(to_timestamp(timestamp), 'YYYY-MM-DD\"T\"HH24:00')"
    else:
        bucket_expr = "to_char(to_timestamp(timestamp), 'YYYY-MM-DD')"

    rows = await pool.fetch(
        f"""SELECT {bucket_expr} AS bucket,
                   AVG(metric_value) AS avg_value,
                   MIN(metric_value) AS min_value,
                   MAX(metric_value) AS max_value,
                   COUNT(*)          AS sample_count
            FROM time_series_metrics
            WHERE {where}
            GROUP BY bucket
            ORDER BY bucket ASC""",
        *p.values,
    )
    return [
        {
            "timestamp":    r["bucket"],
            "value":        round(float(r["avg_value"]), 4),
            "min":          round(float(r["min_value"]), 4),
            "max":          round(float(r["max_value"]), 4),
            "sample_count": int(r["sample_count"]),
        }
        for r in rows
    ]


async def get_metrics_summary(
    project_id:  Optional[str] = "default",
    agent_name:  Optional[str] = None,
    range_days:  int = 7,
) -> Dict[str, Any]:
    pool = get_pool()
    cutoff = time.time() - range_days * 86400
    p = _P()
    clauses = [f"timestamp >= {p.add(cutoff)}"]
    if project_id:
        clauses.append(f"project_id = {p.add(project_id)}")
    if agent_name:
        clauses.append(f"agent_name = {p.add(agent_name)}")
    where = " AND ".join(clauses)

    rows = await pool.fetch(
        f"""SELECT metric_name,
                   AVG(metric_value) AS avg_value,
                   MIN(metric_value) AS min_value,
                   MAX(metric_value) AS max_value,
                   COUNT(*)          AS sample_count
            FROM time_series_metrics
            WHERE {where}
            GROUP BY metric_name""",
        *p.values,
    )
    return {
        r["metric_name"]: {
            "avg":          round(float(r["avg_value"]), 4),
            "min":          round(float(r["min_value"]), 4),
            "max":          round(float(r["max_value"]), 4),
            "sample_count": int(r["sample_count"]),
        }
        for r in rows
    }


async def detect_degradation(
    project_id:  str = "default",
    metric_name: str = "overall_reliability_score",
    recent_n:    int = 5,
    baseline_n:  int = 20,
    threshold:   float = 0.10,
) -> Dict[str, Any]:
    pool = get_pool()
    p = _P()
    rows = await pool.fetch(
        f"""SELECT metric_value, timestamp
            FROM time_series_metrics
            WHERE metric_name = {p.add(metric_name)} AND project_id = {p.add(project_id)}
            ORDER BY timestamp DESC
            LIMIT {p.add(recent_n + baseline_n)}""",
        *p.values,
    )
    values = [float(r["metric_value"]) for r in rows]
    if len(values) < recent_n + 1:
        return {
            "metric": metric_name, "degraded": False,
            "reason": "Insufficient data",
            "recent_avg": None, "baseline_avg": None, "delta": None, "threshold": threshold,
        }

    recent_vals   = values[:recent_n]
    baseline_vals = values[recent_n:recent_n + baseline_n] or values[recent_n:]
    recent_avg    = sum(recent_vals)   / len(recent_vals)
    baseline_avg  = sum(baseline_vals) / len(baseline_vals)
    delta         = recent_avg - baseline_avg
    degraded      = delta < -threshold

    p2 = _P()
    anom_rows = await pool.fetch(
        f"""SELECT AVG(metric_value) AS avg_val
            FROM time_series_metrics
            WHERE metric_name = 'anomaly_count' AND project_id = {p2.add(project_id)}
            ORDER BY timestamp DESC
            LIMIT {p2.add(recent_n)}""",
        *p2.values,
    )
    recent_anomaly_rate = float(anom_rows[0]["avg_val"] or 0) if anom_rows else 0.0

    p3 = _P()
    base_anom = await pool.fetch(
        f"""SELECT AVG(metric_value) AS avg_val
            FROM (
                SELECT metric_value FROM time_series_metrics
                WHERE metric_name = 'anomaly_count' AND project_id = {p3.add(project_id)}
                ORDER BY timestamp DESC
                LIMIT {p3.add(baseline_n)} OFFSET {p3.add(recent_n)}
            ) sub""",
        *p3.values,
    )
    baseline_anomaly_rate = float(base_anom[0]["avg_val"] or 0) if base_anom else 0.0
    anomaly_spike = (
        baseline_anomaly_rate > 0
        and recent_anomaly_rate > baseline_anomaly_rate * 2
    )

    return {
        "metric":                metric_name,
        "degraded":              degraded,
        "anomaly_spike":         anomaly_spike,
        "reason": (
            f"Recent {recent_n}-run avg ({recent_avg:.3f}) is {abs(delta):.3f} below "
            f"baseline {len(baseline_vals)}-run avg ({baseline_avg:.3f})"
            if degraded else "No regression detected"
        ),
        "recent_avg":            round(recent_avg, 4),
        "baseline_avg":          round(baseline_avg, 4),
        "delta":                 round(delta, 4),
        "threshold":             threshold,
        "recent_anomaly_rate":   round(recent_anomaly_rate, 3),
        "baseline_anomaly_rate": round(baseline_anomaly_rate, 3),
    }


# ── Time-series metrics ────────────────────────────────────────────────────

async def get_metrics_timeline(
    project_id: Optional[str] = None,
    hours: int = 24,
    bucket_minutes: int = 60,
) -> Dict[str, Any]:
    """
    Return time-bucketed reliability metrics for Friend 2's trend analysis.

    Buckets traces from the last `hours` hours into `bucket_minutes`-minute
    windows.  Register a ``post_analysis`` hook (core.hooks) to persist
    additional data without modifying this function.
    """
    pool = get_pool()
    since = time.time() - hours * 3600
    bucket_seconds = bucket_minutes * 60

    p = _P()
    clauses: List[str] = [f"t.start_time >= {p.add(since)}"]
    if project_id:
        clauses.append(f"t.project_id = {p.add(project_id)}")
    where = " AND ".join(clauses)

    bucket_expr = f"(t.start_time / {bucket_seconds})::BIGINT * {bucket_seconds}"

    rows = await pool.fetch(
        f"""SELECT
              {bucket_expr}                                                      AS bucket_ts,
              COUNT(DISTINCT t.trace_id)                                        AS trace_count,
              AVG((t.metrics::jsonb->>'overall_reliability_score')::FLOAT)      AS avg_ors,
              COUNT(*) FILTER (WHERE t.success)                                 AS successes,
              SUM(t.error_count)                                                AS total_errors,
              COUNT(DISTINCT a.id)                                              AS anomaly_count
            FROM traces t
            LEFT JOIN anomalies a ON a.trace_id = t.trace_id
            WHERE {where}
            GROUP BY bucket_ts
            ORDER BY bucket_ts ASC""",
        *p.values,
    )

    buckets = []
    for r in rows:
        d = dict(r)
        total = int(d.get("trace_count") or 1)
        buckets.append({
            "timestamp":             int(d["bucket_ts"]),
            "trace_count":           total,
            "avg_reliability_score": round(float(d["avg_ors"] or 0), 3),
            "success_rate":          round(int(d["successes"] or 0) / total * 100, 1),
            "anomaly_count":         int(d["anomaly_count"] or 0),
            "error_count":           int(d["total_errors"] or 0),
        })

    return {
        "project_id":     project_id,
        "hours":          hours,
        "bucket_minutes": bucket_minutes,
        "buckets":        buckets,
    }


# ── Baseline CRUD ──────────────────────────────────────────────────────────

async def compute_and_save_baselines(project_id: str = "default") -> int:
    """
    Compute per-span-name duration baselines from all spans for the project.
    Returns the number of baseline records saved.
    """
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT name, duration_ms FROM spans WHERE project_id = $1 AND duration_ms IS NOT NULL ORDER BY name",
        project_id,
    )

    by_name: Dict[str, List[float]] = {}
    for r in rows:
        by_name.setdefault(r["name"], []).append(float(r["duration_ms"]))

    saved = 0
    async with pool.acquire() as conn:
        for name, values in by_name.items():
            if len(values) < 3:
                continue
            values_sorted = sorted(values)
            n    = len(values_sorted)
            mean = statistics.mean(values)
            std  = statistics.stdev(values) if n > 1 else 0.0
            p50  = values_sorted[int(n * 0.50)]
            p95  = values_sorted[min(int(n * 0.95), n - 1)]
            p99  = values_sorted[min(int(n * 0.99), n - 1)]
            await conn.execute(
                """INSERT INTO baselines
                       (id, project_id, span_name, metric,
                        mean, std, p50, p95, p99, sample_count, computed_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                   ON CONFLICT (project_id, span_name, metric) DO UPDATE SET
                       mean         = EXCLUDED.mean,
                       std          = EXCLUDED.std,
                       p50          = EXCLUDED.p50,
                       p95          = EXCLUDED.p95,
                       p99          = EXCLUDED.p99,
                       sample_count = EXCLUDED.sample_count,
                       computed_at  = EXCLUDED.computed_at""",
                str(uuid.uuid4()), project_id, name, "duration_ms",
                mean, std, p50, p95, p99, n, time.time(),
            )
            saved += 1
    return saved


async def get_baselines(project_id: str = "default") -> Dict[str, Dict[str, float]]:
    pool = get_pool()
    rows = await pool.fetch(
        "SELECT * FROM baselines WHERE project_id = $1", project_id
    )
    result: Dict[str, Dict[str, float]] = {}
    for r in rows:
        d = dict(r)
        result[d["span_name"]] = d
    return result


async def save_domain(domain_name: str, config: Dict[str, Any]) -> None:
    pool = get_pool()
    await pool.execute(
        """INSERT INTO domains (domain_name, config, updated_at)
           VALUES ($1,$2,$3)
           ON CONFLICT (domain_name) DO UPDATE SET
               config = EXCLUDED.config,
               updated_at = EXCLUDED.updated_at""",
        domain_name,
        json.dumps(config),
        time.time(),
    )


async def list_domains() -> List[Dict[str, Any]]:
    pool = get_pool()
    rows = await pool.fetch("SELECT domain_name, config, updated_at FROM domains ORDER BY domain_name ASC")
    return [
        {
            "domain_name": r["domain_name"],
            "config": json.loads(r["config"] or "{}"),
            "updated_at": r.get("updated_at"),
        }
        for r in rows
    ]


# ── Judge results CRUD ──────────────────────────────────────────────────────────

async def save_judge_result(result: Dict[str, Any]) -> None:
    """Upsert an LLM judge result (one row per trace_id)."""
    pool = get_pool()
    await pool.execute(
        """INSERT INTO judge_results
               (id, trace_id, tool_selection, param_correct, faithfulness,
                workflow_order, task_completion, explanation,
                confidence_score, source, judge_backend, model, created_at)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
           ON CONFLICT (trace_id) DO UPDATE SET
               tool_selection   = EXCLUDED.tool_selection,
               param_correct    = EXCLUDED.param_correct,
               faithfulness     = EXCLUDED.faithfulness,
               workflow_order   = EXCLUDED.workflow_order,
               task_completion  = EXCLUDED.task_completion,
               explanation      = EXCLUDED.explanation,
               confidence_score = EXCLUDED.confidence_score,
               source           = EXCLUDED.source,
               judge_backend    = EXCLUDED.judge_backend,
               model            = EXCLUDED.model,
               created_at       = EXCLUDED.created_at""",
        str(uuid.uuid4()),
        result["trace_id"],
        result.get("tool_selection", "PASS"),
        result.get("parameter_correctness", "PASS"),
        result.get("reasoning_faithfulness", "PASS"),
        result.get("workflow_order", "PASS"),
        result.get("task_completion", "PASS"),
        result.get("explanation", ""),
        result.get("confidence_score"),
        result.get("source", "llm"),
        result.get("judge_backend", "rule_based_fallback" if result.get("source") == "rule_based" else "llm"),
        result.get("model"),
        time.time(),
    )


async def get_judge_result(trace_id: str) -> Optional[Dict[str, Any]]:
    """Return the cached LLM judge result for a trace, or None."""
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT * FROM judge_results WHERE trace_id = $1", trace_id
    )
    return dict(row) if row else None


def _row_to_trace(row: Any) -> Trace:
    d = dict(row)
    return Trace(
        trace_id=d["trace_id"],
        project_id=d.get("project_id", "default"),
        session_id=d.get("session_id"),
        task=d["task"],
        scenario=d.get("scenario", "normal"),
        tags=json.loads(d.get("tags") or "[]"),
        start_time=d["start_time"],
        end_time=d.get("end_time"),
        duration_ms=d.get("duration_ms"),
        total_steps=d.get("total_steps", 0),
        tool_call_count=d.get("tool_call_count", 0),
        error_count=d.get("error_count", 0),
        token_usage=json.loads(d.get("token_usage") or "{}"),
        metrics=json.loads(d.get("metrics") or "{}"),
        attack_active=bool(d.get("attack_active", False)),
        attack_type=d.get("attack_type"),
        attack_succeeded=bool(d.get("attack_succeeded", False)),
        completed=bool(d.get("completed", False)),
        success=bool(d.get("success", False)),
        partial_completion=bool(d.get("partial_completion", False)),
        final_summary=d.get("final_summary", ""),
        root_span_id=d.get("root_span_id"),
    )


def _row_to_span(row: Any) -> Span:
    d = dict(row)
    events_raw = json.loads(d.get("events") or "[]")
    events = [SpanEvent(**e) for e in events_raw]
    return Span(
        span_id=d["span_id"],
        trace_id=d["trace_id"],
        parent_span_id=d.get("parent_span_id"),
        kind=SpanKind(d["kind"]),
        name=d["name"],
        start_time=d["start_time"],
        end_time=d.get("end_time"),
        duration_ms=d.get("duration_ms"),
        status=SpanStatus(d["status"]),
        attributes=json.loads(d.get("attributes") or "{}"),
        events=events,
        error_message=d.get("error_message"),
        contains_injection=bool(d.get("contains_injection", False)),
        injection_payload=d.get("injection_payload"),
        service_name=d.get("service_name", "demo-agent"),
        project_id=d.get("project_id", "default"),
        session_id=d.get("session_id"),
        token_usage=json.loads(d.get("token_usage") or "{}"),
    )
