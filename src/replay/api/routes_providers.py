"""Provider key (BYOK) management. Secrets are encrypted and never returned."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from replay.api.schemas import ProviderKeyCreate, ProviderKeyOut
from replay.auth.deps import ManagementContext, get_management_context, management_session
from replay.db.models import ProviderKey
from replay.vault.keys import add_provider_key

router = APIRouter()

_SUPPORTED = {"anthropic", "openai", "gemini"}


@router.post("/provider-keys", response_model=ProviderKeyOut, status_code=status.HTTP_201_CREATED)
async def add_key(
    body: ProviderKeyCreate,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> ProviderKeyOut:
    if body.provider not in _SUPPORTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported provider; choose one of {sorted(_SUPPORTED)}",
        )
    row = await add_provider_key(session, ctx.org_id, body.provider, body.label, body.secret)
    return ProviderKeyOut(
        id=row.id,
        provider=row.provider,
        label=row.label,
        created_at=row.created_at,
        revoked_at=row.revoked_at,
    )


@router.get("/provider-keys", response_model=list[ProviderKeyOut])
async def list_keys(
    session: Annotated[AsyncSession, Depends(management_session)],
) -> list[ProviderKeyOut]:
    rows = (
        await session.execute(select(ProviderKey).order_by(ProviderKey.created_at.desc()))
    ).scalars()
    return [
        ProviderKeyOut(
            id=r.id,
            provider=r.provider,
            label=r.label,
            created_at=r.created_at,
            revoked_at=r.revoked_at,
        )
        for r in rows
    ]


@router.post("/provider-keys/{key_id}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_key(
    key_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(management_session)],
) -> None:
    row = await session.get(ProviderKey, key_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key not found")
    if row.revoked_at is None:
        row.revoked_at = dt.datetime.now(dt.UTC)
