"""Org bootstrap and listing."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from replay.api.schemas import MeOut, OrgCreate, OrgMembership, OrgOut
from replay.auth.deps import (
    ManagementContext,
    VerifiedUser,
    get_management_context,
    get_verified_user,
    management_session,
)
from replay.db.base import get_sessionmaker
from replay.db.models import Membership, Org, User
from replay.db.rls import auth_bootstrap_session, org_session

router = APIRouter()


@router.get("/me", response_model=MeOut)
async def me(user: Annotated[VerifiedUser, Depends(get_verified_user)]) -> MeOut:
    """The verified user and the orgs they belong to. Drives onboarding: an
    empty orgs list means the user needs to create one.
    """
    async with auth_bootstrap_session() as session:
        stmt = (
            select(Membership.role, Org.id, Org.name, Org.slug)
            .join(Org, Org.id == Membership.org_id)
            .where(Membership.user_id == user.user_id)
            .order_by(Org.created_at)
        )
        rows = (await session.execute(stmt)).all()
    return MeOut(
        user_id=user.user_id,
        email=user.email,
        orgs=[OrgMembership(id=r.id, name=r.name, slug=r.slug, role=r.role) for r in rows],
    )


@router.post("/orgs", response_model=OrgOut, status_code=status.HTTP_201_CREATED)
async def create_org(
    body: OrgCreate,
    user: Annotated[VerifiedUser, Depends(get_verified_user)],
) -> OrgOut:
    """Create an org and make the calling user its owner.

    This is the one management route that does not require an existing
    membership, since it is how the first membership comes to exist.
    """
    # orgs and users carry no org_id and are not RLS protected, so they can be
    # written without a scope. The membership insert needs the new org scope to
    # satisfy the WITH CHECK clause.
    async with get_sessionmaker()() as session, session.begin():
        existing = (
            await session.execute(select(Org).where(Org.slug == body.slug))
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="slug already exists"
            )
        org = Org(name=body.name, slug=body.slug)
        session.add(org)
        # Upsert the user row.
        db_user = await session.get(User, user.user_id)
        if db_user is None:
            session.add(User(id=user.user_id, email=user.email))
        await session.flush()
        org_id = org.id

    async with org_session(org_id) as session:
        session.add(Membership(org_id=org_id, user_id=user.user_id, role="owner"))

    return OrgOut(id=org_id, name=body.name, slug=body.slug)


@router.get("/orgs/current", response_model=OrgOut)
async def current_org(
    ctx: Annotated[ManagementContext, Depends(get_management_context)],
    session: Annotated[AsyncSession, Depends(management_session)],
) -> OrgOut:
    org = await session.get(Org, ctx.org_id)
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="org not found")
    return OrgOut(id=org.id, name=org.name, slug=org.slug)
