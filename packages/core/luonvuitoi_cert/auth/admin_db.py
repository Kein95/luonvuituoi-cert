"""Admin user storage: table schema + CRUD on the same SQLite file as students.

Schema:

- ``admin_users(id TEXT PK, email TEXT UNIQUE NOT NULL, password_hash TEXT,
  role TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT)``

Passwords are optional — OTP-email and magic-link modes leave the column
``NULL``. Role is stored as the string enum value; :class:`Role` enforces the
allowed set at read time.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from luonvuitoi_cert.auth.passwords import hash_password, verify_password


class Role(str, Enum):
    SUPER_ADMIN = "super-admin"
    ADMIN = "admin"
    VIEWER = "viewer"


class AdminUserError(Exception):
    """Raised for duplicate-email inserts, unknown users, or role mismatches."""


@dataclass(frozen=True, slots=True)
class AdminUser:
    id: str
    email: str
    role: Role
    is_active: bool
    created_at: str


_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS admin_users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT,
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""


def ensure_admin_schema(db_path: str | Path) -> None:
    db = Path(db_path).expanduser().resolve()
    db.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(db))) as conn, conn:
        conn.execute(_CREATE_SQL)


def _row_to_user(row: sqlite3.Row) -> AdminUser:
    return AdminUser(
        id=row["id"],
        email=row["email"],
        role=Role(row["role"]),
        is_active=bool(row["is_active"]),
        created_at=row["created_at"],
    )


def create_admin_user(
    db_path: str | Path,
    *,
    email: str,
    role: Role,
    password: str | None = None,
) -> AdminUser:
    """Insert a new admin. Password is optional for OTP/magic-link projects."""
    email = email.strip().lower()
    if not email or "@" not in email:
        raise AdminUserError(f"invalid email: {email!r}")
    user = AdminUser(
        id=str(uuid.uuid4()),
        email=email,
        role=role,
        is_active=True,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    ensure_admin_schema(db_path)
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        try:
            conn.execute(
                "INSERT INTO admin_users (id, email, password_hash, role, is_active, created_at) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (
                    user.id,
                    user.email,
                    hash_password(password) if password else None,
                    user.role.value,
                    user.created_at,
                ),
            )
        except sqlite3.IntegrityError as e:
            raise AdminUserError(f"email already exists: {email!r}") from e
    return user


def get_admin_user(
    db_path: str | Path, *, email: str | None = None, user_id: str | None = None
) -> AdminUser | None:
    if not email and not user_id:
        raise AdminUserError("get_admin_user requires email or user_id")
    ensure_admin_schema(db_path)
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        if email is not None:
            row = conn.execute(
                "SELECT * FROM admin_users WHERE email = ? LIMIT 1", (email.strip().lower(),)
            ).fetchone()
        else:
            row = conn.execute("SELECT * FROM admin_users WHERE id = ? LIMIT 1", (user_id,)).fetchone()
    return _row_to_user(row) if row else None


def list_admin_users(db_path: str | Path) -> list[AdminUser]:
    ensure_admin_schema(db_path)
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM admin_users ORDER BY created_at").fetchall()
    return [_row_to_user(r) for r in rows]


def update_admin_password(db_path: str | Path, *, user_id: str, new_password: str) -> None:
    if not new_password:
        raise AdminUserError("new password must not be empty")
    ensure_admin_schema(db_path)
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        cursor = conn.execute(
            "UPDATE admin_users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        if cursor.rowcount == 0:
            raise AdminUserError(f"admin user not found: {user_id!r}")


def delete_admin_user(db_path: str | Path, *, user_id: str) -> None:
    ensure_admin_schema(db_path)
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        cursor = conn.execute("DELETE FROM admin_users WHERE id = ?", (user_id,))
        if cursor.rowcount == 0:
            raise AdminUserError(f"admin user not found: {user_id!r}")


def verify_admin_password(db_path: str | Path, *, email: str, password: str) -> AdminUser | None:
    """Return the user if the password matches; ``None`` otherwise. Constant-ish time.

    M8: single SELECT that fetches the row + password hash together, instead of
    the prior two-query dance (``get_admin_user`` + extra ``SELECT password_hash``).
    """
    ensure_admin_schema(db_path)
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM admin_users WHERE email = ? LIMIT 1",
            (email.strip().lower(),),
        ).fetchone()
    stored_hash = row["password_hash"] if row else ""
    # Always run verify_password, even for unknown emails, to avoid timing leaks.
    ok = verify_password(password, stored_hash or "")
    if not ok or row is None:
        return None
    user = _row_to_user(row)
    return user if user.is_active else None
