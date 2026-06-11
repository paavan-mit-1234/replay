import { useCallback, useEffect, useRef, useState } from 'react'
import {
  getStats,
  getTimeseries,
  listModels,
  listRequests,
  type Filters,
  type RequestRow,
  type Stats,
  type TimeBucket,
} from './api'
import Budget from './Budget'
import Charts from './Charts'
import RequestDetailView from './RequestDetailView'

type Range = '24h' | '7d' | '30d' | 'all'

const RANGES: { key: Range; label: string; hours: number | null; bucket: 'hour' | 'day' }[] = [
  { key: '24h', label: '24h', hours: 24, bucket: 'hour' },
  { key: '7d', label: '7d', hours: 24 * 7, bucket: 'day' },
  { key: '30d', label: '30d', hours: 24 * 30, bucket: 'day' },
  { key: 'all', label: 'all', hours: null, bucket: 'day' },
]

function FilterBar({
  range,
  setRange,
  model,
  setModel,
  models,
  errorsOnly,
  setErrorsOnly,
}: {
  range: Range
  setRange: (r: Range) => void
  model: string
  setModel: (m: string) => void
  models: string[]
  errorsOnly: boolean
  setErrorsOnly: (v: boolean) => void
}) {
  return (
    <div className="filterbar">
      <div className="seg">
        {RANGES.map((r) => (
          <button
            key={r.key}
            className={`seg__btn ${range === r.key ? 'on' : ''}`}
            onClick={() => setRange(r.key)}
          >
            {r.label}
          </button>
        ))}
      </div>
      <select
        className="input"
        style={{ width: 'auto', padding: '6px 28px 6px 10px' }}
        value={model}
        onChange={(e) => setModel(e.target.value)}
      >
        <option value="">all models</option>
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      <button
        className={`seg__btn ${errorsOnly ? 'on' : ''}`}
        onClick={() => setErrorsOnly(!errorsOnly)}
      >
        errors only
      </button>
    </div>
  )
}

function fmtCost(v: number | null): string {
  return v === null ? '-' : v.toFixed(6)
}

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-GB', { hour12: false })
}

function StatusTag({ row }: { row: RequestRow }) {
  if (row.error) return <span className="tag tag--err">ERR</span>
  const s = row.status_code ?? 0
  if (s >= 200 && s < 300) return <span className="tag tag--ok">{s}</span>
  if (s === 429) return <span className="tag tag--warn">{s}</span>
  if (s >= 400) return <span className="tag tag--err">{s}</span>
  return <span className="tag tag--info">{s || '-'}</span>
}

function Gauges({ stats }: { stats: Stats | null }) {
  const spend = stats ? stats.spend_usd.toFixed(6) : '0.000000'
  const reqs = stats ? stats.request_count : 0
  const med = stats?.median_latency_ms ?? null
  const errPct = stats ? (stats.error_rate * 100).toFixed(1) : '0.0'
  return (
    <div className="gauges">
      <div className="gauge gauge--spend">
        <div className="kicker">cost / spend</div>
        <div>
          <span className="gauge__value">{spend}</span>
          <span className="gauge__unit"> usd</span>
        </div>
      </div>
      <div className="gauge">
        <div className="kicker">signal / requests</div>
        <div>
          <span className="gauge__value">{reqs}</span>
        </div>
      </div>
      <div className="gauge">
        <div className="kicker">latency / median</div>
        <div>
          <span className="gauge__value">{med ?? '-'}</span>
          <span className="gauge__unit"> ms</span>
        </div>
      </div>
      <div className="gauge gauge--errors">
        <div className="kicker">signal / error rate</div>
        <div>
          <span className="gauge__value">{errPct}</span>
          <span className="gauge__unit"> %</span>
        </div>
      </div>
    </div>
  )
}

function Stream({ rows, onSelect }: { rows: RequestRow[]; onSelect: (id: string) => void }) {
  return (
    <div className="stream">
      <table className="signal">
        <thead>
          <tr>
            <th>time</th>
            <th>provider</th>
            <th>model</th>
            <th>status</th>
            <th className="num">in</th>
            <th className="num">out</th>
            <th className="num">cost usd</th>
            <th className="num">ms</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={8} className="muted">
                no signal yet. point your app's base_url at replay and send a call.
              </td>
            </tr>
          )}
          {rows.map((r, i) => (
            <tr
              key={r.id}
              className={`clickrow ${i === 0 ? 'playhead' : ''}`}
              onClick={() => onSelect(r.id)}
            >
              <td>{fmtTime(r.created_at)}</td>
              <td>{r.provider}</td>
              <td>{r.model}</td>
              <td>
                <StatusTag row={r} />
              </td>
              <td className="num">{r.input_tokens ?? '-'}</td>
              <td className="num">{r.output_tokens ?? '-'}</td>
              <td className="num">{fmtCost(r.cost_usd)}</td>
              <td className="num">{r.latency_ms ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [rows, setRows] = useState<RequestRow[]>([])
  const [series, setSeries] = useState<TimeBucket[]>([])
  const [models, setModels] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)

  const [range, setRange] = useState<Range>('7d')
  const [model, setModel] = useState('')
  const [errorsOnly, setErrorsOnly] = useState(false)

  const rangeDef = RANGES.find((r) => r.key === range) ?? RANGES[1]
  const since =
    rangeDef.hours != null
      ? new Date(Date.now() - rangeDef.hours * 3600_000).toISOString()
      : null
  // Primitive deps so the poller is stable across renders.
  const fkey = `${since ?? ''}|${model}|${errorsOnly}|${rangeDef.bucket}`
  // Drop responses from a superseded filter so a slow reply cannot clobber a
  // newer one (filters change faster than the 3s poll completes).
  const seq = useRef(0)

  const poll = useCallback(async () => {
    const mine = ++seq.current
    try {
      const f: Filters = { since, model: model || null, errorsOnly }
      const [s, r, t] = await Promise.all([
        getStats(f),
        listRequests(f, 40),
        getTimeseries(f, rangeDef.bucket),
      ])
      if (mine !== seq.current) return
      setStats(s)
      setRows(r)
      setSeries(t)
      setError(null)
    } catch (e) {
      if (mine === seq.current) setError(e instanceof Error ? e.message : String(e))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fkey])

  useEffect(() => {
    listModels().then(setModels).catch(() => {})
  }, [])

  useEffect(() => {
    poll()
    if (!live) return
    const id = setInterval(poll, 3000)
    return () => clearInterval(id)
  }, [live, poll])

  return (
    <>
      {error && (
        <div className="panel" style={{ marginBottom: 24, borderColor: 'var(--coral)' }}>
          <span className="tag tag--err">error</span> <span className="mono">{error}</span>
        </div>
      )}
      <Budget />
      <FilterBar
        range={range}
        setRange={setRange}
        model={model}
        setModel={setModel}
        models={models}
        errorsOnly={errorsOnly}
        setErrorsOnly={setErrorsOnly}
      />
      <Gauges stats={stats} />
      <Charts data={series} />
      <div className="section-head">
        <div>
          <div className="kicker">signal / transport</div>
          <h2 className="display" style={{ fontSize: 22 }}>
            live request stream
          </h2>
        </div>
        <div className="row-between">
          {live && <div style={{ width: 110 }} className="tape" />}
          <button className="btn btn--ghost" onClick={() => setLive((v) => !v)}>
            {live ? 'pause' : 'play'}
          </button>
        </div>
      </div>
      <Stream rows={rows} onSelect={setSelected} />
      {selected && <RequestDetailView id={selected} onClose={() => setSelected(null)} />}
    </>
  )
}
