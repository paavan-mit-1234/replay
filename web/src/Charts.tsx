import type { TimeBucket } from './api'

interface SeriesProps {
  label: string
  data: TimeBucket[]
  pick: (b: TimeBucket) => number | null
  format: (v: number) => string
  color: string
}

// A hand-drawn bar chart in the analog-lab style: hard-edged columns on a
// baseline, mono labels, no gridlines or rounded corners. SVG scales to its box.
function BarChart({ label, data, pick, format, color }: SeriesProps) {
  const W = 320
  const H = 120
  const pad = 6
  const values = data.map((b) => pick(b) ?? 0)
  const max = Math.max(...values, 0)
  const total = values.reduce((a, v) => a + v, 0)
  const peak = max > 0 ? max : 1
  const n = Math.max(values.length, 1)
  const slot = (W - pad * 2) / n
  const barW = Math.max(slot * 0.7, 2)

  return (
    <div className="chart">
      <div className="row-between" style={{ alignItems: 'baseline' }}>
        <span className="kicker" style={{ margin: 0 }}>
          {label}
        </span>
        <span className="mono chart__peak">peak {format(max)}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="chart__svg">
        <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} className="chart__axis" />
        {values.map((v, i) => {
          const h = (v / peak) * (H - pad * 2)
          const x = pad + i * slot + (slot - barW) / 2
          const y = H - pad - h
          return <rect key={i} x={x} y={y} width={barW} height={Math.max(h, v > 0 ? 2 : 0)} fill={color} />
        })}
      </svg>
      <div className="mono chart__foot">
        {data.length > 0 ? `${data.length} buckets / total ${format(total)}` : 'no data in range'}
      </div>
    </div>
  )
}

export default function Charts({ data }: { data: TimeBucket[] }) {
  return (
    <div className="charts">
      <BarChart
        label="trend / spend usd"
        data={data}
        pick={(b) => b.spend_usd}
        format={(v) => v.toFixed(4)}
        color="var(--coral)"
      />
      <BarChart
        label="trend / requests"
        data={data}
        pick={(b) => b.requests}
        format={(v) => String(Math.round(v))}
        color="var(--ink)"
      />
      <BarChart
        label="trend / median latency ms"
        data={data}
        pick={(b) => b.median_latency_ms}
        format={(v) => `${Math.round(v)}`}
        color="var(--cobalt)"
      />
    </div>
  )
}
