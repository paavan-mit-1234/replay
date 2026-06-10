import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { currentAuth } from './api'

export default function Playground() {
  const [model, setModel] = useState('gemini-2.5-flash')
  const [prompt, setPrompt] = useState('Name three colors, one word each.')
  const [output, setOutput] = useState('')
  const [running, setRunning] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function run() {
    setOutput('')
    setErr(null)
    setRunning(true)
    const { token, org, apiUrl } = currentAuth()
    try {
      const resp = await fetch(`${apiUrl}/api/playground/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          'X-Replay-Org': org,
        },
        body: JSON.stringify({ model, prompt, stream: true }),
      })
      if (!resp.ok || !resp.body) {
        throw new Error(`${resp.status}: ${await resp.text()}`)
      }
      const reader = resp.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buf += dec.decode(value, { stream: true })
        let idx: number
        while ((idx = buf.indexOf('\n\n')) >= 0) {
          const event = buf.slice(0, idx)
          buf = buf.slice(idx + 2)
          for (const line of event.split('\n')) {
            if (!line.startsWith('data:')) continue
            const payload = line.slice(5).trim()
            if (payload === '[DONE]') continue
            try {
              const d = JSON.parse(payload)
              const t = d?.choices?.[0]?.delta?.content
              if (t) setOutput((o) => o + t)
            } catch {
              // ignore non JSON keepalive lines
            }
          }
        }
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <>
      <div className="section-head">
        <div>
          <div className="kicker">transport / playground</div>
          <h2 className="display" style={{ fontSize: 22 }}>
            send a test call
          </h2>
        </div>
      </div>
      <div className="panel" style={{ marginBottom: 24 }}>
        <p style={{ marginBottom: 14 }}>
          Fire a call through your proxy using this org's provider key. It streams here and is
          captured on the dashboard, exactly like traffic from your app. No API key needed.
        </p>
        <div className="field">
          <label>model</label>
          <input className="input" value={model} onChange={(e) => setModel(e.target.value)} />
        </div>
        <div className="field">
          <label>prompt</label>
          <textarea
            className="input"
            style={{ minHeight: 90, resize: 'vertical' }}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </div>
        <button className="btn" onClick={run} disabled={running || !prompt.trim()}>
          {running ? 'running…' : 'run'}
        </button>
        {err && (
          <p style={{ marginTop: 14 }}>
            <span className="tag tag--err">error</span> <span className="mono">{err}</span>
          </p>
        )}
      </div>

      <div className="section-head">
        <div className="kicker">signal / output</div>
        {running && <div style={{ width: 110 }} className="tape" />}
      </div>
      <div
        className="panel md-output"
        style={{ minHeight: 140, background: 'var(--ink)', color: 'var(--paper)' }}
      >
        {output ? (
          <ReactMarkdown>{output}</ReactMarkdown>
        ) : (
          <span className="muted">output appears here as it streams in.</span>
        )}
      </div>
    </>
  )
}
