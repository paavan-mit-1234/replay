"""Fire one call through the Replay proxy to Gemini, for manual testing.

Usage:
    python scripts/try_call.py <rpl_key> "your prompt here" [model]

Defaults to gemini-2.0-flash. The proxy must be running on localhost:8000 and
the org must have a gemini provider key stored.
"""

from __future__ import annotations

import sys

import httpx


def main() -> int:
    if len(sys.argv) < 3:
        print('usage: python scripts/try_call.py <rpl_key> "prompt" [model]')
        return 2
    rpl_key = sys.argv[1]
    prompt = sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else "gemini-2.5-flash"

    resp = httpx.post(
        "http://localhost:8000/v1/chat/completions",
        headers={"Authorization": f"Bearer {rpl_key}"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=60,
    )
    print(f"HTTP {resp.status_code}")
    data = resp.json()
    if resp.status_code < 400:
        text = data["choices"][0]["message"]["content"]
        print("\nreply:\n" + text)
        print("\nusage:", data.get("usage"))
    else:
        print(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
