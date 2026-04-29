from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from core.models import IngestRequest as IngestSpanRequest
from core.hooks import hooks
from ingestion.normalizer import normalize_otlp_batch, normalize_sdk_spans
from storage import repository

from api.deps import require_api_key, limiter
from api.utils import ensure_trace_exists

router = APIRouter()

@router.post("/v1/traces", summary="OTLP/HTTP trace receiver")
async def receive_otlp(
    payload: Dict[str, Any],
    project_id: str = Query(default="default"),
    service_name: str = Query(default="external-agent"),
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Accept OpenTelemetry spans in OTLP/JSON format from any agent that has
    configured `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000`.
    """
    try:
        spans = normalize_otlp_batch(
            payload, project_id=project_id, service_name=service_name
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"OTLP parse error: {exc}")

    if not spans:
        return {"accepted": 0}

    # Group spans by trace_id and persist
    by_trace: Dict[str, List] = {}
    for s in spans:
        by_trace.setdefault(s.trace_id, []).append(s)

    for tid, tspans in by_trace.items():
        await ensure_trace_exists(tid, project_id, tspans)
        await repository.save_spans_bulk(tid, tspans)
        await repository.push_event(tid, {"type": "batch_ingest", "count": len(tspans)})

    return {"accepted": len(spans), "traces": list(by_trace)}


@router.post("/api/ingest", summary="SDK span ingest endpoint")
@limiter.limit("60/minute")
async def ingest_spans(
    request: Request,
    req: IngestSpanRequest,
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Simplified ingest for agents using sdk.py.  Accepts raw span dicts,
    normalises them, then stores and triggers analysis.
    """
    try:
        spans = normalize_sdk_spans(
            req.spans,
            trace_id=req.trace_id,
            project_id=req.project_id,
            service_name=req.service_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Normalise error: {exc}")

    await ensure_trace_exists(req.trace_id, req.project_id, spans)
    await repository.save_spans_bulk(req.trace_id, spans)

    # Fire post_ingest hook (Friend 1 real-agent instrumentation plugs in here)
    await hooks.fire(
        "post_ingest", spans=spans, trace_id=req.trace_id, project_id=req.project_id
    )

    return {"accepted": len(spans), "trace_id": req.trace_id}


@router.post("/api/ingest/batch", summary="Batch SDK span ingest endpoint")
@limiter.limit("30/minute")
async def ingest_spans_batch(
    request: Request,
    reqs: List[IngestSpanRequest],
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    """
    Accept multiple trace payloads in a single HTTP call.  Useful for
    high-throughput agents that buffer spans locally and flush in bulk.
    Returns a count of accepted spans and unique trace IDs.
    """
    total_spans = 0
    trace_ids: List[str] = []
    for req in reqs:
        try:
            spans = normalize_sdk_spans(
                req.spans,
                trace_id=req.trace_id,
                project_id=req.project_id,
                service_name=req.service_name,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Normalise error for trace {req.trace_id}: {exc}",
            )
        await ensure_trace_exists(req.trace_id, req.project_id, spans)
        await repository.save_spans_bulk(req.trace_id, spans)
        total_spans += len(spans)
        trace_ids.append(req.trace_id)

    return {
        "accepted": total_spans,
        "traces": len(reqs),
        "trace_ids": trace_ids,
    }
