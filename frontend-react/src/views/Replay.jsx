/**
 * Replay view — step-through debugger for a trace replay.
 *
 * Keyboard: ← prev step, → next step, Space advance
 */
import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { KindBadge, StatusBadge } from '../components/ui/Badge'
import { Spinner } from '../components/ui/Spinner'
import { EmptyState } from '../components/ui/EmptyState'
import useStore from '../store/useStore'
import { useAsync } from '../hooks/useAsync'
import { useKeyboard } from '../hooks/useKeyboard'
import api from '../services/api'
import { short, fmtDuration, fmtTimestamp } from '../utils/format'

function FrameDetail({ frame }) {
  if (!frame) return null
  // Normalize backend field names (span_name, span_kind, etc.) to display-friendly names
  const name       = frame.span_name  ?? frame.name  ?? ''
  const kind       = frame.span_kind  ?? frame.kind  ?? ''
  const status     = frame.span_status ?? frame.status ?? ''
  const duration   = frame.duration_ms
  const input      = frame.tool_params  ?? frame.llm_input  ?? frame.input  ?? null
  const output     = frame.tool_response ?? frame.llm_output ?? frame.output ?? null
  const errorMsg   = frame.error_message ?? frame.error ?? null
  const isAnomaly  = frame.is_anomalous ?? frame.contains_injection ?? false

  return (
    <div className="replay-frame-detail">
      <div className="replay-frame-header">
        <KindBadge kind={kind} />
        <span className="replay-frame-name">{name}</span>
        <StatusBadge success={status.toUpperCase() === 'OK'} label={status} />
        <span className="muted">{fmtDuration(duration)}</span>
      </div>
      {input != null && (
        <div className="replay-frame-section">
          <div className="replay-frame-section-title">Input</div>
          <pre className="code-block">{JSON.stringify(input, null, 2)}</pre>
        </div>
      )}
      {output != null && (
        <div className="replay-frame-section">
          <div className="replay-frame-section-title">Output</div>
          <pre className="code-block">{JSON.stringify(output, null, 2)}</pre>
        </div>
      )}
      {errorMsg && (
        <div className="replay-frame-section">
          <div className="replay-frame-section-title" style={{ color: 'var(--red)' }}>Error</div>
          <pre className="code-block error-block">{errorMsg}</pre>
        </div>
      )}
      {frame.state_snapshot && Object.keys(frame.state_snapshot).length > 0 && (
        <div className="replay-frame-section">
          <div className="replay-frame-section-title">State Snapshot</div>
          <pre className="code-block">{JSON.stringify(frame.state_snapshot, null, 2)}</pre>
        </div>
      )}
      {isAnomaly && (
        <div className="replay-anomaly-banner">⚠ Anomaly / injection detected at this step</div>
      )}
    </div>
  )
}

export default function Replay() {
  const { traceId: urlId } = useParams()
  const navigate = useNavigate()
  const toast    = useStore((s) => s.toast)

  const [traceId, setTraceId]   = useState(urlId ?? '')
  const [inputId, setInputId]   = useState(urlId ?? '')
  const [step,    setStep]      = useState(0)

  // Trace list
  const { data: traceList, execute: loadList } = useAsync(
    useCallback(() => api.listTraces(), [])
  )

  // Full replay manifest
  const { data: replay, loading: replayLoading, error, execute: loadReplay } = useAsync(
    useCallback((id) => api.getReplay(id), [])
  )

  // Current frame detail
  const { data: frame, loading: frameLoading, execute: loadFrame } = useAsync(
    useCallback((id, s) => api.getReplayFrame(id, s), [])
  )

  useEffect(() => { loadList() }, [loadList])
  useEffect(() => { if (error) toast(`Replay load failed: ${error}`, 'error') }, [error, toast])

  // Load when traceId set from URL
  useEffect(() => {
    if (urlId) { setTraceId(urlId); setInputId(urlId); loadReplay(urlId) }
  }, [urlId]) // eslint-disable-line

  // Load frame whenever step changes
  useEffect(() => {
    if (traceId && replay) loadFrame(traceId, step)
  }, [step, traceId, replay]) // eslint-disable-line

  const steps = replay?.frames ?? []
  const total = steps.length

  // Helper: get display name/kind/status from a frame object
  const frameName   = (f) => f?.span_name   ?? f?.name   ?? `Step`
  const frameKind   = (f) => f?.span_kind   ?? f?.kind   ?? ''
  const frameStatus = (f) => f?.span_status ?? f?.status ?? ''

  const prev = useCallback(() => setStep((s) => Math.max(0, s - 1)), [])
  const next = useCallback(() => setStep((s) => Math.min(total - 1, s + 1)), [total])

  // Keyboard shortcuts (arrow keys) — only active within this view
  useKeyboard(useCallback(() => ({ ArrowLeft: prev, ArrowRight: next, ' ': next }), [prev, next])())

  const handleLoad = () => {
    const id = inputId.trim()
    if (!id) { toast('Enter a trace ID.', 'warn'); return }
    setTraceId(id)
    setStep(0)
    navigate(`/replay/${id}`, { replace: true })
    loadReplay(id)
  }

  return (
    <div className="view">
      <div className="view-header">
        <h1 className="view-title">Replay Debugger</h1>
        {traceId && (
          <div className="view-header-actions">
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/traces/${traceId}`)}>Trace</button>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(`/graph/${traceId}`)}>Graph</button>
          </div>
        )}
      </div>

      {/* Trace selector */}
      <div className="panel" style={{ padding: '12px 16px', marginBottom: 16 }}>
        <div className="trace-selector">
          <select
            className="form-select"
            value={inputId}
            onChange={(e) => setInputId(e.target.value)}
            style={{ flex: 1 }}
          >
            <option value="">Select a trace…</option>
            {(traceList ?? []).map((t) => (
              <option key={t.trace_id} value={t.trace_id}>
                {short(t.trace_id, 22)} — {t.scenario ?? 'unknown'}
              </option>
            ))}
          </select>
          <button className="btn btn-primary btn-sm" onClick={handleLoad} disabled={replayLoading}>
            {replayLoading ? <Spinner size="sm" /> : 'Load'}
          </button>
        </div>
      </div>

      {!replay && !replayLoading && (
        <EmptyState
          icon="▶"
          title="No replay loaded"
          description="Select a trace above and click Load."
        />
      )}

      {replay && (
        <div className="replay-layout">
          {/* Left: step timeline */}
          <div className="replay-timeline-pane">
            <div className="replay-pane-title">Steps ({total})</div>
            <div className="replay-step-list">
              {steps.map((s, i) => {
                const isErr = frameStatus(s).toUpperCase() === 'ERROR'
                const isAnomaly = s.is_anomalous || s.contains_injection
                return (
                  <div
                    key={i}
                    className={[
                      'replay-step',
                      i === step    ? 'replay-step--active'  : '',
                      isErr         ? 'replay-step--error'   : '',
                      isAnomaly     ? 'replay-step--anomaly' : '',
                    ].filter(Boolean).join(' ')}
                    onClick={() => setStep(i)}
                  >
                    <span className="replay-step-num">{i + 1}</span>
                    <div className="replay-step-info">
                      <span className="replay-step-name">{frameName(s)}</span>
                      <span className="muted replay-step-dur">{fmtDuration(s.duration_ms)}</span>
                    </div>
                    <KindBadge kind={frameKind(s)} />
                  </div>
                )
              })}
            </div>
          </div>

          {/* Right: frame detail + controls */}
          <div className="replay-detail-pane">
            {/* Navigation controls */}
            <div className="replay-controls">
              <button
                className="btn btn-secondary replay-ctrl-btn"
                onClick={() => setStep(0)}
                disabled={step === 0}
                title="First step"
              >
                ⏮
              </button>
              <button
                className="btn btn-secondary replay-ctrl-btn"
                onClick={prev}
                disabled={step === 0}
                title="Previous (←)"
              >
                ◀
              </button>
              <span className="replay-position">
                {step + 1} / {total}
              </span>
              <button
                className="btn btn-secondary replay-ctrl-btn"
                onClick={next}
                disabled={step >= total - 1}
                title="Next (→)"
              >
                ▶
              </button>
              <button
                className="btn btn-secondary replay-ctrl-btn"
                onClick={() => setStep(total - 1)}
                disabled={step >= total - 1}
                title="Last step"
              >
                ⏭
              </button>
            </div>

            {/* Progress bar */}
            <div className="replay-progress-bar">
              <div
                className="replay-progress-fill"
                style={{ width: total > 1 ? `${(step / (total - 1)) * 100}%` : '0%' }}
              />
            </div>

            {frameLoading && <div className="panel-loading"><Spinner /> Loading frame…</div>}
            {!frameLoading && <FrameDetail frame={frame ?? steps[step]} />}

            <div className="replay-kbd-hint muted">
              Use <kbd>←</kbd> / <kbd>→</kbd> to navigate steps
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
