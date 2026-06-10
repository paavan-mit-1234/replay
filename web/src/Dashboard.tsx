import { useCallback, useEffect, useState } from 'react'
import { getStats, listRequests, type RequestRow, type Stats } from './api'
import RequestDetailView from './RequestDetailView'

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
  const [error, setError] = useState<string | null>(null)
  const [live, setLive] = useState(true)
  const [selected, setSelected] = useState<string | null>(null)

  const poll = useCallback(async () => {
    try {
      const [s, r] = await Promise.all([getStats(), listRequests(40)])
      setStats(s)
      setRows(r)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    if (!live) return
    poll()
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
      <Gauges stats={stats} />
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
