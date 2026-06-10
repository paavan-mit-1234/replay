import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { getRequest, type RequestDetail } from './api'

function contentToText(c: unknown): string {
  if (typeof c === 'string') return c
  if (Array.isArray(c))
    return c
      .map((b) =>
        typeof b === 'string' ? b : ((b as Record<string, unknown>)?.text as string) ?? '',
      )
      .join('')
  return ''
}

interface Msg {
  role: string
  text: string
}

function extractMessages(body: Record<string, unknown>): Msg[] {
  const out: Msg[] = []
  if (typeof body.system === 'string' && body.system) out.push({ role: 'system', text: body.system })
  const msgs = body.messages
  if (Array.isArray(msgs)) {
    for (const m of msgs) {
      const mm = m as Record<string, unknown>
      out.push({ role: String(mm.role ?? 'user'), text: contentToText(mm.content) })
    }
  }
  return out
}

function extractOutput(body: Record<string, unknown> | null): string | null {
  if (!body) return null
  if (typeof body.text === 'string') return body.text // streamed summary
  const choices = body.choices as Array<Record<string, unknown>> | undefined
  if (choices && choices[0]) {
    const message = choices[0].message as Record<string, unknown> | undefined
    if (message && typeof message.content === 'string') return message.content
  }
  if (Array.isArray(body.content)) return contentToText(body.content)
  return null
}

function RoleTag({ role }: { role: string }) {
  const cls =
    role === 'assistant' ? 'tag tag--ok' : role === 'system' ? 'tag tag--info' : 'tag tag--warn'
  return <span className={cls}>{role}</span>
}

export default function RequestDetailView({ id, onClose }: { id: string; onClose: () => void }) {
  const [data, setData] = useState<RequestDetail | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [showRaw, setShowRaw] = useState(false)

  useEffect(() => {
    getRequest(id)
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
  }, [id])

  const messages = data ? extractMessages(data.request_body) : []
  const output = data ? extractOutput(data.response_body) : null

  return (
    <div className="overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <div className="row-between" style={{ marginBottom: 16 }}>
          <div className="kicker" style={{ margin: 0 }}>
            signal / call detail
          </div>
          <button className="btn btn--ghost" onClick={onClose}>
            close
          </button>
        </div>

        {err && (
          <p>
            <span className="tag tag--err">error</span> <span className="mono">{err}</span>
          </p>
        )}

        {data && (
          <>
            <div className="detail-meta mono">
              <span>{data.created_at.replace('T', ' ').slice(0, 19)}</span>
              <span>{data.provider}</span>
              <span>{data.model}</span>
              <span>status {data.status_code ?? data.error ?? '-'}</span>
              <span>in {data.input_tokens ?? '-'}</span>
              <span>out {data.output_tokens ?? '-'}</span>
              <span>{data.cost_usd !== null ? `$${data.cost_usd.toFixed(6)}` : 'cost -'}</span>
              <span>{data.latency_ms ?? '-'} ms</span>
            </div>

            <div className="kicker" style={{ marginTop: 20 }}>
              request
            </div>
            {messages.length === 0 && <p className="muted mono">no messages parsed</p>}
            {messages.map((m, i) => (
              <div key={i} className="msg">
                <RoleTag role={m.role} />
                <div className="md-output md-light">
                  <ReactMarkdown>{m.text}</ReactMarkdown>
                </div>
              </div>
            ))}

            <div className="kicker" style={{ marginTop: 20 }}>
              response
            </div>
            {output ? (
              <div className="md-output" style={{ background: 'var(--ink)', color: 'var(--paper)', padding: 16 }}>
                <ReactMarkdown>{output}</ReactMarkdown>
              </div>
            ) : (
              <p className="muted mono">
                {data.error ? `error: ${data.error}` : 'no assistant text (see raw below)'}
              </p>
            )}

            <button
              className="linklike"
              style={{ marginTop: 18 }}
              onClick={() => setShowRaw((v) => !v)}
            >
              {showRaw ? 'hide raw json' : 'show raw json'}
            </button>
            {showRaw && (
              <pre className="raw mono">
                {JSON.stringify(
                  { request_body: data.request_body, response_body: data.response_body },
                  null,
                  2,
                )}
              </pre>
            )}
          </>
        )}
      </div>
    </div>
  )
}
