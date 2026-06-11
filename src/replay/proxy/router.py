"""The proxy endpoints.

Supports the Anthropic Messages API and the OpenAI-style chat completions shape
(used to reach Gemini's free tier), both non streaming and streaming. The hot
path stays thin: authenticate, fetch the tenant secret, forward, return. For
streams the response is teed (forwarded chunk by chunk while accumulated in
memory) so usage and assembled output are captured once the stream closes.
Capture and cost never fail the caller's request.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from replay import budget
from replay.auth.deps import ProxyContext, get_proxy_context
from replay.config import get_settings
from replay.cost.calculator import Usage
from replay.db.rls import org_session
from replay.proxy import capture, passthrough
from replay.proxy.providers.anthropic import anthropic_provider
from replay.proxy.providers.base import Provider
from replay.proxy.providers.gemini import gemini_provider
from replay.proxy.streaming import SSEParser, make_state
from replay.vault.keys import get_active_secret

logger = logging.getLogger("replay.proxy")

router = APIRouter()

# Cap stored assembled stream text so a long generation does not bloat a row.
STREAM_TEXT_CAP = 100_000


async def _read_body(request: Request) -> tuple[bytes, dict[str, Any]]:
    """Read and validate the request body, returning raw bytes and parsed JSON."""
    settings = get_settings()
    raw = await request.body()
    if len(raw) > settings.max_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="request body too large",
        )
    try:
        body = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="invalid JSON body"
        ) from exc
    return raw, body


async def _safe_capture(**fields: Any) -> None:
    """Build and persist a requests row. Never raises into the caller's path.

    After the row lands, re-evaluate the org's monthly budget so a crossed
    threshold raises an alert. Both steps are best effort.
    """
    try:
        row = capture.build_request_row(**fields)
        async with org_session(fields["org_id"]) as session:
            session.add(row)
    except Exception:  # noqa: BLE001
        logger.exception("failed to capture request log")
        return
    with contextlib.suppress(Exception):
        await budget.evaluate_and_alert(fields["org_id"])


async def _fetch_secret(provider: Provider, org_id: Any) -> str:
    async with org_session(org_id) as session:
        secret = await get_active_secret(session, provider.name)
    if secret is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"no active {provider.name} provider key for this org",
        )
    return secret


async def _proxy(
    *,
    provider: Provider,
    upstream_path: str,
    endpoint_label: str,
    request: Request,
    raw: bytes,
    request_body: dict[str, Any],
    ctx: ProxyContext,
) -> Response:
    """Non streaming proxy flow."""
    secret = await _fetch_secret(provider, ctx.org_id)

    started = time.monotonic()
    error: str | None = None
    response_body: dict[str, Any] | None = None
    status_code = status.HTTP_502_BAD_GATEWAY
    content = b""
    try:
        upstream = await passthrough.forward(
            provider, secret, upstream_path, raw, dict(request.headers)
        )
        status_code = upstream.status_code
        content = upstream.content
        try:
            response_body = upstream.json()
        except ValueError:
            response_body = None
    except Exception as exc:  # noqa: BLE001
        error = repr(exc)
        logger.warning("upstream call failed: %s", error)

    latency_ms = int((time.monotonic() - started) * 1000)
    model = provider.extract_model(request_body, response_body)
    usage = provider.extract_usage(response_body if status_code < 400 else None)

    await _safe_capture(
        org_id=ctx.org_id,
        api_key_id=ctx.api_key_id,
        provider=provider.name,
        model=model,
        endpoint=endpoint_label,
        request_body=request_body,
        response_body=response_body if status_code < 400 else None,
        status_code=status_code if error is None else None,
        error=error,
        usage=usage,
        latency_ms=latency_ms,
    )

    if error is not None:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="upstream call failed"
        )
    return Response(content=content, status_code=status_code, media_type="application/json")


async def _stream_proxy(
    *,
    provider: Provider,
    upstream_path: str,
    endpoint_label: str,
    request: Request,
    raw: bytes,
    request_body: dict[str, Any],
    ctx: ProxyContext,
) -> Response:
    """Streaming proxy flow with teeing. Forwards each chunk untouched while
    accumulating usage and assembled text, then captures on close.
    """
    secret = await _fetch_secret(provider, ctx.org_id)
    client, upstream_req = passthrough.build_stream(
        provider, secret, upstream_path, raw, dict(request.headers)
    )
    started = time.monotonic()

    try:
        upstream = await client.send(upstream_req, stream=True)
    except Exception as exc:  # noqa: BLE001
        await client.aclose()
        latency_ms = int((time.monotonic() - started) * 1000)
        await _safe_capture(
            org_id=ctx.org_id,
            api_key_id=ctx.api_key_id,
            provider=provider.name,
            model=provider.extract_model(request_body, None),
            endpoint=endpoint_label,
            request_body=request_body,
            response_body=None,
            status_code=None,
            error=repr(exc),
            usage=Usage(),
            latency_ms=latency_ms,
            streamed=True,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="upstream call failed"
        ) from exc

    status_code = upstream.status_code

    # An upstream error is not an SSE stream: read it whole and pass it through.
    if status_code >= 400:
        body = await upstream.aread()
        media = upstream.headers.get("content-type", "application/json")
        await upstream.aclose()
        await client.aclose()
        latency_ms = int((time.monotonic() - started) * 1000)
        await _safe_capture(
            org_id=ctx.org_id,
            api_key_id=ctx.api_key_id,
            provider=provider.name,
            model=provider.extract_model(request_body, None),
            endpoint=endpoint_label,
            request_body=request_body,
            response_body=None,
            status_code=status_code,
            error=None,
            usage=Usage(),
            latency_ms=latency_ms,
            streamed=True,
        )
        return Response(content=body, status_code=status_code, media_type=media)

    state = make_state(provider.name)
    parser = SSEParser()
    media = upstream.headers.get("content-type", "text/event-stream")

    async def gen() -> AsyncIterator[bytes]:
        # Tee: forward each chunk untouched while accumulating in memory.
        try:
            async for chunk in upstream.aiter_bytes():
                for data in parser.feed(chunk):
                    try:
                        state.consume(data)
                    except Exception:  # noqa: BLE001
                        logger.exception("stream consume failed")
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    async def capture_on_close() -> None:
        # Runs as a background task after the response is fully sent, so the DB
        # write is not cancelled when the request cycle tears down (which is why
        # capture cannot live in the generator's finally).
        latency_ms = int((time.monotonic() - started) * 1000)
        await _safe_capture(
            org_id=ctx.org_id,
            api_key_id=ctx.api_key_id,
            provider=provider.name,
            model=state.model or provider.extract_model(request_body, None),
            endpoint=endpoint_label,
            request_body=request_body,
            response_body={
                "streamed": True,
                "partial": not state.done,
                "text": state.text[:STREAM_TEXT_CAP],
            },
            status_code=status_code,
            error=None if state.done else "stream incomplete",
            usage=state.usage,
            latency_ms=latency_ms,
            streamed=True,
        )

    return StreamingResponse(
        gen(),
        status_code=status_code,
        media_type=media,
        background=BackgroundTask(capture_on_close),
    )


async def _dispatch(
    *,
    provider: Provider,
    upstream_path: str,
    endpoint_label: str,
    request: Request,
    raw: bytes,
    body: dict[str, Any],
    ctx: ProxyContext,
) -> Response:
    await budget.enforce(ctx.org_id)
    handler = _stream_proxy if body.get("stream") else _proxy
    return await handler(
        provider=provider,
        upstream_path=upstream_path,
        endpoint_label=endpoint_label,
        request=request,
        raw=raw,
        request_body=body,
        ctx=ctx,
    )


async def proxy_chat_for_org(
    *,
    request: Request,
    ctx: ProxyContext,
    model: str,
    prompt: str,
    stream: bool,
) -> Response:
    """Run a chat completion on behalf of an org (used by the in-app playground).

    Builds an OpenAI-style request from a prompt and runs it through the same
    proxy and capture path, so playground calls are logged like any other.
    """
    if not (isinstance(model, str) and model.startswith("gemini")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="the playground supports gemini-* models for now",
        )
    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }
    if stream:
        body["stream_options"] = {"include_usage": True}
    raw = json.dumps(body).encode()
    return await _dispatch(
        provider=gemini_provider,
        upstream_path="/chat/completions",
        endpoint_label="chat.completions",
        request=request,
        raw=raw,
        body=body,
        ctx=ctx,
    )


@router.post("/v1/messages")
async def messages(
    request: Request,
    ctx: Annotated[ProxyContext, Depends(get_proxy_context)],
    x_replay_prompt: Annotated[str | None, Header()] = None,
    x_replay_prompt_version: Annotated[str | None, Header()] = None,
) -> Response:
    """Anthropic Messages API (streaming and non streaming)."""
    raw, body = await _read_body(request)
    return await _dispatch(
        provider=anthropic_provider,
        upstream_path="/v1/messages",
        endpoint_label="messages",
        request=request,
        raw=raw,
        body=body,
        ctx=ctx,
    )


@router.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    ctx: Annotated[ProxyContext, Depends(get_proxy_context)],
    x_replay_prompt: Annotated[str | None, Header()] = None,
    x_replay_prompt_version: Annotated[str | None, Header()] = None,
) -> Response:
    """OpenAI-style chat completions. Routes gemini-* models to Google's
    OpenAI-compatible endpoint. OpenAI itself arrives later in Phase 2.
    """
    raw, body = await _read_body(request)
    model = body.get("model", "")
    if isinstance(model, str) and model.startswith("gemini"):
        provider: Provider = gemini_provider
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="this build supports gemini-* models here; OpenAI arrives in Phase 2",
        )
    return await _dispatch(
        provider=provider,
        upstream_path="/chat/completions",
        endpoint_label="chat.completions",
        request=request,
        raw=raw,
        body=body,
        ctx=ctx,
    )
