"""Row Level Security isolation, proven against a real Postgres.

This test only means something when the connecting role is subject to RLS, so
it skips when the role is a superuser or has BYPASSRLS (for example the default
Supabase postgres role). Point REPLAY_DATABASE_URL at the database using the
replay_app role to run it for real. CI runs it against a dedicated role.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text

from replay.db.base import get_sessionmaker
from replay.db.models import ApiKey, Request
from replay.db.rls import org_session

pytestmark = pytest.mark.asyncio


async def _role_is_rls_subject() -> bool:
    async with get_sessionmaker()() as session:
        row = (
            await session.execute(
                text(
                    "select rolsuper or rolbypassrls from pg_roles "
                    "where rolname = current_user"
                )
            )
        ).scalar()
    return not bool(row)


@pytest.fixture(scope="module", autouse=True)
async def _require_rls_db():
    try:
        if not await _role_is_rls_subject():
            pytest.skip("connecting role bypasses RLS; run as replay_app to test isolation")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no RLS-capable Postgres reachable: {exc}")


def _make_request(org_id: uuid.UUID) -> Request:
    return Request(
        org_id=org_id,
        provider="anthropic",
        model="claude-opus-4-8",
        endpoint="messages",
        request_body={"probe": str(org_id)},
    )


async def test_org_cannot_read_another_orgs_rows() -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    async with org_session(org_a) as session:
        session.add(_make_request(org_a))
    async with org_session(org_b) as session:
        session.add(_make_request(org_b))

    # Org B sees only its own rows, never org A's.
    async with org_session(org_b) as session:
        rows = (await session.execute(select(Request))).scalars().all()
    assert rows, "org B should see its own row"
    assert all(r.org_id == org_b for r in rows)

    # cleanup
    async with org_session(org_a) as session:
        await session.execute(text("delete from requests where org_id = :o"), {"o": str(org_a)})
    async with org_session(org_b) as session:
        await session.execute(text("delete from requests where org_id = :o"), {"o": str(org_b)})


async def test_cross_org_write_is_rejected() -> None:
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(Exception):  # noqa: B017 (RLS raises a database error)
        async with org_session(org_a) as session:
            # Scoped to org A, try to write a row tagged org B.
            session.add(_make_request(org_b))
            await session.flush()


async def test_proxy_auth_resolves_org_and_records_usage() -> None:
    """Regression: the proxy auth path must update api_keys.last_used_at without
    tripping RLS. The usage write has to happen in an org scoped session, not the
    bootstrap session (which has no org scope and fails the WITH CHECK clause).
    """
    from sqlalchemy import select, text

    from replay.auth import apikeys
    from replay.auth.deps import get_proxy_context

    org = uuid.uuid4()
    gen = apikeys.generate_key()
    async with org_session(org) as session:
        session.add(ApiKey(org_id=org, name="t", prefix=gen.prefix, hash=gen.hash))

    ctx = await get_proxy_context(authorization=f"Bearer {gen.plaintext}")
    assert ctx.org_id == org

    async with org_session(org) as session:
        row = (
            await session.execute(select(ApiKey).where(ApiKey.id == ctx.api_key_id))
        ).scalar_one()
        assert row.last_used_at is not None

    async with org_session(org) as session:
        await session.execute(text("delete from api_keys where org_id = :o"), {"o": str(org)})
