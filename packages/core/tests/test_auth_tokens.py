"""Tests for :mod:`luonvuitoi_cert.auth.tokens`."""

from __future__ import annotations

import time

import pytest

from luonvuitoi_cert.auth.admin_db import Role
from luonvuitoi_cert.auth.tokens import TokenError, issue_admin_token, verify_admin_token


def _env() -> dict[str, str]:
    # 32+ chars to silence PyJWT's InsecureKeyLengthWarning under SHA256.
    return {"JWT_SECRET": "test-secret-please-change-32-bytes-min"}


def test_issue_verify_roundtrip() -> None:
    env = _env()
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=env)
    claims = verify_admin_token(token, env=env)
    assert claims.user_id == "u1"
    assert claims.email == "a@b.co"
    assert claims.role == Role.ADMIN
    assert claims.jti


def test_tampered_token_rejected() -> None:
    env = _env()
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=env)
    with pytest.raises(TokenError, match="invalid"):
        verify_admin_token(token + "garbage", env=env)


def test_wrong_secret_rejected() -> None:
    token = issue_admin_token(
        user_id="u1",
        email="a@b.co",
        role=Role.ADMIN,
        env={"JWT_SECRET": "secretA-padded-long-enough-for-sha256"},
    )
    with pytest.raises(TokenError):
        verify_admin_token(
            token, env={"JWT_SECRET": "secretB-padded-long-enough-for-sha256"}
        )


def test_expired_token_rejected() -> None:
    env = _env()
    past = int(time.time()) - 100
    token = issue_admin_token(
        user_id="u1", email="a@b.co", role=Role.ADMIN, ttl_seconds=1, now=past, env=env
    )
    with pytest.raises(TokenError, match="expired"):
        verify_admin_token(token, env=env)


def test_empty_token_rejected() -> None:
    with pytest.raises(TokenError, match="required"):
        verify_admin_token("", env=_env())


def test_unknown_role_rejected() -> None:
    import jwt

    payload = {"sub": "u1", "email": "a@b.co", "role": "emperor", "jti": "x", "iat": 0, "exp": 9999999999}
    token = jwt.encode(payload, _env()["JWT_SECRET"], algorithm="HS256")
    with pytest.raises(TokenError, match="unknown role"):
        verify_admin_token(token, env=_env())


def test_missing_jwt_secret_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression: Phase 06 review H1 — silent ephemeral fallback removed."""
    with pytest.raises(TokenError, match="JWT_SECRET is not set"):
        issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env={})
