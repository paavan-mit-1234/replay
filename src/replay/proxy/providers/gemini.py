"""Gemini provider via Google's OpenAI-compatible endpoint.

Google exposes an OpenAI-compatible surface at
https://generativelanguage.googleapis.com/v1beta/openai, so the proxy can speak
to Gemini using the same /chat/completions shape as OpenAI. Gemini has a free
tier, which makes it the zero-cost way to exercise the proxy end to end.
"""

from __future__ import annotations

from typing import Any

from replay.cost.calculator import Usage, usage_from_openai


class GeminiProvider:
    name = "gemini"
    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"

    def auth_headers(self, secret: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {secret}"}

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
        return usage_from_openai(usage)


gemini_provider = GeminiProvider()
