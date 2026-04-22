"""Admin handler — update one field on a student record, with audit trail.

Authorization:
- Viewer role: rejected (read-only).
- Admin / Super-admin: allowed to update any declared data_mapping column or
  subject ``db_col``.

Validation:
- Column name must be in the config-derived schema for the target round.
- Old and new values are recorded in the activity log as metadata so reversals
  are straightforward.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from luonvuitoi_cert.api.security import SecurityError, validate_sbd
from luonvuitoi_cert.auth.activity_log import ActivityLog, log_admin_action
from luonvuitoi_cert.auth.admin_db import Role
from luonvuitoi_cert.auth.tokens import TokenError, verify_admin_token
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.storage.sqlite_schema import build_schema


class AdminUpdateError(Exception):
    """Raised when the update can't be applied (permission, missing target, bad column)."""


@dataclass(slots=True)
class UpdateResponse:
    sbd: str
    column: str
    old_value: str
    new_value: str
    changed: bool


def _allowed_columns(config: CertConfig) -> set[str]:
    return {c.name for c in build_schema(config)[0].columns}


def _find_round_table(config: CertConfig, round_id: str) -> str:
    for r in config.rounds:
        if r.id == round_id:
            return r.table
    raise AdminUpdateError(f"unknown round_id {round_id!r}; available: {[r.id for r in config.rounds]}")


def update_student_field(
    *,
    config: CertConfig,
    db_path: str | Path,
    activity: ActivityLog,
    params: dict[str, Any],
    client_ip: str | None = None,
    env: dict[str, str] | None = None,
) -> UpdateResponse:
    """Authorize the caller, apply the update, and write an audit entry."""
    token_raw = str(params.get("token", "")).strip()
    try:
        token = verify_admin_token(token_raw, env=env)
    except TokenError as e:
        raise AdminUpdateError(str(e)) from e
    # Allowlist rather than denylist — any future role (e.g. Role.AUDITOR) is
    # read-only by default until explicitly granted write access.
    if token.role not in (Role.ADMIN, Role.SUPER_ADMIN):
        raise AdminUpdateError(f"role {token.role.value!r} is read-only")

    sbd = validate_sbd(params.get("sbd"))
    round_id = str(params.get("round_id", "")).strip()
    column = str(params.get("column", "")).strip()
    new_value = params.get("new_value")
    if new_value is None:
        raise SecurityError("new_value is required")
    new_value_str = str(new_value)

    if column not in _allowed_columns(config):
        raise AdminUpdateError(
            f"column {column!r} is not in the schema; allowed: {sorted(_allowed_columns(config))}"
        )
    if column == config.data_mapping.sbd_col:
        raise AdminUpdateError("refusing to change primary key; delete + re-insert instead")

    table = _find_round_table(config, round_id)
    sbd_col = config.data_mapping.sbd_col

    with closing(sqlite3.connect(str(Path(db_path).expanduser().resolve()))) as conn, conn:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(f'SELECT * FROM "{table}" WHERE "{sbd_col}" = ? LIMIT 1', (sbd,)).fetchone()
        if existing is None:
            raise AdminUpdateError(f"no row in {table!r} with {sbd_col}={sbd!r}")
        old_value = str(existing[column] or "")
        if old_value == new_value_str:
            changed = False
        else:
            conn.execute(
                f'UPDATE "{table}" SET "{column}" = ? WHERE "{sbd_col}" = ?',
                (new_value_str, sbd),
            )
            changed = True

    # M5: never persist raw cell values in the audit log. The caller knows what
    # they sent (via the API response); downstream webhook forwarders (GSheet)
    # should only see that a change happened, not phone/DOB/address contents.
    # ``value_length_delta`` preserves rough observability without leaking PII.
    log_admin_action(
        activity,
        user_id=token.user_id,
        user_email=token.email,
        action="student.update",
        target_id=f"{table}:{sbd}",
        metadata={
            "column": column,
            "changed": changed,
            "value_length_delta": len(new_value_str) - len(old_value),
        },
        ip=client_ip,
    )
    return UpdateResponse(
        sbd=sbd, column=column, old_value=old_value, new_value=new_value_str, changed=changed
    )
