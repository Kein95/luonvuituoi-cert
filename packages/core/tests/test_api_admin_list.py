"""Tests for :mod:`luonvuitoi_cert.api.admin_list`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from luonvuitoi_cert.api.admin_list import (
    MAX_LIST_RESULTS,
    MIN_NAME_PREFIX,
    AdminListError,
    admin_list_students,
)
from luonvuitoi_cert.api.security import SecurityError
from luonvuitoi_cert.auth import ActivityLog, Role, issue_admin_token


def _env() -> dict[str, str]:
    return {"JWT_SECRET": "test-secret-please-change-32-bytes-min"}


def _token(role: Role = Role.ADMIN) -> str:
    return issue_admin_token(user_id="u1", email="a@b.co", role=role, env=_env())


def _seed_rows(db: Path, rows: list[dict]) -> None:
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE IF NOT EXISTS students ("
        "sbd TEXT PRIMARY KEY, full_name TEXT, dob TEXT, school TEXT, phone TEXT, result TEXT)"
    )
    for r in rows:
        conn.execute(
            "INSERT OR REPLACE INTO students VALUES (?, ?, ?, ?, ?, ?)",
            (r["sbd"], r["full_name"], r["dob"], r["school"], r["phone"], r["result"]),
        )
    conn.commit()
    conn.close()


@pytest.fixture
def seeded_db(cert_config, tmp_path: Path) -> Path:  # type: ignore[no-untyped-def]
    db = tmp_path / "test.db"
    _seed_rows(
        db,
        [
            {
                "sbd": "10001",
                "full_name": "Nguyễn Văn An",
                "dob": "2010-01-15",
                "school": "A",
                "phone": "0901000001",
                "result": "GOLD",
            },
            {
                "sbd": "10002",
                "full_name": "Nguyễn Thị Bình",
                "dob": "2010-02-20",
                "school": "B",
                "phone": "0901000002",
                "result": "SILVER",
            },
            {
                "sbd": "10003",
                "full_name": "Trần Văn Chung",
                "dob": "2011-03-30",
                "school": "C",
                "phone": "0901000003",
                "result": "BRONZE",
            },
        ],
    )
    return db


def test_rejects_missing_filter(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    with pytest.raises(SecurityError, match="at least one filter"):
        admin_list_students(
            config=cert_config,
            db_path=seeded_db,
            activity=log,
            params={"token": _token()},
            env=_env(),
        )


def test_rejects_short_name(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    with pytest.raises(SecurityError, match=f"≥ {MIN_NAME_PREFIX}"):
        admin_list_students(
            config=cert_config,
            db_path=seeded_db,
            activity=log,
            params={"token": _token(), "name": "A"},
            env=_env(),
        )


def test_rejects_invalid_token(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    with pytest.raises(AdminListError):
        admin_list_students(
            config=cert_config,
            db_path=seeded_db,
            activity=log,
            params={"token": "not-a-jwt", "name": "Nguyen"},
            env=_env(),
        )


def test_name_prefix_accent_tolerant(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    resp = admin_list_students(
        config=cert_config,
        db_path=seeded_db,
        activity=log,
        params={"token": _token(), "name": "nguyen"},
        env=_env(),
    )
    names = [r.name for r in resp.rows]
    assert "Nguyễn Văn An" in names
    assert "Nguyễn Thị Bình" in names
    assert "Trần Văn Chung" not in names
    assert resp.total == 2


def test_sbd_exact_match(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    resp = admin_list_students(
        config=cert_config,
        db_path=seeded_db,
        activity=log,
        params={"token": _token(), "sbd": "10002"},
        env=_env(),
    )
    assert resp.total == 1
    assert resp.rows[0].sbd == "10002"


def test_combined_name_and_dob(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    resp = admin_list_students(
        config=cert_config,
        db_path=seeded_db,
        activity=log,
        params={"token": _token(), "name": "nguyen", "dob": "15/01/2010"},
        env=_env(),
    )
    assert resp.total == 1
    assert resp.rows[0].sbd == "10001"


def test_phone_last4(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    resp = admin_list_students(
        config=cert_config,
        db_path=seeded_db,
        activity=log,
        params={"token": _token(), "phone": "0003"},
        env=_env(),
    )
    assert resp.total == 1
    assert resp.rows[0].sbd == "10003"


def test_no_matches_returns_empty_not_error(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    resp = admin_list_students(
        config=cert_config,
        db_path=seeded_db,
        activity=log,
        params={"token": _token(), "sbd": "99999"},
        env=_env(),
    )
    assert resp.total == 0
    assert resp.rows == []


def test_viewer_role_can_read(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Admin list is read-only; viewer is allowed."""
    log = ActivityLog(tmp_path / "audit.db")
    resp = admin_list_students(
        config=cert_config,
        db_path=seeded_db,
        activity=log,
        params={"token": _token(Role.VIEWER), "name": "nguyen"},
        env=_env(),
    )
    assert resp.total == 2


def test_logs_admin_list_action(cert_config, seeded_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    admin_list_students(
        config=cert_config,
        db_path=seeded_db,
        activity=log,
        params={"token": _token(), "name": "nguyen"},
        env=_env(),
    )
    entries = log.recent()
    assert entries[0].action == "admin.list"
    assert "name" in entries[0].metadata["filters"]
    assert entries[0].metadata["total"] == 2


def test_truncates_at_max_results(cert_config, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    db = tmp_path / "big.db"
    _seed_rows(
        db,
        [
            {
                "sbd": f"200{i:02d}",
                "full_name": f"Nguyen Test {i}",
                "dob": "2010-01-01",
                "school": "S",
                "phone": f"09010{i:05d}",
                "result": "GOLD",
            }
            for i in range(MAX_LIST_RESULTS + 5)
        ],
    )
    log = ActivityLog(tmp_path / "audit.db")
    resp = admin_list_students(
        config=cert_config,
        db_path=db,
        activity=log,
        params={"token": _token(), "name": "nguyen"},
        env=_env(),
    )
    assert resp.total == MAX_LIST_RESULTS + 5
    assert resp.truncated is True
    assert len(resp.rows) == MAX_LIST_RESULTS
