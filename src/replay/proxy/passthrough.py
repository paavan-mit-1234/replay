"""Upstream forwarding with httpx.

The proxy swaps only the auth: the incoming Replay key is dropped and the
tenant's decrypted provider secret is attached. Hop by hop and client auth
headers are never forwarded upstream.
"""

from __future__ import annotations

import httpx

from replay.config import get_settings
from replay.proxy.providers.base import Provider

# Headers we never forward from the caller to the provider.
_STRIP = {
    "authorization",
    "x-api-key",
    "host",
    "content-length",
    "connection",
    "accept-encoding",
}


def _forward_headers(incoming: dict[str, str], provider: Provider, secret: str) -> dict[str, str]:
    headers = {k: v for k, v in incoming.items() if k.lower() not in _STRIP}
    headers.update(provider.auth_headers(secret))
    headers.setdefault("content-type", "application/json")
    return headers


def _timeout() -> httpx.Timeout:
    settings = get_settings()
    return httpx.Timeout(
        connect=settings.upstream_connect_timeout,
        read=settings.upstream_read_timeout,
        write=settings.upstream_read_timeout,
        pool=settings.upstream_connect_timeout,
    )


async def forward(
    provider: Provider,
    secret: str,
    path: str,
    body: bytes,
    incoming_headers: dict[str, str],
) -> httpx.Response:
    """POST the body to the provider and return the raw response (non streaming)."""
    headers = _forward_headers(incoming_headers, provider, secret)
    async with httpx.AsyncClient(
        base_url=provider.base_url, timeout=_timeout(), http2=True
    ) as client:
        return await client.post(path, content=body, headers=headers)


def build_stream(
    provider: Provider,
    secret: str,
    path: str,
    body: bytes,
    incoming_headers: dict[str, str],
) -> tuple[httpx.AsyncClient, httpx.Request]:
    """Build a client and a streaming request. The caller sends it with
    stream=True, iterates the body to tee it, then closes both. The client
    lifetime must span the whole stream, so it is not closed here.
    """
    client = httpx.AsyncClient(base_url=provider.base_url, timeout=_timeout(), http2=True)
    headers = _forward_headers(incoming_headers, provider, secret)
    request = client.build_request("POST", path, content=body, headers=headers)
    return client, request
