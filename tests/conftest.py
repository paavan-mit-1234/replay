"""Shared test fixtures."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet


@pytest.fixture(scope="session", autouse=True)
def _vault_key_env() -> None:
    """Ensure a vault key exists for tests that exercise encryption."""
    os.environ.setdefault("REPLAY_VAULT_KEY", Fernet.generate_key().decode())
    from replay.config import get_settings

    get_settings.cache_clear()
