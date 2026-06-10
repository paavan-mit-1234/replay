"""Provider key store. Stores BYOK secrets encrypted, decrypts at request time.

Plaintext provider keys exist only in memory for the duration of a single
upstream call and are never written to the database or logs.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from replay.db.models import ProviderKey
from replay.vault import crypto


async def add_provider_key(
    session: AsyncSession,
    org_id: uuid.UUID,
    provider: str,
    label: str,
    secret: str,
) -> ProviderKey:
    """Encrypt and store a provider secret. Returns the row (without plaintext)."""
    row = ProviderKey(
        org_id=org_id,
        provider=provider,
        label=label,
        ciphertext=crypto.encrypt(secret),
    )
    session.add(row)
    await session.flush()
    return row


async def get_active_secret(
    session: AsyncSession,
    provider: str,
) -> str | None:
    """Return the decrypted secret for the most recent active key of a provider.

    The session must already be org scoped, so RLS guarantees only this org's
    keys are visible. Returns None when no active key exists.
    """
    stmt = (
        select(ProviderKey)
        .where(ProviderKey.provider == provider)
        .where(ProviderKey.revoked_at.is_(None))
        .order_by(ProviderKey.created_at.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return None
    return crypto.decrypt(row.ciphertext)
