"""FastAPI dependencies that resolve the org scope for each request.

Two surfaces:
- Management (dashboard, CLI): a Supabase JWT identifies the user; the org is
  resolved from memberships, optionally narrowed by the X-Replay-Org header.
- Proxy: a Replay API key identifies the org directly.

Both yield an org scoped AsyncSession, so route code never sets the scope by
hand and no query can forget it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from replay.auth import apikeys
from replay.auth.jwt import AuthError, verify_token
from replay.db.models import ApiKey, Membership
from replay.db.rls import auth_bootstrap_session, org_session


@dataclass(frozen=True)
class ManagementContext:
    user_id: uuid.UUID
    email: str
    org_id: uuid.UUID


@dataclass(frozen=True)
class VerifiedUser:
    user_id: uuid.UUID
    email: str


@dataclass(frozen=True)
class ProxyContext:
    org_id: uuid.UUID
    # None for in-app playground calls, which authenticate by JWT rather than a
    # Replay API key.
    api_key_id: uuid.UUID | None


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
        )
    return authorization[7:].strip()


async def get_verified_user(
    authorization: Annotated[str | None, Header()] = None,
) -> VerifiedUser:
    """Verify the JWT only. Used by org bootstrap, before any membership exists."""
    token = _bearer(authorization)
    try:
        claims = verify_token(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    return VerifiedUser(user_id=uuid.UUID(claims.user_id), email=claims.email)


async def get_management_context(
    authorization: Annotated[str | None, Header()] = None,
    x_replay_org: Annotated[str | None, Header()] = None,
) -> ManagementContext:
    """Verify the JWT and resolve the active org from the user's memberships."""
    token = _bearer(authorization)
    try:
        claims = verify_token(token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc

    user_id = uuid.UUID(claims.user_id)
    async with auth_bootstrap_session() as session:
        stmt = select(Membership.org_id).where(Membership.user_id == user_id)
        if x_replay_org:
            stmt = stmt.where(Membership.org_id == uuid.UUID(x_replay_org))
        org_ids = (await session.execute(stmt)).scalars().all()

    if not org_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user has no org membership",
        )
    if x_replay_org is None and len(org_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="multiple orgs; set the X-Replay-Org header",
        )
    return ManagementContext(user_id=user_id, email=claims.email, org_id=org_ids[0])


async def management_session(
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
) -> AsyncIterator[AsyncSession]:
    """Yield an org scoped session for management routes."""
    async with org_session(ctx.org_id) as session:
        yield session


async def get_proxy_context(
    authorization: Annotated[str | None, Header()] = None,
) -> ProxyContext:
    """Resolve the org and api key id from a presented Replay API key."""
    token = _bearer(authorization)
    key_hash = apikeys.hash_key(token)
    # Resolve the key in the bootstrap session (org scope is not known yet).
    async with auth_bootstrap_session() as session:
        stmt = select(ApiKey).where(
            ApiKey.hash == key_hash, ApiKey.revoked_at.is_(None)
        )
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid api key",
            )
        org_id = row.org_id
        api_key_id = row.id
    # Record usage in an org scoped session, so the RLS WITH CHECK clause is
    # satisfied (the bootstrap session has no org scope and would be rejected).
    async with org_session(org_id) as session:
        await session.execute(
            update(ApiKey).where(ApiKey.id == api_key_id).values(last_used_at=_utcnow())
        )
    return ProxyContext(org_id=org_id, api_key_id=api_key_id)


def _utcnow() -> object:
    # Imported lazily to keep this module import light and avoid a circular hint.
    import datetime as dt

    return dt.datetime.now(dt.UTC)
