<div align="center">

<h1>🛫 Agent Hub</h1>
<h3>AI Agent Reliability & Red-Teaming Observability Platform</h3>

<p>
  <a href="#-overview">Overview</a> •
  <a href="#-key-features">Features</a> •
  <a href="#-architecture">Architecture</a> •
  <a href="#-quick-start">Quick Start</a> •
  <a href="#-api-reference">API</a> •
  <a href="#-scenarios--demos">Demos</a> •
  <a href="#-integrations">Integrations</a> •
  <a href="#-research-foundation">Research</a>
</p>

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![OpenTelemetry](https://img.shields.io/badge/OpenTelemetry-compatible-f5a623?logo=opentelemetry&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

---

## 🔭 Overview

**Agent Hub** is a full-stack observability and adversarial testing platform for autonomous AI agents. It functions as a **black-box + white-box flight recorder and testing laboratory**: every reasoning step, tool call, parameter, and intermediate decision is captured as an OpenTelemetry-compatible span, visualised as an interactive execution DAG, and evaluated through a multi-dimensional reliability scoring engine.

### The Core Thesis

> *An AI agent can produce a correct-looking final answer while its execution trajectory is silently broken, dangerous, or adversarially compromised. Output-level validators cannot see this — Agent Hub can.*

Traditional LLM evaluation measures what the agent *says*. Agent Hub measures what the agent *does* — every tool call, every parameter, every reasoning step — and detects deviations from the expected workflow, security policy violations, and adversarial attacks in real time.

---

## ✨ Key Features

### 🔍 Full Execution Tracing
- **OpenTelemetry / OpenInference compatible** — drop-in integration with any agent that exports OTLP spans
- Captures 7 span kinds: `AGENT`, `TOOL`, `CHAIN`, `RETRIEVER`, `LLM`, `CLIENT`, `INTERNAL`
- Real-time Server-Sent Events (SSE) stream — watch agent execution unfold live
- Persistent SQLite storage with WAL mode for concurrent reads

### 📊 Multi-Dimensional Reliability Scoring
The **Overall Reliability Score (ORS)** is computed as a weighted composite:

$$\text{ORS} = 0.25 \cdot \text{TSA} + 0.20 \cdot \text{PC} + 0.25 \cdot \text{TCR} + 0.15 \cdot \text{WC} + 0.15 \cdot (1 - \text{Penalty})$$

| Metric | Weight | Description |
|--------|--------|-------------|
| Tool Selection Accuracy (TSA) | 25% | Fraction of tool calls that match the optimal execution path |
| Parameter Correctness (PC) | 20% | Fraction of required tool parameters present and non-empty |
| Task Completion Rate (TCR) | 25% | Coverage of optimal-path steps actually executed |
| Workflow Correctness (WC) | 15% | LCS-based order similarity vs. optimal tool sequence |
| Anomaly Penalty | 15% | Score reduction based on detected anomaly severity |

### 🚨 14-Type Anomaly Detection Engine
Two-layer detection system combining pattern recognition and statistical baseline analysis:

**Pattern Detectors:**
| Anomaly Type | Trigger Condition | Severity |
|---|---|---|
| `REASONING_LOOP` | Same tool fails ≥ 3 consecutive times | High |
| `WRONG_TOOL_SELECTION` | Tool not in the optimal execution path | Medium |
| `WRONG_PARAMETERS` | Missing or empty required parameters | Medium |
| `SKIPPED_STEP` | Optimal-path step never executed in completed trace | Medium |
| `HALLUCINATED_OUTPUT` | Span marked with `HALLUCINATED` status | Critical |
| `PROMPT_INJECTION` | `contains_injection` flag on any span | Critical |
| `UNAUTHORIZED_TOOL` | Tool call violates domain security policy | Critical |
| `EXCESSIVE_STEPS` | Total tool calls exceeds threshold (default: 15) | Medium |
| `PARTIAL_COMPLETION` | Trace ended incomplete without full task success | Low |
| `SCHEMA_POISONING` | Injection payload embedded in TOOL span | Critical |
| `ABNORMAL_LATENCY` | Span duration exceeds threshold (default: 10,000 ms) | Low |
| `WORKFLOW_DEVIATION` | Levenshtein distance from optimal tool sequence too high | Medium |
| `GOAL_HIJACKING` | Unauthorized sequence suggesting attacker-redirected execution | Critical |
| `STATISTICAL_OUTLIER` | Span duration deviates `> 2.5σ` from per-span historical baseline | Low |

**Two-layer detection:** Pattern detectors run synchronously during trace ingestion. The statistical layer compares each span's `duration_ms` against baselines stored in the `baselines` table — recomputed via `POST /api/baselines/compute`.

### ⚖️ LLM-as-a-Judge Evaluation (No API Key Required)
Deterministic 5-rubric judge with pass/warn/fail verdicts and per-span explanations:
1. **Tool Selection Accuracy** — path compliance and unauthorized tool check
2. **Parameter Correctness** — required parameter presence and schema validity
3. **Faithfulness / Hallucination** — claimed success vs. actual execution check
4. **Tool Schema Integrity** — injection marker and exfiltration string detection
5. **Authorisation Compliance** — domain security policy enforcement

### 🔴 Red-Team Adversarial Testing
7-attack-type automated red-team engine with Attack Success Rate (ASR) computation:

| Attack | Description |
|---|---|
| **IDPI** (Indirect Prompt Injection) | Malicious instruction hidden in retrieved documents hijacks agent goal |
| **Schema Poisoning** | Tool description modified to exfiltrate parameters to an attacker |
| **Tool Fuzzing** | Boundary/null/injection parameter mutations to destabilise tool execution |
| **Memory Poisoning** | Adversarial content injected into agent's persistent memory context |
| **Goal Hijacking** | Agent redirected to serve attacker objectives instead of user task |
| **Jailbreak** | System prompt constraints bypassed via adversarial prompt patterns |
| **Context Overflow** | Token budget exhausted to reduce tool call capacity and coverage |

Each attack run produces: baseline metrics, attacked metrics, ASR score, reliability delta, platform detection flag, and recommended countermeasures.

### 🎬 Step-by-Step Replay Debugger
- Time-ordered `ReplayFrame` per span with complete LLM I/O, tool parameters/responses, and retrieved documents
- Cumulative execution state snapshot at every step
- **Keyboard-navigable** debugger UI (← →, Home, End, Space)
- **Replay Diff** — side-by-side divergence comparison between baseline and attacked executions

### 🕸️ Interactive Execution DAG
- React Flow-powered directed acyclic graph visualisation
- **Cycle detection** — DFS-based loop identification
- **Critical path** — memoized longest-duration path highlighting
- Node colouring by span kind and status; edge weight by duration

### 📈 Pass@k Reliability Benchmarking
Run the same task `k` times in parallel and compute the empirical pass rate — directly implementing the Tau-bench Pass^k metric from academic literature.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Agent Hub                             │
├─────────────────────────────────────────────────────────────────┤
│              React SPA (Vite)  ·  frontend-react/               │
│   React Flow DAG  •  Recharts  •  Zustand  •  React Router DOM  │
└──────────┬──────────────────────────────────────────────────────┘
           │  REST + SSE (port 8000)
┌──────────▼───────────────────────────────────────────────────────┐
│                     FastAPI Backend                              │
│  backend/                                                        │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐  ┌───────────┐  │
│  │ Ingestion  │  │  Anomaly   │  │Evaluation │  │ Red-Team  │  │
│  │ Normalizer │  │ Detector   │  │ Engine    │  │ Engine    │  │
│  │ (OTLP+SDK) │  │ (14 types) │  │(ORS+Judge)│  │(7 attacks)│  │
│  └────────────┘  └────────────┘  └───────────┘  └───────────┘  │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐  ┌───────────┐  │
│  │   Graph    │  │   Replay   │  │  Storage  │  │   SDK     │  │
│  │  Builder   │  │  Engine    │  │SQLite/PG  │  │  Tracer   │  │
│  │  (DAG+BFS) │  │ (Frames)   │  │ 5 tables  │  │  + HTTP   │  │
│  └────────────┘  └────────────┘  └───────────┘  └───────────┘  │
└──────────────────────────────────────────────────────────────────┘
           │  Adapters
┌──────────▼───────────────────────────────────────────────────────┐
│              Agent Framework Integrations                        │
│   LangChain (CallbackHandler)  •  AutoGen (Middleware)           │
│   CrewAI (Adapter)  •  OTLP-native  •  Direct SDK               │
└──────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend Runtime** | Python 3.11+, FastAPI 0.104+, Uvicorn (ASGI) |
| **Data Validation** | Pydantic v2 |
| **Database** | PostgreSQL (asyncpg pool, port 5433) |
| **HTTP Client** | httpx (async) |
| **Frontend Framework** | React 18, Vite 5 |
| **Routing** | React Router DOM v6 |
| **State Management** | Zustand v5 |
| **Graph Visualisation** | @xyflow/react (React Flow) |
| **Charts** | Recharts |
| **Telemetry Standard** | OpenTelemetry / OpenInference v1.37+ |

---

## 🚀 Quick Start

### Prerequisites

- Python **3.11** or later
- Node.js **18+** (for the React frontend only — optional)
- A modern browser (Chrome, Edge, Firefox)

### 1 · Clone the Repository

```bash
git clone https://github.com/yaswanthsetty/Agent Hub.git
cd Agent Hub
```

### 2 · Set Up the Backend

```bash
cd backend
python -m venv ../venv
# Windows
..\venv\Scripts\activate
# macOS / Linux
source ../venv/bin/activate

pip install -r requirements.txt
```

### 3 · Configure Environment Variables

```bash
# From the repository root:
cp .env.example .env
```

Open `.env` and fill in the values you need. At minimum, you need nothing for the demo — the platform works without any API keys using rule-based evaluation and simulated flight data.

See the [Environment Variables](#%EF%B8%8F-environment-variables) section below for a full description of each setting.

### 4 · Start the Backend Server

```bash
# From the backend/ directory:
cd backend
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

The API is now live at `http://127.0.0.1:8000`.  
Interactive API docs: `http://127.0.0.1:8000/docs`

### 5 · Start the Frontend

```bash
cd frontend-react
npm install
npm run dev
# Opens at http://localhost:3000 with proxy to port 8000
```

### 6 · Run Your First Agent Trace

```bash
curl -X POST http://localhost:8000/api/execute \
  -H "Content-Type: application/json" \
  -d '{"scenario": "normal", "task": "Book a flight from NYC to London"}'
```

---

## 🧪 Running Tests

```bash
# From the repository root:
cd backend
python -m pytest ../backend/tests/ -v
```

Or with an explicit `PYTHONPATH` (recommended on Windows):

```powershell
$env:PYTHONPATH = "$PWD/backend"
python -m pytest backend/tests/ -v --tb=short
```

The test suite covers:

| Test Module | What it covers |
|-------------|----------------|
| `test_metrics.py` | ORS computation, Pass@k, weighted scoring, anomaly penalty |
| `test_anomaly_detection.py` | All 14 anomaly detectors (pattern-based + statistical layer) |
| `test_llm_judge.py` | 5-rubric judge verdicts + mocked OpenAI / Anthropic responses |
| `test_redteam.py` | 7 attack types, ASR computation, detection flag |
| `test_ingestion.py` | OTLP normaliser, SDK ingest, span deduplication |
| `test_replay.py` | ReplayManifest build, frame ordering, diff engine |

---

## ✈️ Running the Real Agent

The real agent (`backend/agents/real_agent.py`) is a LangChain-powered flight booking assistant that connects to live flight APIs and is fully instrumented with the Agent Hub SDK.

```bash
cd backend
python agents/real_agent.py
```

When prompted:

```
Task: book a flight to Delhi tomorrow
```

**API key notes:**
- `OPENAI_API_KEY` — required in `.env` to drive the LangChain agent if not using Ollama
- `AVIATIONSTACK_API_KEY` — optional; if blank the agent automatically falls back to realistic simulated flight data (clearly labelled in the trace)

The agent streams spans to `http://localhost:8000` in real time. Open the **Execute** view in the frontend to watch its execution unfold live.

---

## 🐋 Running Local LLM with Ollama (Optional)

You can run Agent Hub entirely offline for real agent logic, red-teaming, and LLM-as-a-judge capabilities by using a local Ollama container.

1. Start the Ollama container via Docker Compose:
```bash
docker compose up -d
```

2. Download a model (we recommend `mistral` for balanced speed and reasoning or `llama3`/`qwen2` depending on hardware):
```bash
docker exec -it ollama ollama pull mistral
```

3. Ensure the `backend/.env` file contains the Ollama settings:
```ini
LLM_PROVIDER=ollama
OLLAMA_MODEL=mistral
```

---

## ⚙️ Environment Variables

All settings are read from a `.env` file at the project root (copy `.env.example` to get started). Every variable is optional for the demo — defaults let you run the full platform with no API keys.

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://yaswanth@localhost:5433/agent_scope` | PostgreSQL connection string |

### Authentication

| Variable | Default | Description |
|----------|---------|-------------|
| `FLIGHT_RECORDER_API_KEY` | *(blank = disabled)* | When set, all write endpoints require `X-API-Key: <value>` |
| `FLIGHT_RECORDER_ENV` | `development` | Environment tag (`development` / `staging` / `production`) |

### LLM Judge — OpenAI

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(blank)* | Enables OpenAI-backed LLM judge. If blank, rule-based fallback is used. |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name for judge calls |
| `OPENAI_API_BASE` | *(OpenAI default)* | Override base URL (e.g. Azure OpenAI endpoint) |

### LLM Judge — Anthropic

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | *(blank)* | Enables Anthropic/Claude-backed LLM judge |
| `ANTHROPIC_MODEL` | `claude-3-5-sonnet-20241022` | Model name for judge calls |

### Real Agent

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_NAME` | `gpt-4o-mini` | LangChain model name for the real agent |
| `AVIATIONSTACK_API_KEY` | *(blank)* | Live flight data API key. Blank → simulated data with a warning. |

### Email / SMTP

| Variable | Default | Description |
|----------|---------|-------------|
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server hostname |
| `SMTP_PORT` | `587` | SMTP server port (587 = STARTTLS, 465 = SSL) |
| `SMTP_USER` | *(blank)* | SMTP login username |
| `SMTP_PASS` | *(blank)* | SMTP login password |

---

## 📚 API Reference

All endpoints are served from `http://localhost:8000`. Full Swagger UI available at `/docs`.

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Liveness probe — returns `{"status":"ok","version":"2.0.0"}` |

### Telemetry Ingestion

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/traces` | **OTLP/HTTP receiver** — standard OpenTelemetry JSON (`resourceSpans[…]`) |
| `POST` | `/api/ingest` | **SDK ingest** — simplified span dictionary (see SDK usage below) |
| `POST` | `/api/ingest/batch` | **Batch ingest** — list of span payloads in one HTTP call |

### Agent Execution

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/execute` | Run a demo agent scenario — returns `trace_id` immediately; execution runs in background |

### Traces

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/traces` | List traces (filter by `project_id`, `scenario`; paginate with `limit`/`offset`) |
| `GET` | `/api/traces/{trace_id}` | Full trace with all spans |
| `GET` | `/api/traces/{trace_id}/stream` | **SSE live stream** — push each span as a JSON event in real time |
| `GET` | `/api/traces/{trace_id}/evaluate` | Full `EvaluationReport` with ORS, judge assessments, recommendations |
| `GET` | `/api/traces/{trace_id}/graph` | Execution DAG — nodes, edges, cycle flags, critical path |
| `GET` | `/api/traces/{trace_id}/judge` | LLM-as-a-Judge evaluation — 5-rubric per-span assessment (cached) |
| `GET` | `/api/traces/{trace_id}/anomalies` | Anomalies detected within a specific trace |
| `GET` | `/api/traces/{trace_id}/replay` | Full `ReplayManifest` — ordered frames for step-by-step debug |
| `GET` | `/api/traces/{trace_id}/replay/{step}` | Single `ReplayFrame` at a given step index |

### Anomalies & Evaluation

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/anomalies` | All anomalies across all traces, sorted by severity |
| `POST` | `/api/passk` | Pass@k benchmark — run same task `k` times, return pass rate and reliability stats |
| `GET` | `/api/replay/compare` | Replay diff — side-by-side divergence between `?baseline_id` and `?attacked_id` |

### Red-Team

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/redteam/catalogue` | Full 7-attack catalogue with payloads and countermeasures |
| `POST` | `/api/redteam/run` | Execute one attack: baseline → attacked → ASR → `AttackResult` |
| `GET` | `/api/redteam/results` | Historical red-team results from the database |
| `GET` | `/api/redteam/generate-prompts` | Generate `n` adversarial prompt variants for a given `attack_type` |
| `POST` | `/api/redteam/fuzz-params` | Generate `n` mutation variants (null, overflow, injection) for a tool's params |
| `POST` | `/api/redteam/evolution/start` | Start an attack evolution test (iterative payload strengthening) |
| `GET` | `/api/redteam/evolution/{test_id}` | Results of a running or completed evolution test |

### Baselines

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/baselines/compute` | Recompute statistical baselines (mean, std, p95, p99) from DB history |
| `GET` | `/api/baselines` | Current baseline values for all tracked spans |

### Time-Series Metrics

All metric endpoints accept a `range_days` query parameter (default: 7).

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/metrics/trend` | Generic trend series — pass `?metric=<name>` (10 valid metrics) |
| `GET` | `/api/metrics/reliability_trend` | Overall Reliability Score trend over time |
| `GET` | `/api/metrics/anomaly_trend` | Anomaly count trend |
| `GET` | `/api/metrics/tool_accuracy` | Tool Selection Accuracy trend |
| `GET` | `/api/metrics/attack_success_rate` | Attack Success Rate trend |
| `GET` | `/api/metrics/summary` | Summary stats (min, max, avg, p95) for all tracked metrics |
| `GET` | `/api/metrics/degradation` | Regression detector — compares recent N traces vs baseline N |
| `GET` | `/api/metrics/all_trends` | All 7 key metric trends in a single request |
| `GET` | `/api/metrics/timeline` | Time-bucketed reliability (params: `hours`, `bucket_minutes`) |

**Valid metric names:** `overall_reliability_score`, `tool_selection_accuracy`, `parameter_correctness`, `task_completion_rate`, `workflow_correctness`, `anomaly_count`, `hallucination_rate`, `error_rate`, `attack_success_rate`, `reliability_delta`

### Dashboard

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/dashboard` | Aggregate KPIs: total traces, success rate, avg reliability, anomaly count, attack runs |

---

## �‍💻 Developer Guide

### Instrumenting Your Own Agent

Add tracing to any Python agent in three steps:

**Step 1 — Import the SDK (no extra package needed)**

```python
import sys
sys.path.insert(0, "path/to/backend")
from sdk import Tracer
```

**Step 2 — Create a tracer**

```python
tracer = Tracer(
    service_name="my-agent",        # identifies your agent in the UI
    project_id="my-project",        # groups traces together
    endpoint="http://localhost:8000/api/ingest",
    # api_key="secret"              # only needed if FLIGHT_RECORDER_API_KEY is set
)
```

**Step 3 — Wrap your agent logic**

```python
async def run():
    async with tracer.start_trace(task="Book NYC → London") as trace_id:

        # Instrument a tool call
        async with tracer.tool_span(trace_id, "flight_search_api") as span:
            span.attributes["origin"] = "JFK"
            span.attributes["destination"] = "LHR"
            result = await my_flight_search(origin="JFK", dest="LHR")
            span.attributes["result"] = result

        # Instrument an LLM call
        async with tracer.llm_span(trace_id, "decision_layer") as span:
            span.attributes["model"] = "gpt-4o"
            decision = await call_llm(prompt="Which flight should I book?")
            span.attributes["output"] = decision
```

Every context manager automatically records `start_time`, `end_time`, `duration_ms`, and catches exceptions into `error_message` + `SpanStatus.ERROR`. No boilerplate needed.

**Decorator alternative:**

```python
@tracer.trace_tool("flight_search_api", trace_id)
async def search_flights(origin: str, destination: str, date: str):
    ...  # entire function body is auto-traced with timing and error capture
```

### OTLP-Native Integration (LangChain, LlamaIndex, AutoGen…)

Any agent that already emits OpenTelemetry spans works zero-config:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000
export OTEL_EXPORTER_OTLP_PROTOCOL=http/json
```

The `/v1/traces` endpoint accepts the standard OTLP JSON format and normalises spans to the Agent Hub schema automatically.

### Viewing Results

| What you want | Where to look |
|---------------|---------------|
| Live execution stream | **Execute** view → paste `trace_id` → watch SSE events |
| Full span timeline | **Traces** → click a trace row |
| Execution DAG | **Graph** → interactive React Flow diagram |
| Anomaly list | **Anomalies** → sorted by severity |
| Reliability scores | **Metrics** → radar chart and per-dimension breakdown |
| Step-by-step replay | **Replay** → keyboard-navigable frame debugger |
| Red-team results | **Red Team** → attack launcher and ASR history |

### Adding a New Scenario

1. Add an entry to `DOMAINS` in `backend/core/config.py`:

```python
"my_domain": {
    "name": "My Workflow",
    "scenarios": {"my_scenario", "my_attack_scenario"},
    "optimal_path": ["step1_api", "step2_api", "step3_api"],
    "required_params": {
        "step1_api": ["param_a", "param_b"],
    },
    "unauthorized_tools": {"dangerous_api"},
},
```

2. POST a trace with `"scenario": "my_scenario"` — the anomaly detector, metrics engine, and replay engine will automatically use the new domain config.

---

## �🐍 SDK Usage

Instrument any Python agent without modifying its logic:

```python
from backend.sdk import Tracer

tracer = Tracer(
    service_name="my-agent",
    project_id="flight-booking",
    endpoint="http://localhost:8000/api/ingest",
    # api_key="secret"  # optional
)

async with tracer.start_trace(task="Book NYC → London") as trace_id:
    async with tracer.tool_span(trace_id, "flight_search_api") as span:
        span.attributes["origin"] = "JFK"
        span.attributes["destination"] = "LHR"
        # your tool logic here

    async with tracer.llm_span(trace_id, "decision_layer") as span:
        span.attributes["model"] = "gpt-4o"
        # your LLM call here
```

**Decorator-based tracing:**

```python
@tracer.trace_tool("flight_search_api", trace_id)
async def search_flights(origin, destination, date):
    ...  # auto-traced with timing and error capture
```

**OTLP-native agents** (LangChain, LlamaIndex, etc.) just need:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000
export OTEL_EXPORTER_OTLP_PROTOCOL=http/json
```

---

## 🔌 Integrations

### LangChain

```python
from backend.integrations.langchain_adapter import FlightRecorderCallbackHandler

handler = FlightRecorderCallbackHandler(
    endpoint="http://localhost:8000/api/ingest",
    project_id="my-project"
)
agent_executor.run("Book a flight", callbacks=[handler])
```

Hooks: `on_llm_start/end`, `on_tool_start/end`, `on_chain_start/end`, `on_retriever_run`, `on_agent_action`.

### AutoGen

```python
from backend.integrations.autogen_adapter import FlightRecorderAutoGenMiddleware

FlightRecorderAutoGenMiddleware.install(
    endpoint="http://localhost:8000/api/ingest",
    project_id="my-project"
)
# All ConversableAgent.generate_reply calls are now traced automatically
```

### CrewAI

```python
from backend.integrations.crewai_adapter import FlightRecorderCrewAIAdapter

FlightRecorderCrewAIAdapter.install(
    endpoint="http://localhost:8000/api/ingest",
    project_id="my-project"
)
# All crewai.Agent.execute_task calls are now traced automatically
```

All three adapters use `contextvars.ContextVar` for implicit trace-context propagation — **no plumbing changes** needed in your agent code.

---

## 🎯 Scenarios & Demos

The built-in demo agent simulates a **flight booking assistant** with a 5-tool optimal path:

```
flight_search_api → price_comparison_tool → booking_api → payment_api → email_api
```

| Scenario | Trigger | Anomalies Detected |
|----------|---------|-------------------|
| `normal` | All 5 tools execute in order | None — 100% reliability |
| `tool_error` | `web_search` used instead of `flight_search_api` | `WRONG_TOOL_SELECTION` |
| `param_error` | Date passed as `"tomorrow"` not ISO-8601 | `WRONG_PARAMETERS`, 422 cascade |
| `reasoning_loop` | `price_comparison_tool` retried 5× | `REASONING_LOOP` (high severity) |
| `hallucination` | Agent reports email sent — `email_api` never called | `HALLUCINATED_OUTPUT` (critical) |
| `idpi` | Malicious instruction in retrieved document | `PROMPT_INJECTION` (critical) |
| `schema_poison` | Payment tool description exfiltrates card data | `SCHEMA_POISONING` (critical) |
| `memory_poison` | Adversarial content injected into memory | `GOAL_HIJACKING` (critical) |

---

## 🖥️ Frontend Views

The React SPA provides **11 views**:

| Route | View | Description |
|-------|------|-------------|
| `/dashboard` | Dashboard | KPI cards, success rate gauge, recent traces table |
| `/execute` | Execute | Scenario selector, live SSE event log, instant evaluation card |
| `/traces` | Traces | Paginated trace list with project/scenario filters |
| `/traces/:id` | Trace Detail | Full span timeline with status badges and durations |
| `/graph/:id` | Execution DAG | React Flow interactive graph with cycle/critical path overlays |
| `/metrics` | Metrics | Reliability radar chart + tool distribution bar chart |
| `/anomalies` | Anomalies | Severity-sorted anomaly table across all traces |
| `/replay/:id` | Replay Debugger | Step-by-step frame navigator with full LLM I/O and tool params |
| `/redteam` | Red Team | Attack launcher, 7-attack catalogue browser, ASR result cards |
| `/ingest` | Ingest | Manual span/trace ingestion form |
| `/analytics` | Analytics | Long-term reliability trends and metric analytics |

---

## ⚙️ Configuration

All settings are defined in `backend/core/config.py` and can be overridden via environment variables:

| Setting | Environment Variable | Default |
|---------|---------------------|---------|
| Database connection URL | `DATABASE_URL` | `postgresql://yaswanth@localhost:5433/agent_scope` |
| API key authentication | `FLIGHT_RECORDER_API_KEY` | Disabled (empty = open) |
| Max tool calls threshold | — | `15` |
| Reasoning loop threshold | — | `3` failures |
| Max span duration | — | `10,000 ms` |
| Statistical anomaly z-score | — | `2.5 σ` |

**Enable API key authentication:**

```bash
export FLIGHT_RECORDER_API_KEY=your-secret-key
```

Then pass `X-API-Key: your-secret-key` on all write endpoints.

---

## 🗄️ Database Schema

The platform relies strictly on PostgreSQL via `asyncpg`. The schema consists of five core tables auto-created on application startup.

| Table | Purpose |
|-------|---------|
| `traces` | One row per agent execution; JSON blobs for metrics, tags, token usage |
| `spans` | One row per span; attributes/events as JSON; FK → `traces` |
| `anomalies` | Detected anomalies; FK → `traces`; indexed on severity and type |
| `baselines` | Statistical baselines (mean, std, p50, p95, p99) per `(project_id, span_name, metric)` |
| `attack_results` | Red-team run history; stores baseline/attacked metrics, ASR, delta, detection flag |

---

## 🔬 Research Foundation

Agent Hub is directly grounded in published academic and industry research:

| Paper / Standard | Contribution |
|---|---|
| **Tau-bench Pass^k** (Yao et al., 2024) | Pass@k multi-run reliability metric |
| **AgentPoison** (Chen et al., 2024) | RAG backdoor attacks (>80% ASR demonstrated) |
| **TAMAS** (Tan et al., 2024) | Multi-agent Byzantine adversary modelling |
| **SentinelAgent** (Liu et al., 2024) | Graph-based execution anomaly detection |
| **Greshake et al. (2023)** | Indirect Prompt Injection (IDPI) taxonomy |
| **OWASP LLM Top 10** | LLM01 (Prompt Injection), LLM04 (Tool Fuzzing) security framing |
| **OpenInference v1.37+** | Span kind and attribute semantic conventions |
| **OpenTelemetry GenAI** | Telemetry schema and OTLP ingestion standard |
| **AgentBench, GAIA** | Why static benchmarks are insufficient for agent evaluation |

The full research survey is available in [`Agentic AI Reliability Research Report.md`](Agentic%20AI%20Reliability%20Research%20Report.md).

---

## 📁 Project Structure

```
Agent Hub/
├── backend/                        # FastAPI backend
│   ├── main.py                     # API entrypoint — all routes
│   ├── sdk.py                      # Standalone Python tracing SDK
│   ├── requirements.txt            # Python dependencies
│   ├── agents/
│   │   └── demo_agent.py           # 9-scenario flight booking simulator
│   ├── anomaly/
│   │   └── detector.py             # 14-type anomaly detection engine
│   ├── core/
│   │   ├── config.py               # Domain definitions & thresholds
│   │   └── models.py               # Canonical Pydantic v2 data models
│   ├── evaluation/
│   │   ├── judge.py                # 5-rubric LLM-as-a-Judge (deterministic)
│   │   └── metrics.py              # ORS + Pass@k computation
│   ├── graph/
│   │   └── builder.py              # DAG builder — BFS depth, DFS cycles, critical path
│   ├── ingestion/
│   │   └── normalizer.py           # OTLP & SDK span normalisation
│   ├── integrations/
│   │   ├── langchain_adapter.py    # LangChain CallbackHandler
│   │   ├── autogen_adapter.py      # AutoGen middleware
│   │   └── crewai_adapter.py       # CrewAI task adapter
│   ├── redteam/
│   │   ├── catalogue.py            # 7-attack static catalogue
│   │   ├── engine.py               # Attack execution + ASR computation
│   │   └── prompt_generator.py     # Adversarial prompt & fuzz-param generator
│   ├── replay/
│   │   └── engine.py               # ReplayManifest builder + diff engine
│   └── storage/
       ├── __init__.py             # Exports pg_database and pg_repository exclusively
       ├── pg_database.py          # PostgreSQL connection pool (asyncpg, min=2 max=10)
       └── pg_repository.py        # PostgreSQL CRUD operations
├── frontend-react/                 # React 18 SPA (Vite)
│   ├── src/
│   │   ├── views/                  # 11 route-level view components
│   │   ├── components/             # Reusable UI, charts, graph, trace components
│   │   ├── store/useStore.js       # Zustand global state
│   │   ├── services/api.js         # API client layer
│   │   └── utils/format.js         # Formatting helpers
│   ├── package.json
│   └── vite.config.js              # Dev server with port-8000 proxy
├── Agentic AI Reliability Research Report.md
└── README.md
```

---

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-improvement`
3. Commit with clear messages following [Conventional Commits](https://conventionalcommits.org)
4. Open a Pull Request with a description of what you changed and why

---

## 📄 License

This project is licensed under the **MIT License**. See [LICENSE](LICENSE) for details.

---

<div align="center">
Built with ❤️ — grounded in real AI safety and reliability research
</div>
# Agent_Scope
