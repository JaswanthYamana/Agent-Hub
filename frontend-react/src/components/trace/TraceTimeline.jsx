/**
 * TraceTimeline — CSS-based Gantt chart for a single trace's spans.
 *
 * Props:
 *   spans      — array of span objects from GET /api/traces/:id
 *   onSelect   — (span) => void   called when a span row is clicked
 *   selected   — currently selected span id (or null)
 */
import { useMemo } from 'react'
import { fmtDuration, kindColor } from '../../utils/format'

export default function TraceTimeline({ spans = [], onSelect, selected }) {
  const { minT, range } = useMemo(() => {
    if (!spans.length) return { minT: 0, range: 1 }
    const starts = spans.map((s) => s.start_time ?? 0)
    const ends   = spans.map((s) => (s.start_time ?? 0) + (s.duration_ms ?? 0))
    const minT   = Math.min(...starts)
    const maxT   = Math.max(...ends)
    return { minT, range: Math.max(maxT - minT, 1) }
  }, [spans])

  if (!spans.length) return (
    <div className="gantt-empty">No spans available.</div>
  )

  return (
    <div className="gantt">
      {/* Header ruler */}
      <div className="gantt-ruler">
        <div className="gantt-label-col" />
        <div className="gantt-bar-col">
          {[0, 25, 50, 75, 100].map((pct) => (
            <span key={pct} style={{ left: `${pct}%` }} className="gantt-tick">
              {fmtDuration(range * pct / 100)}
            </span>
          ))}
        </div>
      </div>

      {/* Span rows */}
      {spans.map((span) => {
        const left  = range > 0 ? ((span.start_time ?? 0) - minT) / range * 100 : 0
        const width = range > 0 ? (span.duration_ms ?? 0) / range * 100 : 2
        const isErr = (span.status || '').toUpperCase() === 'ERROR'
        const isAnomaly = span.is_anomalous
        const color = isErr ? 'var(--red)' : isAnomaly ? 'var(--orange)' : kindColor(span.kind)
        const isSel = selected && selected === span.span_id

        return (
          <div
            key={span.span_id}
            className={`gantt-row${isSel ? ' gantt-row--selected' : ''}`}
            onClick={() => onSelect?.(span)}
          >
            <div className="gantt-label" title={span.name}>
              <span className="gantt-kind" style={{ color: kindColor(span.kind) }}>
                {(span.kind || 'SPAN')[0]}
              </span>
              {span.name}
            </div>
            <div className="gantt-track">
              <div
                className="gantt-bar"
                style={{
                  left: `${Math.min(left, 99)}%`,
                  width: `${Math.max(width, 0.5)}%`,
                  background: color,
                  opacity: isErr || isAnomaly ? 1 : 0.82,
                }}
                title={`${span.name} — ${fmtDuration(span.duration_ms)}`}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
