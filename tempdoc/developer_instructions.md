# Detailed Developer Track Instructions

This document provides explicit, step-by-step instructions for each developer based on the master [implementation_plan.md](file:///C:/Users/Yaswanth/.gemini/antigravity/brain/c4d20f5b-e724-4e64-a41e-1f99a37ccb5a/implementation_plan.md). The backend API router split is **already complete** on the base branch, so you can branch off safely.

---

## Developer A: Infrastructure, Storage & Security
**Branch Name Suggestion:** `feature/infra-storage-security`

### 1. Ingest Optimization (MAJOR-1)
*   **Target Files:** [backend/api/ingest.py](file:///d:/Projects/Agent_Reliablity/backend/api/ingest.py), [backend/storage/repository.py](file:///d:/Projects/Agent_Reliablity/backend/storage/repository.py)
*   **Objective:** The current batch ingest `/api/ingest/batch` calls `save_span()` sequentially, creating high write amplification.
*   **Actionable Steps:**
    *   In [backend/storage/repository.py](file:///d:/Projects/Agent_Reliablity/backend/storage/repository.py), implement an `async def save_spans_bulk(trace_id, spans)` function. The function needs to insert all spans in a single `aiosqlite` transaction (`executemany`).
    *   Update [backend/api/ingest.py](file:///d:/Projects/Agent_Reliablity/backend/api/ingest.py) to use `save_spans_bulk` instead of looping through `save_span`.

### 2. SSE Reliability (MAJOR-4)
*   **Target Files:** [backend/storage/repository.py](file:///d:/Projects/Agent_Reliablity/backend/storage/repository.py), [backend/api/traces.py](file:///d:/Projects/Agent_Reliablity/backend/api/traces.py)
*   **Objective:** SSE events (Streaming data) drop on worker restart because they use process-local memory.
*   **Actionable Steps:**
    *   Replace the in-memory buffered event dictionaries in `repository.py` with an external persistent queue (e.g., Redis via `aioredis` or a dedicated persistent SQLite buffer table).
    *   Update the stream timeout and event pulling logic in the `/api/traces/{trace_id}/stream` endpoint to read from the durable data source to properly support `Last-Event-ID`.

### 3. Security Hardening (SECURITY-1, SECURITY-2)
*   **Target Files:** [backend/core/config.py](file:///d:/Projects/Agent_Reliablity/backend/core/config.py), [backend/api/metrics.py](file:///d:/Projects/Agent_Reliablity/backend/api/metrics.py), [backend/api/traces.py](file:///d:/Projects/Agent_Reliablity/backend/api/traces.py)
*   **Objective:** Stop open deployments and stop unthrottled GET requests.
*   **Actionable Steps:**
    *   In `core/config.py`, check `ENVIRONMENT`. If it is `production`, throw an error right at startup if `FLIGHT_RECORDER_API_KEY` is not set. 
    *   In [backend/api/metrics.py](file:///d:/Projects/Agent_Reliablity/backend/api/metrics.py) and [backend/api/traces.py](file:///d:/Projects/Agent_Reliablity/backend/api/traces.py), apply `@limiter.limit(".../minute")` to all the highly expensive GET endpoints (e.g. `/api/metrics/trend`, `/api/traces/compare`).

### 4. Testing Rigor & Cleanup (MAJOR-2, SECURITY-3)
*   **Target Files:** [.gitignore](file:///d:/Projects/Agent_Reliablity/.gitignore), `backend/tests/integration/*`
*   **Actionable Steps:**
    *   Add [pytest_output.txt](file:///d:/Projects/Agent_Reliablity/pytest_output.txt) to the [.gitignore](file:///d:/Projects/Agent_Reliablity/.gitignore) file. Delete the file from Git index `git rm --cached pytest_output.txt`.
    *   In `test_api_endpoints.py`, add explicit failure-path assertions (e.g. asserts for 401 when missing API keys on POST, Rate Limit assertions for the throttler). 

---

## Developer B: Core Engine, Evolution & Adherence
**Branch Name Suggestion:** `feature/redteam-engine-evolution`

### 1. Real-Agent Red-Teaming (CRITICAL-1, MAJOR-3)
*   **Target Files:** [backend/api/redteam.py](file:///d:/Projects/Agent_Reliablity/backend/api/redteam.py), [backend/redteam/engine.py](file:///d:/Projects/Agent_Reliablity/backend/redteam/engine.py)
*   **Objective:** The red team engine always targets `DemoAgent`, which is scripted.
*   **Actionable Steps:**
    *   In `/api/redteam/run` and `run_attack`, modify the request payload to take an `agent_target` parameter (`demo`, `real`, `external`).
    *   Route traffic to `real_agent.execute()` instead of the scripted demo engine if the target is `real`.
    *   When persisting the trace in [run_and_persist()](file:///d:/Projects/Agent_Reliablity/backend/api/utils.py#44-82), append an execution provenance attribute (`trace.source = "real_agent"`) to correctly attribute it in the metrics later.

### 2. Attack Evolution Realism (CRITICAL-2)
*   **Target Files:** [backend/redteam/evolution.py](file:///d:/Projects/Agent_Reliablity/backend/redteam/evolution.py)
*   **Objective:** Evolution tests optimize against placeholder string matching instead of actual model loops.
*   **Actionable Steps:**
    *   In `run_evolution_loop()`, swap the dummy responses out and wire it up to properly execute the agent environment (similar to the logic in `run_attack`).
    *   Change the success fitness parameter: rather than naive string rules, measure behavior divergence against the core instruction constraints directly (using specific rule violations as the score). Persist these parent-child metrics in `save_evolution_result()`.

### 3. Attribute Schema Normalization (QUALITY-2)
*   **Target Files:** [backend/core/models.py](file:///d:/Projects/Agent_Reliablity/backend/core/models.py), [backend/anomaly/detector.py](file:///d:/Projects/Agent_Reliablity/backend/anomaly/detector.py), `backend/evaluation/*`, [backend/tests/conftest.py](file:///d:/Projects/Agent_Reliablity/backend/tests/conftest.py)
*   **Objective:** Trace attributes are fragmented ([tool](file:///d:/Projects/Agent_Reliablity/backend/api/metrics.py#71-81) vs `tool_name`).
*   **Actionable Steps:**
    *   In `core/models.py`, define a `SemanticAttributes` dictionary/enum with fixed keys (e.g. `TOOL_NAME_KEY`, `INPUT_PARAMS_KEY`).
    *   Systematically replace all hardcoded strings (like ` span.attributes.get("tool") `) across tests, detectors, and evaluators to use your new constant variables. 

### 4. Research Checkpoints (Tempdoc Goal #4)
*   **Target Files:** [backend/evaluation/llm_judge.py](file:///d:/Projects/Agent_Reliablity/backend/evaluation/llm_judge.py), [backend/api/traces.py](file:///d:/Projects/Agent_Reliablity/backend/api/traces.py)
*   **Actionable Steps:**
    *   Implement "LLM-as-a-Judge real-time checkpoints" to evaluate "Tool Selection Accuracy". Add a method to trigger `LLMJudgeEngine` specifically on a single `TOOL` span, and add a flag to fire a faux "human-in-the-loop" escalation warning if confidence is extremely low (<0.4).

### 5. Fix Scenario Drift (QUALITY-1)
*   **Target Files:** [backend/agents/demo_agent.py](file:///d:/Projects/Agent_Reliablity/backend/agents/demo_agent.py)
*   **Objective:** `DemoAgent` silently falls back if a scenario is unknown.
*   **Actionable Steps:** Add explicit `HTTPException(422)` failures in `DemoAgent` for unsupported scenarios, or add handlers for the documented missing scenarios (e.g. `goal_hijacking`).

---

## Developer C: Domains, Fuzzing & Frontend Graph
**Branch Name Suggestion:** `feature/domains-fuzzing-ui`

### 1. Robust Starter Domains (CRITICAL-3)
*   **Target Files:** `backend/domains/` (Create this module), `core/config.py`
*   **Objective:** Out-of-the-box domain evaluations are too narrow.
*   **Actionable Steps:**
    *   Define 4 to 6 new, robust starter domains configured statically (e.g. Customer Support FAQ, Coding Repository Maintenance, Operations Triage). 
    *   Define their `optimal_path`, expected tools, and minimum reliability thresholds in code. Wire them into the `DOMAINS` dict in `config.py`.

### 2. Auto-IDPI & Schema Fuzzer (Tempdoc Goal #2 & #3)
*   **Target Files:** `backend/redteam/idpi_fuzzer.py` (New), `backend/redteam/schema_fuzzer.py` (New), [backend/api/redteam.py](file:///d:/Projects/Agent_Reliablity/backend/api/redteam.py)
*   **Objective:** Need automated injection and fuzzing to meet the Agentic Reliability Report requirements.
*   **Actionable Steps:**
    *   Create `idpi_fuzzer.py`: Write an adversarial generation tool that embeds hidden payloads (e.g., zero-pixel fonts, white text). Expose this over a new `api/redteam/generate-idpi` endpoint.
    *   Create `schema_fuzzer.py`: Write a tool that mutates JSON schema tool descriptions intentionally to test an agent's parameter-extraction recovery. Expose over a fuzzing endpoint.

### 3. Frontend Graph & Domain UX (Tempdoc Goal #1)
*   **Target Files:** `frontend-react/src/views/`
*   **Objective:** Bring up the user interface.
*   **Actionable Steps:**
    *   **Graph:** The backend graph builder (`/api/traces/{trace_id}/graph`) already exists. Consume this in the React frontend to visualize execution trajectories (nodes are Agent/Tool/Retriever, edges are logic jumps). 
    *   **Domain Admin:** Build a new "Domain Configurations" UI under Settings that talks to `POST /api/domains` to allow users to visually build and manage domain logic.
