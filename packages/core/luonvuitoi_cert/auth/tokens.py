"""JWT HS256 issue + verify for admin sessions.

Keeping the token logic in one place means admin handlers only ever see
:class:`AdminToken` objects — they never import PyJWT themselves. The secret
comes from ``JWT_SECRET`` env var; in tests and local dev a fallback is
allowed but loudly logged once per process.
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass

import jwt

from luonvuitoi_cert.auth.admin_db import Role

DEFAULT_TOKEN_TTL_SECONDS = 8 * 3600
ALGORITHM = "HS256"


class TokenError(Exception):
    """Raised when a presented token is missing, malformed, tampered with, or expired."""


@dataclass(frozen=True, slots=True)
class AdminToken:
    user_id: str
    email: str
    role: Role
    jti: str
    issued_at: int
    expires_at: int


def _resolve_secret(env: dict[str, str] | None) -> str:
    """Require ``JWT_SECRET`` explicitly — no silent fallback.

    Serverless handlers may run in many processes; sharing an ephemeral
    secret across invocations is impossible, so a missing secret is a
    configuration bug, not something to paper over. Tests set the env via
    the ``_jwt_secret_for_tests`` autouse fixture.
    """
    source = env if env is not None else os.environ
    secret = source.get("JWT_SECRET", "")
    if not secret:
        raise TokenError("JWT_SECRET is not set; cannot issue/verify admin tokens")
    return secret


def issue_admin_token(
    *,
    user_id: str,
    email: str,
    role: Role,
    ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    env: dict[str, str] | None = None,
    now: int | None = None,
) -> str:
    """Mint a signed JWT describing an authenticated admin session."""
    issued_at = int(now if now is not None else time.time())
    expires_at = issued_at + ttl_seconds
    payload = {
        "sub": user_id,
        "email": email,
        "role": role.value if isinstance(role, Role) else str(role),
        "jti": secrets.token_urlsafe(12),
        "iat": issued_at,
        "exp": expires_at,
    }
    return jwt.encode(payload, _resolve_secret(env), algorithm=ALGORITHM)


def verify_admin_token(token: str, *, env: dict[str, str] | None = None) -> AdminToken:
    """Decode and validate a JWT, returning the structured claims."""
    if not token:
        raise TokenError("admin token is required")
    try:
        claims = jwt.decode(token, _resolve_secret(env), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as e:
        raise TokenError("admin session expired") from e
    except jwt.InvalidTokenError as e:
        raise TokenError("admin token is invalid") from e
    try:
        role = Role(claims["role"])
    except (KeyError, ValueError) as e:
        raise TokenError(f"admin token has unknown role: {claims.get('role')!r}") from e
    return AdminToken(
        user_id=claims.get("sub", ""),
        email=claims.get("email", ""),
        role=role,
        jti=claims.get("jti", ""),
        issued_at=int(claims.get("iat", 0)),
        expires_at=int(claims.get("exp", 0)),
    )
