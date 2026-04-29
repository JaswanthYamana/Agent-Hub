/**
 * Anomalies view — grouped anomaly cards with severity tabs.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { SeverityBadge, ScenarioPill } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import useStore from '../store/useStore'
import { useAsync } from '../hooks/useAsync'
import api from '../services/api'
import { short, fmtTimestamp } from '../utils/format'

const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3 }

function AnomalyCard({ anomaly, onViewTrace }) {
  const sev = (anomaly.severity || 'low').toLowerCase()
  return (
    <div className={`anomaly-card anomaly-card--${sev}`}>
      <div className="anomaly-card-header">
        <SeverityBadge severity={sev} />
        <span className="anomaly-card-type">{anomaly.anomaly_type ?? anomaly.type ?? 'Unknown'}</span>
        <span className="anomaly-card-time muted">{fmtTimestamp(anomaly.detected_at)}</span>
      </div>
      <div className="anomaly-card-body">
        <p className="anomaly-card-desc">{anomaly.description ?? anomaly.message ?? '—'}</p>
        {anomaly.affected_span && (
          <div className="anomaly-card-span">
            <span className="muted">Span: </span>
            <code className="mono">{short(anomaly.affected_span, 22)}</code>
          </div>
        )}
      </div>
      {anomaly.trace_id && (
        <div className="anomaly-card-footer">
          <span className="muted">{short(anomaly.trace_id, 14)}</span>
          <button
            className="btn btn-ghost btn-xs"
            onClick={() => onViewTrace(anomaly.trace_id)}
          >
            View Trace →
          </button>
        </div>
      )}
    </div>
  )
}

export default function Anomalies() {
  const navigate = useNavigate()
  const toast    = useStore((s) => s.toast)
  const [sevTab, setSevTab] = useState('all')

  const { data, loading, error, execute: loadAnomalies } = useAsync(
    useCallback(() => api.listAnomalies(), [])
  )

  useEffect(() => { loadAnomalies() }, [loadAnomalies])
  useEffect(() => { if (error) toast(`Load failed: ${error}`, 'error') }, [error, toast])

  const anomalies = data ?? []

  const counts = useMemo(() => {
    return anomalies.reduce((acc, a) => {
      const s = (a.severity || 'low').toLowerCase()
      acc[s] = (acc[s] ?? 0) + 1
      return acc
    }, {})
  }, [anomalies])

  const filtered = useMemo(() => {
    const list = sevTab === 'all'
      ? anomalies
      : anomalies.filter((a) => (a.severity || 'low').toLowerCase() === sevTab)
    return [...list].sort((a, b) =>
      (SEV_ORDER[a.severity?.toLowerCase()] ?? 3) -
      (SEV_ORDER[b.severity?.toLowerCase()] ?? 3)
    )
  }, [anomalies, sevTab])

  const tabs = [
    { key: 'all',      label: `All (${anomalies.length})` },
    { key: 'critical', label: `Critical (${counts.critical ?? 0})` },
    { key: 'high',     label: `High (${counts.high ?? 0})` },
    { key: 'medium',   label: `Medium (${counts.medium ?? 0})` },
    { key: 'low',      label: `Low (${counts.low ?? 0})` },
  ]

  return (
    <div className="view">
      <div className="view-header">
        <h1 className="view-title">Anomalies</h1>
        <button className="btn btn-ghost btn-sm" onClick={loadAnomalies} disabled={loading}>
          {loading ? <Spinner size="sm" /> : '↺ Refresh'}
        </button>
      </div>

      {/* Summary stats */}
      <div className="stat-grid" style={{ marginBottom: 16 }}>
        {['critical', 'high', 'medium', 'low'].map((s) => (
          <div key={s} className={`stat-card stat-card--${s}`} onClick={() => setSevTab(s)} style={{ cursor: 'pointer' }}>
            <div className="stat-card-label" style={{ textTransform: 'capitalize' }}>{s}</div>
            <div className="stat-card-value" style={{
              color: s === 'critical' ? 'var(--red)' :
                     s === 'high'     ? 'var(--orange)' :
                     s === 'medium'   ? 'var(--orange)' : 'var(--text-secondary)'
            }}>
              {counts[s] ?? 0}
            </div>
          </div>
        ))}
      </div>

      {/* Severity tabs */}
      <div className="tab-bar" style={{ marginBottom: 16 }}>
        {tabs.map((t) => (
          <button
            key={t.key}
            className={`tab-btn${sevTab === t.key ? ' tab-btn--active' : ''}`}
            onClick={() => setSevTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {loading && <div className="panel-loading"><Spinner /> Loading anomalies…</div>}

      {!loading && filtered.length === 0 && (
        <EmptyState
          icon="✓"
          title="No anomalies found"
          description={sevTab === 'all' ? 'No anomalies have been detected.' : `No ${sevTab} anomalies.`}
        />
      )}

      <div className="anomaly-grid">
        {filtered.map((a, i) => (
          <AnomalyCard
            key={a.id ?? a.anomaly_id ?? i}
            anomaly={a}
            onViewTrace={(id) => navigate(`/traces/${id}`)}
          />
        ))}
      </div>
    </div>
  )
}
