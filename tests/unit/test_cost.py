"""Cost engine tests."""

from __future__ import annotations

from replay.cost.calculator import Usage, compute_cost
from replay.cost.pricing import lookup


def test_opus_input_and_output() -> None:
    # 1M input at $5 plus 1M output at $25.
    cost = compute_cost("anthropic", "claude-opus-4-8", Usage(1_000_000, 1_000_000))
    assert cost == 30.0


def test_all_token_classes_including_cache() -> None:
    # Sonnet: input 3, output 15, cache_read 0.30, cache_write 3.75 per Mtok.
    usage = Usage(
        input_tokens=500_000,
        output_tokens=200_000,
        cache_read_tokens=1_000_000,
        cache_write_tokens=100_000,
    )
    expected = (
        500_000 * 3.0
        + 200_000 * 15.0
        + 1_000_000 * 0.30
        + 100_000 * 3.75
    ) / 1_000_000
    assert compute_cost("anthropic", "claude-sonnet-4-6", usage) == round(expected, 6)


def test_unknown_model_returns_none() -> None:
    assert compute_cost("anthropic", "claude-made-up", Usage(10, 10)) is None


def test_dated_model_id_strips_to_alias() -> None:
    assert lookup("anthropic", "claude-haiku-4-5-20251001") is not None


def test_zero_usage_is_zero_cost() -> None:
    assert compute_cost("anthropic", "claude-opus-4-8", Usage()) == 0.0
