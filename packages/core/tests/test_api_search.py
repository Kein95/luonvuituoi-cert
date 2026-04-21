"""Tests for :mod:`luonvuitoi_cert.api.search`."""

from __future__ import annotations

import re

import pytest

from luonvuitoi_cert.api.captcha import issue_challenge
from luonvuitoi_cert.api.rate_limiter import RateLimitError
from luonvuitoi_cert.api.search import SearchError, search_student
from luonvuitoi_cert.api.security import SecurityError


def _solve(question: str) -> int:
    a, op, b = re.match(r"(\d+)\s*([+\-×])\s*(\d+)", question).groups()  # type: ignore[union-attr]
    return {"+": int(a) + int(b), "-": int(a) - int(b), "×": int(a) * int(b)}[op]


def _student_params(kv, **extra) -> dict:  # type: ignore[no-untyped-def]
    ch = issue_challenge(kv)
    return {
        "sbd": "12345",
        "name": "Nguyễn Văn A",
        "dob": "01-06-2010",
        "captcha_id": ch.id,
        "captcha_answer": _solve(ch.question),
        **extra,
    }


# ── Happy path ──────────────────────────────────────────────────────


def test_student_mode_finds_match(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    res = search_student(
        config=cert_config,
        db_path=populated_db,
        kv=kv_memory,
        params=_student_params(kv_memory),
        client_id="ip-1",
    )
    assert res.sbd == "12345"
    assert res.name == "Nguyễn Văn A"
    assert len(res.certificates) == 1
    cert = res.certificates[0]
    assert cert.round_id == "main"
    assert cert.subject_code == "S"
    assert cert.result_name == "GOLD"
    assert cert.page_number == 1


def test_name_is_accent_tolerant(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    params = _student_params(kv_memory, name="nguyen van a")  # no diacritics, lowercase
    res = search_student(
        config=cert_config, db_path=populated_db, kv=kv_memory, params=params, client_id="ip-1"
    )
    assert res.sbd == "12345"


def test_dob_normalization(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    params = _student_params(kv_memory, dob="1/6/2010")  # slashes, no zero pad
    res = search_student(
        config=cert_config, db_path=populated_db, kv=kv_memory, params=params, client_id="ip-1"
    )
    assert res.sbd == "12345"


@pytest.mark.parametrize("dob", ["01-06-2010", "1/6/2010", "01.06.2010", "2010-06-01", "  01-06-2010  "])
def test_dob_accepts_iso_and_dotted_and_whitespace(cert_config, populated_db, kv_memory, dob: str) -> None:  # type: ignore[no-untyped-def]
    """Regression: Phase 05 review H2 — ISO, dotted, and trimmed variants must match."""
    params = _student_params(kv_memory, dob=dob)
    res = search_student(
        config=cert_config, db_path=populated_db, kv=kv_memory, params=params, client_id="ip-1"
    )
    assert res.sbd == "12345"


# ── Admin mode ──────────────────────────────────────────────────────


def _admin_token() -> str:
    from luonvuitoi_cert.auth import Role, issue_admin_token

    return issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN)


def test_admin_mode_skips_captcha(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    res = search_student(
        config=cert_config,
        db_path=populated_db,
        kv=kv_memory,
        params={"sbd": "12345", "token": _admin_token()},
        client_id="ip-1",
        mode="admin",
    )
    assert res.sbd == "12345"


def test_admin_mode_requires_valid_jwt(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SecurityError):
        search_student(
            config=cert_config,
            db_path=populated_db,
            kv=kv_memory,
            params={"sbd": "12345", "token": "not-a-real-jwt"},
            client_id="ip-1",
            mode="admin",
        )


def test_admin_mode_rejects_empty_token(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(SecurityError):
        search_student(
            config=cert_config,
            db_path=populated_db,
            kv=kv_memory,
            params={"sbd": "12345"},
            client_id="ip-1",
            mode="admin",
        )


def test_admin_mode_honors_env_jwt_secret(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    """Regression: Phase 06 review C2 — env= must thread through to verify_admin_token."""
    from luonvuitoi_cert.auth import Role, issue_admin_token

    custom_env = {"JWT_SECRET": "isolated-env-secret-padded-to-32-bytes"}
    token = issue_admin_token(user_id="u1", email="a@b.co", role=Role.ADMIN, env=custom_env)
    res = search_student(
        config=cert_config,
        db_path=populated_db,
        kv=kv_memory,
        params={"sbd": "12345", "token": token},
        client_id="ip-1",
        mode="admin",
        env=custom_env,
    )
    assert res.sbd == "12345"

    # Same token against a different env must fail (proves env is actually threaded).
    wrong_env = {"JWT_SECRET": "completely-different-secret-for-test"}
    with pytest.raises(SecurityError):
        search_student(
            config=cert_config,
            db_path=populated_db,
            kv=kv_memory,
            params={"sbd": "12345", "token": token},
            client_id="ip-1",
            mode="admin",
            env=wrong_env,
        )


# ── Failure modes ───────────────────────────────────────────────────


def test_no_match_raises(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    params = _student_params(kv_memory, sbd="99999")
    with pytest.raises(SearchError, match="no matching"):
        search_student(
            config=cert_config, db_path=populated_db, kv=kv_memory, params=params, client_id="ip-1"
        )


def test_wrong_dob_rejected(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    params = _student_params(kv_memory, dob="02-06-2010")
    with pytest.raises(SearchError, match="no matching"):
        search_student(
            config=cert_config, db_path=populated_db, kv=kv_memory, params=params, client_id="ip-1"
        )


def test_wrong_name_rejected(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    params = _student_params(kv_memory, name="Someone Else")
    with pytest.raises(SearchError, match="no matching"):
        search_student(
            config=cert_config, db_path=populated_db, kv=kv_memory, params=params, client_id="ip-1"
        )


def test_invalid_sbd_format(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    params = _student_params(kv_memory, sbd="abc/../etc/passwd")
    with pytest.raises(SecurityError):
        search_student(
            config=cert_config, db_path=populated_db, kv=kv_memory, params=params, client_id="ip-1"
        )


def test_rate_limit_kicks_in(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    for _ in range(20):
        search_student(
            config=cert_config,
            db_path=populated_db,
            kv=kv_memory,
            params=_student_params(kv_memory),
            client_id="ip-1",
        )
    with pytest.raises(RateLimitError):
        search_student(
            config=cert_config,
            db_path=populated_db,
            kv=kv_memory,
            params=_student_params(kv_memory),
            client_id="ip-1",
        )


def test_failed_captcha_does_not_tick_rate_limit(cert_config, populated_db, kv_memory) -> None:  # type: ignore[no-untyped-def]
    """Regression: Phase 05 review H3 — 20 wrong CAPTCHA guesses used to lock out legit users."""
    from luonvuitoi_cert.api.captcha import CaptchaError

    # 30 wrong CAPTCHA submissions (well over the 20-req/min limit).
    for _ in range(30):
        params = _student_params(kv_memory, captcha_answer=99999)  # wrong
        with pytest.raises(CaptchaError):
            search_student(
                config=cert_config,
                db_path=populated_db,
                kv=kv_memory,
                params=params,
                client_id="ip-1",
            )
    # Next legitimate request still succeeds — rate limit never ticked.
    res = search_student(
        config=cert_config,
        db_path=populated_db,
        kv=kv_memory,
        params=_student_params(kv_memory),
        client_id="ip-1",
    )
    assert res.sbd == "12345"
