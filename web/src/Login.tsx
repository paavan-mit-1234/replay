import { useState } from 'react'
import { supabase } from './supabase'

type Mode = 'signin' | 'signup' | 'reset'

export default function Login() {
  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function google() {
    setErr(null)
    const { error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin },
    })
    if (error) setErr(error.message)
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setErr(null)
    setMsg(null)
    try {
      if (mode === 'signin') {
        const { error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
      } else if (mode === 'signup') {
        const { error } = await supabase.auth.signUp({ email, password })
        if (error) throw error
        setMsg('check your email to confirm, then sign in. (confirmation may be disabled in dev)')
      } else {
        const { error } = await supabase.auth.resetPasswordForEmail(email, {
          redirectTo: window.location.origin,
        })
        if (error) throw error
        setMsg('password reset email sent. follow the link to set a new password.')
      }
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
        <div className="kicker">transport / sign in</div>
      </div>

      <div className="panel" style={{ maxWidth: 460 }}>
        <p className="kicker">
          {mode === 'signin' && 'access the console'}
          {mode === 'signup' && 'create an account'}
          {mode === 'reset' && 'reset your password'}
        </p>

        <button className="btn" style={{ width: '100%', marginBottom: 18 }} onClick={google}>
          continue with google
        </button>

        <div className="kicker" style={{ textAlign: 'center', margin: '6px 0 14px' }}>
          or with email
        </div>

        <form onSubmit={submit}>
          <div className="field">
            <label>email</label>
            <input
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          {mode !== 'reset' && (
            <div className="field">
              <label>password</label>
              <input
                className="input"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
          )}
          <button className="btn" type="submit" disabled={busy} style={{ width: '100%' }}>
            {mode === 'signin' && 'sign in'}
            {mode === 'signup' && 'sign up'}
            {mode === 'reset' && 'send reset link'}
          </button>
        </form>

        {err && (
          <p style={{ marginTop: 14 }}>
            <span className="tag tag--err">error</span> <span className="mono">{err}</span>
          </p>
        )}
        {msg && (
          <p style={{ marginTop: 14 }}>
            <span className="tag tag--info">note</span> <span className="mono">{msg}</span>
          </p>
        )}

        <div className="row-between" style={{ marginTop: 20, fontSize: 13 }}>
          {mode !== 'signin' && (
            <button className="linklike" onClick={() => setMode('signin')}>
              have an account? sign in
            </button>
          )}
          {mode === 'signin' && (
            <>
              <button className="linklike" onClick={() => setMode('signup')}>
                create account
              </button>
              <button className="linklike" onClick={() => setMode('reset')}>
                forgot password
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
