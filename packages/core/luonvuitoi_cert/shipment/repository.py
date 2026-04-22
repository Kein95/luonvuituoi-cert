"""CRUD for the shipments table.

One record per ``(round_id, sbd)`` pair. Upsert-by-composite-key so admin
updates and initial creates share the same entry point. ``status`` must
belong to ``config.features.shipment.statuses`` at write time.
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.shipment.schema import FIXED_COLUMNS, ensure_shipment_schema


class ShipmentError(Exception):
    """Raised for unknown statuses, unknown extra fields, or missing rows."""


@dataclass(slots=True)
class ShipmentRecord:
    id: str
    round_id: str
    sbd: str
    status: str
    created_at: str
    updated_at: str
    fields: dict[str, str] = field(default_factory=dict)


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _validate_status(config: CertConfig, status: str) -> str:
    if status not in config.features.shipment.statuses:
        raise ShipmentError(
            f"status {status!r} not in config.features.shipment.statuses "
            f"({config.features.shipment.statuses})"
        )
    return status


def _validate_extra_fields(config: CertConfig, fields_patch: dict[str, object]) -> dict[str, str]:
    allowed = set(config.features.shipment.fields)
    unknown = set(fields_patch) - allowed
    if unknown:
        raise ShipmentError(f"unknown shipment fields: {sorted(unknown)}; allowed: {sorted(allowed)}")
    return {k: "" if v is None else str(v) for k, v in fields_patch.items()}


def _row_to_record(row: sqlite3.Row, extra_cols: list[str]) -> ShipmentRecord:
    return ShipmentRecord(
        id=row["id"],
        round_id=row["round_id"],
        sbd=row["sbd"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        fields={col: str(row[col] or "") for col in extra_cols},
    )


def upsert_shipment(
    db_path: str | Path,
    config: CertConfig,
    *,
    round_id: str,
    sbd: str,
    status: str,
    fields: dict[str, object] | None = None,
    clock=None,  # type: ignore[no-untyped-def]
) -> ShipmentRecord:
    """Create or update the shipment for ``(round_id, sbd)`` atomically.

    Uses SQLite ``ON CONFLICT DO UPDATE`` so concurrent admins pressing Save
    on the same record don't race each other into an IntegrityError. Patch
    semantics on conflict: ``status`` + ``updated_at`` always land; each
    extra field lands only when the caller includes it in ``fields``,
    otherwise the existing value is preserved.
    """
    _validate_status(config, status)
    cleaned_fields = _validate_extra_fields(config, fields or {})
    now = (clock or _iso_now)() if callable(clock) else _iso_now()
    ensure_shipment_schema(db_path, config)

    extra_cols = list(config.features.shipment.fields)
    new_id = str(uuid.uuid4())
    insert_cols = ["id", "round_id", "sbd", "status", "created_at", "updated_at", *extra_cols]
    insert_values: list[object] = [new_id, round_id, sbd, status, now, now] + [
        cleaned_fields.get(c, "") for c in extra_cols
    ]
    placeholders = ", ".join(["?"] * len(insert_cols))
    quoted_insert = ", ".join(f'"{c}"' for c in insert_cols)

    update_parts = ['"status" = excluded."status"', '"updated_at" = excluded."updated_at"']
    for col in extra_cols:
        if col in cleaned_fields:
            update_parts.append(f'"{col}" = excluded."{col}"')

    sql = (
        f"INSERT INTO shipments ({quoted_insert}) VALUES ({placeholders}) "
        f'ON CONFLICT("round_id", "sbd") DO UPDATE SET {", ".join(update_parts)}'
    )
    with closing(sqlite3.connect(str(Path(db_path).expanduser().resolve()))) as conn, conn:
        conn.row_factory = sqlite3.Row
        conn.execute(sql, insert_values)
        row = conn.execute(
            "SELECT * FROM shipments WHERE round_id = ? AND sbd = ? LIMIT 1",
            (round_id, sbd),
        ).fetchone()
    assert row is not None
    return _row_to_record(row, extra_cols)


def get_shipment(
    db_path: str | Path, config: CertConfig, *, round_id: str, sbd: str
) -> ShipmentRecord | None:
    ensure_shipment_schema(db_path, config)
    extra_cols = list(config.features.shipment.fields)
    with closing(sqlite3.connect(str(Path(db_path).expanduser().resolve()))) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM shipments WHERE round_id = ? AND sbd = ? LIMIT 1",
            (round_id, sbd),
        ).fetchone()
    return _row_to_record(row, extra_cols) if row else None


MAX_LIST_LIMIT = 500


def list_shipments(
    db_path: str | Path,
    config: CertConfig,
    *,
    status: str | None = None,
    round_id: str | None = None,
    limit: int = 200,
) -> list[ShipmentRecord]:
    ensure_shipment_schema(db_path, config)
    extra_cols = list(config.features.shipment.fields)
    clamped_limit = max(1, min(int(limit), MAX_LIST_LIMIT))
    sql = "SELECT * FROM shipments"
    where: list[str] = []
    params: list[object] = []
    if status is not None:
        _validate_status(config, status)
        where.append('"status" = ?')
        params.append(status)
    if round_id is not None:
        where.append('"round_id" = ?')
        params.append(round_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += ' ORDER BY "updated_at" DESC LIMIT ?'
    params.append(clamped_limit)
    with closing(sqlite3.connect(str(Path(db_path).expanduser().resolve()))) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    # Explicit loop so the unused _FIXED import reference stays obvious.
    _ = FIXED_COLUMNS
    return [_row_to_record(r, extra_cols) for r in rows]
