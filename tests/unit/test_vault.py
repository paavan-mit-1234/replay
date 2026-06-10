"""Key vault encryption tests."""

from __future__ import annotations

from replay.vault import crypto


def test_round_trip() -> None:
    secret = "sk-ant-super-secret-value"
    token = crypto.encrypt(secret)
    # Ciphertext must not contain the plaintext.
    assert secret.encode() not in token
    assert crypto.decrypt(token) == secret


def test_ciphertext_differs_each_time() -> None:
    # Fernet includes a random IV, so two encryptions differ.
    assert crypto.encrypt("same") != crypto.encrypt("same")
