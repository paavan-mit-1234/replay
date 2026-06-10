"""Pydantic request and response models for the management API."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import BaseModel


class OrgCreate(BaseModel):
    name: str
    slug: str


class OrgOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class OrgMembership(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str


class MeOut(BaseModel):
    user_id: uuid.UUID
    email: str
    orgs: list[OrgMembership]


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    created_at: dt.datetime
    last_used_at: dt.datetime | None
    revoked_at: dt.datetime | None


class ApiKeyCreated(ApiKeyOut):
    # The plaintext key, returned exactly once at creation.
    key: str


class ProviderKeyCreate(BaseModel):
    provider: str
    label: str
    secret: str


class ProviderKeyOut(BaseModel):
    id: uuid.UUID
    provider: str
    label: str
    created_at: dt.datetime
    revoked_at: dt.datetime | None


class RequestOut(BaseModel):
    id: uuid.UUID
    provider: str
    model: str
    endpoint: str
    status_code: int | None
    error: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int | None
    created_at: dt.datetime


class RequestDetail(RequestOut):
    request_body: dict[str, Any]
    response_body: dict[str, Any] | None
    cache_read_tokens: int | None
    cache_write_tokens: int | None


class CostBucket(BaseModel):
    key: str
    requests: int
    cost_usd: float


class StatsOut(BaseModel):
    spend_usd: float
    request_count: int
    error_count: int
    error_rate: float
    median_latency_ms: int | None
