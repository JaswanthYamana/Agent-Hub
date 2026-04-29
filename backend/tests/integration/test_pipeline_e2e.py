from __future__ import annotations

import os

from fastapi.testclient import TestClient

from main import app


def _auth_headers() -> dict[str, str]:
    api_key = os.getenv("FLIGHT_RECORDER_API_KEY", "")
    return {"X-API-Key": api_key} if api_key else {}


def test_execution_pipeline_end_to_end() -> None:
    with TestClient(app) as client:
        exec_res = client.post(
            "/api/execute",
            json={"task": "Run a hallucination scenario", "scenario": "hallucination"},
            headers=_auth_headers(),
        )
        assert exec_res.status_code == 200
        trace_id = exec_res.json()["trace_id"]

        trace_res = client.get(f"/api/traces/{trace_id}")
        assert trace_res.status_code == 200
        trace_body = trace_res.json()

        assert isinstance(trace_body.get("spans", []), list)
        assert len(trace_body["spans"]) > 0
        assert isinstance(trace_body.get("metrics", {}), dict)
        assert "overall_reliability_score" in trace_body["metrics"]

        anomalies_res = client.get(f"/api/traces/{trace_id}/anomalies")
        assert anomalies_res.status_code == 200
        assert isinstance(anomalies_res.json(), list)

        graph_res = client.get(f"/api/traces/{trace_id}/graph")
        assert graph_res.status_code == 200
        assert "nodes" in graph_res.json()
