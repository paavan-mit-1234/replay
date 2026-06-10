export default function Landing({ onStart }: { onStart: () => void }) {
  return (
    <div className="app landing">
      <div className="topbar">
        <div className="wordmark">
          REPLAY<span className="dot">.</span>
        </div>
        <button className="btn btn--ghost" onClick={onStart}>
          sign in
        </button>
      </div>

      <section className="hero">
        <div className="kicker">signal / live</div>
        <h1 className="display hero-title">
          capture every prompt.
          <br />
          make every next one <span className="hl">better</span>.
        </h1>
        <p className="hero-sub">
          Replay sits between you and any AI. It records what you ask, coaches you to ask
          better, and shows you exactly what each call costs. Free to use, bring your own key.
        </p>
        <button className="btn hero-cta" onClick={onStart}>
          get started free
        </button>
      </section>

      <section className="doors">
        <div className="door">
          <div className="kicker">door one / for people</div>
          <h2 className="display door-title">a smarter place to chat with ai</h2>
          <p>
            Ask anything. Stuck on how to phrase it? One click sharpens your prompt. After every
            answer, learn how you could have asked better. Replay quietly learns your style and
            surfaces when you have asked something like it before.
          </p>
        </div>
        <div className="door door--dark">
          <div className="kicker">door two / for developers</div>
          <h2 className="display door-title">observability for your ai app</h2>
          <p>
            Change one line, your base_url, and Replay captures every call: tokens, cost,
            latency, the full prompt and response. Streaming passthrough, per-tenant isolation,
            a live dashboard, and a request inspector. Your provider key stays encrypted.
          </p>
        </div>
      </section>

      <section className="features">
        {[
          ['prompt doctor', 'rewrites a vague prompt into a sharp one in one click'],
          ['autopsy', 'a friendly critique after any answer, so you learn as you go'],
          ['learning loop', 'embeddings spot the prompts you ask again and again'],
          ['streaming', 'token by token, with usage captured the moment it finishes'],
          ['cost accounting', 'every call priced to the millionth of a dollar'],
          ['bring your own key', 'your provider key, your free tier, encrypted at rest'],
        ].map(([t, d]) => (
          <div className="feature" key={t}>
            <div className="feature-t">{t}</div>
            <div className="feature-d">{d}</div>
          </div>
        ))}
      </section>

      <section className="final-cta">
        <div className="kicker">transport / begin</div>
        <h2 className="display" style={{ fontSize: 40 }}>
          start in thirty seconds
        </h2>
        <button className="btn hero-cta" onClick={onStart}>
          get started free
        </button>
      </section>
    </div>
  )
}
