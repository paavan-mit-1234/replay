"""Stream a call through the Replay proxy and print tokens as they arrive.

Usage:
    python scripts/try_stream.py <rpl_key> "your prompt" [model]

Demonstrates token-by-token passthrough. The proxy tees the stream: you see
tokens live here, and Replay still logs the call with usage and cost on close.
Set stream_options.include_usage so the upstream reports tokens in the stream.
"""

from __future__ import annotations

import json
import os
import sys

import httpx


def main() -> int:
    if len(sys.argv) < 3:
        print('usage: python scripts/try_stream.py <rpl_key> "prompt" [model]')
        return 2
    rpl_key = sys.argv[1]
    prompt = sys.argv[2]
    model = sys.argv[3] if len(sys.argv) > 3 else "gemini-2.5-flash"
    base = os.environ.get("REPLAY_API_URL", "http://localhost:8000")

    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    with httpx.stream(
        "POST",
        f"{base}/v1/chat/completions",
        headers={"Authorization": f"Bearer {rpl_key}"},
        json=body,
        timeout=60,
    ) as r:
        print(f"HTTP {r.status_code}\n")
        for line in r.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            for choice in data.get("choices", []):
                piece = choice.get("delta", {}).get("content")
                if piece:
                    print(piece, end="", flush=True)
    print("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
