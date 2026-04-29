/**
 * Ingest view — SDK documentation and REST API reference.
 */
import { useState } from 'react'

const CODE = {
  python_sdk: `from flight_recorder import FlightRecorder, scenario

# Initialize the recorder
recorder = FlightRecorder(backend_url="http://localhost:8000")

# Use the context manager
with recorder.trace(scenario="normal") as trace:
    result = my_agent.run("Find flights from NYC to London")

print("Trace ID:", trace.trace_id)`,

  decorator: `from flight_recorder import FlightRecorder

recorder = FlightRecorder()

@recorder.agent(scenario="normal")
def my_agent(task: str):
    # Your agent logic here
    return result

# Automatic tracing — no manual context needed
result = my_agent("Find cheap flights")`,

  async_sdk: `import asyncio
from flight_recorder import AsyncFlightRecorder

recorder = AsyncFlightRecorder(backend_url="http://localhost:8000")

async def run():
    async with recorder.trace(scenario="normal") as trace:
        result = await my_async_agent.run("Book a flight")
    print("Trace:", trace.trace_id)

asyncio.run(run())`,

  langchain: `from flight_recorder.integrations.langchain_callback import FlightRecorderCallback

callback = FlightRecorderCallback(backend_url="http://localhost:8000")

chain.invoke(
    {"input": "Find me the cheapest flight"},
    config={"callbacks": [callback]}
)`,

  crewai: `from flight_recorder.integrations.crewai_adapter import FlightRecorderCrewAIAdapter

adapter = FlightRecorderCrewAIAdapter(backend_url="http://localhost:8000")

# Wrap your crew before kicking off
adapter.instrument(crew)
crew.kickoff()`,

  autogen: `from flight_recorder.integrations.autogen_adapter import FlightRecorderAutoGenMiddleware

with FlightRecorderAutoGenMiddleware(backend_url="http://localhost:8000"):
    # All ConversableAgent calls are automatically traced
    result = assistant.initiate_chat(
        user_proxy,
        message="Find the best flight"
    )`,

  otlp: `# Set the OTLP exporter endpoint to the Flight Recorder backend
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:8000/v1
export OTEL_SERVICE_NAME=my-agent

# Any OpenTelemetry-instrumented app will now send spans here.
# Supported protocols: grpc (port 4317), http (port 4318/v1/traces)`,

  rest: null,
}

const ENDPOINTS = [
  { method: 'GET',  path: '/api/traces',              desc: 'List all traces' },
  { method: 'GET',  path: '/api/traces/:id',           desc: 'Get trace with spans' },
  { method: 'GET',  path: '/api/traces/:id/evaluate',  desc: 'Run reliability evaluation' },
  { method: 'GET',  path: '/api/traces/:id/graph',     desc: 'Get execution DAG' },
  { method: 'GET',  path: '/api/traces/:id/replay',    desc: 'Replay manifest' },
  { method: 'GET',  path: '/api/traces/:id/replay/:step', desc: 'Single replay frame' },
  { method: 'POST', path: '/api/execute',              desc: 'Execute agent task' },
  { method: 'GET',  path: '/api/dashboard',            desc: 'Platform KPIs' },
  { method: 'GET',  path: '/api/anomalies',            desc: 'List all anomalies' },
  { method: 'GET',  path: '/api/anomalies/:trace_id',  desc: 'Anomalies for a trace' },
  { method: 'POST', path: '/api/metrics/pass-k',       desc: 'Run Pass@k evaluation' },
  { method: 'POST', path: '/api/metrics/baselines',    desc: 'Compute scenario baselines' },
  { method: 'GET',  path: '/api/metrics/baselines',    desc: 'Fetch cached baselines' },
  { method: 'GET',  path: '/api/redteam/catalogue',    desc: 'Get attack catalogue' },
  { method: 'POST', path: '/api/redteam/run',          desc: 'Run red-team attack' },
  { method: 'GET',  path: '/api/redteam/results',      desc: 'List attack results' },
  { method: 'POST', path: '/api/redteam/generate',     desc: 'Generate adversarial prompts' },
  { method: 'POST', path: '/api/redteam/fuzz',         desc: 'Fuzz tool parameters' },
  { method: 'POST', path: '/api/ingest/batch',         desc: 'Batch-ingest spans' },
  { method: 'POST', path: '/v1/traces',                desc: 'OTLP trace ingest (HTTP)' },
]

const TABS = [
  { key: 'python_sdk',  label: 'Python SDK' },
  { key: 'decorator',   label: 'Decorator API' },
  { key: 'async_sdk',   label: 'Async' },
  { key: 'langchain',   label: 'LangChain' },
  { key: 'crewai',      label: 'CrewAI' },
  { key: 'autogen',     label: 'AutoGen' },
  { key: 'otlp',        label: 'OTLP' },
  { key: 'rest',        label: 'REST API' },
]

function MethodBadge({ method }) {
  const color = {
    GET: 'var(--green)', POST: 'var(--blue)', PUT: 'var(--orange)',
    DELETE: 'var(--red)', PATCH: 'var(--purple)',
  }[method] ?? 'var(--text-secondary)'
  return (
    <span className="badge" style={{ background: `${color}22`, color, fontFamily: 'monospace', minWidth: 52, textAlign: 'center' }}>
      {method}
    </span>
  )
}

export default function Ingest() {
  const [tab, setTab] = useState('python_sdk')

  return (
    <div className="view">
      <div className="view-header">
        <h1 className="view-title">Ingest &amp; SDK</h1>
      </div>

      <div className="tab-bar" style={{ marginBottom: 20 }}>
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`tab-btn${tab === t.key ? ' tab-btn--active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab !== 'rest' && CODE[tab] && (
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">{TABS.find((t) => t.key === tab)?.label}</span>
          </div>
          <pre className="code-block code-block--lg">{CODE[tab]}</pre>
        </div>
      )}

      {tab === 'rest' && (
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">REST API Reference</span>
            <span className="muted" style={{ fontSize: 12 }}>Base: http://localhost:8000</span>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Method</th>
                <th>Path</th>
                <th>Description</th>
              </tr>
            </thead>
            <tbody>
              {ENDPOINTS.map((ep, i) => (
                <tr key={i}>
                  <td><MethodBadge method={ep.method} /></td>
                  <td><code className="mono">{ep.path}</code></td>
                  <td className="muted">{ep.desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Installation card */}
      {tab !== 'rest' && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header"><span className="panel-title">Installation</span></div>
          <pre className="code-block">pip install flight-recorder-sdk</pre>
          <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
            Or install from source: <code className="mono">pip install -e backend/sdk/</code>
          </p>
        </div>
      )}
    </div>
  )
}
