"""Budget configuration, current spend, and alerts."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from replay import budget as budget_mod
from replay.auth.deps import ManagementContext, get_management_context, management_session
from replay.db.models import Alert, Budget

router = APIRouter()


class BudgetIn(BaseModel):
    monthly_limit_usd: float | None = Field(default=None, ge=0)
    alert_threshold_pct: int = Field(default=80, ge=1, le=100)
    block_over_limit: bool = False


class BudgetOut(BaseModel):
    monthly_limit_usd: float | None
    alert_threshold_pct: int
    block_over_limit: bool
    month_spend_usd: float
    usage_pct: float | None
    status: str  # unset, ok, warn, over


class AlertOut(BaseModel):
    id: uuid.UUID
    kind: str
    payload: dict[str, Any] | None
    created_at: dt.datetime
    acknowledged_at: dt.datetime | None


def _status(limit: float | None, spend: float, threshold: int) -> tuple[str, float | None]:
    if limit is None or limit <= 0:
        return "unset", None
    pct = spend / limit * 100
    if pct >= 100:
        state = "over"
    elif pct >= threshold:
        state = "warn"
    else:
        state = "ok"
    return state, round(pct, 1)


async def _budget_out(session: AsyncSession, budget: Budget | None) -> BudgetOut:
    """Build the response from the persisted budget so the limit reflects the
    stored (cents-rounded) value, keeping GET and PUT consistent.
    """
    spend = await budget_mod.month_spend(session)
    limit = (
        float(budget.monthly_limit_usd)
        if budget and budget.monthly_limit_usd is not None
        else None
    )
    threshold = budget.alert_threshold_pct if budget else 80
    state, pct = _status(limit, spend, threshold)
    return BudgetOut(
        monthly_limit_usd=limit,
        alert_threshold_pct=threshold,
        block_over_limit=budget.block_over_limit if budget else False,
        month_spend_usd=round(spend, 6),
        usage_pct=pct,
        status=state,
    )


@router.get("/budget", response_model=BudgetOut)
async def get_budget(
    session: Annotated[AsyncSession, Depends(management_session)],
) -> BudgetOut:
    return await _budget_out(session, await budget_mod.get_budget(session))


@router.put("/budget", response_model=BudgetOut)
async def put_budget(
    body: BudgetIn,
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> BudgetOut:
    budget = await budget_mod.get_budget(session)
    if budget is None:
        budget = Budget(
            org_id=ctx.org_id,
            monthly_limit_usd=body.monthly_limit_usd,
            alert_threshold_pct=body.alert_threshold_pct,
            block_over_limit=body.block_over_limit,
        )
        session.add(budget)
    else:
        budget.monthly_limit_usd = body.monthly_limit_usd
        budget.alert_threshold_pct = body.alert_threshold_pct
        budget.block_over_limit = body.block_over_limit
    await session.flush()
    await session.refresh(budget)
    return await _budget_out(session, budget)


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(
    session: Annotated[AsyncSession, Depends(management_session)],
) -> list[AlertOut]:
    rows = (
        await session.execute(select(Alert).order_by(Alert.created_at.desc()).limit(50))
    ).scalars()
    return [
        AlertOut(
            id=a.id,
            kind=a.kind,
            payload=a.payload,
            created_at=a.created_at,
            acknowledged_at=a.acknowledged_at,
        )
        for a in rows
    ]


@router.post("/alerts/{alert_id}/ack", status_code=status.HTTP_204_NO_CONTENT)
async def ack_alert(
    alert_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(management_session)],
) -> None:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="alert not found")
    if alert.acknowledged_at is None:
        alert.acknowledged_at = dt.datetime.now(dt.UTC)
