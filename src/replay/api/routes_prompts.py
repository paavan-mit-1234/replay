"""Prompt library: save and reuse prompts."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from replay.auth.deps import ManagementContext, get_management_context, management_session
from replay.db.models import SavedPrompt

router = APIRouter()


class SavedPromptIn(BaseModel):
    content: str


class SavedPromptOut(BaseModel):
    id: uuid.UUID
    content: str
    created_at: dt.datetime


@router.get("/prompts", response_model=list[SavedPromptOut])
async def list_prompts(
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> list[SavedPromptOut]:
    rows = (
        await session.execute(
            select(SavedPrompt)
            .where(SavedPrompt.user_id == ctx.user_id)
            .order_by(SavedPrompt.created_at.desc())
            .limit(100)
        )
    ).scalars()
    return [SavedPromptOut(id=p.id, content=p.content, created_at=p.created_at) for p in rows]


@router.post("/prompts", response_model=SavedPromptOut, status_code=status.HTTP_201_CREATED)
async def save_prompt(
    body: SavedPromptIn,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> SavedPromptOut:
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="empty prompt")
    row = SavedPrompt(org_id=ctx.org_id, user_id=ctx.user_id, content=content[:4000])
    session.add(row)
    await session.flush()
    return SavedPromptOut(id=row.id, content=row.content, created_at=row.created_at)


@router.delete("/prompts/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_prompt(
    prompt_id: uuid.UUID,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> None:
    await session.execute(
        delete(SavedPrompt).where(
            SavedPrompt.id == prompt_id, SavedPrompt.user_id == ctx.user_id
        )
    )
