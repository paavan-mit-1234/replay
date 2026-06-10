"""Cost calculation from token usage."""

from __future__ import annotations

from dataclasses import dataclass

from replay.cost.pricing import lookup


@dataclass(frozen=True)
class Usage:
    """Token counts captured from a provider response."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


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
