"""Replay API key generation and hashing tests."""

from __future__ import annotations

from replay.auth import apikeys


def test_generated_key_has_prefix_and_hash() -> None:
    gen = apikeys.generate_key()
    assert gen.plaintext.startswith("rpl_")
    assert gen.prefix == gen.plaintext[:12]
    # The stored hash is a SHA-256 hex digest, never the plaintext.
    assert gen.hash != gen.plaintext
    assert len(gen.hash) == 64


def test_hash_is_verifiable_and_deterministic() -> None:
    gen = apikeys.generate_key()
    assert apikeys.hash_key(gen.plaintext) == gen.hash


def test_keys_are_unique() -> None:
    assert apikeys.generate_key().plaintext != apikeys.generate_key().plaintext
