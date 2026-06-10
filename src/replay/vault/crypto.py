"""Symmetric encryption for the provider key vault.

The primary key encrypts. Any configured key (primary plus rotation keys) can
decrypt, so keys can be rotated without a flag day. Keys come from the
environment only and are never persisted.
"""

from __future__ import annotations

from cryptography.fernet import Fernet, MultiFernet

from replay.config import get_settings


class VaultNotConfigured(RuntimeError):
    """Raised when no vault key is available to encrypt or decrypt."""


def _fernets() -> list[Fernet]:
    keys = get_settings().vault_decrypt_keys
    if not keys:
        raise VaultNotConfigured(
            "REPLAY_VAULT_KEY is not set. Generate one with "
            "python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())"'
        )
    return [Fernet(k.encode()) for k in keys]


def encrypt(plaintext: str) -> bytes:
    """Encrypt with the primary key. Returns a Fernet token as bytes."""
    primary = _fernets()[0]
    return primary.encrypt(plaintext.encode())


def decrypt(token: bytes) -> str:
    """Decrypt, trying the primary key then any rotation keys."""
    multi = MultiFernet(_fernets())
    return multi.decrypt(token).decode()
