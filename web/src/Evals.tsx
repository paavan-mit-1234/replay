import { useCallback, useEffect, useState } from 'react'
import {
  addGolden,
  addVersion,
  createSuite,
  deleteGolden,
  deleteSuite,
  getRun,
  getSuite,
  listRuns,
  listSuites,
  startRun,
  type EvalRun,
  type EvalSuite,
  type PromptVersion,
  type RunDetail,
  type SuiteDetail,
} from './api'

const MODELS = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash']

function pct(v: number | null | undefined): string {
  return v == null ? '-' : `${Math.round(v * 100)}%`
}

function passClass(rate: number | null | undefined): string {
  if (rate == null) return ''
  if (rate >= 0.8) return 'tag tag--ok'
  if (rate >= 0.5) return 'tag tag--warn'
  return 'tag tag--err'
}

function Goldens({ detail, reload }: { detail: SuiteDetail; reload: () => void }) {
  const [input, setInput] = useState('')
  const [reference, setReference] = useState('')
  const [busy, setBusy] = useState(false)

  async function add(e: React.FormEvent) {
    e.preventDefault()
    if (!input.trim() || !reference.trim()) return
    setBusy(true)
    try {
      await addGolden(detail.id, input.trim(), reference.trim())
      setInput('')
      setReference('')
      reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel" style={{ marginBottom: 20 }}>
      <p className="kicker">suite / golden cases</p>
      <h3 className="display" style={{ fontSize: 17, marginBottom: 10 }}>
        what good looks like
      </h3>
      <table className="signal" style={{ marginBottom: 12 }}>
        <thead>
          <tr>
            <th>input</th>
            <th>expected answer</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {detail.goldens.length === 0 && (
            <tr>
              <td colSpan={3} className="muted">
                no cases yet. add the questions you want to grade against.
              </td>
            </tr>
          )}
          {detail.goldens.map((g) => (
            <tr key={g.id}>
              <td>{g.input}</td>
              <td>{g.reference}</td>
              <td>
                <button
                  className="linklike"
                  onClick={() => deleteGolden(detail.id, g.id).then(reload)}
                >
                  remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <form onSubmit={add} className="row-between" style={{ alignItems: 'flex-end', gap: 10 }}>
        <div className="field" style={{ marginBottom: 0, flex: 1 }}>
          <label>input</label>
          <input className="input" value={input} onChange={(e) => setInput(e.target.value)} />
        </div>
        <div className="field" style={{ marginBottom: 0, flex: 1 }}>
          <label>expected answer</label>
          <input
            className="input"
            value={reference}
            onChange={(e) => setReference(e.target.value)}
          />
        </div>
        <button className="btn" type="submit" disabled={busy || !input.trim() || !reference.trim()}>
          add case
        </button>
      </form>
    </div>
  )
}

function Versions({
  detail,
  reload,
  onRun,
  running,
}: {
  detail: SuiteDetail
  reload: () => void
  onRun: (v: PromptVersion) => void
  running: boolean
}) {
  const [open, setOpen] = useState(false)
  const [template, setTemplate] = useState('{input}')
  const [system, setSystem] = useState('You are a helpful assistant. Answer clearly and concisely.')
  const [model, setModel] = useState('gemini-2.5-flash')
  const [busy, setBusy] = useState(false)

  async function add(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await addVersion(detail.id, { template, system, model })
      setOpen(false)
      reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="panel" style={{ marginBottom: 20 }}>
      <div className="row-between" style={{ alignItems: 'baseline' }}>
        <div>
          <p className="kicker" style={{ margin: 0 }}>
            suite / prompt versions
          </p>
          <h3 className="display" style={{ fontSize: 17, margin: '4px 0 0' }}>
            the prompts you are testing
          </h3>
        </div>
        <button className="btn btn--ghost" onClick={() => setOpen((v) => !v)}>
          {open ? 'cancel' : 'new version'}
        </button>
      </div>

      {open && (
        <form onSubmit={add} className="version-form">
          <div className="field" style={{ marginBottom: 10 }}>
            <label>system prompt</label>
            <textarea
              className="input"
              rows={2}
              value={system}
              onChange={(e) => setSystem(e.target.value)}
            />
          </div>
          <div className="field" style={{ marginBottom: 10 }}>
            <label>template (use {'{input}'} where the case input goes)</label>
            <textarea
              className="input"
              rows={2}
              value={template}
              onChange={(e) => setTemplate(e.target.value)}
            />
          </div>
          <div className="row-between" style={{ alignItems: 'flex-end', gap: 10 }}>
            <div className="field" style={{ marginBottom: 0 }}>
              <label>model</label>
              <select className="input" value={model} onChange={(e) => setModel(e.target.value)}>
                {MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            <button className="btn" type="submit" disabled={busy}>
              save version
            </button>
          </div>
        </form>
      )}

      <table className="signal" style={{ marginTop: 12 }}>
        <thead>
          <tr>
            <th>version</th>
            <th>model</th>
            <th>system</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {detail.versions.map((v) => (
            <tr key={v.id}>
              <td className="mono">v{v.version}</td>
              <td>{v.model}</td>
              <td className="muted" style={{ maxWidth: 280 }}>
                {v.system.slice(0, 70)}
              </td>
              <td>
                <button
                  className="btn"
                  style={{ padding: '4px 12px' }}
                  disabled={running || detail.goldens.length === 0}
                  onClick={() => onRun(v)}
                >
                  run eval
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {detail.goldens.length === 0 && (
        <p className="muted mono" style={{ fontSize: 12, marginTop: 8 }}>
          add at least one golden case before running.
        </p>
      )}
    </div>
  )
}

function RunRow({ run, prev }: { run: EvalRun; prev: EvalRun | undefined }) {
  const [open, setOpen] = useState(false)
  const [detail, setDetail] = useState<RunDetail | null>(null)
  const rate = run.summary?.pass_rate ?? null
  const prevRate = prev?.summary?.pass_rate ?? null
  const delta = rate != null && prevRate != null ? rate - prevRate : null

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && !detail) setDetail(await getRun(run.id))
  }

  return (
    <>
      <tr className="clickrow" onClick={toggle}>
        <td className="mono">v{run.version ?? '?'}</td>
        <td>
          {run.status === 'done' ? (
            <span className={passClass(rate)}>{pct(rate)}</span>
          ) : (
            <span className="tag tag--info">{run.status}</span>
          )}
        </td>
        <td className="num">{run.summary ? run.summary.avg_score : '-'}</td>
        <td className="num">
          {delta == null ? (
            '-'
          ) : (
            <span style={{ color: delta >= 0 ? 'var(--ink)' : 'var(--coral)' }}>
              {delta >= 0 ? '+' : ''}
              {Math.round(delta * 100)}%
            </span>
          )}
        </td>
        <td>{new Date(run.created_at).toLocaleString('en-GB', { hour12: false })}</td>
      </tr>
      {open && detail && (
        <tr>
          <td colSpan={5} style={{ background: 'var(--paper)' }}>
            <table className="signal">
              <thead>
                <tr>
                  <th>input</th>
                  <th>expected</th>
                  <th>got</th>
                  <th>score</th>
                  <th>why</th>
                </tr>
              </thead>
              <tbody>
                {detail.results.map((r) => (
                  <tr key={r.id}>
                    <td>{r.input}</td>
                    <td>{r.reference}</td>
                    <td>{r.actual.slice(0, 80)}</td>
                    <td>
                      <span className={r.passed ? 'tag tag--ok' : 'tag tag--err'}>{r.score}</span>
                    </td>
                    <td className="muted">{r.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  )
}

function Runs({ runs }: { runs: EvalRun[] }) {
  return (
    <div className="panel">
      <p className="kicker">suite / runs</p>
      <h3 className="display" style={{ fontSize: 17, marginBottom: 10 }}>
        results over time
      </h3>
      <table className="signal">
        <thead>
          <tr>
            <th>version</th>
            <th>pass rate</th>
            <th className="num">avg score</th>
            <th className="num">vs prev</th>
            <th>when</th>
          </tr>
        </thead>
        <tbody>
          {runs.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                no runs yet. run a version above to grade it.
              </td>
            </tr>
          )}
          {runs.map((run, i) => (
            <RunRow key={run.id} run={run} prev={runs[i + 1]} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Evals() {
  const [suites, setSuites] = useState<EvalSuite[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<SuiteDetail | null>(null)
  const [runs, setRuns] = useState<EvalRun[]>([])
  const [newName, setNewName] = useState('')
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const loadSuites = useCallback(async () => {
    try {
      setSuites(await listSuites())
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [])

  const loadDetail = useCallback(async (id: string) => {
    const [d, r] = await Promise.all([getSuite(id), listRuns(id)])
    setDetail(d)
    setRuns(r)
  }, [])

  useEffect(() => {
    loadSuites()
  }, [loadSuites])

  useEffect(() => {
    if (selectedId) loadDetail(selectedId)
    else {
      setDetail(null)
      setRuns([])
    }
  }, [selectedId, loadDetail])

  async function create(e: React.FormEvent) {
    e.preventDefault()
    if (!newName.trim()) return
    setErr(null)
    try {
      const s = await createSuite(newName.trim())
      setNewName('')
      await loadSuites()
      setSelectedId(s.id)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }

  async function run(v: PromptVersion) {
    if (!selectedId) return
    setRunning(true)
    setErr(null)
    try {
      const started = await startRun(v.id)
      // Poll until the background run finishes.
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 2500))
        const d = await getRun(started.id)
        if (d.status === 'done' || d.status === 'failed') break
      }
      await loadDetail(selectedId)
      await loadSuites()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  async function removeSuite(id: string) {
    await deleteSuite(id)
    if (selectedId === id) setSelectedId(null)
    loadSuites()
  }

  return (
    <div className="evals">
      <aside className="evals-side">
        <form onSubmit={create} style={{ marginBottom: 12 }}>
          <div className="field" style={{ marginBottom: 8 }}>
            <label>new suite</label>
            <input
              className="input"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="e.g. support replies"
            />
          </div>
          <button className="btn" type="submit" style={{ width: '100%' }} disabled={!newName.trim()}>
            create suite
          </button>
        </form>
        <div className="kicker">test suites</div>
        <div className="conv-list">
          {suites.length === 0 && (
            <p className="muted mono" style={{ fontSize: 12 }}>
              none yet
            </p>
          )}
          {suites.map((s) => (
            <div
              key={s.id}
              className={`conv ${s.id === selectedId ? 'active' : ''}`}
              onClick={() => setSelectedId(s.id)}
            >
              <span className="conv-title">
                {s.name}
                <span className="mono muted" style={{ fontSize: 11, marginLeft: 6 }}>
                  {s.golden_count}c
                  {s.latest_pass_rate != null && ` / ${pct(s.latest_pass_rate)}`}
                </span>
              </span>
              <button
                className="conv-del"
                onClick={(e) => {
                  e.stopPropagation()
                  removeSuite(s.id)
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="evals-main">
        {err && (
          <div className="panel" style={{ marginBottom: 20, borderColor: 'var(--coral)' }}>
            <span className="tag tag--err">error</span> <span className="mono">{err}</span>
          </div>
        )}
        {!detail ? (
          <div className="panel">
            <p className="kicker">eval / harness</p>
            <h2 className="display" style={{ fontSize: 24, marginBottom: 8 }}>
              measure your prompts
            </h2>
            <p className="muted" style={{ maxWidth: 560 }}>
              A suite is a set of questions and the answers you expect. Run a prompt version
              against it and a Gemini judge scores every case, so you can prove a change made
              things better, not worse. Create a suite to begin.
            </p>
          </div>
        ) : (
          <>
            <div className="section-head">
              <div>
                <div className="kicker">eval / suite</div>
                <h2 className="display" style={{ fontSize: 22 }}>
                  {detail.name}
                </h2>
              </div>
              {running && <span className="tag tag--info">running eval…</span>}
            </div>
            <Goldens detail={detail} reload={() => loadDetail(detail.id)} />
            <Versions
              detail={detail}
              reload={() => loadDetail(detail.id)}
              onRun={run}
              running={running}
            />
            <Runs runs={runs} />
          </>
        )}
      </section>
    </div>
  )
}
