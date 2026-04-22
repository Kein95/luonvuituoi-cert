"""Regression tests for JWT revocation (M7).

Verifies:
- ``revoke_admin_token`` stores the caller's ``jti`` in the KV denylist.
- ``verify_admin_token`` with ``kv=`` rejects a revoked token.
- ``verify_admin_token`` without ``kv=`` (legacy calls) still accepts it
  — backwards compatible by design.
- TTL on the denylist entry matches the token's remaining life.
- Already-expired tokens are no-op on revoke.
"""

from __future__ import annotations

import contextlib
import time

import pytest
from luonvuitoi_cert.auth import (
    Role,
    TokenError,
    issue_admin_token,
    revoke_admin_token,
    verify_admin_token,
)
from luonvuitoi_cert.auth.tokens import JTI_DENYLIST_PREFIX


class _MemKV:
    """Minimal in-memory KV for unit tests — mirrors the KVBackend protocol."""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, float]] = {}

    def get(self, key: str) -> str | None:
        entry = self.store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at and time.time() > expires_at:
            del self.store[key]
            return None
        return value

    def set(self, key: str, value: str, *, ttl_seconds: int | None = None) -> None:
        expires_at = time.time() + ttl_seconds if ttl_seconds else 0.0
        self.store[key] = (value, expires_at)

    def delete(self, key: str) -> None:
        self.store.pop(key, None)

    def consume(self, key: str) -> str | None:
        v = self.get(key)
        if v is not None:
            self.delete(key)
        return v


def _env() -> dict[str, str]:
    return {"JWT_SECRET": "test-secret-padded-to-32-bytes-min-here"}


def test_revoke_stores_jti_in_denylist() -> None:
    kv = _MemKV()
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    jti = revoke_admin_token(kv, token=token, env=_env())
    assert kv.get(f"{JTI_DENYLIST_PREFIX}{jti}") == "1"


def test_verify_with_kv_rejects_revoked_token() -> None:
    kv = _MemKV()
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    revoke_admin_token(kv, token=token, env=_env())
    with pytest.raises(TokenError, match="revoked"):
        verify_admin_token(token, env=_env(), kv=kv)


def test_verify_without_kv_still_accepts_revoked_token() -> None:
    """Backwards compat: callers that don't thread kv through keep old behavior."""
    kv = _MemKV()
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    revoke_admin_token(kv, token=token, env=_env())
    # No kv passed → denylist is not consulted → token still verifies.
    decoded = verify_admin_token(token, env=_env())
    assert decoded.user_id == "u1"


def test_fresh_token_with_kv_still_verifies() -> None:
    kv = _MemKV()
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=_env())
    decoded = verify_admin_token(token, env=_env(), kv=kv)
    assert decoded.email == "a@b.co"


def test_revoke_expired_token_is_noop() -> None:
    """Tokens that already expired aren't added to the denylist."""
    kv = _MemKV()
    # Issue a token that expired 1 second ago.
    token = issue_admin_token(
        user_id="u1",
        email="a@b.co",
        role=Role.ADMIN,
        ttl_seconds=1,
        env=_env(),
        now=int(time.time()) - 10,
    )
    # Must be called before JWT lib rejects on exp; since our test helper stays
    # inside the library, PyJWT may reject it first. Accept either outcome:
    with contextlib.suppress(TokenError):
        revoke_admin_token(kv, token=token, env=_env())
    # Denylist should remain empty (no revocation of expired tokens).
    assert not kv.store


def test_revocation_ttl_matches_remaining_life() -> None:
    kv = _MemKV()
    token = issue_admin_token(
        user_id="u1",
        email="a@b.co",
        role=Role.ADMIN,
        ttl_seconds=120,
        env=_env(),
    )
    jti = revoke_admin_token(kv, token=token, env=_env())
    _, expires_at = kv.store[f"{JTI_DENYLIST_PREFIX}{jti}"]
    # Should be within a few seconds of now + 120s (clock-jitter tolerance).
    remaining = expires_at - time.time()
    assert 100 <= remaining <= 125, f"TTL drift: {remaining}s"
