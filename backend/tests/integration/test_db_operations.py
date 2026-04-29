from __future__ import annotations

import asyncio
import os

from fastapi.testclient import TestClient

from main import app
from storage import repository


def _auth_headers() -> dict[str, str]:
    api_key = os.getenv("FLIGHT_RECORDER_API_KEY", "")
    return {"X-API-Key": api_key} if api_key else {}


def test_trace_span_anomaly_persistence() -> None:
    with TestClient(app) as client:
        exec_res = client.post(
            "/api/execute",
            json={"task": "Trigger an error path", "scenario": "tool_error"},
            headers=_auth_headers(),
        )
        assert exec_res.status_code == 200
        trace_id = exec_res.json()["trace_id"]

        trace_api = client.get(f"/api/traces/{trace_id}")
        assert trace_api.status_code == 200
        trace_body = trace_api.json()
        assert trace_body["trace_id"] == trace_id
        assert isinstance(trace_body.get("spans", []), list)
        assert len(trace_body["spans"]) > 0

        anomalies_res = client.get(f"/api/traces/{trace_id}/anomalies")
        assert anomalies_res.status_code == 200
        anomalies = anomalies_res.json()
        assert isinstance(anomalies, list)
