"""Cost calculation from token usage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from replay.cost.pricing import lookup


@dataclass(frozen=True)
class Usage:
    """Token counts captured from a provider response."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


def usage_from_openai(usage: dict[str, Any]) -> Usage:
    """Build a Usage from an OpenAI-style usage object.

    Reasoning ("thinking") tokens are billed at the output rate, but Gemini's
    OpenAI-compatible endpoint leaves them out of completion_tokens; they only
    show up in total_tokens. Anything counted beyond prompt + completion is
    therefore folded into output. OpenAI itself includes reasoning in
    completion_tokens, so the inferred extra is zero there and nothing is
    counted twice.
    """
    prompt = int(usage.get("prompt_tokens", 0) or 0)
    completion = int(usage.get("completion_tokens", 0) or 0)
    total = int(usage.get("total_tokens", 0) or 0)
    hidden = max(total - prompt - completion, 0)
    details = usage.get("prompt_tokens_details") or {}
    cached = int(details.get("cached_tokens", 0) or 0) if isinstance(details, dict) else 0
    return Usage(
        input_tokens=prompt,
        output_tokens=completion + hidden,
        cache_read_tokens=cached,
        cache_write_tokens=0,
    )


def compute_cost(provider: str, model: str, usage: Usage) -> float | None:
    """Return the dollar cost for a call, or None if the model is unknown.

    Cost is the sum over token classes of (tokens / 1e6) times the class rate.
    Rounded to six decimal places to match the requests.cost_usd column.
    """
    price = lookup(provider, model)
    if price is None:
        return None
    total = (
        usage.input_tokens * price.input
        + usage.output_tokens * price.output
        + usage.cache_read_tokens * price.cache_read
        + usage.cache_write_tokens * price.cache_write
    ) / 1_000_000
    return round(total, 6)
