"""Tests for :mod:`luonvuitoi_cert.api.admin_update`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from luonvuitoi_cert.api.admin_update import AdminUpdateError, update_student_field
from luonvuitoi_cert.auth import ActivityLog, Role, issue_admin_token


def _env() -> dict[str, str]:
    return {"JWT_SECRET": "test-secret-please-change-32-bytes-min"}


def _token(role: Role) -> str:
    return issue_admin_token(user_id="u1", email="a@b.co", role=role, env=_env())


def _fetch_value(db: Path, table: str, sbd: str, col: str) -> str:
    conn = sqlite3.connect(str(db))
    row = conn.execute(f'SELECT "{col}" FROM "{table}" WHERE "sbd" = ?', (sbd,)).fetchone()
    conn.close()
    return str(row[0]) if row else ""


def test_admin_updates_field(cert_config, populated_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    resp = update_student_field(
        config=cert_config,
        db_path=populated_db,
        activity=log,
        params={
            "token": _token(Role.ADMIN),
            "sbd": "12345",
            "round_id": "main",
            "column": "school",
            "new_value": "Updated School",
        },
        env=_env(),
    )
    assert resp.changed
    assert _fetch_value(populated_db, "students", "12345", "school") == "Updated School"
    entries = log.recent()
    assert entries[0].action == "student.update"
    assert entries[0].metadata["new"] == "Updated School"


def test_viewer_role_is_read_only(cert_config, populated_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    with pytest.raises(AdminUpdateError, match="read-only"):
        update_student_field(
            config=cert_config,
            db_path=populated_db,
            activity=log,
            params={
                "token": _token(Role.VIEWER),
                "sbd": "12345",
                "round_id": "main",
                "column": "school",
                "new_value": "X",
            },
            env=_env(),
        )


def test_refuses_to_change_primary_key(cert_config, populated_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    with pytest.raises(AdminUpdateError, match="primary key"):
        update_student_field(
            config=cert_config,
            db_path=populated_db,
            activity=log,
            params={
                "token": _token(Role.ADMIN),
                "sbd": "12345",
                "round_id": "main",
                "column": "sbd",
                "new_value": "99999",
            },
            env=_env(),
        )


def test_rejects_unknown_column(cert_config, populated_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    with pytest.raises(AdminUpdateError, match="not in the schema"):
        update_student_field(
            config=cert_config,
            db_path=populated_db,
            activity=log,
            params={
                "token": _token(Role.ADMIN),
                "sbd": "12345",
                "round_id": "main",
                "column": "totally_not_a_column",
                "new_value": "X",
            },
            env=_env(),
        )


def test_rejects_missing_student(cert_config, populated_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    with pytest.raises(AdminUpdateError, match="no row"):
        update_student_field(
            config=cert_config,
            db_path=populated_db,
            activity=log,
            params={
                "token": _token(Role.ADMIN),
                "sbd": "99999",
                "round_id": "main",
                "column": "school",
                "new_value": "X",
            },
            env=_env(),
        )


def test_noop_update_is_recorded_but_not_changed(cert_config, populated_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    resp = update_student_field(
        config=cert_config,
        db_path=populated_db,
        activity=log,
        params={
            "token": _token(Role.ADMIN),
            "sbd": "12345",
            "round_id": "main",
            "column": "school",
            "new_value": "Test School",  # same as the seeded value
        },
        env=_env(),
    )
    assert not resp.changed
    assert log.recent()[0].metadata["changed"] is False


def test_invalid_token_rejected(cert_config, populated_db, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    log = ActivityLog(tmp_path / "audit.db")
    with pytest.raises(AdminUpdateError):
        update_student_field(
            config=cert_config,
            db_path=populated_db,
            activity=log,
            params={
                "token": "not-a-jwt",
                "sbd": "12345",
                "round_id": "main",
                "column": "school",
                "new_value": "X",
            },
            env=_env(),
        )
