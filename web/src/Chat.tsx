import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import {
  autopsy,
  deleteConversation,
  findSimilar,
  getConversation,
  improvePrompt,
  listConversations,
  messageFeedback,
  sendChat,
  type ChatMessage,
  type Conversation,
  type SimilarItem,
} from './api'

const MODEL = 'gemini-2.5-flash'

export default function Chat() {
  const [convs, setConvs] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [pendingUser, setPendingUser] = useState<string | null>(null)
  const [streamText, setStreamText] = useState('')
  const [busy, setBusy] = useState(false)
  const [improving, setImproving] = useState(false)
  const [similar, setSimilar] = useState<SimilarItem[]>([])
  const [autopsies, setAutopsies] = useState<Record<string, string>>({})
  const [err, setErr] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  const loadConvs = useCallback(async () => {
    try {
      setConvs(await listConversations())
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    loadConvs()
  }, [loadConvs])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamText, pendingUser])

  async function openConv(id: string) {
    setErr(null)
    setSimilar([])
    setAutopsies({})
    try {
      const d = await getConversation(id)
      setActiveId(d.id)
      setMessages(d.messages)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }

  function newChat() {
    setActiveId(null)
    setMessages([])
    setSimilar([])
    setAutopsies({})
    setErr(null)
  }

  async function send() {
    const content = input.trim()
    if (!content || busy) return
    setInput('')
    setErr(null)
    setSimilar([])
    setBusy(true)
    setPendingUser(content)
    setStreamText('')
    try {
      const { conversationId } = await sendChat(content, activeId, MODEL, (t) =>
        setStreamText((s) => s + t),
      )
      setActiveId(conversationId)
      // The assistant message is persisted by a background task just after the
      // stream closes, so retry the reload until it appears (with real ids).
      let d = await getConversation(conversationId)
      for (let i = 0; i < 6; i++) {
        const last = d.messages[d.messages.length - 1]
        if (last && last.role === 'assistant') break
        await new Promise((r) => setTimeout(r, 400))
        d = await getConversation(conversationId)
      }
      setMessages(d.messages)
      loadConvs()
      findSimilar(content)
        .then((items) => setSimilar(items.filter((i) => i.content !== content)))
        .catch(() => {})
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setPendingUser(null)
      setStreamText('')
      setBusy(false)
    }
  }

  async function improve() {
    if (!input.trim() || improving) return
    setImproving(true)
    try {
      const { improved } = await improvePrompt(input.trim())
      setInput(improved)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setImproving(false)
    }
  }

  async function vote(m: ChatMessage, rating: number) {
    const next = m.feedback === rating ? 0 : rating
    setMessages((ms) =>
      ms.map((x) => (x.id === m.id ? { ...x, feedback: next || null } : x)),
    )
    messageFeedback(m.id, next).catch(() => {})
  }

  async function runAutopsy(assistant: ChatMessage, idx: number) {
    const userPrompt = idx > 0 ? messages[idx - 1]?.content ?? '' : ''
    setAutopsies((a) => ({ ...a, [assistant.id]: 'analyzing…' }))
    try {
      const { markdown } = await autopsy(userPrompt, assistant.content)
      setAutopsies((a) => ({ ...a, [assistant.id]: markdown }))
    } catch (e) {
      setAutopsies((a) => ({
        ...a,
        [assistant.id]: e instanceof Error ? e.message : String(e),
      }))
    }
  }

  return (
    <div className="chat">
      <aside className="chat-side">
        <button className="btn" style={{ width: '100%', marginBottom: 12 }} onClick={newChat}>
          + new chat
        </button>
        <div className="kicker">your chats</div>
        <div className="conv-list">
          {convs.length === 0 && <p className="muted mono" style={{ fontSize: 12 }}>none yet</p>}
          {convs.map((c) => (
            <div
              key={c.id}
              className={`conv ${c.id === activeId ? 'active' : ''}`}
              onClick={() => openConv(c.id)}
            >
              <span className="conv-title">{c.title}</span>
              <button
                className="conv-del"
                onClick={(e) => {
                  e.stopPropagation()
                  deleteConversation(c.id).then(() => {
                    if (c.id === activeId) newChat()
                    loadConvs()
                  })
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>

      <section className="chat-main">
        <div className="kicker">workspace / chat</div>
        <div className="thread">
          {messages.length === 0 && !pendingUser && (
            <div className="empty">
              <h2 className="display" style={{ fontSize: 26 }}>
                ask anything
              </h2>
              <p className="muted">
                Type a question below. Stuck on how to phrase it? Hit{' '}
                <strong>improve my prompt</strong> and Replay sharpens it for you.
              </p>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={m.id} className={`bubble ${m.role}`}>
              <div className="bubble-role kicker">{m.role === 'user' ? 'you' : 'ai'}</div>
              {m.role === 'assistant' ? (
                <div className="md-output">
                  <ReactMarkdown>{m.content}</ReactMarkdown>
                </div>
              ) : (
                <div className="bubble-text">{m.content}</div>
              )}
              {m.role === 'assistant' && (
                <div className="bubble-actions">
                  <button
                    className={`chip ${m.feedback === 1 ? 'on' : ''}`}
                    onClick={() => vote(m, 1)}
                  >
                    good
                  </button>
                  <button
                    className={`chip ${m.feedback === -1 ? 'on-bad' : ''}`}
                    onClick={() => vote(m, -1)}
                  >
                    bad
                  </button>
                  <button className="chip" onClick={() => runAutopsy(m, i)}>
                    how could i ask better?
                  </button>
                </div>
              )}
              {autopsies[m.id] && (
                <div className="autopsy md-output md-light">
                  <ReactMarkdown>{autopsies[m.id]}</ReactMarkdown>
                </div>
              )}
            </div>
          ))}

          {pendingUser && (
            <>
              <div className="bubble user">
                <div className="bubble-role kicker">you</div>
                <div className="bubble-text">{pendingUser}</div>
              </div>
              <div className="bubble assistant">
                <div className="bubble-role kicker">ai</div>
                <div className="md-output">
                  {streamText ? (
                    <ReactMarkdown>{streamText}</ReactMarkdown>
                  ) : (
                    <span className="muted">thinking…</span>
                  )}
                </div>
              </div>
            </>
          )}
          <div ref={endRef} />
        </div>

        {similar.length > 0 && (
          <div className="similar">
            <span className="kicker" style={{ margin: 0 }}>
              you have asked similar before
            </span>
            {similar.map((s) => (
              <button key={s.conversation_id} className="chip" onClick={() => openConv(s.conversation_id)}>
                {s.content.slice(0, 48)}
              </button>
            ))}
          </div>
        )}

        {err && (
          <p style={{ margin: '8px 0' }}>
            <span className="tag tag--err">error</span> <span className="mono">{err}</span>
          </p>
        )}

        <div className="composer">
          <textarea
            className="input"
            placeholder="ask anything…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                send()
              }
            }}
          />
          <div className="composer-actions">
            <button className="btn btn--ghost" onClick={improve} disabled={improving || !input.trim()}>
              {improving ? 'improving…' : 'improve my prompt'}
            </button>
            <button className="btn" onClick={send} disabled={busy || !input.trim()}>
              {busy ? 'sending…' : 'send'}
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
