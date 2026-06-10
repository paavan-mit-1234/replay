"""Replay API key management."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from replay.api.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut
from replay.auth import apikeys
from replay.auth.deps import ManagementContext, get_management_context, management_session
from replay.db.models import ApiKey

router = APIRouter()


@router.post("/keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreate,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> ApiKeyCreated:
    generated = apikeys.generate_key()
    row = ApiKey(
        org_id=ctx.org_id,
        name=body.name,
        prefix=generated.prefix,
        hash=generated.hash,
    )
    session.add(row)
    await session.flush()
    return ApiKeyCreated(
        id=row.id,
        name=row.name,
        prefix=row.prefix,
        created_at=row.created_at,
        last_used_at=None,
        revoked_at=None,
        key=generated.plaintext,
    )


@router.get("/keys", response_model=list[ApiKeyOut])
async def list_keys(
    session: Annotated[AsyncSession, Depends(management_session)],
) -> list[ApiKeyOut]:
    rows = (await session.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))).scalars()
    return [
        ApiKeyOut(
            id=r.id,
            name=r.name,
            prefix=r.prefix,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            revoked_at=r.revoked_at,
        )
        for r in rows
    ]


@router.post("/keys/{key_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    key_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(management_session)],
) -> None:
    row = await session.get(ApiKey, key_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key not found")
    if row.revoked_at is None:
        row.revoked_at = dt.datetime.now(dt.UTC)
