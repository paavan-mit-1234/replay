# BUILD PROMPT: Replay

> Hand this entire document to a coding agent. It is the complete specification for building Replay from an empty directory to a deployed, multi-tenant product. Follow it section by section. Where a decision is already made here, do not relitigate it. Where you must choose, choose the option that keeps the project free to run and production grade.

---

## 0. Your role

You are the lead engineer building Replay end to end. You write the backend, the data layer, the CLI, the test suite, the deployment config, and the web dashboard. You make small implementation decisions yourself and you ask the human only when a choice is irreversible or costs money. You ship in phases. Each phase must run and pass tests before you start the next one.

Hard rules for you, the agent:

1. Never write a secret, API key, or token into source code, logs, or test fixtures. Read them from environment or the encrypted vault only.
2. Every database row that belongs to a tenant carries an `org_id` and is protected by Row Level Security. There is no code path that reads tenant data without an org scope.
3. Bring Your Own Key (BYOK). Replay never pays for inference. Every upstream provider call uses the tenant's own provider key, decrypted at request time and never persisted in plaintext.
4. Keep it free to run. Target free tiers only. If a design forces a paid service, stop and surface it to the human before continuing.
5. No em dashes anywhere in code comments, UI copy, docs, or commit messages. Use periods, commas, colons, or parentheses instead.

---

## 1. What Replay is

Replay is a self hostable, multi tenant platform that does two things with one shared data model:

**Observe.** A drop in proxy sits between an application and the LLM providers (Anthropic and OpenAI). The app changes one line, its `base_url`, to point at Replay. Replay forwards the call using the tenant's own provider key, then records the request, the response, the token counts, the dollar cost, the latency, the model, the prompt version, and the cache status.

**Evaluate.** Because every real request is already captured, any logged request can be promoted into a golden test case with one command. Prompts are versioned. When a prompt changes, Replay replays the golden set against the new version, scores the outputs, and reports regressions. The same data powers a Continuous Integration gate and a drift view over time.

The core thesis, and the reason for the name: the proxy that watches production traffic is also the thing that captures eval data, and the eval harness works by replaying that captured traffic against new prompt versions. Observation and evaluation are the same system seen from two sides.

This is the neighborhood of Langfuse, Helicone, and Braintrust, which proves the pain is real. Replay differs by treating capture and replay as one loop and by being trivially self hostable on free infrastructure.

---

## 2. Goals and non goals

**Goals**
- A working multi tenant observability proxy with strict tenant isolation.
- BYOK with provider keys encrypted at rest.
- Accurate per request cost accounting.
- A prompt versioning and replay based evaluation harness.
- A CI gate that fails a build when a prompt change regresses quality.
- A CLI that covers the full workflow.
- A web dashboard with a distinctive, original visual identity (see Section 18).
- Runs end to end on free tier infrastructure.

**Non goals (for now)**
- Fine tuning, training, or model hosting. Replay never runs a model.
- Being a general API gateway. It proxies LLM chat and message endpoints only.
- A billing or payments system for charging Replay's own users. Quotas exist, invoicing does not.
- Providers beyond Anthropic and OpenAI in the first build. The provider layer is pluggable so more can be added later.

---

## 3. Primary users and stories

**The application developer** points their SDK at Replay and forgets about it. Later they open the dashboard and ask: where is my spend going, which model, which feature, which tenant of mine.

**The prompt engineer** edits a system prompt, pushes a branch, and wants to know before merge whether the new prompt is better or worse than the old one on real captured traffic.

**The platform owner** runs Replay for a small team, manages orgs and keys, sets monthly budgets per org, and gets alerted when an org approaches its cap.

User stories to satisfy:
- As a developer I swap one base_url and my calls keep working, streaming included.
- As a developer I see every call with cost and latency within two seconds of it happening.
- As a prompt engineer I promote a real logged call to a golden case in one command.
- As a prompt engineer I run a replay and see a pass and fail breakdown per case with a diff.
- As a CI system I get a non zero exit code when quality drops below a threshold.
- As a platform owner I never see another org's data, and neither does my SQL.

---

## 4. Architecture

```
   app SDK                                  provider
  (base_url) ───────────────►  REPLAY  ───────────────►  Anthropic / OpenAI
                                 │
                 ┌───────────────┼────────────────┐
                 │               │                │
            proxy core      key vault        cost engine
          (httpx stream)   (Fernet AES)     (pricing tables)
                 │
                 ▼
            Postgres  (org_id + Row Level Security on every table)
                 │
       ┌─────────┴──────────┐
       │                    │
   eval engine          CLI + REST API
  (replay + scorers)   (Typer + FastAPI)
                            │
                            ▼
                       web dashboard
                   (instrument panel UI)
```

The proxy is a thin, fast hot path. Everything expensive (scoring, aggregation, alert evaluation) runs out of band so the proxy never adds meaningful latency to a live request. Target proxy overhead is under 15 milliseconds on top of the upstream call, measured at the median, excluding the time spent waiting on the provider.

---

## 5. Tech stack

Pin major versions. Use the latest stable minor at build time.

- Language: Python 3.12.
- Package and env manager: `uv`.
- Web framework: FastAPI.
- HTTP client for passthrough: `httpx` with HTTP/2 and async streaming.
- Database: PostgreSQL 15 or newer, hosted on the Supabase free tier.
- ORM and migrations: SQLAlchemy 2.0 (async) with `asyncpg`, migrations with Alembic.
- Auth: Supabase Auth issuing JWTs, verified in Replay middleware. Proxy endpoints use Replay issued API keys instead of JWTs.
- Secret encryption: `cryptography` Fernet for the provider key vault.
- CLI: Typer plus Rich for output.
- Background jobs: start with FastAPI background tasks and a simple async worker loop. Introduce a real queue only if and when load demands it. Do not add Celery or Redis in the first build.
- Config: `pydantic-settings`, all config from environment.
- Lint and format: Ruff. Type check: mypy in strict mode on the `replay` package.
- Tests: pytest, pytest-asyncio, and `respx` for mocking upstream HTTP.
- Frontend: see Section 18. Use Vite plus React plus TypeScript, plain CSS with custom properties (no component framework that imposes its own look, since the visual identity is the point).

---

## 6. Repository layout

```
replay/
  pyproject.toml
  README.md
  .env.example
  alembic.ini
  docker-compose.yml          # local Postgres only, optional
  src/replay/
    __init__.py
    config.py                 # pydantic settings
    db/
      base.py                 # async engine, session
      models.py               # SQLAlchemy models
      rls.py                  # helpers to set the org scope per session
    migrations/               # alembic
    auth/
      jwt.py                  # supabase jwt verification
      apikeys.py              # replay api key hashing and lookup
      deps.py                 # FastAPI dependencies that resolve org_id
    vault/
      crypto.py               # fernet wrap and unwrap
      keys.py                 # provider key store
    proxy/
      router.py               # POST /v1/messages, POST /v1/chat/completions
      passthrough.py          # httpx forwarding, non streaming and SSE
      providers/
        base.py               # provider interface
        anthropic.py
        openai.py
      capture.py              # build the log row from request and response
    cost/
      pricing.py              # model pricing tables
      calculator.py
    eval/
      golden.py               # promote logged request to golden case
      prompts.py              # prompt and prompt_version logic
      replay_engine.py        # run a golden set against a prompt version
      scorers/
        base.py
        exact.py
        semantic.py           # embedding similarity
        llm_judge.py
      gate.py                 # CI pass and fail logic
    budgets/
      quotas.py
      alerts.py
    api/
      app.py                  # FastAPI app factory
      routes_orgs.py
      routes_keys.py
      routes_requests.py
      routes_eval.py
      routes_health.py
    cli/
      main.py                 # Typer entrypoint
    retention/
      prune.py                # retention and payload truncation job
  tests/
    unit/
    integration/
    e2e/
  web/                        # the dashboard, see Section 18
```

---

## 7. Data model

Use UUID primary keys generated in the database. All timestamps are `timestamptz` in UTC. Every tenant table carries `org_id uuid not null`. Enable Row Level Security on every tenant table and write a policy that compares `org_id` to a per session setting `app.current_org`.

Tables:

**orgs**
- `id uuid pk`
- `name text not null`
- `slug text unique not null`
- `created_at timestamptz default now()`

**users**
- `id uuid pk`  (matches the Supabase auth user id)
- `email text unique not null`
- `created_at timestamptz default now()`

**memberships** (a user belongs to one or more orgs with a role)
- `id uuid pk`
- `org_id uuid not null references orgs`
- `user_id uuid not null references users`
- `role text not null check (role in ('owner','admin','member'))`
- unique on (`org_id`, `user_id`)

**api_keys** (Replay's own keys that an app uses to authenticate to the proxy)
- `id uuid pk`
- `org_id uuid not null`
- `name text not null`
- `prefix text not null`            # first 8 chars, shown in UI for identification
- `hash text not null`              # argon2 or sha256 of the full key, never the key itself
- `created_at timestamptz default now()`
- `last_used_at timestamptz`
- `revoked_at timestamptz`

**provider_keys** (the tenant's BYOK secrets, encrypted)
- `id uuid pk`
- `org_id uuid not null`
- `provider text not null check (provider in ('anthropic','openai'))`
- `label text not null`
- `ciphertext bytea not null`       # Fernet token of the provider api key
- `created_at timestamptz default now()`
- `revoked_at timestamptz`

**requests** (the core log, one row per proxied call)
- `id uuid pk`
- `org_id uuid not null`
- `api_key_id uuid references api_keys`
- `provider text not null`
- `model text not null`
- `endpoint text not null`          # messages or chat.completions
- `prompt_id uuid references prompts`        # nullable, set when the caller tags a prompt
- `prompt_version_id uuid references prompt_versions`  # nullable
- `request_body jsonb not null`     # captured input, subject to truncation policy
- `response_body jsonb`             # captured output, nullable on error
- `status_code int`
- `error text`
- `input_tokens int`
- `output_tokens int`
- `cache_read_tokens int`
- `cache_write_tokens int`
- `cost_usd numeric(12,6)`
- `latency_ms int`
- `streamed boolean not null default false`
- `created_at timestamptz default now()`
- indexes on (`org_id`, `created_at desc`), (`org_id`, `model`), (`org_id`, `prompt_id`)

**prompts**
- `id uuid pk`
- `org_id uuid not null`
- `name text not null`              # human handle, for example "support-router"
- `created_at timestamptz default now()`
- unique on (`org_id`, `name`)

**prompt_versions**
- `id uuid pk`
- `org_id uuid not null`
- `prompt_id uuid not null references prompts`
- `version int not null`            # monotonic per prompt
- `template text not null`          # the prompt text or template
- `metadata jsonb`                  # model, params, notes
- `created_at timestamptz default now()`
- unique on (`prompt_id`, `version`)

**golden_cases** (a frozen input plus an expected or reference output)
- `id uuid pk`
- `org_id uuid not null`
- `prompt_id uuid not null references prompts`
- `source_request_id uuid references requests`   # where it came from, nullable
- `input jsonb not null`
- `reference_output jsonb`          # nullable when using reference free scorers
- `tags text[]`
- `created_at timestamptz default now()`

**eval_runs**
- `id uuid pk`
- `org_id uuid not null`
- `prompt_version_id uuid not null references prompt_versions`
- `status text not null check (status in ('queued','running','done','failed'))`
- `created_at timestamptz default now()`
- `finished_at timestamptz`
- `summary jsonb`                   # counts, pass rate, mean scores

**eval_results** (one per golden case per run)
- `id uuid pk`
- `org_id uuid not null`
- `eval_run_id uuid not null references eval_runs`
- `golden_case_id uuid not null references golden_cases`
- `actual_output jsonb`
- `scores jsonb not null`           # map of scorer name to numeric score
- `passed boolean not null`
- `latency_ms int`
- `cost_usd numeric(12,6)`

**budgets**
- `id uuid pk`
- `org_id uuid not null unique`
- `monthly_limit_usd numeric(12,2)`
- `alert_threshold_pct int default 80`
- `created_at timestamptz default now()`

**alerts**
- `id uuid pk`
- `org_id uuid not null`
- `kind text not null`              # budget_threshold, budget_exceeded
- `payload jsonb`
- `created_at timestamptz default now()`
- `acknowledged_at timestamptz`

Row Level Security pattern for every tenant table:

```sql
alter table requests enable row level security;
create policy org_isolation on requests
  using (org_id = current_setting('app.current_org')::uuid);
```

Before any tenant scoped query, the session must run `set local app.current_org = '<org_id>'`. Put this in a single helper in `db/rls.py` and use it in the FastAPI dependency that opens a session, so isolation is automatic and no route can forget it.

---

## 8. Security and the key vault

- The provider key vault uses Fernet. The Fernet key comes from `REPLAY_VAULT_KEY` in the environment and is never stored in the database. Support a list of keys for rotation, where the first key encrypts and any key may decrypt.
- Provider keys are written as `ciphertext` only. The plaintext exists in memory for the duration of a single upstream request and is never logged.
- Replay API keys are shown to the user exactly once at creation. Store only a hash plus an 8 character prefix for display. Verify by hashing the presented key.
- Redact secrets from all logs. Add a logging filter that masks anything matching known key shapes (for example `sk-`, `sk-ant-`).
- The capture step must scrub `authorization` and `x-api-key` headers from anything it stores.
- Validate and cap request body size. Reject bodies over a configurable limit (default 2 megabytes) before forwarding.
- Rate limit the proxy per API key with a simple token bucket to protect against runaway loops.

---

## 9. Authentication

Two distinct auth surfaces:

**Dashboard and management API.** Supabase issues a JWT on login. Replay verifies the JWT signature against the Supabase JWKS, extracts the user id and email, looks up memberships, and resolves the active `org_id` (from a header `X-Replay-Org` or the user's single membership). A FastAPI dependency yields `(user, org_id)` and sets `app.current_org` on the session.

**Proxy endpoints.** The calling application presents a Replay API key in the `Authorization: Bearer` header (or the provider native header, see Section 10). Replay hashes it, looks it up, resolves the owning `org_id`, updates `last_used_at`, and sets the org scope. No JWT is involved on the hot path.

---

## 10. The proxy core

Endpoints:
- `POST /v1/messages` mirrors the Anthropic Messages API.
- `POST /v1/chat/completions` mirrors the OpenAI Chat Completions API.

Behavior for both:

1. Authenticate the Replay API key and resolve `org_id`.
2. Read an optional `X-Replay-Prompt` header naming a prompt, and `X-Replay-Prompt-Version` for a version, so calls can be tied to a prompt for later eval. These are optional and absent by default.
3. Select the tenant's provider key for the target provider. If none exists, return a clear 400 that names the missing key.
4. Forward the request to the upstream provider with `httpx`, preserving the path, query, method, and body, swapping only the auth header to the decrypted provider key.
5. Capture timing around the upstream call.
6. On a normal response, read usage from the provider payload, compute cost, and persist a `requests` row.
7. Return the upstream response to the caller unchanged in shape and status.

**Streaming (Server Sent Events).** This is the one genuinely hard part. When the caller requests a stream, Replay must stream the upstream response back chunk by chunk with no buffering of the full body, so time to first token is preserved. Replay tees the stream: it forwards each event to the client immediately and at the same time accumulates the parsed events in memory so it can reconstruct the final usage numbers and the assembled output after the stream closes. When the stream ends, write the `requests` row from the accumulated data. If the client disconnects mid stream, still record what was received and mark it partial. Build streaming in Phase 2, not Phase 1.

**Errors and resilience.**
- Pass provider error status and body through to the caller faithfully. Record the error on the row.
- On HTTP 429 from the provider, do not silently retry in a way that hides cost. Surface the 429 to the caller. Optionally honor a single retry with backoff only if the caller opts in via header. Default is no retry.
- Set sane timeouts: connect 10 seconds, read 600 seconds (long generations are normal). Make these config.
- If the capture or cost step fails, never fail the user's request because of it. Log the internal error and still return the provider response. Observability must not break the proxy.

---

## 11. Cost calculation

- Maintain a pricing table keyed by provider and model, with per million token rates for input, output, cache read, and cache write.
- Store pricing as data (a versioned Python module or a `model_prices` table seeded by migration), not scattered constants, so it is easy to update when providers change prices.
- At build time, verify current Anthropic and OpenAI prices against official documentation. Do not trust placeholder numbers. Treat the table below as a shape to fill, not as ground truth.

```
provider   model                     input/Mtok  output/Mtok  cache_read/Mtok  cache_write/Mtok
anthropic  claude-opus-4-x           VERIFY      VERIFY       VERIFY           VERIFY
anthropic  claude-sonnet-4-x         VERIFY      VERIFY       VERIFY           VERIFY
anthropic  claude-haiku-4-x          VERIFY      VERIFY       VERIFY           VERIFY
openai     gpt-4.x                   VERIFY      VERIFY       VERIFY           VERIFY
```

- Cost equals the sum over token classes of tokens divided by one million times the class rate. Store the result in `cost_usd` with six decimal places.
- If a model is unknown, record the request with `cost_usd` null and a warning, never a crash.

---

## 12. The evaluation harness

This is what makes Replay more than a logger.

**Promote to golden.** Given a `request_id`, `golden.py` reads the captured input (and optionally the output as a reference), and writes a `golden_cases` row tied to a prompt. The CLI exposes this as a one liner. A developer who sees a great or a bad real example can freeze it as a test case instantly.

**Prompt versioning.** A prompt is a named handle. Each edit creates a new `prompt_versions` row with an incremented version and the new template. Versions are immutable once created.

**The replay engine.** `replay_engine.py` takes a `prompt_version_id` and a set of golden cases (all cases for that prompt, or a tag filtered subset). For each case it renders the prompt version with the case input, calls the provider through the same proxy and BYOK path (so eval traffic is also logged and costed), collects the output, runs every configured scorer, and writes an `eval_results` row. It rolls the run up into an `eval_runs.summary` with pass rate and mean scores. Runs execute out of band, not in the request hot path.

**Scorers** (pluggable, all implement a common interface that returns a float in 0 to 1 and a pass boolean against a threshold):
- `exact`: normalized string equality against the reference output.
- `semantic`: cosine similarity between embeddings of the actual and reference outputs, using a provider embedding endpoint through BYOK. Pass when similarity is above a configurable threshold.
- `llm_judge`: a rubric prompt that asks a model to score the actual output, optionally given the reference, returning a structured score. Use a strict JSON response and parse defensively.

**The CI gate.** `gate.py` compares an eval run against a baseline (the previous version's run, or a pinned baseline). It computes the change in pass rate and per case regressions. The CLI command returns a non zero exit code when the pass rate drops more than a configurable tolerance or when any case flips from pass to fail. This is what a CI pipeline calls on a pull request.

**Drift.** Provide an aggregation that plots pass rate and mean score per prompt over successive versions and over calendar time, so quality trends are visible, not just point in time.

---

## 13. The CLI

Typer app named `replay`. Auth via a stored token from `replay login`. Every command is org scoped. Output uses Rich tables that match the visual language where reasonable (hard rules, bright accents in the terminal where supported).

Commands:
- `replay login` and `replay logout`.
- `replay orgs list` and `replay orgs use <slug>`.
- `replay keys create <name>` (prints the key once), `replay keys list`, `replay keys revoke <id>`.
- `replay providers add <provider> <label>` (prompts for the secret, stores it encrypted), `replay providers list`, `replay providers revoke <id>`.
- `replay logs tail` (live follow), `replay logs list --model --since --limit`, `replay logs show <id>` (full request and response with cost and latency).
- `replay cost summary --since --group-by model|prompt|day`.
- `replay prompts create <name>`, `replay prompts version <name> --file prompt.txt`, `replay prompts list`.
- `replay golden add --from-request <id> --prompt <name>`, `replay golden list --prompt <name>`.
- `replay eval run --prompt <name> --version <n>` (kicks off a run, streams progress).
- `replay eval gate --prompt <name> --version <n> --baseline <n> --tolerance 0.05` (exits non zero on regression, for CI).
- `replay budget set --limit 50 --alert-at 80`.

---

## 14. Budgets, quotas, and alerts

- A budget is a monthly dollar limit per org with an alert threshold percentage.
- A lightweight periodic job sums the current month's `cost_usd` per org, compares to the budget, and writes `alerts` rows when the threshold and the limit are crossed. Each alert kind fires once per period, not repeatedly.
- When an org exceeds its hard limit, the proxy may either warn (default) or block further calls (opt in per org via a flag). Make the behavior explicit and configurable, never a silent surprise.
- Surface alerts in the dashboard and through the CLI.

---

## 15. Configuration

All from environment, loaded by `pydantic-settings`. Provide `.env.example`. Keys:

```
REPLAY_DATABASE_URL=postgresql+asyncpg://...
REPLAY_VAULT_KEY=...                 # base64 fernet key, primary
REPLAY_VAULT_KEYS_OLD=...            # comma separated, for rotation, optional
SUPABASE_URL=...
SUPABASE_JWKS_URL=...
SUPABASE_JWT_AUD=authenticated
REPLAY_MAX_BODY_BYTES=2097152
REPLAY_UPSTREAM_CONNECT_TIMEOUT=10
REPLAY_UPSTREAM_READ_TIMEOUT=600
REPLAY_RETENTION_DAYS=30
REPLAY_LOG_LEVEL=INFO
```

---

## 16. Testing

Aim for high coverage on the proxy, the cost engine, the RLS isolation, and the eval gate. These are the parts where a bug is expensive or silent.

Required test cases:
- Proxy passthrough returns the upstream body and status unchanged, with the upstream mocked by `respx`.
- The proxy swaps the auth header to the decrypted provider key and never forwards the Replay API key upstream.
- A captured `requests` row has correct token counts and cost for a known fixture.
- Cost calculation matches hand computed values for each token class, including cache tokens.
- RLS isolation: a session scoped to org A cannot read, update, or delete org B rows, proven by direct SQL through the app session.
- A Replay API key is stored only as a hash, and authentication succeeds against the hash.
- Provider keys round trip through Fernet and are never present in plaintext in the database or logs.
- Promote to golden builds a correct case from a request fixture.
- The replay engine scores a small golden set and writes results.
- The CI gate exits non zero when pass rate drops past tolerance and zero when it holds.
- Streaming: a chunked SSE upstream is teed correctly, the client receives all events in order, and the final captured row has assembled output and usage (Phase 2).
- A failing capture or cost step does not fail the proxied request.

Test layout: `unit` for pure logic, `integration` for database and RLS against a real Postgres (spin one up in CI), `e2e` for the proxy and CLI against a mocked provider.

---

## 17. Deployment, free tier, and operations

- Database and auth: Supabase free tier. Use the Supabase tooling to create the project, run migrations, and apply RLS policies.
- Compute: Oracle Cloud Always Free VM is the most generous option. Fly.io or Render free tier are acceptable alternatives. Package the app with a small Dockerfile and a Uvicorn or Gunicorn with Uvicorn workers process.
- Retention is the one thing that can push storage past the free tier, because Replay logs every request and response. Mitigate by default:
  - A daily `retention/prune.py` job deletes `requests` rows older than `REPLAY_RETENTION_DAYS`.
  - Truncate very large `request_body` and `response_body` payloads to a configurable cap, keeping head and tail plus a note, while preserving token counts and cost exactly.
  - Optionally compress stored bodies.
- CI: GitHub Actions running Ruff, mypy, and the full pytest suite against a Postgres service container on every push and pull request.
- Health: `GET /health` returns liveness, database connectivity, and migration version. Add structured JSON logging with request ids and the org id (never the secret).

---

## 18. Design system: the visual identity

This is not a generic SaaS dashboard. The look is an analog signal laboratory: an instrument that captures a moving signal and lets you scrub back through it. Build the whole identity around capture, transport, and replay. Loud, physical, printed, mechanical. It should feel like a well made piece of lab hardware and a bold risograph poster at the same time.

Avoid the entire set of default machine made choices. Specifically forbidden:

- No rounded corners anywhere. Every corner is a true 90 degree angle. Border radius is always zero.
- No em dashes in any copy. Use periods, commas, colons, or parentheses.
- No soft blurred drop shadows. Shadows are hard, offset, and solid color with zero blur.
- No purple to blue gradients, no glassmorphism, no frosted translucency.
- No timid grays on white minimalism. No giant empty hero with one thin centered sentence.
- No generic Inter or Roboto as the personality font. No pill shaped buttons. No emoji as iconography in the product UI.

### Concept

The signal moves left to right like tape. A playhead marks the present. You can scrub back into captured history. Numbers are read like an instrument panel: large, monospaced, precise. The page is built on a visible grid, the way graph paper or an oscilloscope screen is. Color is used in confident blocks, not as subtle accents.

### Color

A warm paper base, dense ink, and four loud signal colors. Use color as flat fills in blocks, never as gradients.

```
ink        #14130F   near black, warm, for text, borders, and hard shadows
paper      #F3EFE2   warm bone background, the canvas
panel      #FBF8EF   slightly lighter paper for raised panels
lime       #C5F82A   electric lime, the primary signal and the playhead
coral      #FF4D2E   hot coral, for cost, spend, and danger
cobalt     #2438FF   deep electric blue, for links and active states
marigold   #FFB000   amber, for warnings and budgets
```

Rules:
- Default text is `ink` on `paper`. There is no pure white and no pure black anywhere.
- Borders are always `ink`, 2.5 pixels, solid.
- The signal color `lime` marks the live and the selected. The playhead is `lime`.
- `coral` always means money and risk: cost figures, over budget, destructive actions.
- Backgrounds of stat panels can be saturated blocks of a single signal color with `ink` text on top, used sparingly and deliberately for the one number that matters on a screen.
- Status uses solid rectangular tags, never soft pills: success on `lime`, error on `coral`, warning on `marigold`, info on `cobalt`, all with `ink` text and an `ink` border.

### Typography

Three voices. A wide heavy grotesque for display, a clean grotesque for prose, and a monospace for all data and numbers. Numbers are always monospaced so columns line up like a readout.

- Display and headings: a wide or expanded heavy grotesque, for example Archivo Expanded at weight 800, set in uppercase for section titles with generous letter spacing. This is the loud voice.
- Body and UI text: a neutral grotesque, for example Hanken Grotesk, weights 400 and 600.
- Data, metrics, code, tables, timestamps, costs, token counts: a monospace, for example JetBrains Mono. Every number in the product is monospaced.

Use real type scale jumps, not timid ones. A headline metric can be very large (for example 64 to 96 pixels), sitting right next to small monospaced labels at 12 to 13 pixels in uppercase. The contrast in size is part of the instrument feel.

### Shape, border, and shadow

- Border radius: 0 everywhere, no exceptions.
- Borders: 2.5 pixel solid `ink` on panels, inputs, buttons, tags, and table outlines.
- Shadow: a hard offset block shadow, for example `6px 6px 0 0 #14130F`, no blur, on raised elements like primary buttons and the active panel. This is the printed, physical feel.
- Interaction: a button at rest sits up on its hard shadow. On press it translates down and right by the shadow offset and the shadow collapses to zero, so it physically clicks into the page. This is the single signature interaction. Keep it snappy, around 60 milliseconds, with a linear or near linear easing, never a soft bounce.

### Layout

- Build on a visible grid. Show thin `ink` grid lines at low opacity behind content, like graph paper, so the instrument metaphor is literal.
- Prefer asymmetry and deliberate density over centered, airy minimalism. Align things to a strong left column. Let big numbers dominate.
- The primary observability screen is laid out like a panel of gauges across the top (total spend in `coral`, request count, median latency, error rate), then a live request stream below that scrolls like tape, newest at one edge, with a `lime` playhead marking the current row.
- The replay and eval screen uses a transport metaphor: a horizontal timeline of prompt versions, a scrub control, and a pass and fail grid where each golden case is a hard edged cell, lime for pass, coral for fail, so a regression reads as a block of coral appearing.

### Motion

- Motion is mechanical and brief, never floaty. Things snap and click. Transport controls (play, scrub, step) feel like physical buttons.
- The live request stream advances in discrete steps like tape transport, not a smooth continuous scroll.
- Loading is a moving signal trace or a stepped progress bar in `lime`, not a spinning circle.

### Iconography and detail

- Icons are simple stroke icons with square caps and joins, never rounded caps. Think technical schematic, not friendly rounded set.
- Use small monospaced labels and tick marks the way lab equipment is labeled. Section headers can carry a short uppercase monospaced kicker above them, for example `SIGNAL / LIVE` or `TRANSPORT / REPLAY`.
- Tables have a thick `ink` header rule and thin row rules. Numeric columns are right aligned and monospaced.

### Voice and copy

- Confident, plain, technical. Short declarative lines. No marketing fluff, no exclamation soup.
- No em dashes. Restructure sentences to use periods, commas, colons, or parentheses.
- Label things like an instrument: CAPTURE, REPLAY, SIGNAL, TRANSPORT, COST, DRIFT.

### A reference component, for tone

```css
:root {
  --ink: #14130F;
  --paper: #F3EFE2;
  --panel: #FBF8EF;
  --lime: #C5F82A;
  --coral: #FF4D2E;
  --cobalt: #2438FF;
  --marigold: #FFB000;
}

.btn {
  font-family: "JetBrains Mono", monospace;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--ink);
  background: var(--lime);
  border: 2.5px solid var(--ink);
  border-radius: 0;
  box-shadow: 6px 6px 0 0 var(--ink);
  padding: 12px 20px;
  transition: transform 60ms linear, box-shadow 60ms linear;
}
.btn:active {
  transform: translate(6px, 6px);
  box-shadow: 0 0 0 0 var(--ink);
}

.stat-cost {
  font-family: "JetBrains Mono", monospace;
  font-size: 72px;
  color: var(--ink);
  background: var(--coral);
  border: 2.5px solid var(--ink);
  padding: 16px 20px;
}
```

Use this as the seed for the whole UI. Hard edges, flat loud color, monospaced numbers, hard offset shadows, a physical click. Original, fresh, and unmistakable.

---

## 19. Build order and acceptance per phase

Ship in phases. Do not start a phase until the previous one runs and its tests pass.

**Phase 1: the spine.**
Repo scaffold, config, Postgres, all models and migrations, RLS on every table, the key vault, both auth surfaces, a non streaming proxy for Anthropic with capture and cost, and the core CLI (`login`, `keys`, `providers`, `logs`, `cost`).
Acceptance: a real Anthropic call routed through Replay with a tenant key returns correctly, a `requests` row is written with correct cost, the CLI shows it, and the RLS isolation test passes.

**Phase 2: production proxy.**
OpenAI provider, full SSE streaming with teeing, budgets and quotas and alerts, retention and truncation jobs, rate limiting, and the web dashboard observability screen in the design system above.
Acceptance: a streamed call preserves time to first token and still records assembled output and usage, an org over budget triggers exactly one alert, and the dashboard shows the live request stream.

**Phase 3: the eval harness.**
Prompts and versions, promote to golden, the replay engine, the three scorers, eval runs and results, and the replay and eval dashboard screen with the transport and pass and fail grid.
Acceptance: a prompt edit produces a new version, a replay over a golden set scores every case, and the dashboard shows pass and fail per case.

**Phase 4: CI and drift.**
The CI gate command and a GitHub Actions example workflow, drift aggregation and its dashboard view, and the LLM judge scorer hardened with strict JSON parsing.
Acceptance: a deliberately worse prompt version makes `replay eval gate` exit non zero in CI, and the drift view shows pass rate over versions.

---

## 20. Definition of done

- All four phases complete, each with passing tests.
- Ruff clean, mypy strict clean on the `replay` package.
- RLS proven by test on every tenant table.
- No secret anywhere in source, logs, or fixtures.
- Runs end to end on free tier infrastructure with the documented environment.
- The dashboard matches the design system: zero rounded corners, hard offset shadows, the warm paper and loud signal palette, monospaced numbers, and no em dashes in any copy.
- A README that explains the one line base_url swap, the BYOK setup, and the CLI workflow, written in the same plain confident voice.

Build it in order. Keep it free. Keep it isolated. Make it unmistakable.
