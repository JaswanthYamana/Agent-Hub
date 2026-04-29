import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Request

from storage import repository
from api.deps import require_api_key, limiter

router = APIRouter()

_VALID_METRICS = {
    "overall_reliability_score",
    "tool_selection_accuracy",
    "parameter_correctness",
    "task_completion_rate",
    "workflow_correctness",
    "anomaly_count",
    "hallucination_rate",
    "error_rate",
    "attack_success_rate",
    "reliability_delta",
}

@router.get("/api/metrics/trend", summary="Time-series trend for a single metric")
@limiter.limit("60/minute")
async def get_metric_trend(
    request: Request,
    metric:      str           = Query(..., description="Metric name, e.g. overall_reliability_score"),
    range:       int           = Query(default=7,  ge=1, le=90, description="Days of history"),
    granularity: str           = Query(default="day", description="day | hour"),
    project_id:  Optional[str] = Query(default="default"),
    agent_name:  Optional[str] = Query(default=None),
) -> List[Dict[str, Any]]:
    if metric not in _VALID_METRICS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown metric '{metric}'. Valid metrics: {sorted(_VALID_METRICS)}",
        )
    if granularity not in ("day", "hour"):
        raise HTTPException(status_code=400, detail="granularity must be 'day' or 'hour'")
    return await repository.get_metric_trend(
        metric_name=metric,
        project_id=project_id,
        agent_name=agent_name,
        range_days=range,
        granularity=granularity,
    )


@router.get("/api/metrics/reliability_trend", summary="ORS trend (convenience alias)")
@limiter.limit("60/minute")
async def get_reliability_trend(
    request: Request,
    range:       int           = Query(default=7, ge=1, le=90),
    granularity: str           = Query(default="day"),
    project_id:  Optional[str] = Query(default="default"),
) -> List[Dict[str, Any]]:
    return await repository.get_metric_trend(
        "overall_reliability_score", project_id=project_id,
        range_days=range, granularity=granularity,
    )


@router.get("/api/metrics/anomaly_trend", summary="Anomaly count trend")
@limiter.limit("60/minute")
async def get_anomaly_trend(
    request: Request,
    range:       int           = Query(default=7, ge=1, le=90),
    granularity: str           = Query(default="day"),
    project_id:  Optional[str] = Query(default="default"),
) -> List[Dict[str, Any]]:
    return await repository.get_metric_trend(
        "anomaly_count", project_id=project_id,
        range_days=range, granularity=granularity,
    )


@router.get("/api/metrics/tool_accuracy", summary="Tool Selection Accuracy trend")
@limiter.limit("60/minute")
async def get_tool_accuracy_trend(
    request: Request,
    range:       int           = Query(default=7, ge=1, le=90),
    granularity: str           = Query(default="day"),
    project_id:  Optional[str] = Query(default="default"),
) -> List[Dict[str, Any]]:
    return await repository.get_metric_trend(
        "tool_selection_accuracy", project_id=project_id,
        range_days=range, granularity=granularity,
    )


@router.get("/api/metrics/attack_success_rate", summary="Attack Success Rate trend")
@limiter.limit("60/minute")
async def get_asr_trend(
    request: Request,
    range:       int           = Query(default=7, ge=1, le=90),
    granularity: str           = Query(default="day"),
    project_id:  Optional[str] = Query(default="default"),
) -> List[Dict[str, Any]]:
    return await repository.get_metric_trend(
        "attack_success_rate", project_id=project_id,
        range_days=range, granularity=granularity,
    )


@router.get("/api/metrics/summary", summary="Summary stats for all tracked metrics")
@limiter.limit("60/minute")
async def get_metrics_summary(
    request: Request,
    range:       int           = Query(default=7, ge=1, le=90),
    project_id:  Optional[str] = Query(default="default"),
    agent_name:  Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    return await repository.get_metrics_summary(
        project_id=project_id, agent_name=agent_name, range_days=range,
    )


@router.get("/api/metrics/degradation", summary="Reliability regression / degradation report")
@limiter.limit("30/minute")
async def get_degradation_report(
    request: Request,
    metric:     str           = Query(default="overall_reliability_score"),
    recent_n:   int           = Query(default=5,  ge=2, le=20),
    baseline_n: int           = Query(default=20, ge=5, le=100),
    threshold:  float         = Query(default=0.10, ge=0.01, le=0.5),
    project_id: Optional[str] = Query(default="default"),
) -> Dict[str, Any]:
    return await repository.detect_degradation(
        project_id=project_id,
        metric_name=metric,
        recent_n=recent_n,
        baseline_n=baseline_n,
        threshold=threshold,
    )


@router.get("/api/metrics/all_trends", summary="All key metric trends in one request")
@limiter.limit("20/minute")
async def get_all_trends(
    request: Request,
    range:       int           = Query(default=7, ge=1, le=90),
    granularity: str           = Query(default="day"),
    project_id:  Optional[str] = Query(default="default"),
) -> Dict[str, List[Dict[str, Any]]]:
    metrics_to_fetch = [
        "overall_reliability_score",
        "tool_selection_accuracy",
        "parameter_correctness",
        "task_completion_rate",
        "anomaly_count",
        "attack_success_rate",
        "reliability_delta",
    ]
    results = await asyncio.gather(*[
        repository.get_metric_trend(
            m, project_id=project_id, range_days=range, granularity=granularity
        )
        for m in metrics_to_fetch
    ])
    return dict(zip(metrics_to_fetch, results))


@router.get("/api/metrics/timeline", summary="Reliability metrics trend over time")
@limiter.limit("30/minute")
async def get_metrics_timeline(
    request: Request,
    project_id: Optional[str] = Query(default=None),
    hours: int = Query(default=24, ge=1, le=168),
    bucket_minutes: int = Query(default=60, ge=5, le=1440),
) -> Dict[str, Any]:
    return await repository.get_metrics_timeline(
        project_id=project_id,
        hours=hours,
        bucket_minutes=bucket_minutes,
    )

@router.post(
    "/api/baselines/compute", summary="Compute statistical baselines from DB history"
)
async def compute_baselines(
    project_id: str = Query(default="default"),
    _auth: None = Depends(require_api_key),
) -> Dict[str, Any]:
    count = await repository.compute_and_save_baselines(project_id)
    return {"status": "ok", "updated_baselines": count, "project_id": project_id}


@router.get("/api/baselines", summary="Current baselines")
async def get_baselines(project_id: str = Query(default="default")) -> Dict[str, Any]:
    return await repository.get_baselines(project_id)


@router.get("/api/dashboard", summary="Aggregate platform statistics")
@limiter.limit("30/minute")
async def get_dashboard(
    request: Request,
    project_id: Optional[str] = Query(default=None),
) -> Dict[str, Any]:
    return await repository.get_dashboard_stats(project_id)
