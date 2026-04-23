"""Admin-only list/filter endpoint.

Unlike the student portal (which demands SBD + CAPTCHA and returns exactly
one row), admins often need to *browse* — "show me everyone whose name
starts with Nguyen" or "everyone with DOB 01/01/2010." This handler returns
up to ``MAX_LIST_RESULTS`` matches per round with minimal row data and
records an ``admin.search`` entry in the activity log so read actions are
auditable alongside the existing write actions.

Accent-tolerant name match piggybacks on :func:`search._strip_accents_upper`.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from luonvuitoi_cert.api.search import _normalize_dob, _strip_accents_upper
from luonvuitoi_cert.api.security import SecurityError
from luonvuitoi_cert.auth.activity_log import ActivityLog, log_admin_action
from luonvuitoi_cert.auth.admin_db import Role
from luonvuitoi_cert.auth.tokens import TokenError, verify_admin_token
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.storage.kv.base import KVBackend

MAX_LIST_RESULTS = 50
MIN_NAME_PREFIX = 2  # Reject 1-char queries — would return most of the DB.


class AdminListError(Exception):
    """Raised for unauthenticated callers, bad filters, or over-limit queries."""


@dataclass(frozen=True, slots=True)
class AdminListRow:
    sbd: str
    name: str
    round_id: str
    round_label: str
    fields: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AdminListResponse:
    total: int
    truncated: bool
    rows: list[AdminListRow] = field(default_factory=list)


def admin_list_students(
    *,
    config: CertConfig,
    db_path: str | Path,
    activity: ActivityLog,
    params: dict[str, Any],
    client_ip: str | None = None,
    env: dict[str, str] | None = None,
    kv: KVBackend | None = None,
) -> AdminListResponse:
    """Filter + paginate students for an authenticated admin.

    Accepted filter keys in ``params`` (any non-empty subset, must supply at
    least one): ``name`` (accent-tolerant prefix, ≥2 chars), ``sbd``,
    ``dob`` (DD/MM/YYYY or YYYY-MM-DD), ``phone`` (last-4 digits),
    ``round_id`` (restrict to one round).

    ``token`` is the admin JWT. Viewer role can read; only admin/super-admin
    can write (enforced by other handlers).
    """
    try:
        token = verify_admin_token(str(params.get("token", "")).strip(), env=env, kv=kv)
    except TokenError as e:
        raise AdminListError(str(e)) from e

    name_query = str(params.get("name", "") or "").strip()
    sbd_query = str(params.get("sbd", "") or "").strip()
    dob_raw = str(params.get("dob", "") or "").strip()
    phone_query = str(params.get("phone", "") or "").strip()
    round_filter = str(params.get("round_id", "") or "").strip() or None

    if not any([name_query, sbd_query, dob_raw, phone_query]):
        raise SecurityError("at least one filter required (name, sbd, dob, phone)")
    if name_query and len(name_query) < MIN_NAME_PREFIX:
        raise SecurityError(f"name filter must be ≥ {MIN_NAME_PREFIX} chars")

    name_norm = _strip_accents_upper(name_query) if name_query else ""
    dob_norm = _normalize_dob(dob_raw) if dob_raw else ""
    phone_last4 = phone_query[-4:] if phone_query else ""

    rounds = [r for r in config.rounds if r.id == round_filter] if round_filter else list(config.rounds)
    if round_filter and not rounds:
        raise AdminListError(f"unknown round_id: {round_filter!r}")

    m = config.data_mapping
    matches: list[AdminListRow] = []
    total = 0

    with closing(sqlite3.connect(str(Path(db_path).expanduser().resolve()))) as conn:
        conn.row_factory = sqlite3.Row
        for r in rounds:
            rows = conn.execute(f'SELECT * FROM "{r.table}"').fetchall()
            for row in rows:
                # sqlite3.Row iterates values by default; .keys() is the
                # correct accessor for column names. ruff SIM118 misfires here.
                row_dict = {k: (row[k] if row[k] is not None else "") for k in row.keys()}  # noqa: SIM118
                if sbd_query and row_dict.get(m.sbd_col, "") != sbd_query:
                    continue
                if name_norm and name_norm not in _strip_accents_upper(row_dict.get(m.name_col, "")):
                    continue
                if dob_norm:
                    if not m.dob_col:
                        continue
                    if _normalize_dob(row_dict.get(m.dob_col, "")) != dob_norm:
                        continue
                if phone_last4:
                    if not m.phone_col:
                        continue
                    if str(row_dict.get(m.phone_col, ""))[-4:] != phone_last4:
                        continue
                total += 1
                if len(matches) < MAX_LIST_RESULTS:
                    matches.append(
                        AdminListRow(
                            sbd=str(row_dict.get(m.sbd_col, "")),
                            name=str(row_dict.get(m.name_col, "")),
                            round_id=r.id,
                            round_label=r.label,
                            fields={k: str(v) for k, v in row_dict.items()},
                        )
                    )

    log_admin_action(
        activity,
        user_id=token.user_id,
        user_email=token.email,
        action="admin.list",
        target_id=round_filter or "*",
        metadata={
            "filters": sorted(
                [
                    k
                    for k, v in {
                        "name": name_query,
                        "sbd": sbd_query,
                        "dob": dob_raw,
                        "phone": phone_query,
                    }.items()
                    if v
                ]
            ),
            "total": total,
            "role": token.role.value if isinstance(token.role, Role) else str(token.role),
        },
        ip=client_ip,
    )
    return AdminListResponse(total=total, truncated=total > len(matches), rows=matches)
