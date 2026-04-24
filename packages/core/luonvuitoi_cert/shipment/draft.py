"""Shipment draft state machine — forward half of the shipping lifecycle.

Admins curate a list of students to ship (filter by column value, result
tier, or external Excel list), export to carrier-ready Excel, then hard-lock
the batch. Once a carrier returns tracking data, the import pipeline
(see ``bulk_import.py``) promotes matching drafts into ``shipment_history``.

State machine
-------------
``draft``     — added, editable, not exported
``exported``  — included in an export; HARD-LOCKED (immutable; cancel only)
``cancelled`` — admin voided before or after export
``promoted``  — bulk_import matched a tracking_code; see shipment_history for
                the live delivery status

Schema lives in ``shipment_draft`` table (separate from ``shipment_history``).
Composite PK ``(round_id, sbd)`` — one draft per student per round. Creating
a second draft for the same (round, sbd) while the first is still ``draft``
replaces it; second draft while first is ``exported`` raises unless
``--force`` (not implemented — hard lock means cancel first).
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from luonvuitoi_cert.auth.activity_log import ActivityLog, log_admin_action
from luonvuitoi_cert.auth.admin_db import Role
from luonvuitoi_cert.auth.tokens import TokenError, verify_admin_token
from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.shipment.bulk_import import _iso_now  # reuse

_DRAFT_SCHEMA = """
CREATE TABLE IF NOT EXISTS shipment_draft (
    id TEXT PRIMARY KEY,
    round_id TEXT NOT NULL,
    sbd TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('draft','exported','cancelled','promoted')),
    carrier TEXT,
    batch_id TEXT,
    exported_at TEXT,
    promoted_at TEXT,
    tracking_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    note TEXT,
    UNIQUE (round_id, sbd, status)
);
CREATE INDEX IF NOT EXISTS idx_shipment_draft_round ON shipment_draft(round_id, status);
CREATE INDEX IF NOT EXISTS idx_shipment_draft_batch ON shipment_draft(batch_id);
"""


class DraftError(Exception):
    """Raised for invalid tokens, bad filters, lock violations, missing template."""


@dataclass(frozen=True, slots=True)
class DraftRow:
    id: str
    round_id: str
    sbd: str
    status: str
    carrier: str | None
    batch_id: str | None
    exported_at: str | None
    promoted_at: str | None
    tracking_code: str | None
    created_at: str
    updated_at: str
    snapshot: dict[str, str] = field(default_factory=dict)
    note: str | None = None


@dataclass(frozen=True, slots=True)
class ExportResult:
    batch_id: str
    carrier: str
    round_id: str
    row_count: int
    file_bytes: bytes
    filename: str


# ---------- helpers ---------------------------------------------------------


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_DRAFT_SCHEMA)


def _verify_admin(params: dict[str, Any], env: dict[str, str] | None, kv: object | None) -> tuple[str, str]:
    try:
        token = verify_admin_token(str(params.get("token", "")).strip(), env=env, kv=kv)  # type: ignore[arg-type]
    except TokenError as e:
        raise DraftError(str(e)) from e
    if token.role not in (Role.ADMIN, Role.SUPER_ADMIN):
        raise DraftError(f"role {token.role.value!r} cannot manage drafts")
    return token.user_id, token.email


def _row_to_draft(row: sqlite3.Row) -> DraftRow:
    import json as _json

    return DraftRow(
        id=row["id"],
        round_id=row["round_id"],
        sbd=row["sbd"],
        status=row["status"],
        carrier=row["carrier"],
        batch_id=row["batch_id"],
        exported_at=row["exported_at"],
        promoted_at=row["promoted_at"],
        tracking_code=row["tracking_code"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        snapshot=_json.loads(row["snapshot_json"] or "{}"),
        note=row["note"],
    )


def _require_round_table(config: CertConfig, round_id: str) -> str:
    for r in config.rounds:
        if r.id == round_id:
            return r.table
    raise DraftError(f"unknown round_id {round_id!r}; available: {[r.id for r in config.rounds]}")


def _parse_filters(raw: Any) -> dict[str, str]:
    """Accept dict ``{col: value}`` or list of ``"col=value"`` strings."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v}
    if isinstance(raw, list):
        out: dict[str, str] = {}
        for item in raw:
            s = str(item).strip()
            if "=" not in s:
                raise DraftError(f"bad filter expression {item!r} — expected 'column=value'")
            k, v = s.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip()] = v.strip()
        return out
    raise DraftError(f"filters must be dict or list[str], got {type(raw).__name__}")


def _query_students(
    db_path: Path,
    table: str,
    column_filters: dict[str, str],
    result_filter: str | None,
    sbd_list: list[str] | None,
    data_mapping_cols: set[str],
) -> list[dict[str, str]]:
    """Pull rows from students table matching the combined filter set."""
    where: list[str] = []
    args: list[Any] = []
    for col, val in column_filters.items():
        if col not in data_mapping_cols:
            raise DraftError(
                f"filter column {col!r} not in students schema; allowed: {sorted(data_mapping_cols)}"
            )
        where.append(f'LOWER(TRIM("{col}")) = LOWER(?)')
        args.append(val.strip())
    if sbd_list:
        placeholders = ",".join(["?"] * len(sbd_list))
        where.append(f'"sbd" IN ({placeholders})')
        args.extend(sbd_list)
    if result_filter:
        # Match ANY subject column carrying the result token (accent-insensitive
        # by pre-uppercasing both sides; students table already stores them
        # pre-normalized on ingest).
        subject_clauses = [
            f'UPPER(TRIM("{col}")) = UPPER(?)'
            for col in data_mapping_cols
            if col not in {"sbd", "full_name", "dob", "school", "phone", "grade"}
        ]
        if subject_clauses:
            where.append("(" + " OR ".join(subject_clauses) + ")")
            args.extend([result_filter] * len(subject_clauses))

    sql = f'SELECT * FROM "{table}"'
    if where:
        sql += " WHERE " + " AND ".join(where)

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError as e:
            raise DraftError(f"query failed: {e}") from e
    return [
        {k: (row[k] if row[k] is not None else "") for k in row.keys()}  # noqa: SIM118
        for row in rows
    ]


def _students_columns(config: CertConfig) -> set[str]:
    m = config.data_mapping
    cols = {m.sbd_col, m.name_col}
    for c in (m.dob_col, m.school_col, m.grade_col, m.phone_col):
        if c:
            cols.add(c)
    cols.update(m.extra_cols)
    for s in config.subjects:
        cols.add(s.db_col)
    return cols


# ---------- public API ------------------------------------------------------


def draft_add(
    *,
    config: CertConfig,
    db_path: str | Path,
    activity: ActivityLog,
    params: dict[str, Any],
    env: dict[str, str] | None = None,
    kv: object | None = None,
    client_ip: str | None = None,
) -> list[DraftRow]:
    """Create drafts from a student filter. Returns newly-created rows.

    Accepted params:
        - ``round_id`` (required)
        - ``filters`` (optional dict or list[str] "col=value")
        - ``result`` (optional) — match any subject column
        - ``sbd_list`` (optional list[str]) — restrict to known SBDs
        - ``note`` (optional) — stamp onto every draft

    At least one of ``filters`` / ``result`` / ``sbd_list`` must be non-empty
    so ``add`` can never accidentally target the whole student table.
    """
    import json as _json

    user_id, user_email = _verify_admin(params, env, kv)
    round_id = str(params.get("round_id", "")).strip()
    round_table = _require_round_table(config, round_id)
    filters = _parse_filters(params.get("filters"))
    result_filter = str(params.get("result", "") or "").strip() or None
    sbd_list = params.get("sbd_list") or None
    if sbd_list is not None and not isinstance(sbd_list, list):
        raise DraftError("sbd_list must be a list of strings")
    note = str(params.get("note", "") or "").strip() or None

    if not (filters or result_filter or sbd_list):
        raise DraftError(
            "must supply at least one of filters / result / sbd_list — refusing to draft the entire round"
        )

    columns = _students_columns(config)
    rows = _query_students(
        Path(db_path).expanduser().resolve(),
        round_table,
        filters,
        result_filter,
        [str(s).strip() for s in (sbd_list or []) if str(s).strip()],
        columns,
    )

    now = _iso_now()
    created: list[DraftRow] = []
    sbd_col = config.data_mapping.sbd_col
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        _ensure_schema(conn)
        for row in rows:
            sbd = str(row.get(sbd_col, "")).strip()
            if not sbd:
                continue
            # Skip if an active draft/exported already exists for this (round, sbd)
            existing = conn.execute(
                "SELECT id, status FROM shipment_draft "
                "WHERE round_id = ? AND sbd = ? AND status IN ('draft','exported')",
                (round_id, sbd),
            ).fetchone()
            if existing is not None:
                continue
            draft_id = str(uuid.uuid4())
            snapshot = _json.dumps(row, ensure_ascii=False)
            conn.execute(
                "INSERT INTO shipment_draft "
                "(id, round_id, sbd, status, created_at, updated_at, snapshot_json, note) "
                "VALUES (?, ?, ?, 'draft', ?, ?, ?, ?)",
                (draft_id, round_id, sbd, now, now, snapshot, note),
            )
            created.append(
                DraftRow(
                    id=draft_id,
                    round_id=round_id,
                    sbd=sbd,
                    status="draft",
                    carrier=None,
                    batch_id=None,
                    exported_at=None,
                    promoted_at=None,
                    tracking_code=None,
                    created_at=now,
                    updated_at=now,
                    snapshot=row,
                    note=note,
                )
            )

    log_admin_action(
        activity,
        user_id=user_id,
        user_email=user_email,
        action="shipment.draft.add",
        target_id=round_id,
        metadata={
            "created": len(created),
            "matched_students": len(rows),
            "filters": sorted(filters),
            "has_result": bool(result_filter),
            "has_sbd_list": bool(sbd_list),
        },
        ip=client_ip,
    )
    return created


def draft_list(
    *,
    config: CertConfig,
    db_path: str | Path,
    params: dict[str, Any],
    env: dict[str, str] | None = None,
    kv: object | None = None,
) -> list[DraftRow]:
    """List drafts, optionally filtered by round_id / status / batch_id."""
    _verify_admin(params, env, kv)
    round_id = str(params.get("round_id", "") or "").strip() or None
    status = str(params.get("status", "") or "").strip() or None
    batch_id = str(params.get("batch_id", "") or "").strip() or None
    limit = int(params.get("limit") or 500)
    if limit < 1 or limit > 5000:
        raise DraftError("limit must be 1..5000")

    where: list[str] = []
    args: list[Any] = []
    if round_id:
        where.append("round_id = ?")
        args.append(round_id)
    if status:
        where.append("status = ?")
        args.append(status)
    if batch_id:
        where.append("batch_id = ?")
        args.append(batch_id)

    sql = "SELECT * FROM shipment_draft"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY updated_at DESC, rowid DESC LIMIT ?"
    args.append(limit)

    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError:
            return []
    return [_row_to_draft(r) for r in rows]


def draft_cancel(
    *,
    config: CertConfig,
    db_path: str | Path,
    activity: ActivityLog,
    params: dict[str, Any],
    env: dict[str, str] | None = None,
    kv: object | None = None,
    client_ip: str | None = None,
) -> int:
    """Cancel drafts by id list. Returns number of rows affected.

    Exported drafts *can* be cancelled (operator caught a mistake after
    export) but the carrier upload has already happened — follow up with
    carrier to void the actual shipment.
    """
    user_id, user_email = _verify_admin(params, env, kv)
    ids = params.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise DraftError("ids must be a non-empty list")
    now = _iso_now()
    placeholders = ",".join(["?"] * len(ids))
    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        _ensure_schema(conn)
        cursor = conn.execute(
            f"UPDATE shipment_draft SET status='cancelled', updated_at=? "
            f"WHERE id IN ({placeholders}) AND status IN ('draft','exported')",
            [now, *ids],
        )
        affected = cursor.rowcount or 0

    log_admin_action(
        activity,
        user_id=user_id,
        user_email=user_email,
        action="shipment.draft.cancel",
        target_id="*",
        metadata={"cancelled": affected, "requested": len(ids)},
        ip=client_ip,
    )
    return affected


def draft_export(
    *,
    config: CertConfig,
    db_path: str | Path,
    activity: ActivityLog,
    params: dict[str, Any],
    env: dict[str, str] | None = None,
    kv: object | None = None,
    client_ip: str | None = None,
) -> ExportResult:
    """Export all 'draft'-status rows for (round, carrier) to a carrier-ready
    Excel file. Marks them 'exported' with a shared batch_id — HARD LOCK.
    """
    user_id, user_email = _verify_admin(params, env, kv)
    round_id = str(params.get("round_id", "")).strip()
    _require_round_table(config, round_id)
    carrier = str(params.get("carrier", "")).strip()
    if not carrier:
        raise DraftError("carrier is required for export")

    if config.features.shipment.import_ is None:
        raise DraftError("features.shipment.import is not configured")
    profile = config.features.shipment.import_.profiles.get(carrier)
    if profile is None:
        raise DraftError(f"unknown carrier {carrier!r}")
    if profile.export_template is None:
        raise DraftError(
            f"carrier {carrier!r} has no export_template — add features.shipment.import.profiles.{carrier}.export_template"
        )

    batch_id = str(uuid.uuid4())
    now = _iso_now()

    with closing(sqlite3.connect(str(db_path))) as conn, conn:
        _ensure_schema(conn)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM shipment_draft WHERE round_id = ? AND status = 'draft' ORDER BY created_at",
            (round_id,),
        ).fetchall()
        drafts = [_row_to_draft(r) for r in rows]
        if not drafts:
            raise DraftError(f"no 'draft'-status rows for round_id={round_id!r}")

        ids = [d.id for d in drafts]
        placeholders = ",".join(["?"] * len(ids))
        conn.execute(
            f"UPDATE shipment_draft "
            f"SET status='exported', carrier=?, batch_id=?, exported_at=?, updated_at=? "
            f"WHERE id IN ({placeholders})",
            [carrier, batch_id, now, now, *ids],
        )

    # Build the Excel
    tpl = profile.export_template
    header: list[tuple[str, str]] = []  # (logical_field, header_name)
    if tpl.sbd:
        header.append((config.data_mapping.sbd_col, tpl.sbd))
    if tpl.full_name:
        header.append((config.data_mapping.name_col, tpl.full_name))
    if tpl.phone and config.data_mapping.phone_col:
        header.append((config.data_mapping.phone_col, tpl.phone))
    if tpl.address:
        header.append(("__template_blank__address__", tpl.address))
    if tpl.recipient:
        header.append(("__template_blank__recipient__", tpl.recipient))
    if tpl.weight:
        header.append(("__template_blank__weight__", tpl.weight))
    if tpl.cod:
        header.append(("__template_blank__cod__", tpl.cod))
    if tpl.note:
        header.append(("__template_blank__note__", tpl.note))
    for logical, carrier_header in tpl.extra_columns.items():
        header.append((logical, carrier_header))

    wb = Workbook()
    ws = wb.active
    ws.append([h[1] for h in header])
    for d in drafts:
        row_cells: list[str] = []
        for logical, _ in header:
            if logical.startswith("__template_blank__"):
                row_cells.append("")
            else:
                row_cells.append(str(d.snapshot.get(logical, "")))
        ws.append(row_cells)

    import io

    buf = io.BytesIO()
    wb.save(buf)
    file_bytes = buf.getvalue()
    filename = f"{round_id}-{carrier}-{batch_id[:8]}.xlsx"

    log_admin_action(
        activity,
        user_id=user_id,
        user_email=user_email,
        action="shipment.export",
        target_id=f"{round_id}:{carrier}",
        metadata={
            "batch_id": batch_id,
            "row_count": len(drafts),
            "carrier": carrier,
        },
        ip=client_ip,
    )
    return ExportResult(
        batch_id=batch_id,
        carrier=carrier,
        round_id=round_id,
        row_count=len(drafts),
        file_bytes=file_bytes,
        filename=filename,
    )
