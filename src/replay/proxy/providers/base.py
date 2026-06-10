"""Provider interface.

A provider knows its upstream base URL, how to authenticate with a tenant's
secret, and how to read usage and model out of a response. Keeping this behind
an interface lets the proxy stay provider agnostic and makes adding OpenAI in
Phase 2 a matter of one more implementation.
"""

from __future__ import annotations

from typing import Any, Protocol

from replay.cost.calculator import Usage


class Provider(Protocol):
    name: str
    base_url: str

    def auth_headers(self, secret: str) -> dict[str, str]:
        """Headers that authenticate the upstream call with the tenant secret."""
        ...

    def extract_model(
        self, request_body: dict[str, Any], response_body: dict[str, Any] | None
    ) -> str:
        """Determine the model id for this call."""
        ...

    def extract_usage(self, response_body: dict[str, Any] | None) -> Usage:
        """Read token counts from a successful response body."""
        ...
