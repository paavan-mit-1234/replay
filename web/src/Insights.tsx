import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { generateFingerprint, getInsightStats, type InsightStats } from './api'

function Gauges({ stats }: { stats: InsightStats | null }) {
  const good = stats ? stats.good_feedback : 0
  const bad = stats ? stats.bad_feedback : 0
  const rated = good + bad
  const goodPct = rated > 0 ? ((good / rated) * 100).toFixed(0) : null
  return (
    <div className="gauges">
      <div className="gauge gauge--spend">
        <div className="kicker">you / prompts asked</div>
        <div>
          <span className="gauge__value">{stats?.prompts_sent ?? 0}</span>
        </div>
      </div>
      <div className="gauge">
        <div className="kicker">you / chats</div>
        <div>
          <span className="gauge__value">{stats?.conversations ?? 0}</span>
        </div>
      </div>
      <div className="gauge">
        <div className="kicker">you / answers rated good</div>
        <div>
          <span className="gauge__value">{goodPct ?? '-'}</span>
          {goodPct !== null && <span className="gauge__unit"> %</span>}
        </div>
      </div>
      <div className="gauge">
        <div className="kicker">you / days active</div>
        <div>
          <span className="gauge__value">{stats?.days_active ?? 0}</span>
        </div>
      </div>
    </div>
  )
}

export default function Insights() {
  const [stats, setStats] = useState<InsightStats | null>(null)
  const [fingerprint, setFingerprint] = useState<string | null>(null)
  const [reading, setReading] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    getInsightStats()
      .then(setStats)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
  }, [])

  async function read() {
    if (reading) return
    setReading(true)
    setErr(null)
    try {
      const { markdown } = await generateFingerprint()
      setFingerprint(markdown)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setReading(false)
    }
  }

  return (
    <>
      <Gauges stats={stats} />
      <div className="section-head">
        <div>
          <div className="kicker">you / fingerprint</div>
          <h2 className="display" style={{ fontSize: 22 }}>
            your prompt fingerprint
          </h2>
        </div>
        <button className="btn" onClick={read} disabled={reading}>
          {reading ? 'reading…' : fingerprint ? 'read again' : 'read my fingerprint'}
        </button>
      </div>

      {err && (
        <div className="panel" style={{ marginBottom: 24, borderColor: 'var(--coral)' }}>
          <span className="tag tag--err">error</span> <span className="mono">{err}</span>
        </div>
      )}

      {fingerprint ? (
        <div className="panel md-output md-light">
          <ReactMarkdown>{fingerprint}</ReactMarkdown>
        </div>
      ) : (
        <div className="panel">
          <p className="muted" style={{ margin: 0 }}>
            Replay reads your recent prompts and writes back a profile of how you ask:
            your style, your topics, the habits worth upgrading, and a personal cheat
            sheet of prompts tailored to you. Nothing leaves your workspace.
          </p>
        </div>
      )}
    </>
  )
}
