/**
 * ToolDistChart — Recharts doughnut / bar for tool-call distribution.
 *
 * Props:
 *   data  — array of { tool, count } objects
 */
import {
  PieChart,
  Pie,
  Cell,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

const COLORS = [
  'var(--blue)',
  'var(--green)',
  'var(--purple)',
  'var(--orange)',
  '#e06c75',
  '#56b6c2',
  '#98c379',
  '#c678dd',
]

export default function ToolDistChart({ data = [] }) {
  if (!data.length) return (
    <div className="chart-empty">No tool calls recorded.</div>
  )

  const total = data.reduce((s, d) => s + (d.count ?? 0), 0)

  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie
          data={data}
          dataKey="count"
          nameKey="tool"
          cx="50%"
          cy="50%"
          innerRadius="55%"
          outerRadius="80%"
          paddingAngle={2}
          label={({ tool, count }) => `${tool} (${((count / total) * 100).toFixed(0)}%)`}
          labelLine={false}
        >
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            color: 'var(--text-primary)',
            fontSize: 12,
          }}
          formatter={(v, name) => [v, name]}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 11, color: 'var(--text-secondary)' }}
        />
      </PieChart>
    </ResponsiveContainer>
  )
}
