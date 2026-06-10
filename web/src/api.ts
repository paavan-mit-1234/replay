// Typed client for the Replay management API. Auth comes from the Supabase
// session access token; the active org is sent as X-Replay-Org.

const API_URL = (import.meta.env.VITE_REPLAY_API_URL as string) ?? 'http://localhost:8000'

let _token = ''
let _org = ''

export function configureApi(token: string, org: string): void {
  _token = token
  _org = org
}

export function currentAuth(): { token: string; org: string; apiUrl: string } {
  return { token: _token, org: _org, apiUrl: API_URL }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${_token}`,
      'X-Replay-Org': _org,
      ...(init?.headers ?? {}),
    },
  })
  if (!resp.ok) {
    let detail = resp.statusText
    try {
      detail = (await resp.json()).detail ?? detail
    } catch {
      // non JSON body
    }
    throw new Error(`${resp.status}: ${detail}`)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

// Types
export interface OrgMembership {
  id: string
  name: string
  slug: string
  role: string
}
export interface Me {
  user_id: string
  email: string
  orgs: OrgMembership[]
}
export interface Stats {
  spend_usd: number
  request_count: number
  error_count: number
  error_rate: number
  median_latency_ms: number | null
}
export interface RequestRow {
  id: string
  provider: string
  model: string
  endpoint: string
  status_code: number | null
  error: string | null
  input_tokens: number | null
  output_tokens: number | null
  cost_usd: number | null
  latency_ms: number | null
  created_at: string
}
export interface ApiKey {
  id: string
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}
export interface ApiKeyCreated extends ApiKey {
  key: string
}
export interface ProviderKey {
  id: string
  provider: string
  label: string
  created_at: string
  revoked_at: string | null
}

// Endpoints
export const getMe = () => call<Me>('/api/me')
export const createOrg = (name: string, slug: string) =>
  call<OrgMembership>('/api/orgs', { method: 'POST', body: JSON.stringify({ name, slug }) })

export interface RequestDetail extends RequestRow {
  request_body: Record<string, unknown>
  response_body: Record<string, unknown> | null
  cache_read_tokens: number | null
  cache_write_tokens: number | null
}

export const getStats = () => call<Stats>('/api/stats')
export const listRequests = (limit = 40) =>
  call<RequestRow[]>(`/api/requests?limit=${limit}`)
export const getRequest = (id: string) => call<RequestDetail>(`/api/requests/${id}`)

export const listKeys = () => call<ApiKey[]>('/api/keys')
export const createKey = (name: string) =>
  call<ApiKeyCreated>('/api/keys', { method: 'POST', body: JSON.stringify({ name }) })
export const revokeKey = (id: string) =>
  call<void>(`/api/keys/${id}/revoke`, { method: 'POST' })

// --- Chat workspace ---
export interface Conversation {
  id: string
  title: string
  updated_at: string
}
export interface ChatMessage {
  id: string
  role: string
  content: string
  feedback: number | null
  created_at: string
}
export interface ConversationDetail {
  id: string
  title: string
  messages: ChatMessage[]
}
export interface SimilarItem {
  content: string
  conversation_id: string
  title: string
}

export const listConversations = () => call<Conversation[]>('/api/chat/conversations')
export const getConversation = (id: string) =>
  call<ConversationDetail>(`/api/chat/conversations/${id}`)
export const deleteConversation = (id: string) =>
  call<void>(`/api/chat/conversations/${id}`, { method: 'DELETE' })
export const renameConversation = (id: string, title: string) =>
  call<void>(`/api/chat/conversations/${id}/rename`, {
    method: 'POST',
    body: JSON.stringify({ title }),
  })
export const messageFeedback = (id: string, rating: number) =>
  call<void>(`/api/chat/messages/${id}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ rating }),
  })
export const findSimilar = (content: string) =>
  call<SimilarItem[]>('/api/chat/similar', { method: 'POST', body: JSON.stringify({ content }) })
export const improvePrompt = (prompt: string) =>
  call<{ improved: string }>('/api/improve', { method: 'POST', body: JSON.stringify({ prompt }) })
export const autopsy = (prompt: string, response: string) =>
  call<{ markdown: string }>('/api/autopsy', {
    method: 'POST',
    body: JSON.stringify({ prompt, response }),
  })

export async function sendChat(
  content: string,
  conversationId: string | null,
  model: string,
  onToken: (t: string) => void,
): Promise<{ conversationId: string; text: string }> {
  const { token, org, apiUrl } = currentAuth()
  const resp = await fetch(`${apiUrl}/api/chat/send`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Replay-Org': org,
    },
    body: JSON.stringify({ content, conversation_id: conversationId, model }),
  })
  if (!resp.ok || !resp.body) {
    throw new Error(`${resp.status}: ${await resp.text()}`)
  }
  const convId = resp.headers.get('X-Conversation-Id') ?? conversationId ?? ''
  const reader = resp.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  let text = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let idx: number
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const evt = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      for (const line of evt.split('\n')) {
        if (!line.startsWith('data:')) continue
        const p = line.slice(5).trim()
        if (p === '[DONE]') continue
        try {
          const d = JSON.parse(p)
          const t = d?.choices?.[0]?.delta?.content
          if (t) {
            text += t
            onToken(t)
          }
        } catch {
          // ignore keepalive lines
        }
      }
    }
  }
  return { conversationId: convId, text }
}

export const listProviderKeys = () => call<ProviderKey[]>('/api/provider-keys')
export const addProviderKey = (provider: string, label: string, secret: string) =>
  call<ProviderKey>('/api/provider-keys', {
    method: 'POST',
    body: JSON.stringify({ provider, label, secret }),
  })
export const revokeProviderKey = (id: string) =>
  call<void>(`/api/provider-keys/${id}/revoke`, { method: 'POST' })
