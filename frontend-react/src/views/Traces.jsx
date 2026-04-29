/**
 * Traces view — sortable/filterable trace table with split detail panel.
 *
 * Features:
 *  - Filter by scenario, status, and free-text search
 *  - Click row → right-side panel: TraceTimeline + EvalReport + SpanDetailSidebar
 *  - Deep-link via /traces/:traceId
 *  - Action buttons: View Graph, Replay, Re-evaluate
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import TraceTimeline from '../components/trace/TraceTimeline'
import SpanDetailSidebar from '../components/trace/SpanDetailSidebar'
import EvalReport from '../components/trace/EvalReport'
import JudgeResultsPanel from '../components/trace/JudgeResultsPanel'
import { ScenarioPill, StatusBadge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import useStore from '../store/useStore'
import { useAsync } from '../hooks/useAsync'
import api from '../services/api'
import { fmtDuration, fmtTimestamp, short } from '../utils/format'

const SCENARIOS = ['all', 'normal', 'hallucination', 'idpi', 'schema_poisoning', 'memory_poisoning']
const STATUSES  = ['all', 'OK', 'ERROR', 'ANOMALOUS']
const ANOMALY_TYPES = [
  { value: 'all',               label: 'All anomalies' },
  { value: 'prompt_injection',  label: 'Prompt Injection' },
  { value: 'wrong_tool',        label: 'Tool Misuse' },
  { value: 'workflow_deviation', label: 'Workflow Deviation' },
  { value: 'reasoning_loop',    label: 'Reasoning Loop' },
  { value: 'schema_poisoning',  label: 'Schema Poisoning' },
  { value: 'goal_hijacking',    label: 'Goal Hijacking' },
  { value: 'unauthorized_tool', label: 'Unauthorized Tool' },
]

export default function Traces() {
  const { traceId: urlTraceId } = useParams()
  const navigate = useNavigate()
  const toast    = useStore((s) => s.toast)
  const setActive = useStore((s) => s.setActiveTrace)

  // Filters
  const [scenarioFilter, setScenarioFilter] = useState('all')
  const [statusFilter,   setStatusFilter]   = useState('all')
  const [anomalyFilter,  setAnomalyFilter]  = useState('all')
  const [minScore,       setMinScore]       = useState(0)
  const [traceIdSearch,  setTraceIdSearch]  = useState('')
  const [search,         setSearch]         = useState('')

  // Selected trace
  const [selectedId,  setSelectedId]  = useState(urlTraceId ?? null)
  const [selectedSpan, setSelectedSpan] = useState(null)

  // Data loaders
  const {
    data: traceList, loading: listLoading, error: listError, execute: loadList,
  } = useAsync(useCallback(() => api.listTraces(), []))

  const {
    data: traceDetail, loading: detailLoading, execute: loadDetail,
  } = useAsync(useCallback(
    (id) => id ? api.getTrace(id) : Promise.resolve(null),
    []
  ))

  const {
    data: evalReport, loading: evalLoading, execute: loadEval,
  } = useAsync(useCallback(
    (id) => id ? api.evaluateTrace(id) : Promise.resolve(null),
    []
  ))

  // Initial load
  useEffect(() => { loadList() }, [loadList])
  useEffect(() => { if (listError) toast(`Failed to load traces: ${listError}`, 'error') }, [listError, toast])

  // Deep-link: preselect trace from URL param
  useEffect(() => {
    if (urlTraceId) selectTrace(urlTraceId)
  }, [urlTraceId]) // eslint-disable-line

  const selectTrace = useCallback((id) => {
    setSelectedId(id)
    setSelectedSpan(null)
    setActive(id)
    if (id) {
      loadDetail(id)
      loadEval(id)
    }
  }, [loadDetail, loadEval, setActive])

  // Filtered + sorted list
  const filtered = useMemo(() => {
    if (!traceList) return []
    return traceList
      .filter((t) => {
        if (scenarioFilter !== 'all' && t.scenario !== scenarioFilter) return false
        if (statusFilter   !== 'all' && (t.status  || '').toUpperCase() !== statusFilter) return false
        if (anomalyFilter  !== 'all') {
          const hasAnomaly = (t.anomalies ?? []).some(
            (a) => (a.anomaly_type || a.type || '').toLowerCase().includes(anomalyFilter.replace(/_/g, ' ').split('_').join(''))
              || (a.anomaly_type || a.type || '').toLowerCase().includes(anomalyFilter.toLowerCase())
          ) || (t.scenario || '').toLowerCase().includes(anomalyFilter.toLowerCase())
          if (!hasAnomaly) return false
        }
        if (minScore > 0) {
          const score = (t.metrics?.overall_reliability_score ?? 1) * 100
          if (score < minScore) return false
        }
        if (search && !JSON.stringify(t).toLowerCase().includes(search.toLowerCase())) return false
        return true
      })
      .sort((a, b) => (b.start_time ?? 0) - (a.start_time ?? 0))
  }, [traceList, scenarioFilter, statusFilter, anomalyFilter, minScore, search])

  const handleSpanSelect = (span) => setSelectedSpan(span)
  const handleCloseSidebar = () => setSelectedSpan(null)

  // Direct trace ID lookup
  const handleTraceIdSearch = (e) => {
    e.preventDefault()
    const id = traceIdSearch.trim()
    if (!id) return
    selectTrace(id)
    navigate(`/traces/${id}`)
  }

  return (
    <div className="view">
      <div className="view-header">
        <h1 className="view-title">Traces</h1>
        <button className="btn btn-ghost btn-sm" onClick={loadList} disabled={listLoading}>
          {listLoading ? <Spinner size="sm" /> : '↺ Refresh'}
        </button>
      </div>

      {/* ── Filter bar ─────────────────────────────────────────────────── */}
      <div className="filter-bar" style={{ flexWrap: 'wrap', gap: 8 }}>
        {/* Text search */}
        <input
          className="form-input filter-search"
          type="search"
          placeholder="Search traces…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{ minWidth: 160 }}
        />

        {/* Scenario filter */}
        <select
          className="form-select"
          value={scenarioFilter}
          onChange={(e) => setScenarioFilter(e.target.value)}
        >
          {SCENARIOS.map((s) => (
            <option key={s} value={s}>{s === 'all' ? 'All scenarios' : s}</option>
          ))}
        </select>

        {/* Status filter */}
        <select
          className="form-select"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s === 'all' ? 'All statuses' : s}</option>
          ))}
        </select>

        {/* Anomaly type filter */}
        <select
          className="form-select"
          value={anomalyFilter}
          onChange={(e) => setAnomalyFilter(e.target.value)}
          title="Filter by anomaly type"
        >
          {ANOMALY_TYPES.map((a) => (
            <option key={a.value} value={a.value}>{a.label}</option>
          ))}
        </select>

        {/* Reliability score slider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <label style={{ fontSize: 12, color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>
            Min score:
          </label>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={minScore}
            onChange={(e) => setMinScore(Number(e.target.value))}
            style={{ width: 90 }}
          />
          <span style={{
            fontSize: 12, fontWeight: 700, minWidth: 36,
            color: minScore >= 80 ? 'var(--green)' : minScore >= 50 ? 'var(--orange)' : 'var(--text-muted)',
          }}>
            {minScore}%
          </span>
        </div>

        <span className="muted" style={{ fontSize: 12, marginLeft: 4 }}>
          {filtered.length} traces
        </span>
      </div>

      {/* ── Trace ID direct search ──────────────────────────────────────── */}
      <form onSubmit={handleTraceIdSearch} style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <input
          className="form-input"
          type="text"
          placeholder="Jump to trace ID…"
          value={traceIdSearch}
          onChange={(e) => setTraceIdSearch(e.target.value)}
          style={{ flex: 1, maxWidth: 380, fontSize: 12, fontFamily: 'monospace' }}
        />
        <button type="submit" className="btn btn-ghost btn-sm" disabled={!traceIdSearch.trim()}>
          Go →
        </button>
      </form>

      {/* ── Main split: table | detail ──────────────────────────────────── */}
      <div className={`trace-split${selectedId ? ' trace-split--open' : ''}`}>

        {/* Left: trace table */}
        <div className="trace-table-pane">
          {listLoading && <div className="panel-loading"><Spinner /> Loading traces…</div>}

          {!listLoading && filtered.length === 0 && (
            <EmptyState
              icon="⬡"
              title="No traces found"
              description="Adjust filters or run the Execute view to create traces."
            />
          )}

          {!listLoading && filtered.length > 0 && (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Trace ID</th>
                  <th>Task</th>
                  <th>Scenario</th>
                  <th>Reliability</th>
                  <th>Anomalies</th>
                  <th>Attack Type</th>
                  <th>Status</th>
                  <th>Spans</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => {
                  const ors = t.metrics?.overall_reliability_score
                  const pct = ors != null ? Math.round(ors * 100) : null
                  const scoreColor = pct == null ? 'var(--text-muted)' : pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--orange)' : 'var(--red)'
                  const anomalyCount = (t.anomalies ?? []).length
                  const statusLabel = t.status ||
                    (t.success ? 'OK' : t.error_count > 0 ? 'ERROR' : t.completed ? 'OK' : 'PENDING')
                  return (
                    <tr
                      key={t.trace_id}
                      className={`table-row-hover${selectedId === t.trace_id ? ' table-row--selected' : ''}`}
                      onClick={() => selectTrace(t.trace_id)}
                    >
                      <td><code className="mono">{short(t.trace_id, 14)}</code></td>
                      <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        <span title={t.task}>{short(t.task ?? '—', 35)}</span>
                      </td>
                      <td><ScenarioPill scenario={t.scenario} /></td>
                      <td>
                        {pct != null ? (
                          <span style={{ fontWeight: 700, color: scoreColor }}>{pct}%</span>
                        ) : <span className="muted">—</span>}
                      </td>
                      <td>
                        {anomalyCount > 0 ? (
                          <span style={{ color: 'var(--red)', fontWeight: 700 }}>⚠ {anomalyCount}</span>
                        ) : <span className="muted">0</span>}
                      </td>
                      <td>
                        {t.attack_type ? (
                          <span style={{ fontSize: 11, color: 'var(--orange)', fontWeight: 600 }}>
                            {t.attack_type.replace(/_/g, ' ')}
                          </span>
                        ) : <span className="muted">—</span>}
                      </td>
                      <td>
                        <StatusBadge
                          success={statusLabel.toUpperCase() === 'OK'}
                          label={statusLabel}
                        />
                      </td>
                      <td>{t.span_count ?? '—'}</td>
                      <td className="muted">{fmtTimestamp(t.start_time)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>

        {/* Right: detail panel */}
        {selectedId && (
          <div className="trace-detail-pane">
            <div className="trace-detail-header">
              <code className="mono trace-detail-id">{short(selectedId, 18)}</code>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-ghost btn-xs" onClick={() => navigate(`/graph/${selectedId}`)}>Graph</button>
                <button className="btn btn-ghost btn-xs" onClick={() => navigate(`/replay/${selectedId}`)}>Replay</button>
                <button className="btn btn-ghost btn-xs" onClick={() => { setSelectedId(null); setSelectedSpan(null) }}>✕</button>
              </div>
            </div>

            {detailLoading && <div className="panel-loading"><Spinner /> Loading spans…</div>}

            {!detailLoading && traceDetail && (
              <TraceTimeline
                spans={traceDetail.spans ?? []}
                onSelect={handleSpanSelect}
                selected={selectedSpan?.span_id}
              />
            )}

            <div style={{ marginTop: 16 }}>
              <EvalReport report={evalReport} loading={evalLoading} />
              <JudgeResultsPanel traceId={selectedId} />
            </div>

            {selectedSpan && (
              <SpanDetailSidebar span={selectedSpan} onClose={handleCloseSidebar} />
            )}
          </div>
        )}
      </div>
    </div>
  )
}
