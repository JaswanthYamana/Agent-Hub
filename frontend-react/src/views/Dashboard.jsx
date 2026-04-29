import { useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { ScenarioPill, StatusBadge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import useStore from '../store/useStore'
import { useAsync } from '../hooks/useAsync'
import api from '../services/api'
import { fmtDuration, fmtTimestamp, short } from '../utils/format'

function StatCard({ label, value, color, sub }) {
  return (
    <div className="stat-card">
      <div className="stat-card-label">{label}</div>
      <div className="stat-card-value" style={{ color: color ?? 'var(--text-primary)' }}>
        {value ?? '—'}
      </div>
      {sub && <div className="stat-card-sub">{sub}</div>}
    </div>
  )
}

export default function Dashboard() {
  const navigate  = useNavigate()
  const toast     = useStore((s) => s.toast)

  const { data, loading, error, execute } = useAsync(
    useCallback(() => api.getDashboard(), [])
  )

  useEffect(() => { execute() }, [execute])
  useEffect(() => {
    if (error) toast(`Dashboard load failed: ${error}`, 'error')
  }, [error, toast])

  const d = data ?? {}
  const successRate = d.success_rate != null
    ? `${(d.success_rate > 1 ? d.success_rate : d.success_rate * 100).toFixed(1)}%`
    : '—'
  const avgScore = d.avg_reliability != null
    ? `${(d.avg_reliability * 100).toFixed(0)}`
    : '—'

  return (
    <div className="view">
      <div className="view-header">
        <h1 className="view-title">Dashboard</h1>
        <button
          className="btn btn-ghost btn-sm"
          onClick={execute}
          disabled={loading}
          title="Refresh"
        >
          {loading ? <Spinner size="sm" /> : '↺ Refresh'}
        </button>
      </div>

      {/* KPI stat cards */}
      <div className="stat-grid">
        <StatCard label="Total Traces"    value={d.total_traces}    />
        <StatCard
          label="Success Rate"
          value={successRate}
          color={d.success_rate >= 0.8 ? 'var(--green)' : d.success_rate >= 0.5 ? 'var(--orange)' : 'var(--red)'}
        />
        <StatCard
          label="Avg Reliability"
          value={avgScore}
          color={d.avg_reliability >= 0.8 ? 'var(--green)' : d.avg_reliability >= 0.5 ? 'var(--orange)' : 'var(--red)'}
          sub="/ 100"
        />
        <StatCard label="Anomalies"     value={d.anomaly_count}    color="var(--orange)" />
        <StatCard label="Attack Runs"   value={d.attack_run_count} color="var(--purple)" />
      </div>

      {/* Recent traces */}
      <div className="panel" style={{ marginTop: 24 }}>
        <div className="panel-header">
          <span className="panel-title">Recent Traces</span>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/traces')}>
            View all →
          </button>
        </div>

        {loading && <div className="panel-loading"><Spinner /> Loading…</div>}

        {!loading && (!d.recent_traces || d.recent_traces.length === 0) && (
          <EmptyState
            icon="⬡"
            title="No traces yet"
            description="Run your first agent task to see traces here."
            action={
              <button className="btn btn-primary btn-sm" onClick={() => navigate('/execute')}>
                Run Agent
              </button>
            }
          />
        )}

        {!loading && d.recent_traces?.length > 0 && (
          <table className="data-table">
            <thead>
              <tr>
                <th>Trace ID</th>
                <th>Scenario</th>
                <th>Status</th>
                <th>Spans</th>
                <th>Duration</th>
                <th>When</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {d.recent_traces.map((t) => (
                <tr key={t.trace_id} className="table-row-hover">
                  <td>
                    <code className="mono">{short(t.trace_id, 12)}</code>
                  </td>
                  <td><ScenarioPill scenario={t.scenario} /></td>
                  <td>
                    {(() => {
                      const st = t.status ||
                        (t.success ? 'OK' : t.error_count > 0 ? 'ERROR' : t.completed ? 'OK' : 'PENDING')
                      return (
                        <StatusBadge
                          success={st.toUpperCase() === 'OK'}
                          label={st}
                        />
                      )
                    })()}
                  </td>
                  <td>{t.span_count ?? t.total_steps ?? '—'}</td>
                  <td>{fmtDuration(t.duration_ms)}</td>
                  <td className="muted">{fmtTimestamp(t.start_time)}</td>
                  <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <button
                      className="btn btn-ghost btn-xs"
                      onClick={() => navigate(`/traces/${t.trace_id}`)}
                    >
                      Inspect
                    </button>
                    <button
                      className="btn btn-ghost btn-xs"
                      onClick={() => navigate(`/graph/${t.trace_id}`)}
                      style={{ marginLeft: 4 }}
                    >
                      Graph
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Quick actions */}
      <div className="quick-actions" style={{ marginTop: 20 }}>
        <button className="btn btn-primary"   onClick={() => navigate('/execute')}>⚡ Execute Agent</button>
        <button className="btn btn-secondary" onClick={() => navigate('/redteam')}>🔴 Red-Team</button>
        <button className="btn btn-secondary" onClick={() => navigate('/anomalies')}>🔍 Anomalies</button>
        <button className="btn btn-secondary" onClick={() => navigate('/metrics')}>📊 Metrics</button>
      </div>
    </div>
  )
}
