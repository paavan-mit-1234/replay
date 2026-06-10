"""Allow the gemini provider on provider_keys.

Revision ID: 0002_gemini_provider
Revises: 0001_initial
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0002_gemini_provider"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("alter table provider_keys drop constraint ck_provider_key_provider")
    op.execute(
        "alter table provider_keys add constraint ck_provider_key_provider "
        "check (provider in ('anthropic','openai','gemini'))"
    )


def downgrade() -> None:
    op.execute("alter table provider_keys drop constraint ck_provider_key_provider")
    op.execute(
        "alter table provider_keys add constraint ck_provider_key_provider "
        "check (provider in ('anthropic','openai'))"
    )
