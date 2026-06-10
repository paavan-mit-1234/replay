"""Model pricing tables.

Rates are US dollars per one million tokens, by token class. Prompt cache read
is 0.1x the input rate, and the 5 minute cache write is 1.25x the input rate,
which is how these tables are derived. Verified against Anthropic pricing as of
2026-06. Update here when providers change prices; nothing else needs to change.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    """Per million token rates for one model."""

    input: float
    output: float
    cache_read: float
    cache_write: float


# Keyed by (provider, model). Anthropic exposes model aliases without date
# suffixes, so we match on the alias and also accept dated variants via
# normalization in lookup().
PRICES: dict[tuple[str, str], Price] = {
    ("anthropic", "claude-opus-4-8"): Price(5.00, 25.00, 0.50, 6.25),
    ("anthropic", "claude-opus-4-7"): Price(5.00, 25.00, 0.50, 6.25),
    ("anthropic", "claude-opus-4-6"): Price(5.00, 25.00, 0.50, 6.25),
    ("anthropic", "claude-opus-4-5"): Price(5.00, 25.00, 0.50, 6.25),
    ("anthropic", "claude-sonnet-4-6"): Price(3.00, 15.00, 0.30, 3.75),
    ("anthropic", "claude-sonnet-4-5"): Price(3.00, 15.00, 0.30, 3.75),
    ("anthropic", "claude-haiku-4-5"): Price(1.00, 5.00, 0.10, 1.25),
    # Gemini paid rates (per Mtok). The free tier costs nothing; these let the
    # cost engine report the notional spend. Cache write is 0 because Gemini
    # bills cached context by storage time, not per written token. Verify
    # against Google pricing before relying on these.
    ("gemini", "gemini-2.5-flash"): Price(0.30, 2.50, 0.075, 0.00),
    ("gemini", "gemini-2.5-pro"): Price(1.25, 10.00, 0.3125, 0.00),
    ("gemini", "gemini-2.0-flash"): Price(0.10, 0.40, 0.025, 0.00),
    ("gemini", "gemini-2.0-flash-lite"): Price(0.075, 0.30, 0.01875, 0.00),
    ("gemini", "gemini-1.5-flash"): Price(0.075, 0.30, 0.01875, 0.00),
    # OpenAI rates are placeholders pending Phase 2. Verify before enabling
    # the OpenAI provider. Left here so the table shape is complete.
    ("openai", "gpt-4.1"): Price(2.00, 8.00, 0.50, 0.00),
    ("openai", "gpt-4o"): Price(2.50, 10.00, 1.25, 0.00),
}


def lookup(provider: str, model: str) -> Price | None:
    """Find a price for a provider and model.

    Tries the exact model id, then strips a trailing date suffix
    (for example claude-opus-4-8-20260101 to claude-opus-4-8).
    Returns None when the model is unknown, so callers record the request
    with a null cost rather than crashing.
    """
    exact = PRICES.get((provider, model))
    if exact is not None:
        return exact
    # Strip a trailing -YYYYMMDD style suffix if present.
    parts = model.rsplit("-", 1)
    if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 8:
        return PRICES.get((provider, parts[0]))
    return None
