"""Row Level Security scope helpers.

Every tenant scoped query must run inside a session that has set the Postgres
session variable ``app.current_org``. The RLS policies compare each row's
``org_id`` to that setting, so a scoped session can only ever see its own org.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from replay.db.base import get_sessionmaker


async def set_org_scope(session: AsyncSession, org_id: uuid.UUID) -> None:
    """Set app.current_org on this session for the current transaction.

    Uses set_config with is_local=true so the scope is bound to the
    transaction and cannot leak across pooled connections.
    """
    await session.execute(
        text("select set_config('app.current_org', :org, true)"),
        {"org": str(org_id)},
    )


@asynccontextmanager
async def org_session(org_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Open a session already scoped to one org, inside a transaction."""
    async with get_sessionmaker()() as session, session.begin():
        await set_org_scope(session, org_id)
        yield session


@asynccontextmanager
async def auth_bootstrap_session() -> AsyncIterator[AsyncSession]:
    """Open a session that can read api_keys and memberships before the org
    scope is known. Only those two tables honor the bootstrap flag; every other
    tenant table stays isolated. Use this only to resolve identity, then switch
    to an org scoped session for real work.
    """
    async with get_sessionmaker()() as session, session.begin():
        await session.execute(text("select set_config('app.auth_bootstrap', 'on', true)"))
        yield session
