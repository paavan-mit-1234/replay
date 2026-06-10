"""Initial schema with Row Level Security on every tenant table.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-09
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# Import models so every table is registered on Base.metadata.
import replay.db.models  # noqa: F401
from replay.db.base import Base
from replay.db.models import TENANT_TABLES

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # gen_random_uuid is built into Postgres 13+, but pgcrypto guarantees it
    # on older or minimal installs. Safe to run if it already exists.
    op.execute("create extension if not exists pgcrypto")

    # Create every table from the model metadata. This keeps the baseline in
    # lockstep with the models for v1. Later schema changes get their own
    # explicit migrations.
    Base.metadata.create_all(bind=bind)

    # Turn on Row Level Security and add the org isolation policy on every
    # tenant table. FORCE makes the policy apply even to the table owner role,
    # which is what Supabase and local superuser connections use.
    #
    # Two tables (api_keys, memberships) must be readable during the auth
    # bootstrap, before the org scope is known: the proxy looks up an API key
    # by hash, and the dashboard resolves a user's memberships. Those tables
    # get an extra branch keyed on the app.auth_bootstrap setting. The sensitive
    # tables (provider_keys, requests, and the rest) never honor bootstrap and
    # stay strictly isolated to the current org.
    bootstrap_tables = {"api_keys", "memberships"}
    org_clause = "org_id = nullif(current_setting('app.current_org', true), '')::uuid"
    bootstrap_clause = "current_setting('app.auth_bootstrap', true) = 'on'"

    for table in TENANT_TABLES:
        op.execute(f"alter table {table} enable row level security")
        op.execute(f"alter table {table} force row level security")
        if table in bootstrap_tables:
            using = f"({org_clause}) or ({bootstrap_clause})"
            op.execute(
                f"create policy org_isolation on {table} "
                f"using ({using}) with check ({org_clause})"
            )
        else:
            op.execute(
                f"create policy org_isolation on {table} "
                f"using ({org_clause}) with check ({org_clause})"
            )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"drop policy if exists org_isolation on {table}")
        op.execute(f"alter table {table} disable row level security")
    Base.metadata.drop_all(bind=op.get_bind())
