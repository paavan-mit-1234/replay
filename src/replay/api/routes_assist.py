"""Prompt Doctor and Autopsy: help anyone write better prompts. Both call the
org's Gemini key to rewrite or critique a prompt.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from replay import assist
from replay.auth.deps import ManagementContext, get_management_context
from replay.db.rls import org_session
from replay.vault.keys import get_active_secret

router = APIRouter()

IMPROVE_SYSTEM = (
    "You are an expert prompt engineer helping a non-technical person. Rewrite "
    "their prompt so an AI gives a clearly better, more useful answer. Keep their "
    "intent and language. Make it specific, add helpful context and constraints, "
    "and state the desired format when useful. Do not answer the prompt. Return "
    "ONLY the improved prompt text, with no preamble, labels, or quotation marks."
)

AUTOPSY_SYSTEM = (
    "You are a friendly prompt coach for a non-technical person. Given their "
    "prompt and the AI's response, give a short, encouraging critique. Respond in "
    "markdown with exactly two sections: a '**What could be better**' bullet list "
    "(2 to 3 short points) and an '**Improved prompt**' section containing a single "
    "rewritten prompt they can reuse. Be concise and practical."
)


class ImproveIn(BaseModel):
    prompt: str


class ImproveOut(BaseModel):
    improved: str


class AutopsyIn(BaseModel):
    prompt: str
    response: str


class AutopsyOut(BaseModel):
    markdown: str


async def _secret(org_id: object) -> str:
    async with org_session(org_id) as session:  # type: ignore[arg-type]
        secret = await get_active_secret(session, "gemini")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="add a gemini provider key in settings first",
        )
    return secret


@router.post("/improve", response_model=ImproveOut)
async def improve(
    body: ImproveIn,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
) -> ImproveOut:
    secret = await _secret(ctx.org_id)
    out = (await assist.complete(secret, IMPROVE_SYSTEM, body.prompt)).strip()
    return ImproveOut(improved=out or body.prompt)


@router.post("/autopsy", response_model=AutopsyOut)
async def autopsy(
    body: AutopsyIn,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
) -> AutopsyOut:
    secret = await _secret(ctx.org_id)
    user = f"PROMPT:\n{body.prompt}\n\nAI RESPONSE:\n{body.response[:4000]}"
    out = await assist.complete(secret, AUTOPSY_SYSTEM, user)
    return AutopsyOut(markdown=out or "Could not analyze this one. Try again.")
