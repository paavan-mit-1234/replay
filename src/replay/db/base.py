"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

import ssl
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from replay.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """Declarative base for all models."""


def supabase_connect_args(database_url: str) -> dict[str, object]:
    """Connect args for Supabase (and any pgbouncer style pooler).

    asyncpg's prepared statement cache must be disabled behind the pooler, and
    TLS is required. The pooler presents a certificate signed by Supabase's own
    CA, so we encrypt without strict chain verification (equivalent to libpq
    sslmode=require). Production deployments that want full verification should
    pin Supabase's CA bundle here. Local Postgres (no "supabase" in the URL) is
    unaffected.
    """
    if "supabase" not in database_url:
        return {}
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return {"ssl": ctx, "statement_cache_size": 0}


def get_engine() -> AsyncEngine:
    """Lazily create the process wide async engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            future=True,
            connect_args=supabase_connect_args(settings.database_url),
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Lazily create the session factory."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield a session without an org scope. Use only for non tenant operations."""
    async with get_sessionmaker()() as session:
        yield session
