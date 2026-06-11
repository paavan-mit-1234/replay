"""Eval harness pure-helper tests (no DB, no network)."""

from __future__ import annotations

from replay.evals import parse_judge, render_input


def test_render_input_substitutes_placeholder() -> None:
    assert render_input("Q: {input}", "hello") == "Q: hello"


def test_render_input_appends_when_no_placeholder() -> None:
    assert render_input("Answer briefly.", "hello") == "Answer briefly.\n\nhello"


def test_render_input_passthrough_when_template_blank() -> None:
    assert render_input("   ", "hello") == "hello"


def test_parse_judge_plain_json() -> None:
    assert parse_judge('{"score": 80, "reason": "close enough"}') == (80, "close enough")


def test_parse_judge_clamps_and_tolerates_fences() -> None:
    score, reason = parse_judge('```json\n{"score": 150, "reason": "great"}\n```')
    assert score == 100
    assert reason == "great"


def test_parse_judge_handles_garbage() -> None:
    assert parse_judge("not json at all") == (0, "could not parse judge response")
