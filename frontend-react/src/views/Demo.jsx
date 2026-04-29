/**
 * Demo.jsx — Guided 3-step demo showing the full observability story:
 *   Step 1: Normal Agent Run → high reliability, no anomalies
 *   Step 2: Prompt Injection Attack → low reliability, anomaly detected
 *   Step 3: Compare Executions → side-by-side graph diff
 */
import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Spinner } from '../components/ui/Spinner'
import { SeverityBadge } from '../components/ui/Badge'
import useStore from '../store/useStore'
import api from '../services/api'
import { fmtDuration } from '../utils/format'

// ─── Score ring ───────────────────────────────────────────────────────────────
function ScoreRing({ score }) {
  const pct = score != null ? Math.round(score * 100) : null
  const color = pct == null ? 'var(--text-muted)' : pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--orange)' : 'var(--red)'
  const radius = 36
  const circ = 2 * Math.PI * radius
  const dash = pct != null ? (pct / 100) * circ : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4 }}>
      <svg width={88} height={88} viewBox="0 0 88 88">
        <circle cx={44} cy={44} r={radius} fill="none" stroke="var(--border)" strokeWidth={8} />
        {pct != null && (
          <circle
            cx={44} cy={44} r={radius}
            fill="none"
            stroke={color}
            strokeWidth={8}
            strokeDasharray={`${dash} ${circ}`}
            strokeLinecap="round"
            transform="rotate(-90 44 44)"
            style={{ transition: 'stroke-dasharray 0.6s ease' }}
          />
        )}
        <text x={44} y={44} textAnchor="middle" dominantBaseline="middle"
          style={{ fill: color, fontSize: 16, fontWeight: 700, fontFamily: 'monospace' }}>
          {pct != null ? `${pct}%` : '—'}
        </text>
      </svg>
      <span style={{ fontSize: 11, color: 'var(--text-secondary)' }}>Reliability</span>
    </div>
  )
}

// ─── Span row ─────────────────────────────────────────────────────────────────
function SpanRow({ span, highlight }) {
  const isErr = (span.status || '').toUpperCase() === 'ERROR'
  const isAnomaly = span.is_anomalous || span.contains_injection
  const kindColors = {
    TOOL: 'var(--blue)', LLM: 'var(--purple)', AGENT: 'var(--green)',
    RETRIEVER: 'var(--teal)', CHAIN: 'var(--orange)',
  }
  const kindColor = kindColors[(span.kind || '').toUpperCase()] || 'var(--text-secondary)'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '6px 10px', borderRadius: 6, marginBottom: 4,
      background: highlight ? 'rgba(248,81,73,0.1)' : 'var(--bg-elevated)',
      border: `1px solid ${highlight ? 'var(--red)' : 'var(--border)'}`,
    }}>
      <span style={{ fontSize: 10, color: kindColor, fontWeight: 700, width: 70, flexShrink: 0 }}>
        {(span.kind || 'TOOL').toUpperCase()}
      </span>
      <span style={{ flex: 1, fontSize: 13, color: isErr ? 'var(--red)' : 'var(--text-primary)', fontWeight: isAnomaly ? 600 : 400 }}>
        {span.name}
        {isAnomaly && <span style={{ marginLeft: 6, color: 'var(--red)', fontSize: 11 }}>⚠ anomalous</span>}
      </span>
      <span style={{ fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
        {fmtDuration(span.duration_ms)}
      </span>
      <span style={{
        fontSize: 10, padding: '1px 6px', borderRadius: 4, fontWeight: 600,
        background: isErr ? 'rgba(248,81,73,0.2)' : 'rgba(63,185,80,0.15)',
        color: isErr ? 'var(--red)' : 'var(--green)',
      }}>
        {(span.status || 'OK').toUpperCase()}
      </span>
    </div>
  )
}

// ─── Anomaly row ──────────────────────────────────────────────────────────────
function AnomalyRow({ anomaly }) {
  const sevColor = { critical: 'var(--red)', high: 'var(--orange)', medium: 'var(--yellow, var(--orange))', low: 'var(--text-muted)' }
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '8px 12px', borderRadius: 6, marginBottom: 6,
      background: 'rgba(248,81,73,0.08)', border: '1px solid var(--red)',
    }}>
      <span style={{ fontSize: 16 }}>⚠</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          {(anomaly.anomaly_type || anomaly.type || 'UNKNOWN').replace(/_/g, ' ')}
        </div>
        {anomaly.description && (
          <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{anomaly.description}</div>
        )}
      </div>
      <SeverityBadge severity={anomaly.severity || 'medium'} />
    </div>
  )
}

// ─── Metric breakdown bar ─────────────────────────────────────────────────────
function MetricBar({ label, value }) {
  const pct = value != null ? Math.round(value * 100) : 0
  const color = pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--orange)' : 'var(--red)'
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{label.replace(/_/g, ' ')}</span>
        <span style={{ fontSize: 12, fontWeight: 700, color }}>{pct}%</span>
      </div>
      <div style={{ height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: 3, transition: 'width 0.5s ease' }} />
      </div>
    </div>
  )
}

// ─── Run result panel ─────────────────────────────────────────────────────────
function ResultPanel({ title, accent, result, evalData }) {
  const spans = result?.spans ?? []
  const anomalies = result?.anomalies ?? (evalData?.anomalies ?? [])
  const metrics = evalData?.metrics ?? (result?.metrics ?? {})
  const ors = metrics.overall_reliability_score ?? null
  const METRIC_LABELS = {
    tool_selection_accuracy: 'Tool Selection',
    parameter_correctness: 'Parameter Correctness',
    task_completion_rate: 'Task Completion',
    workflow_correctness: 'Workflow Correctness',
  }

  return (
    <div style={{
      flex: 1, background: 'var(--bg-surface)', border: `1px solid ${accent}`,
      borderRadius: 10, padding: 20, minWidth: 0,
    }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: accent, marginBottom: 16 }}>{title}</div>

      {/* Score + metrics */}
      <div style={{ display: 'flex', gap: 20, marginBottom: 20, alignItems: 'flex-start' }}>
        <ScoreRing score={ors} />
        <div style={{ flex: 1 }}>
          {Object.entries(METRIC_LABELS).map(([key, label]) => (
            metrics[key] != null && <MetricBar key={key} label={label} value={metrics[key]} />
          ))}
          {Object.keys(metrics).filter(k => !METRIC_LABELS[k] && k !== 'overall_reliability_score' && k !== 'anomaly_penalty').length === 0 &&
            Object.keys(metrics).length === 0 && (
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Metrics loading…</span>
            )}
        </div>
      </div>

      {/* Anomalies */}
      {anomalies.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
            ANOMALIES DETECTED ({anomalies.length})
          </div>
          {anomalies.map((a, i) => <AnomalyRow key={i} anomaly={a} />)}
        </div>
      )}
      {anomalies.length === 0 && ors != null && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 8, padding: '8px 12px',
          background: 'rgba(63,185,80,0.1)', border: '1px solid var(--green)', borderRadius: 6, marginBottom: 16,
        }}>
          <span>✅</span>
          <span style={{ fontSize: 13, color: 'var(--green)' }}>No anomalies detected</span>
        </div>
      )}

      {/* Spans */}
      {spans.length > 0 && (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
            EXECUTION TRACE ({spans.length} spans)
          </div>
          <div style={{ maxHeight: 240, overflowY: 'auto' }}>
            {spans.map((s, i) => <SpanRow key={s.span_id ?? i} span={s} highlight={s.is_anomalous || s.contains_injection} />)}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Compare diff panel ───────────────────────────────────────────────────────
function CompareDiff({ diff, normalTrace, attackTrace }) {
  if (!diff && !normalTrace && !attackTrace) return null

  const normalSpans = normalTrace?.spans ?? []
  const attackSpans = attackTrace?.spans ?? []

  // Find divergent spans from diff
  const divergentNames = new Set(
    (diff?.diffs ?? []).filter(d => d.diverged).map(d => d.step_name)
  )

  return (
    <div style={{ display: 'flex', gap: 16 }}>
      {/* Baseline */}
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--green)', marginBottom: 10 }}>
          ✅ Baseline Execution
        </div>
        <div style={{ maxHeight: 300, overflowY: 'auto' }}>
          {normalSpans.map((s, i) => (
            <SpanRow key={s.span_id ?? i} span={s} highlight={false} />
          ))}
        </div>
      </div>

      {/* Divider */}
      <div style={{ width: 1, background: 'var(--border)' }} />

      {/* Attacked */}
      <div style={{ flex: 1 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--red)', marginBottom: 10 }}>
          ☣ Attacked Execution
        </div>
        <div style={{ maxHeight: 300, overflowY: 'auto' }}>
          {attackSpans.map((s, i) => (
            <SpanRow
              key={s.span_id ?? i}
              span={s}
              highlight={divergentNames.has(s.name) || s.is_anomalous || s.contains_injection}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Step container ───────────────────────────────────────────────────────────
function StepCard({ number, title, subtitle, done, active, children }) {
  return (
    <div style={{
      background: 'var(--bg-surface)',
      border: `1px solid ${done ? 'var(--green)' : active ? 'var(--blue)' : 'var(--border)'}`,
      borderRadius: 10, marginBottom: 20, overflow: 'hidden',
    }}>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 14, padding: '16px 20px',
        background: done ? 'rgba(63,185,80,0.06)' : active ? 'rgba(88,166,255,0.06)' : 'transparent',
        borderBottom: children ? '1px solid var(--border)' : 'none',
      }}>
        <div style={{
          width: 32, height: 32, borderRadius: '50%', flexShrink: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 14, fontWeight: 700,
          background: done ? 'var(--green)' : active ? 'var(--blue)' : 'var(--bg-card)',
          color: (done || active) ? '#000' : 'var(--text-secondary)',
        }}>
          {done ? '✓' : number}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)' }}>{title}</div>
          {subtitle && <div style={{ fontSize: 12, color: 'var(--text-secondary)', marginTop: 2 }}>{subtitle}</div>}
        </div>
      </div>
      {children && <div style={{ padding: '16px 20px' }}>{children}</div>}
    </div>
  )
}

// ─── Main Demo view ───────────────────────────────────────────────────────────
const DEMO_TASK = 'Book cheapest flight to Delhi tomorrow and send confirmation email'

export default function Demo() {
  const navigate = useNavigate()
  const toast = useStore((s) => s.toast)

  // Step 1 — normal run
  const [step1Loading, setStep1Loading] = useState(false)
  const [normalResult, setNormalResult] = useState(null)
  const [normalEval, setNormalEval] = useState(null)
  const [normalTraceId, setNormalTraceId] = useState(null)

  // Step 2 — attack run
  const [step2Loading, setStep2Loading] = useState(false)
  const [attackResult, setAttackResult] = useState(null)
  const [attackEval, setAttackEval] = useState(null)
  const [attackTraceId, setAttackTraceId] = useState(null)

  // Step 3 — compare
  const [step3Loading, setStep3Loading] = useState(false)
  const [compareData, setCompareData] = useState(null)
  const [normalFull, setNormalFull] = useState(null)
  const [attackFull, setAttackFull] = useState(null)

  const step1Done = normalResult != null
  const step2Done = attackResult != null
  const step3Done = compareData != null || (normalFull != null && attackFull != null)

  // ── Step 1: Normal run ─────────────────────────────────────────────────────
  const runNormal = useCallback(async () => {
    setStep1Loading(true)
    setNormalResult(null)
    setNormalEval(null)
    setNormalTraceId(null)
    try {
      const result = await api.execute({ task: DEMO_TASK, scenario: 'normal', k_trials: 1 })
      setNormalResult(result)
      const tid = result.trace_id
      setNormalTraceId(tid)
      if (tid) {
        const ev = await api.evaluateTrace(tid)
        setNormalEval(ev)
      }
      toast('Normal agent run complete.', 'success')
    } catch (e) {
      toast(`Step 1 failed: ${e.message}`, 'error')
    } finally {
      setStep1Loading(false)
    }
  }, [toast])

  // ── Step 2: Attack run ─────────────────────────────────────────────────────
  const runAttack = useCallback(async () => {
    setStep2Loading(true)
    setAttackResult(null)
    setAttackEval(null)
    setAttackTraceId(null)
    try {
      const result = await api.runRedteam({ attack_type: 'prompt_injection', target_scenario: 'normal', intensity: 'high' })
      setAttackResult(result)
      const tid = result.trace_id
      setAttackTraceId(tid)
      if (tid) {
        const ev = await api.evaluateTrace(tid)
        setAttackEval(ev)
      }
      toast('Attack simulation complete.', 'success')
    } catch (e) {
      toast(`Step 2 failed: ${e.message}`, 'error')
    } finally {
      setStep2Loading(false)
    }
  }, [toast])

  // ── Step 3: Compare ────────────────────────────────────────────────────────
  const runCompare = useCallback(async () => {
    if (!normalTraceId || !attackTraceId) {
      toast('Complete Steps 1 and 2 first.', 'warn')
      return
    }
    setStep3Loading(true)
    setCompareData(null)
    setNormalFull(null)
    setAttackFull(null)
    try {
      const [diff, nFull, aFull] = await Promise.all([
        api.compareReplays(normalTraceId, attackTraceId).catch(() => null),
        api.getTrace(normalTraceId),
        api.getTrace(attackTraceId),
      ])
      setCompareData(diff)
      setNormalFull(nFull)
      setAttackFull(aFull)
      toast('Comparison complete.', 'success')
    } catch (e) {
      toast(`Step 3 failed: ${e.message}`, 'error')
    } finally {
      setStep3Loading(false)
    }
  }, [normalTraceId, attackTraceId, toast])

  // ── Reliability drop calculation ──────────────────────────────────────────
  const normalScore = normalEval?.metrics?.overall_reliability_score
  const attackScore = attackEval?.metrics?.overall_reliability_score

  return (
    <div className="view">
      {/* ── Header ── */}
      <div className="view-header" style={{ marginBottom: 24 }}>
        <div>
          <h1 className="view-title" style={{ fontSize: 22, marginBottom: 4 }}>
            🚀 AI Agent Flight Recorder — Live Demo
          </h1>
          <p style={{ color: 'var(--text-secondary)', fontSize: 13, margin: 0 }}>
            Watch how an AI agent behaves normally, gets compromised by an attack, and how our platform detects it.
          </p>
        </div>
      </div>

      {/* ── Story banner ── */}
      <div style={{
        display: 'flex', gap: 0, marginBottom: 28, borderRadius: 10, overflow: 'hidden',
        border: '1px solid var(--border)',
      }}>
        {[
          { icon: '▶', label: 'Normal Run', sub: 'Reliable execution', color: 'var(--green)', done: step1Done },
          { icon: '→', label: '', sub: '', color: 'var(--border)', arrow: true },
          { icon: '☣', label: 'Attack Injected', sub: 'Reliability drops', color: 'var(--red)', done: step2Done },
          { icon: '→', label: '', sub: '', color: 'var(--border)', arrow: true },
          { icon: '🔍', label: 'Platform Detects', sub: 'Compare & explain', color: 'var(--blue)', done: step3Done },
        ].map((item, i) =>
          item.arrow ? (
            <div key={i} style={{ display: 'flex', alignItems: 'center', padding: '0 8px', background: 'var(--bg-elevated)', color: 'var(--text-muted)', fontSize: 18 }}>›</div>
          ) : (
            <div key={i} style={{
              flex: 1, padding: '14px 20px', background: item.done ? `${item.color}18` : 'var(--bg-elevated)',
              borderLeft: i === 0 ? 'none' : '1px solid var(--border)',
              transition: 'background 0.4s',
            }}>
              <div style={{ fontSize: 20, marginBottom: 4 }}>{item.done ? '✅' : item.icon}</div>
              <div style={{ fontSize: 13, fontWeight: 700, color: item.done ? item.color : 'var(--text-primary)' }}>{item.label}</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{item.sub}</div>
            </div>
          )
        )}
      </div>

      {/* ── Step 1 ── */}
      <StepCard
        number="1"
        title="Run Normal Agent"
        subtitle={`Task: "${DEMO_TASK}"`}
        done={step1Done}
        active={!step1Done}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: step1Done ? 20 : 0 }}>
          <button
            className="btn btn-primary"
            onClick={runNormal}
            disabled={step1Loading}
            style={{ minWidth: 180 }}
          >
            {step1Loading ? <><Spinner size="sm" /> Running…</> : '▶  Run Normal Agent'}
          </button>
          {step1Loading && <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Executing agent task…</span>}
          {step1Done && !step1Loading && (
            <span style={{ color: 'var(--green)', fontSize: 13 }}>
              ✓ Complete — Trace: <code style={{ fontSize: 12 }}>{normalTraceId?.slice(0, 16)}…</code>
            </span>
          )}
          {normalTraceId && (
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/traces/${normalTraceId}`)}>
              View Trace
            </button>
          )}
        </div>

        {step1Done && (
          <ResultPanel
            title="Normal Execution Result"
            accent="var(--green)"
            result={normalResult}
            evalData={normalEval}
          />
        )}
      </StepCard>

      {/* ── Step 2 ── */}
      <StepCard
        number="2"
        title="Run Prompt Injection Attack"
        subtitle="Attack type: PROMPT_INJECTION — simulates adversarial input hijacking the agent's goal"
        done={step2Done}
        active={step1Done && !step2Done}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: step2Done ? 20 : 0 }}>
          <button
            className="btn btn-danger"
            onClick={runAttack}
            disabled={step2Loading}
            style={{ minWidth: 220 }}
          >
            {step2Loading ? <><Spinner size="sm" /> Attacking…</> : '☣  Run Prompt Injection Attack'}
          </button>
          {step2Loading && <span style={{ color: 'var(--text-secondary)', fontSize: 13 }}>Simulating adversarial attack…</span>}
          {step2Done && !step2Loading && (
            <span style={{ color: 'var(--red)', fontSize: 13 }}>
              ⚠ Attack complete — anomalies introduced
            </span>
          )}
          {attackTraceId && (
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/traces/${attackTraceId}`)}>
              View Trace
            </button>
          )}
        </div>

        {step2Done && (
          <>
            {/* Reliability drop highlight */}
            {normalScore != null && attackScore != null && (
              <div style={{
                display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 16px', borderRadius: 8,
                background: 'rgba(248,81,73,0.1)', border: '1px solid var(--red)',
                marginBottom: 16,
              }}>
                <span style={{ fontSize: 13, color: 'var(--text-secondary)' }}>Reliability Drop:</span>
                <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--green)' }}>
                  {Math.round(normalScore * 100)}%
                </span>
                <span style={{ fontSize: 18, color: 'var(--text-muted)' }}>→</span>
                <span style={{ fontSize: 18, fontWeight: 700, color: 'var(--red)' }}>
                  {Math.round(attackScore * 100)}%
                </span>
                <span style={{
                  marginLeft: 4, fontSize: 12, padding: '2px 8px', borderRadius: 12,
                  background: 'var(--red)', color: '#fff', fontWeight: 700,
                }}>
                  -{Math.round((normalScore - attackScore) * 100)} pts
                </span>
              </div>
            )}
            <ResultPanel
              title="Attacked Execution Result"
              accent="var(--red)"
              result={attackResult}
              evalData={attackEval}
            />
          </>
        )}
      </StepCard>

      {/* ── Step 3 ── */}
      <StepCard
        number="3"
        title="Compare Executions"
        subtitle="Side-by-side diff of normal vs attacked trace — highlights divergence, unauthorized calls, and workflow deviations"
        done={step3Done}
        active={step1Done && step2Done && !step3Done}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: step3Done ? 20 : 0 }}>
          <button
            className="btn btn-primary"
            onClick={runCompare}
            disabled={step3Loading || !step1Done || !step2Done}
            style={{ minWidth: 200 }}
          >
            {step3Loading ? <><Spinner size="sm" /> Comparing…</> : '🔍  Compare Executions'}
          </button>
          {!step1Done || !step2Done ? (
            <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Complete Steps 1 & 2 first</span>
          ) : null}
          {step3Done && !step3Loading && (
            <span style={{ color: 'var(--blue)', fontSize: 13 }}>✓ Comparison ready</span>
          )}
        </div>

        {step3Done && (
          <CompareDiff diff={compareData} normalTrace={normalFull} attackTrace={attackFull} />
        )}
      </StepCard>

      {/* ── Bottom CTA ── */}
      {step3Done && (
        <div style={{
          background: 'linear-gradient(135deg, rgba(88,166,255,0.1), rgba(63,185,80,0.1))',
          border: '1px solid var(--border)', borderRadius: 10, padding: '20px 24px',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>
              🎯 Demo Complete
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              The platform recorded agent execution, detected the attack, and explained the failure.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/analytics')}>View Analytics</button>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/redteam')}>Red Team Lab</button>
            <button className="btn btn-primary btn-sm" onClick={() => navigate('/traces')}>Explore Traces</button>
          </div>
        </div>
      )}
    </div>
  )
}
