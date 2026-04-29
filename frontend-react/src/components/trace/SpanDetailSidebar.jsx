/**
 * SpanDetailSidebar — Details panel for a selected span.
 *
 * Props:
 *   span     — span object (or null to hide)
 *   onClose  — () => void
 */
import { KindBadge, StatusBadge } from '../ui/Badge'
import { fmtDuration, fmtTimestamp } from '../../utils/format'

function Row({ label, children }) {
  return (
    <div className="span-detail-row">
      <span className="span-detail-key">{label}</span>
      <span className="span-detail-val">{children}</span>
    </div>
  )
}

function JsonBlock({ value }) {
  if (value == null) return <span className="muted">—</span>
  let text
  try { text = JSON.stringify(value, null, 2) } catch { text = String(value) }
  return <pre className="code-block" style={{ maxHeight: 200 }}>{text}</pre>
}

export default function SpanDetailSidebar({ span, onClose }) {
  if (!span) return null

  return (
    <aside className="span-detail">
      <div className="span-detail-header">
        <span className="span-detail-title">{span.name}</span>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>✕</button>
      </div>

      <div className="span-detail-body">
        <Row label="Span ID">
          <code className="mono">{span.span_id}</code>
        </Row>
        <Row label="Trace ID">
          <code className="mono">{span.trace_id}</code>
        </Row>
        {span.parent_id && (
          <Row label="Parent ID">
            <code className="mono">{span.parent_id}</code>
          </Row>
        )}
        <Row label="Kind">
          <KindBadge kind={span.kind} />
        </Row>
        <Row label="Status">
          <StatusBadge success={(span.status || '').toUpperCase() === 'OK'} label={span.status} />
        </Row>
        <Row label="Duration">{fmtDuration(span.duration_ms)}</Row>
        <Row label="Start">{fmtTimestamp(span.start_time)}</Row>

        {span.is_anomalous && (
          <div className="span-detail-warning">
            ⚠ Flagged as anomalous
          </div>
        )}

        {span.input != null && (
          <div className="span-detail-section">
            <div className="span-detail-section-title">Input</div>
            <JsonBlock value={span.input} />
          </div>
        )}

        {span.output != null && (
          <div className="span-detail-section">
            <div className="span-detail-section-title">Output</div>
            <JsonBlock value={span.output} />
          </div>
        )}

        {span.error && (
          <div className="span-detail-section">
            <div className="span-detail-section-title" style={{ color: 'var(--red)' }}>
              Error
            </div>
            <pre className="code-block error-block">{span.error}</pre>
          </div>
        )}

        {span.attributes && Object.keys(span.attributes).length > 0 && (
          <div className="span-detail-section">
            <div className="span-detail-section-title">Attributes</div>
            <JsonBlock value={span.attributes} />
          </div>
        )}
      </div>
    </aside>
  )
}
