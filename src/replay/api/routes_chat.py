"""The consumer chat workspace: multi-turn conversations that stream through the
proxy (BYOK, captured to the dashboard like any other traffic), plus the
learning loop (embeddings for recurring-prompt detection, and message feedback).
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask

from replay import assist
from replay.auth.deps import ManagementContext, get_management_context, management_session
from replay.db.models import Conversation, Message
from replay.db.rls import org_session
from replay.proxy import passthrough
from replay.proxy.providers.gemini import gemini_provider
from replay.proxy.router import STREAM_TEXT_CAP, _safe_capture
from replay.proxy.streaming import SSEParser, make_state
from replay.vault.keys import get_active_secret

router = APIRouter()


# --- schemas -----------------------------------------------------------------


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    updated_at: dt.datetime


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    feedback: int | None
    created_at: dt.datetime


class ConversationDetail(BaseModel):
    id: uuid.UUID
    title: str
    messages: list[MessageOut]


class SendIn(BaseModel):
    content: str
    conversation_id: uuid.UUID | None = None
    model: str = "gemini-2.5-flash"


class RenameIn(BaseModel):
    title: str


class FeedbackIn(BaseModel):
    rating: int  # 1, -1, or 0 to clear


class SimilarIn(BaseModel):
    content: str


class SimilarItem(BaseModel):
    content: str
    conversation_id: uuid.UUID
    title: str


# --- conversation CRUD -------------------------------------------------------


@router.get("/chat/conversations", response_model=list[ConversationOut])
async def list_conversations(
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> list[ConversationOut]:
    rows = (
        await session.execute(
            select(Conversation)
            .where(Conversation.user_id == ctx.user_id)
            .order_by(Conversation.updated_at.desc())
            .limit(100)
        )
    ).scalars()
    return [ConversationOut(id=c.id, title=c.title, updated_at=c.updated_at) for c in rows]


@router.get("/chat/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> ConversationDetail:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    rows = (
        await session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
    ).scalars()
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                feedback=m.feedback,
                created_at=m.created_at,
            )
            for m in rows
        ],
    )


@router.delete("/chat/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> None:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    await session.execute(delete(Conversation).where(Conversation.id == conversation_id))


@router.post("/chat/conversations/{conversation_id}/rename", status_code=status.HTTP_204_NO_CONTENT)
async def rename_conversation(
    conversation_id: uuid.UUID,
    body: RenameIn,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> None:
    conv = await session.get(Conversation, conversation_id)
    if conv is None or conv.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found")
    conv.title = body.title[:80] or "new chat"


@router.post("/chat/messages/{message_id}/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def message_feedback(
    message_id: uuid.UUID,
    body: FeedbackIn,
    session: Annotated[AsyncSession, Depends(management_session)],
) -> None:
    rating = max(-1, min(1, body.rating)) or None
    await session.execute(update(Message).where(Message.id == message_id).values(feedback=rating))


# --- learning loop: similar past prompts -------------------------------------


@router.post("/chat/similar", response_model=list[SimilarItem])
async def similar(
    body: SimilarIn,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
) -> list[SimilarItem]:
    """Find the user's most similar past prompts (recurring-intent detection)."""
    async with org_session(ctx.org_id) as session:
        secret = await get_active_secret(session, "gemini")
    if not secret:
        return []
    vec = await assist.embed(secret, body.content)
    if not vec:
        return []
    lit = assist.vector_literal(vec)
    query = text(
        """
        select m.content, c.id as conversation_id, c.title
        from messages m join conversations c on c.id = m.conversation_id
        where c.user_id = :uid and m.role = 'user' and m.embedding is not null
        order by m.embedding <=> cast(:v as vector)
        limit 3
        """
    )
    async with org_session(ctx.org_id) as session:
        rows = (
            await session.execute(query, {"uid": str(ctx.user_id), "v": lit})
        ).all()
    return [
        SimilarItem(content=r.content, conversation_id=r.conversation_id, title=r.title)
        for r in rows
    ]


# --- the streaming send ------------------------------------------------------


@router.post("/chat/send")
async def chat_send(
    body: SendIn,
    request: Request,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
) -> Response:
    org_id, user_id = ctx.org_id, ctx.user_id

    # Resolve or create the conversation, capture history, store the user turn.
    async with org_session(org_id) as session:
        if body.conversation_id is not None:
            conv = await session.get(Conversation, body.conversation_id)
            if conv is None or conv.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found"
                )
            conv_id = conv.id
        else:
            conv = Conversation(
                org_id=org_id, user_id=user_id, title=(body.content[:60] or "new chat")
            )
            session.add(conv)
            await session.flush()
            conv_id = conv.id
        history = (
            await session.execute(
                select(Message.role, Message.content)
                .where(Message.conversation_id == conv_id)
                .order_by(Message.created_at)
            )
        ).all()
        user_msg = Message(
            org_id=org_id, conversation_id=conv_id, role="user", content=body.content
        )
        session.add(user_msg)
        await session.flush()
        user_msg_id = user_msg.id

    async with org_session(org_id) as session:
        secret = await get_active_secret(session, "gemini")
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="add a gemini provider key in settings first",
        )

    messages: list[dict[str, str]] = [{"role": r, "content": c} for r, c in history]
    messages.append({"role": "user", "content": body.content})
    chat_body: dict[str, Any] = {
        "model": body.model,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    raw = json.dumps(chat_body).encode()

    client, upstream_req = passthrough.build_stream(
        gemini_provider, secret, "/chat/completions", raw, dict(request.headers)
    )
    started = time.monotonic()
    upstream = await client.send(upstream_req, stream=True)
    status_code = upstream.status_code

    if status_code >= 400:
        err = await upstream.aread()
        media = upstream.headers.get("content-type", "application/json")
        await upstream.aclose()
        await client.aclose()
        return Response(content=err, status_code=status_code, media_type=media)

    state = make_state("gemini")
    parser = SSEParser()

    async def gen() -> Any:
        try:
            async for chunk in upstream.aiter_bytes():
                for data in parser.feed(chunk):
                    with contextlib.suppress(Exception):
                        state.consume(data)
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    async def on_close() -> None:
        latency_ms = int((time.monotonic() - started) * 1000)
        await _safe_capture(
            org_id=org_id,
            api_key_id=None,
            provider="gemini",
            model=state.model or chat_body["model"],
            endpoint="chat.completions",
            request_body=chat_body,
            response_body={
                "streamed": True,
                "partial": not state.done,
                "text": state.text[:STREAM_TEXT_CAP],
            },
            status_code=status_code,
            error=None if state.done else "stream incomplete",
            usage=state.usage,
            latency_ms=latency_ms,
            streamed=True,
        )
        async with org_session(org_id) as session:
            session.add(
                Message(
                    org_id=org_id, conversation_id=conv_id, role="assistant", content=state.text
                )
            )
            await session.execute(
                update(Conversation)
                .where(Conversation.id == conv_id)
                .values(updated_at=dt.datetime.now(dt.UTC))
            )
        # Embed the user turn for recurring-prompt detection (best effort).
        vec = await assist.embed(secret, body.content)
        if vec:
            async with org_session(org_id) as session:
                await session.execute(
                    text("update messages set embedding = cast(:v as vector) where id = :id"),
                    {"v": assist.vector_literal(vec), "id": str(user_msg_id)},
                )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"X-Conversation-Id": str(conv_id)},
        background=BackgroundTask(on_close),
    )
