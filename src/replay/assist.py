"""Assistant helpers: one-shot completions and embeddings via the org's Gemini
key. Used by the chat workspace, Prompt Doctor, Autopsy, and the learning loop.
These are internal meta-calls and are intentionally not logged as user traffic.
"""

from __future__ import annotations

import json

from replay.proxy import passthrough
from replay.proxy.providers.gemini import gemini_provider

DEFAULT_MODEL = "gemini-2.5-flash"
# gemini-embedding-001 returns 3072 dims by default; we request 768 to match the
# messages.embedding column (vector(768)).
EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768


async def complete(secret: str, system: str, user: str, model: str = DEFAULT_MODEL) -> str:
    """Run a single non-streaming completion and return the assistant text."""
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    resp = await passthrough.forward(
        gemini_provider, secret, "/chat/completions", json.dumps(body).encode(), {}
    )
    try:
        data = resp.json()
        return str(data["choices"][0]["message"]["content"])
    except Exception:  # noqa: BLE001
        return ""


async def embed(secret: str, content: str) -> list[float] | None:
    """Return a 768-dim embedding for text, or None on failure (best effort)."""
    body = {"model": EMBED_MODEL, "input": content[:8000], "dimensions": EMBED_DIM}
    try:
        resp = await passthrough.forward(
            gemini_provider, secret, "/embeddings", json.dumps(body).encode(), {}
        )
        if resp.status_code >= 400:
            return None
        vec = resp.json()["data"][0]["embedding"]
        return [float(x) for x in vec]
    except Exception:  # noqa: BLE001
        return None


def vector_literal(vec: list[float]) -> str:
    """Format an embedding as a pgvector literal, e.g. [0.1,0.2,...]."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
