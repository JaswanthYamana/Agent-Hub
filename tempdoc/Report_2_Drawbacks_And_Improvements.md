# Report 2: Drawbacks, Risks & Improvement Roadmap (Updated)

> Tone: Objective and architectural
> Scope: current codebase constraints and next steps after the major integration milestones
> Audit date: 2026-03-14

---

## 1. Resolved Critical Issues

The following major roadblocks have been successfully eradicated in the latest release:
- **Write Amplification in Ingestion**: save_span bottleneck replaced with a high-performance save_spans_bulk utilizing PostgreSQL xecutemany.
- **Database Concurrency Risks**: SQLite completely eliminated; full migration to unblocked concurrent syncpg execution.
- **Cost and Connectivity Dependencies**: Local LLMs (Ollama) now manage testing and judging, removing brittle API costs.
- **Brittle Testing Architecture**: Test suites now dynamically verify Auth paths and cleanly tear down global Config dependencies. Total passing test count: 214.

---

## 2. Issues Still Requiring Refinement

### ISSUE-1: Synthetic Red-Teaming Legacy Bias
Severity: Medium

Problem:
While the IDPI Fuzzer natively works and produces deterministic payloads, the fundamental red-team /api/redteam/run tests still occasionally default to the deterministic DemoAgent() mock.

Impact:
Some graphical metrics in the frontend might trace purely functional mock outcomes instead of LLM-generated pathways unless switched to 
eal_agent.

Fix direction:
1. Make 
eal_agent (via Ollama) the default evaluation pipeline for all frontend Red-Team executions.

---

### ISSUE-2: In-Memory SSE Stream Queues
Severity: Medium

Problem:
SSE trace events are maintained within process memory.

Impact:
Restarting the FastAPI server will cause any clients currently streaming dashboard traces to lose history that wasn't previously committed.

Fix direction:
1. Incorporate a basic Redis Pub/Sub deployment within docker-compose to propagate streams globally across potential multi-worker nodes.

---

### ISSUE-3: Agent Evolution Logic
Severity: Low

Problem:
The adversarial generation creates deterministic inputs but evaluates success via string-grounded rules rather than semantic outcome impact.

Fix direction:
1. Expand the LLMJudge to act as the primary evolutionary fitness function, grading whether an attack genuinely bypassed agent safety constraints.

---

## 3. Prioritized Improvement Plan

### Phase 1: Operational Scaling (1 Week)
1. Add Redis Pub/Sub to fully distribute SSE streams, mitigating volatile memory limits.
2. Bind frontend metrics specifically to 
eal_agent deployments standardizing on the new Ollama models.

### Phase 2: Enhanced Product Capabilities (2 Weeks)
1. Provide UI tools for users to inject custom domain logic without relying entirely on backend config definitions.
2. Allow custom OTLP ingestion rules from the frontend dashboard.

---

## 4. Closing Assessment

The recent architectural investments (PostgreSQL, Ollama, batch optimization) successfully elevate this application from a local prototype to an enterprise-ready analytics and red-teaming platform. Remaining efforts involve fine-tuning the UI experience and maximizing LLM-based fitness evaluations to fully exploit the robust infrastructure now in place.
