"""Derive the ``shipments`` SQLite table from :class:`CertConfig`.

Fixed columns (``id`` PK, ``round_id``, ``sbd``, ``status``, ``created_at``,
``updated_at``) + one TEXT column per entry in
``config.features.shipment.fields``. ``(round_id, sbd)`` is UNIQUE so upserts
are well-defined. All columns are TEXT — same rationale as the students
schema.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from luonvuitoi_cert.config import CertConfig


class ShipmentSchemaError(Exception):
    """Raised when the config shouldn't produce a valid shipment schema."""


FIXED_COLUMNS: tuple[str, ...] = ("id", "round_id", "sbd", "status", "created_at", "updated_at")


def build_shipment_schema(config: CertConfig) -> str:
    """Return the ``CREATE TABLE IF NOT EXISTS shipments`` SQL for ``config``."""
    if not config.features.shipment.enabled:
        raise ShipmentSchemaError("shipment feature is disabled; no schema to build")
    extra = config.features.shipment.fields
    columns = [
        '"id" TEXT PRIMARY KEY',
        '"round_id" TEXT NOT NULL',
        '"sbd" TEXT NOT NULL',
        '"status" TEXT NOT NULL',
        '"created_at" TEXT NOT NULL',
        '"updated_at" TEXT NOT NULL',
    ]
    columns.extend(f'"{col}" TEXT' for col in extra)
    columns.append('UNIQUE("round_id", "sbd")')
    body = ",\n  ".join(columns)
    return f"CREATE TABLE IF NOT EXISTS shipments (\n  {body}\n);"


def ensure_shipment_schema(db_path: str | Path, config: CertConfig) -> None:
    """Create the shipments table on ``db_path`` if it doesn't exist."""
    sql = build_shipment_schema(config)
    p = Path(db_path).expanduser().resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(str(p))) as conn, conn:
        conn.execute(sql)
