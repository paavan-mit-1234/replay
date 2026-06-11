"""Cost engine tests."""

from __future__ import annotations

from replay.cost.calculator import Usage, compute_cost, usage_from_openai
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


def test_gemini_thinking_tokens_fold_into_output() -> None:
    # Gemini's compatible endpoint leaves thinking out of completion_tokens:
    # total 1000 = 100 prompt + 300 completion + 600 thinking.
    usage = usage_from_openai(
        {"prompt_tokens": 100, "completion_tokens": 300, "total_tokens": 1000}
    )
    assert usage == Usage(input_tokens=100, output_tokens=900)


def test_openai_reasoning_already_in_completion_is_not_double_counted() -> None:
    # OpenAI includes reasoning in completion_tokens, so total adds up exactly
    # and the details breakdown must not be added again.
    usage = usage_from_openai(
        {
            "prompt_tokens": 100,
            "completion_tokens": 500,
            "total_tokens": 600,
            "completion_tokens_details": {"reasoning_tokens": 400},
        }
    )
    assert usage == Usage(input_tokens=100, output_tokens=500)


def test_usage_from_openai_cached_tokens_and_missing_fields() -> None:
    usage = usage_from_openai(
        {
            "prompt_tokens": 200,
            "completion_tokens": 50,
            "prompt_tokens_details": {"cached_tokens": 150},
        }
    )
    assert usage == Usage(input_tokens=200, output_tokens=50, cache_read_tokens=150)
    assert usage_from_openai({}) == Usage()
