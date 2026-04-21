"""Tests for :mod:`luonvuitoi_cert.auth.login` — password / OTP / magic-link dispatch."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from luonvuitoi_cert.auth import (
    LoginError,
    NullEmailProvider,
    Role,
    create_admin_user,
    perform_login,
    verify_admin_token,
)
from luonvuitoi_cert.config import CertConfig


def _cfg(auth_mode: str) -> CertConfig:
    return CertConfig.model_validate(
        {
            "project": {"name": "T", "slug": "t"},
            "rounds": [{"id": "m", "label": "M", "table": "students", "pdf": "t.pdf"}],
            "subjects": [{"code": "S", "en": "S", "db_col": "s"}],
            "results": {"S": {"GOLD": 1}},
            "layout": {
                "page_size": [100, 100],
                "fields": {"n": {"x": 0, "y": 0, "font": "f", "size": 10, "align": "left"}},
            },
            "fonts": {"f": "f.ttf"},
            "admin": {"auth_mode": auth_mode},
        }
    )


def _env() -> dict[str, str]:
    return {"JWT_SECRET": "test-secret-please-change-32-bytes-min"}


# ── password mode ───────────────────────────────────────────────────


def test_password_login_success(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "auth.db"
    create_admin_user(db, email="a@b.co", role=Role.ADMIN, password="pw")
    resp = perform_login(
        _cfg("password"),
        db_path=db,
        kv=kv_memory,
        email_provider=NullEmailProvider(),
        params={"email": "a@b.co", "password": "pw"},
        env=_env(),
    )
    assert resp.token
    claims = verify_admin_token(resp.token, env=_env())
    assert claims.email == "a@b.co"


def test_password_login_wrong_password(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "auth.db"
    create_admin_user(db, email="a@b.co", role=Role.ADMIN, password="pw")
    with pytest.raises(LoginError, match="invalid credentials"):
        perform_login(
            _cfg("password"),
            db_path=db,
            kv=kv_memory,
            email_provider=NullEmailProvider(),
            params={"email": "a@b.co", "password": "wrong"},
            env=_env(),
        )


def test_password_login_unknown_user_same_error(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    """Unknown email and wrong password must surface the same LoginError text."""
    db = tmp_path / "auth.db"
    with pytest.raises(LoginError, match="invalid credentials"):
        perform_login(
            _cfg("password"),
            db_path=db,
            kv=kv_memory,
            email_provider=NullEmailProvider(),
            params={"email": "ghost@x.co", "password": "any"},
            env=_env(),
        )


# ── OTP email mode ──────────────────────────────────────────────────


def test_otp_login_two_steps(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "auth.db"
    create_admin_user(db, email="a@b.co", role=Role.ADMIN, password=None)
    mailer = NullEmailProvider()

    step1 = perform_login(
        _cfg("otp_email"),
        db_path=db,
        kv=kv_memory,
        email_provider=mailer,
        params={"email": "a@b.co"},
        env=_env(),
    )
    assert step1.challenge_issued and step1.token is None
    assert len(mailer.sent) == 1

    # Recover the 6-digit code from the sent email body.
    code = re.search(r"\b(\d{6})\b", mailer.sent[0].text).group(1)  # type: ignore[union-attr]

    step2 = perform_login(
        _cfg("otp_email"),
        db_path=db,
        kv=kv_memory,
        email_provider=mailer,
        params={"email": "a@b.co", "code": code},
        env=_env(),
    )
    assert step2.token is not None


def test_otp_login_unknown_email(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "auth.db"
    mailer = NullEmailProvider()
    with pytest.raises(LoginError):
        perform_login(
            _cfg("otp_email"),
            db_path=db,
            kv=kv_memory,
            email_provider=mailer,
            params={"email": "ghost@x.co"},
            env=_env(),
        )
    assert mailer.sent == []  # no email sent to unknown accounts


def test_otp_login_wrong_code(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "auth.db"
    create_admin_user(db, email="a@b.co", role=Role.ADMIN, password=None)
    mailer = NullEmailProvider()
    perform_login(
        _cfg("otp_email"),
        db_path=db,
        kv=kv_memory,
        email_provider=mailer,
        params={"email": "a@b.co"},
        env=_env(),
    )
    with pytest.raises(LoginError):
        perform_login(
            _cfg("otp_email"),
            db_path=db,
            kv=kv_memory,
            email_provider=mailer,
            params={"email": "a@b.co", "code": "000000"},
            env=_env(),
        )


# ── Magic link mode ─────────────────────────────────────────────────


def test_magic_link_two_steps(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "auth.db"
    create_admin_user(db, email="a@b.co", role=Role.ADMIN, password=None)
    mailer = NullEmailProvider()

    step1 = perform_login(
        _cfg("magic_link"),
        db_path=db,
        kv=kv_memory,
        email_provider=mailer,
        params={"email": "a@b.co"},
        env=_env(),
        magic_link_builder=lambda token: f"https://example/login?t={token}",
    )
    assert step1.challenge_issued and step1.token is None
    # Extract the token from the URL in the email body.
    token = re.search(r"t=([A-Za-z0-9_\-]+)", mailer.sent[0].text).group(1)  # type: ignore[union-attr]

    step2 = perform_login(
        _cfg("magic_link"),
        db_path=db,
        kv=kv_memory,
        email_provider=mailer,
        params={"token": token},
        env=_env(),
    )
    assert step2.token is not None


def test_magic_link_token_is_single_use(tmp_path: Path, kv_memory) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "auth.db"
    create_admin_user(db, email="a@b.co", role=Role.ADMIN, password=None)
    mailer = NullEmailProvider()
    perform_login(
        _cfg("magic_link"),
        db_path=db,
        kv=kv_memory,
        email_provider=mailer,
        params={"email": "a@b.co"},
        env=_env(),
        magic_link_builder=lambda token: f"https://example/login?t={token}",
    )
    token = re.search(r"t=([A-Za-z0-9_\-]+)", mailer.sent[0].text).group(1)  # type: ignore[union-attr]
    perform_login(
        _cfg("magic_link"),
        db_path=db,
        kv=kv_memory,
        email_provider=mailer,
        params={"token": token},
        env=_env(),
    )
    with pytest.raises(LoginError):
        perform_login(
            _cfg("magic_link"),
            db_path=db,
            kv=kv_memory,
            email_provider=mailer,
            params={"token": token},
            env=_env(),
        )
