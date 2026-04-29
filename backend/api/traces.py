import asyncio
import json
import time
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request  # type: ignore
from fastapi.responses import StreamingResponse  # type: ignore

from core.config import get_llm_provider  # type: ignore
from core.models import SemanticAttributes, PassKRequest, TaskRequest, Trace  # type: ignore
from evaluation.judge import build_evaluation_report  # type: ignore
from evaluation.metrics import compute_pass_k  # type: ignore
from storage import repository  # type: ignore
from replay.engine import capture as capture_replay  # type: ignore
from replay.engine import diff_manifests, manifest_to_dict  # type: ignore

from api.deps import require_api_key, limiter, graph, metrics  # type: ignore
from api.utils import run_and_persist  # type: ignore

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/api/traces", summary="List traces")
@limiter.limit("60/minute")
async def list_traces(
    request: Request,
    project_id: Optional[str] = Query(default=None),
    scenario: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> List[Dict[str, Any]]:
    traces = await repository.list_traces(
        project_id=project_id, scenario=scenario, limit=limit, offset=offset
    )
    return [t.model_dump(mode="json", exclude={"spans"}) for t in traces]


@router.get("/api/traces/compare", summary="Graph-based trace comparison with AI explanation")
@limiter.limit("20/minute")
async def compare_traces_endpoint(
    request: Request,
    traceA: str = Query(..., description="Baseline trace ID"),
    traceB: str = Query(..., description="Attacked/comparison trace ID"),
) -> Dict[str, Any]:
    from explain.divergence import generate_divergence_explanation  # type: ignore
    from replay.engine import compare_traces as graph_compare_traces  # type: ignore

    ta = await repository.get_trace(traceA, include_spans=True)
    tb = await repository.get_trace(traceB, include_spans=True)
    if ta is None:
        raise HTTPException(status_code=404, detail=f"Trace '{traceA}' not found")
    if tb is None:
        raise HTTPException(status_code=404, detail=f"Trace '{traceB}' not found")

    assert ta is not None
    assert tb is not None

    comparison = graph_compare_traces(ta, tb)
    graph_a = graph.build(ta.trace_id, ta.spans)
    graph_b = graph.build(tb.trace_id, tb.spans)
    graph_diff = graph.diff_graphs(graph_a, graph_b)

    comparison["graph_diff"] = graph_diff
    
    from analysis.trace_diff import compare_traces as sequence_compare  # type: ignore
    seq_diff = sequence_compare(ta, tb)
    comparison["divergence"] = seq_diff
    
    task_desc = ta.task or tb.task or ""
    explanation = generate_divergence_explanation(comparison, task_description=task_desc)
    comparison["explanation"] = explanation

    def _trace_meta(t: "Trace") -> Dict[str, Any]:
        return {
            "trace_id":    t.trace_id,
            "task":        t.task,
            "scenario":    t.scenario,
            "total_steps": t.total_steps,
            "success":     t.success,
            "steps": [
                {
                    "step":   i,
                    "name":   s.name,
                    "kind":   s.kind.value,
                    "status": s.status.value,
                    "duration_ms": s.duration_ms,
                    "tool":   s.attributes.get(SemanticAttributes.TOOL_NAME, s.name),
                }
                for i, s in enumerate(t.spans)
            ],
        }

    comparison["trace_a"] = _trace_meta(ta)
    comparison["trace_b"] = _trace_meta(tb)

    return comparison


@router.post("/api/traces/{trace_id}/evaluate-span")
async def evaluate_span_endpoint(trace_id: str, span_id: str = Query(...)) -> Dict[str, Any]:
    trace = await repository.get_trace(trace_id, include_spans=True)
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found")
    
    assert trace is not None
        
    target_span = next((s for s in trace.spans if s.span_id == span_id), None)
    if not target_span:
        raise HTTPException(status_code=404, detail="Span not found in trace")
        
    from evaluation.llm_judge import LLMJudgeEngine  # type: ignore
    judge = LLMJudgeEngine()
    result = await judge.evaluate_span(target_span, trace)
    
    # Save the updated trace to persist potentially added 'human_review_required' flag
    if result.get("confidence", 1.0) < 0.4:
        await repository.save_trace(trace)
        
    return result


@router.get("/api/traces/{trace_id}", summary="Get full trace with spans")
@limiter.limit("120/minute")
async def get_trace(request: Request, trace_id: str) -> Dict[str, Any]:
    trace = await repository.get_trace(trace_id, include_spans=True)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    assert trace is not None
    return trace.model_dump(mode="json")


@router.get("/api/traces/{trace_id}/risk", summary="Get trace risk score")
async def get_trace_risk(trace_id: str) -> Dict[str, Any]:
    trace = await repository.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
        
    assert trace is not None
    return {
        "trace_id": trace.trace_id,
        "risk_score": trace.risk_score,
        "risk_level": trace.risk_level
    }


@router.get("/api/traces/{trace_id}/stream", summary="SSE live span stream")
async def stream_trace(
    trace_id: str,
    last_event_id: Optional[str] = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    repository.create_queue(trace_id)

    async def _gen() -> AsyncGenerator[str, None]:
        timeout_at = time.time() + 60
        replay_after = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0

        buffered = repository.get_buffered_events(trace_id, after_event_id=replay_after)
        for event in buffered:
            event_id = int(event.get("_event_id", 0))
            payload = {k: v for k, v in event.items() if k != "_event_id"}
            yield f"id: {event_id}\ndata: {json.dumps(payload)}\n\n"

        try:
            while time.time() < timeout_at:
                event = await repository.pop_event(trace_id, timeout=0.5)
                if event is not None:
                    event_id = int(event.get("_event_id", 0))
                    payload = {k: v for k, v in event.items() if k != "_event_id"}
                    yield f"id: {event_id}\ndata: {json.dumps(payload)}\n\n"
                    if payload.get("type") == "done":
                        break
                else:
                    yield ": heartbeat\n\n"
        finally:
            repository.release_queue(trace_id)

    return StreamingResponse(_gen(), media_type="text/event-stream")


@router.get("/api/traces/{trace_id}/evaluate", summary="Evaluate a trace")
@limiter.limit("30/minute")
async def evaluate_trace(
    request: Request,
    trace_id: str,
    k: Optional[int] = Query(default=None, ge=2, le=20),
) -> Dict[str, Any]:
    if get_llm_provider() == "none":
        raise HTTPException(
            status_code=400,
            detail="LLM judge requires OPENAI_API_KEY.",
        )

    trace = await repository.get_trace(trace_id, include_spans=True)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    
    assert trace is not None
    trace_metrics = metrics.compute(trace)

    pass_k_value: Optional[float] = None
    if k and k >= 2:
        extra_tasks = [
            run_and_persist(
                TaskRequest(
                    task=trace.task,
                    scenario=trace.scenario,
                    project_id=trace.project_id,
                )
            )
            for _ in range(k - 1)
        ]
        extra_traces = await asyncio.gather(*extra_tasks)
        all_traces = [trace] + list(extra_traces)
        pass_k_value = compute_pass_k(all_traces)

    report = await build_evaluation_report(trace, trace_metrics, pass_k=pass_k_value)
    return report.model_dump(mode="json")


@router.post("/api/passk", summary="Pass@k consistency benchmark")
@limiter.limit("15/minute")
async def run_pass_k(
    request: Request,
    passk_request: PassKRequest,
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    tasks = [
        run_and_persist(
            TaskRequest(
                task=passk_request.task,
                scenario=passk_request.scenario,
                project_id=passk_request.project_id,
            )
        )
        for _ in range(passk_request.k)
    ]
    traces = await asyncio.gather(*tasks)
    pass_k = compute_pass_k(list(traces))
    scores = [t.metrics.get("overall_reliability_score", 0) for t in traces]
    avg_s = sum(scores) / len(scores) if scores else 0
    std_s = (
        (sum((s - avg_s) ** 2 for s in scores) / len(scores)) ** 0.5 if scores else 0
    )
    return {
        "task": passk_request.task,
        "k": passk_request.k,
        "pass_k": round(float(pass_k), 3),  # type: ignore
        "successes": sum(1 for t in traces if t.success),
        "avg_score": round(avg_s, 3),  # type: ignore
        "score_std": round(std_s, 4),  # type: ignore
        "trace_ids": [t.trace_id for t in traces],
    }


@router.get("/api/traces/{trace_id}/graph", summary="Execution graph (DAG)")
@limiter.limit("60/minute")
async def get_trace_graph(request: Request, trace_id: str) -> Dict[str, Any]:
    trace = await repository.get_trace(trace_id, include_spans=True)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    assert trace is not None
    trace_graph = graph.build(trace_id, trace.spans)
    return trace_graph.model_dump(mode="json")


@router.get("/api/traces/{trace_id}/judge", summary="LLM-based judge evaluation")
@limiter.limit("20/minute")
async def get_judge_results(request: Request, trace_id: str) -> Dict[str, Any]:
    from evaluation.llm_judge import LLMJudgeEngine, _dict_to_result  # type: ignore

    if get_llm_provider() == "none":
        raise HTTPException(
            status_code=400,
            detail="LLM judge requires OPENAI_API_KEY.",
        )

    cached = await repository.get_judge_result(trace_id)
    if cached:
        return {"trace_id": trace_id, "judge_result": _dict_to_result(cached, trace_id).model_dump(mode="json"), "cached": True}

    trace = await repository.get_trace(trace_id, include_spans=True)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    
    assert trace is not None
    try:
        engine = LLMJudgeEngine()
        result = await engine.evaluate(trace)
        return {"trace_id": trace_id, "judge_result": result.model_dump(mode="json"), "cached": False}
    except Exception as exc:
        logger.exception("Judge endpoint failed for trace %s", trace_id)
        raise HTTPException(status_code=500, detail=f"Judge evaluation failed: {exc}") from exc


@router.get("/api/anomalies", summary="List anomalies")
@limiter.limit("60/minute")
async def list_anomalies(
    request: Request,
    project_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> List[Dict[str, Any]]:
    return await repository.list_anomalies(project_id=project_id, severity=severity, limit=limit, offset=offset)


@router.get("/api/traces/{trace_id}/anomalies", summary="Anomalies for a specific trace")
@limiter.limit("120/minute")
async def trace_anomalies(request: Request, trace_id: str) -> List[Dict[str, Any]]:
    return await repository.list_anomalies(trace_id=trace_id)


@router.get("/api/traces/{trace_id}/replay", summary="Full replay manifest")
@limiter.limit("60/minute")
async def get_replay(request: Request, trace_id: str) -> Dict[str, Any]:
    trace = await repository.get_trace(trace_id, include_spans=True)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    assert trace is not None
    manifest = capture_replay(trace)
    return manifest_to_dict(manifest)


@router.get("/api/traces/{trace_id}/replay/{step}", summary="Single replay frame")
@limiter.limit("120/minute")
async def get_replay_frame(request: Request, trace_id: str, step: int) -> Dict[str, Any]:
    trace = await repository.get_trace(trace_id, include_spans=True)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")
    assert trace is not None
    manifest = capture_replay(trace)
    frame = manifest.frames[step] if 0 <= step < len(manifest.frames) else None
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Step {step} out of range")
    from dataclasses import asdict
    return asdict(frame)


@router.get("/api/replay/compare", summary="Diff two replay manifests")
@limiter.limit("30/minute")
async def compare_replays(
    request: Request,
    baseline_id: str = Query(...),
    attacked_id: str = Query(...),
) -> Dict[str, Any]:
    bt = await repository.get_trace(baseline_id, include_spans=True)
    at = await repository.get_trace(attacked_id, include_spans=True)
    if bt is None or at is None:
        raise HTTPException(status_code=404, detail="One or both traces not found")
    assert bt is not None
    assert at is not None
    bm = capture_replay(bt)
    am = capture_replay(at)
    diff = diff_manifests(bm, am)
    from dataclasses import asdict
    return asdict(diff)
