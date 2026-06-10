"""Streaming proxy tests: teeing preserves the byte stream to the client while
capturing assembled output and usage once the stream closes."""

from __future__ import annotations

import contextlib
import uuid

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from replay.api.app import create_app
from replay.auth.deps import ProxyContext, get_proxy_context

ORG_ID = uuid.uuid4()
API_KEY_ID = uuid.uuid4()
SECRET = "provider-secret"

ANTHROPIC_UPSTREAM = "https://api.anthropic.com/v1/messages"
GEMINI_UPSTREAM = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

ANTHROPIC_SSE = (
    b'event: message_start\n'
    b'data: {"type":"message_start","message":{"model":"claude-opus-4-8",'
    b'"usage":{"input_tokens":10,"cache_read_input_tokens":0,"cache_creation_input_tokens":0}}}\n\n'
    b'event: content_block_delta\n'
    b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}\n\n'
    b'event: content_block_delta\n'
    b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":" world"}}\n\n'
    b'event: message_delta\n'
    b'data: {"type":"message_delta","usage":{"output_tokens":5}}\n\n'
    b'event: message_stop\n'
    b'data: {"type":"message_stop"}\n\n'
)

GEMINI_SSE = (
    b'data: {"model":"gemini-2.5-flash","choices":[{"delta":{"content":"Hello"}}]}\n\n'
    b'data: {"model":"gemini-2.5-flash","choices":[{"delta":{"content":" world"},'
    b'"finish_reason":"stop"}]}\n\n'
    b'data: {"model":"gemini-2.5-flash","choices":[],'
    b'"usage":{"prompt_tokens":6,"completion_tokens":8}}\n\n'
    b'data: [DONE]\n\n'
)


class FakeSession:
    def __init__(self, sink: list) -> None:  # noqa: ANN001
        self._sink = sink

    def add(self, row: object) -> None:
        self._sink.append(row)


def _fake_org_session_factory(sink: list):  # noqa: ANN001
    @contextlib.asynccontextmanager
    async def _fake(org_id):  # noqa: ANN001
        yield FakeSession(sink)

    return _fake


async def _fake_secret(session, provider):  # noqa: ANN001
    return SECRET


@pytest.fixture
def sink(monkeypatch):  # noqa: ANN001
    rows: list = []
    monkeypatch.setattr("replay.proxy.router.get_active_secret", _fake_secret)
    monkeypatch.setattr("replay.proxy.router.org_session", _fake_org_session_factory(rows))
    return rows


@pytest.fixture
def client(sink):  # noqa: ANN001
    app = create_app()
    app.dependency_overrides[get_proxy_context] = lambda: ProxyContext(
        org_id=ORG_ID, api_key_id=API_KEY_ID
    )
    return TestClient(app)


@respx.mock
def test_anthropic_stream_tees_and_captures(client, sink) -> None:  # noqa: ANN001
    respx.post(ANTHROPIC_UPSTREAM).mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=ANTHROPIC_SSE
        )
    )
    resp = client.post(
        "/v1/messages",
        headers={"Authorization": "Bearer rpl_caller"},
        json={"model": "claude-opus-4-8", "messages": [], "stream": True},
    )
    assert resp.status_code == 200
    # The client receives every event byte for byte, in order.
    assert resp.content == ANTHROPIC_SSE
    # The capture row reconstructs usage and assembled text.
    assert len(sink) == 1
    row = sink[0]
    assert row.streamed is True
    assert row.input_tokens == 10
    assert row.output_tokens == 5
    assert row.response_body["text"] == "Hello world"
    assert row.response_body["partial"] is False
    assert row.cost_usd is not None


@respx.mock
def test_gemini_stream_tees_and_captures(client, sink) -> None:  # noqa: ANN001
    respx.post(GEMINI_UPSTREAM).mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=GEMINI_SSE
        )
    )
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer rpl_caller"},
        json={"model": "gemini-2.5-flash", "messages": [], "stream": True},
    )
    assert resp.status_code == 200
    assert resp.content == GEMINI_SSE
    row = sink[0]
    assert row.streamed is True
    assert row.input_tokens == 6
    assert row.output_tokens == 8
    assert row.response_body["text"] == "Hello world"
    assert row.response_body["partial"] is False


@respx.mock
def test_partial_stream_is_marked(client, sink) -> None:  # noqa: ANN001
    # Truncated stream: no message_stop, so it is recorded as partial.
    truncated = ANTHROPIC_SSE.split(b"event: message_stop")[0]
    respx.post(ANTHROPIC_UPSTREAM).mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=truncated
        )
    )
    resp = client.post(
        "/v1/messages",
        headers={"Authorization": "Bearer rpl_caller"},
        json={"model": "claude-opus-4-8", "messages": [], "stream": True},
    )
    assert resp.status_code == 200
    row = sink[0]
    assert row.response_body["partial"] is True
    assert row.error == "stream incomplete"
