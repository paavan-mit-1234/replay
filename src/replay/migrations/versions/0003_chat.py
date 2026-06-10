"""Chat workspace: conversations, messages, and pgvector embeddings.

Revision ID: 0003_chat
Revises: 0002_gemini_provider
Create Date: 2026-06-10

Note: requires the pgvector extension. On a fresh CI Postgres, use a
pgvector-enabled image (for example pgvector/pgvector:pg15).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003_chat"
down_revision: str | None = "0002_gemini_provider"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ORG = "org_id = nullif(current_setting('app.current_org', true), '')::uuid"


def upgrade() -> None:
    op.execute("create extension if not exists vector")
    op.execute(
        """
        create table conversations (
          id uuid default gen_random_uuid() not null,
          org_id uuid not null,
          user_id uuid not null,
          title text not null default 'new chat',
          created_at timestamptz default now() not null,
          updated_at timestamptz default now() not null,
          primary key (id)
        )
        """
    )
    op.execute(
        "create index ix_conversations_org_user on conversations (org_id, user_id, updated_at)"
    )
    op.execute(
        """
        create table messages (
          id uuid default gen_random_uuid() not null,
          org_id uuid not null,
          conversation_id uuid not null references conversations(id) on delete cascade,
          role text not null,
          content text not null,
          request_id uuid,
          feedback integer,
          embedding vector(768),
          created_at timestamptz default now() not null,
          primary key (id)
        )
        """
    )
    op.execute("create index ix_messages_conversation on messages (conversation_id, created_at)")
    for table in ("conversations", "messages"):
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        op.execute(
            f"create policy org_isolation on {table} using ({_ORG}) with check ({_ORG})"
        )
        op.execute(f"grant select, insert, update, delete on {table} to replay_app")


def downgrade() -> None:
    op.execute("drop table if exists messages")
    op.execute("drop table if exists conversations")
