"""Tests for :mod:`luonvuitoi_cert.auth.admin_db`."""

from __future__ import annotations

from pathlib import Path

import pytest
from luonvuitoi_cert.auth.admin_db import (
    AdminUserError,
    Role,
    create_admin_user,
    delete_admin_user,
    ensure_admin_schema,
    get_admin_user,
    list_admin_users,
    update_admin_password,
    verify_admin_password,
)


def _db(tmp_path: Path) -> Path:
    return tmp_path / "auth.db"


def test_create_and_fetch(tmp_path: Path) -> None:
    db = _db(tmp_path)
    user = create_admin_user(db, email="Admin@Example.Co", role=Role.ADMIN, password="hunter2")
    assert user.email == "admin@example.co"  # normalized
    assert user.role == Role.ADMIN
    assert user.is_active
    fetched = get_admin_user(db, email="admin@example.co")
    assert fetched is not None and fetched.id == user.id


def test_duplicate_email_rejected(tmp_path: Path) -> None:
    db = _db(tmp_path)
    create_admin_user(db, email="a@b.co", role=Role.ADMIN, password="pw")
    with pytest.raises(AdminUserError, match="already exists"):
        create_admin_user(db, email="a@b.co", role=Role.SUPER_ADMIN, password="pw2")


def test_invalid_email_rejected(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with pytest.raises(AdminUserError, match="invalid email"):
        create_admin_user(db, email="nope", role=Role.ADMIN, password="pw")


def test_list_returns_insertion_order(tmp_path: Path) -> None:
    db = _db(tmp_path)
    for e in ("a@x.co", "b@x.co", "c@x.co"):
        create_admin_user(db, email=e, role=Role.VIEWER, password="pw")
    emails = [u.email for u in list_admin_users(db)]
    assert emails == ["a@x.co", "b@x.co", "c@x.co"]


def test_update_password_changes_stored_hash(tmp_path: Path) -> None:
    db = _db(tmp_path)
    user = create_admin_user(db, email="a@b.co", role=Role.ADMIN, password="old")
    update_admin_password(db, user_id=user.id, new_password="new")
    assert verify_admin_password(db, email="a@b.co", password="new") is not None
    assert verify_admin_password(db, email="a@b.co", password="old") is None


def test_update_password_unknown_user_raises(tmp_path: Path) -> None:
    db = _db(tmp_path)
    with pytest.raises(AdminUserError, match="not found"):
        update_admin_password(db, user_id="bogus", new_password="pw")


def test_delete_removes_user(tmp_path: Path) -> None:
    db = _db(tmp_path)
    user = create_admin_user(db, email="a@b.co", role=Role.ADMIN, password="pw")
    delete_admin_user(db, user_id=user.id)
    assert get_admin_user(db, email="a@b.co") is None


def test_verify_password_returns_none_for_unknown_email(tmp_path: Path) -> None:
    db = _db(tmp_path)
    ensure_admin_schema(db)
    assert verify_admin_password(db, email="ghost@x.co", password="any") is None


def test_passwordless_user_cannot_login_with_password(tmp_path: Path) -> None:
    db = _db(tmp_path)
    create_admin_user(db, email="otp@x.co", role=Role.ADMIN, password=None)
    assert verify_admin_password(db, email="otp@x.co", password="anything") is None


def test_get_admin_requires_key(tmp_path: Path) -> None:
    db = _db(tmp_path)
    ensure_admin_schema(db)
    with pytest.raises(AdminUserError, match="email or user_id"):
        get_admin_user(db)
