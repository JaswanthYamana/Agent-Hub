# Comprehensive Native Testing & Verification Checklist

Based on the deep analysis of the Agentic Reliability Platform (FastAPI Backend, React/Vite Frontend), this comprehensive testing strategy is tailored specifically to your architecture: `aiosqlite` storage, `slowapi` rate limiters, Server-Sent Events (SSE), OpenTelemetry ingestion, LLM-as-a-judge (`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`), and `@xyflow/react` graph execution tracking.

---

## 1. Complete Manual QA Checklist

### A. Core Functionality Verification
- [ ] **Agent Execution Loop**: Trigger a normal run via POST `/api/execute`. Validate that the backend creates a trace, iterates through the agent's tools, and completes gracefully.
- [ ] **Trace Comparison Diffing**: Compare a baseline trace with an attacked trace (`GET /api/traces/compare`). Ensure the AI explanation correlates with divergence in the execution graph.
- [ ] **Red Team Evolution**: Start an attack evolution using `POST /api/redteam/evolution/start`. Wait for generations to complete and verify the success rate curve metrics.
- [ ] **Baseline Computations**: Trigger `POST /api/baselines/compute` and assert it retrieves past spans and calculates proper p50/p95/p99 duration metrics.

### B. Input Validation and Error Handling
- [ ] **Invalid OTLP Payloads**: Send malformed JSON to `POST /v1/traces`. Confirm it returns a clear `422 Unprocessable Entity` without crashing the server.
- [ ] **Missing Environment Keys (LLM Judge)**: Remove `OPENAI_API_KEY` and trigger `/api/traces/{id}/judge`. Assert it safely throws a `400 Bad Request: LLM judge requires OPENAI_API_KEY` or falls back gracefully to the rule-based engine.
- [ ] **Invalid Granularity**: Query `/api/metrics/trend?granularity=yearly`. Confirm it raises an error explicitly stating valid choices (`day | hour`).

### C. Authentication and Authorization
- [ ] **Production Lock-out**: Turn on `ENVIRONMENT=production`. Confirm the backend explicitly crashes on boot if `FLIGHT_RECORDER_API_KEY` is not provided.
- [ ] **API Key Enforcement**: Send a `POST` request to `/api/execute` without `X-API-Key` in the headers. Confirm it fails with `401 Unauthorized`.
- [ ] **Public Read-Only Access**: Verify that GET requests like `/api/dashboard` and `/api/traces` function normally *without* the `X-API-Key` header (as by design).

### D. API Endpoints and Integrations (SSE & Graphs)
- [ ] **SSE Connection Persistence**: Connect to `/api/traces/{trace_id}/stream`. Ensure it receives `batch_ingest` and `done` events. 
- [ ] **SSE Reconnection (`Last-Event-ID`)**: Force close the SSE connection midway. Reconnect passing `Last-Event-ID: 5`. Confirm it correctly replays stored events starting from ID 6 using the updated `sse_events` database table.
- [ ] **Graph (DAG) Construction**: Navigate to the trace breakdown UI. Verify that `@xyflow/react` correctly renders nodes (tools/agents) and edges (control flow) from the `/api/traces/{trace_id}/graph` backend.

### E. Database Operations and Data Integrity
- [ ] **Ingest Write Amplification (Bulk Insert check)**: Send a batch of 50 OpenTelemetry spans via POST `/api/ingest/batch`. Ensure [save_spans_bulk](file:///d:/Projects/Agent_Reliablity/backend/storage/repository.py#276-315) inserts them instantly rather than blocking the async loop.
- [ ] **Foreign Key Constraints**: Attempt to insert a span or anomaly linking to a non-existent `trace_id`. Confirm the SQLite `PRAGMA foreign_keys = ON;` rejects the insertion.
- [ ] **State Resilience on Restart**: Terminate the FastAPI application (`Ctrl+C`). Start it again. Ensure traces, domains, and metrics queries immediately resolve accurately.

### F. Security Vulnerabilities and Best Practices
- [ ] **Rate Limiting (slowapi)**: Hit `/api/traces` (List traces) over 60 times in 1 minute. Confirm the API returns a `429 Too Many Requests` response. Check `frontend-react` handles this 429 gracefully rather than blanking the screen.
- [ ] **CORS Integrity**: Change the `ALLOWED_ORIGIN` environment variable to a rogue domain. Verify the browser blocks the React application's preflight `OPTIONS` requests.

### G. Performance & Load Considerations
- [ ] **Metrics Dashboard Saturation**: Run the platform until you have >1,000 traces in the database. Open the Dashboard. Verify that `GET /api/dashboard` and time-series aggregations (recharts visualizations) load in <300ms.
- [ ] **Pass@K Concurrency Benchmark**: Fire `POST /api/passk` with `k=15`. Ensure the fast API server processes the 15 simulated agent runs concurrently without deadlocking the SQLite single writer thread (via `aiosqlite` connection pool).

---

## 2. Specific Test Cases & Verification Steps

**Test Case: IDPI (Indirect Prompt Injection) Fuzzing**
*   **Action:** Execute `POST /api/redteam/run` with `attack_type: "idpi"` and target scenario `flight_booking`.
*   **Verification Step 1:** Wait for trace execution to finish.
*   **Verification Step 2:** Check `/api/traces/{id}/anomalies`. It must contain an anomaly with `type="injection_detected"` and `severity="critical"`.
*   **Verification Step 3:** View the trace on the React frontend. Ensure the "Threat Detected" banner activates.

**Test Case: Live Stream Recovery**
*   **Action:** Trigger a background agent execution that takes > 10 seconds.
*   **Verification Step 1:** Curl the SSE endpoint: `curl -N http://localhost:8000/api/traces/{id}/stream`.
*   **Verification Step 2:** Kill the curl request after 3 seconds.
*   **Verification Step 3:** Curl again with header `Last-Event-ID: 2`. Notice `id: 3`, `id: 4` rapidly stream out from the SQLite `sse_events` persistent table, seamlessly resuming state.

**Test Case: Dashboard Time-series Rendering**
*   **Action:** Execute `GET /api/metrics/all_trends`.
*   **Verification Step 1:** Payload MUST return arrays containing `{timestamp: "...", value: X, ...}`.
*   **Verification Step 2:** On the frontend, verify the Recharts `LineChart` and `BarChart` components correctly parse the string timestamps and plot the trajectories for metrics like `overall_reliability_score`.

---

## 3. Automation Tasks to Add to Your Codebase

To mature this project, I strongly recommend implementing the following automation files. You can copy/paste these ideas into your backlogs or CI structure:

1.  **Synthetic Ping Script (`backend/scripts/ping_agent.py`)** 
    *   *Purpose*: A lightweight chron-job Python script executing `requests.post("/api/execute")` every 15 minutes. This creates a perpetual hum of data, driving the metrics dashboards.
2.  **Health-check Standard (`backend/api/health.py`)**
    *   *Purpose*: Enhance the current simple `/health` endpoint to attempt a quick `SELECT 1` from the SQLite database and check LLM connectivity via a lightweight dummy prompt. Useful for Docker/K8s liveness probes.
3.  **Frontend State Validator Utilities (`frontend-react/src/utils/debug.js`)**
    *   *Purpose*: Expose a `window.__ZUSTAND_STORE__` logger in development mode so developers can view the current selected trace, node state, and timeline state without React dev tools.
4.  **Database Seeder (`backend/scripts/seed_db.py`)**
    *   *Purpose*: Currently, a blank DB looks empty on the dashboard. Add a script that generates 100 fake traces, baseline spans, and anomalies to test UI pagination and graph edge-cases easily.

---

## 4. Project-Specific Architectural Recommendations

Based on the libraries currently running in your environment:

1.  **SQLite WAL Checkpointing**: You are using `aiosqlite` with `PRAGMA journal_mode = WAL;`. With heavy bulk insertions ([save_spans_bulk](file:///d:/Projects/Agent_Reliablity/backend/storage/repository.py#276-315)), the [-wal](file:///d:/Projects/Agent_Reliablity/backend/flight_recorder.db-wal) file can grow indefinitely. **Recommendation**: Implement a tiny background lifespan task in [main.py](file:///d:/Projects/Agent_Reliablity/backend/main.py) that runs `PRAGMA wal_checkpoint(TRUNCATE);` every 12 hours.
2.  **SSE Reverse Proxy Buffering**: Server-Sent Events over FastAPI/Starlette often get broken when deployed behind NGINX if proxy buffering is on. **Recommendation**: When you move to production, ensure your NGINX config has `proxy_buffering off;` and `proxy_read_timeout 86400;` on the `/api/traces/*/stream` path.
3.  **React Flow DAG Rendering**: `@xyflow/react` can become laggy if an agent executes hundreds of loops (e.g., `reasoning_loop` anomalies). **Recommendation**: Use React Flow's `useNodesInitialized` hook to defer rendering edges until nodes are sized, or conditionally flatten long recursive loops into single expandable "Loop Groups".
4.  **Zustand Persistence**: Since the user might be analyzing a trace and accidentally refresh the dashboard, the currently selected `traceId` will vanish from memory. **Recommendation**: use [persist](file:///d:/Projects/Agent_Reliablity/backend/api/utils.py#44-82) middleware from `zustand/middleware` bound to `sessionStorage` for the active trace ID so that page reloads don't disrupt the user's workflow.
