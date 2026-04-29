/**
 * EvalReport — Displays the reliability evaluation for a trace.
 *
 * Props:
 *   report  — result from GET /api/traces/:id/evaluate
 *   loading — bool
 */
import { Spinner } from '../ui/Spinner'

function ScoreGauge({ score }) {
  const pct = Math.round((score ?? 0) * 100)
  const color =
    pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--orange)' : 'var(--red)'
  return (
    <div className="eval-gauge">
      <svg viewBox="0 0 120 70" className="eval-gauge-svg">
        {/* Background arc */}
        <path
          d="M10,65 A55,55 0 0,1 110,65"
          fill="none"
          stroke="var(--bg-card)"
          strokeWidth="12"
          strokeLinecap="round"
        />
        {/* Foreground arc */}
        <path
          d="M10,65 A55,55 0 0,1 110,65"
          fill="none"
          stroke={color}
          strokeWidth="12"
          strokeLinecap="round"
          strokeDasharray={`${pct * 1.73} 173`}
          style={{ transition: 'stroke-dasharray 0.6s ease' }}
        />
        <text x="60" y="68" textAnchor="middle" className="eval-gauge-value" fill={color}>
          {pct}
        </text>
      </svg>
      <div className="eval-gauge-label">Reliability Score</div>
    </div>
  )
}

function MetricPill({ label, value, max = 1 }) {
  const pct = Math.round((value ?? 0) / max * 100)
  const color =
    pct >= 80 ? 'var(--green)' : pct >= 50 ? 'var(--orange)' : 'var(--red)'
  return (
    <div className="eval-metric-pill">
      <span className="eval-metric-label">{label}</span>
      <span className="eval-metric-value" style={{ color }}>{pct}%</span>
    </div>
  )
}

export default function EvalReport({ report, loading }) {
  if (loading) return <div className="eval-loading"><Spinner /> Running evaluation…</div>
  if (!report)  return null

  const detections = report.detections ?? {}
  const metrics = report.metrics ?? {}

  return (
    <div className="eval-report">
      <ScoreGauge score={report.reliability_score} />

      {/* Per-dimension metrics */}
      {Object.keys(metrics).length > 0 && (
        <div className="eval-metrics-grid">
          {Object.entries(metrics).map(([k, v]) => (
            <MetricPill key={k} label={k.replace(/_/g, ' ')} value={v} />
          ))}
        </div>
      )}

      {/* Judge assessments */}
      {report.scenario && (
        <div className="eval-scenario">
          <span className="muted">Scenario: </span>
          <strong>{report.scenario}</strong>
        </div>
      )}

      {Object.keys(detections).length > 0 && (
        <div className="eval-detections">
          <div className="eval-section-title">Attack Detections</div>
          {Object.entries(detections).map(([name, detected]) => (
            <div key={name} className={`eval-detection ${detected ? 'detected' : 'clean'}`}>
              <span className="eval-detection-icon">{detected ? '⚠' : '✓'}</span>
              {name.replace(/_/g, ' ')}
            </div>
          ))}
        </div>
      )}

      {report.judge_notes && (
        <div className="eval-notes">
          <div className="eval-section-title">Judge Notes</div>
          <p className="eval-notes-text">{report.judge_notes}</p>
        </div>
      )}
    </div>
  )
}
