"""Monthly spend budgets, threshold alerts, and optional hard blocking.

A budget is per org: an optional monthly dollar limit, an alert threshold
percent, and a flag to reject proxied calls once the limit is hit. Spend is the
sum of requests.cost_usd since the start of the current UTC month. Alerts are
written at most once per month per kind, so crossing a threshold does not spam.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from replay.db.models import Alert, Budget, Request
from replay.db.rls import org_session

ALERT_THRESHOLD = "budget_threshold"
ALERT_EXCEEDED = "budget_exceeded"


def month_start(now: dt.datetime | None = None) -> dt.datetime:
    now = now or dt.datetime.now(dt.UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def month_spend(session: AsyncSession, since: dt.datetime | None = None) -> float:
    """Org spend (RLS scoped) since the start of the current month."""
    start = since or month_start()
    total = (
        await session.execute(
            select(func.coalesce(func.sum(Request.cost_usd), 0)).where(
                Request.created_at >= start
            )
        )
    ).scalar()
    return float(total or 0)


async def get_budget(session: AsyncSession) -> Budget | None:
    return (await session.execute(select(Budget))).scalar_one_or_none()


async def _alert_exists(session: AsyncSession, kind: str, since: dt.datetime) -> bool:
    found = (
        await session.execute(
            select(Alert.id).where(Alert.kind == kind, Alert.created_at >= since).limit(1)
        )
    ).first()
    return found is not None


async def evaluate_and_alert(org_id: uuid.UUID) -> None:
    """Recompute month spend and record a threshold or exceeded alert if a line
    was just crossed. Best effort: callers wrap this in suppress.
    """
    start = month_start()
    async with org_session(org_id) as session:
        budget = await get_budget(session)
        if budget is None or budget.monthly_limit_usd is None:
            return
        limit = float(budget.monthly_limit_usd)
        if limit <= 0:
            return
        spend = await month_spend(session, start)
        pct = spend / limit * 100
        payload = {
            "spend_usd": round(spend, 6),
            "limit_usd": limit,
            "usage_pct": round(pct, 1),
            "month": start.date().isoformat(),
        }
        if pct >= 100 and not await _alert_exists(session, ALERT_EXCEEDED, start):
            session.add(Alert(org_id=org_id, kind=ALERT_EXCEEDED, payload=payload))
        elif (
            pct >= budget.alert_threshold_pct
            and not await _alert_exists(session, ALERT_THRESHOLD, start)
            and not await _alert_exists(session, ALERT_EXCEEDED, start)
        ):
            session.add(Alert(org_id=org_id, kind=ALERT_THRESHOLD, payload=payload))


async def enforce(org_id: uuid.UUID) -> None:
    """Reject a proxied call when the org blocks over its limit and is over it."""
    async with org_session(org_id) as session:
        budget = await get_budget(session)
        if budget is None or not budget.block_over_limit or budget.monthly_limit_usd is None:
            return
        limit = float(budget.monthly_limit_usd)
        if limit <= 0:
            return
        spend = await month_spend(session)
    if spend >= limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=(
                f"monthly budget of ${limit:.2f} reached "
                f"(${spend:.2f} spent). Raise or remove the limit in settings."
            ),
        )
