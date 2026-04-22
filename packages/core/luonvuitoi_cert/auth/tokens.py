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
from luonvuitoi_cert.storage.kv.base import KVBackend

DEFAULT_TOKEN_TTL_SECONDS = 8 * 3600
ALGORITHM = "HS256"
# M7: KV prefix for the JTI denylist. Sign-out stores `{jti}` here with TTL =
# `exp - now`; verify_admin_token treats any hit as an expired session.
JTI_DENYLIST_PREFIX = "jwt_denylist:"


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


def verify_admin_token(
    token: str,
    *,
    env: dict[str, str] | None = None,
    kv: KVBackend | None = None,
) -> AdminToken:
    """Decode and validate a JWT, returning the structured claims.

    If ``kv`` is provided, the decoded ``jti`` is also checked against the
    denylist (M7). A revoked token is rejected with the same ``TokenError``
    shape as an expired one — callers don't need to distinguish.
    """
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
    jti = claims.get("jti", "")
    if kv is not None and jti and kv.get(f"{JTI_DENYLIST_PREFIX}{jti}"):
        raise TokenError("admin session revoked")
    return AdminToken(
        user_id=claims.get("sub", ""),
        email=claims.get("email", ""),
        role=role,
        jti=jti,
        issued_at=int(claims.get("iat", 0)),
        expires_at=int(claims.get("exp", 0)),
    )


def revoke_admin_token(kv: KVBackend, *, token: str, env: dict[str, str] | None = None) -> str:
    """Add the token's ``jti`` to the denylist with TTL matching its remaining life.

    Returns the revoked ``jti`` so callers can log the sign-out. Silently
    succeeds for already-expired tokens (no point denylisting something the
    JWT library will reject anyway).
    """
    # Decode without the kv check so a token revoked in a prior session can
    # still be "revoked" idempotently.
    decoded = verify_admin_token(token, env=env, kv=None)
    remaining = decoded.expires_at - int(time.time())
    if remaining <= 0:
        return decoded.jti
    if decoded.jti:
        kv.set(f"{JTI_DENYLIST_PREFIX}{decoded.jti}", "1", ttl_seconds=remaining)
    return decoded.jti
