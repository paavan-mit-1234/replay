"""Gemini proxy path tests (OpenAI-compatible chat completions, mocked upstream)."""

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
GEMINI_SECRET = "AIza-test-gemini-key"

UPSTREAM = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
SAMPLE_RESPONSE = {
    "id": "chatcmpl-1",
    "model": "gemini-2.0-flash",
    "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}}],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


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


async def _fake_get_active_secret(session, provider):  # noqa: ANN001
    return GEMINI_SECRET


@pytest.fixture
def captured(monkeypatch):  # noqa: ANN001
    sink: list = []
    monkeypatch.setattr("replay.proxy.router.get_active_secret", _fake_get_active_secret)
    monkeypatch.setattr("replay.proxy.router.org_session", _fake_org_session_factory(sink))
    return sink


@pytest.fixture
def client(captured):  # noqa: ANN001
    app = create_app()
    app.dependency_overrides[get_proxy_context] = lambda: ProxyContext(
        org_id=ORG_ID, api_key_id=API_KEY_ID
    )
    return TestClient(app)


@respx.mock
def test_gemini_passthrough_and_key_swap(client, captured) -> None:  # noqa: ANN001
    route = respx.post(UPSTREAM).mock(return_value=httpx.Response(200, json=SAMPLE_RESPONSE))
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer rpl_caller_key"},
        json={"model": "gemini-2.0-flash", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert route.called
    assert resp.status_code == 200
    assert resp.json() == SAMPLE_RESPONSE
    sent = route.calls.last.request
    # The tenant Gemini secret is attached, the Replay key is never forwarded.
    assert sent.headers["authorization"] == f"Bearer {GEMINI_SECRET}"
    assert all("rpl_" not in v for v in sent.headers.values())


@respx.mock
def test_gemini_usage_and_cost_captured(client, captured) -> None:  # noqa: ANN001
    respx.post(UPSTREAM).mock(return_value=httpx.Response(200, json=SAMPLE_RESPONSE))
    client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer rpl_caller_key"},
        json={"model": "gemini-2.0-flash", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert len(captured) == 1
    row = captured[0]
    assert row.provider == "gemini"
    assert row.input_tokens == 10
    assert row.output_tokens == 5
    # 10 input at 0.10 and 5 output at 0.40 per Mtok.
    assert float(row.cost_usd) == round((10 * 0.10 + 5 * 0.40) / 1_000_000, 6)


def test_non_gemini_model_is_rejected_here(client) -> None:  # noqa: ANN001
    resp = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer rpl_caller_key"},
        json={"model": "gpt-4o", "messages": []},
    )
    assert resp.status_code == 400
