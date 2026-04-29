import time
import logging
from typing import List

from core.models import Span, Trace, SpanStatus, TaskRequest
from core.hooks import hooks
from storage import repository
from api.deps import agent, detector, metrics

logger = logging.getLogger(__name__)

async def ensure_trace_exists(trace_id: str, project_id: str, spans: List[Span]) -> None:
    """Ensure a Trace record exists before saving spans to satisfy FOREIGN KEY."""
    existing = await repository.get_trace(trace_id, include_spans=False)
    if existing:
        return
    
    start_time = min((s.start_time for s in spans), default=time.time())
    end_times = [s.end_time for s in spans if s.end_time is not None]
    end_time = max(end_times) if end_times else None
    duration_ms = (end_time - start_time) * 1000 if end_time else None
    
    total_prompt = sum((s.token_usage.get("prompt_tokens", 0) for s in spans))
    total_comp = sum((s.token_usage.get("completion_tokens", 0) for s in spans))
    token_usage = {}
    if total_prompt or total_comp:
        token_usage = {"prompt_tokens": total_prompt, "completion_tokens": total_comp, "total_tokens": total_prompt + total_comp}

    t = Trace(
        trace_id=trace_id,
        project_id=project_id,
        task="External Agent Task",
        scenario="normal",
        start_time=start_time,
        end_time=end_time,
        duration_ms=duration_ms,
        total_steps=len(spans),
        completed=bool(end_time),
        success=all(s.status == SpanStatus.OK for s in spans) if spans else False,
        token_usage=token_usage,
    )
    await repository.save_trace(t)

async def run_and_persist(request: TaskRequest, agent_target: str = "demo") -> Trace:
    """Execute the specified agent, run analysis, persist everything."""
    if agent_target == "real":
        from api.deps import real_agent
        trace = await real_agent.execute(request)
    else:
        trace = await agent.execute(request)
        
    trace.source = "real_agent" if agent_target == "real" else "demo_agent"
    
    baselines = await repository.get_baselines(request.project_id)

    # Anomaly detection (pattern + statistical)
    anomalies = detector.detect(trace, baselines=baselines)
    trace.anomalies = anomalies

    from evaluation.risk_engine import compute_risk
    risk_data = compute_risk(trace)
    trace.risk_score = risk_data["risk_score"]
    trace.risk_level = risk_data["risk_level"]

    # Reliability metrics
    trace.metrics = metrics.compute(trace)

    # Emit time-series metric rows for trend analysis
    await repository.emit_trace_metrics(trace)

    # Fire post_analysis hook (Friend 2 time-series tracking plugs in here)
    await hooks.fire("post_analysis", trace=trace)

    # Persist — guaranteed to push SSE done even on DB failure
    try:
        await repository.save_trace_bundle(trace, anomalies)
    except Exception:
        logger.exception("Failed to persist trace %s", trace.trace_id)
    finally:
        # Always broadcast so SSE consumers don’t hang
        for span in trace.spans:
            await repository.push_event(trace.trace_id, span.model_dump(mode="json"))
        await repository.push_event(
            trace.trace_id,
            {
                "type": "done",
                "trace_id": trace.trace_id,
                "success": trace.success,
                "anomaly_count": len(trace.anomalies),
            },
        )

    return trace
