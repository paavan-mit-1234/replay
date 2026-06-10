# Replay

Self hostable, multi tenant LLM observability and evaluation. One proxy captures
your production traffic. The same captured traffic is replayed against new prompt
versions to catch regressions before they ship.

Replay does two things with one shared data model:

- **Observe.** Point your SDK `base_url` at Replay. It forwards each call using your
  own provider key (BYOK), then records tokens, cost, latency, model, and status.
- **Evaluate.** Promote any logged request to a golden case, version your prompts,
  and replay the golden set on every change. A CI gate fails the build on a regression.

## Status

Phase 1 (the spine) is under construction: multi tenant proxy with strict tenant
isolation, BYOK key vault, cost accounting, and the core CLI.

## Quick start (local)

```
python -m uv venv
python -m uv pip install -e ".[dev]"
cp .env.example .env
# set REPLAY_VAULT_KEY and REPLAY_DATABASE_URL in .env
python -m replay.cli.main --help
```

Generate a vault key:

```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## The one line swap

Once you have a Replay API key and have stored a provider key, point your client at
Replay and keep using your provider SDK as normal. Replay forwards with your key and
records everything.

```
base_url = "https://your-replay-host/v1"
```

## Design

Replay's dashboard uses a deliberate, original visual identity (an analog signal
laboratory: hard edges, loud flat color, monospaced numbers). See BUILD_PROMPT.md
section 18 for the full design system.

## License

MIT.
