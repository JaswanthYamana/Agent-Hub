/**
 * Analytics.jsx – Reliability Analytics (Time-Series) view.
 *
 * Shows time-series charts for all key reliability metrics plus a
 * degradation detection banner when regressions are identified.
 */
import { useState, useEffect, useCallback } from 'react'
import {
  LineChart, Line,
  BarChart, Bar,
  AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine,
} from 'recharts'
import api from '../services/api'
import { Spinner } from '../components/ui/Spinner'

// ── Constants ────────────────────────────────────────────────────────────

const RANGE_OPTIONS = [
  { label: '24h', value: 1,  granularity: 'hour' },
  { label: '7d',  value: 7,  granularity: 'day'  },
  { label: '30d', value: 30, granularity: 'day'  },
  { label: '90d', value: 90, granularity: 'day'  },
]

const METRIC_LABELS = {
  overall_reliability_score: 'Overall Reliability (ORS)',
  tool_selection_accuracy:   'Tool Selection Accuracy',
  parameter_correctness:     'Parameter Correctness',
  task_completion_rate:      'Task Completion Rate',
  anomaly_count:             'Anomaly Count',
  attack_success_rate:       'Attack Success Rate',
}

const PCT_METRICS = new Set([
  'overall_reliability_score',
  'tool_selection_accuracy',
  'parameter_correctness',
  'task_completion_rate',
  'attack_success_rate',
])

// ── Helpers ───────────────────────────────────────────────────────────────

function fmt(val, metric) {
  if (val == null) return '—'
  if (PCT_METRICS.has(metric)) return `${(val * 100).toFixed(1)}%`
  return Number(val).toFixed(2)
}

function fmtPct(val) {
  if (val == null) return '—'
  return `${(val * 100).toFixed(1)}%`
}

function scoreColor(val) {
  if (val == null) return '#94a3b8'
  if (val >= 0.8) return '#22c55e'
  if (val >= 0.6) return '#f59e0b'
  return '#ef4444'
}

// ── Sub-components ────────────────────────────────────────────────────────

function SummaryCard({ label, avg, min, max, metricKey, samples }) {
  const color = PCT_METRICS.has(metricKey) ? scoreColor(avg) : '#60a5fa'
  return (
    <div className="card" style={{ flex: '1 1 160px', minWidth: 160 }}>
      <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color, lineHeight: 1.1 }}>
        {fmt(avg, metricKey)}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>
        ↓ {fmt(min, metricKey)} &nbsp;·&nbsp; ↑ {fmt(max, metricKey)}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
        {samples ?? '—'} samples
      </div>
    </div>
  )
}

function DegradationBanner({ report }) {
  if (!report) return null
  const { degraded, anomaly_spike, reason, recent_avg, baseline_avg, delta } = report
  if (!degraded && !anomaly_spike) return null

  const issues = []
  if (degraded) issues.push(`Reliability regression: ${reason}`)
  if (anomaly_spike) issues.push(
    `Anomaly spike: recent avg ${report.recent_anomaly_rate?.toFixed(2)} vs baseline ${report.baseline_anomaly_rate?.toFixed(2)}`
  )

  return (
    <div style={{
      background: 'rgba(239,68,68,0.12)',
      border: '1px solid #ef4444',
      borderRadius: 8,
      padding: '12px 16px',
      marginBottom: 20,
      display: 'flex',
      alignItems: 'flex-start',
      gap: 10,
    }}>
      <span style={{ fontSize: 20 }}>⚠️</span>
      <div>
        <div style={{ fontWeight: 600, color: '#ef4444', marginBottom: 4 }}>
          Reliability Degradation Detected
        </div>
        {issues.map((msg, i) => (
          <div key={i} style={{ fontSize: 13, color: 'var(--text-muted)' }}>{msg}</div>
        ))}
        <div style={{ fontSize: 12, marginTop: 6, color: 'var(--text-muted)' }}>
          Recent avg: <b>{fmtPct(recent_avg)}</b> &nbsp;·&nbsp;
          Baseline avg: <b>{fmtPct(baseline_avg)}</b> &nbsp;·&nbsp;
          Delta: <b style={{ color: '#ef4444' }}>{delta != null ? (delta * 100).toFixed(2) + '%' : '—'}</b>
        </div>
      </div>
    </div>
  )
}

function TrendTooltip({ active, payload, label, metricKey }) {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border)',
      borderRadius: 6,
      padding: '8px 12px',
      fontSize: 12,
    }}>
      <div style={{ marginBottom: 4, color: 'var(--text-muted)' }}>{label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} style={{ color: p.color }}>
          {p.name}: <b>{fmt(p.value, metricKey)}</b>
        </div>
      ))}
    </div>
  )
}

// Format x-axis labels
function xTickFmt(val, granularity) {
  if (!val) return ''
  try {
    if (granularity === 'hour') {
      // "2026-03-10T14:00" → "10 14h"
      const parts = val.split('T')
      return `${parts[0].slice(8)} ${parts[1]?.slice(0, 5) ?? ''}`
    }
    // "2026-03-10" → "Mar 10"
    const d = new Date(val + 'T00:00:00Z')
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
  } catch { return val }
}

// ── Main view ─────────────────────────────────────────────────────────────

export default function Analytics() {
  const [rangeIdx, setRangeIdx]     = useState(1)   // default 7d
  const [loading, setLoading]       = useState(false)
  const [trends, setTrends]         = useState({})
  const [summary, setSummary]       = useState({})
  const [degradation, setDegr]      = useState(null)
  const [error, setError]           = useState(null)

  const { value: range, granularity } = RANGE_OPTIONS[rangeIdx]

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [allTrends, summaryData, dgrReport] = await Promise.all([
        api.getAllTrends({ range, granularity }),
        api.getMetricsSummary({ range }),
        api.getDegradationReport({ recent_n: 5, baseline_n: 20 }),
      ])
      setTrends(allTrends)
      setSummary(summaryData)
      setDegr(dgrReport)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [range, granularity])

  useEffect(() => { load() }, [load])

  // ── Render helpers ─────────────────────────────────────────────────────

  const reliabilityMetrics = ['overall_reliability_score', 'tool_selection_accuracy', 'parameter_correctness', 'task_completion_rate']
  const COLORS = ['#60a5fa', '#34d399', '#f59e0b', '#a78bfa', '#f472b6', '#38bdf8']

  // Build combined reliability chart data (all four metrics on one chart)
  const combinedData = (() => {
    const keys = reliabilityMetrics
    const allBuckets = new Set()
    keys.forEach(k => (trends[k] || []).forEach(d => allBuckets.add(d.timestamp)))
    const sorted = [...allBuckets].sort()
    return sorted.map(ts => {
      const row = { timestamp: ts }
      keys.forEach(k => {
        const pt = (trends[k] || []).find(d => d.timestamp === ts)
        row[k] = pt ? pt.value : null
      })
      return row
    })
  })()

  const anomalyData = (trends.anomaly_count || []).map(d => ({ ...d, timestamp: d.timestamp }))
  const asrData     = (trends.attack_success_rate || []).map(d => ({ ...d, timestamp: d.timestamp }))

  const hasData = combinedData.length > 0 || anomalyData.length > 0 || asrData.length > 0

  return (
    <div style={{ padding: '24px 32px', maxWidth: 1280 }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>Reliability Analytics</h1>
          <p style={{ margin: '4px 0 0', color: 'var(--text-muted)', fontSize: 14 }}>
            Time-series observability — track agent behavior across executions
          </p>
        </div>

        {/* Range selector */}
        <div style={{ display: 'flex', gap: 6 }}>
          {RANGE_OPTIONS.map((opt, i) => (
            <button
              key={opt.label}
              className={`btn ${i === rangeIdx ? 'btn-primary' : 'btn-ghost'}`}
              style={{ padding: '6px 14px', fontSize: 13 }}
              onClick={() => setRangeIdx(i)}
            >
              {opt.label}
            </button>
          ))}
          <button
            className="btn btn-ghost"
            style={{ padding: '6px 12px' }}
            onClick={load}
            title="Refresh"
          >
            ↻
          </button>
        </div>
      </div>

      {/* Degradation banner */}
      <DegradationBanner report={degradation} />

      {/* Error */}
      {error && (
        <div className="card" style={{ color: '#ef4444', marginBottom: 16 }}>
          ⚠ {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 60 }}>
          <Spinner />
        </div>
      )}

      {!loading && (
        <>
          {/* Summary cards */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 28 }}>
            {[
              'overall_reliability_score',
              'tool_selection_accuracy',
              'parameter_correctness',
              'task_completion_rate',
              'anomaly_count',
              'attack_success_rate',
            ].map(key => {
              const s = summary[key]
              return (
                <SummaryCard
                  key={key}
                  metricKey={key}
                  label={METRIC_LABELS[key] || key}
                  avg={s?.avg}
                  min={s?.min}
                  max={s?.max}
                  samples={s?.sample_count}
                />
              )
            })}
          </div>

          {!hasData && (
            <div className="card" style={{ textAlign: 'center', padding: 48, color: 'var(--text-muted)' }}>
              <div style={{ fontSize: 40, marginBottom: 12 }}>📈</div>
              <div style={{ fontSize: 16, fontWeight: 600 }}>No time-series data yet</div>
              <div style={{ fontSize: 13, marginTop: 6 }}>
                Run some agent executions and the charts will populate automatically.
              </div>
            </div>
          )}

          {hasData && (
            <>
              {/* ── Chart 1: Combined reliability metrics ── */}
              <div className="card" style={{ marginBottom: 24 }}>
                <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 16 }}>
                  Reliability Metrics Over Time
                </div>
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart data={combinedData} margin={{ top: 5, right: 16, bottom: 5, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis
                      dataKey="timestamp"
                      tickFormatter={v => xTickFmt(v, granularity)}
                      tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                    />
                    <YAxis
                      domain={[0, 1]}
                      tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                      tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                      width={42}
                    />
                    <Tooltip content={<TrendTooltip metricKey="overall_reliability_score" />} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <ReferenceLine y={0.8} stroke="#22c55e" strokeDasharray="4 4" strokeOpacity={0.5} label={{ value: '80%', position: 'right', fontSize: 10, fill: '#22c55e' }} />
                    {reliabilityMetrics.map((key, i) => (
                      <Line
                        key={key}
                        type="monotone"
                        dataKey={key}
                        name={METRIC_LABELS[key]}
                        stroke={COLORS[i]}
                        strokeWidth={2}
                        dot={{ r: 3 }}
                        activeDot={{ r: 5 }}
                        connectNulls
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>

              {/* ── Charts 2 & 3 side by side ── */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 24 }}>

                {/* Anomaly count */}
                <div className="card">
                  <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 16 }}>
                    Anomaly Count Over Time
                  </div>
                  {anomalyData.length === 0 ? (
                    <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '20px 0' }}>No data</div>
                  ) : (
                    <ResponsiveContainer width="100%" height={220}>
                      <BarChart data={anomalyData} margin={{ top: 5, right: 8, bottom: 5, left: 0 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                        <XAxis
                          dataKey="timestamp"
                          tickFormatter={v => xTickFmt(v, granularity)}
                          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        />
                        <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} width={30} allowDecimals={false} />
                        <Tooltip
                          content={({ active, payload, label }) =>
                            active && payload?.length ? (
                              <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', borderRadius: 6, padding: '8px 12px', fontSize: 12 }}>
                                <div style={{ color: 'var(--text-muted)', marginBottom: 4 }}>{label}</div>
                                <div style={{ color: '#f59e0b' }}>Avg anomalies: <b>{payload[0]?.value?.toFixed(2)}</b></div>
                              </div>
                            ) : null
                          }
                        />
                        <Bar dataKey="value" name="Avg anomaly count" fill="#f59e0b" radius={[3, 3, 0, 0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  )}
                </div>

                {/* Attack success rate */}
                <div className="card">
                  <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 16 }}>
                    Attack Success Rate (ASR) Over Time
                  </div>
                  {asrData.length === 0 ? (
                    <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '20px 0' }}>
                      No red-team data — run red-team attacks to populate
                    </div>
                  ) : (
                    <ResponsiveContainer width="100%" height={220}>
                      <AreaChart data={asrData} margin={{ top: 5, right: 8, bottom: 5, left: 0 }}>
                        <defs>
                          <linearGradient id="asrGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#ef4444" stopOpacity={0.03} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                        <XAxis
                          dataKey="timestamp"
                          tickFormatter={v => xTickFmt(v, granularity)}
                          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        />
                        <YAxis
                          domain={[0, 1]}
                          tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                          width={42}
                        />
                        <Tooltip content={<TrendTooltip metricKey="attack_success_rate" />} />
                        <Area
                          type="monotone"
                          dataKey="value"
                          name="Attack Success Rate"
                          stroke="#ef4444"
                          strokeWidth={2}
                          fill="url(#asrGrad)"
                          dot={{ r: 3 }}
                          connectNulls
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  )}
                </div>
              </div>

              {/* ── Degradation table ── */}
              {degradation && (
                <div className="card" style={{ marginBottom: 24 }}>
                  <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 14 }}>
                    Degradation Analysis — Overall Reliability Score
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
                    {[
                      { label: 'Regression Detected', value: degradation.degraded ? '⚠ YES' : '✓ No', color: degradation.degraded ? '#ef4444' : '#22c55e' },
                      { label: 'Anomaly Spike', value: degradation.anomaly_spike ? '⚠ YES' : '✓ No', color: degradation.anomaly_spike ? '#f59e0b' : '#22c55e' },
                      { label: `Recent ${degradation.recent_avg != null ? `(${5} runs)` : ''} Avg`, value: fmtPct(degradation.recent_avg) },
                      { label: 'Baseline Avg', value: fmtPct(degradation.baseline_avg) },
                      { label: 'Delta', value: degradation.delta != null ? `${(degradation.delta * 100).toFixed(2)}%` : '—', color: degradation.delta < 0 ? '#ef4444' : '#22c55e' },
                      { label: 'Threshold', value: fmtPct(degradation.threshold) },
                    ].map(({ label, value, color }) => (
                      <div key={label} style={{ minWidth: 140 }}>
                        <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 2 }}>{label}</div>
                        <div style={{ fontSize: 16, fontWeight: 600, color: color || 'var(--text)' }}>{value}</div>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: 12, fontSize: 12, color: 'var(--text-muted)' }}>
                    {degradation.reason}
                  </div>
                </div>
              )}

              {/* ── ORS area chart (standalone, prominent) ── */}
              {(trends.overall_reliability_score || []).length > 0 && (
                <div className="card">
                  <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 16 }}>
                    Overall Reliability Score (ORS) — Detailed Trend
                  </div>
                  <ResponsiveContainer width="100%" height={240}>
                    <AreaChart
                      data={trends.overall_reliability_score}
                      margin={{ top: 5, right: 16, bottom: 5, left: 0 }}
                    >
                      <defs>
                        <linearGradient id="orsGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%"  stopColor="#60a5fa" stopOpacity={0.3} />
                          <stop offset="95%" stopColor="#60a5fa" stopOpacity={0.03} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                      <XAxis
                        dataKey="timestamp"
                        tickFormatter={v => xTickFmt(v, granularity)}
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                      />
                      <YAxis
                        domain={[0, 1]}
                        tickFormatter={v => `${(v * 100).toFixed(0)}%`}
                        tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                        width={42}
                      />
                      <Tooltip content={<TrendTooltip metricKey="overall_reliability_score" />} />
                      <ReferenceLine y={0.8} stroke="#22c55e" strokeDasharray="4 4" strokeOpacity={0.6} label={{ value: 'Target 80%', position: 'insideTopRight', fontSize: 10, fill: '#22c55e' }} />
                      <Area
                        type="monotone"
                        dataKey="value"
                        name="ORS"
                        stroke="#60a5fa"
                        strokeWidth={2.5}
                        fill="url(#orsGrad)"
                        dot={{ r: 4 }}
                        activeDot={{ r: 6 }}
                        connectNulls
                      />
                      <Area
                        type="monotone"
                        dataKey="min"
                        name="Min"
                        stroke="#60a5fa"
                        strokeWidth={1}
                        strokeDasharray="3 3"
                        fill="none"
                        dot={false}
                        connectNulls
                      />
                      <Area
                        type="monotone"
                        dataKey="max"
                        name="Max"
                        stroke="#60a5fa"
                        strokeWidth={1}
                        strokeDasharray="3 3"
                        fill="none"
                        dot={false}
                        connectNulls
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  )
}
