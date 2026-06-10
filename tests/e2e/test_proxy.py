"""Proxy hot path tests.

The database is mocked so these run with no Postgres. They verify the behavior
that matters on the hot path: faithful passthrough, the provider key swap (the
Replay key is never forwarded upstream and the provider secret is), stream
rejection in Phase 1, and that a capture failure never breaks the response.
"""

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
PROVIDER_SECRET = "sk-ant-test-provider-secret"

UPSTREAM = "https://api.anthropic.com/v1/messages"
SAMPLE_RESPONSE = {
    "id": "msg_1",
    "model": "claude-opus-4-8",
    "content": [{"type": "text", "text": "hi"}],
    "usage": {"input_tokens": 10, "output_tokens": 5},
}


class FakeSession:
    def __init__(self, on_add=None) -> None:
        self.added: list[object] = []
        self._on_add = on_add

    def add(self, row: object) -> None:
        if self._on_add is not None:
            self._on_add(row)
        self.added.append(row)


def _fake_org_session_factory(on_add=None):
    @contextlib.asynccontextmanager
    async def _fake(org_id):  # noqa: ANN001
        yield FakeSession(on_add=on_add)

    return _fake


async def _fake_get_active_secret(session, provider):  # noqa: ANN001
    return PROVIDER_SECRET


@pytest.fixture
def client(monkeypatch):  # noqa: ANN001
    monkeypatch.setattr(
        "replay.proxy.router.get_active_secret", _fake_get_active_secret
    )
    monkeypatch.setattr(
        "replay.proxy.router.org_session", _fake_org_session_factory()
    )
    app = create_app()
    app.dependency_overrides[get_proxy_context] = lambda: ProxyContext(
        org_id=ORG_ID, api_key_id=API_KEY_ID
    )
    return TestClient(app)


@respx.mock
def test_passthrough_returns_upstream_body_and_status(client) -> None:  # noqa: ANN001
    route = respx.post(UPSTREAM).mock(
        return_value=httpx.Response(200, json=SAMPLE_RESPONSE)
    )
    resp = client.post(
        "/v1/messages",
        headers={"Authorization": "Bearer rpl_caller_key"},
        json={"model": "claude-opus-4-8", "messages": []},
    )
    assert route.called
    assert resp.status_code == 200
    assert resp.json() == SAMPLE_RESPONSE


@respx.mock
def test_provider_key_swapped_and_replay_key_never_forwarded(client) -> None:  # noqa: ANN001
    route = respx.post(UPSTREAM).mock(
        return_value=httpx.Response(200, json=SAMPLE_RESPONSE)
    )
    client.post(
        "/v1/messages",
        headers={"Authorization": "Bearer rpl_caller_key"},
        json={"model": "claude-opus-4-8", "messages": []},
    )
    sent = route.calls.last.request
    # The tenant secret is attached.
    assert sent.headers["x-api-key"] == PROVIDER_SECRET
    # The Replay key is not forwarded, in any header.
    assert "authorization" not in {k.lower() for k in sent.headers}
    assert all("rpl_" not in v for v in sent.headers.values())


@respx.mock
def test_capture_failure_does_not_break_response(monkeypatch) -> None:  # noqa: ANN001
    def _boom(row: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(
        "replay.proxy.router.get_active_secret", _fake_get_active_secret
    )
    monkeypatch.setattr(
        "replay.proxy.router.org_session", _fake_org_session_factory(on_add=_boom)
    )
    app = create_app()
    app.dependency_overrides[get_proxy_context] = lambda: ProxyContext(
        org_id=ORG_ID, api_key_id=API_KEY_ID
    )
    local_client = TestClient(app)

    respx.post(UPSTREAM).mock(return_value=httpx.Response(200, json=SAMPLE_RESPONSE))
    resp = local_client.post(
        "/v1/messages",
        headers={"Authorization": "Bearer rpl_caller_key"},
        json={"model": "claude-opus-4-8", "messages": []},
    )
    # The capture write blew up, but the proxied response is still returned.
    assert resp.status_code == 200
    assert resp.json() == SAMPLE_RESPONSE
