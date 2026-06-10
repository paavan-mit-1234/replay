"""Build the requests log row from a proxied call."""

from __future__ import annotations

import uuid
from typing import Any

from replay.cost.calculator import Usage, compute_cost
from replay.db.models import Request


def build_request_row(
    *,
    org_id: uuid.UUID,
    api_key_id: uuid.UUID | None,
    provider: str,
    model: str,
    endpoint: str,
    request_body: dict[str, Any],
    response_body: dict[str, Any] | None,
    status_code: int | None,
    error: str | None,
    usage: Usage,
    latency_ms: int,
    streamed: bool = False,
) -> Request:
    """Assemble a Request row, computing cost from usage. Stores no secrets:
    only the JSON bodies are kept, never auth headers.
    """
    cost = compute_cost(provider, model, usage)
    return Request(
        org_id=org_id,
        api_key_id=api_key_id,
        provider=provider,
        model=model,
        endpoint=endpoint,
        request_body=request_body,
        response_body=response_body,
        status_code=status_code,
        error=error,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_tokens=usage.cache_read_tokens,
        cache_write_tokens=usage.cache_write_tokens,
        cost_usd=cost,
        latency_ms=latency_ms,
        streamed=streamed,
    )
