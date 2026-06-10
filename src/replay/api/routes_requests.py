"""Request log listing, detail, and cost summary."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from replay.api.schemas import CostBucket, RequestDetail, RequestOut, StatsOut
from replay.auth.deps import management_session
from replay.db.models import Request

router = APIRouter()


@router.get("/stats", response_model=StatsOut)
async def stats(
    session: Annotated[AsyncSession, Depends(management_session)],
    since: dt.datetime | None = None,
) -> StatsOut:
    """Headline gauges: spend, request count, error rate, median latency."""
    error_pred = (Request.status_code >= 400) | (Request.error.isnot(None))
    stmt = select(
        func.coalesce(func.sum(Request.cost_usd), 0).label("spend"),
        func.count().label("n"),
        func.count().filter(error_pred).label("errors"),
        func.percentile_cont(0.5).within_group(Request.latency_ms).label("median_ms"),
    )
    if since:
        stmt = stmt.where(Request.created_at >= since)
    row = (await session.execute(stmt)).one()
    n = int(row.n)
    errors = int(row.errors)
    median = int(row.median_ms) if row.median_ms is not None else None
    return StatsOut(
        spend_usd=float(row.spend),
        request_count=n,
        error_count=errors,
        error_rate=(errors / n) if n else 0.0,
        median_latency_ms=median,
    )


@router.get("/requests", response_model=list[RequestOut])
async def list_requests(
    session: Annotated[AsyncSession, Depends(management_session)],
    model: str | None = None,
    since: dt.datetime | None = None,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[RequestOut]:
    stmt = select(Request).order_by(Request.created_at.desc()).limit(limit)
    if model:
        stmt = stmt.where(Request.model == model)
    if since:
        stmt = stmt.where(Request.created_at >= since)
    rows = (await session.execute(stmt)).scalars()
    return [
        RequestOut(
            id=r.id,
            provider=r.provider,
            model=r.model,
            endpoint=r.endpoint,
            status_code=r.status_code,
            error=r.error,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            cost_usd=float(r.cost_usd) if r.cost_usd is not None else None,
            latency_ms=r.latency_ms,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/requests/{request_id}", response_model=RequestDetail)
async def get_request(
    request_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(management_session)],
) -> RequestDetail:
    r = await session.get(Request, request_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="request not found")
    return RequestDetail(
        id=r.id,
        provider=r.provider,
        model=r.model,
        endpoint=r.endpoint,
        status_code=r.status_code,
        error=r.error,
        input_tokens=r.input_tokens,
        output_tokens=r.output_tokens,
        cost_usd=float(r.cost_usd) if r.cost_usd is not None else None,
        latency_ms=r.latency_ms,
        created_at=r.created_at,
        request_body=r.request_body,
        response_body=r.response_body,
        cache_read_tokens=r.cache_read_tokens,
        cache_write_tokens=r.cache_write_tokens,
    )


@router.get("/cost/summary", response_model=list[CostBucket])
async def cost_summary(
    session: Annotated[AsyncSession, Depends(management_session)],
    group_by: str = Query(default="model", pattern="^(model|day)$"),
    since: dt.datetime | None = None,
) -> list[CostBucket]:
    key = Request.model if group_by == "model" else func.date(Request.created_at)
    stmt = select(
        key.label("key"),
        func.count().label("requests"),
        func.coalesce(func.sum(Request.cost_usd), 0).label("cost"),
    ).group_by(key)
    if since:
        stmt = stmt.where(Request.created_at >= since)
    rows = (await session.execute(stmt)).all()
    return [
        CostBucket(key=str(r.key), requests=int(r.requests), cost_usd=float(r.cost))
        for r in rows
    ]
