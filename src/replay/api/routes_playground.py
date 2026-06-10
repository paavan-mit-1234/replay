"""In-app playground: run a test call from the dashboard, no Replay API key
needed. Authenticated by the user's Supabase JWT; the call uses the org's
stored provider key and flows through the normal proxy and capture path.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from replay.auth.deps import ManagementContext, ProxyContext, get_management_context
from replay.proxy.router import proxy_chat_for_org

router = APIRouter()


class PlaygroundIn(BaseModel):
    prompt: str
    model: str = "gemini-2.5-flash"
    stream: bool = True


@router.post("/playground/chat")
async def playground_chat(
    body: PlaygroundIn,
    request: Request,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
) -> Response:
    proxy_ctx = ProxyContext(org_id=ctx.org_id, api_key_id=None)
    return await proxy_chat_for_org(
        request=request,
        ctx=proxy_ctx,
        model=body.model,
        prompt=body.prompt,
        stream=body.stream,
    )
