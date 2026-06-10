"""Replay API key generation, hashing, and verification.

A Replay API key is a high entropy random token shown to the user exactly once
at creation. Only a SHA-256 hash and a short display prefix are stored, never
the key itself. Verification hashes the presented key and compares.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

KEY_PREFIX = "rpl_"
_PREFIX_DISPLAY_LEN = 12


@dataclass(frozen=True)
class GeneratedKey:
    """A freshly minted key. The plaintext is returned once and never stored."""

    plaintext: str
    prefix: str
    hash: str


def hash_key(plaintext: str) -> str:
    """Return the SHA-256 hex digest of a key. High entropy input makes this safe."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


def generate_key() -> GeneratedKey:
    """Create a new random key with a rpl_ prefix."""
    token = KEY_PREFIX + secrets.token_urlsafe(32)
    return GeneratedKey(
        plaintext=token,
        prefix=token[:_PREFIX_DISPLAY_LEN],
        hash=hash_key(token),
    )
