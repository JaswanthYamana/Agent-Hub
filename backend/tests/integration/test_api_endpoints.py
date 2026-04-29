from __future__ import annotations

import os

from fastapi.testclient import TestClient

from main import app


def _auth_headers() -> dict[str, str]:
    api_key = os.getenv("FLIGHT_RECORDER_API_KEY", "")
    return {"X-API-Key": api_key} if api_key else {}


def test_core_api_endpoints() -> None:
    with TestClient(app) as client:
        exec_res = client.post(
            "/api/execute",
            json={"task": "Book a flight from NYC to LAX", "scenario": "normal"},
            headers=_auth_headers(),
        )
        assert exec_res.status_code == 200
        trace_id = exec_res.json().get("trace_id")
        assert trace_id

        traces_res = client.get("/api/traces", params={"limit": 10})
        assert traces_res.status_code == 200
        assert isinstance(traces_res.json(), list)

        redteam_res = client.post(
            "/api/redteam/run",
            json={"attack_type": "idpi", "target_scenario": "normal", "intensity": "low"},
            headers=_auth_headers(),
        )
        assert redteam_res.status_code == 200
        redteam_body = redteam_res.json()
        assert "attack_success_rate" in redteam_body
        assert "baseline_trace_id" in redteam_body

        metrics_res = client.get("/api/metrics/summary")
        assert metrics_res.status_code == 200
        assert isinstance(metrics_res.json(), dict)

def test_api_auth_failure() -> None:
    # Ensure auth is enabled for this test
    import core.config
    original_api_key = core.config.API_KEY
    original_enable_auth = core.config.ENABLE_AUTH

    core.config.API_KEY = "test-key"
    core.config.ENABLE_AUTH = True
    
    try:
        with TestClient(app) as client:
            # POST without auth should fail
            exec_res = client.post(
                "/api/execute",
                json={"task": "Book a flight from NYC to LAX", "scenario": "normal"},
            )
            assert exec_res.status_code == 401
    finally:
        core.config.API_KEY = original_api_key
        core.config.ENABLE_AUTH = original_enable_auth

def test_api_rate_limiting() -> None:
    # Mocking the rate limiter for a quick check.
    # We call a limited endpoint multiple times to trigger a 429.
    with TestClient(app) as client:
        # call the /api/metrics/trend endpoint 61 times (limit is 60/minute)
        for _ in range(61):
            res = client.get("/api/metrics/trend?metric=overall_reliability_score")
            if res.status_code == 429:
                break
        
        assert res.status_code == 429
