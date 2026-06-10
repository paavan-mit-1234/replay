import { useCallback, useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from './supabase'
import { configureApi, getMe, type Me } from './api'
import Login from './Login'
import Onboarding from './Onboarding'
import Chat from './Chat'
import Dashboard from './Dashboard'
import Playground from './Playground'
import Settings from './Settings'

type View = 'chat' | 'dashboard' | 'playground' | 'settings'

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [ready, setReady] = useState(false)
  const [me, setMe] = useState<Me | null>(null)
  const [orgId, setOrgId] = useState<string | null>(null)
  const [view, setView] = useState<View>('chat')
  const [loadingMe, setLoadingMe] = useState(false)

  // Track the Supabase session.
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setReady(true)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => setSession(s))
    return () => sub.subscription.unsubscribe()
  }, [])

  // Resolve the user's orgs once signed in.
  const loadMe = useCallback(async () => {
    if (!session) return
    setLoadingMe(true)
    try {
      configureApi(session.access_token, '')
      const m = await getMe()
      setMe(m)
      if (m.orgs.length > 0) setOrgId((cur) => cur ?? m.orgs[0].id)
    } catch {
      setMe({ user_id: '', email: '', orgs: [] })
    } finally {
      setLoadingMe(false)
    }
  }, [session])

  useEffect(() => {
    if (session) loadMe()
    else {
      setMe(null)
      setOrgId(null)
    }
  }, [session, loadMe])

  // Keep the API client configured with the current token and org.
  useEffect(() => {
    if (session) configureApi(session.access_token, orgId ?? '')
  }, [session, orgId])

  if (!ready) return null
  if (!session) return <Login />
  if (loadingMe && !me)
    return (
      <div className="app">
        <div className="kicker">connecting…</div>
      </div>
    )
  if (me && me.orgs.length === 0) return <Onboarding onCreated={loadMe} />
  if (!orgId) return null

  const activeOrg = me?.orgs.find((o) => o.id === orgId)

  return (
    <div className="app">
      <div className="topbar">
        <div>
          <div className="kicker">signal / live</div>
          <div className="wordmark">
            REPLAY<span className="dot">.</span>
          </div>
        </div>
        <div className="row-between" style={{ gap: 10 }}>
          <nav className="nav">
            <button className={view === 'chat' ? 'active' : ''} onClick={() => setView('chat')}>
              chat
            </button>
            <button
              className={view === 'dashboard' ? 'active' : ''}
              onClick={() => setView('dashboard')}
            >
              dashboard
            </button>
            <button
              className={view === 'playground' ? 'active' : ''}
              onClick={() => setView('playground')}
            >
              playground
            </button>
            <button
              className={view === 'settings' ? 'active' : ''}
              onClick={() => setView('settings')}
            >
              settings
            </button>
          </nav>
          <button className="btn btn--ghost" onClick={() => supabase.auth.signOut()}>
            sign out
          </button>
        </div>
      </div>

      <div className="orgbar">
        <span className="kicker" style={{ margin: 0 }}>
          org
        </span>{' '}
        <span className="mono">{activeOrg?.name}</span>
        {me && me.orgs.length > 1 && (
          <select
            className="input"
            style={{ width: 'auto', marginLeft: 12, padding: '4px 8px' }}
            value={orgId}
            onChange={(e) => setOrgId(e.target.value)}
          >
            {me.orgs.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
        )}
        <span className="mono muted" style={{ marginLeft: 12 }}>
          {me?.email}
        </span>
      </div>

      {view === 'chat' && <Chat />}
      {view === 'dashboard' && <Dashboard />}
      {view === 'playground' && <Playground />}
      {view === 'settings' && <Settings />}
    </div>
  )
}
