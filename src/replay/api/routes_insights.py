"""Insights: a personal prompt fingerprint built from the user's chat history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from replay import assist
from replay.auth.deps import ManagementContext, get_management_context, management_session
from replay.db.rls import org_session
from replay.vault.keys import get_active_secret

router = APIRouter()

FINGERPRINT_SYSTEM = (
    "You are a friendly prompt coach for a non-technical person. You are given a "
    "numbered list of prompts they have asked an AI, newest first. Write their "
    "personal 'prompt fingerprint' in markdown with exactly four sections: "
    "'**Your style**' (2 to 3 warm sentences about how they tend to ask), "
    "'**What you ask about**' (a short bullet list of their main topics), "
    "'**Habits to upgrade**' (2 to 3 bullets, each naming one habit and one "
    "concrete fix), and '**Your cheat sheet**' (3 reusable prompt templates "
    "tailored to their topics, each on its own line in a code block, with "
    "[BRACKETS] for the parts to fill in). Be specific to their actual prompts, "
    "encouraging, and concise."
)

FINGERPRINT_MIN_PROMPTS = 3
FINGERPRINT_SAMPLE = 40


class InsightStats(BaseModel):
    prompts_sent: int
    conversations: int
    good_feedback: int
    bad_feedback: int
    days_active: int


class FingerprintOut(BaseModel):
    markdown: str
    sampled: int


@router.get("/insights/stats", response_model=InsightStats)
async def insight_stats(
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> InsightStats:
    row = (
        await session.execute(
            text(
                """
                select
                  count(*) filter (where m.role = 'user') as prompts_sent,
                  count(distinct c.id) as conversations,
                  count(*) filter (where m.feedback = 1) as good_feedback,
                  count(*) filter (where m.feedback = -1) as bad_feedback,
                  count(distinct date(m.created_at)) as days_active
                from conversations c
                left join messages m on m.conversation_id = c.id
                where c.user_id = :uid
                """
            ),
            {"uid": str(ctx.user_id)},
        )
    ).one()
    return InsightStats(
        prompts_sent=row.prompts_sent,
        conversations=row.conversations,
        good_feedback=row.good_feedback,
        bad_feedback=row.bad_feedback,
        days_active=row.days_active,
    )


@router.post("/insights/fingerprint", response_model=FingerprintOut)
async def fingerprint(
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
) -> FingerprintOut:
    async with org_session(ctx.org_id) as session:
        rows = (
            await session.execute(
                text(
                    """
                    select m.content
                    from messages m join conversations c on c.id = m.conversation_id
                    where c.user_id = :uid and m.role = 'user'
                    order by m.created_at desc
                    limit :n
                    """
                ),
                {"uid": str(ctx.user_id), "n": FINGERPRINT_SAMPLE},
            )
        ).scalars().all()
    if len(rows) < FINGERPRINT_MIN_PROMPTS:
        return FingerprintOut(
            markdown=(
                "**Not enough signal yet.** Ask a few more questions in chat, "
                "then come back: your fingerprint gets sharper with every prompt."
            ),
            sampled=len(rows),
        )
    async with org_session(ctx.org_id) as session:
        secret = await get_active_secret(session, "gemini")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="add a gemini provider key in settings first",
        )
    listing = "\n".join(f"{i + 1}. {content[:300]}" for i, content in enumerate(rows))
    out = await assist.complete(secret, FINGERPRINT_SYSTEM, listing)
    return FingerprintOut(
        markdown=out or "Could not read your fingerprint this time. Try again.",
        sampled=len(rows),
    )
