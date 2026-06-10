import { useCallback, useEffect, useState } from 'react'
import {
  addProviderKey,
  createKey,
  listKeys,
  listProviderKeys,
  revokeKey,
  revokeProviderKey,
  type ApiKey,
  type ProviderKey,
} from './api'

const API_URL = (import.meta.env.VITE_REPLAY_API_URL as string) ?? 'http://localhost:8000'

function ProviderKeys() {
  const [rows, setRows] = useState<ProviderKey[]>([])
  const [provider, setProvider] = useState('gemini')
  const [label, setLabel] = useState('default')
  const [secret, setSecret] = useState('')
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(await listProviderKeys())
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [])
  useEffect(() => {
    load()
  }, [load])

  async function add(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    try {
      await addProviderKey(provider, label, secret)
      setSecret('')
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="panel" style={{ marginBottom: 24 }}>
      <p className="kicker">byok / provider keys</p>
      <h3 className="display" style={{ fontSize: 18, marginBottom: 12 }}>
        provider keys
      </h3>
      <p style={{ marginBottom: 14 }}>
        Your own LLM provider key. Stored encrypted, never shown again. Replay forwards your
        traffic using this key.
      </p>
      <form onSubmit={add} className="row-between" style={{ alignItems: 'flex-end', gap: 12 }}>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>provider</label>
          <select className="input" value={provider} onChange={(e) => setProvider(e.target.value)}>
            <option value="gemini">gemini</option>
            <option value="anthropic">anthropic</option>
            <option value="openai">openai</option>
          </select>
        </div>
        <div className="field" style={{ marginBottom: 0 }}>
          <label>label</label>
          <input className="input" value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="field" style={{ marginBottom: 0, flex: 1 }}>
          <label>secret</label>
          <input
            className="input"
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="paste provider key"
            required
          />
        </div>
        <button className="btn" type="submit">
          add
        </button>
      </form>
      {err && (
        <p style={{ marginTop: 12 }}>
          <span className="tag tag--err">error</span> <span className="mono">{err}</span>
        </p>
      )}
      <table className="signal" style={{ marginTop: 16 }}>
        <thead>
          <tr>
            <th>provider</th>
            <th>label</th>
            <th>added</th>
            <th>status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.provider}</td>
              <td>{r.label}</td>
              <td>{r.created_at.slice(0, 19)}</td>
              <td>
                {r.revoked_at ? (
                  <span className="tag tag--err">revoked</span>
                ) : (
                  <span className="tag tag--ok">active</span>
                )}
              </td>
              <td>
                {!r.revoked_at && (
                  <button
                    className="linklike"
                    onClick={async () => {
                      await revokeProviderKey(r.id)
                      load()
                    }}
                  >
                    revoke
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ApiKeys() {
  const [rows, setRows] = useState<ApiKey[]>([])
  const [name, setName] = useState('app')
  const [fresh, setFresh] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setRows(await listKeys())
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [])
  useEffect(() => {
    load()
  }, [load])

  async function create(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    try {
      const created = await createKey(name)
      setFresh(created.key)
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div className="panel" style={{ marginBottom: 24 }}>
      <p className="kicker">access / replay keys</p>
      <h3 className="display" style={{ fontSize: 18, marginBottom: 12 }}>
        replay api keys
      </h3>
      <p style={{ marginBottom: 14 }}>
        Use these in your application to authenticate to the proxy. Shown once at creation.
      </p>
      <form onSubmit={create} className="row-between" style={{ alignItems: 'flex-end', gap: 12 }}>
        <div className="field" style={{ marginBottom: 0, flex: 1 }}>
          <label>name</label>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <button className="btn" type="submit">
          create key
        </button>
      </form>
      {fresh && (
        <div
          className="panel"
          style={{ marginTop: 14, background: 'var(--lime)', boxShadow: 'none' }}
        >
          <p className="kicker">copy now, not shown again</p>
          <code className="mono" style={{ wordBreak: 'break-all' }}>
            {fresh}
          </code>
        </div>
      )}
      {err && (
        <p style={{ marginTop: 12 }}>
          <span className="tag tag--err">error</span> <span className="mono">{err}</span>
        </p>
      )}
      <table className="signal" style={{ marginTop: 16 }}>
        <thead>
          <tr>
            <th>prefix</th>
            <th>name</th>
            <th>last used</th>
            <th>status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              <td>{r.prefix}</td>
              <td>{r.name}</td>
              <td>{r.last_used_at ? r.last_used_at.slice(0, 19) : '-'}</td>
              <td>
                {r.revoked_at ? (
                  <span className="tag tag--err">revoked</span>
                ) : (
                  <span className="tag tag--ok">active</span>
                )}
              </td>
              <td>
                {!r.revoked_at && (
                  <button
                    className="linklike"
                    onClick={async () => {
                      await revokeKey(r.id)
                      load()
                    }}
                  >
                    revoke
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Integration() {
  const snippet = `from openai import OpenAI

client = OpenAI(
    base_url="${API_URL}/v1",
    api_key="rpl_your_key",   # your Replay key
)
resp = client.chat.completions.create(
    model="gemini-2.5-flash",
    messages=[{"role": "user", "content": "hello"}],
)`
  return (
    <div className="panel">
      <p className="kicker">transport / integrate</p>
      <h3 className="display" style={{ fontSize: 18, marginBottom: 12 }}>
        point your app here
      </h3>
      <p style={{ marginBottom: 14 }}>
        Change one line in your app: send your LLM client at Replay with a Replay key. Your
        provider key stays here, encrypted.
      </p>
      <pre
        className="mono"
        style={{
          background: 'var(--ink)',
          color: 'var(--paper)',
          padding: 16,
          overflowX: 'auto',
          border: 'var(--border)',
        }}
      >
        {snippet}
      </pre>
    </div>
  )
}

export default function Settings() {
  return (
    <>
      <ProviderKeys />
      <ApiKeys />
      <Integration />
    </>
  )
}
