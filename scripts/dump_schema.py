"""Emit the full Phase 1 schema DDL for Postgres, mirroring migration 0001.

This is a helper for applying the baseline through the Supabase tooling. The
Alembic migration remains the source of truth for deployment and CI; this just
lets us stand up the same schema on a managed Postgres without local creds.
"""

from __future__ import annotations

from sqlalchemy.schema import CreateIndex, CreateTable
from sqlalchemy.dialects import postgresql

from replay.db.base import Base
from replay.db import models  # noqa: F401  (registers tables)
from replay.db.models import TENANT_TABLES

dialect = postgresql.dialect()

print("create extension if not exists pgcrypto;")

for table in Base.metadata.sorted_tables:
    print(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
    for index in table.indexes:
        print(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")

bootstrap_tables = {"api_keys", "memberships"}
org_clause = "org_id = nullif(current_setting('app.current_org', true), '')::uuid"
bootstrap_clause = "current_setting('app.auth_bootstrap', true) = 'on'"

for table in TENANT_TABLES:
    print(f"alter table {table} enable row level security;")
    print(f"alter table {table} force row level security;")
    if table in bootstrap_tables:
        using = f"({org_clause}) or ({bootstrap_clause})"
        print(
            f"create policy org_isolation on {table} "
            f"using ({using}) with check ({org_clause});"
        )
    else:
        print(
            f"create policy org_isolation on {table} "
            f"using ({org_clause}) with check ({org_clause});"
        )
