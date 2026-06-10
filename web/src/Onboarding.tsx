import { useState } from 'react'
import { createOrg } from './api'

function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

export default function Onboarding({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [slug, setSlug] = useState('')
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    try {
      await createOrg(name, slug || slugify(name))
      onCreated()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app">
      <div className="topbar">
        <div className="wordmark">
          REPLAY<span className="dot">.</span>
        </div>
        <div className="kicker">transport / first run</div>
      </div>
      <div className="panel" style={{ maxWidth: 480 }}>
        <p className="kicker">create your workspace</p>
        <h2 className="display" style={{ fontSize: 24, marginBottom: 12 }}>
          name your org
        </h2>
        <p style={{ marginBottom: 16 }}>
          An org holds your provider keys, your API keys, and all captured traffic. You can
          invite teammates to it later.
        </p>
        <form onSubmit={submit}>
          <div className="field">
            <label>name</label>
            <input
              className="input"
              value={name}
              onChange={(e) => {
                setName(e.target.value)
                setSlug(slugify(e.target.value))
              }}
              required
            />
          </div>
          <div className="field">
            <label>slug</label>
            <input className="input" value={slug} onChange={(e) => setSlug(e.target.value)} />
          </div>
          <button className="btn" type="submit" disabled={busy}>
            create org
          </button>
        </form>
        {err && (
          <p style={{ marginTop: 14 }}>
            <span className="tag tag--err">error</span> <span className="mono">{err}</span>
          </p>
        )}
      </div>
    </div>
  )
}
