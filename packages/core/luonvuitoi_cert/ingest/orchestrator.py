"""Turn raw source rows into SQLite inserts for a single round.

Usage:

.. code-block:: python

    rows = read_excel(xlsx_path)
    result = ingest_rows(config, db_path, round_id="main", rows=rows)
    print(result.summary())

The orchestrator owns three concerns:

1. **Schema bootstrap** — calls :func:`build_schema` and runs the generated
   ``CREATE TABLE IF NOT EXISTS`` statements idempotently.
2. **Column projection** — drops source columns the config doesn't declare;
   fills missing declared columns with the empty string.
3. **Duplicate policy** — ``warn`` (default, records dup as a warning and
   keeps the first), ``skip`` (silent), or ``replace`` (overwrite).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Literal

from luonvuitoi_cert.config import CertConfig
from luonvuitoi_cert.ingest.base import IngestError, IngestResult
from luonvuitoi_cert.storage.sqlite_schema import build_schema

DuplicatePolicy = Literal["warn", "skip", "replace"]


def _target_columns(config: CertConfig) -> list[str]:
    """Ordered list of column names expected in the DB, identical across rounds."""
    tables = build_schema(config)
    return [c.name for c in tables[0].columns]


def _find_round_table(config: CertConfig, round_id: str) -> str:
    for r in config.rounds:
        if r.id == round_id:
            return r.table
    raise IngestError(
        f"round_id {round_id!r} not found in config.rounds "
        f"(available: {[r.id for r in config.rounds]})"
    )


def _apply_schema(conn: sqlite3.Connection, config: CertConfig) -> None:
    for t in build_schema(config):
        conn.execute(t.create_sql())
    conn.commit()


def ingest_rows(
    config: CertConfig,
    db_path: str | Path,
    round_id: str,
    rows: Iterable[dict[str, object]],
    *,
    on_duplicate: DuplicatePolicy = "warn",
) -> IngestResult:
    """Insert ``rows`` into the round's table, honoring ``on_duplicate`` policy."""
    table = _find_round_table(config, round_id)
    columns = _target_columns(config)
    sbd_col = config.data_mapping.sbd_col
    placeholders = ", ".join(["?"] * len(columns))
    quoted_cols = ", ".join(f'"{c}"' for c in columns)

    if on_duplicate == "replace":
        sql = f'INSERT OR REPLACE INTO "{table}" ({quoted_cols}) VALUES ({placeholders})'
    else:
        sql = f'INSERT OR IGNORE INTO "{table}" ({quoted_cols}) VALUES ({placeholders})'

    result = IngestResult()
    db_path = Path(db_path).expanduser().resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(str(db_path)) as conn:
        _apply_schema(conn, config)
        for idx, row in enumerate(rows, start=1):
            sbd = str(row.get(sbd_col, "")).strip()
            if not sbd:
                result.rows_skipped += 1
                result.warn(f"row #{idx} missing {sbd_col!r}; skipped")
                continue
            values = [sbd] + [str(row.get(c, "") or "").strip() for c in columns[1:]]
            before = conn.total_changes
            conn.execute(sql, values)
            if conn.total_changes == before:
                # INSERT OR IGNORE no-op → duplicate SBD
                result.rows_skipped += 1
                if on_duplicate == "warn":
                    result.warn(f"duplicate {sbd_col}={sbd!r} at row #{idx}; kept first entry")
                continue
            result.rows_inserted += 1
        conn.commit()
    return result
