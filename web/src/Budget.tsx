import { useCallback, useEffect, useState } from 'react'
import {
  ackAlert,
  getBudget,
  listAlerts,
  putBudget,
  type Alert,
  type Budget as BudgetType,
} from './api'

const STATUS_COLOR: Record<string, string> = {
  ok: 'var(--lime)',
  warn: 'var(--marigold)',
  over: 'var(--coral)',
  unset: 'var(--panel)',
}

function alertLine(a: Alert): string {
  const p = (a.payload ?? {}) as { spend_usd?: number; limit_usd?: number; usage_pct?: number }
  const spend = p.spend_usd != null ? `$${p.spend_usd.toFixed(2)}` : '?'
  const limit = p.limit_usd != null ? `$${p.limit_usd.toFixed(2)}` : '?'
  const pct = p.usage_pct != null ? `${p.usage_pct}%` : ''
  if (a.kind === 'budget_exceeded') return `Monthly limit reached: ${spend} of ${limit} (${pct})`
  return `Spend crossed your alert threshold: ${spend} of ${limit} (${pct})`
}

export default function Budget() {
  const [budget, setBudget] = useState<BudgetType | null>(null)
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [limit, setLimit] = useState('')
  const [threshold, setThreshold] = useState('80')
  const [block, setBlock] = useState(false)
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      const [b, a] = await Promise.all([getBudget(), listAlerts()])
      setBudget(b)
      setAlerts(a.filter((x) => x.acknowledged_at === null))
      setLimit(b.monthly_limit_usd != null ? String(b.monthly_limit_usd) : '')
      setThreshold(String(b.alert_threshold_pct))
      setBlock(b.block_over_limit)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  async function save(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setErr(null)
    try {
      const parsed = limit.trim() === '' ? null : Number(limit)
      await putBudget({
        monthly_limit_usd: parsed,
        alert_threshold_pct: Number(threshold),
        block_over_limit: block,
      })
      setEditing(false)
      await load()
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(false)
    }
  }

  async function dismiss(id: string) {
    setAlerts((xs) => xs.filter((x) => x.id !== id))
    ackAlert(id).catch(() => load())
  }

  const spend = budget?.month_spend_usd ?? 0
  const pct = budget?.usage_pct ?? null
  const barPct = pct != null ? Math.min(pct, 100) : 0
  const color = STATUS_COLOR[budget?.status ?? 'unset']

  return (
    <div className="panel budget" style={{ marginBottom: 24 }}>
      {alerts.map((a) => (
        <div
          key={a.id}
          className="budget-alert"
          style={{ borderColor: a.kind === 'budget_exceeded' ? 'var(--coral)' : 'var(--marigold)' }}
        >
          <span className={`tag ${a.kind === 'budget_exceeded' ? 'tag--err' : 'tag--warn'}`}>
            {a.kind === 'budget_exceeded' ? 'over budget' : 'budget alert'}
          </span>
          <span className="mono" style={{ flex: 1 }}>
            {alertLine(a)}
          </span>
          <button className="linklike" onClick={() => dismiss(a.id)}>
            dismiss
          </button>
        </div>
      ))}

      <div className="row-between" style={{ alignItems: 'baseline' }}>
        <div>
          <p className="kicker" style={{ margin: 0 }}>
            cost / monthly budget
          </p>
          <div className="mono" style={{ fontSize: 13, marginTop: 4 }}>
            this month: <strong>${spend.toFixed(2)}</strong>
            {budget?.monthly_limit_usd != null ? (
              <>
                {' '}
                of ${budget.monthly_limit_usd.toFixed(2)}
                {pct != null && <> ({pct}%)</>}
                {budget.block_over_limit && <span className="tag tag--info"> blocks over</span>}
              </>
            ) : (
              <span className="muted"> no limit set</span>
            )}
          </div>
        </div>
        <button className="btn btn--ghost" onClick={() => setEditing((v) => !v)}>
          {editing ? 'cancel' : budget?.monthly_limit_usd != null ? 'edit budget' : 'set a budget'}
        </button>
      </div>

      {budget?.monthly_limit_usd != null && (
        <div className="budget-bar">
          <div className="budget-bar__fill" style={{ width: `${barPct}%`, background: color }} />
        </div>
      )}

      {editing && (
        <form onSubmit={save} className="budget-form" style={{ marginTop: 14 }}>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>monthly limit (usd)</label>
            <input
              className="input"
              type="number"
              min="0"
              step="0.01"
              value={limit}
              onChange={(e) => setLimit(e.target.value)}
              placeholder="e.g. 50.00 (blank = none)"
              style={{ width: 200 }}
            />
          </div>
          <div className="field" style={{ marginBottom: 0 }}>
            <label>alert at (% of limit)</label>
            <input
              className="input"
              type="number"
              min="1"
              max="100"
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
              style={{ width: 120 }}
            />
          </div>
          <label className="budget-check">
            <input
              type="checkbox"
              checked={block}
              onChange={(e) => setBlock(e.target.checked)}
            />
            block proxied calls over the limit
          </label>
          <button className="btn" type="submit" disabled={saving}>
            {saving ? 'saving…' : 'save budget'}
          </button>
        </form>
      )}

      {err && (
        <p style={{ marginTop: 12 }}>
          <span className="tag tag--err">error</span> <span className="mono">{err}</span>
        </p>
      )}
    </div>
  )
}
