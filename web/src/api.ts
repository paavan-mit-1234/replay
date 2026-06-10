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

export const listProviderKeys = () => call<ProviderKey[]>('/api/provider-keys')
export const addProviderKey = (provider: string, label: string, secret: string) =>
  call<ProviderKey>('/api/provider-keys', {
    method: 'POST',
    body: JSON.stringify({ provider, label, secret }),
  })
export const revokeProviderKey = (id: string) =>
  call<void>(`/api/provider-keys/${id}/revoke`, { method: 'POST' })
