/**
 * Metrics view — reliability radar, tool distribution, Pass@k runner,
 * reliability breakdown bars, and time-series trend chart.
 */
import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'
import ReliabilityRadar from '../components/charts/ReliabilityRadar'
import ToolDistChart    from '../components/charts/ToolDistChart'
import { Spinner }      from '../components/ui/Spinner'
import { EmptyState }   from '../components/ui/EmptyState'
import useStore         from '../store/useStore'
import { useAsync }     from '../hooks/useAsync'
import api              from '../services/api'
import { short, fmtDuration, pctColor } from '../utils/format'

// ─── Horizontal bar breakdown ─────────────────────────────────────────────────
const METRIC_META = [
  { key: 'tool_selection_accuracy',  label: 'Tool Selection Accuracy',  icon: '🔧' },
  { key: 'parameter_correctness',    label: 'Parameter Correctness',    icon: '⚙️'  },
  { key: 'task_completion_rate',     label: 'Task Completion Rate',     icon: '✅' },
  { key: 'workflow_correctness',     label: 'Workflow Correctness',     icon: '🔀' },
]

function ReliabilityBreakdown({ metrics, evalData }) {
  const ors = metrics.overall_reliability_score
  const penalty = metrics.anomaly_penalty ?? 0
  const pct = ors != null ? Math.round(ors * 100) : null
  const orsColor = pct == null ? 'var(--text-muted)' : pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--orange)' : 'var(--red)'

  return (
    <div>
      {/* ORS headline */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 20, marginBottom: 24 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 48, fontWeight: 800, color: orsColor, lineHeight: 1 }}>
            {pct != null ? pct : '—'}
          </div>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>Overall Reliability</div>
        </div>

        <div style={{ flex: 1 }}>
          {METRIC_META.map(({ key, label, icon }) => {
            const val = metrics[key]
            const vpct = val != null ? Math.round(val * 100) : null
            const barColor = vpct == null ? 'var(--border)' : vpct >= 80 ? 'var(--green)' : vpct >= 50 ? 'var(--orange)' : 'var(--red)'
            return (
              <div key={key} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                  <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>{icon} {label}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: barColor }}>{vpct != null ? `${vpct}%` : '—'}</span>
                </div>
                <div style={{ height: 8, background: 'var(--bg-card)', borderRadius: 4, overflow: 'hidden' }}>
                  <div style={{
                    width: `${vpct ?? 0}%`, height: '100%',
                    background: barColor, borderRadius: 4,
                    transition: 'width 0.6s ease',
                  }} />
                </div>
              </div>
            )
          })}

          {/* Anomaly penalty */}
          {penalty > 0 && (
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 8 }}>
              <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>⚠ Anomaly Penalty</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--red)' }}>
                -{Math.round(penalty * 100)}%
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Trend chart ──────────────────────────────────────────────────────────────
function TrendChart({ data }) {
  if (!data || data.length === 0) {
    return <EmptyState icon="📈" title="No trend data yet" description="Run more agent executions to see trends over time." />
  }

  const chartData = data.map((d) => ({
    time: d.bucket_label ?? d.timestamp ?? d.ts ?? '',
    reliability: d.avg_ors != null ? Math.round(d.avg_ors * 100) : null,
    anomalies: d.anomaly_count ?? 0,
    traces: d.trace_count ?? 0,
  })).filter(d => d.time)

  if (chartData.length === 0) {
    return <EmptyState icon="📈" title="No trend data" description="No time-bucketed data available yet." />
  }

  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={chartData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis
          dataKey="time"
          stroke="var(--text-muted)"
          tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
          tickFormatter={(v) => {
            if (!v) return ''
            // Try to format as time if it's a ISO string
            try { return new Date(v).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) } catch { return String(v).slice(0, 8) }
          }}
        />
        <YAxis
          stroke="var(--text-muted)"
          tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
          tickFormatter={(v) => `${v}%`}
          domain={[0, 100]}
          yAxisId="score"
        />
        <YAxis
          stroke="var(--text-muted)"
          tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
          yAxisId="count"
          orientation="right"
          width={30}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--bg-elevated)', border: '1px solid var(--border)',
            borderRadius: 6, color: 'var(--text-primary)', fontSize: 12,
          }}
          formatter={(val, name) => name === 'Reliability' ? `${val}%` : val}
        />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Line
          yAxisId="score"
          type="monotone"
          dataKey="reliability"
          name="Reliability"
          stroke="var(--blue)"
          strokeWidth={2}
          dot={{ r: 3 }}
          activeDot={{ r: 5 }}
          connectNulls
        />
        <Line
          yAxisId="count"
          type="monotone"
          dataKey="anomalies"
          name="Anomalies"
          stroke="var(--red)"
          strokeWidth={1.5}
          strokeDasharray="4 2"
          dot={{ r: 2 }}
          connectNulls
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

export default function Metrics() {
  const toast    = useStore((s) => s.toast)
  const navigate = useNavigate()

  // Trace list for the selector
  const { data: traceList, execute: loadList } = useAsync(
    useCallback(() => api.listTraces(), [])
  )

  // Per-trace evaluation
  const [traceId, setTraceId] = useState('')
  const { data: evalData, loading: evalLoading, error: evalError, execute: loadEval } = useAsync(
    useCallback((id) => api.evaluateTrace(id), [])
  )

  // Baselines
  const { data: baselines, loading: bLoading, execute: loadBaselines } = useAsync(
    useCallback((n) => api.computeBaselines(n), [])
  )

  // Time-series trend
  const { data: trendData, loading: trendLoading, execute: loadTrend } = useAsync(
    useCallback(() => api.getMetricsTimeline({ hours: 48, bucket_minutes: 60 }), [])
  )

  // Pass@k
  const [pk, setPk] = useState(5)
  const { data: pkResult, loading: pkLoading, execute: runPassK } = useAsync(
    useCallback((id, k) => api.evaluateTrace(id, k), [])
  )

  useEffect(() => { loadList() }, [loadList])
  useEffect(() => { loadTrend() }, [loadTrend])
  useEffect(() => { if (evalError) toast(`Eval failed: ${evalError}`, 'error') }, [evalError, toast])

  const handleEval = () => {
    if (!traceId.trim()) { toast('Select a trace.', 'warn'); return }
    loadEval(traceId.trim())
  }

  const handlePassK = () => {
    if (!traceId.trim()) { toast('Select a trace.', 'warn'); return }
    runPassK(traceId.trim(), pk)
  }

  const metrics    = evalData?.metrics    ?? {}
  const toolDist   = evalData?.tool_dist  ?? []

  return (
    <div className="view">
      <div className="view-header">
        <h1 className="view-title">Metrics</h1>
        <button className="btn btn-ghost btn-sm" onClick={loadList}>↺ Refresh</button>
      </div>

      {/* Trace selector */}
      <div className="panel" style={{ marginBottom: 16, padding: '12px 16px' }}>
        <div className="trace-selector">
          <select
            className="form-select"
            value={traceId}
            onChange={(e) => setTraceId(e.target.value)}
            style={{ flex: 1 }}
          >
            <option value="">Select a trace…</option>
            {(traceList ?? []).map((t) => (
              <option key={t.trace_id} value={t.trace_id}>
                {short(t.trace_id, 20)} — {t.scenario ?? 'unknown'} — {t.status}
              </option>
            ))}
          </select>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleEval}
            disabled={evalLoading || !traceId}
          >
            {evalLoading ? <Spinner size="sm" /> : 'Evaluate'}
          </button>
        </div>
      </div>

      {/* Charts grid */}
      <div className="metrics-grid">
        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Reliability Radar</span>
          </div>
          {evalLoading && <div className="panel-loading"><Spinner /></div>}
          {!evalLoading && Object.keys(metrics).length === 0 && (
            <EmptyState icon="📊" title="Run evaluation above" description="Select a trace and click Evaluate." />
          )}
          {!evalLoading && Object.keys(metrics).length > 0 && (
            <ReliabilityRadar metrics={metrics} />
          )}
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Tool Distribution</span>
          </div>
          {evalLoading && <div className="panel-loading"><Spinner /></div>}
          {!evalLoading && toolDist.length === 0 && (
            <EmptyState icon="🔧" title="No tool data" description="Run evaluation to see tool distribution." />
          )}
          {!evalLoading && toolDist.length > 0 && (
            <ToolDistChart data={toolDist} />
          )}
        </div>
      </div>

      {/* Reliability breakdown panel */}
      {!evalLoading && Object.keys(metrics).length > 0 && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">
            <span className="panel-title">Reliability Breakdown</span>
          </div>
          <ReliabilityBreakdown metrics={metrics} evalData={evalData} />
        </div>
      )}

      {/* Time-series trend */}
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-header">
          <span className="panel-title">Reliability Trend</span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={loadTrend}
            disabled={trendLoading}
          >
            {trendLoading ? <Spinner size="sm" /> : '↺ Refresh'}
          </button>
        </div>
        <p style={{ fontSize: 12, color: 'var(--text-secondary)', marginBottom: 12, marginTop: 0 }}>
          Agent reliability and anomaly count over the last 48 hours.
        </p>
        {trendLoading && <div className="panel-loading"><Spinner /></div>}
        {!trendLoading && (
          <TrendChart data={trendData?.buckets ?? trendData?.data ?? (Array.isArray(trendData) ? trendData : [])} />
        )}
      </div>

      {/* Pass@k */}
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-header">
          <span className="panel-title">Pass@k</span>
        </div>
        <div className="passk-form">
          <label className="form-label" style={{ marginRight: 8 }}>k =</label>
          <input
            className="form-input"
            type="number"
            min={1}
            max={100}
            value={pk}
            onChange={(e) => setPk(Number(e.target.value))}
            style={{ width: 80 }}
          />
          <button
            className="btn btn-primary btn-sm"
            onClick={handlePassK}
            disabled={pkLoading || !traceId}
            style={{ marginLeft: 8 }}
          >
            {pkLoading ? <Spinner size="sm" /> : 'Run Pass@k'}
          </button>
        </div>

        {pkResult && (
          <div className="passk-result">
            <span className="passk-label">Pass@{pk}:</span>
            <strong className="passk-value" style={{
              color: pkResult.pass_at_k >= 0.8 ? 'var(--green)' : pkResult.pass_at_k >= 0.5 ? 'var(--orange)' : 'var(--red)'
            }}>
              {(pkResult.pass_at_k * 100).toFixed(1)}%
            </strong>
            <span className="muted" style={{ fontSize: 12 }}>
              ({pkResult.passes}/{pkResult.trials} passes)
            </span>
          </div>
        )}
      </div>

      {/* Baselines */}
      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-header">
          <span className="panel-title">Baselines</span>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => loadBaselines(50)}
            disabled={bLoading}
          >
            {bLoading ? <Spinner size="sm" /> : 'Compute (n=50)'}
          </button>
        </div>
        {baselines && (
          <table className="data-table">
            <thead>
              <tr><th>Scenario</th><th>Avg Score</th><th>p50</th><th>p95</th><th>Traces</th></tr>
            </thead>
            <tbody>
              {Object.entries(baselines).map(([sc, b]) => (
                <tr key={sc}>
                  <td>{sc}</td>
                  <td>{((b.avg ?? 0) * 100).toFixed(1)}%</td>
                  <td>{((b.p50 ?? 0) * 100).toFixed(1)}%</td>
                  <td>{((b.p95 ?? 0) * 100).toFixed(1)}%</td>
                  <td>{b.n ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
