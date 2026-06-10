"""Health and readiness."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from replay.db.base import get_sessionmaker

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, object]:
    """Liveness plus database connectivity and migration version."""
    db_ok = True
    migration: str | None = None
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("select 1"))
            result = await session.execute(text("select version_num from alembic_version"))
            row = result.first()
            migration = row[0] if row else None
    except Exception:  # noqa: BLE001
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "migration": migration}
