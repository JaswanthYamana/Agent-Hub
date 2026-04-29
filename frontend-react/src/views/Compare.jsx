/**
 * Compare.jsx — Side-by-side animated trace comparison with AI explanation.
 *
 * Features:
 *  - Trace A / Trace B selectors
 *  - Graph-based diff via GET /api/traces/compare
 *  - Animated synchronized step playback (Play / Pause / Step ◀▶)
 *  - Color-coded diff rows: green=ok, red=mismatch, yellow=extra, grey=missing
 *  - AI divergence explanation panel
 *  - Diff detail table
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import useStore from '../store/useStore'
import { useAsync } from '../hooks/useAsync'
import api from '../services/api'
import { short, fmtDuration } from '../utils/format'

// ── Diff type helpers ────────────────────────────────────────────────────────

const DIFF_TYPE_META = {
  tool_mismatch:      { label: 'Mismatch',   cls: 'compare-step--mismatch', icon: '🔴' },
  missing_node:       { label: 'Missing',    cls: 'compare-step--missing',  icon: '⬜' },
  extra_node:         { label: 'Extra',      cls: 'compare-step--extra',    icon: '🟡' },
  workflow_deviation: { label: 'Reordered',  cls: 'compare-step--deviation', icon: '🔀' },
}

function diffClassForStep(stepIndex, differences) {
  const d = differences?.find((d) => d.step === stepIndex)
  return d ? DIFF_TYPE_META[d.type]?.cls ?? '' : 'compare-step--ok'
}

function diffIconForStep(stepIndex, isSideB, differences) {
  const d = differences?.find((d) => d.step === stepIndex)
  if (!d) return '✅'
  if (isSideB) {
    if (d.type === 'missing_node') return '—'
  }
  return DIFF_TYPE_META[d.type]?.icon ?? '❓'
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StepList({ steps = [], differences = [], activeStep, isSideB, listRef }) {
  return (
    <div className="compare-step-list" ref={listRef}>
      {steps.length === 0 && (
        <div className="compare-empty-lane">No steps</div>
      )}
      {steps.map((s, i) => {
        const diffCls = diffClassForStep(i, differences)
        const icon = diffIconForStep(i, isSideB, differences)
        const isActive = i === activeStep
        return (
          <div
            key={i}
            className={[
              'compare-step',
              diffCls,
              isActive ? 'compare-step--active' : '',
            ].filter(Boolean).join(' ')}
            data-step={i}
          >
            <span className="compare-step-num">{i + 1}</span>
            <div className="compare-step-body">
              <span className="compare-step-name">{s.name ?? `Step ${i + 1}`}</span>
              <span className="compare-step-kind muted">{s.kind}</span>
            </div>
            <span className="compare-step-dur muted">{fmtDuration(s.duration_ms)}</span>
            <span className="compare-step-icon">{icon}</span>
          </div>
        )
      })}
    </div>
  )
}

function ExplanationPanel({ explanation }) {
  if (!explanation) return null
  const rows = [
    { key: 'summary',       label: '📋 Summary',       color: 'var(--blue)' },
    { key: 'root_cause',    label: '🔍 Root Cause',    color: 'var(--orange)' },
    { key: 'impact',        label: '⚡ Impact',        color: 'var(--red)' },
    { key: 'suggested_fix', label: '🛠 Suggested Fix', color: 'var(--green)' },
  ]
  return (
    <div className="compare-explanation panel">
      <div className="panel-header" style={{ color: 'var(--purple)' }}>
        ✨ AI Divergence Explanation
      </div>
      <div className="compare-explanation-body">
        {rows.map(({ key, label, color }) => (
          explanation[key] && (
            <div key={key} className="compare-explanation-row">
              <div className="compare-explanation-label" style={{ color }}>{label}</div>
              <div className="compare-explanation-text">{explanation[key]}</div>
            </div>
          )
        ))}
      </div>
    </div>
  )
}

function DiffSummary({ result }) {
  const count = result?.divergence_count ?? 0
  const first = result?.first_divergence_step
  const gd    = result?.graph_diff ?? {}

  return (
    <div className="compare-summary">
      <div className="stat-grid" style={{ gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))' }}>
        <div className={`stat-card ${count === 0 ? 'green' : 'red'}`}>
          <div className="stat-label">Divergences</div>
          <div className="stat-value">{count}</div>
        </div>
        <div className={`stat-card ${first == null ? 'green' : 'orange'}`}>
          <div className="stat-label">First at Step</div>
          <div className="stat-value">{first != null ? first + 1 : '—'}</div>
        </div>
        <div className={`stat-card ${(gd.missing_nodes?.length ?? 0) > 0 ? 'red' : 'green'}`}>
          <div className="stat-label">Missing Nodes</div>
          <div className="stat-value">{gd.missing_nodes?.length ?? 0}</div>
        </div>
        <div className={`stat-card ${(gd.extra_nodes?.length ?? 0) > 0 ? 'orange' : 'green'}`}>
          <div className="stat-label">Extra Nodes</div>
          <div className="stat-value">{gd.extra_nodes?.length ?? 0}</div>
        </div>
        <div className={`stat-card ${(gd.edge_changes?.length ?? 0) > 0 ? 'orange' : 'green'}`}>
          <div className="stat-label">Edge Changes</div>
          <div className="stat-value">{gd.edge_changes?.length ?? 0}</div>
        </div>
      </div>
    </div>
  )
}

function DiffTable({ differences = [], graphDiff = {} }) {
  const { missing_nodes = [], extra_nodes = [], edge_changes = [] } = graphDiff
  return (
    <div className="compare-diff-section panel">
      <div className="panel-header">🔬 Difference Detail</div>
      <div style={{ padding: '0 0 4px', overflowX: 'auto' }}>
        {differences.length > 0 && (
          <>
            <div className="compare-diff-subtitle">Step-level differences</div>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Step</th>
                  <th>Baseline</th>
                  <th>Attacked</th>
                  <th>Type</th>
                </tr>
              </thead>
              <tbody>
                {differences.map((d, i) => {
                  const meta = DIFF_TYPE_META[d.type] ?? {}
                  return (
                    <tr key={i}>
                      <td className="font-mono">{d.step + 1}</td>
                      <td>{d.baseline}</td>
                      <td>{d.attacked}</td>
                      <td>
                        <span className={`badge badge-compare-${d.type}`}>
                          {meta.icon} {meta.label ?? d.type}
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </>
        )}

        {edge_changes.length > 0 && (
          <>
            <div className="compare-diff-subtitle" style={{ marginTop: 16 }}>Edge changes</div>
            <table className="data-table">
              <thead><tr><th>Baseline Path</th><th>Attacked Path</th></tr></thead>
              <tbody>
                {edge_changes.map((e, i) => (
                  <tr key={i}>
                    <td className="font-mono">{e.baseline}</td>
                    <td className="font-mono">{e.attacked}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}

        {missing_nodes.length > 0 && (
          <div className="compare-node-chips" style={{ marginTop: 12 }}>
            <span className="compare-diff-subtitle">Missing nodes: </span>
            {missing_nodes.map((n) => (
              <span key={n} className="badge badge-error" style={{ marginRight: 4 }}>{n}</span>
            ))}
          </div>
        )}
        {extra_nodes.length > 0 && (
          <div className="compare-node-chips" style={{ marginTop: 8 }}>
            <span className="compare-diff-subtitle">Extra nodes: </span>
            {extra_nodes.map((n) => (
              <span key={n} className="badge badge-warn" style={{ marginRight: 4 }}>{n}</span>
            ))}
          </div>
        )}

        {differences.length === 0 && edge_changes.length === 0 &&
          missing_nodes.length === 0 && extra_nodes.length === 0 && (
          <div className="empty-state" style={{ padding: '20px' }}>
            <span className="empty-icon">✅</span>
            <p>No differences detected — traces are identical.</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────

export default function Compare() {
  const toast = useStore((s) => s.toast)

  const [idA, setIdA] = useState('')
  const [idB, setIdB] = useState('')
  const [activeStep, setActiveStep] = useState(null)
  const [playing, setPlaying] = useState(false)

  const refListA = useRef(null)
  const refListB = useRef(null)
  const playTimer = useRef(null)

  const { data: traceList, execute: loadList } = useAsync(
    useCallback(() => api.listTraces(), [])
  )

  const {
    data: result,
    loading,
    error,
    execute: runCompare,
  } = useAsync(useCallback((a, b) => api.compareTraces(a, b), []))

  useEffect(() => { loadList() }, [loadList])
  useEffect(() => {
    if (error) toast(`Compare failed: ${error}`, 'error')
  }, [error, toast])

  // Reset state when result changes
  useEffect(() => {
    if (result) {
      setActiveStep(null)
      setPlaying(false)
    }
  }, [result])

  // Auto-scroll both panes to the active step
  useEffect(() => {
    if (activeStep == null) return
    ;[refListA, refListB].forEach((ref) => {
      const el = ref.current?.querySelector(`[data-step="${activeStep}"]`)
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    })
  }, [activeStep])

  // Play animation
  useEffect(() => {
    if (!playing || !result) return
    const stepsA = result.trace_a?.steps ?? []
    const stepsB = result.trace_b?.steps ?? []
    const maxSteps = Math.max(stepsA.length, stepsB.length)

    playTimer.current = setInterval(() => {
      setActiveStep((prev) => {
        const next = (prev ?? -1) + 1
        if (next >= maxSteps) {
          setPlaying(false)
          return prev
        }
        return next
      })
    }, 750)
    return () => clearInterval(playTimer.current)
  }, [playing, result])

  const stepsA = result?.trace_a?.steps ?? []
  const stepsB = result?.trace_b?.steps ?? []
  const maxSteps = Math.max(stepsA.length, stepsB.length)
  const differences = result?.differences ?? []

  const handleCompare = () => {
    if (!idA.trim() || !idB.trim()) {
      toast('Select both traces before comparing.', 'warn')
      return
    }
    if (idA === idB) {
      toast('Select two different traces.', 'warn')
      return
    }
    setActiveStep(null)
    setPlaying(false)
    runCompare(idA, idB)
  }

  const stepPrev = () => setActiveStep((s) => Math.max(0, (s ?? 1) - 1))
  const stepNext = () => setActiveStep((s) => Math.min(maxSteps - 1, (s ?? -1) + 1))

  return (
    <div className="view">
      {/* Header */}
      <div className="view-header">
        <h1 className="view-title">⟺ Trace Comparison</h1>
        {result && (
          <div className="compare-legend">
            {[
              { cls: 'compare-dot--ok',       label: 'Identical' },
              { cls: 'compare-dot--mismatch', label: 'Mismatch' },
              { cls: 'compare-dot--extra',    label: 'Extra' },
              { cls: 'compare-dot--missing',  label: 'Missing' },
            ].map(({ cls, label }) => (
              <span key={label} className="compare-legend-item">
                <span className={`compare-dot ${cls}`} />
                {label}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Trace selectors */}
      <div className="panel compare-selectors">
        <div className="compare-selector-col">
          <label className="form-label">Trace A — Baseline</label>
          <select
            className="form-select"
            value={idA}
            onChange={(e) => setIdA(e.target.value)}
          >
            <option value="">Select baseline trace…</option>
            {(traceList ?? []).map((t) => (
              <option key={t.trace_id} value={t.trace_id}>
                {short(t.trace_id, 22)} — {t.scenario ?? 'unknown'} {t.success ? '✅' : '❌'}
              </option>
            ))}
          </select>
        </div>

        <div className="compare-selector-vs">VS</div>

        <div className="compare-selector-col">
          <label className="form-label">Trace B — Attacked / Comparison</label>
          <select
            className="form-select"
            value={idB}
            onChange={(e) => setIdB(e.target.value)}
          >
            <option value="">Select comparison trace…</option>
            {(traceList ?? []).map((t) => (
              <option key={t.trace_id} value={t.trace_id}>
                {short(t.trace_id, 22)} — {t.scenario ?? 'unknown'} {t.success ? '✅' : '❌'}
              </option>
            ))}
          </select>
        </div>

        <button
          className="btn btn-primary"
          onClick={handleCompare}
          disabled={loading}
          style={{ alignSelf: 'flex-end', minWidth: 110 }}
        >
          {loading ? <Spinner size="sm" /> : '⟺ Compare'}
        </button>
      </div>

      {/* Empty state */}
      {!result && !loading && (
        <EmptyState
          icon="⟺"
          title="No comparison loaded"
          description="Select two traces above and click Compare to see where they diverged."
        />
      )}

      {loading && (
        <div className="loading-row">
          <Spinner /> Running graph-based comparison…
        </div>
      )}

      {result && (
        <>
          {/* Summary stats */}
          <DiffSummary result={result} />

          {/* Side-by-side step timelines */}
          <div className="panel compare-layout">
            <div className="compare-pane-header">
              <div className="compare-pane-title">
                📍 Baseline: <span className="font-mono text-blue">{short(result.trace_a?.trace_id, 18)}</span>
                <span className="muted" style={{ marginLeft: 8 }}>({stepsA.length} steps)</span>
              </div>
              <div className="compare-pane-title">
                ⚔ Attacked: <span className="font-mono text-red">{short(result.trace_b?.trace_id, 18)}</span>
                <span className="muted" style={{ marginLeft: 8 }}>({stepsB.length} steps)</span>
              </div>
            </div>

            <div className="compare-panes">
              <StepList
                steps={stepsA}
                differences={differences}
                activeStep={activeStep}
                isSideB={false}
                listRef={refListA}
              />
              <div className="compare-pane-divider" />
              <StepList
                steps={stepsB}
                differences={differences}
                activeStep={activeStep}
                isSideB={true}
                listRef={refListB}
              />
            </div>

            {/* Animation controls */}
            <div className="compare-controls">
              <button
                className="btn btn-secondary compare-ctrl-btn"
                onClick={() => { setPlaying(false); setActiveStep(0) }}
                title="Go to first step"
              >⏮</button>
              <button
                className="btn btn-secondary compare-ctrl-btn"
                onClick={stepPrev}
                disabled={activeStep === 0 || activeStep == null}
                title="Previous step"
              >◀</button>

              <button
                className={`btn compare-ctrl-btn ${playing ? 'btn-danger' : 'btn-primary'}`}
                onClick={() => setPlaying((p) => !p)}
                title={playing ? 'Pause' : 'Play animation'}
                style={{ minWidth: 80 }}
              >
                {playing ? '⏸ Pause' : '▶ Play'}
              </button>

              <button
                className="btn btn-secondary compare-ctrl-btn"
                onClick={stepNext}
                disabled={activeStep != null && activeStep >= maxSteps - 1}
                title="Next step"
              >▶</button>
              <button
                className="btn btn-secondary compare-ctrl-btn"
                onClick={() => { setPlaying(false); setActiveStep(maxSteps - 1) }}
                title="Go to last step"
              >⏭</button>

              <span className="compare-step-counter muted">
                {activeStep != null
                  ? `Step ${activeStep + 1} / ${maxSteps}`
                  : `${maxSteps} total steps`}
              </span>
            </div>
          </div>

          {/* AI Explanation */}
          <ExplanationPanel explanation={result.explanation} />

          {/* Diff detail */}
          <DiffTable
            differences={differences}
            graphDiff={result.graph_diff ?? {}}
          />
        </>
      )}
    </div>
  )
}
