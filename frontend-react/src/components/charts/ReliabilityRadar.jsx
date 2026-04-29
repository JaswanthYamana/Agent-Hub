/**
 * ReliabilityRadar — Recharts radar for per-dimension reliability scores.
 *
 * Props:
 *   metrics  — object { key: 0‒1, … }  (from evaluate endpoint)
 */
import {
  RadarChart,
  Radar,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'

export default function ReliabilityRadar({ metrics = {} }) {
  const data = Object.entries(metrics).map(([key, value]) => ({
    subject: key.replace(/_/g, ' '),
    value: Math.round((value ?? 0) * 100),
    fullMark: 100,
  }))

  if (!data.length) return (
    <div className="chart-empty">No metric data available.</div>
  )

  return (
    <ResponsiveContainer width="100%" height={280}>
      <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
        <PolarGrid stroke="var(--border)" />
        <PolarAngleAxis
          dataKey="subject"
          tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
        />
        <PolarRadiusAxis
          angle={30}
          domain={[0, 100]}
          tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
          tickCount={4}
        />
        <Radar
          name="Score"
          dataKey="value"
          stroke="var(--blue)"
          fill="var(--blue)"
          fillOpacity={0.25}
          strokeWidth={2}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            color: 'var(--text-primary)',
            fontSize: 12,
          }}
          formatter={(v) => [`${v}%`, 'Score']}
        />
      </RadarChart>
    </ResponsiveContainer>
  )
}
