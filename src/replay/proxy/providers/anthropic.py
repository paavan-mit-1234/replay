"""Anthropic provider."""

from __future__ import annotations

from typing import Any

from replay.cost.calculator import Usage

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"
    base_url = "https://api.anthropic.com"

    def auth_headers(self, secret: str) -> dict[str, str]:
        return {
            "x-api-key": secret,
            "anthropic-version": ANTHROPIC_VERSION,
        }

    def extract_model(
        self, request_body: dict[str, Any], response_body: dict[str, Any] | None
    ) -> str:
        if isinstance(response_body, dict) and isinstance(response_body.get("model"), str):
            return str(response_body["model"])
        model = request_body.get("model")
        return model if isinstance(model, str) else "unknown"

    def extract_usage(self, response_body: dict[str, Any] | None) -> Usage:
        if not isinstance(response_body, dict):
            return Usage()
        usage = response_body.get("usage")
        if not isinstance(usage, dict):
            return Usage()
        return Usage(
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0) or 0),
            cache_write_tokens=int(usage.get("cache_creation_input_tokens", 0) or 0),
        )


anthropic_provider = AnthropicProvider()
