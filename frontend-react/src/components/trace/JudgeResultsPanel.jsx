import { useEffect, useState } from 'react'
import api from '../../services/api'

// Verdict → CSS colour variable
const VERDICT_COLOR = {
  PASS: 'var(--green)',
  WARN: 'var(--orange)',
  FAIL: 'var(--red)',
}

const DIMENSIONS = [
  { key: 'tool_selection',         label: 'Tool Selection' },
  { key: 'parameter_correctness',  label: 'Parameter Correctness' },
  { key: 'reasoning_faithfulness', label: 'Reasoning Faithfulness' },
  { key: 'workflow_order',         label: 'Workflow Order' },
  { key: 'task_completion',        label: 'Task Completion' },
]

function VerdictBadge({ verdict }) {
  const color = VERDICT_COLOR[verdict] ?? 'var(--fg-muted)'
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 10px',
      borderRadius: 12,
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: '0.05em',
      color: '#fff',
      background: color,
      minWidth: 44,
      textAlign: 'center',
    }}>
      {verdict ?? '—'}
    </span>
  )
}

export default function JudgeResultsPanel({ traceId }) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState(null)

  useEffect(() => {
    if (!traceId) return
    let cancelled = false
    setLoading(true)
    setData(null)
    setError(null)
    api.getJudgeResults(traceId)
      .then(res => { if (!cancelled) setData(res) })
      .catch(err => { if (!cancelled) setError(err.message ?? 'Failed to load judge results') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [traceId])

  if (!traceId)  return null
  if (loading)   return <p style={{ color: 'var(--fg-muted)', padding: '12px 0' }}>Loading judge results…</p>
  if (error)     return <p style={{ color: 'var(--red)', padding: '12px 0' }}>Judge error: {error}</p>
  if (!data?.judge_result) return null

  const r = data.judge_result
  const overallColor = VERDICT_COLOR[r.overall_verdict] ?? 'var(--fg-muted)'
  const sourceLabel  = r.source === 'llm'
    ? `LLM · ${r.model ?? 'unknown model'}`
    : 'Rule-based fallback'
  const confidence   = r.confidence_score != null
    ? ` · confidence ${Math.round(r.confidence_score * 100)}%`
    : ''

  return (
    <section style={{ marginTop: 24 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
        <h3 style={{ margin: 0, fontSize: 14, fontWeight: 700 }}>LLM Judge</h3>
        <VerdictBadge verdict={r.overall_verdict} />
        <span style={{ fontSize: 11, color: 'var(--fg-muted)', marginLeft: 'auto' }}>
          {sourceLabel}{confidence}
        </span>
      </div>

      {/* Dimension rows */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr auto',
        gap: '6px 12px',
        alignItems: 'center',
        background: 'var(--bg-card)',
        borderRadius: 8,
        padding: '12px 16px',
      }}>
        {DIMENSIONS.map(({ key, label }) => (
          <>
            <span key={`lbl-${key}`} style={{ fontSize: 12, color: 'var(--fg-muted)' }}>
              {label}
            </span>
            <VerdictBadge key={`badge-${key}`} verdict={r[key]} />
          </>
        ))}
      </div>

      {/* Explanation */}
      {r.explanation && (
        <p style={{
          marginTop: 10,
          fontSize: 12,
          color: 'var(--fg-muted)',
          lineHeight: 1.6,
          padding: '10px 14px',
          background: 'var(--bg-card)',
          borderRadius: 8,
          borderLeft: `3px solid ${overallColor}`,
        }}>
          {r.explanation}
        </p>
      )}
    </section>
  )
}
