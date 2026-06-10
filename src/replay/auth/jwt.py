"""Supabase JWT verification.

When Supabase is configured, verify the JWT signature against the project JWKS
and return the user id and email. When it is not configured (local dev), a
fallback accepts an unverified token so the stack runs without Supabase.
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from replay.config import get_settings


class AuthError(Exception):
    """Raised when a token cannot be verified."""


@dataclass(frozen=True)
class TokenClaims:
    user_id: str
    email: str


_jwks_client: PyJWKClient | None = None


def _client(jwks_url: str) -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = PyJWKClient(jwks_url)
    return _jwks_client


def verify_token(token: str) -> TokenClaims:
    """Verify a Supabase JWT and extract the user id and email."""
    settings = get_settings()
    if not settings.auth_enabled:
        # Local dev fallback: decode without verifying the signature. Never
        # reached in production, where SUPABASE_JWKS_URL is set.
        claims = jwt.decode(token, options={"verify_signature": False})
        return _claims_from(claims)

    try:
        signing_key = _client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.supabase_jwt_aud,
        )
    except Exception as exc:  # noqa: BLE001 (surface any verification failure uniformly)
        raise AuthError(str(exc)) from exc
    return _claims_from(claims)


def _claims_from(claims: dict[str, object]) -> TokenClaims:
    user_id = claims.get("sub")
    email = claims.get("email", "")
    if not isinstance(user_id, str) or not user_id:
        raise AuthError("token missing sub claim")
    if not isinstance(email, str):
        email = ""
    return TokenClaims(user_id=user_id, email=email)
