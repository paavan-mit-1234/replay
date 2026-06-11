"""Prompt library: saved_prompts.

Revision ID: 0004_saved_prompts
Revises: 0003_chat
Create Date: 2026-06-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_saved_prompts"
down_revision: str | None = "0003_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORG = "org_id = nullif(current_setting('app.current_org', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        """
        create table saved_prompts (
          id uuid default gen_random_uuid() not null,
          org_id uuid not null,
          user_id uuid not null,
          content text not null,
          created_at timestamptz default now() not null,
          primary key (id)
        )
        """
    )
    op.execute("create index ix_saved_prompts_user on saved_prompts (org_id, user_id, created_at)")
    op.execute("alter table saved_prompts enable row level security")
    op.execute("alter table saved_prompts force row level security")
    op.execute(f"create policy org_isolation on saved_prompts using ({_ORG}) with check ({_ORG})")
    op.execute("grant select, insert, update, delete on saved_prompts to replay_app")


def downgrade() -> None:
    op.execute("drop table if exists saved_prompts")
